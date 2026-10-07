from __future__ import annotations

import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.control_actions import ControlActionService
from app.engine import _apply_owner_budget_authorizations
from app.standalone_antiloop_epoch import EPOCH_KEY as STANDALONE_ANTI_LOOP_EPOCH_KEY


def _control_dedupe_key(
    *,
    action_type: str,
    plan_id: str,
    work_order_id: str,
    job_id: str | None,
    generation_fingerprint: str,
    payload: dict,
) -> str:
    source = json.dumps(
        {
            "action_type": action_type,
            "plan_id": plan_id,
            "work_order_id": work_order_id,
            "job_id": job_id,
            "generation_fingerprint": generation_fingerprint,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class FakeStorage:
    def __init__(self, jobs=None):
        self.jobs = deepcopy(jobs or {})
        self.lease = None

    def get(self, job_id):
        value = self.jobs.get(job_id)
        return deepcopy(value) if value is not None else None

    def update(self, job_id, **fields):
        self.jobs[job_id].update(deepcopy(fields))

    def project_lease(self, project_id):
        return deepcopy(self.lease)


class FakeEngine:
    def __init__(self):
        self.enqueued = []

    async def enqueue(self, job_id):
        self.enqueued.append(job_id)


class FakeStore:
    pass


def base_job(*, reason="execution_budget_exhausted", last_failure="model-call budget exhausted"):
    return {
        "id": "job-1",
        "status": "blocked",
        "updated_at": "2026-09-14T00:00:00+00:00",
        "route": {
            "strategy": {
                "budget": {
                    "max_model_calls": 10,
                    "max_tool_calls": 160,
                    "max_test_runs": 14,
                    "max_wall_time_minutes": 50,
                    "max_repair_iterations": 2,
                    "max_iterations": 8,
                }
            }
        },
        "progress": {
            "model_calls": 10,
            "tool_calls": 4,
            "test_runs": 2,
            "elapsed_minutes": 12.5,
            "repair_iterations": 1,
            "iteration": 3,
            "provider_failures": [],
        },
        "checkpoint": {
            "work_order": {
                "id": "WO-1",
                "budget": {"max_model_calls": 10},
            },
            "route_history": [],
        },
        "result": {
            "reason": reason,
            "last_failure": last_failure,
        },
    }


def row():
    return {
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "execution_mode": "agent",
        "state": "blocked",
        "job_id": "job-1",
        "updated_at": "2026-09-14T00:00:00+00:00",
    }


def service(job=None):
    storage = FakeStorage({"job-1": job or base_job()})
    engine = FakeEngine()
    controls = ControlActionService(storage, engine, FakeStore())
    return controls, storage


def action_types(advisory):
    return [item["action_type"] for item in advisory["action_specs"]]


def test_model_call_budget_block_is_actionable_without_resetting_usage():
    controls, _ = service()

    advisory = controls.blocked_advisory(row(), base_job())

    assert advisory["reason"] == "execution_budget_exhausted"
    assert "not a provider" in advisory["cause"].lower()
    model_metric = next(item for item in advisory["metrics"] if item.get("key") == "max_model_calls")
    assert model_metric["used"] == 10
    assert model_metric["limit"] == 10
    extension = advisory["action_specs"][0]
    assert extension["action_type"] == "budget_extend"
    assert extension["payload"] == {"dimension": "max_model_calls", "increment": 4}
    assert "keep_blocked" in action_types(advisory)


def test_provider_quota_block_gets_quota_reset_action_but_sanitizes_raw_failure():
    job = base_job(
        reason="provider_failure_without_fallback",
        last_failure="RAW provider error with supersecret-token and /private/path",
    )
    job["progress"]["provider_failures"] = [
        {"model": "codex_terra", "provider": "openai", "kind": "quota_exhausted"}
    ]
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)
    serialized = json.dumps(advisory, ensure_ascii=False)

    assert advisory["reason"] == "provider_failure_without_fallback"
    assert action_types(advisory)[:2] == ["provider_quota_reset", "reroute_provider"]
    assert "supersecret-token" not in serialized
    assert "/private/path" not in serialized
    assert "raw provider error" not in serialized.lower()


def test_unknown_block_reason_fails_closed_without_mutating_recovery_action():
    job = base_job(reason="unknown_future_block", last_failure="do something unsafe")
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert action_types(advisory) == ["details", "keep_blocked"]
    assert "resume_same" not in action_types(advisory)
    assert "force_complete" not in action_types(advisory)


def test_ci_infrastructure_block_offers_only_preserved_delivery_recovery():
    job = base_job(
        reason="github_ci_infrastructure_failure",
        last_failure="quality failed before runner assignment",
    )
    job["result"]["accepted_result"] = {
        "status": "accepted",
        "commit": "b" * 40,
        "delivery": {"pull_request": {"number": 18}},
    }
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert "before repository execution" in advisory["cause"]
    assert action_types(advisory) == [
        "retry_delivery",
        "recheck_ci",
        "details",
        "keep_blocked",
    ]
    assert "reroute_retry" not in action_types(advisory)


def test_legacy_misclassified_delivery_offers_delivery_recovery_not_reroute():
    job = base_job(
        reason="material_change_missing_without_model_fallback",
        last_failure="no new material diff after obsolete CI repair",
    )
    commit = "b" * 40
    source = "a" * 40
    branch = "ai/job-1"
    repository = "acme/demo"
    job.update({"branch": branch, "source_commit": source})
    job["route"]["strategy"].update({
        "evaluator": {"id": "reviewer", "provider": "provider"},
        "permissions": {"commit": True, "push_ai_branch": True, "create_pr": True},
        "review_policy": {"required": True, "independent": True, "independence_satisfied": True},
    })
    job["progress"].update({
        "tests_passed": True,
        "required_checks_passed": True,
        "unexpected_scope": False,
        "review_history": [{
            "verdict": "pass",
            "protocol_valid": True,
            "model": "reviewer",
            "provider": "provider",
        }],
    })
    job["checkpoint"].update({
        "last_review_report": {
            "verdict": "pass",
            "protocol_valid": True,
            "finding_count": 0,
        },
        "delivery": {
            "enabled": True,
            "state": "ci_failure",
            "branch": branch,
            "commit": commit,
            "publish": {
                "published": True,
                "branch": branch,
                "commit": commit,
                "source_commit": source,
                "repository": repository,
            },
            "pull_request": {
                "job_id": "job-1",
                "number": 289,
                "state": "open",
                "head": commit,
                "head_ref": branch,
                "base_ref": "main",
                "repository": repository,
            },
            "ci": {"state": "failure", "commit": commit},
        },
    })
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert advisory["phase"] == "delivery"
    assert action_types(advisory) == ["retry_delivery", "recheck_ci", "details", "keep_blocked"]
    assert "reroute_retry" not in action_types(advisory)


def test_ordinary_material_change_missing_still_offers_bounded_reroute():
    job = base_job(reason="material_change_missing_without_model_fallback")
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert action_types(advisory)[0] == "reroute_retry"


def test_legacy_misclassified_delivery_with_incomplete_evidence_has_no_retry_or_reroute():
    job = base_job(reason="material_change_missing_without_model_fallback")
    job["checkpoint"]["delivery"] = {"enabled": True, "state": "ci_failure"}
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert advisory["phase"] == "delivery"
    assert action_types(advisory) == ["details", "keep_blocked"]
    assert "reroute_retry" not in action_types(advisory)


def test_budget_extension_is_additive_audited_and_preserves_work_order_and_progress():
    controls, storage = service()
    before = storage.get("job-1")
    action = {
        "action_id": "opaque-action",
        "job_id": "job-1",
        "payload": {"dimension": "max_model_calls", "increment": 4},
    }

    result = controls._apply_budget_extension(action)
    after = storage.get("job-1")

    assert result == {
        "dimension": "max_model_calls",
        "previous_limit": 10,
        "new_limit": 14,
        "used": 10,
    }
    assert after["route"]["strategy"]["budget"]["max_model_calls"] == 14
    assert after["progress"] == before["progress"]
    assert after["checkpoint"]["work_order"] == before["checkpoint"]["work_order"]
    audit = after["checkpoint"]["budget_authorizations"][-1]
    assert audit["channel"] == "telegram"
    assert audit["previous_limit"] == 10
    assert audit["new_limit"] == 14
    assert audit["used"] == 10


def test_owner_budget_authorization_survives_a_fresh_route_without_mutating_work_order():
    route = {"strategy": {"budget": {"max_model_calls": 10, "max_tool_calls": 80}}}
    checkpoint = {
        "work_order": {"id": "WO-1", "budget": {"max_model_calls": 10}},
        "budget_authorizations": [
            {
                "action_id": "opaque-action",
                "channel": "telegram",
                "dimension": "max_model_calls",
                "previous_limit": 10,
                "new_limit": 14,
                "used": 10,
            }
        ],
    }

    updated = _apply_owner_budget_authorizations(route, checkpoint)

    assert route["strategy"]["budget"]["max_model_calls"] == 10
    assert updated["strategy"]["budget"]["max_model_calls"] == 14
    assert checkpoint["work_order"]["budget"]["max_model_calls"] == 10


def test_owner_budget_overlay_ignores_untrusted_or_non_monotonic_checkpoint_data():
    route = {"strategy": {"budget": {"max_model_calls": 10}}}
    checkpoint = {
        "budget_authorizations": [
            {
                "action_id": "bad-channel",
                "channel": "unknown",
                "dimension": "max_model_calls",
                "previous_limit": 10,
                "new_limit": 99,
            },
            {
                "action_id": "bad-direction",
                "channel": "telegram",
                "dimension": "max_model_calls",
                "previous_limit": 10,
                "new_limit": 9,
            },
        ]
    }

    updated = _apply_owner_budget_authorizations(route, checkpoint)

    assert updated["strategy"]["budget"]["max_model_calls"] == 10


def test_budget_extension_fails_closed_at_platform_hard_max():
    job = base_job()
    job["route"]["strategy"]["budget"]["max_model_calls"] = 100
    controls, _ = service(job)

    with pytest.raises(RuntimeError, match="hard maximum"):
        controls._apply_budget_extension(
            {
                "action_id": "opaque-action",
                "job_id": "job-1",
                "payload": {"dimension": "max_model_calls", "increment": 4},
            }
        )


def test_state_fingerprint_changes_when_block_generation_changes():
    controls, _ = service()
    plan = {"plan_id": "plan-1", "status": "blocked", "updated_at": "t1"}
    work_order = row()
    job = base_job()

    first = controls.state_fingerprint(plan, work_order, job)
    job["updated_at"] = "t2"
    second = controls.state_fingerprint(plan, work_order, job)

    assert first != second


def test_attention_generation_ignores_timestamps_but_changes_for_material_detail():
    controls, _ = service()
    plan = {"plan_id": "plan-1", "status": "waiting_merge", "updated_at": "p1"}
    work_order = {
        **row(),
        "state": "awaiting_merge",
        "pr_number": 18,
        "pr_url": "https://github.com/acme/demo/pull/18",
        "detail": {"delivery_state": "ci_success"},
    }
    job = base_job()
    job.update(status="completed", result={"delivery": {"state": "ci_success"}})
    advisory = controls.manual_merge_advisory(work_order["pr_url"])

    first = controls.attention_generation_fingerprint(plan, work_order, job, advisory)
    plan["updated_at"] = "p2"
    work_order["updated_at"] = "w2"
    job["updated_at"] = "j2"
    second = controls.attention_generation_fingerprint(plan, work_order, job, advisory)
    work_order["detail"] = {"delivery_state": "ci_success", "reason": "new_generation"}
    third = controls.attention_generation_fingerprint(plan, work_order, job, advisory)

    assert first == second
    assert third != second


class InMemoryControls(ControlActionService):
    def __init__(self):
        super().__init__(FakeStorage(), FakeEngine(), FakeStore())
        self.rows = {}
        self.created = 0

    def ensure(self):
        return None

    def create_action(self, **fields):
        key = (
            fields["action_type"],
            fields["plan_id"],
            fields["work_order_id"],
            fields["job_id"],
            fields["generation_fingerprint"],
            json.dumps(fields["payload"], sort_keys=True),
        )
        if key not in self.rows:
            self.created += 1
            self.rows[key] = {
                **deepcopy(fields),
                "action_id": f"action-{self.created}",
                "status": "pending",
            }
        return deepcopy(self.rows[key])

    def supersede_pending_actions(self, *, plan_id, work_order_id, except_generation=None):
        changed = 0
        for row in self.rows.values():
            if (
                row["status"] == "pending"
                and row["plan_id"] == plan_id
                and row["work_order_id"] == work_order_id
                and row["generation_fingerprint"] != except_generation
            ):
                row["status"] = "cancelled"
                changed += 1
        return changed


def test_stable_attention_reuses_control_action_generation_and_material_change_replaces_it():
    controls = InMemoryControls()
    plan = {"plan_id": "plan-1", "status": "waiting_merge", "updated_at": "p1"}
    work_order = {
        **row(),
        "state": "awaiting_merge",
        "pr_number": 18,
        "pr_url": "https://github.com/acme/demo/pull/18",
        "detail": {"delivery_state": "ci_success"},
    }
    job = base_job()
    job.update(status="completed", result={"delivery": {"state": "ci_success"}})
    advisory = controls.manual_merge_advisory(work_order["pr_url"])

    first = controls.create_actions(
        plan=plan,
        work_order=work_order,
        job=job,
        advisory=advisory,
    )
    plan["updated_at"] = "p2"
    work_order["updated_at"] = "w2"
    job["updated_at"] = "j2"
    second = controls.create_actions(
        plan=plan,
        work_order=work_order,
        job=job,
        advisory=advisory,
    )

    first_callback = next(item for item in first if item.get("action_id"))
    second_callback = next(item for item in second if item.get("action_id"))
    assert first_callback["action_id"] == second_callback["action_id"]
    assert controls.created == 1

    work_order["detail"] = {"delivery_state": "ci_success", "reason": "new_gate"}
    third = controls.create_actions(
        plan=plan,
        work_order=work_order,
        job=job,
        advisory=advisory,
    )
    third_callback = next(item for item in third if item.get("action_id"))

    assert third_callback["action_id"] != first_callback["action_id"]
    assert controls.created == 2
    assert sorted(item["status"] for item in controls.rows.values()) == [
        "cancelled",
        "pending",
    ]


class ActionResult:
    def __init__(self, row=None, *, rows=None, rowcount=0):
        self.row = deepcopy(row)
        self.rows = deepcopy(rows or [])
        self.rowcount = rowcount

    def fetchone(self):
        return deepcopy(self.row)

    def fetchall(self):
        return deepcopy(self.rows)


class ActionConnection:
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
        if "CREATE TABLE IF NOT EXISTS cp_control_actions" in normalized:
            return ActionResult()
        if normalized.startswith("SELECT * FROM cp_control_actions WHERE action_id="):
            return ActionResult(self.storage.actions.get(params[0]))
        if (
            normalized.startswith("SELECT * FROM cp_control_actions WHERE job_id=")
            and "status='pending'" in normalized
            and "expires_at>" in normalized
        ):
            job_id, timestamp = params
            rows = [
                deepcopy(action)
                for action in self.storage.actions.values()
                if action.get("job_id") == job_id
                and action.get("status") == "pending"
                and action.get("expires_at") > timestamp
            ]
            rows.sort(
                key=lambda action: (
                    action.get("created_at"),
                    action.get("action_id"),
                ),
                reverse=True,
            )
            return ActionResult(rows=rows)
        if normalized.startswith("INSERT INTO cp_control_actions"):
            (
                action_id, dedupe_key, action_type, plan_id, work_order_id, job_id,
                state_fingerprint, generation_fingerprint, payload, expires_at,
                created_at, updated_at,
            ) = params
            existing = next(
                (
                    row for row in self.storage.actions.values()
                    if row.get("dedupe_key") == dedupe_key
                ),
                None,
            )
            if existing is not None:
                if (
                    existing.get("status") == "failed"
                    and existing.get("state_fingerprint") == state_fingerprint
                    and existing.get("generation_fingerprint") == generation_fingerprint
                ):
                    existing.update(
                        status="pending",
                        result=None,
                        expires_at=expires_at,
                        updated_at=updated_at,
                    )
                return ActionResult(existing)
            row = {
                "action_id": action_id,
                "dedupe_key": dedupe_key,
                "action_type": action_type,
                "plan_id": plan_id,
                "work_order_id": work_order_id,
                "job_id": job_id,
                "state_fingerprint": state_fingerprint,
                "generation_fingerprint": generation_fingerprint,
                "payload": json.loads(payload),
                "status": "pending",
                "result": None,
                "expires_at": expires_at,
                "created_at": created_at,
                "updated_at": updated_at,
            }
            self.storage.actions[action_id] = row
            return ActionResult(row)
        if (
            normalized.startswith("UPDATE cp_control_actions SET status='cancelled'")
            and "WHERE status='pending' AND plan_id=" in normalized
            and "FROM cp_plan_work_orders" not in normalized
        ):
            updated_at, plan_id, work_order_id, *rest = params
            except_generation = rest[0] if rest else None
            changed = 0
            for action in self.storage.actions.values():
                if action.get("status") != "pending":
                    continue
                if action.get("plan_id") != plan_id or action.get("work_order_id") != work_order_id:
                    continue
                if (
                    except_generation is not None
                    and action.get("generation_fingerprint") == except_generation
                ):
                    continue
                action.update(status="cancelled", updated_at=updated_at)
                changed += 1
            return ActionResult(rowcount=changed)
        if "SET status='cancelled'" in normalized and "FROM cp_plan_work_orders" in normalized:
            changed = 0
            if (
                self.storage.store.work_order.get("lifecycle", "active") != "active"
                or self.storage.store.work_order["state"] not in {
                "awaiting_merge",
                "blocked",
                "waiting_human",
                }
            ):
                for action in self.storage.actions.values():
                    if action["status"] == "pending":
                        action["status"] = "cancelled"
                        changed += 1
            return ActionResult(rowcount=changed)
        if "SET status='executed', result=" in normalized:
            result, updated_at, action_id = params
            action = self.storage.actions[action_id]
            if action["status"] == "pending":
                action.update(status="executed", result=json.loads(result), updated_at=updated_at)
                return ActionResult(rowcount=1)
            return ActionResult(rowcount=0)
        if "SET status='stale'" in normalized:
            updated_at, action_id = params
            self.storage.actions[action_id].update(status="stale", updated_at=updated_at)
            return ActionResult(rowcount=1)
        raise AssertionError(f"Unexpected SQL: {normalized}")


class ActionStore:
    def __init__(self, state, *, lifecycle="active"):
        self.work_order = {
            "plan_id": "plan-1",
            "work_order_id": "WO-1",
            "execution_mode": "agent",
            "state": state,
            "lifecycle": lifecycle,
            "job_id": None,
            "detail": {},
            "updated_at": "w-current",
        }

    def ensure(self):
        return None

    def orchestration(self, plan_id):
        return {
            "plan_id": plan_id,
            "status": "completed" if self.work_order["state"] == "completed" else "blocked",
            "lifecycle": self.work_order.get("lifecycle", "active"),
            "updated_at": "p-current",
        }

    def work_orders(self, plan_id):
        return [deepcopy(self.work_order)]


class ActionStorage(FakeStorage):
    def __init__(self, actions, store):
        super().__init__()
        self.actions = {item["action_id"]: deepcopy(item) for item in actions}
        self.store = store

    def connect(self):
        return ActionConnection(self)


def control_action(action_id, action_type, *, status="pending", fingerprint="old"):
    timestamp = datetime.now(timezone.utc)
    return {
        "action_id": action_id,
        "action_type": action_type,
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "job_id": None,
        "state_fingerprint": fingerprint,
        "generation_fingerprint": "generation-1",
        "payload": {},
        "status": status,
        "result": None,
        "expires_at": timestamp + timedelta(hours=1),
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def test_completed_recheck_is_benign_after_pending_action_is_superseded(monkeypatch):
    monkeypatch.setenv("TELEGRAM_OWNER_USER_ID", "owner")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    store = ActionStore("completed")
    storage = ActionStorage(
        [
            control_action("recheck-old", "recheck_orchestration"),
            control_action("executed-history", "details", status="executed"),
        ],
        store,
    )
    controls = ControlActionService(storage, FakeEngine(), store)

    assert controls.supersede_obsolete_actions() == 1
    assert storage.actions["recheck-old"]["status"] == "cancelled"
    assert storage.actions["executed-history"]["status"] == "executed"

    result = asyncio.run(
        controls.execute(
            "recheck-old",
            telegram_user_id="owner",
            telegram_chat_id="chat",
        )
    )

    assert result["status"] == "already_resolved"
    assert "no action is required" in result["message"]
    assert storage.actions["recheck-old"]["status"] == "cancelled"


def test_superseded_historical_callback_is_benign_without_recovery(monkeypatch):
    monkeypatch.setenv("TELEGRAM_OWNER_USER_ID", "owner")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    store = ActionStore("blocked", lifecycle="superseded")
    store.work_order.update(
        superseded_by_plan_id="replacement-plan",
        superseded_by_work_order_id="WO-1-r2",
    )
    storage = ActionStorage(
        [control_action("resume-old", "reroute_retry", status="cancelled")],
        store,
    )
    controls = ControlActionService(storage, FakeEngine(), store)

    result = asyncio.run(
        controls.execute(
            "resume-old",
            telegram_user_id="owner",
            telegram_chat_id="chat",
        )
    )

    assert result == {
        "status": "superseded",
        "action_id": "resume-old",
        "action_type": "reroute_retry",
        "message": "This WorkOrder was explicitly replaced; no recovery action is required.",
        "superseded_by_plan_id": "replacement-plan",
        "superseded_by_work_order_id": "WO-1-r2",
    }
    assert storage.actions["resume-old"]["status"] == "cancelled"


def test_conflicting_old_mutation_action_remains_stale_and_fail_closed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_OWNER_USER_ID", "owner")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    store = ActionStore("blocked")
    storage = ActionStorage([], store)
    controls = ControlActionService(storage, FakeEngine(), store)
    old_plan = {"plan_id": "plan-1", "status": "waiting_human", "updated_at": "p-old"}
    old_work_order = {
        **store.work_order,
        "state": "waiting_human",
        "updated_at": "w-old",
    }
    fingerprint = controls.state_fingerprint(old_plan, old_work_order, None)
    storage.actions["operator-old"] = control_action(
        "operator-old",
        "operator_complete",
        fingerprint=fingerprint,
    )

    with pytest.raises(RuntimeError, match="stale because Runtime state changed"):
        asyncio.run(
            controls.execute(
                "operator-old",
                telegram_user_id="owner",
                telegram_chat_id="chat",
            )
        )

    assert storage.actions["operator-old"]["status"] == "stale"


def test_changed_file_scope_reassessment_advisory_exposes_safe_reason_and_recovery():
    job = base_job(reason="reassessment_stopped", last_failure="scope target exceeded")
    job["route"]["strategy"].update({
        "budget_mode": "adaptive",
        "budget": {
            **job["route"]["strategy"]["budget"],
            "max_changed_files": 8,
        },
    })
    job["progress"].update({
        "changed_files": 10,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    job["result"].update({
        "reassess": {
            "action": "stop",
            "reason": "Circuit breaker: abnormal execution signal without a valid escalation path",
            "signals": ["scope_expansion"],
        }
    })
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert advisory["action_specs"][0]["action_type"] == "pm_scope_reassess"
    assert "Circuit breaker" in advisory["cause"]
    assert any(
        item.get("label") == "Reassessment signals"
        and "scope_expansion" in item.get("value", "")
        for item in advisory["metrics"]
    )
    changed = next(item for item in advisory["metrics"] if item.get("key") == "max_changed_files")
    assert changed["used"] == 10
    assert changed["limit"] == 8


def test_changed_file_scope_reassessment_ignores_adaptive_headroom_telemetry():
    job = base_job(reason="reassessment_stopped", last_failure="scope target exceeded")
    job["route"]["strategy"].update({
        "budget_mode": "adaptive",
        "budget": {
            **job["route"]["strategy"]["budget"],
            "max_changed_files": 8,
        },
    })
    job["progress"].update({
        "changed_files": 9,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    job["result"].update({
        "reassess": {
            "action": "stop",
            "reason": "Circuit breaker: abnormal execution signal without a valid escalation path",
            "signals": [
                "budget_headroom_active:max_test_runs",
                "budget_headroom_active:max_wall_time_minutes",
                "scope_expansion",
            ],
        }
    })
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert advisory["action_specs"][0]["action_type"] == "pm_scope_reassess"


def test_changed_file_scope_reassessment_ignores_adaptive_estimate_telemetry():
    job = base_job(reason="reassessment_stopped", last_failure="scope target exceeded")
    job["route"]["strategy"].update({
        "budget_mode": "adaptive",
        "budget": {
            **job["route"]["strategy"]["budget"],
            "max_changed_files": 8,
        },
    })
    job["progress"].update({
        "changed_files": 9,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    job["result"].update({
        "reassess": {
            "action": "stop",
            "reason": "Circuit breaker",
            "signals": [
                "budget_estimate_exceeded:max_model_calls",
                "scope_expansion",
            ],
        }
    })
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert advisory["action_specs"][0]["action_type"] == "pm_scope_reassess"


def test_changed_file_scope_reassessment_keeps_emergency_budget_signal_blocking():
    job = base_job(reason="reassessment_stopped", last_failure="scope target exceeded")
    job["route"]["strategy"].update({
        "budget_mode": "adaptive",
        "budget": {
            **job["route"]["strategy"]["budget"],
            "max_changed_files": 8,
        },
    })
    job["progress"].update({
        "changed_files": 9,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    job["result"].update({
        "reassess": {
            "action": "stop",
            "reason": "Circuit breaker",
            "signals": [
                "budget_emergency_threshold_reached:max_wall_time_minutes",
                "scope_expansion",
            ],
        }
    })
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert "pm_scope_reassess" not in action_types(advisory)


def test_changed_file_scope_reassessment_recovery_is_not_offered_for_other_anomalies():
    job = base_job(reason="reassessment_stopped", last_failure="scope plus no progress")
    job["route"]["strategy"].update({
        "budget_mode": "adaptive",
        "budget": {
            **job["route"]["strategy"]["budget"],
            "max_changed_files": 8,
        },
    })
    job["progress"].update({
        "changed_files": 10,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    job["result"].update({
        "reassess": {
            "action": "stop",
            "reason": "Circuit breaker",
            "signals": ["scope_expansion", "no_progress"],
        }
    })
    controls, _ = service(job)

    advisory = controls.blocked_advisory(row(), job)

    assert "pm_scope_reassess" not in action_types(advisory)


def test_failed_control_action_is_rearmed_only_for_same_state_generation(monkeypatch):
    monkeypatch.setenv("TELEGRAM_OWNER_USER_ID", "owner")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    store = ActionStore("blocked")
    timestamp = datetime.now(timezone.utc)
    failed = {
        **control_action("scope-failed", "pm_scope_reassess", status="failed", fingerprint="same-state"),
        "dedupe_key": "placeholder",
        "generation_fingerprint": "same-generation",
        "result": {"status": "failed"},
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    storage = ActionStorage([failed], store)
    controls = ControlActionService(storage, FakeEngine(), store)

    plan = {"plan_id": "plan-1", "status": "blocked", "lifecycle": "active", "updated_at": "p-current"}
    work_order = {
        **store.work_order,
        "state": "blocked",
        "lifecycle": "active",
        "updated_at": "w-current",
    }
    job = base_job(reason="reassessment_stopped")
    job["id"] = "job-1"
    job["status"] = "blocked"

    advisory = {
        "reason": "reassessment_stopped",
        "action_specs": [
            {"action_type": "pm_scope_reassess", "label": "PM scope", "payload": {}}
        ],
    }
    generation = controls.attention_generation_fingerprint(
        plan,
        work_order,
        job,
        advisory,
    )
    state = controls.state_fingerprint(plan, work_order, job)

    failed["dedupe_key"] = _control_dedupe_key(
        action_type="pm_scope_reassess",
        plan_id="plan-1",
        work_order_id="WO-1",
        job_id="job-1",
        generation_fingerprint=generation,
        payload={},
    )
    failed["generation_fingerprint"] = generation
    failed["state_fingerprint"] = state
    storage.actions["scope-failed"] = failed

    rendered = controls.create_actions(
        plan=plan,
        work_order=work_order,
        job=job,
        advisory=advisory,
    )

    assert rendered[0]["action_id"] == "scope-failed"
    assert storage.actions["scope-failed"]["status"] == "pending"
    assert storage.actions["scope-failed"]["result"] is None


def test_failed_control_action_is_not_rearmed_after_state_drift():
    store = ActionStore("blocked")
    failed = {
        **control_action(
            "scope-failed",
            "pm_scope_reassess",
            status="failed",
            fingerprint="old-state",
        ),
        "generation_fingerprint": "same-generation",
        "result": {"status": "failed"},
    }
    failed["dedupe_key"] = _control_dedupe_key(
        action_type="pm_scope_reassess",
        plan_id="plan-1",
        work_order_id="WO-1",
        job_id="job-1",
        generation_fingerprint="same-generation",
        payload={},
    )
    storage = ActionStorage([failed], store)
    controls = ControlActionService(storage, FakeEngine(), store)

    row = controls.create_action(
        action_type="pm_scope_reassess",
        plan_id="plan-1",
        work_order_id="WO-1",
        job_id="job-1",
        state_fingerprint="new-state",
        generation_fingerprint="same-generation",
        payload={},
        ttl_hours=48,
    )

    assert row["status"] == "failed"
    assert row["state_fingerprint"] == "old-state"


def test_remote_control_executes_only_exact_routine_action_generation(monkeypatch):
    controls, _ = service()
    calls = []

    monkeypatch.setattr(
        controls,
        "get_action",
        lambda action_id: {
            "action_id": action_id,
            "action_type": "pm_scope_reassess",
            "job_id": "job-1",
            "generation_fingerprint": "generation-1",
        },
    )

    async def execute_authorized(action_id):
        calls.append(action_id)
        return {"status": "executed", "action_id": action_id}

    monkeypatch.setattr(controls, "_execute_authorized", execute_authorized)

    result = asyncio.run(
        controls.execute_remote(
            "action-12345678",
            expected_job_id="job-1",
            expected_generation="generation-1",
        )
    )

    assert result["status"] == "executed"
    assert calls == ["action-12345678"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("job_id", "job-other", "job identity mismatch"),
        ("generation_fingerprint", "generation-other", "generation mismatch"),
        ("action_type", "budget_extend", "cannot execute action_type"),
        ("action_type", "provider_quota_reset", "cannot execute action_type"),
        ("action_type", "reroute_provider", "cannot execute action_type"),
    ],
)
def test_remote_control_rejects_stale_or_nonroutine_actions(
    monkeypatch,
    field,
    value,
    message,
):
    controls, _ = service()
    action = {
        "action_id": "action-12345678",
        "action_type": "resume_same",
        "job_id": "job-1",
        "generation_fingerprint": "generation-1",
    }
    action[field] = value
    monkeypatch.setattr(controls, "get_action", lambda action_id: action)

    with pytest.raises(RuntimeError, match=message):
        asyncio.run(
            controls.execute_remote(
                "action-12345678",
                expected_job_id="job-1",
                expected_generation="generation-1",
            )
        )


def standalone_scope_job():
    job = base_job(
        reason="reassessment_stopped",
        last_failure="scope target exceeded",
    )
    job["id"] = "job-1"
    job["status"] = "blocked"
    job["updated_at"] = "2026-10-07T02:09:50+07:00"
    job["source_commit"] = "a" * 40
    job["branch"] = "ai/job-1"
    job["checkpoint"]["canonical_intake"] = {
        "policy_version": 1,
        "mode": "direct",
        "bounded_direct": True,
        "decomposition_required": False,
    }
    job["route"]["strategy"].update({
        "budget_mode": "adaptive",
        "budget": {
            **job["route"]["strategy"]["budget"],
            "max_changed_files": 8,
        },
    })
    job["progress"].update({
        "changed_files": 10,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    job["result"].update({
        "reassess": {
            "action": "stop",
            "reason": "Circuit breaker: abnormal execution signal without a valid escalation path",
            "signals": ["scope_expansion"],
        }
    })
    return job


def test_standalone_reassessment_exposes_only_runtime_offered_routine_action():
    job = standalone_scope_job()
    controls, _ = service(job)

    view = controls.standalone_remote_actions("job-1")

    assert view["reason"] == "reassessment_stopped"
    assert view["phase"] == "reassessment"
    assert view["actions"] == [
        {
            "action_type": "pm_scope_reassess",
            "label": "🧭 PM review file scope",
        }
    ]
    assert len(view["generation"]) == 64


def test_standalone_recovery_recomputes_generation_and_action_before_dispatch(
    monkeypatch,
):
    job = standalone_scope_job()
    controls, storage = service(job)
    view = controls.standalone_remote_actions("job-1")
    dispatched = []

    async def dispatch(action):
        dispatched.append(action)
        return {
            "status": "executed",
            "action_type": action["action_type"],
        }

    monkeypatch.setattr(controls, "_dispatch", dispatch)

    result = asyncio.run(
        controls.execute_standalone_remote(
            "job-1",
            expected_generation=view["generation"],
            action_type="pm_scope_reassess",
        )
    )
    assert result["status"] == "executed"
    assert dispatched[0]["action_type"] == "pm_scope_reassess"

    storage.jobs["job-1"]["updated_at"] = "2026-10-07T02:10:00+07:00"
    with pytest.raises(RuntimeError, match="generation mismatch"):
        asyncio.run(
            controls.execute_standalone_remote(
                "job-1",
                expected_generation=view["generation"],
                action_type="pm_scope_reassess",
            )
        )

    current = controls.standalone_remote_actions("job-1")
    with pytest.raises(RuntimeError, match="not currently offered"):
        asyncio.run(
            controls.execute_standalone_remote(
                "job-1",
                expected_generation=current["generation"],
                action_type="retry_delivery",
            )
        )


def test_standalone_remote_recovery_rejects_noncanonical_or_active_job():
    job = standalone_scope_job()
    job["checkpoint"].pop("canonical_intake")
    controls, _ = service(job)
    with pytest.raises(RuntimeError, match="canonical bounded-direct"):
        controls.standalone_remote_actions("job-1")

    job = standalone_scope_job()
    job["status"] = "executing"
    controls, _ = service(job)
    with pytest.raises(RuntimeError, match="blocked/interrupted"):
        controls.standalone_remote_actions("job-1")


def _current_orchestrated_control_fixture():
    store = ActionStore("blocked")
    store.work_order["job_id"] = "job-1"
    storage = ActionStorage([], store)
    job = base_job(reason="reassessment_stopped")
    job["id"] = "job-1"
    job["status"] = "blocked"
    job["updated_at"] = "j-current"
    storage.jobs["job-1"] = deepcopy(job)
    controls = ControlActionService(storage, FakeEngine(), store)
    plan = store.orchestration("plan-1")
    work_order = store.work_orders("plan-1")[0]
    state = controls.state_fingerprint(plan, work_order, job)
    return controls, storage, store, job, state


def test_remote_pending_actions_exposes_only_exact_current_routine_generation():
    controls, storage, _store, _job, state = (
        _current_orchestrated_control_fixture()
    )
    current = control_action(
        "scope-current",
        "pm_scope_reassess",
        fingerprint=state,
    )
    current.update(
        job_id="job-1",
        generation_fingerprint="generation-current",
    )
    nonroutine = control_action(
        "budget-current",
        "budget_extend",
        fingerprint=state,
    )
    nonroutine.update(
        job_id="job-1",
        generation_fingerprint="generation-current",
    )
    cancelled = control_action(
        "old-cancelled",
        "resume_same",
        status="cancelled",
        fingerprint=state,
    )
    cancelled.update(
        job_id="job-1",
        generation_fingerprint="generation-old",
    )
    storage.actions = {
        item["action_id"]: item
        for item in (current, nonroutine, cancelled)
    }

    result = controls.remote_pending_actions("job-1")

    assert result == {
        "job_id": "job-1",
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "generation": "generation-current",
        "actions": [
            {
                "control_action_id": "scope-current",
                "action_type": "pm_scope_reassess",
            }
        ],
    }


def test_remote_pending_actions_omits_stale_state_and_expired_actions():
    controls, storage, _store, _job, state = (
        _current_orchestrated_control_fixture()
    )
    stale = control_action(
        "stale-current",
        "resume_same",
        fingerprint="stale-state",
    )
    stale.update(
        job_id="job-1",
        generation_fingerprint="generation-current",
    )
    expired = control_action(
        "expired-current",
        "retry_delivery",
        fingerprint=state,
    )
    expired.update(
        job_id="job-1",
        generation_fingerprint="generation-current",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    storage.actions = {
        stale["action_id"]: stale,
        expired["action_id"]: expired,
    }

    result = controls.remote_pending_actions("job-1")

    assert result == {
        "job_id": "job-1",
        "generation": None,
        "plan_id": None,
        "work_order_id": None,
        "actions": [],
    }


def test_remote_pending_actions_refuses_multiple_current_generations():
    controls, storage, _store, _job, state = (
        _current_orchestrated_control_fixture()
    )
    first = control_action(
        "first-current",
        "resume_same",
        fingerprint=state,
    )
    first.update(
        job_id="job-1",
        generation_fingerprint="generation-a",
    )
    second = control_action(
        "second-current",
        "retry_delivery",
        fingerprint=state,
    )
    second.update(
        job_id="job-1",
        generation_fingerprint="generation-b",
    )
    storage.actions = {
        first["action_id"]: first,
        second["action_id"]: second,
    }

    with pytest.raises(RuntimeError, match="Multiple exact-current"):
        controls.remote_pending_actions("job-1")


def blocked_repair_job():
    job = base_job(reason="reassessment_stopped", last_failure="circuit breaker")
    job.update({
        "id": "job-1",
        "project_id": "chonhac",
        "status": "blocked",
        "source_commit": "a" * 40,
        "branch": "ai/job-1",
        "workspace": "/home/sonvh/chonhac",
    })
    job["checkpoint"].update({
        "canonical_intake": {
            "policy_version": 1,
            "mode": "direct",
            "bounded_direct": True,
            "decomposition_required": False,
        },
        "workspace_mode": "direct",
        "pending_decision": None,
    })
    job["progress"].update({
        "changed_files": 5,
        "unexpected_scope": False,
        "important_decision_flags": [],
        "required_checks_passed": False,
        "failure_fingerprints": [
            "old-a",
            "same",
            "same",
            "same",
        ],
        "progress_markers": [
            "old-a",
            "same",
            "same",
            "same",
        ],
        "repair_iterations": 8,
        "pm_reassessments": 0,
    })
    job["result"] = {
        "reason": "reassessment_stopped",
        "last_failure": "Circuit breaker",
        "reassess": {
            "action": "stop",
            "reason": "Circuit breaker: abnormal execution signal without a valid escalation path",
            "signals": [
                "repeated_failure:1d70a54f5249177b07c2c01d",
                "no_progress",
                "budget_headroom_active:max_model_calls",
                "budget_headroom_active:max_repair_iterations",
                "budget_estimate_exceeded:max_test_runs",
            ],
        },
        "diff": {
            "diff_hash": "a160822e5810bd2e19e8630022ef577a97e1b242886d0afe3b7f9bc61869c3a1",
            "changed_files": ["one.php", "two.php"],
        },
    }
    return job


def blocked_repair_service(job=None):
    job = job or blocked_repair_job()
    storage = FakeStorage({"job-1": job})
    storage.lease = {
        "project_id": "chonhac",
        "owner_job_id": "job-1",
        "generation": 3,
        "state": "active",
    }
    engine = FakeEngine()
    controls = ControlActionService(storage, engine, FakeStore())
    return controls, storage, engine


def test_remote_blocked_repair_reuses_exact_job_workspace_and_counters():
    controls, storage, engine = blocked_repair_service()
    before = storage.get("job-1")
    view = controls.standalone_remote_actions("job-1")

    result = asyncio.run(
        controls.request_standalone_blocked_repair(
            "job-1",
            expected_generation=view["generation"],
            finding=(
                "Inspect the preserved targeted_tests failure locally, repair only "
                "the existing five-file bounded diff, rerun deterministic tests, "
                "and do not expand scope or alter contract authority."
            ),
            references=["GH-77", "PCP diagnostic 6031574054"],
        )
    )

    assert result["id"] == "job-1"
    assert result["status"] == "queued"
    assert engine.enqueued == ["job-1"]

    after = storage.get("job-1")
    assert after["source_commit"] == before["source_commit"]
    assert after["branch"] == before["branch"]
    assert after["workspace"] == before["workspace"]
    assert after["route"] == before["route"]
    for key in (
        "model_calls",
        "tool_calls",
        "test_runs",
        "elapsed_minutes",
        "iteration",
    ):
        assert after["progress"][key] == before["progress"][key]

    assert after["progress"]["repair_iterations"] == 9
    assert after["progress"]["pm_reassessments"] == 1
    assert after["progress"]["required_checks_passed"] is False
    assert len(after["progress"]["failure_fingerprints"]) == (
        len(before["progress"]["failure_fingerprints"]) + 1
    )
    assert after["checkpoint"]["failure_context"]["kind"] == "semantic_repair"
    assert after["checkpoint"]["failure_context"]["source"] == "pm_reassessment"
    assert after["checkpoint"]["failure_context"]["diff_hash"] == (
        before["result"]["diff"]["diff_hash"]
    )
    assert (
        after["checkpoint"]["last_pm_reassessment"]["decision"]["action"]
        == "request_repair"
    )
    assert after["result"]["reason"] == "remote_pm_repair_requested"
    assert (
        after["result"]["previous_block"]["reason"]
        == "reassessment_stopped"
    )
    assert storage.lease["owner_job_id"] == "job-1"
    assert storage.lease["state"] == "active"


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda job: job["checkpoint"].update(
                pending_decision={"key": "human:1"}
            ),
            "pending Human decision",
        ),
        (
            lambda job: job["progress"].update(
                important_decision_flags=["security_boundary_change"]
            ),
            "protected decision flags",
        ),
        (
            lambda job: job["progress"].update(unexpected_scope=True),
            "unexpected scope",
        ),
        (
            lambda job: job["result"]["reassess"]["signals"].append(
                "scope_expansion"
            ),
            "unsupported reassessment signal",
        ),
        (
            lambda job: job["result"]["diff"].update(diff_hash=""),
            "preserved diff hash",
        ),
        (
            lambda job: job["checkpoint"]["canonical_intake"].update(
                bounded_direct=False
            ),
            "canonical bounded-direct",
        ),
        (
            lambda job: job.update(status="executing"),
            "exact blocked job state",
        ),
    ],
)
def test_remote_blocked_repair_rejects_stale_or_protected_boundaries(
    mutate,
    match,
):
    job = blocked_repair_job()
    mutate(job)
    controls, storage, engine = blocked_repair_service(job)

    advisory = controls.blocked_advisory({}, job)
    generation = controls.standalone_attention_generation_fingerprint(
        job,
        advisory,
    )

    with pytest.raises(RuntimeError, match=match):
        asyncio.run(
            controls.request_standalone_blocked_repair(
                "job-1",
                expected_generation=generation,
                finding="Repair the preserved targeted test failure only.",
            )
        )

    assert engine.enqueued == []
    assert storage.get("job-1")["status"] == job["status"]


def test_remote_blocked_repair_rejects_stale_generation_and_wrong_lease():
    controls, storage, engine = blocked_repair_service()
    view = controls.standalone_remote_actions("job-1")

    with pytest.raises(RuntimeError, match="generation mismatch"):
        asyncio.run(
            controls.request_standalone_blocked_repair(
                "job-1",
                expected_generation="f" * 64,
                finding="Repair exact targeted test failure.",
            )
        )

    storage.lease["owner_job_id"] = "different-job"
    with pytest.raises(RuntimeError, match="same-job project lease"):
        asyncio.run(
            controls.request_standalone_blocked_repair(
                "job-1",
                expected_generation=view["generation"],
                finding="Repair exact targeted test failure.",
            )
        )
    assert engine.enqueued == []


def test_remote_blocked_repair_requires_repeat_and_no_progress_signals():
    for missing_prefix in ("repeated_failure:", "no_progress"):
        job = blocked_repair_job()
        job["result"]["reassess"]["signals"] = [
            signal
            for signal in job["result"]["reassess"]["signals"]
            if not (
                signal == missing_prefix
                or signal.startswith(missing_prefix)
            )
        ]
        controls, _storage, engine = blocked_repair_service(job)
        view = controls.standalone_remote_actions("job-1")
        expected = (
            "repeated_failure signal"
            if missing_prefix == "repeated_failure:"
            else "no_progress signal"
        )
        with pytest.raises(RuntimeError, match=expected):
            asyncio.run(
                controls.request_standalone_blocked_repair(
                    "job-1",
                    expected_generation=view["generation"],
                    finding="Repair exact targeted test failure.",
                )
            )
        assert engine.enqueued == []


def adaptive_emergency_repair_job():
    job = blocked_repair_job()
    job["route"]["strategy"]["budget_mode"] = "adaptive"
    job["progress"].update({
        "repair_iterations": 12,
        "pm_reassessments": 1,
    })
    prior_diff = job["result"]["diff"]["diff_hash"]
    current_diff = "ded7f2ca08baf2bba412b46c096dd44bcc76cc18eddf381b462f11f4ab5b269c"
    job["checkpoint"]["failure_context"] = {
        "version": 1,
        "kind": "semantic_repair",
        "source": "pm_reassessment",
        "message": "PCP_PM_REASSESSMENT: repair prior diff",
        "diff_hash": prior_diff,
    }
    job["checkpoint"]["deterministic_verification_failure_streak"] = {
        "count": 1,
        "limit": 2,
        "verification_attempt": 11,
        "signature": "0753dd6a298967d35d97a7f6",
        "diff_hash": current_diff,
        "failing_phases": ["targeted_tests"],
    }
    job["result"]["diff"]["diff_hash"] = current_diff
    job["result"]["reassess"]["signals"] = [
        "repeated_failure:1d70a54f5249177b07c2c01d",
        "no_progress",
        "budget_headroom_active:max_test_runs",
        "budget_estimate_exceeded:max_tool_calls",
        "budget_headroom_active:max_model_calls",
        "budget_emergency_threshold_reached:max_repair_iterations",
    ]
    return job


def test_remote_blocked_repair_allows_progress_proven_adaptive_emergency_telemetry():
    job = adaptive_emergency_repair_job()
    controls, storage, engine = blocked_repair_service(job)
    before = storage.get("job-1")
    advisory = controls.blocked_advisory({}, before)
    generation = controls.standalone_attention_generation_fingerprint(
        before,
        advisory,
    )

    result = asyncio.run(
        controls.request_standalone_blocked_repair(
            "job-1",
            expected_generation=generation,
            finding=(
                "Run current targeted_tests first and identify the exact failing "
                "assertion before editing. Repair only the current five-file diff."
            ),
            references=["GH-77", "PCP diagnostic 6033146203"],
        )
    )

    assert result["status"] == "queued"
    assert engine.enqueued == ["job-1"]
    after = storage.get("job-1")
    assert after["route"] == before["route"]
    assert after["source_commit"] == before["source_commit"]
    assert after["branch"] == before["branch"]
    assert after["workspace"] == before["workspace"]
    assert after["progress"]["repair_iterations"] == 13
    for key in (
        "model_calls",
        "tool_calls",
        "test_runs",
        "elapsed_minutes",
        "iteration",
    ):
        assert after["progress"][key] == before["progress"][key]
    assert (
        after["result"]["previous_block"]["diff_hash"]
        == before["result"]["diff"]["diff_hash"]
    )
    marker = after["checkpoint"]["remote_adaptive_emergency_repair"]
    assert marker["blocker_generation"] == generation
    assert marker["prior_diff_hash"] == (
        before["checkpoint"]["failure_context"]["diff_hash"]
    )
    assert marker["current_diff_hash"] == before["result"]["diff"]["diff_hash"]
    assert marker["dimensions"] == ["max_repair_iterations"]
    assert marker["recorded_at"]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda job: job["route"]["strategy"].update(
                budget_mode="legacy_hard"
            ),
            "requires adaptive route",
        ),
        (
            lambda job: job["result"]["reassess"]["signals"].append(
                "budget_emergency_threshold_reached:max_changed_files"
            ),
            "unsupported emergency telemetry dimension",
        ),
        (
            lambda job: job["checkpoint"].update(
                remote_adaptive_emergency_repair={
                    "blocker_generation": "old-generation",
                    "prior_diff_hash": "a" * 64,
                    "current_diff_hash": "b" * 64,
                    "dimensions": ["max_repair_iterations"],
                    "recorded_at": "2026-10-07T00:00:00+00:00",
                }
            ),
            "emergency repair window was already used",
        ),
        (
            lambda job: job["checkpoint"]["failure_context"].update(
                source="provider"
            ),
            "prior PM repair context",
        ),
        (
            lambda job: job["checkpoint"]["failure_context"].update(
                diff_hash=job["result"]["diff"]["diff_hash"]
            ),
            "material diff progress",
        ),
        (
            lambda job: job["checkpoint"][
                "deterministic_verification_failure_streak"
            ].update(count=2),
            "one fresh current-diff failure",
        ),
        (
            lambda job: job["checkpoint"][
                "deterministic_verification_failure_streak"
            ].update(diff_hash="f" * 64),
            "one fresh current-diff failure",
        ),
    ],
)
def test_remote_blocked_repair_rejects_unproven_adaptive_emergency_telemetry(
    mutate,
    match,
):
    job = adaptive_emergency_repair_job()
    mutate(job)
    controls, storage, engine = blocked_repair_service(job)
    advisory = controls.blocked_advisory({}, job)
    generation = controls.standalone_attention_generation_fingerprint(
        job,
        advisory,
    )

    with pytest.raises(RuntimeError, match=match):
        asyncio.run(
            controls.request_standalone_blocked_repair(
                "job-1",
                expected_generation=generation,
                finding="Repair only the new targeted test failure.",
            )
        )

    assert engine.enqueued == []
    assert storage.get("job-1")["status"] == "blocked"



def reblocked_after_emergency_repair(job, storage):
    reblocked = storage.get("job-1")
    reblocked["status"] = "blocked"
    reblocked["result"] = deepcopy(job["result"])
    reblocked["result"]["diff"]["diff_hash"] = "e" * 64
    reblocked["result"]["reassess"]["signals"] = list(
        job["result"]["reassess"]["signals"]
    ) + ["budget_emergency_threshold_reached:max_test_runs"]
    reblocked["progress"]["repair_iterations"] = 16
    reblocked["progress"]["test_runs"] = 42
    reblocked["checkpoint"]["failure_context"] = {
        "version": 1,
        "kind": "semantic_repair",
        "source": "pm_reassessment",
        "message": "second repair context",
        "diff_hash": job["result"]["diff"]["diff_hash"],
    }
    reblocked["checkpoint"]["deterministic_verification_failure_streak"] = {
        "count": 1,
        "limit": 2,
        "verification_attempt": 14,
        "signature": "fresh-signature",
        "diff_hash": "e" * 64,
        "failing_phases": ["targeted_tests"],
    }
    storage.jobs["job-1"] = deepcopy(reblocked)
    return reblocked


def test_pm_antiloop_all_current_authorizes_one_more_same_job_window():
    job = adaptive_emergency_repair_job()
    controls, storage, engine = blocked_repair_service(job)
    first = controls.standalone_remote_actions("job-1")
    asyncio.run(
        controls.request_standalone_blocked_repair(
            "job-1",
            expected_generation=first["generation"],
            finding="Use the normal one-time adaptive emergency repair turn.",
        )
    )

    reblocked = reblocked_after_emergency_repair(job, storage)
    advisory = controls.blocked_advisory({}, reblocked)
    generation = controls.standalone_attention_generation_fingerprint(
        reblocked,
        advisory,
    )
    before = storage.get("job-1")

    result = asyncio.run(
        controls.request_standalone_blocked_repair(
            "job-1",
            expected_generation=generation,
            finding="PM reviewed the blocker; continue one bounded same-job repair.",
            references=["GH-77", "PCP #547"],
            anti_loop_bypass=["all_current"],
            authorization_reference={
                "channel": "github_pm_control",
                "comment_id": 999,
                "issue_number": 77,
            },
        )
    )

    assert result["status"] == "queued"
    assert engine.enqueued == ["job-1", "job-1"]
    after = storage.get("job-1")
    assert after["source_commit"] == before["source_commit"]
    assert after["branch"] == before["branch"]
    assert after["workspace"] == before["workspace"]
    assert after["progress"]["test_runs"] == before["progress"]["test_runs"]
    assert after["progress"]["model_calls"] == before["progress"]["model_calls"]
    assert after["progress"]["tool_calls"] == before["progress"]["tool_calls"]
    assert after["progress"]["repair_iterations"] == 17

    record = after["checkpoint"]["last_pm_antiloop_bypass"]
    assert record["blocker_generation"] == generation
    assert record["requested"] == ["all_current"]
    assert record["selectors"] == [
        "adaptive_emergency_repair_window",
        "max_repair_iterations",
        "max_test_runs",
        "no_progress",
        "repeated_failure",
    ]
    assert record["counters"]["test_runs"] == 42
    assert record["counters"]["repair_iterations"] == 16
    assert record["authorization_reference"] == {
        "channel": "github_pm_control",
        "comment_id": 999,
        "issue_number": 77,
    }
    assert len(after["checkpoint"]["pm_antiloop_bypass_history"]) == 1
    assert after["result"]["repair"]["anti_loop_bypass"] == record["selectors"]

    epoch = after["checkpoint"][STANDALONE_ANTI_LOOP_EPOCH_KEY]
    assert epoch["blocker_generation"] == generation
    assert epoch["selectors"] == record["selectors"]
    assert epoch["failure_fingerprint_start"] == len(
        after["progress"]["failure_fingerprints"]
    )
    assert epoch["progress_marker_start"] == len(
        after["progress"]["progress_markers"]
    )
    assert epoch["latest_verification_signature"] == "fresh-signature"
    assert epoch["baseline_counters"]["repair_iterations"] == 17


def test_pm_antiloop_partial_bypass_must_cover_every_required_current_gate():
    job = adaptive_emergency_repair_job()
    controls, storage, engine = blocked_repair_service(job)
    first = controls.standalone_remote_actions("job-1")
    asyncio.run(
        controls.request_standalone_blocked_repair(
            "job-1",
            expected_generation=first["generation"],
            finding="Use the normal emergency window.",
        )
    )
    reblocked = reblocked_after_emergency_repair(job, storage)
    advisory = controls.blocked_advisory({}, reblocked)
    generation = controls.standalone_attention_generation_fingerprint(
        reblocked,
        advisory,
    )

    with pytest.raises(RuntimeError, match="missing required current gate"):
        asyncio.run(
            controls.request_standalone_blocked_repair(
                "job-1",
                expected_generation=generation,
                finding="Authorize only part of the current anti-loop blocker.",
                anti_loop_bypass=[
                    "adaptive_emergency_repair_window",
                    "max_test_runs",
                ],
            )
        )

    assert engine.enqueued == ["job-1"]
    assert storage.get("job-1")["status"] == "blocked"


def test_pm_antiloop_bypass_cannot_cross_protected_boundary():
    protected = adaptive_emergency_repair_job()
    protected["progress"]["unexpected_scope"] = True
    controls, _storage, engine = blocked_repair_service(protected)
    advisory = controls.blocked_advisory({}, protected)
    generation = controls.standalone_attention_generation_fingerprint(
        protected,
        advisory,
    )
    with pytest.raises(RuntimeError, match="unexpected scope"):
        asyncio.run(
            controls.request_standalone_blocked_repair(
                "job-1",
                expected_generation=generation,
                finding="Attempt bypass.",
                anti_loop_bypass=["all_current"],
            )
        )
    assert engine.enqueued == []


def test_pm_antiloop_adaptive_counter_at_legacy_hard_max_is_bypassable():
    job = adaptive_emergency_repair_job()
    job["checkpoint"]["remote_adaptive_emergency_repair"] = {
        "blocker_generation": "prior",
        "prior_diff_hash": "a" * 64,
        "current_diff_hash": job["result"]["diff"]["diff_hash"],
        "dimensions": ["max_repair_iterations"],
        "recorded_at": "2026-10-07T00:00:00+00:00",
    }
    job["progress"]["repair_iterations"] = 20
    controls, storage, engine = blocked_repair_service(job)
    advisory = controls.blocked_advisory({}, job)
    generation = controls.standalone_attention_generation_fingerprint(
        job,
        advisory,
    )

    result = asyncio.run(
        controls.request_standalone_blocked_repair(
            "job-1",
            expected_generation=generation,
            finding="PM authorizes one more adaptive anti-loop repair window.",
            anti_loop_bypass=["all_current"],
        )
    )

    assert result["status"] == "queued"
    assert engine.enqueued == ["job-1"]
    after = storage.get("job-1")
    assert after["progress"]["repair_iterations"] == 21
    assert after["checkpoint"]["last_pm_antiloop_bypass"]["selectors"] == [
        "adaptive_emergency_repair_window",
        "max_repair_iterations",
        "no_progress",
        "repeated_failure",
    ]


def test_remote_blocked_repair_emergency_window_is_consumed_once():
    job = adaptive_emergency_repair_job()
    controls, storage, engine = blocked_repair_service(job)
    advisory = controls.blocked_advisory({}, job)
    generation = controls.standalone_attention_generation_fingerprint(
        job,
        advisory,
    )

    asyncio.run(
        controls.request_standalone_blocked_repair(
            "job-1",
            expected_generation=generation,
            finding="Use the one allowed adaptive emergency repair turn.",
        )
    )
    assert engine.enqueued == ["job-1"]

    reblocked = storage.get("job-1")
    reblocked["status"] = "blocked"
    reblocked["result"] = deepcopy(job["result"])
    reblocked["result"]["diff"]["diff_hash"] = "e" * 64
    reblocked["result"]["reassess"]["signals"] = list(
        job["result"]["reassess"]["signals"]
    )
    reblocked["checkpoint"]["failure_context"] = {
        "version": 1,
        "kind": "semantic_repair",
        "source": "pm_reassessment",
        "message": "second repair context",
        "diff_hash": job["result"]["diff"]["diff_hash"],
    }
    reblocked["checkpoint"]["deterministic_verification_failure_streak"] = {
        "count": 1,
        "limit": 2,
        "verification_attempt": 12,
        "signature": "fresh-signature",
        "diff_hash": "e" * 64,
        "failing_phases": ["targeted_tests"],
    }
    storage.jobs["job-1"] = deepcopy(reblocked)

    advisory = controls.blocked_advisory({}, reblocked)
    second_generation = controls.standalone_attention_generation_fingerprint(
        reblocked,
        advisory,
    )
    with pytest.raises(RuntimeError, match="emergency repair window was already used"):
        asyncio.run(
            controls.request_standalone_blocked_repair(
                "job-1",
                expected_generation=second_generation,
                finding="This second emergency repair must not run.",
            )
        )
    assert engine.enqueued == ["job-1"]
