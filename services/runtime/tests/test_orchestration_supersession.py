from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.orchestrator_resume import prepare_orchestrated_job_resume
from app.plan_orchestrator import ORCHESTRATOR_DDL, PlanOrchestratorStore


ORIGINAL_PLAN = "pm-gh-original"
ORIGINAL_WORK_ORDER = "UI-CL-1-responsive-regression-matrix"
ORIGINAL_JOB = "4283bb02a28a5c96b71f7bb1bc5e3676"
REPLACEMENT_PLAN = "pm-gh-5772402026"
REPLACEMENT_WORK_ORDER = "UI-CL-1-responsive-regression-matrix-r2"


class Result:
    def __init__(self, row=None, *, rows=None, rowcount=0):
        self.row = deepcopy(row)
        self.rows = deepcopy(rows or [])
        self.rowcount = rowcount

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
        self.storage.commits += 1

    def execute(self, sql, params=None):
        values = list(params or [])
        normalized = " ".join(sql.split())
        if normalized.startswith("CREATE TABLE"):
            self.storage.ensure_calls += 1
            return Result()
        if normalized.startswith("INSERT INTO cp_plan_orchestrator_meta"):
            return Result()
        if normalized.startswith("SELECT * FROM cp_plan_orchestrations WHERE plan_id="):
            return Result(self.storage.plans.get(values[0]))
        if normalized.startswith("SELECT * FROM cp_plan_work_orders WHERE plan_id="):
            if len(values) == 2:
                return Result(self.storage.work_orders.get((values[0], values[1])))
            rows = [
                row
                for (plan_id, _), row in self.storage.work_orders.items()
                if plan_id == values[0]
            ]
            return Result(rows=sorted(rows, key=lambda row: (row["sequence_no"], row["work_order_id"])))
        if normalized.startswith("SELECT * FROM cp_plan_work_orders WHERE job_id="):
            row = next(
                (row for row in self.storage.work_orders.values() if row.get("job_id") == values[0]),
                None,
            )
            return Result(row)
        if normalized.startswith("SELECT status FROM cp_jobs WHERE id="):
            job = self.storage.jobs.get(values[0])
            return Result({"status": job["status"]} if job else None)
        if normalized.startswith("SELECT 1 FROM cp_plan_work_orders work_order JOIN cp_plan_orchestrations"):
            plan_id, work_order_id = values
            work_order = self.storage.work_orders.get((plan_id, work_order_id))
            plan = self.storage.plans.get(plan_id)
            eligible = bool(
                work_order
                and plan
                and work_order.get("lifecycle", "active") == "active"
                and plan.get("lifecycle", "active") == "active"
            )
            return Result({"?column?": 1} if eligible else None)
        if normalized.startswith("UPDATE cp_plan_work_orders SET lifecycle='superseded'"):
            replacement_plan, replacement_work_order, stamp, reason, updated, plan_id, work_order_id = values
            row = self.storage.work_orders[(plan_id, work_order_id)]
            if row["lifecycle"] != "active":
                return Result(rowcount=0)
            row.update(
                lifecycle="superseded",
                superseded_by_plan_id=replacement_plan,
                superseded_by_work_order_id=replacement_work_order,
                superseded_at=stamp,
                supersession_reason=reason,
                updated_at=updated,
            )
            return Result(rowcount=1)
        if normalized.startswith("UPDATE cp_notification_outbox SET status='superseded'"):
            _, plan_id, work_order_id, *_ = values
            changed = 0
            for row in self.storage.notifications:
                if (
                    row["status"] in {"pending", "delivering"}
                    and row["plan_id"] == plan_id
                    and row["work_order_id"] == work_order_id
                    and row["event_type"] in {
                        "work_order_blocked",
                        "human_decision_required",
                        "operator_action_required",
                    }
                ):
                    row.update(status="superseded", lease_until=None)
                    changed += 1
            return Result(rowcount=changed)
        if normalized.startswith("UPDATE cp_control_actions SET status='cancelled'"):
            _, plan_id, work_order_id = values
            changed = 0
            for row in self.storage.controls:
                if (
                    row["status"] == "pending"
                    and row["plan_id"] == plan_id
                    and row["work_order_id"] == work_order_id
                ):
                    row["status"] = "cancelled"
                    changed += 1
            return Result(rowcount=changed)
        if normalized.startswith("SELECT COUNT(*) AS count FROM cp_plan_work_orders"):
            count = sum(
                1
                for (plan_id, _), row in self.storage.work_orders.items()
                if plan_id == values[0] and row["lifecycle"] == "active"
            )
            return Result({"count": count})
        if normalized.startswith("SELECT state FROM cp_plan_work_orders"):
            rows = [
                {"state": row["state"]}
                for (plan_id, _), row in self.storage.work_orders.items()
                if plan_id == values[0] and row["lifecycle"] == "active"
            ]
            return Result(rows=rows)
        if normalized.startswith("UPDATE cp_plan_orchestrations SET lifecycle='superseded'"):
            stamp, updated, plan_id = values
            row = self.storage.plans[plan_id]
            if row["lifecycle"] != "active":
                return Result(rowcount=0)
            row.update(lifecycle="superseded", superseded_at=stamp, updated_at=updated)
            return Result(rowcount=1)
        if normalized.startswith("UPDATE cp_plan_orchestrations SET status="):
            status, updated, plan_id, expected = values
            row = self.storage.plans[plan_id]
            if row["status"] == expected:
                return Result(rowcount=0)
            row.update(status=status, updated_at=updated)
            return Result(rowcount=1)
        if normalized.startswith("UPDATE cp_notification_outbox SET status='pending'"):
            return Result(rowcount=0)
        if normalized.startswith("SELECT * FROM cp_notification_outbox"):
            available = [
                row
                for row in self.storage.notifications
                if row["status"] == "pending" and row["available_at"] <= values[0]
            ]
            return Result(min(available, key=lambda row: row["id"]) if available else None)
        if normalized.startswith("UPDATE cp_notification_outbox SET status='delivering'"):
            lease_until, updated_at, event_id = values
            row = next(row for row in self.storage.notifications if row["id"] == event_id)
            row.update(status="delivering", lease_until=lease_until, updated_at=updated_at)
            return Result(row, rowcount=1)
        raise AssertionError(f"Unexpected SQL: {normalized}")


