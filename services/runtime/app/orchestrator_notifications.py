from __future__ import annotations

import hashlib
from typing import Any

from .plan_orchestrator import PlanOrchestrator as CorePlanOrchestrator


class PlanOrchestrator(CorePlanOrchestrator):
    """Core orchestration plus owner-attention notifications.

    Keep notification observation separate from execution-state transitions so a
    Telegram transport failure can never alter whether work runs, blocks or waits
    for manual merge.
    """

    async def _reconcile_plan(self, plan: dict[str, Any]) -> None:
        plan_id = str(plan["plan_id"])
        before = {
            str(row["work_order_id"]): dict(row)
            for row in self.store.work_orders(plan_id)
        }

        self._notify_new_quota_failures(plan, before)
        await super()._reconcile_plan(plan)

        after = {
            str(row["work_order_id"]): dict(row)
            for row in self.store.work_orders(plan_id)
        }
        for work_order_id, current in after.items():
            previous_state = str((before.get(work_order_id) or {}).get("state") or "")
            if current.get("state") == "awaiting_merge" and previous_state != "awaiting_merge":
                self._emit_attention(
                    plan,
                    work_order_id=work_order_id,
                    event_type="human_decision_required",
                    severity="warning",
                    summary="PR passed its automated gates and is ready for manual merge.",
                    suffix=f"manual-merge:{current.get('pr_number')}",
                    github_url=str(current.get("pr_url") or "") or None,
                    payload={"pr_number": current.get("pr_number")},
                )

    async def resolve_operator(
        self,
        *,
        plan_id: str,
        work_order_id: str,
        action: str,
        note: str,
    ) -> dict[str, Any]:
        # Core complete flow is safe and also reconciles downstream dependencies.
        if action != "block":
            return await super().resolve_operator(
                plan_id=plan_id,
                work_order_id=work_order_id,
                action=action,
                note=note,
            )

        rows = {row["work_order_id"]: row for row in self.store.work_orders(plan_id)}
        row = rows.get(work_order_id)
        if row is None:
            raise RuntimeError("Unknown orchestrated WorkOrder")
        if row["execution_mode"] != "operator" or row["state"] != "waiting_human":
            raise RuntimeError("WorkOrder is not waiting for an operator")

        detail = dict(row.get("detail") or {})
        detail["operator_note"] = note.strip()[:2000]
        self.store.update_work_order(plan_id, work_order_id, state="blocked", detail=detail)
        self.store.update_plan(plan_id, status="blocked")

        plan = self._plan_context(plan_id)
        self._emit_attention(
            plan,
            work_order_id=work_order_id,
            event_type="work_order_blocked",
            severity="error",
            summary="Operator marked the WorkOrder blocked.",
            suffix="operator-blocked",
        )
        result = self.view(plan_id)
        assert result is not None
        return result

    def _notify_new_quota_failures(
        self,
        plan: dict[str, Any],
        tracked: dict[str, dict[str, Any]],
    ) -> None:
        for work_order_id, row in tracked.items():
            job_id = row.get("job_id")
            if not job_id:
                continue
            job = self.storage.get(str(job_id))
            if not job:
                continue
            progress = dict(job.get("progress") or {})
            for failure in progress.get("provider_failures") or []:
                if not isinstance(failure, dict) or str(failure.get("kind") or "") != "quota_exhausted":
                    continue
                model = str(failure.get("model") or "unknown")
                provider = str(failure.get("provider") or "unknown")
                self._emit_attention(
                    plan,
                    work_order_id=work_order_id,
                    event_type="provider_quota_exhausted",
                    severity="warning",
                    summary=(
                        f"Model quota exhausted for {model} ({provider}). "
                        "The platform will continue with an eligible fallback when available."
                    ),
                    suffix=f"quota:{job_id}:{model}:{provider}",
                    payload={"job_id": job_id, "model": model, "provider": provider},
                )

    def _plan_context(self, plan_id: str) -> dict[str, Any]:
        execution = dict(self.storage.get_execution_plan(plan_id) or {})
        orchestration = dict(self.store.orchestration(plan_id) or {})
        return {
            **execution,
            **orchestration,
            "plan_id": plan_id,
            "ticket": execution.get("ticket") or {},
        }

    def _emit_attention(
        self,
        plan: dict[str, Any],
        *,
        work_order_id: str | None,
        event_type: str,
        severity: str,
        summary: str,
        suffix: str,
        github_url: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        plan_id = str(plan.get("plan_id") or plan.get("id") or "")
        if not plan_id:
            return
        ticket = dict(plan.get("ticket") or {})
        project_id = str(plan.get("project_id") or "")
        base_key = f"{project_id}:{plan_id}:{work_order_id or '-'}:{event_type}:{suffix}"
        dedupe_key = hashlib.sha256(base_key.encode("utf-8")).hexdigest()
        self.store.emit_notification(
            dedupe_key=dedupe_key,
            event_type=event_type,
            severity=severity,
            project_id=project_id,
            ticket_id=str(ticket.get("id") or plan.get("ticket_id") or "") or None,
            plan_id=plan_id,
            work_order_id=work_order_id,
            summary=summary,
            github_url=github_url or str(plan.get("github_url") or "") or None,
            payload=payload,
        )
