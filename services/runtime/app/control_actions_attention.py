from __future__ import annotations

import json
from typing import Any

from .control_actions_reroute import ControlActionService as BaseControlActionService


_DELIVERY_ATTENTION_ACTIONS = frozenset({"retry_delivery", "recheck_ci"})


def record_owner_delivery_attention(storage: Any, action: dict[str, Any]) -> bool:
    """Persist one idempotent Human Attention event for owner delivery recovery.

    Task delivery retry counters remain execution telemetry. This event records a
    distinct fact: the Human Owner had to execute an explicit durable recovery
    control. Only successful actions are eligible, and ``action_id`` is the
    dedupe authority so a repeated read/replay cannot inflate attention metrics.
    """
    action_type = str(action.get("action_type") or "")
    if action_type not in _DELIVERY_ATTENTION_ACTIONS:
        return False
    if str(action.get("status") or "") != "executed":
        return False

    action_id = str(action.get("action_id") or "")
    job_id = str(action.get("job_id") or "")
    opened_at = action.get("created_at")
    resolved_at = action.get("updated_at")
    if not action_id or not job_id or opened_at is None or resolved_at is None:
        return False

    event_key = f"control:{job_id}:{action_id}"
    metadata = {
        "action_id": action_id,
        "action_type": action_type,
        "plan_id": str(action.get("plan_id") or "") or None,
        "work_order_id": str(action.get("work_order_id") or "") or None,
        "channel": "telegram_owner_control",
    }
    with storage.connect() as conn:
        inserted = conn.execute(
            """INSERT INTO cp_attention_events
            (job_id, event_key, category, kind, avoidable, opened_at, resolved_at, wait_seconds, metadata)
            VALUES (%s,%s,'routine_operational','owner_delivery_recovery',TRUE,%s,%s,
              GREATEST(0, EXTRACT(EPOCH FROM (%s - %s))),%s::jsonb)
            ON CONFLICT (event_key) DO NOTHING
            RETURNING id""",
            (
                job_id,
                event_key,
                opened_at,
                resolved_at,
                resolved_at,
                opened_at,
                json.dumps(metadata),
            ),
        ).fetchone()
        conn.commit()
    return inserted is not None


class ControlActionService(BaseControlActionService):
    """Add advisory Human Attention accounting after durable control success."""

    async def execute(
        self,
        action_id: str,
        *,
        telegram_user_id: str,
        telegram_chat_id: str,
    ) -> dict[str, Any]:
        result = await super().execute(
            action_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )

        # The control action is already durable and successful at this point.
        # Attention persistence is downstream observability only: a telemetry
        # outage must never roll back or reinterpret the owner action.
        try:
            with self.storage.connect() as conn:
                row = conn.execute(
                    """SELECT action_id, action_type, plan_id, work_order_id, job_id,
                              status, created_at, updated_at
                    FROM cp_control_actions WHERE action_id=%s""",
                    (action_id,),
                ).fetchone()
            if row is not None:
                record_owner_delivery_attention(self.storage, dict(row))
        except Exception:
            pass

        return result


__all__ = ["ControlActionService", "record_owner_delivery_attention"]