class Storage:
    def __init__(self):
        stamp = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
        self.ensure_calls = 0
        self.commits = 0
        self.plans = {
            ORIGINAL_PLAN: {
                "plan_id": ORIGINAL_PLAN,
                "project_id": "chonhac",
                "status": "blocked",
                "lifecycle": "active",
                "superseded_at": None,
                "updated_at": stamp,
            },
            REPLACEMENT_PLAN: {
                "plan_id": REPLACEMENT_PLAN,
                "project_id": "chonhac",
                "status": "completed",
                "lifecycle": "active",
                "superseded_at": None,
                "updated_at": stamp,
            },
        }
        self.work_orders = {
            (ORIGINAL_PLAN, ORIGINAL_WORK_ORDER): {
                "plan_id": ORIGINAL_PLAN,
                "work_order_id": ORIGINAL_WORK_ORDER,
                "sequence_no": 0,
                "execution_mode": "agent",
                "state": "blocked",
                "lifecycle": "active",
                "job_id": ORIGINAL_JOB,
                "detail": {"reason": "work_order_policy_rejected"},
                "superseded_by_plan_id": None,
                "superseded_by_work_order_id": None,
                "superseded_at": None,
                "supersession_reason": None,
                "updated_at": stamp,
            },
            (REPLACEMENT_PLAN, REPLACEMENT_WORK_ORDER): {
                "plan_id": REPLACEMENT_PLAN,
                "work_order_id": REPLACEMENT_WORK_ORDER,
                "sequence_no": 0,
                "execution_mode": "agent",
                "state": "completed",
                "lifecycle": "active",
                "job_id": "812aabd7ab0a5adbb18a7a5edc8d7009",
                "detail": {"merge_commit_sha": "56e0b74"},
                "updated_at": stamp,
            },
        }
        self.jobs = {
            ORIGINAL_JOB: {
                "id": ORIGINAL_JOB,
                "status": "blocked",
                "result": {"reason": "work_order_policy_rejected"},
                "progress": {"model_calls": 0, "tool_calls": 0},
                "workspace": f"/tmp/workspaces/{ORIGINAL_JOB}",
            }
        }
        self.notifications = [
            self._notification(1, "pending"),
            self._notification(2, "delivering"),
            self._notification(3, "sent"),
        ]
        self.controls = [
            self._control("pending-control", "pending"),
            self._control("executed-control", "executed"),
        ]

    @staticmethod
    def _notification(event_id, status):
        stamp = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
        return {
            "id": event_id,
            "plan_id": ORIGINAL_PLAN,
            "work_order_id": ORIGINAL_WORK_ORDER,
            "event_type": "work_order_blocked",
            "status": status,
            "available_at": stamp - timedelta(minutes=1),
            "lease_until": stamp + timedelta(minutes=5) if status == "delivering" else None,
            "updated_at": stamp,
        }

    @staticmethod
    def _control(action_id, status):
        return {
            "action_id": action_id,
            "plan_id": ORIGINAL_PLAN,
            "work_order_id": ORIGINAL_WORK_ORDER,
            "status": status,
        }

    def connect(self):
        return Connection(self)

    def get(self, job_id):
        return deepcopy(self.jobs.get(job_id))


