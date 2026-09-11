from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .adapters import build_adapter
from .config import project_config
from .executor_client import DdevExecutorClient
from .fingerprint import failure_fingerprint
from .prompts import evaluator_prompt, execution_prompt, planning_prompt
from .repo import analyze_repo, commit_changes, diff_state
from .router_client import RouterClient
from .storage import Storage
from .usage import estimated_cost_usd, normalize_usage


TERMINAL = {"completed", "blocked", "failed", "cancelled", "waiting_human"}


class RuntimeEngine:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.router = RouterClient()
        self.ddev = DdevExecutorClient()
        self.workspace_root = Path(os.getenv("CODING_WORKSPACES_ROOT", "/workspaces")).resolve()
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.storage.init()
        # A process crash must not silently replay a side-effecting agent turn.
        # Queue jobs are safe to retry; in-flight jobs become interrupted.
        for job in self.storage.list(limit=500):
            if job["status"] == "queued":
                await self.queue.put(job["id"])
            elif job["status"] not in TERMINAL:
                self.storage.update(job["id"], status="interrupted", error="Runtime restarted during an in-flight job; explicit resume required.")
        self.worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, job_id: str) -> None:
        await self.queue.put(job_id)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                await self.run_job(job_id)
            except Exception as exc:  # final containment boundary
                self.storage.update(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
            finally:
                self.queue.task_done()

    def create_job(self, payload: dict[str, Any]) -> str:
        # Validate registration only. The runtime intentionally cannot see the
        # source-repository root; the constrained executor owns repo/workspace ops.
        project_config(payload["project_id"])
        job_id = uuid.uuid4().hex
        self.storage.create({
            "id": job_id,
            "project_id": payload["project_id"],
            "status": "queued",
            "source_commit": payload.get("source_commit"),
            "task": payload["task"],
            "repo_analysis": {"hints": payload.get("repo_hints", {}), "provider_state": payload.get("provider_state", {})},
            "progress": self._new_progress(),
            "dry_run": bool(payload.get("dry_run", False)),
        })
        return job_id

    @staticmethod
    def _new_progress() -> dict[str, Any]:
        return {
            "iteration": 0, "repair_iterations": 0, "escalations": 0, "provider_failovers": 0, "model_failovers": 0, "model_calls": 0,
            "tool_calls": 0, "test_runs": 0, "input_tokens": 0, "output_tokens": 0,
            "elapsed_minutes": 0.0, "cost_usd": 0.0,
            "changed_files": 0, "failure_fingerprints": [], "diff_hashes": [], "progress_markers": [],
            "tests_passed": False, "required_checks_passed": False, "material_change_present": False,
            "agent_succeeded": False, "last_agent_failure_kind": None, "unexpected_scope": False,
            "important_decision_flags": [], "provider_failures": [], "agent_attempts": [],
        }

    @staticmethod
    def _remaining_seconds(strategy: dict[str, Any], started: float, per_call_cap: int) -> int:
        total = int(strategy["budget"]["max_wall_time_minutes"] * 60)
        remaining = total - int(time.monotonic() - started)
        if remaining <= 0:
            raise RuntimeError("Job wall-time budget exhausted before next operation")
        return max(10, min(per_call_cap, remaining))

    @staticmethod
    def _record_usage(progress: dict[str, Any], model_id: str, raw_usage: dict[str, Any] | None) -> None:
        usage = normalize_usage(raw_usage)
        progress["input_tokens"] += int(usage["input_tokens"])
        progress["output_tokens"] += int(usage["output_tokens"])
        progress["cost_usd"] = round(
            float(progress.get("cost_usd", 0.0)) + estimated_cost_usd(model_id, raw_usage), 8
        )

    def _cancelled(self, job_id: str) -> bool:
        current = self.storage.get(job_id)
        return bool(current and current["status"] == "cancelled")

    @staticmethod
    def _mark_provider_failure(provider_state: dict[str, Any], choice: dict[str, Any], kind: str) -> None:
        # Resource failures are not reasoning failures. Disable the whole provider
        # for this job so a shared subscription/quota pool cannot immediately
        # reroute to another model from the same exhausted provider.
        provider_key = f"provider:{choice.get('provider')}"
        state = dict(provider_state.get(provider_key) or {})
        state.update({"healthy": False, "available": False, "error_rate": 1.0})
        if kind in {"quota_exhausted", "rate_limited"}:
            state["quota_pressure"] = 1.0
        provider_state[provider_key] = state

    @staticmethod
    def _mark_model_failure(provider_state: dict[str, Any], choice: dict[str, Any], reason: str) -> None:
        # A model can be semantically ineffective even when its provider is healthy
        # (for example a successful CLI turn that produced no required repository change).
        # Exclude only this model for the current job; do not poison the whole provider.
        model_id = str(choice.get("id") or "")
        if not model_id:
            return
        state = dict(provider_state.get(model_id) or {})
        state.update({"healthy": False, "available": False, "error_rate": 1.0})
        provider_state[model_id] = state

    @staticmethod
    def _record_agent_attempt(progress: dict[str, Any], choice: dict[str, Any], run: Any) -> None:
        attempts = progress.setdefault("agent_attempts", [])
        attempts.append({
            "iteration": progress.get("iteration", 0),
            "model": choice.get("id"),
            "provider": choice.get("provider"),
            "adapter": choice.get("adapter"),
            "returncode": run.returncode,
            "failure_kind": run.failure_kind,
            "output_excerpt": (run.output or "")[-4000:],
            "stderr_excerpt": (run.stderr or "")[-4000:],
            "usage": normalize_usage(run.usage),
        })
        # Keep local observability bounded.
        if len(attempts) > 12:
            del attempts[:-12]

    async def _model_failover(
        self, *, route_payload: dict[str, Any], provider_state: dict[str, Any],
        current_choice: dict[str, Any], progress: dict[str, Any], strategy: dict[str, Any],
        reason: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if progress.get("model_failovers", 0) >= int(strategy["budget"].get("max_model_failovers", 2)):
            return None, None
        self._mark_model_failure(provider_state, current_choice, reason)
        payload = dict(route_payload)
        payload["provider_state"] = provider_state
        try:
            reroute = await self.router.route(payload)
        except Exception:
            return None, None
        candidate = reroute.get("strategy", {}).get("executor")
        if not candidate or candidate.get("id") == current_choice.get("id"):
            return None, reroute
        progress["model_failovers"] = int(progress.get("model_failovers", 0)) + 1
        return candidate, reroute

    async def _provider_failover(
        self, *, route_payload: dict[str, Any], provider_state: dict[str, Any],
        current_choice: dict[str, Any], failure_kind: str, progress: dict[str, Any],
        strategy: dict[str, Any], role: str = "executor",
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if progress.get("provider_failovers", 0) >= int(strategy["budget"].get("max_provider_failovers", 2)):
            return None, None
        self._mark_provider_failure(provider_state, current_choice, failure_kind)
        payload = dict(route_payload)
        payload["provider_state"] = provider_state
        try:
            reroute = await self.router.route(payload)
        except Exception:
            return None, None
        candidate = reroute.get("strategy", {}).get(role)
        if not candidate or candidate.get("id") == current_choice.get("id"):
            return None, reroute
        progress["provider_failovers"] = int(progress.get("provider_failovers", 0)) + 1
        return candidate, reroute

    async def run_job(self, job_id: str) -> None:
        started = time.monotonic()
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")
        if job["status"] in TERMINAL:
            return
        project = project_config(job["project_id"])
        task = dict(job["task"])
        stored = dict(job.get("repo_analysis") or {})
        hints = dict(stored.get("hints") or {})
        provider_state = dict(stored.get("provider_state") or {})

        ws = await self.ddev.create_workspace(
            job_id=job_id, project_id=job["project_id"], ref=job.get("source_commit")
        )
        workspace = Path(ws["workspace"]).resolve()
        branch = ws["branch"]
        source_commit = ws["source_commit"]
        self.storage.update(job_id, workspace=str(workspace), branch=branch, source_commit=source_commit)

        repo_analysis, enriched_task = analyze_repo(workspace, task, hints)
        self.storage.update(job_id, status="routing", repo_analysis=repo_analysis, task=enriched_task)
        route_payload = {
            "job_id": job_id,
            "project_id": job["project_id"],
            "repository": job["project_id"],
            "source_commit": source_commit,
            "task": enriched_task,
            "repo": repo_analysis,
            "provider_state": provider_state,
        }
        route = await self.router.route(route_payload)
        strategy = route["strategy"]
        self.storage.update(job_id, route=route)
        if strategy.get("human_decision", {}).get("required"):
            self.storage.update(job_id, status="waiting_human", result={"decision": strategy["human_decision"], "workspace": str(workspace), "branch": branch})
            return

        runtime_cfg = project.get("runtime", {})

        # Each isolated workspace gets a unique DDEV project name, preventing collisions with
        # the original project or another parallel coding job.
        if project.get("ddev", {}).get("enabled", False) and (workspace / ".ddev").exists():
            safe_name = re.sub(r"[^a-z0-9-]", "-", f"cp-{job_id[:10]}")
            (workspace / ".ddev" / "config.coding-platform.yaml").write_text(f"name: {safe_name}\n", encoding="utf-8")

        if job.get("dry_run"):
            self.storage.update(job_id, status="completed", result={"dry_run": True, "route": route, "workspace": str(workspace), "branch": branch})
            return

        progress = self._new_progress()
        route_history: list[dict[str, Any]] = [{"reason": "initial", "route": route}]
        max_diff = int(runtime_cfg.get("max_diff_bytes", 500000))
        plan: str | None = None
        if strategy.get("planner"):
            self.storage.update(job_id, status="planning")
            choice = strategy["planner"]
            while True:
                result = await build_adapter(choice["adapter"], choice["model"]).run(
                    workspace=workspace,
                    prompt=planning_prompt(task=enriched_task, repo_analysis=repo_analysis),
                    mode="plan",
                    timeout=self._remaining_seconds(strategy, started, 1800),
                )
                progress["model_calls"] += 1
                self._record_usage(progress, choice["id"], result.usage)
                if result.provider_failed:
                    progress["provider_failures"].append({"model": choice["id"], "provider": choice.get("provider"), "kind": result.failure_kind})
                    next_choice, reroute = await self._provider_failover(
                        route_payload=route_payload, provider_state=provider_state, current_choice=choice,
                        failure_kind=result.failure_kind or "provider_unavailable", progress=progress,
                        strategy=strategy, role="planner",
                    )
                    if next_choice:
                        route_history.append({"reason": f"planner_provider_failover:{choice['id']}:{result.failure_kind}", "route": reroute})
                        choice = next_choice
                        continue
                    self.storage.update(
                        job_id, status="blocked", progress=progress,
                        result={"reason": "planner_provider_failure_without_fallback", "route_history": route_history,
                                "last_failure": result.failure_message or result.stderr or result.output},
                    )
                    return
                if result.returncode != 0:
                    raise RuntimeError(f"Planner failed: {result.stderr or result.output}")
                plan = result.output[-20000:]
                break

        if project.get("ddev", {}).get("enabled", False):
            self.storage.update(job_id, status="verifying")
            preflight = await self.ddev.phase(
                job_id=job_id, project_id=job["project_id"], workspace=str(workspace), phase="preflight",
                timeout_seconds=self._remaining_seconds(strategy, started, 900),
            )
            progress["tool_calls"] += len(preflight.get("commands", []))
            if not preflight.get("passed", False):
                raise RuntimeError(f"DDEV preflight failed: {preflight}")

        executor_choice = strategy["executor"]
        last_failure: str | None = None
        while True:
            if self._cancelled(job_id):
                return
            progress["iteration"] += 1
            progress["elapsed_minutes"] = round((time.monotonic() - started) / 60.0, 3)
            self.storage.update(job_id, status="executing", progress=progress)
            adapter = build_adapter(executor_choice["adapter"], executor_choice["model"])
            run = await adapter.run(
                workspace=workspace,
                prompt=execution_prompt(task=enriched_task, route=route, repo_analysis=repo_analysis, plan=plan, failure=last_failure),
                mode="execute",
                timeout=self._remaining_seconds(strategy, started, 2400),
            )
            progress["model_calls"] += 1
            self._record_usage(progress, executor_choice["id"], run.usage)
            self._record_agent_attempt(progress, executor_choice, run)
            progress["agent_succeeded"] = run.returncode == 0
            progress["last_agent_failure_kind"] = run.failure_kind

            if run.provider_failed:
                failure_text = run.failure_message or run.stderr or run.output or f"{executor_choice['id']} provider failure"
                last_failure = f"Provider failure ({run.failure_kind}) from {executor_choice['id']}:\n{failure_text}"[-30000:]
                fp = failure_fingerprint(last_failure)
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(f"provider:{executor_choice['id']}:{run.failure_kind}")
                progress["provider_failures"].append({
                    "model": executor_choice["id"],
                    "provider": executor_choice.get("provider"),
                    "kind": run.failure_kind,
                })
                next_executor, reroute = await self._provider_failover(
                    route_payload=route_payload, provider_state=provider_state, current_choice=executor_choice,
                    failure_kind=run.failure_kind or "provider_unavailable", progress=progress, strategy=strategy,
                )
                if next_executor:
                    route_history.append({
                        "reason": f"provider_failover:{executor_choice['id']}:{run.failure_kind}",
                        "route": reroute,
                    })
                    executor_choice = next_executor
                    self.storage.update(job_id, status="routing", progress=progress, route=reroute)
                    continue
                self.storage.update(
                    job_id, status="blocked", progress=progress,
                    result={"reason": "provider_failure_without_fallback", "last_failure": last_failure, "route_history": route_history},
                )
                return

            if run.returncode != 0:
                last_failure = f"Agent command failed ({run.returncode}):\n{run.stderr}\n{run.output}"[-30000:]
            self.storage.update(job_id, status="verifying", progress=progress)

            diff = diff_state(workspace, max_diff)
            progress["changed_files"] = diff["changed_file_count"]
            progress["material_change_present"] = diff["changed_file_count"] > 0
            progress["diff_hashes"].append(diff["diff_hash"])

            material_required = "material_change" in strategy.get("definition_of_done", {}).get("required", [])
            if material_required and not progress["material_change_present"]:
                # Do not burn test/repair budget verifying an unchanged repository when
                # the task explicitly requires an implementation change. A successful
                # CLI process with no diff is a no-effect execution, not a test failure.
                last_failure = "Agent completed without producing the required material repository change."
                progress["last_agent_failure_kind"] = progress.get("last_agent_failure_kind") or "no_effect"
                fp = failure_fingerprint(last_failure + "\n" + (run.output or "")[-4000:])
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(f"no_effect:{executor_choice['id']}")
                next_executor, reroute = await self._model_failover(
                    route_payload=route_payload, provider_state=provider_state, current_choice=executor_choice,
                    progress=progress, strategy=strategy, reason="no_effect",
                )
                if next_executor:
                    route_history.append({
                        "reason": f"model_failover:{executor_choice['id']}:no_effect",
                        "route": reroute,
                    })
                    executor_choice = next_executor
                    self.storage.update(job_id, status="routing", progress=progress, route=reroute)
                    continue
                progress["elapsed_minutes"] = round((time.monotonic() - started) / 60.0, 3)
                self.storage.update(
                    job_id, status="blocked", progress=progress,
                    result={
                        "reason": "material_change_missing_without_model_fallback",
                        "last_failure": last_failure,
                        "diff": diff,
                        "route_history": route_history,
                        "agent_attempts": progress.get("agent_attempts", []),
                    },
                )
                return

            verification = await self._verify(job_id, job["project_id"], workspace, project, strategy, started)
            progress["tool_calls"] += verification["tool_calls"]
            progress["test_runs"] += verification["test_runs"]
            progress["tests_passed"] = verification["tests_passed"]
            progress["required_checks_passed"] = verification["passed"]
            progress["unexpected_scope"] = diff["changed_file_count"] > int(strategy["budget"]["max_changed_files"])

            if verification["passed"]:
                evaluator_ok = True
                evaluator_output = None
                if strategy.get("evaluator"):
                    self.storage.update(job_id, status="evaluating", progress=progress)
                    choice = strategy["evaluator"]
                    while True:
                        evaluation = await build_adapter(choice["adapter"], choice["model"]).run(
                            workspace=workspace,
                            prompt=evaluator_prompt(task=enriched_task, diff=diff["diff"], verification=verification),
                            mode="evaluate",
                            timeout=self._remaining_seconds(strategy, started, 1200),
                        )
                        progress["model_calls"] += 1
                        self._record_usage(progress, choice["id"], evaluation.usage)
                        if evaluation.provider_failed:
                            progress["provider_failures"].append({"model": choice["id"], "provider": choice.get("provider"), "kind": evaluation.failure_kind})
                            next_choice, reroute = await self._provider_failover(
                                route_payload=route_payload, provider_state=provider_state, current_choice=choice,
                                failure_kind=evaluation.failure_kind or "provider_unavailable", progress=progress,
                                strategy=strategy, role="evaluator",
                            )
                            if next_choice:
                                route_history.append({"reason": f"evaluator_provider_failover:{choice['id']}:{evaluation.failure_kind}", "route": reroute})
                                choice = next_choice
                                continue
                            self.storage.update(
                                job_id, status="blocked", progress=progress,
                                result={"reason": "evaluator_provider_failure_without_fallback", "route_history": route_history,
                                        "last_failure": evaluation.failure_message or evaluation.stderr or evaluation.output, "diff": diff},
                            )
                            return
                        evaluator_output = evaluation.output[-20000:]
                        evaluator_ok = evaluation.returncode == 0 and evaluator_output.strip().upper().startswith("PASS")
                        break
                if evaluator_ok and not progress["unexpected_scope"]:
                    progress["required_checks_passed"] = True
                    reassess = await self.router.reassess({"route": route, "progress": progress, "provider_state": provider_state})
                    if reassess["action"] == "complete":
                        commit_sha = None
                        if strategy.get("permissions", {}).get("commit", False):
                            commit_sha = commit_changes(workspace, f"AI: {enriched_task['title']}")
                        result = {
                            "status": "accepted",
                            "branch": branch,
                            "commit": commit_sha,
                            "diff": diff,
                            "verification": verification,
                            "evaluator": evaluator_output,
                            "route": route,
                            "route_history": route_history,
                            "progress": progress,
                        }
                        self.storage.update(job_id, status="completed", result=result, progress=progress)
                        return
                    if reassess["action"] == "human_decision":
                        self.storage.update(job_id, status="waiting_human", result={"reassess": reassess, "route_history": route_history}, progress=progress)
                        return
                    if reassess["action"] == "stop":
                        self.storage.update(job_id, status="blocked", result={"reassess": reassess, "diff": diff, "route_history": route_history}, progress=progress)
                        return
                    if reassess["action"] == "escalate" and reassess.get("next_executor"):
                        progress["escalations"] += 1
                        executor_choice = reassess["next_executor"]
                        last_failure = reassess.get("reason") or "Execution strategy escalated"
                    else:
                        if "material_change" in strategy.get("definition_of_done", {}).get("required", []) and not progress["material_change_present"]:
                            last_failure = "Definition of done requires a material repository change, but the agent produced no diff."
                        elif not progress["agent_succeeded"]:
                            last_failure = last_failure or "Agent did not complete successfully."
                        else:
                            last_failure = reassess.get("reason") or "Definition of done is not complete."
                else:
                    last_failure = f"Evaluator failed:\n{evaluator_output or 'unexpected scope'}"
            else:
                last_failure = verification.get("failure_text") or last_failure or "Verification failed"

            if last_failure:
                fp = failure_fingerprint(last_failure)
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(fp)
            else:
                progress["progress_markers"].append(diff["diff_hash"][:24])
            progress["repair_iterations"] += 1
            progress["elapsed_minutes"] = round((time.monotonic() - started) / 60.0, 3)
            self.storage.update(job_id, progress=progress)
            reassess = await self.router.reassess({"route": route, "progress": progress, "provider_state": provider_state})
            action = reassess["action"]
            if action == "escalate" and reassess.get("next_executor"):
                progress["escalations"] += 1
                executor_choice = reassess["next_executor"]
                continue
            if action == "continue":
                continue
            if action == "human_decision":
                self.storage.update(job_id, status="waiting_human", result={"reassess": reassess, "last_failure": last_failure}, progress=progress)
                return
            if action == "complete":
                # Completion should normally happen in the verified branch above, where
                # the final diff/commit are captured. Refuse a bare completion here.
                self.storage.update(
                    job_id, status="blocked",
                    result={"reassess": reassess, "last_failure": last_failure, "diff": diff, "route_history": route_history},
                    progress=progress,
                )
                return
            self.storage.update(job_id, status="blocked", result={"reassess": reassess, "last_failure": last_failure, "diff": diff, "route_history": route_history, "agent_attempts": progress.get("agent_attempts", [])}, progress=progress)
            return

    async def _verify(
        self, job_id: str, project_id: str, workspace: Path, project: dict[str, Any],
        strategy: dict[str, Any], started: float,
    ) -> dict[str, Any]:
        if not project.get("ddev", {}).get("enabled", False):
            return {"passed": True, "tests_passed": True, "tool_calls": 0, "test_runs": 0, "phases": []}
        phases = ["targeted_tests", "static_analysis"]
        if strategy.get("profile") in {"complex", "critical"}:
            phases.append("full_tests")
        outputs = []
        tool_calls = 0
        test_runs = 0
        failures: list[str] = []
        for phase in phases:
            result = await self.ddev.phase(
                job_id=job_id, project_id=project_id, workspace=str(workspace), phase=phase,
                timeout_seconds=self._remaining_seconds(strategy, started, 1200),
            )
            outputs.append(result)
            tool_calls += len(result.get("commands", []))
            test_runs += len(result.get("commands", []))
            if not result.get("passed", False):
                failures.append(str(result))
        return {
            "passed": not failures,
            "tests_passed": not failures,
            "tool_calls": tool_calls,
            "test_runs": test_runs,
            "phases": outputs,
            "failure_text": "\n".join(failures)[-30000:],
        }

    async def cleanup(self, job_id: str, remove_workspace: bool = False) -> dict[str, Any]:
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")
        workspace = job.get("workspace")
        if not workspace:
            return {"cleaned": False, "reason": "no workspace"}
        project = project_config(job["project_id"])
        cleanup_result = None
        if project.get("ddev", {}).get("enabled", False):
            cleanup_result = await self.ddev.phase(job_id=job_id, project_id=job["project_id"], workspace=workspace, phase="cleanup")
        remove_result = None
        if remove_workspace:
            remove_result = await self.ddev.remove_workspace(
                job_id=job_id, project_id=job["project_id"], workspace=workspace
            )
        return {"cleaned": True, "ddev": cleanup_result, "workspace_removed": remove_workspace, "workspace_result": remove_result}
