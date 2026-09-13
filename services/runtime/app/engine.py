"""Governance-aware facade for the checkpointed Runtime engine.

The implementation remains split into engine_core (lifecycle/state transitions),
engine_execution (coding/verification loop), and engine_delivery (bounded GitHub
branch/PR/CI delivery). This facade owns project-governance metadata that must be
validated and pinned atomically when a job row is first created.
"""

from __future__ import annotations

import uuid
from typing import Any

from .baseline import resolve_project_baseline
from .config import project_config
from .engine_delivery import RuntimeEngine as _RuntimeEngine
from .state import (
    checkpoint_from_row,
    clear_routing_choices_for_resume,
    clear_transient_provider_failures,
)
from .work_order import (
    WorkOrderPolicyError,
    apply_work_order_budget,
    canonical_task_from_work_order,
    rehydrate_task_from_work_order,
    validate_work_order_against_baseline,
    work_order_snapshot,
)


_REASONING_ORDER = ["low", "medium", "high"]


class WorkOrderRouterProxy:
    """Apply per-job WorkOrder ceilings to every Router decision without global state."""

    def __init__(self, delegate: Any, storage: Any) -> None:
        self.delegate = delegate
        self.storage = storage

    async def health(self) -> bool:
        return await self.delegate.health()

    async def route(self, payload: dict[str, Any]) -> dict[str, Any]:
        route = await self.delegate.route(payload)
        row = self.storage.get(str(payload.get("job_id") or ""))
        if not row:
            return route
        checkpoint = row.get("checkpoint") or {}
        work_order = work_order_snapshot(checkpoint.get("work_order"))
        if work_order is None:
            return route
        return apply_work_order_budget(route, work_order)

    async def reassess(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.reassess(payload)


class RuntimeEngine(_RuntimeEngine):
    def __init__(self, storage: Any) -> None:
        super().__init__(storage)
        self.router = WorkOrderRouterProxy(self.router, self.storage)

    @staticmethod
    def _next_reasoning_choice(
        current_choice: dict[str, Any], strategy: dict[str, Any], role: str = "executor"
    ) -> dict[str, Any] | None:
        if current_choice.get("adapter") != "codex_cli":
            return None
        current = current_choice.get("reasoning_effort")
        ceiling = (strategy.get("reasoning_ceiling") or {}).get(role)
        if current not in _REASONING_ORDER or ceiling not in _REASONING_ORDER:
            return None
        current_idx = _REASONING_ORDER.index(current)
        ceiling_idx = _REASONING_ORDER.index(ceiling)
        if current_idx >= ceiling_idx:
            return None
        next_choice = dict(current_choice)
        next_choice["reasoning_effort"] = _REASONING_ORDER[current_idx + 1]
        reasons = list(next_choice.get("reasons") or [])
        reasons.append(f"reasoning escalation {current}->{next_choice['reasoning_effort']}")
        next_choice["reasons"] = reasons
        return next_choice

    async def _model_failover(
        self,
        *,
        route_payload: dict[str, Any],
        provider_state: dict[str, Any],
        current_choice: dict[str, Any],
        progress: dict[str, Any],
        strategy: dict[str, Any],
        reason: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        # A deterministic/no-effect repair is cheaper to retry with more reasoning
        # on the same Codex model before consuming a stronger model tier. Provider
        # failures deliberately bypass this path and still use provider failover.
        if progress.get("escalations", 0) < int(strategy["budget"].get("max_escalations", 0)):
            boosted = self._next_reasoning_choice(current_choice, strategy)
            if boosted is not None:
                progress["escalations"] = int(progress.get("escalations", 0)) + 1
                return boosted, {
                    "reason": "reasoning_effort_escalation",
                    "strategy": {"executor": boosted},
                }
        return await super()._model_failover(
            route_payload=route_payload,
            provider_state=provider_state,
            current_choice=current_choice,
            progress=progress,
            strategy=strategy,
            reason=reason,
        )

    def _record_agent_attempt(self, progress: dict[str, Any], choice: dict[str, Any], run: Any) -> None:
        super()._record_agent_attempt(progress, choice, run)
        attempts = progress.get("agent_attempts") or []
        if attempts:
            attempts[-1]["reasoning_effort"] = choice.get("reasoning_effort")

    async def resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool = False,
        reroute: bool = False,
        _allow_failed_orchestrated_resume: bool = False,
    ) -> dict[str, Any]:
        """Resume a paused job, optionally replacing only its stale route state.

        Explicit reroute preserves the deterministic job/workspace, WorkOrder,
        plan and all progress/budget counters. A fresh route is resolved before
        the job is made runnable, so a Router failure leaves the job blocked.
        """
        self._restore_work_order_task(job_id)
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        resumable_statuses = {"queued", "interrupted", "blocked"}
        # Only main.py may set this after it has confirmed that this exact job
        # belongs to a blocked agent WorkOrder in a blocked orchestration plan.
        # It is deliberately not part of the public run request contract.
        if _allow_failed_orchestrated_resume:
            resumable_statuses.add("failed")
        if row["status"] not in resumable_statuses:
            raise RuntimeError(f"Job cannot be resumed from status={row['status']}")

        checkpoint = checkpoint_from_row(row)
        if reset_transient_provider_failures:
            checkpoint = clear_transient_provider_failures(checkpoint)

        fields: dict[str, Any] = {
            "status": "queued",
            "error": None,
            "checkpoint": checkpoint,
        }
        if reroute:
            repo_analysis = row.get("repo_analysis")
            source_commit = str(row.get("source_commit") or "").strip()
            if not isinstance(repo_analysis, dict) or "estimated_files" not in repo_analysis:
                raise RuntimeError("Explicit reroute requires persisted repository analysis")
            if not source_commit:
                raise RuntimeError("Explicit reroute requires a persisted source commit")

            checkpoint = clear_routing_choices_for_resume(checkpoint)
            provider_state = dict(checkpoint.get("provider_state") or {})
            fresh_route = await self.router.route({
                "job_id": job_id,
                "project_id": row["project_id"],
                "repository": row["project_id"],
                "source_commit": source_commit,
                "task": row["task"],
                "repo": repo_analysis,
                "provider_state": provider_state,
            })
            route_history = list(checkpoint.get("route_history") or [])
            route_history.append({"reason": "explicit_resume_reroute", "route": fresh_route})
            checkpoint["route_history"] = route_history
            checkpoint["provider_state"] = provider_state
            fields["route"] = fresh_route
            fields["checkpoint"] = checkpoint

        self.storage.update(job_id, **fields)
        await self.enqueue(job_id)
        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    def create_job(self, payload: dict[str, Any]) -> str:
        """Create one job with its governing baseline/contract in the same write.

        `_job_id` is an internal-only idempotency hook used by the durable plan
        orchestrator. Public API models never expose it. Reusing the same id is
        accepted only when the persisted project and WorkOrder identity match.
        """

        project = project_config(payload["project_id"])
        work_order = work_order_snapshot(payload.get("work_order"))
        requested_revision = (
            work_order.baseline_revision if work_order is not None else payload.get("baseline_revision")
        )
        baseline = resolve_project_baseline(payload["project_id"], requested_revision)

        if work_order is not None:
            validate_work_order_against_baseline(work_order, baseline, project)
            task = canonical_task_from_work_order(work_order)
        else:
            task = payload.get("task")
            if not isinstance(task, dict):
                raise ValueError("Legacy job creation requires task when work_order is absent")

        requested_job_id = str(payload.get("_job_id") or "").strip()
        job_id = requested_job_id or uuid.uuid4().hex
        if requested_job_id:
            try:
                uuid.UUID(hex=requested_job_id)
            except ValueError as exc:
                raise ValueError("Internal orchestrator job id must be a UUID hex value") from exc
            existing = self.storage.get(job_id)
            if existing is not None:
                existing_checkpoint = existing.get("checkpoint") or {}
                existing_work_order = work_order_snapshot(existing_checkpoint.get("work_order"))
                if (
                    existing.get("project_id") != payload["project_id"]
                    or work_order is None
                    or existing_work_order is None
                    or existing_work_order.id != work_order.id
                    or existing_work_order.baseline_revision != work_order.baseline_revision
                ):
                    raise RuntimeError("Deterministic orchestrator job id collides with different job metadata")
                return job_id

        checkpoint = {
            "hints": payload.get("repo_hints", {}),
            "provider_state": payload.get("provider_state", {}),
            "route_history": [],
            "approved_decisions": [],
        }
        if baseline is not None:
            checkpoint["project_baseline"] = baseline.model_dump(mode="json")
        if work_order is not None:
            checkpoint["work_order"] = work_order.model_dump(mode="json")

        self.storage.create({
            "id": job_id,
            "project_id": payload["project_id"],
            "status": "queued",
            "source_commit": payload.get("source_commit"),
            "task": task,
            "repo_analysis": None,
            "progress": self._new_progress(),
            "checkpoint": checkpoint,
            "dry_run": bool(payload.get("dry_run", False)),
        })
        return job_id

    def _restore_work_order_task(self, job_id: str) -> None:
        row = self.storage.get(job_id)
        if not row:
            return
        checkpoint = row.get("checkpoint") or {}
        work_order = work_order_snapshot(checkpoint.get("work_order"))
        if work_order is None:
            return
        canonical = rehydrate_task_from_work_order(row.get("task"), work_order)
        if canonical != row.get("task"):
            self.storage.update(job_id, task=canonical)

    async def run_job(self, job_id: str) -> None:
        self._restore_work_order_task(job_id)
        try:
            await super().run_job(job_id)
        except WorkOrderPolicyError as exc:
            row = self.storage.get(job_id)
            if not row:
                raise
            checkpoint = dict(row.get("checkpoint") or {})
            progress = dict(row.get("progress") or self._new_progress())
            self._block(
                job_id=job_id,
                progress=progress,
                checkpoint=checkpoint,
                reason="work_order_policy_rejected",
                last_failure=str(exc),
            )

    async def _verify(
        self,
        job_id: str,
        project_id: str,
        workspace: Any,
        project: dict[str, Any],
        strategy: dict[str, Any],
        started: float,
        progress: dict[str, Any],
    ) -> dict[str, Any]:
        result = await super()._verify(
            job_id,
            project_id,
            workspace,
            project,
            strategy,
            started,
            progress,
        )
        row = self.storage.get(job_id)
        checkpoint = (row or {}).get("checkpoint") or {}
        work_order = work_order_snapshot(checkpoint.get("work_order"))
        if work_order is None or not result.get("passed", False):
            return result

        required = set(work_order.verification.required_phases)
        base_profile = str(strategy.get("profile") or "")
        extra_phases: list[str] = []
        if "full_tests" in required and base_profile not in {"complex", "critical"}:
            extra_phases.append("full_tests")

        for phase in extra_phases:
            commands = project.get("ddev", {}).get(phase, []) or []
            count = len(commands)
            budget = strategy["budget"]
            if (
                progress["tool_calls"] + int(result.get("tool_calls", 0)) + count
                > int(budget["max_tool_calls"])
                or progress["test_runs"] + int(result.get("test_runs", 0)) + count
                > int(budget["max_test_runs"])
            ):
                result["passed"] = False
                result["tests_passed"] = False
                result["failure_text"] = (
                    str(result.get("failure_text") or "")
                    + f"\n{phase}: WorkOrder-required verification would exceed execution budget"
                ).strip()[-30000:]
                return result

            phase_result = await self.ddev.phase(
                job_id=job_id,
                project_id=project_id,
                workspace=str(workspace),
                phase=phase,
                timeout_seconds=self._remaining_seconds(strategy, started, 1200),
            )
            result.setdefault("phases", []).append(phase_result)
            result["tool_calls"] = int(result.get("tool_calls", 0)) + len(phase_result.get("commands", []))
            result["test_runs"] = int(result.get("test_runs", 0)) + len(phase_result.get("commands", []))
            if not phase_result.get("passed", False):
                result["passed"] = False
                result["tests_passed"] = False
                result["failure_text"] = (
                    str(result.get("failure_text") or "") + "\n" + str(phase_result)
                ).strip()[-30000:]
                return result

        return result


__all__ = ["RuntimeEngine"]