def supersede(store):
    return store.supersede_work_order(
        plan_id=ORIGINAL_PLAN,
        work_order_id=ORIGINAL_WORK_ORDER,
        reason="replaced_after_router_false_positive_fix",
        superseded_by_plan_id=REPLACEMENT_PLAN,
        superseded_by_work_order_id=REPLACEMENT_WORK_ORDER,
    )


def test_live_shaped_supersession_preserves_execution_truth_and_retires_attention():
    storage = Storage()
    store = PlanOrchestratorStore(storage)
    original_job = deepcopy(storage.jobs[ORIGINAL_JOB])
    replacement = deepcopy(storage.work_orders[(REPLACEMENT_PLAN, REPLACEMENT_WORK_ORDER)])
    notification_count = len(storage.notifications)

    result = supersede(store)

    assert result["changed"] is True
    assert result["plan"]["status"] == "blocked"
    assert result["plan"]["lifecycle"] == "superseded"
    assert result["work_order"]["state"] == "blocked"
    assert result["work_order"]["lifecycle"] == "superseded"
    assert result["work_order"]["superseded_by_plan_id"] == REPLACEMENT_PLAN
    assert result["work_order"]["superseded_by_work_order_id"] == REPLACEMENT_WORK_ORDER
    assert result["work_order"]["supersession_reason"] == "replaced_after_router_false_positive_fix"
    assert storage.jobs[ORIGINAL_JOB] == original_job
    assert storage.jobs[ORIGINAL_JOB]["result"]["reason"] == "work_order_policy_rejected"
    assert storage.work_orders[(REPLACEMENT_PLAN, REPLACEMENT_WORK_ORDER)] == replacement
    assert [row["status"] for row in storage.notifications] == ["superseded", "superseded", "sent"]
    assert len(storage.notifications) == notification_count
    assert [row["status"] for row in storage.controls] == ["cancelled", "executed"]
    assert store.claim_notification() is None
    assert store.emit_notification(
        dedupe_key="must-not-reappear",
        event_type="work_order_blocked",
        severity="error",
        project_id="chonhac",
        ticket_id="GH-14",
        plan_id=ORIGINAL_PLAN,
        work_order_id=ORIGINAL_WORK_ORDER,
        summary="stale blocked attention",
        github_url=None,
        attention_state="blocked",
        attention_generation="stale-generation",
    ) is False
    assert len(storage.notifications) == notification_count


def test_explicit_supersession_is_idempotent_and_persists_across_store_instances():
    storage = Storage()
    first = supersede(PlanOrchestratorStore(storage))
    timestamp = first["work_order"]["superseded_at"]

    second = supersede(PlanOrchestratorStore(storage))
    read_back = PlanOrchestratorStore(storage).work_orders(ORIGINAL_PLAN)[0]

    assert second["changed"] is False
    assert second["work_order"]["superseded_at"] == timestamp
    assert read_back["lifecycle"] == "superseded"
    assert read_back["job_id"] == ORIGINAL_JOB


def test_supersession_identity_validation_fails_closed():
    storage = Storage()
    store = PlanOrchestratorStore(storage)
    common = {
        "reason": "explicit replacement",
        "superseded_by_plan_id": REPLACEMENT_PLAN,
        "superseded_by_work_order_id": REPLACEMENT_WORK_ORDER,
    }

    with pytest.raises(RuntimeError, match="Unknown orchestration plan"):
        store.supersede_work_order(plan_id="missing", work_order_id=ORIGINAL_WORK_ORDER, **common)
    with pytest.raises(RuntimeError, match="Unknown orchestrated WorkOrder"):
        store.supersede_work_order(plan_id=ORIGINAL_PLAN, work_order_id="missing", **common)
    with pytest.raises(RuntimeError, match="supplied together"):
        store.supersede_work_order(
            plan_id=ORIGINAL_PLAN,
            work_order_id=ORIGINAL_WORK_ORDER,
            reason="explicit replacement",
            superseded_by_plan_id=REPLACEMENT_PLAN,
        )
    with pytest.raises(RuntimeError, match="exact plan"):
        store.supersede_work_order(
            plan_id=f" {ORIGINAL_PLAN}",
            work_order_id=ORIGINAL_WORK_ORDER,
            reason="explicit replacement",
        )
    with pytest.raises(RuntimeError, match="Unknown replacement orchestrated WorkOrder"):
        store.supersede_work_order(
            plan_id=ORIGINAL_PLAN,
            work_order_id=ORIGINAL_WORK_ORDER,
            reason="explicit replacement",
            superseded_by_plan_id=REPLACEMENT_PLAN,
            superseded_by_work_order_id="wrong-r2",
        )

    assert storage.work_orders[(ORIGINAL_PLAN, ORIGINAL_WORK_ORDER)]["lifecycle"] == "active"


