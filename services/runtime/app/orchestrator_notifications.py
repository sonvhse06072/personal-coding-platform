from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from .control_actions_attention import ControlActionService
from .legacy_adaptive_recovery import LegacyAdaptiveRecovery
from .provider_capacity_recovery import ProviderCapacityRecovery
from .orchestrator_merge import PlanOrchestrator as CorePlanOrchestrator


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
        self.provider_capacity_recovery = ProviderCapacityRecovery(storage, engine, self.store)
        self.legacy_adaptive_recovery = LegacyAdaptiveRecovery(storage, engine, self.store)
        self._notification_tick_lock = asyncio.Lock()
        if controls is not None and hasattr(controls, "orchestrator"):
            controls.orchestrator = self

    async def start(self) -> None:
        self.store.ensure()
        self.controls.ensure()
        self._supersede_obsolete_attention()
        # Core start calls self.tick(), and this subclass materializes all stable
        # attention states after that tick. Existing blocked/waiting/merge gates
        # therefore receive controls after an upgrade without being resumed unless
        # the narrow legacy-adaptive recovery policy proves them safe to continue.
        await super().start()

    async def tick(self) -> dict[str, Any]:
        async with self._notification_tick_lock:
            # Provider-capacity recovery has priority for already-blocked work:
            # authoritative post-failure quota evidence may reopen the exact same
            # job without Human Owner state clearing.
            provider_recovered = await self.provider_capacity_recovery.recover_one()

            # Recover an already-blocked pre-adaptive job before core scheduling so
            # rollout cannot launch unrelated work ahead of the preserved job.
            legacy_recovered = None
            if provider_recovered is None:
                legacy_recovered = await self.legacy_adaptive_recovery.recover_one()

            result = await super().tick()

            # A job may have become blocked during core reconciliation. Recheck one
            # safe automatic recovery after that durable transition.
            if provider_recovered is None and legacy_recovered is None:
                provider_recovered = await self.provider_capacity_recovery.recover_one()
            if provider_recovered is None and legacy_recovered is None:
                legacy_recovered = await self.legacy_adaptive_recovery.recover_one()

            if provider_recovered is not None:
                result = {**result, "provider_capacity_recovery": provider_recovered}
            if legacy_recovered is not None:
                result = {**result, "legacy_adaptive_recovery": legacy_recovered}

            # Retire obsolete durable attention before the transport can claim
            # another row. Sent/executed audit history is never rewritten.
            self._supersede_obsolete_attention()

            # Read-only observation after every core transition/launch. Dedupe keys
            # are tied to durable state generation and the rendered action set.
            self._notify_existing_attention_states()
            return result

    def _supersede_obsolete_attention(self) -> None:
        supersede_notifications = getattr(
            self.store,
            "supersede_obsolete_notifications",
            None,
        )
        if callable(supersede_notifications):
            supersede_notifications()
        supersede_actions = getattr(self.controls, "supersede_obsolete_actions", None)
        if callable(supersede_actions):
            supersede_actions()

    def _notify_existing_attention_states(self) -> None:
        with self.storage.connect() as conn:
            plans = list(
                conn.execute(
                    """SELECT plan_id FROM cp_plan_orchestrations
                    WHERE lifecycle='active' AND status <> 'completed'
                    ORDER BY created_at, plan_id"""
                ).fetchall()
            )
        for item in plans:
            plan_id = str(item["plan_id"])
            plan = self._plan_context(plan_id)
            for row in self.store.work_orders(plan_id):
                current = dict(row)
                if str(current.get("lifecycle") or "active") != "active":
                    continue
                state = str(current.get("state") or "")
                if state not in {"blocked", "waiting_human", "awaiting_merge"}:
                    continue
                self._emit_attention_for_state(plan, current, state)

    async def _reconcile_plan(self, plan: dict[str, Any]) -> None:
        tracked = {
            str(row["work_order_id"]): dict(row)
            for row in self.store.work_orders(str(plan["plan_id"]))
            if str(row.get("lifecycle") or "active") == "active"
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

        if state == "awaiting_merge":
            pr_url = str(current.get("pr_url") or "") or None
            advisory = self.controls.manual_merge_advisory(pr_url)
            generation = self._attention_generation_fingerprint(
                plan,
                current,
                job,
                advisory,
            )
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
                suffix=f"attention:manual-merge:{generation}:{action_fingerprint}",
                github_url=pr_url,
                attention_state=state,
                attention_generation=f"{generation}:{action_fingerprint}",
                payload={
                    "pr_number": current.get("pr_number"),
                    "advisory": self._public_advisory(advisory),
                    "actions": actions,
                },
            )
            return

        if state == "waiting_human":
            advisory = self.controls.waiting_human_advisory(current, job)
            generation = self._attention_generation_fingerprint(
                plan,
                current,
                job,
                advisory,
            )
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
                suffix=f"attention:waiting-human:{generation}:{action_fingerprint}",
                attention_state=state,
                attention_generation=f"{generation}:{action_fingerprint}",
                payload={
                    "job_id": job_id or None,
                    "advisory": self._public_advisory(advisory),
                    "actions": actions,
                },
            )
            return

        advisory = self.controls.blocked_advisory(current, job)
        generation = self._attention_generation_fingerprint(
            plan,
            current,
            job,
            advisory,
        )
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
            suffix=f"attention:blocked:{reason}:{generation}:{action_fingerprint}",
            attention_state=state,
            attention_generation=f"{generation}:{action_fingerprint}",
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
        if str(row.get("lifecycle") or "active") != "active":
            raise RuntimeError("Superseded WorkOrders do not require operator recovery")
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
                str(
                    action.get("action_type")
                    or ("callback" if action.get("callback_data") else "")
                ),
                str(action.get("url") or ""),
            )
            for action in actions
            if isinstance(action, dict)
        ]
        return hashlib.sha256(repr(normalized).encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _attention_generation_fingerprint(
        plan: dict[str, Any],
        work_order: dict[str, Any],
        job: dict[str, Any] | None,
        advisory: dict[str, Any],
    ) -> str:
        snapshot = {
            "plan_id": plan.get("plan_id") or plan.get("id"),
            "plan_status": plan.get("status"),
            "work_order_id": work_order.get("work_order_id"),
            "work_order_state": work_order.get("state"),
            "execution_mode": work_order.get("execution_mode"),
            "job_id": (job or {}).get("id"),
            "job_status": (job or {}).get("status"),
            "pr_number": work_order.get("pr_number"),
            "pr_url": work_order.get("pr_url"),
            "detail": work_order.get("detail") or {},
            "job_result": (job or {}).get("result") or {},
            "advisory_reason": advisory.get("reason"),
            "action_specs": advisory.get("action_specs") or [],
        }
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

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
        attention_state: str | None = None,
        attention_generation: str | None = None,
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
            attention_state=attention_state,
            attention_generation=attention_generation,
        )
