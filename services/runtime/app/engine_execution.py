from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .adapters import build_adapter
from .config import project_config
from .engine_core import RuntimeEngineCore
from .evidence_packs import developer_repair_evidence_pack, pm_evidence_pack
from .fingerprint import failure_fingerprint
from .prompts import evaluator_prompt, execution_prompt, planning_prompt
from .repo import analyze_repo, commit_changes, diff_state
from .review import (
    mark_actioned_review_findings,
    parse_review_output,
    record_review_telemetry,
    review_report_summary,
    should_run_review,
)
from .state import checkpoint_from_row, existing_repo_analysis, merge_progress, validate_workspace


class RuntimeEngine(RuntimeEngineCore):
    async def run_job(self, job_id: str) -> None:
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")
        if job["status"] != "queued":
            return

        project = project_config(job["project_id"])
        task = dict(job["task"])
        checkpoint = checkpoint_from_row(job)
        progress = merge_progress(self._new_progress(), job.get("progress"))
        started = time.monotonic() - float(progress.get("elapsed_minutes", 0.0)) * 60.0
        hints = dict(checkpoint.get("hints") or {})
        provider_state = dict(checkpoint.get("provider_state") or {})

        if job.get("workspace"):
            workspace = validate_workspace(self.workspace_root, job_id, job["workspace"])
            branch = str(job.get("branch") or "")
            source_commit = str(job.get("source_commit") or "")
            if not branch or not source_commit:
                raise RuntimeError("Persisted workspace is missing branch/source commit metadata")
        else:
            ws = await self.ddev.create_workspace(
                job_id=job_id, project_id=job["project_id"], ref=job.get("source_commit")
            )
            workspace = Path(ws["workspace"]).resolve()
            branch = ws["branch"]
            source_commit = ws["source_commit"]
            self.storage.update(
                job_id, workspace=str(workspace), branch=branch, source_commit=source_commit
            )

        repo_analysis = existing_repo_analysis(job)
        enriched_task = task
        if repo_analysis is None:
            repo_analysis, enriched_task = analyze_repo(workspace, task, hints)
            self.storage.update(job_id, repo_analysis=repo_analysis, task=enriched_task)

        route_payload = {
            "job_id": job_id,
            "project_id": job["project_id"],
            "repository": job["project_id"],
            "source_commit": source_commit,
            "task": enriched_task,
            "repo": repo_analysis,
            "provider_state": provider_state,
        }
        route = job.get("route")
        if not route:
            self.storage.update(job_id, status="routing", progress=progress, checkpoint=checkpoint)
            route = await self.router.route(route_payload)
            self.storage.update(job_id, route=route)
        strategy = route["strategy"]

        route_history: list[dict[str, Any]] = list(checkpoint.get("route_history") or [])
        if not route_history:
            route_history.append({"reason": "initial", "route": route})
        checkpoint["route_history"] = route_history
        checkpoint["provider_state"] = provider_state

        initial_decision = strategy.get("human_decision") or {}
        if initial_decision.get("required") and not self._decision_approved(checkpoint, initial_decision):
            self._pause_for_decision(
                job_id=job_id,
                checkpoint=checkpoint,
                progress=progress,
                decision=initial_decision,
                route_history=route_history,
                source="initial_route",
            )
            return

        runtime_cfg = project.get("runtime", {})
        if project.get("ddev", {}).get("enabled", False) and (workspace / ".ddev").exists():
            safe_name = re.sub(r"[^a-z0-9-]", "-", f"cp-{job_id[:10]}")
            (workspace / ".ddev" / "config.coding-platform.yaml").write_text(
                f"name: {safe_name}\n", encoding="utf-8"
            )

        if job.get("dry_run"):
            self.storage.update(
                job_id,
                status="completed",
                result={"dry_run": True, "route": route, "workspace": str(workspace), "branch": branch},
                progress=progress,
                checkpoint=checkpoint,
            )
            return

        max_diff = int(runtime_cfg.get("max_diff_bytes", 500000))
        plan: str | None = checkpoint.get("plan")

        if strategy.get("planner") and not plan:
            choice = dict(checkpoint.get("planner_choice") or strategy["planner"])
            while True:
                self._update_elapsed(progress, started)
                budget_reason = self._pre_model_budget_reason(progress, strategy, include_iteration=False)
                if budget_reason:
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="planner_budget_exhausted",
                        last_failure=budget_reason,
                    )
                    return
                progress["model_calls"] += 1
                checkpoint["planner_choice"] = choice
                checkpoint["provider_state"] = provider_state
                self.storage.update(job_id, status="planning", progress=progress, checkpoint=checkpoint)
                result = await build_adapter(
                    choice["adapter"], choice["model"], choice.get("reasoning_effort")
                ).run(
                    workspace=workspace,
                    prompt=planning_prompt(task=enriched_task, repo_analysis=repo_analysis),
                    mode="plan",
                    timeout=self._remaining_seconds(strategy, started, 1800),
                )
                self._record_usage(progress, choice["id"], result.usage)
                self._update_elapsed(progress, started)
                self.storage.update(job_id, progress=progress)
                if result.provider_failed:
                    progress["provider_failures"].append({
                        "model": choice["id"],
                        "provider": choice.get("provider"),
                        "kind": result.failure_kind,
                    })
                    next_choice, reroute = await self._provider_failover(
                        route_payload=route_payload,
                        provider_state=provider_state,
                        current_choice=choice,
                        failure_kind=result.failure_kind or "provider_unavailable",
                        progress=progress,
                        strategy=strategy,
                        role="planner",
                    )
                    checkpoint["provider_state"] = provider_state
                    if next_choice:
                        route_history.append({
                            "reason": f"planner_provider_failover:{choice['id']}:{result.failure_kind}",
                            "route": reroute,
                        })
                        choice = next_choice
                        checkpoint["planner_choice"] = choice
                        checkpoint["route_history"] = route_history
                        self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                        continue
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="planner_provider_failure_without_fallback",
                        last_failure=result.failure_message or result.stderr or result.output,
                    )
                    return
                if result.returncode != 0:
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="planner_failed",
                        last_failure=result.stderr or result.output,
                    )
                    return
                plan = result.output[-20000:]
                checkpoint["plan"] = plan
                checkpoint.pop("planner_choice", None)
                self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                break

        if project.get("ddev", {}).get("enabled", False):
            commands = project.get("ddev", {}).get("preflight", []) or []
            if (
                not self._adaptive_work_shape_nonblocking(strategy)
                and progress["tool_calls"] + len(commands) > int(strategy["budget"]["max_tool_calls"])
            ):
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="preflight_budget_exhausted",
                    last_failure="tool-call budget would be exceeded by preflight",
                )
                return
            self.storage.update(job_id, status="verifying", progress=progress, checkpoint=checkpoint)
            preflight = await self.ddev.phase(
                job_id=job_id,
                project_id=job["project_id"],
                workspace=str(workspace),
                phase="preflight",
                timeout_seconds=self._remaining_seconds(strategy, started, 900),
            )
            progress["tool_calls"] += len(preflight.get("commands", []))
            self._update_elapsed(progress, started)
            self.storage.update(job_id, progress=progress)
            if not preflight.get("passed", False):
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="preflight_failed",
                    last_failure=str(preflight)[-30000:],
                )
                return

        executor_choice = dict(checkpoint.get("executor_choice") or strategy["executor"])
        last_failure: str | None = checkpoint.get("last_failure")

        while True:
            if self._cancelled(job_id):
                return
            self._update_elapsed(progress, started)
            budget_reason = self._pre_model_budget_reason(progress, strategy, include_iteration=True)
            if budget_reason:
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="execution_budget_exhausted",
                    last_failure=budget_reason,
                )
                return

            progress["iteration"] += 1
            progress["model_calls"] += 1
            checkpoint.update({
                "executor_choice": executor_choice,
                "last_failure": last_failure,
                "provider_state": provider_state,
                "route_history": route_history,
            })
            self.storage.update(job_id, status="executing", progress=progress, checkpoint=checkpoint)
            adapter = build_adapter(
                executor_choice["adapter"], executor_choice["model"], executor_choice.get("reasoning_effort")
            )
            run = await adapter.run(
                workspace=workspace,
                prompt=execution_prompt(
                    task=enriched_task,
                    route=route,
                    repo_analysis=repo_analysis,
                    plan=plan,
                    failure=last_failure,
                    work_order=checkpoint.get("work_order"),
                    baseline=checkpoint.get("project_baseline"),
                    collaboration_context=checkpoint.get("collaboration_context"),
                ),
                mode="execute",
                timeout=self._remaining_seconds(strategy, started, 2400),
            )
            self._record_usage(progress, executor_choice["id"], run.usage)
            self._record_agent_attempt(progress, executor_choice, run)
            progress["agent_succeeded"] = run.returncode == 0
            progress["last_agent_failure_kind"] = run.failure_kind
            self._update_elapsed(progress, started)
            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

            if run.provider_failed:
                failure_text = run.failure_message or run.stderr or run.output or f"{executor_choice['id']} provider failure"
                last_failure = (
                    f"Provider failure ({run.failure_kind}) from {executor_choice['id']}:\n{failure_text}"
                )[-30000:]
                fp = failure_fingerprint(last_failure)
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(f"provider:{executor_choice['id']}:{run.failure_kind}")
                progress["provider_failures"].append({
                    "model": executor_choice["id"],
                    "provider": executor_choice.get("provider"),
                    "kind": run.failure_kind,
                })
                next_executor, reroute = await self._provider_failover(
                    route_payload=route_payload,
                    provider_state=provider_state,
                    current_choice=executor_choice,
                    failure_kind=run.failure_kind or "provider_unavailable",
                    progress=progress,
                    strategy=strategy,
                )
                checkpoint["provider_state"] = provider_state
                checkpoint["last_failure"] = last_failure
                if next_executor:
                    route_history.append({
                        "reason": f"provider_failover:{executor_choice['id']}:{run.failure_kind}",
                        "route": reroute,
                    })
                    executor_choice = next_executor
                    checkpoint["executor_choice"] = executor_choice
                    checkpoint["route_history"] = route_history
                    self.storage.update(job_id, status="routing", progress=progress, checkpoint=checkpoint)
                    continue
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="provider_failure_without_fallback",
                    last_failure=last_failure,
                )
                return

            if run.returncode != 0:
                last_failure = f"Agent command failed ({run.returncode}):\n{run.stderr}\n{run.output}"[-30000:]
            self.storage.update(job_id, status="verifying", progress=progress)

            diff = diff_state(workspace, max_diff)
            progress["changed_files"] = diff["changed_file_count"]
            progress["material_change_present"] = diff["changed_file_count"] > 0
            progress["diff_hashes"].append(diff["diff_hash"])
            mark_actioned_review_findings(
                checkpoint,
                progress,
                current_diff_hash=diff["diff_hash"],
            )

            material_required = "material_change" in strategy.get("definition_of_done", {}).get("required", [])
            if material_required and not progress["material_change_present"]:
                last_failure = "Agent completed without producing the required material repository change."
                progress["last_agent_failure_kind"] = progress.get("last_agent_failure_kind") or "no_effect"
                fp = failure_fingerprint(last_failure + "\n" + (run.output or "")[-4000:])
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(f"no_effect:{executor_choice['id']}")
                next_executor, reroute = await self._model_failover(
                    route_payload=route_payload,
                    provider_state=provider_state,
                    current_choice=executor_choice,
                    progress=progress,
                    strategy=strategy,
                    reason="no_effect",
                )
                checkpoint["provider_state"] = provider_state
                checkpoint["last_failure"] = last_failure
                if next_executor:
                    route_history.append({
                        "reason": f"model_failover:{executor_choice['id']}:no_effect",
                        "route": reroute,
                    })
                    executor_choice = next_executor
                    checkpoint["executor_choice"] = executor_choice
                    checkpoint["route_history"] = route_history
                    self.storage.update(job_id, status="routing", progress=progress, checkpoint=checkpoint)
                    continue
                self._update_elapsed(progress, started)
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="material_change_missing_without_model_fallback",
                    last_failure=last_failure,
                    diff=diff,
                )
                return

            verification = await self._verify(
                job_id, job["project_id"], workspace, project, strategy, started, progress
            )
            progress["tool_calls"] += verification["tool_calls"]
            progress["test_runs"] += verification["test_runs"]
            progress["tests_passed"] = verification["tests_passed"]
            progress["required_checks_passed"] = False
            progress["unexpected_scope"] = diff["changed_file_count"] > int(strategy["budget"]["max_changed_files"])
            self._update_elapsed(progress, started)

            evaluator_output = None
            evaluator_ok = True
            review_report = None
            review_policy = strategy.get("review_policy") or {}
            if "review_policy" in strategy:
                run_review = should_run_review(
                    review_policy,
                    verification,
                    changed_files=diff["changed_file_count"],
                    unexpected_scope=progress["unexpected_scope"],
                )
            else:
                run_review = bool(strategy.get("evaluator"))

            if verification["passed"] and strategy.get("evaluator") and run_review:
                choice = dict(checkpoint.get("evaluator_choice") or strategy["evaluator"])
                while True:
                    budget_reason = self._pre_model_budget_reason(progress, strategy, include_iteration=False)
                    if budget_reason:
                        last_failure = budget_reason
                        evaluator_ok = False
                        break
                    progress["model_calls"] += 1
                    checkpoint["evaluator_choice"] = choice
                    self.storage.update(job_id, status="evaluating", progress=progress, checkpoint=checkpoint)
                    evaluation = await build_adapter(
                        choice["adapter"], choice["model"], choice.get("reasoning_effort")
                    ).run(
                        workspace=workspace,
                        prompt=evaluator_prompt(
                            task=enriched_task,
                            diff=diff["diff"],
                            verification=verification,
                            work_order=checkpoint.get("work_order"),
                            baseline=checkpoint.get("project_baseline"),
                        ),
                        mode="evaluate",
                        timeout=self._remaining_seconds(strategy, started, 1200),
                    )
                    self._record_usage(progress, choice["id"], evaluation.usage)
                    self._update_elapsed(progress, started)
                    if evaluation.provider_failed:
                        progress["provider_failures"].append({
                            "model": choice["id"],
                            "provider": choice.get("provider"),
                            "kind": evaluation.failure_kind,
                        })
                        next_choice, reroute = await self._provider_failover(
                            route_payload=route_payload,
                            provider_state=provider_state,
                            current_choice=choice,
                            failure_kind=evaluation.failure_kind or "provider_unavailable",
                            progress=progress,
                            strategy=strategy,
                            role="evaluator",
                        )
                        checkpoint["provider_state"] = provider_state
                        if next_choice:
                            route_history.append({
                                "reason": f"evaluator_provider_failover:{choice['id']}:{evaluation.failure_kind}",
                                "route": reroute,
                            })
                            choice = next_choice
                            checkpoint["evaluator_choice"] = choice
                            checkpoint["route_history"] = route_history
                            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                            continue
                        self._block(
                            job_id=job_id,
                            progress=progress,
                            checkpoint=checkpoint,
                            reason="evaluator_provider_failure_without_fallback",
                            last_failure=evaluation.failure_message or evaluation.stderr or evaluation.output,
                            diff=diff,
                        )
                        return
                    evaluator_output = evaluation.output[-20000:]
                    review_report = parse_review_output(evaluator_output)
                    record_review_telemetry(
                        progress,
                        review_report,
                        review_level=str(review_policy.get("level") or strategy.get("profile") or "legacy"),
                        model_id=choice.get("id"),
                        provider=choice.get("provider"),
                        raw_usage=evaluation.usage,
                    )
                    checkpoint["last_review_report"] = review_report_summary(review_report)

                    if not review_report.protocol_valid:
                        next_choice, reroute = await self._model_failover(
                            route_payload=route_payload,
                            provider_state=provider_state,
                            current_choice=choice,
                            progress=progress,
                            strategy=strategy,
                            reason="malformed_reviewer_output",
                            role="evaluator",
                        )
                        checkpoint["provider_state"] = provider_state
                        if next_choice:
                            route_history.append({
                                "reason": f"evaluator_model_failover:{choice['id']}:malformed_review",
                                "route": reroute,
                            })
                            choice = next_choice
                            checkpoint["evaluator_choice"] = choice
                            checkpoint["route_history"] = route_history
                            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                            continue
                        self._block(
                            job_id=job_id,
                            progress=progress,
                            checkpoint=checkpoint,
                            reason="evaluator_protocol_failure_without_fallback",
                            last_failure=review_report.summary,
                            diff=diff,
                        )
                        return

                    evaluator_ok = evaluation.returncode == 0 and review_report.verdict == "pass"
                    if review_report.verdict == "fail":
                        checkpoint["pending_review_findings"] = {
                            "diff_hash": diff["diff_hash"],
                            "findings": [item.model_dump(mode="json") for item in review_report.findings],
                        }
                    checkpoint.pop("evaluator_choice", None)
                    self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                    break
            elif verification["passed"] and strategy.get("evaluator") and not run_review:
                progress["review_skipped_strong_evidence"] = int(
                    progress.get("review_skipped_strong_evidence", 0)
                ) + 1
                checkpoint["last_review_report"] = {
                    "verdict": "skipped",
                    "summary": "Model review skipped by policy because deterministic evidence is strong",
                    "finding_count": 0,
                    "findings": [],
                    "jit_context_used": False,
                }
                self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

            progress["required_checks_passed"] = verification["passed"] and evaluator_ok and not progress["unexpected_scope"]

            if progress["required_checks_passed"]:
                effective_route = self._effective_route(route, executor_choice)
                while True:
                    reassess = await self.router.reassess({
                        "route": effective_route,
                        "progress": progress,
                        "provider_state": provider_state,
                    })
                    action = reassess["action"]
                    if action != "human_decision":
                        break
                    decision = dict(reassess.get("human_decision") or {})
                    if not self._decision_approved(checkpoint, decision):
                        self._pause_for_decision(
                            job_id=job_id,
                            checkpoint=checkpoint,
                            progress=progress,
                            decision=decision,
                            route_history=route_history,
                            source="reassessment",
                        )
                        return
                    approved = set(decision.get("triggers") or [])
                    progress["important_decision_flags"] = [
                        item for item in progress.get("important_decision_flags", []) if item not in approved
                    ]
                    self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

                if action == "complete":
                    commit_sha = None
                    if strategy.get("permissions", {}).get("commit", False):
                        commit_sha = commit_changes(workspace, f"AI: {enriched_task['title']}")
                    review_summary = (
                        review_report_summary(review_report)
                        if review_report is not None
                        else checkpoint.get("last_review_report")
                    )
                    work_order = checkpoint.get("work_order") or {}
                    pm_pack = pm_evidence_pack(
                        work_order_ref=str(work_order.get("id") or "legacy-task"),
                        outcome="accepted",
                        verification_summary=verification,
                        review_summary=review_summary if isinstance(review_summary, dict) else None,
                        unresolved_risks=[],
                        protected_decision_flags=list(progress.get("important_decision_flags") or []),
                    )
                    result = {
                        "status": "accepted",
                        "branch": branch,
                        "commit": commit_sha,
                        "diff": diff,
                        "verification": verification,
                        "evaluator": evaluator_output,
                        "review": review_summary,
                        "pm_evidence": pm_pack,
                        "route": route,
                        "route_history": route_history,
                        "progress": progress,
                    }
                    checkpoint["last_failure"] = None
                    checkpoint["executor_choice"] = executor_choice
                    checkpoint["provider_state"] = provider_state
                    self.storage.update(
                        job_id,
                        status="completed",
                        result=result,
                        progress=progress,
                        checkpoint=checkpoint,
                        error=None,
                    )
                    return
                if action == "stop":
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="reassessment_stopped",
                        last_failure=reassess.get("reason"),
                        reassess=reassess,
                        diff=diff,
                    )
                    return
                if action == "escalate" and reassess.get("next_executor"):
                    progress["escalations"] += 1
                    executor_choice = reassess["next_executor"]
                    last_failure = reassess.get("reason") or "Execution strategy escalated"
                else:
                    if not progress["agent_succeeded"]:
                        last_failure = last_failure or "Agent did not complete successfully."
                    else:
                        last_failure = reassess.get("reason") or "Definition of done is not complete."
            elif not verification["passed"]:
                last_failure = verification.get("failure_text") or last_failure or "Verification failed"
            elif not evaluator_ok:
                findings = [item.model_dump(mode="json") for item in review_report.findings] if review_report else []
                work_order = checkpoint.get("work_order") or {}
                repair_pack = developer_repair_evidence_pack(
                    work_order_ref=str(work_order.get("id") or "legacy-task"),
                    current_diff_ref=f"sha256:{diff['diff_hash']}",
                    failing_check=None,
                    reviewer_findings=findings,
                    relevant_files=list(diff.get("changed_files") or []),
                    prior_attempt_summary=review_report.summary if review_report else evaluator_output,
                )
                last_failure = "PCP_REVIEW_FINDINGS: " + json.dumps(
                    repair_pack,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            elif progress["unexpected_scope"]:
                last_failure = "Evaluator completed but the diff exceeded the approved changed-file scope."

            if last_failure:
                fp = failure_fingerprint(last_failure)
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(fp)
            else:
                progress["progress_markers"].append(diff["diff_hash"][:24])
            progress["repair_iterations"] += 1
            self._update_elapsed(progress, started)
            total_findings = int(progress.get("review_findings", 0))
            actioned = int(progress.get("review_findings_actioned", 0))
            progress["review_useful_finding_yield"] = round(actioned / total_findings, 4) if total_findings else 0.0
            checkpoint.update({
                "executor_choice": executor_choice,
                "last_failure": last_failure,
                "provider_state": provider_state,
                "route_history": route_history,
            })
            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

            effective_route = self._effective_route(route, executor_choice)
            reassess = await self.router.reassess({
                "route": effective_route,
                "progress": progress,
                "provider_state": provider_state,
            })
            action = reassess["action"]
            if action == "escalate" and reassess.get("next_executor"):
                progress["escalations"] += 1
                executor_choice = reassess["next_executor"]
                checkpoint["executor_choice"] = executor_choice
                self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                continue
            if action == "continue":
                continue
            if action == "human_decision":
                decision = dict(reassess.get("human_decision") or {})
                if self._decision_approved(checkpoint, decision):
                    approved = set(decision.get("triggers") or [])
                    progress["important_decision_flags"] = [
                        item for item in progress.get("important_decision_flags", []) if item not in approved
                    ]
                    self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                    continue
                self._pause_for_decision(
                    job_id=job_id,
                    checkpoint=checkpoint,
                    progress=progress,
                    decision=decision,
                    route_history=route_history,
                    source="reassessment",
                )
                return
            if action == "complete":
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="unsafe_bare_completion",
                    last_failure=last_failure,
                    reassess=reassess,
                    diff=diff,
                )
                return
            self._block(
                job_id=job_id,
                progress=progress,
                checkpoint=checkpoint,
                reason="reassessment_stopped",
                last_failure=last_failure,
                reassess=reassess,
                diff=diff,
            )
            return

    async def _verify(
        self,
        job_id: str,
        project_id: str,
        workspace: Path,
        project: dict[str, Any],
        strategy: dict[str, Any],
        started: float,
        progress: dict[str, Any],
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
        budget = strategy["budget"]

        for phase in phases:
            commands = project.get("ddev", {}).get(phase, []) or []
            count = len(commands)
            if (
                not self._adaptive_work_shape_nonblocking(strategy)
                and (
                    progress["tool_calls"] + tool_calls + count > int(budget["max_tool_calls"])
                    or progress["test_runs"] + test_runs + count > int(budget["max_test_runs"])
                )
            ):
                failures.append(f"{phase}: verification budget would be exceeded")
                break
            result = await self.ddev.phase(
                job_id=job_id,
                project_id=project_id,
                workspace=str(workspace),
                phase=phase,
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
            cleanup_result = await self.ddev.phase(
                job_id=job_id,
                project_id=job["project_id"],
                workspace=workspace,
                phase="cleanup",
            )
        remove_result = None
        if remove_workspace:
            remove_result = await self.ddev.remove_workspace(
                job_id=job_id, project_id=job["project_id"], workspace=workspace
            )
        return {
            "cleaned": True,
            "ddev": cleanup_result,
            "workspace_removed": remove_workspace,
            "workspace_result": remove_result,
        }