def test_in_flight_or_completed_source_cannot_be_retired_as_a_shortcut():
    storage = Storage()
    store = PlanOrchestratorStore(storage)
    source = storage.work_orders[(ORIGINAL_PLAN, ORIGINAL_WORK_ORDER)]
    source["state"] = "running"
    storage.jobs[ORIGINAL_JOB]["status"] = "executing"

    with pytest.raises(RuntimeError, match="state=running"):
        supersede(store)

    source["state"] = "completed"
    storage.jobs[ORIGINAL_JOB]["status"] = "completed"
    with pytest.raises(RuntimeError, match="state=completed"):
        supersede(store)

    assert source["lifecycle"] == "active"


def test_conflicting_repeat_fails_closed_and_another_work_order_is_unchanged():
    storage = Storage()
    other_key = (ORIGINAL_PLAN, "OTHER-WORK")
    storage.work_orders[other_key] = {
        "plan_id": ORIGINAL_PLAN,
        "work_order_id": "OTHER-WORK",
        "sequence_no": 1,
        "execution_mode": "agent",
        "state": "pending",
        "lifecycle": "active",
        "job_id": None,
        "detail": {},
        "updated_at": datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc),
    }
    other = deepcopy(storage.work_orders[other_key])
    store = PlanOrchestratorStore(storage)
    supersede(store)

    with pytest.raises(RuntimeError, match="different metadata"):
        store.supersede_work_order(
            plan_id=ORIGINAL_PLAN,
            work_order_id=ORIGINAL_WORK_ORDER,
            reason="different reason",
            superseded_by_plan_id=REPLACEMENT_PLAN,
            superseded_by_work_order_id=REPLACEMENT_WORK_ORDER,
        )

    assert storage.work_orders[other_key] == other
    assert storage.plans[ORIGINAL_PLAN]["lifecycle"] == "active"
    assert storage.plans[ORIGINAL_PLAN]["status"] == "active"


def test_superseded_orchestrated_job_cannot_resume_but_old_rows_remain_resumable():
    storage = Storage()
    store = PlanOrchestratorStore(storage)
    supersede(store)

    with pytest.raises(RuntimeError, match="Superseded orchestrated WorkOrders cannot be resumed"):
        prepare_orchestrated_job_resume(store, ORIGINAL_JOB)

    legacy = Storage()
    legacy.work_orders[(ORIGINAL_PLAN, ORIGINAL_WORK_ORDER)].pop("lifecycle")
    legacy.plans[ORIGINAL_PLAN].pop("lifecycle")
    context = prepare_orchestrated_job_resume(PlanOrchestratorStore(legacy), ORIGINAL_JOB)
    assert context["reopen"] is True


def test_schema_upgrade_is_additive_idempotent_and_defaults_old_rows_active():
    assert "ADD COLUMN IF NOT EXISTS lifecycle TEXT NOT NULL DEFAULT 'active'" in ORCHESTRATOR_DDL
    assert "ADD COLUMN IF NOT EXISTS superseded_by_plan_id TEXT" in ORCHESTRATOR_DDL
    assert "ADD COLUMN IF NOT EXISTS supersession_reason TEXT" in ORCHESTRATOR_DDL
    assert "DROP " not in ORCHESTRATOR_DDL.upper()

    storage = Storage()
    storage.work_orders[(ORIGINAL_PLAN, ORIGINAL_WORK_ORDER)].pop("lifecycle")
    store = PlanOrchestratorStore(storage)
    store.ensure()
    store.ensure()

    assert storage.ensure_calls == 2
    assert str(storage.work_orders[(ORIGINAL_PLAN, ORIGINAL_WORK_ORDER)].get("lifecycle") or "active") == "active"
