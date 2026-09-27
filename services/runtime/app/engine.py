"""Governance-aware facade for the checkpointed Runtime engine.

The implementation remains split into engine_core (lifecycle/state transitions),
engine_execution (coding/verification loop), and engine_delivery (bounded GitHub
branch/PR/CI delivery). This facade owns project-governance metadata that must be
validated and pinned atomically when a job row is first created.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from .baseline import resolve_project_baseline
from .config import project_config
from .engine_delivery import RuntimeEngine as _RuntimeEngine
from .repo import diff_state
from .scope_guard import changed_path_protected_signals
from .shell import CommandTimeoutError
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
_OWNER_BUDGET_HARD_MAX = {
    "max_model_calls": 100,
    "max_tool_calls": 500,
    "max_test_runs": 100,
    "max_wall_time_minutes": 240,
    "max_repair_iterations": 20,
    "max_iterations": 30,
}
_AGENT_TIMEOUT_CAP_BY_STATUS = {
    "planning": 1800,
    "executing": 2400,
    "evaluating": 1200,
}


def _apply_owner_budget_authorizations(
    route: dict[str, Any], checkpoint: dict[str, Any]
) -> dict[str, Any]:
    """Overlay explicit owner extensions after normal Router/WorkOrder ceilings.

    The WorkOrder remains immutable. Only audited Telegram authorizations created
    by Runtime may raise a named effective limit, and platform hard maxima still
    apply. This makes an approved extension survive later provider reroutes.
    """
    updated = deepcopy(route)
    strategy = updated.get("strategy") or {}
    budget = dict(strategy.get("budget") or {})
    for authorization in checkpoint.get("budget_authorizations") or []:
        if not isinstance(authorization, dict):
            continue
        if authorization.get("channel") != "telegram" or not authorization.get("action_id"):
            continue
        dimension = str(authorization.get("dimension") or "")
        hard_max = _OWNER_BUDGET_HARD_MAX.get(dimension)
        if hard_max is None or dimension not in budget:
            continue
        try:
            previous_limit = float(authorization["previous_limit"])
            new_limit = float(authorization["new_limit"])
            current = float(budget[dimension])
        except (KeyError, TypeError, ValueError):
            continue
        if new_limit <= previous_limit:
            continue
        authorized = min(new_limit, float(hard_max))
        effective = max(current, authorized)
        if dimension == "max_wall_time_minutes":
            budget[dimension] = effective
        else:
            budget[dimension] = int(effective)
    strategy["budget"] = budget
    updated["strategy"] = strategy
    return updated


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
        if checkpoint.get("legacy_adaptive_adoptions"):
            # The durable WorkOrder snapshot intentionally stays immutable and
            # therefore remains normalized as legacy_hard. A successful recovery
            # writes this internal audit marker only after proving raw pre-adaptive
            # provenance and healthy current-policy reassessment. Reuse adaptive
            # semantics for later reroutes so they cannot silently re-clamp the
            # same job to obsolete ceilings. Missing adaptive Router metadata
            # still fails closed inside apply_work_order_budget().
            work_order = work_order.model_copy(deep=True)
            work_order.budget.mode = "adaptive"
        bounded = apply_work_order_budget(route, work_order)
        return _apply_owner_budget_authorizations(bounded, checkpoint)

    async def staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.staff(payload)

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
        role: str = "executor",
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
                    "strategy": {role: boosted},
                }
        return await super()._model_failover(
            route_payload=route_payload,
            provider_state=provider_state,
            current_choice=current_choice,
            progress=progress,
            strategy=strategy,
            reason=reason,
            role=role,
        )

    def _record_agent_attempt(self, progress: dict[str, Any], choice: dict[str, Any], run: Any) -> None:
        super()._record_agent_attempt(progress, choice, run)
        attempts = progress.get("agent_attempts") or []
        if attempts:
            attempts[-1]["reasoning_effort"] = choice.get("reasoning_effort")

    def _block_wall_budget_command_timeout(
        self,
        job_id: str,
        exc: CommandTimeoutError,
    ) -> bool:
        """Turn only wall-budget-bounded agent timeouts into recoverable blocks.

        Planner/executor/evaluator calls receive one of the phase caps below via
        `_remaining_seconds()`. A timeout shorter than that cap is therefore
        bounded by the job's remaining wall-time budget. Exact-cap timeouts are
        treated as wall-bounded only when the persisted remaining wall time also
        matches that deadline. Ordinary per-call timeouts keep their existing
        terminal-failure semantics.
        """
        row = self.storage.get(job_id)
        if not row:
            return False
        status = str(row.get("status") or "")
        phase_cap = _AGENT_TIMEOUT_CAP_BY_STATUS.get(status)
        if phase_cap is None:
            return False

        route = dict(row.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        if self._adaptive_work_shape_nonblocking(strategy):
            # Adaptive calls are bounded by their per-operation caps rather than
            # remaining total wall time, so a CommandTimeoutError is not a
            # wall-budget recovery event.
            return False
        budget = dict(strategy.get("budget") or {})
        try:
            wall_limit = float(budget["max_wall_time_minutes"])
        except (KeyError, TypeError, ValueError):
            return False

        progress = dict(row.get("progress") or self._new_progress())
        try:
            elapsed = float(progress.get("elapsed_minutes", 0.0))
        except (TypeError, ValueError):
            return False

        remaining_seconds = max(0.0, (wall_limit - elapsed) * 60.0)
        wall_limited = (
            exc.timeout < float(phase_cap)
            or remaining_seconds <= exc.timeout + 1.0
        )
        if not wall_limited:
            return False

        # The command consumed its complete wall-bounded deadline. Persist at
        # least the wall limit before blocking so recovery selection observes an
        # actually exhausted wall-time dimension rather than stale pre-call time.
        progress["elapsed_minutes"] = round(
            max(elapsed + exc.timeout / 60.0, wall_limit),
            3,
        )
        checkpoint = checkpoint_from_row(row)
        reason = "planner_budget_exhausted" if status == "planning" else "execution_budget_exhausted"
        self._block(
            job_id=job_id,
            progress=progress,
            checkpoint=checkpoint,
            reason=reason,
            last_failure="wall-time budget exhausted",
        )
        return True

    async def resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool = False,
        reroute: bool = False,
        _allow_failed_orchestrated_resume: bool = False,
        _require_changed_file_headroom: bool = False,
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

            if _require_changed_file_headroom:
                strategy = dict(fresh_route.get("strategy") or {})
                if strategy.get("budget_mode") != "adaptive":
                    raise RuntimeError(
                        "Changed-file scope recovery requires an effective adaptive route"
                    )
                adaptive = dict(strategy.get("adaptive_budget") or {})
                dimensions = dict(adaptive.get("dimensions") or {})
                envelope = dict(dimensions.get("max_changed_files") or {})
                try:
                    working_target = int(float(envelope["working_target"]))
                    emergency_limit = int(float(envelope["emergency_limit"]))
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeError(
                        "Fresh adaptive route does not expose changed-file headroom"
                    ) from exc

                progress = dict(row.get("progress") or {})
                changed_files = int(progress.get("changed_files") or 0)
                if changed_files <= working_target:
                    raise RuntimeError(
                        "Changed-file scope recovery is stale; the working target is not exceeded"
                    )
                if changed_files > emergency_limit:
                    raise RuntimeError(
                        "Changed-file scope recovery exceeds the fresh emergency ceiling"
                    )

            route_history = list(checkpoint.get("route_history") or [])
            route_history.append({
                "reason": (
                    "changed_file_scope_policy_refresh"
                    if _require_changed_file_headroom
                    else "explicit_resume_reroute"
                ),
                "route": fresh_route,
            })
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
        except CommandTimeoutError as exc:
            if self._block_wall_budget_command_timeout(job_id, exc):
                return
            raise
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

        ddev_cfg = project.get("ddev", {}) or {}
        required_order = list(work_order.verification.required_phases)
        required = set(required_order)

        # Project-owned final checks may be required by the shape of the actual
        # diff even when an older immutable WorkOrder snapshot predates that
        # verification phase. This is deliberately path-scoped so backend-only
        # work does not pay frontend verification cost.
        auto_rules = ddev_cfg.get("auto_required_phases", []) or []
        changed_files: list[str] = []
        if auto_rules:
            current_diff = diff_state(
                Path(workspace),
                int(project.get("runtime", {}).get("max_diff_bytes", 750000)),
            )
            changed_files = list(current_diff.get("changed_files") or [])
        for rule in auto_rules:
            if not isinstance(rule, dict):
                continue
            phase = str(rule.get("phase") or "").strip()
            prefixes = [
                str(item).strip()
                for item in (rule.get("path_prefixes") or [])
                if str(item).strip()
            ]
            if (
                phase
                and prefixes
                and any(
                    path.startswith(prefix)
                    for path in changed_files
                    for prefix in prefixes
                )
                and phase not in required
            ):
                required.add(phase)
                required_order.append(phase)

        completed_phases = {
            str(item.get("phase") or "")
            for item in (result.get("phases") or [])
            if isinstance(item, dict)
        }
        extra_phases = [
            phase
            for phase in required_order
            if phase not in completed_phases
        ]

        for phase in extra_phases:
            commands = ddev_cfg.get(phase, []) or []
            if not commands:
                result["passed"] = False
                result["tests_passed"] = False
                result["failure_text"] = (
                    str(result.get("failure_text") or "")
                    + f"\n{phase}: required verification has no configured commands"
                ).strip()[-30000:]
                return result
            count = len(commands)
            budget = strategy["budget"]
            if (
                not self._adaptive_work_shape_nonblocking(strategy)
                and (
                    progress["tool_calls"] + int(result.get("tool_calls", 0)) + count
                    > int(budget["max_tool_calls"])
                    or progress["test_runs"] + int(result.get("test_runs", 0)) + count
                    > int(budget["max_test_runs"])
                )
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
            annotated = dict(phase_result)
            annotated["verification_layer"] = "final"
            annotated["required_for_final"] = True
            result.setdefault("phases", []).append(annotated)
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