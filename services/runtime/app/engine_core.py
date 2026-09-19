from __future__ import annotations

import asyncio
import os
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from .adapters.antigravity import cancel_all_antigravity_runs
from .config import project_config
from .executor_client import DdevExecutorClient
from .router_client import RouterClient
from .state import checkpoint_from_row, clear_transient_provider_failures, decision_key
from .storage import Storage
from .usage import estimated_cost_usd, normalize_usage


FINAL = {"completed", "failed", "cancelled"}
PAUSED = {"blocked", "waiting_human", "interrupted"}
STABLE = FINAL | PAUSED


class RuntimeEngineCore:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.router = RouterClient()
        self.ddev = DdevExecutorClient()
        self.workspace_root = Path(os.getenv("CODING_WORKSPACES_ROOT", "/workspaces")).resolve()
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker_task: asyncio.Task | None = None
        self.active_jobs: dict[str, asyncio.Task[None]] = {}
        self._stopping = False

    async def start(self) -> None:
        self.storage.init()
        self._stopping = False
        await cancel_all_antigravity_runs()
        for job in self.storage.list(limit=500):
            if job["status"] == "queued":
                await self.queue.put(job["id"])
            elif job["status"] not in STABLE:
                self.storage.update(
                    job["id"],
                    status="interrupted",
                    error="Runtime restarted during an in-flight job; explicit resume required.",
                )
                await self.ddev.cancel(job_id=job["id"])
        self.worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        self._stopping = True
        tasks = list(self.active_jobs.items())
        for job_id, task in tasks:
            row = self.storage.get(job_id)
            if row and row["status"] not in FINAL:
                self.storage.update(
                    job_id,
                    status="interrupted",
                    error="Runtime stopped during an in-flight job; explicit resume required.",
                )
            await self.ddev.cancel(job_id=job_id)
            task.cancel()
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        self.worker_task = None

    async def enqueue(self, job_id: str) -> None:
        await self.queue.put(job_id)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self.queue.get()
            run_task = asyncio.create_task(self.run_job(job_id))
            self.active_jobs[job_id] = run_task
            try:
                await run_task
            except asyncio.CancelledError:
                row = self.storage.get(job_id)
                if row and row["status"] not in FINAL and row["status"] != "interrupted":
                    if row["status"] != "cancelled":
                        self.storage.update(
                            job_id,
                            status="interrupted",
                            error="Job execution was interrupted; explicit resume required.",
                        )
            except Exception as exc:
                row = self.storage.get(job_id)
                if row and row["status"] != "cancelled":
                    self.storage.update(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
            finally:
                self.active_jobs.pop(job_id, None)
                self.queue.task_done()

    def create_job(self, payload: dict[str, Any]) -> str:
        project_config(payload["project_id"])
        job_id = uuid.uuid4().hex
        checkpoint = {
            "hints": payload.get("repo_hints", {}),
            "provider_state": payload.get("provider_state", {}),
            "route_history": [],
            "approved_decisions": [],
        }
        self.storage.create({
            "id": job_id,
            "project_id": payload["project_id"],
            "status": "queued",
            "source_commit": payload.get("source_commit"),
            "task": payload["task"],
            "repo_analysis": None,
            "progress": self._new_progress(),
            "checkpoint": checkpoint,
            "dry_run": bool(payload.get("dry_run", False)),
        })
        return job_id

    async def resume(self, job_id: str, *, reset_transient_provider_failures: bool = False) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        if row["status"] not in {"queued", "interrupted", "blocked"}:
            raise RuntimeError(f"Job cannot be resumed from status={row['status']}")
        checkpoint = checkpoint_from_row(row)
        if reset_transient_provider_failures:
            checkpoint = clear_transient_provider_failures(checkpoint)
        self.storage.update(job_id, status="queued", error=None, checkpoint=checkpoint)
        await self.enqueue(job_id)
        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    async def cancel(self, job_id: str) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        if row["status"] in {"completed", "failed"}:
            raise RuntimeError(f"Job cannot be cancelled from status={row['status']}")
        if row["status"] != "cancelled":
            self.storage.update(job_id, status="cancelled", error=None)
        await self.ddev.cancel(job_id=job_id)
        active = self.active_jobs.get(job_id)
        if active and not active.done():
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    async def resolve_human_decision(self, job_id: str, *, action: str, note: str = "") -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        if row["status"] != "waiting_human":
            raise RuntimeError(f"Job is not waiting for a human decision (status={row['status']})")
        checkpoint = checkpoint_from_row(row)
        pending = dict(checkpoint.get("pending_decision") or {})
        decision = dict(pending.get("decision") or {})
        key = str(pending.get("key") or decision_key(decision))
        history = list(checkpoint.get("decision_history") or [])
        record = {"key": key, "action": action, "note": note}
        history.append(record)
        checkpoint["decision_history"] = history[-20:]
        checkpoint.pop("pending_decision", None)

        if action == "reject":
            self.storage.update(
                job_id,
                status="blocked",
                checkpoint=checkpoint,
                result={"reason": "human_decision_rejected", "decision": decision, "resolution": record},
                error=None,
            )
        elif action == "approve":
            approved = list(checkpoint.get("approved_decisions") or [])
            if key and key not in approved:
                approved.append(key)
            checkpoint["approved_decisions"] = approved[-20:]
            self.storage.update(
                job_id,
                status="queued",
                checkpoint=checkpoint,
                result={"reason": "human_decision_approved", "decision": decision, "resolution": record},
                error=None,
            )
            await self.enqueue(job_id)
        else:
            raise RuntimeError(f"Unsupported decision action: {action}")

        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    @staticmethod
    def _new_progress() -> dict[str, Any]:
        return {
            "iteration": 0, "repair_iterations": 0, "escalations": 0,
            "provider_failovers": 0, "model_failovers": 0, "model_calls": 0,
            "tool_calls": 0, "test_runs": 0, "input_tokens": 0, "output_tokens": 0,
            "elapsed_minutes": 0.0, "cost_usd": 0.0,
            "changed_files": 0, "failure_fingerprints": [], "diff_hashes": [],
            "progress_markers": [], "tests_passed": False,
            "required_checks_passed": False, "material_change_present": False,
            "agent_succeeded": False, "last_agent_failure_kind": None,
            "unexpected_scope": False, "important_decision_flags": [],
            "provider_failures": [], "agent_attempts": [],
        }

    @classmethod
    def _remaining_seconds(
        cls,
        strategy: dict[str, Any],
        started: float,
        per_call_cap: int,
    ) -> int:
        # Effective adaptive WorkOrders treat total elapsed wall time as
        # telemetry/calibration. Keep each individual operation bounded by its
        # existing phase cap so one command/model call still cannot hang forever.
        if cls._adaptive_work_shape_nonblocking(strategy):
            return max(10, int(per_call_cap))

        total = int(strategy["budget"]["max_wall_time_minutes"] * 60)
        remaining = total - int(time.monotonic() - started)
        if remaining <= 0:
            raise RuntimeError("Job wall-time budget exhausted before next operation")
        return max(10, min(per_call_cap, remaining))

    @staticmethod
    def _update_elapsed(progress: dict[str, Any], started: float) -> None:
        progress["elapsed_minutes"] = round((time.monotonic() - started) / 60.0, 3)

    @staticmethod
    def _adaptive_work_shape_nonblocking(strategy: dict[str, Any]) -> bool:
        """Whether static execution counters are telemetry rather than stop gates.

        This includes total elapsed wall time on effective adaptive WorkOrders.
        Individual operation timeouts, tokens, cost, scope and behavioral
        circuit-breakers remain bounded. Missing markers fail closed so
        persisted/legacy routes retain historical behavior.
        """
        return str(strategy.get("budget_mode") or "") == "adaptive"

    @classmethod
    def _pre_model_budget_reason(
        cls,
        progress: dict[str, Any],
        strategy: dict[str, Any],
        *,
        include_iteration: bool,
    ) -> str | None:
        budget = strategy["budget"]

        # Token volume and hard cost remain standalone material ceilings.
        checks = [
            (progress["input_tokens"] >= int(budget["max_input_tokens"]), "input-token budget exhausted"),
            (progress["output_tokens"] >= int(budget["max_output_tokens"]), "output-token budget exhausted"),
            (progress["cost_usd"] >= float(budget["hard_cost_usd"]), "hard cost budget exhausted"),
        ]

        # Static counters, including total elapsed wall time, are telemetry on
        # effective adaptive jobs. Explicit legacy-hard routes preserve the
        # historical strict wall/work-shape ceilings.
        if not cls._adaptive_work_shape_nonblocking(strategy):
            checks.extend([
                (progress["elapsed_minutes"] >= float(budget["max_wall_time_minutes"]), "wall-time budget exhausted"),
                (progress["model_calls"] >= int(budget["max_model_calls"]), "model-call budget exhausted"),
                (progress["tool_calls"] >= int(budget["max_tool_calls"]), "tool-call budget exhausted"),
                (progress["test_runs"] >= int(budget["max_test_runs"]), "test-run budget exhausted"),
                (progress["repair_iterations"] >= int(budget["max_repair_iterations"]), "repair budget exhausted"),
            ])
            if include_iteration:
                checks.append(
                    (progress["iteration"] >= int(budget["max_iterations"]), "iteration budget exhausted")
                )

        for hit, reason in checks:
            if hit:
                return reason
        return None

    @staticmethod
    def _record_usage(progress: dict[str, Any], model_id: str, raw_usage: dict[str, Any] | None) -> None:
        usage = normalize_usage(raw_usage)
        progress["input_tokens"] += int(usage["input_tokens"])
        progress["output_tokens"] += int(usage["output_tokens"])
        progress["cost_usd"] = round(float(progress.get("cost_usd", 0.0)) + estimated_cost_usd(model_id, raw_usage), 8)

    def _cancelled(self, job_id: str) -> bool:
        current = self.storage.get(job_id)
        return bool(current and current["status"] == "cancelled")

    @staticmethod
    def _decision_approved(checkpoint: dict[str, Any], decision: dict[str, Any] | None) -> bool:
        key = decision_key(decision)
        return bool(key) and key in set(checkpoint.get("approved_decisions") or [])

    def _pause_for_decision(self, *, job_id: str, checkpoint: dict[str, Any], progress: dict[str, Any], decision: dict[str, Any], route_history: list[dict[str, Any]], source: str) -> None:
        key = decision_key(decision)
        checkpoint["pending_decision"] = {"key": key, "decision": decision, "source": source}
        checkpoint["route_history"] = route_history
        self.storage.update(
            job_id,
            status="waiting_human",
            progress=progress,
            checkpoint=checkpoint,
            result={"reason": "human_decision_required", "decision": decision, "source": source, "route_history": route_history},
            error=None,
        )

    def _block(self, *, job_id: str, progress: dict[str, Any], checkpoint: dict[str, Any], reason: str, last_failure: str | None = None, **extra: Any) -> None:
        result = {
            "reason": reason,
            "last_failure": last_failure,
            "route_history": checkpoint.get("route_history", []),
            "agent_attempts": progress.get("agent_attempts", []),
            **extra,
        }
        self.storage.update(job_id, status="blocked", progress=progress, checkpoint=checkpoint, result=result, error=None)

    @staticmethod
    def _mark_provider_failure(provider_state: dict[str, Any], choice: dict[str, Any], kind: str) -> None:
        provider_key = f"provider:{choice.get('provider')}"
        state = dict(provider_state.get(provider_key) or {})
        state.update({"healthy": False, "available": False, "error_rate": 1.0})
        if kind in {"quota_exhausted", "rate_limited"}:
            state["quota_pressure"] = 1.0
        provider_state[provider_key] = state

    @staticmethod
    def _mark_model_failure(provider_state: dict[str, Any], choice: dict[str, Any], reason: str) -> None:
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
        if len(attempts) > 12:
            del attempts[:-12]

    async def _model_failover(self, *, route_payload: dict[str, Any], provider_state: dict[str, Any], current_choice: dict[str, Any], progress: dict[str, Any], strategy: dict[str, Any], reason: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if (
            not self._adaptive_work_shape_nonblocking(strategy)
            and progress.get("model_failovers", 0) >= int(strategy["budget"].get("max_model_failovers", 2))
        ):
            return None, None
        # Adaptive model-failover counts are telemetry. Durable failed-model state
        # makes recovery finite because Router must select a distinct eligible model.
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

    async def _provider_failover(self, *, route_payload: dict[str, Any], provider_state: dict[str, Any], current_choice: dict[str, Any], failure_kind: str, progress: dict[str, Any], strategy: dict[str, Any], role: str = "executor") -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        # Provider-failover counts are durable telemetry/planning priors, not a
        # Human Owner continuation gate. Each observed failure is first written
        # into provider/model/quota health and Router must return a distinct
        # eligible choice. Preserved failed-capacity state makes this sequence
        # finite; no eligible route or a contradictory same-choice route still
        # fails closed without resetting the consumed counter.
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

    @staticmethod
    def _effective_route(route: dict[str, Any], executor_choice: dict[str, Any]) -> dict[str, Any]:
        value = deepcopy(route)
        value.setdefault("strategy", {})["executor"] = deepcopy(executor_choice)
        return value
