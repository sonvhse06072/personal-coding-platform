from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from .orchestrator_resume import prepare_orchestrated_job_resume, reopen_orchestrated_job
from .quota_runtime import quota_coordinator
from .state import (
    checkpoint_from_row,
    clear_routing_choices_for_resume,
    migrate_legacy_provider_quota_failure,
)
from .storage import now


_PROVIDER_BLOCK_REASONS = {
    "planner_provider_failure_without_fallback",
    "provider_failure_without_fallback",
    "evaluator_provider_failure_without_fallback",
}


class ProviderCapacityRecovery:
    """Resume one blocked orchestrated job after authoritative quota recovery.

    No state is cleared because time merely passed. Recovery requires a durable
    quota/rate-limit marker, a newer authoritative available snapshot for the
    same quota key, and a fresh Router route using all remaining durable health.
    """

    def __init__(
        self,
        storage: Any,
        engine: Any,
        store: Any,
        *,
        coordinator: Any = quota_coordinator,
    ) -> None:
        self.storage = storage
        self.engine = engine
        self.store = store
        self.coordinator = coordinator
        self._lock = asyncio.Lock()

    async def recover_one(self) -> dict[str, Any] | None:
        if self._lock.locked() or self.store.any_busy_work_order():
            return None

        async with self._lock:
            with self.storage.connect() as conn:
                plans = list(
                    conn.execute(
                        """SELECT plan_id FROM cp_plan_orchestrations
                        WHERE lifecycle='active' AND status='blocked'
                        ORDER BY updated_at, plan_id"""
                    ).fetchall()
                )

            for item in plans:
                plan_id = str(item["plan_id"])
                for tracked_raw in self.store.work_orders(plan_id):
                    tracked = dict(tracked_raw)
                    if str(tracked.get("lifecycle") or "active") != "active":
                        continue
                    if str(tracked.get("state") or "") != "blocked":
                        continue
                    if str(tracked.get("execution_mode") or "") != "agent":
                        continue
                    job_id = str(tracked.get("job_id") or "")
                    if not job_id:
                        continue

                    job_raw = self.storage.get(job_id)
                    if not job_raw:
                        continue
                    job = dict(job_raw)
                    if str(job.get("status") or "") != "blocked":
                        continue
                    if str((job.get("result") or {}).get("reason") or "") not in _PROVIDER_BLOCK_REASONS:
                        continue

                    recovered = await self._try_recover(
                        plan_id=plan_id,
                        tracked=tracked,
                        job=job,
                    )
                    if recovered is not None:
                        return recovered

            return None

    async def _try_recover(
        self,
        *,
        plan_id: str,
        tracked: dict[str, Any],
        job: dict[str, Any],
    ) -> dict[str, Any] | None:
        progress = deepcopy(job.get("progress") or {})
        if progress.get("important_decision_flags") or progress.get("unexpected_scope"):
            return None

        checkpoint = checkpoint_from_row(job)
        migrated = migrate_legacy_provider_quota_failure(
            checkpoint,
            progress,
            failed_at=job.get("updated_at"),
        )
        durable_state = {
            str(key): dict(value or {})
            for key, value in (migrated.get("provider_state") or {}).items()
        }

        _, rehabilitated, telemetry = await self.coordinator.reconcile(durable_state)
        if not rehabilitated:
            return None

        # Authoritative post-failure evidence lets us remove only those exact
        # durable quota failures. Unrelated provider/model/quota failures remain.
        cleaned_state = {
            key: value
            for key, value in durable_state.items()
            if key not in set(rehabilitated)
        }

        repo_analysis = job.get("repo_analysis")
        source_commit = str(job.get("source_commit") or "").strip()
        if not isinstance(repo_analysis, dict) or "estimated_files" not in repo_analysis:
            return None
        if not source_commit:
            return None

        route_payload = {
            "job_id": str(job["id"]),
            "project_id": str(job["project_id"]),
            "repository": str(job["project_id"]),
            "source_commit": source_commit,
            "task": job["task"],
            "repo": repo_analysis,
            "provider_state": cleaned_state,
        }
        try:
            fresh_route = await self.engine.router.route(route_payload)
        except Exception:
            # Do not mutate durable state if recovered capacity still does not
            # produce an eligible route.
            return None

        context = prepare_orchestrated_job_resume(self.store, str(job["id"]))
        if not context or not bool(context.get("reopen")):
            return None

        checkpoint = clear_routing_choices_for_resume(migrated)
        checkpoint["provider_state"] = cleaned_state
        route_history = list(checkpoint.get("route_history") or [])
        audit = {
            "recovered_at": now().isoformat(),
            "plan_id": plan_id,
            "work_order_id": str(tracked.get("work_order_id") or ""),
            "reason": "authoritative_quota_capacity_recovered",
            "rehabilitated_keys": list(rehabilitated),
            "prior_block_reason": str((job.get("result") or {}).get("reason") or ""),
            "telemetry": {
                key: deepcopy(telemetry.get(key))
                for key in rehabilitated
                if key in telemetry
            },
        }
        route_history.append({
            "reason": "authoritative_quota_recovery",
            "route": fresh_route,
            "audit": audit,
        })
        checkpoint["route_history"] = route_history[-30:]
        recoveries = list(checkpoint.get("provider_capacity_recoveries") or [])
        recoveries.append(audit)
        checkpoint["provider_capacity_recoveries"] = recoveries[-20:]

        # All eligibility checks above are read-only. Only now reopen the exact
        # same durable job/WorkOrder/plan and enqueue it.
        self.storage.update(
            str(job["id"]),
            status="queued",
            route=fresh_route,
            checkpoint=checkpoint,
            error=None,
        )
        context = dict(context)
        detail = deepcopy(context.get("detail") or {})
        detail["provider_capacity_recovery"] = audit
        context["detail"] = detail
        reopen_orchestrated_job(self.store, context, str(job["id"]))
        await self.engine.enqueue(str(job["id"]))

        return {
            "plan_id": plan_id,
            "work_order_id": str(tracked.get("work_order_id") or ""),
            "job_id": str(job["id"]),
            "rehabilitated_keys": list(rehabilitated),
            "route": fresh_route,
        }
