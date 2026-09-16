from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.control_actions_attention import (
    BaseControlActionService,
    ControlActionService,
    record_owner_delivery_attention,
)


class FakeResult:
    def __init__(self, row=None) -> None:
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, storage) -> None:
        self.storage = storage

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split())
        if normalized.startswith("SELECT action_id, action_type"):
            return FakeResult(dict(self.storage.action) if self.storage.action else None)
        if normalized.startswith("INSERT INTO cp_attention_events"):
            event_key = params[1]
            if event_key in self.storage.event_keys:
                return FakeResult(None)
            self.storage.event_keys.add(event_key)
            self.storage.inserts.append({"sql": normalized, "params": params})
            return FakeResult({"id": len(self.storage.inserts)})
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def commit(self):
        self.storage.commits += 1


class FakeStorage:
    def __init__(self, action=None, *, fail_connect=False) -> None:
        self.action = action
        self.fail_connect = fail_connect
        self.event_keys = set()
        self.inserts = []
        self.commits = 0

    def connect(self):
        if self.fail_connect:
            raise RuntimeError("telemetry unavailable")
        return FakeConnection(self)


def action(action_type="retry_delivery", *, status="executed"):
    opened = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)
    return {
        "action_id": "opaque-delivery-action",
        "action_type": action_type,
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "job_id": "job-1",
        "status": status,
        "created_at": opened,
        "updated_at": opened + timedelta(seconds=37),
        "result": {"raw": "must-not-enter-attention-metadata"},
    }


def test_successful_retry_delivery_records_one_avoidable_routine_attention_event() -> None:
    storage = FakeStorage()

    assert record_owner_delivery_attention(storage, action()) is True
    assert record_owner_delivery_attention(storage, action()) is False

    assert len(storage.inserts) == 1
    insert = storage.inserts[0]
    sql = insert["sql"]
    params = insert["params"]
    assert "'routine_operational'" in sql
    assert "'owner_delivery_recovery'" in sql
    assert "TRUE" in sql
    assert params[0] == "job-1"
    assert params[1] == "control:job-1:opaque-delivery-action"
    assert "retry_delivery" in params[-1]
    assert "must-not-enter-attention-metadata" not in params[-1]


def test_recheck_ci_is_counted_but_unrelated_or_unsuccessful_actions_are_not() -> None:
    storage = FakeStorage()

    assert record_owner_delivery_attention(storage, action("recheck_ci")) is True
    assert record_owner_delivery_attention(storage, action("budget_extend")) is False
    assert record_owner_delivery_attention(storage, action("retry_delivery", status="failed")) is False

    assert len(storage.inserts) == 1


def test_delivery_attention_requires_durable_action_identity_and_timestamps() -> None:
    storage = FakeStorage()
    value = action()
    value["action_id"] = ""
    assert record_owner_delivery_attention(storage, value) is False

    value = action()
    value["created_at"] = None
    assert record_owner_delivery_attention(storage, value) is False

    assert storage.inserts == []


def test_execute_records_attention_only_after_success_and_telemetry_failure_is_advisory(monkeypatch) -> None:
    async def successful_execute(self, action_id, *, telegram_user_id, telegram_chat_id):
        return {"status": "executed", "action_id": action_id}

    monkeypatch.setattr(BaseControlActionService, "execute", successful_execute)
    storage = FakeStorage(action())
    service = ControlActionService.__new__(ControlActionService)
    service.storage = storage

    result = asyncio.run(
        service.execute(
            "opaque-delivery-action",
            telegram_user_id="owner",
            telegram_chat_id="chat",
        )
    )

    assert result["status"] == "executed"
    assert len(storage.inserts) == 1

    # Replaying an already successful action can repair missing telemetry but
    # cannot create a second attention event because action_id is the event key.
    asyncio.run(
        service.execute(
            "opaque-delivery-action",
            telegram_user_id="owner",
            telegram_chat_id="chat",
        )
    )
    assert len(storage.inserts) == 1

    failing_storage = FakeStorage(action(), fail_connect=True)
    service.storage = failing_storage
    result = asyncio.run(
        service.execute(
            "opaque-delivery-action",
            telegram_user_id="owner",
            telegram_chat_id="chat",
        )
    )
    assert result["status"] == "executed"


def test_failed_control_action_never_records_attention(monkeypatch) -> None:
    async def failed_execute(self, action_id, *, telegram_user_id, telegram_chat_id):
        raise RuntimeError("control failed")

    monkeypatch.setattr(BaseControlActionService, "execute", failed_execute)
    storage = FakeStorage(action())
    service = ControlActionService.__new__(ControlActionService)
    service.storage = storage

    with pytest.raises(RuntimeError, match="control failed"):
        asyncio.run(
            service.execute(
                "opaque-delivery-action",
                telegram_user_id="owner",
                telegram_chat_id="chat",
            )
        )

    assert storage.inserts == []
