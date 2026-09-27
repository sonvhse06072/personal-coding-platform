from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.control_actions import ControlActionService
from app.engine import _apply_owner_budget_authorizations


class FakeStorage:
    def __init__(self, jobs=None):
        self.jobs = deepcopy(jobs or {})

    def get(self, job_id):
        value = self.jobs.get(job_id)
        return deepcopy(value) if value is not None else None

    def update(self, job_id, **fields):
        self.jobs[job_id].update(deepcopy(fields))


class FakeEngine:
    pass


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
    return ControlActionService(storage, FakeEngine(), FakeStore()), storage


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
    def __init__(self, row=None, *, rowcount=0):
        self.row = deepcopy(row)
        self.rowcount = rowcount

    def fetchone(self):
        return deepcopy(self.row)


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
