from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from app.plan_orchestrator import PlanOrchestratorStore


class Result:
    def __init__(self, row=None, *, rowcount=0, rows=None):
        self.row = deepcopy(row)
        self.rowcount = rowcount
        self.rows = deepcopy(rows or [])

    def fetchone(self):
        return deepcopy(self.row)

    def fetchall(self):
        return deepcopy(self.rows)


class Connection:
    def __init__(self, storage):
        self.storage = storage

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        return None

    def execute(self, sql, params=None):
        params = list(params or [])
        normalized = " ".join(sql.split())
        if normalized.startswith("CREATE TABLE"):
            return Result()
        if normalized.startswith("INSERT INTO cp_plan_orchestrator_meta"):
            return Result()
        if normalized.startswith("UPDATE cp_plan_orchestrations SET status="):
            status, updated_at, plan_id, expected = params
            if plan_id != self.storage.plan["plan_id"] or self.storage.plan["status"] == expected:
                return Result(rowcount=0)
            self.storage.plan.update(status=status, updated_at=updated_at)
            return Result(rowcount=1)
        if normalized.startswith("SELECT * FROM cp_plan_work_orders"):
            plan_id, work_order_id = params
            row = self.storage.work_order
            if row["plan_id"] == plan_id and row["work_order_id"] == work_order_id:
                return Result(row=row)
            return Result()
        if normalized.startswith("UPDATE cp_plan_work_orders SET"):
            assignments = normalized.split(" SET ", 1)[1].split(" WHERE ", 1)[0].split(", ")
            values = params[:-2]
            for assignment, value in zip(assignments, values, strict=True):
                key = assignment.split("=", 1)[0]
                self.storage.work_order[key] = json.loads(value) if key == "detail" else value
            return Result(rowcount=1)
        if normalized.startswith("UPDATE cp_notification_outbox SET status='superseded'"):
            _, plan_id, work_order_id, attention_state, *rest = params
            except_generation = rest[0] if rest else None
            changed = 0
            for row in self.storage.notifications:
                payload = row.get("payload") or {}
                advisory = payload.get("advisory") or {}
                inferred = payload.get("attention_state")
                if not inferred and advisory.get("reason") == "awaiting_merge":
                    inferred = "awaiting_merge"
                elif not inferred and advisory.get("reason") in {
                    "human_decision_required",
                    "operator_waiting_human",
                }:
                    inferred = "waiting_human"
                elif not inferred and row.get("event_type") == "work_order_blocked":
                    inferred = "blocked"
                if (
                    row["status"] in {"pending", "delivering"}
                    and row["plan_id"] == plan_id
                    and row["work_order_id"] == work_order_id
                    and inferred == attention_state
                    and (
                        except_generation is None
                        or payload.get("attention_generation", "") != except_generation
                    )
                ):
                    row["status"] = "superseded"
                    row["lease_until"] = None
                    changed += 1
            return Result(rowcount=changed)
        if normalized.startswith("UPDATE cp_control_actions SET status='cancelled'"):
            return Result(rowcount=0)
        if normalized.startswith("UPDATE cp_notification_outbox SET status='pending'"):
            timestamp = params[1]
            changed = 0
            for row in self.storage.notifications:
                if (
                    row["status"] == "delivering"
                    and row.get("lease_until") is not None
                    and row["lease_until"] <= timestamp
                ):
                    row["status"] = "pending"
                    row["lease_until"] = None
                    changed += 1
            return Result(rowcount=changed)
        if normalized.startswith("SELECT * FROM cp_notification_outbox"):
            timestamp = params[0]
            rows = [
                row
                for row in self.storage.notifications
                if row["status"] == "pending" and row["available_at"] <= timestamp
            ]
            return Result(row=min(rows, key=lambda item: item["id"]) if rows else None)
        if normalized.startswith("UPDATE cp_notification_outbox SET status='delivering'"):
            lease_until, updated_at, event_id = params
            row = next(item for item in self.storage.notifications if item["id"] == event_id)
            row.update(
                status="delivering",
                attempts=row.get("attempts", 0) + 1,
                lease_until=lease_until,
                updated_at=updated_at,
            )
            return Result(row=row, rowcount=1)
        raise AssertionError(f"Unexpected SQL: {normalized}")


class Storage:
    def __init__(self):
        initial = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
        self.plan = {
            "plan_id": "pm-gh-5772402026",
            "status": "waiting_merge",
            "updated_at": initial,
        }
        self.work_order = {
            "plan_id": "pm-gh-5772402026",
            "work_order_id": "UI-CL-1-responsive-regression-matrix-r2",
            "state": "awaiting_merge",
            "job_id": "812aabd7ab0a5adbb18a7a5edc8d7009",
            "pr_number": 18,
            "pr_url": "https://github.com/example/chonhac/pull/18",
            "detail": {"delivery_state": "ci_success"},
            "updated_at": initial,
        }
        self.notifications = []

    def connect(self):
        return Connection(self)


def notification(event_id: int, status: str) -> dict:
    timestamp = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
    return {
        "id": event_id,
        "plan_id": "pm-gh-5772402026",
        "work_order_id": "UI-CL-1-responsive-regression-matrix-r2",
        "event_type": "human_decision_required",
        "payload": {"advisory": {"reason": "awaiting_merge"}},
        "status": status,
        "attempts": 0,
        "available_at": timestamp - timedelta(minutes=1),
        "lease_until": timestamp + timedelta(minutes=5) if status == "delivering" else None,
        "updated_at": timestamp,
    }


def test_noop_plan_and_work_order_updates_preserve_timestamps():
    storage = Storage()
    store = PlanOrchestratorStore(storage)
    plan_stamp = storage.plan["updated_at"]
    work_order_stamp = storage.work_order["updated_at"]

    assert store.update_plan(storage.plan["plan_id"], status="waiting_merge") is False
    assert store.update_work_order(
        storage.plan["plan_id"],
        storage.work_order["work_order_id"],
        state="awaiting_merge",
        pr_number=18,
        pr_url="https://github.com/example/chonhac/pull/18",
        detail={"delivery_state": "ci_success"},
    ) is False

    assert storage.plan["updated_at"] == plan_stamp
    assert storage.work_order["updated_at"] == work_order_stamp


def test_real_plan_and_work_order_changes_advance_timestamps():
    storage = Storage()
    store = PlanOrchestratorStore(storage)
    plan_stamp = storage.plan["updated_at"]
    work_order_stamp = storage.work_order["updated_at"]

    assert store.update_plan(storage.plan["plan_id"], status="completed") is True
    assert store.update_work_order(
        storage.plan["plan_id"],
        storage.work_order["work_order_id"],
        pr_number=19,
        detail={"delivery_state": "ci_success", "reason": "new_pr"},
    ) is True

    assert storage.plan["updated_at"] > plan_stamp
    assert storage.work_order["updated_at"] > work_order_stamp
    assert storage.work_order["pr_number"] == 19


def test_awaiting_merge_completion_supersedes_unsent_history_only():
    storage = Storage()
    storage.notifications = [
        notification(1, "pending"),
        notification(2, "delivering"),
        notification(3, "sent"),
    ]
    store = PlanOrchestratorStore(storage)

    assert store.update_work_order(
        storage.plan["plan_id"],
        storage.work_order["work_order_id"],
        state="completed",
        detail={"delivery_state": "ci_success", "merged_at": "2026-09-24T08:10:00Z"},
    ) is True

    assert [row["status"] for row in storage.notifications] == [
        "superseded",
        "superseded",
        "sent",
    ]
    assert len(storage.notifications) == 3
    assert store.claim_notification() is None
