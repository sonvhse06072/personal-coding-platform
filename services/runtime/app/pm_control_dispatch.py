from __future__ import annotations

from typing import Any

from .plan_orchestrator import PlanContinuationConflict
from .pm_control import PMControlEnvelope


class PMControlDispatcher:
    """Dispatch a narrow allow-list onto existing Runtime state transitions."""

    SUPPORTED_ACTIONS = frozenset(
        {
            "resolve_job_decision",
            "review_repair",
            "continue_supervised_plan",
        }
    )

    def __init__(self, storage: Any, engine: Any, orchestrator: Any) -> None:
        self.storage = storage
        self.engine = engine
        self.orchestrator = orchestrator

    def supports(self, action: str) -> bool:
        return action in self.SUPPORTED_ACTIONS

    @staticmethod
    def _job_result(row: dict[str, Any]) -> dict[str, Any]:
        updated_at = row.get("updated_at")
        return {
            "job_id": str(row.get("id") or ""),
            "status": str(row.get("status") or ""),
            "updated_at": (
                updated_at.isoformat()
                if hasattr(updated_at, "isoformat")
                else str(updated_at or "")
            ),
        }

    async def execute(self, envelope: PMControlEnvelope) -> dict[str, Any]:
        if not self.supports(envelope.action):
            raise RuntimeError(
                f"PM control action is not dispatchable in this Runtime: {envelope.action}"
            )

        if envelope.action == "resolve_job_decision":
            assert envelope.job_id
            assert envelope.decision_key
            assert envelope.decision
            row = await self.engine.resolve_human_decision(
                envelope.job_id,
                action=envelope.decision,
                note=envelope.note or "",
                expected_decision_key=envelope.decision_key,
            )
            await self.orchestrator.tick()
            return {
                "action": envelope.action,
                **self._job_result(dict(row)),
                "decision_key": envelope.decision_key,
            }

        if envelope.action == "review_repair":
            assert envelope.job_id
            assert envelope.expected_commit
            assert envelope.finding
            row = await self.engine.request_review_repair(
                envelope.job_id,
                expected_commit=envelope.expected_commit,
                finding=envelope.finding,
                evidence={
                    "transport": "github_pm_control",
                    "project_id": envelope.project_id,
                },
                references=envelope.references,
            )
            return {
                "action": envelope.action,
                **self._job_result(dict(row)),
                "expected_commit": envelope.expected_commit,
            }

        assert envelope.action == "continue_supervised_plan"
        assert envelope.plan_id
        assert envelope.generation is not None
        assert envelope.continuation_key
        assert envelope.checkpoint_id is not None
        assert envelope.checkpoint_key
        assert envelope.ready_work_order_ids
        try:
            result = await self.orchestrator.continue_plan(
                plan_id=envelope.plan_id,
                generation=envelope.generation,
                continuation_key=envelope.continuation_key,
                checkpoint_id=envelope.checkpoint_id,
                checkpoint_key=envelope.checkpoint_key,
                ready_work_order_ids=envelope.ready_work_order_ids,
            )
        except PlanContinuationConflict as exc:
            raise RuntimeError(str(exc)) from exc

        return {
            "action": envelope.action,
            "plan_id": envelope.plan_id,
            "generation": envelope.generation,
            "status": str((result or {}).get("status") or ""),
            "ready_work_order_ids": list(envelope.ready_work_order_ids),
        }


__all__ = ["PMControlDispatcher"]
