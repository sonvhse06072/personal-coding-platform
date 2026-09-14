from __future__ import annotations

import hashlib
from typing import Any

from .control_actions_reroute import ControlActionService
from .plan_orchestrator import PlanOrchestrator as CorePlanOrchestrator


_SUPERSEDED_WORK_ORDER_EVENTS = {
    "human_decision_required",
    "operator_action_required",
    "work_order_blocked",
    "provider_quota_exhausted",
    "ci_failed_after_repairs",
}


class PlanOrchestrator(CorePlanOrchestrator):
    """Core orchestration plus owner-attention notifications and controls.

    Notification/control transport remains separate from execution-state
    transitions. Telegram failure can never decide whether work runs, blocks or
    waits; Runtime validates every one-time control action immediately before it
    mutates durable state.
    """

    def __init__(
        self,
        storage: Any,
        engine: Any,
        *,
        store: Any | None = None,
        controls: Any | None = None,
    ) -> None:
        super().__init__(storage, engine, store=store)
        self.controls = controls or ControlActionService(storage, engine, self.store, self)
        if controls is not None and hasattr(controls, "orchestrator"):
            controls.orchestrator = self

    async def start(self) -> None:
        self.store.ensure()
        self.controls.ensure()
        # Core start calls self.tick(), and this subclass materializes all stable
        # attention states after that tick. Existing blocked/waiting/merge gates
        # therefore receive controls after an upgrade without being resumed.
        await super().start()

    async def tick(self) -> dict[str, Any]:
        result = await super().tick()
        # Read-only observation after every core transition/launch. Dedupe keys are
        # tied to the durable WorkOrder state generation and rendered action set,
        # so polling is quiet while a rollout may still surface newly valid actions.
        self._notify_existing_attention_states()
        return result

    def _notify_existing_attention_states(self) -> None:
        with self.storage.connect() as conn:
            plans = list(
                conn.execute(
                    """SELECT plan_id FROM cp_plan_orchestrations
                    WHERE status <> 'completed'
                    ORDER BY created_at, plan_id"""
                ).fetchall()
            )
        for item in plans:
            plan_id = str(item["plan_id"])
            plan = self._plan_context(plan_id)
            for row in self.store.work_orders(plan_id):
                current = dict(row)
                state = str(current.get("state") or "")
                if state not in {"blocked", "waiting_human", "awaiting_merge"}:
                    continue
                self._emit_attention_for_state(plan, current, state)

    async def _reconcile_plan(self, plan: dict[str, Any]) -> None:
        tracked = {
            str(row["work_order_id"]): dict(row)
            for row in self.store.work_orders(str(plan["plan_id"]))
        }
        # Provider quota exhaustion while the job is still active is informative;
        # no mutation button is emitted because automatic failover may still work.
        self._notify_new_quota_failures(plan, tracked)
        await super()._reconcile_plan(plan)

    def _emit_attention_for_state(
        self,
        plan: dict[str, Any],
        current: dict[str, Any],
        state: str,
    ) -> None:
        work_order_id = str(current.get("work_order_id") or "")
        job_id = str(current.get("job_id") or "")
        job = self.storage.get(job_id) if job_id else None
        job = dict(job) if job else None
        stamp = current.get("updated_at") or "unknown"

        if state == "awaiting_merge":
            pr_url = str(current.get("pr_url") or "") or None
            advisory = self.controls.manual_merge_advisory(pr_url)
            actions = self.controls.create_actions(
                plan=plan,
                work_order=current,
                job=job,
                advisory=advisory,
            )
            action_fingerprint = self._action_set_fingerprint(actions)
            self._emit_attention(
                plan,
                work_order_id=work_order_id,
                event_type="human_decision_required",
                severity="warning",
                summary=advisory["summary"],
                suffix=f"attention:manual-merge:{current.get('pr_number')}:{stamp}:{action_fingerprint}",
                github_url=pr_url,
                payload={
                    "pr_number": current.get("pr_number"),
                    "advisory": self._public_advisory(advisory),
                    "actions": actions,
                },
            )
            return

        if state == "waiting_human":
            advisory = self.controls.waiting_human_advisory(current, job)
            actions = self.controls.create_actions(
                plan=plan,
                work_order=current,
                job=job,
                advisory=advisory,
            )
            action_fingerprint = self._action_set_fingerprint(actions)
            self._emit_attention(
                plan,
                work_order_id=work_order_id,
                event_type="human_decision_required",
                severity="warning",
                summary=advisory["summary"],
                suffix=f"attention:waiting-human:{job_id or 'operator'}:{stamp}:{action_fingerprint}",
                payload={
                    "job_id": job_id or None,
                    "advisory": self._public_advisory(advisory),
                    "actions": actions,
                },
            )
            return

        advisory = self.controls.blocked_advisory(current, job)
        actions = self.controls.create_actions(
            plan=plan,
            work_order=current,
            job=job,
            advisory=advisory,
        )
        reason = str(advisory.get("reason") or "blocked")
        action_fingerprint = self._action_set_fingerprint(actions)
        self._emit_attention(
            plan,
            work_order_id=work_order_id,
            event_type="work_order_blocked",
            severity="error",
            summary=advisory["summary"],
            suffix=f"attention:blocked:{job_id or 'operator'}:{reason}:{stamp}:{action_fingerprint}",
            payload={
                "job_id": job_id or None,
                "advisory": self._public_advisory(advisory),
                "actions": actions,
            },
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
        # For block we perform the same state transition but leave notification
        # formatting to the post-tick attention materializer.
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
        detail["reason"] = "operator_blocked"
        self.store.update_work_order(plan_id, work_order_id, state="blocked", detail=detail)
        self.store.update_plan(plan_id, status="blocked")
        await self.tick()
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
                advisory = {
                    "title": "PROVIDER QUOTA EXHAUSTED",
                    "phase": "provider",
                    "reason": "provider_quota_exhausted",
                    "summary": f"Model quota exhausted for {model} ({provider}).",
                    "cause": "The provider reported quota exhaustion. Runtime will use an eligible fallback when policy and remaining budget allow it.",
                    "preserved": ["The current job/workspace and durable progress remain preserved."],
                    "impact": "No owner action is required while Runtime is actively failing over. If the WorkOrder blocks, a separate actionable notification will be sent.",
                    "recommended": "Wait for the provider quota window to reset only if no fallback completes the WorkOrder.",
                    "metrics": [
                        {"label": "Model", "value": model},
                        {"label": "Provider", "value": provider},
                    ],
                }
                self._emit_attention(
                    plan,
                    work_order_id=work_order_id,
                    event_type="provider_quota_exhausted",
                    severity="warning",
                    summary=advisory["summary"],
                    suffix=f"quota:{job_id}:{model}:{provider}",
                    payload={
                        "job_id": job_id,
                        "model": model,
                        "provider": provider,
                        "advisory": advisory,
                        "actions": [],
                    },
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

    @staticmethod
    def _public_advisory(advisory: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in advisory.items() if key != "action_specs"}

    @staticmethod
    def _action_set_fingerprint(actions: list[dict[str, Any]]) -> str:
        normalized = [
            (
                str(action.get("label") or ""),
                str(action.get("action_id") or ""),
                str(action.get("callback_data") or ""),
                str(action.get("url") or ""),
            )
            for action in actions
            if isinstance(action, dict)
        ]
        return hashlib.sha256(repr(normalized).encode("utf-8")).hexdigest()[:16]

    def _notify(
        self,
        plan: dict[str, Any],
        *,
        work_order_id: str | None,
        event_type: str,
        severity: str,
        summary: str,
        suffix: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        # Core owns state transitions but its work-order attention notifications
        # are intentionally superseded by the sanitized advisory materializer.
        # Plan-level decision/completion events continue through core unchanged.
        if work_order_id is not None and event_type in _SUPERSEDED_WORK_ORDER_EVENTS:
            return
        super()._notify(
            plan,
            work_order_id=work_order_id,
            event_type=event_type,
            severity=severity,
            summary=summary,
            suffix=suffix,
            payload=payload,
        )

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
