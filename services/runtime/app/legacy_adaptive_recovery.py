from __future__ import annotations

import asyncio
from typing import Any

from .state import checkpoint_from_row, clear_routing_choices_for_resume
from .storage import now
from .work_order import apply_work_order_budget, work_order_snapshot


_ANOMALY_SIGNALS = {
    "diff_oscillation",
    "no_progress",
    "scope_expansion",
    "decision_boundary",
    "hard_budget_overrun",
}


class LegacyAdaptiveRecovery:
    """Auto-adopt current adaptive envelopes for safe pre-adaptive jobs.

    This bridge exists only for orchestrated WorkOrders whose raw durable
    ExecutionPlan predates ``budget.mode``. Explicit ``legacy_hard`` contracts
    are never adopted automatically. Durable usage, source/workspace, diff and
    WorkOrder scope remain untouched; only the effective Router route is
    refreshed after a fail-closed health reassessment.
    """

    def __init__(self, storage: Any, engine: Any, store: Any) -> None:
        self.storage = storage
        self.engine = engine
        self.store = store
        self._lock = asyncio.Lock()

    async def recover_one(self) -> dict[str, Any] | None:
        if self._lock.locked():
            return None
        async with self._lock:
            if self.store.any_busy_work_order():
                return None

            with self.storage.connect() as conn:
                plans = list(
                    conn.execute(
                        """SELECT plan_id
                        FROM cp_plan_orchestrations
                        WHERE status='blocked'
                        ORDER BY updated_at, plan_id"""
                    ).fetchall()
                )

            for item in plans:
                plan_id = str(item["plan_id"])
                execution = dict(self.storage.get_execution_plan(plan_id) or {})
                plan_doc = dict(execution.get("plan") or {})
                definitions = {
                    str(value.get("id") or ""): value
                    for value in plan_doc.get("work_orders") or []
                    if isinstance(value, dict)
                }

                for tracked_row in self.store.work_orders(plan_id):
                    tracked = dict(tracked_row)
                    if str(tracked.get("state") or "") != "blocked":
                        continue
                    if str(tracked.get("execution_mode") or "") != "agent":
                        continue
                    job_id = str(tracked.get("job_id") or "")
                    if not job_id:
                        continue

                    work_order_id = str(tracked.get("work_order_id") or "")
                    raw_work_order = definitions.get(work_order_id)
                    if not self._is_pre_adaptive_work_order(raw_work_order):
                        continue

                    job = self.storage.get(job_id)
                    if not job or str(job.get("status") or "") != "blocked":
                        continue
                    if not self._is_budget_only_block(job):
                        continue

                    recovered = await self._try_adopt(
                        plan_id=plan_id,
                        tracked=tracked,
                        raw_work_order=raw_work_order,
                        job=dict(job),
                    )
                    if recovered is not None:
                        return recovered

            return None

    @staticmethod
    def _is_pre_adaptive_work_order(raw_work_order: Any) -> bool:
        if not isinstance(raw_work_order, dict):
            return False
        budget = raw_work_order.get("budget")
        return isinstance(budget, dict) and "mode" not in budget

    @staticmethod
    def _is_budget_only_block(job: dict[str, Any]) -> bool:
        result = dict(job.get("result") or {})
        reason = str(result.get("reason") or "")
        last_failure = str(result.get("last_failure") or "").lower()

        if reason == "execution_budget_exhausted":
            return "budget exhausted" in last_failure

        if reason != "reassessment_stopped":
            return False

        reassess = dict(result.get("reassess") or {})
        signals = {str(value) for value in reassess.get("signals") or []}
        reassess_reason = str(reassess.get("reason") or "").lower()
        return "hard_budget_guard" in signals and "budget exhausted" in reassess_reason

    @staticmethod
    def _has_anomaly(signals: list[Any]) -> bool:
        for value in signals:
            signal = str(value)
            if signal in _ANOMALY_SIGNALS or signal.startswith("repeated_failure:"):
                return True
        return False

    async def _try_adopt(
        self,
        *,
        plan_id: str,
        tracked: dict[str, Any],
        raw_work_order: dict[str, Any],
        job: dict[str, Any],
    ) -> dict[str, Any] | None:
        job_id = str(job["id"])
        work_order_id = str(tracked["work_order_id"])
        checkpoint = checkpoint_from_row(job)
        persisted = work_order_snapshot(checkpoint.get("work_order"))
        if persisted is None or persisted.id != work_order_id:
            return None
        if persisted.budget.mode != "legacy_hard":
            return None

        progress = dict(job.get("progress") or {})
        if progress.get("important_decision_flags") or progress.get("unexpected_scope"):
            return None

        repo_analysis = job.get("repo_analysis")
        source_commit = str(job.get("source_commit") or "").strip()
        if not isinstance(repo_analysis, dict) or "estimated_files" not in repo_analysis:
            return None
        if not source_commit:
            return None

        provider_state = dict(checkpoint.get("provider_state") or {})
        delegate = getattr(self.engine.router, "delegate", None)
        if delegate is None:
            return None

        route_payload = {
            "job_id": job_id,
            "project_id": job["project_id"],
            "repository": job["project_id"],
            "source_commit": source_commit,
            "task": job["task"],
            "repo": repo_analysis,
            "provider_state": provider_state,
        }

        try:
            raw_route = await delegate.route(route_payload)
        except Exception:
            return None

        strategy = dict(raw_route.get("strategy") or {})
        adaptive = dict(strategy.get("adaptive_budget") or {})
        if not adaptive.get("enabled"):
            return None

        adopted_work_order = persisted.model_copy(deep=True)
        adopted_work_order.budget.mode = "adaptive"
        try:
            fresh_route = apply_work_order_budget(raw_route, adopted_work_order)
        except Exception:
            return None

        try:
            reassess = await delegate.reassess(
                {
                    "route": fresh_route,
                    "progress": progress,
                    "provider_state": provider_state,
                }
            )
        except Exception:
            return None

        signals = list(reassess.get("signals") or [])
        if reassess.get("action") != "continue" or self._has_anomaly(signals):
            return None

        previous_route = dict(job.get("route") or {})
        previous_budget = dict((previous_route.get("strategy") or {}).get("budget") or {})
        new_budget = dict((fresh_route.get("strategy") or {}).get("budget") or {})

        # Current durable usage must fit strictly inside the new emergency
        # envelope. Router reassessment already rejects overruns/exhaustion; this
        # explicit check makes the adoption audit self-evident for key counters.
        counter_map = {
            "max_model_calls": "model_calls",
            "max_tool_calls": "tool_calls",
            "max_iterations": "iteration",
            "max_repair_iterations": "repair_iterations",
            "max_test_runs": "test_runs",
            "max_wall_time_minutes": "elapsed_minutes",
        }
        for dimension, counter in counter_map.items():
            if dimension not in new_budget:
                continue
            if float(progress.get(counter, 0) or 0) >= float(new_budget[dimension]):
                return None

        checkpoint = clear_routing_choices_for_resume(checkpoint)
        route_history = list(checkpoint.get("route_history") or [])
        audit = {
            "adopted_at": now().isoformat(),
            "plan_id": plan_id,
            "work_order_id": work_order_id,
            "reason": "pre_adaptive_budget_guard_healthy",
            "previous_block_reason": dict(job.get("result") or {}).get("reason"),
            "previous_budget": previous_budget,
            "new_budget": new_budget,
            "adaptive_budget": dict((fresh_route.get("strategy") or {}).get("adaptive_budget") or {}),
            "reassess": reassess,
        }
        route_history.append({"reason": "legacy_adaptive_adoption", "route": fresh_route, "audit": audit})
        checkpoint["route_history"] = route_history[-30:]
        adoptions = list(checkpoint.get("legacy_adaptive_adoptions") or [])
        adoptions.append(audit)
        checkpoint["legacy_adaptive_adoptions"] = adoptions[-10:]
        checkpoint["provider_state"] = provider_state

        # Preserve result/diff/usage/source/workspace. Only the effective route,
        # checkpoint audit and runnable status change before the same job resumes.
        self.storage.update(
            job_id,
            status="queued",
            route=fresh_route,
            checkpoint=checkpoint,
            error=None,
        )

        detail = dict(tracked.get("detail") or {})
        detail["legacy_adaptive_adoption"] = audit
        self.store.update_work_order(
            plan_id,
            work_order_id,
            state="running",
            detail=detail,
        )
        self.store.update_plan(plan_id, status="executing")
        await self.engine.enqueue(job_id)

        return {
            "plan_id": plan_id,
            "work_order_id": work_order_id,
            "job_id": job_id,
            "previous_budget": previous_budget,
            "new_budget": new_budget,
            "reassess": reassess,
        }
