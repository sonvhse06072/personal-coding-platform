import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.dashboard import (
    _job_snapshot,
    _require_session,
    _session_value,
    _workflow_progress,
    build_dashboard_snapshot,
)
from app.dashboard_ui import DASHBOARD_HTML


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)


def _job():
    return {
        "id": "job-1",
        "project_id": "chonhac",
        "status": "executing",
        "branch": "coding/job-1",
        "source_commit": "abc123",
        "created_at": NOW,
        "updated_at": NOW,
        "task": {"description": "SUPER SECRET RAW TASK"},
        "route": {
            "complexity_score": 72,
            "strategy": {
                "profile": "complex",
                "analysis_depth": 2,
                "planner": {"id": "codex_terra", "provider": "openai", "adapter": "codex_cli", "model": "gpt-5.6-terra", "reasoning_effort": "medium"},
                "executor": {"id": "codex_terra", "provider": "openai", "adapter": "codex_cli", "model": "gpt-5.6-terra", "reasoning_effort": "medium"},
                "evaluator": {"id": "antigravity_free", "provider": "google_antigravity", "adapter": "antigravity_host", "model": "auto", "reasoning_effort": None},
                "budget": {
                    "max_input_tokens": 2_000_000,
                    "max_output_tokens": 300_000,
                    "max_model_calls": 10,
                    "max_tool_calls": 160,
                    "max_test_runs": 14,
                    "max_wall_time_minutes": 50,
                    "max_changed_files": 14,
                    "max_iterations": 8,
                    "max_repair_iterations": 2,
                    "hard_cost_usd": 5.0,
                },
            },
        },
        "checkpoint": {
            "executor_choice": {"id": "codex_terra", "provider": "openai", "adapter": "codex_cli", "model": "gpt-5.6-terra", "reasoning_effort": "high"},
            "private_secret": "DO NOT LEAK",
        },
        "progress": {
            "input_tokens": 668_037,
            "output_tokens": 56_960,
            "model_calls": 2,
            "tool_calls": 5,
            "test_runs": 2,
            "iteration": 1,
            "repair_iterations": 0,
            "escalations": 1,
            "provider_failovers": 0,
            "model_failovers": 0,
            "elapsed_minutes": 12.5,
            "changed_files": 4,
            "tests_passed": True,
            "required_checks_passed": False,
            "agent_succeeded": True,
            "agent_attempts": [{
                "reasoning_effort": "high",
                "output_excerpt": "PRIVATE AGENT OUTPUT",
                "stderr_excerpt": "PRIVATE STDERR",
                "usage": {
                    "input_tokens": 668_037,
                    "gross_input_tokens": 7_568_037,
                    "cached_input_tokens": 6_900_000,
                    "output_tokens": 56_960,
                },
            }],
        },
    }


def test_job_snapshot_exposes_safe_runtime_telemetry_only():
    snapshot = _job_snapshot(_job())
    assert snapshot["profile"] == "complex"
    assert snapshot["analysis_depth"] == 2
    assert snapshot["workspace_mode"] == "isolated_clone"
    assert snapshot["models"]["current"]["id"] == "codex_terra"
    assert snapshot["models"]["current"]["reasoning_effort"] == "high"
    assert snapshot["tokens"]["input_budget_tokens"] == 668_037
    assert snapshot["tokens"]["last_attempt_gross_input_tokens"] == 7_568_037
    assert snapshot["tokens"]["last_attempt_cached_input_tokens"] == 6_900_000
    assert snapshot["workflow_progress"] == {
        "percent": 72,
        "label": "Execution · prior tests passed",
        "estimated": True,
        "paused": False,
    }
    assert snapshot["remaining"] == {
        "input_tokens": 1_331_963,
        "output_tokens": 243_040,
        "model_calls": 8,
        "tool_calls": 155,
        "test_runs": 12,
        "wall_time_minutes": 37.5,
        "changed_files": 10,
        "iterations": 7,
        "repair_iterations": 2,
    }
    encoded = json.dumps(snapshot)
    assert "SUPER SECRET RAW TASK" not in encoded
    assert "DO NOT LEAK" not in encoded
    assert "PRIVATE AGENT OUTPUT" not in encoded
    assert "PRIVATE STDERR" not in encoded


@pytest.mark.parametrize(
    ("status", "progress", "expected"),
    [
        ("queued", {}, (5, "Queued", False)),
        ("routing", {}, (10, "Routing", False)),
        ("planning", {}, (20, "Planning", False)),
        ("executing", {"agent_succeeded": True}, (55, "Execution · prior implementation produced", False)),
        ("verifying", {"tests_passed": True}, (72, "Verification · prior tests passed", False)),
        ("evaluating", {"tests_passed": True}, (85, "Independent review", False)),
        ("delivering", {"required_checks_passed": True}, (95, "Delivery", False)),
        ("completed", {}, (100, "Completed", False)),
        ("blocked", {"tests_passed": True}, (72, "Paused · tests passed", True)),
        ("waiting_human", {"required_checks_passed": True}, (88, "Paused · required checks passed", True)),
        ("interrupted", {"iteration": 1}, (45, "Paused · execution started", True)),
    ],
)
def test_workflow_progress_is_stage_and_milestone_based(status, progress, expected):
    result = _workflow_progress(status, progress)
    percent, label, paused = expected
    assert result == {
        "percent": percent,
        "label": label,
        "estimated": True,
        "paused": paused,
    }


def test_workflow_progress_does_not_use_resource_consumption_as_completion():
    result = _workflow_progress(
        "executing",
        {
            "model_calls": 0,
            "tool_calls": 999,
            "test_runs": 999,
            "elapsed_minutes": 999.0,
            "input_tokens": 9_999_999,
            "output_tokens": 9_999_999,
        },
    )
    assert result["percent"] == 45
    assert result["label"] == "Execution"


def test_dashboard_session_is_separate_and_fail_closed(monkeypatch):
    monkeypatch.delenv("DASHBOARD_READ_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        _require_session(None)
    assert exc.value.status_code == 503

    monkeypatch.setenv("DASHBOARD_READ_TOKEN", "read-only-test-token")
    with pytest.raises(HTTPException) as exc:
        _require_session("wrong")
    assert exc.value.status_code == 401
    _require_session(_session_value("read-only-test-token"))


class _Result:
    def __init__(self, *, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class _Connection:
    def execute(self, query, params=None):
        if "COUNT(*)" in query:
            return _Result(row={"count": 1})
        if "FROM cp_plan_orchestrations" in query:
            return _Result(rows=[{
                "plan_id": "pm-gh-1",
                "project_id": "chonhac",
                "status": "executing",
                "ticket_id": "GH-5",
                "ticket_title": "DEC-025C",
                "github_url": "https://example.invalid/issue/5",
                "baseline_revision": "mvp-v1",
                "baseline_source_commit": "abc123",
                "created_at": NOW,
                "updated_at": NOW,
                "ticket": {"secret": "NOT FOR DASHBOARD"},
                "plan": {"private": "NOT FOR DASHBOARD"},
                "staffing": {"private": "NOT FOR DASHBOARD"},
            }])
        if "FROM cp_notification_outbox" in query:
            assert "ORDER BY id DESC LIMIT 3" in query
            return _Result(rows=[
                {
                    "id": 3,
                    "event_type": "work_order_blocked",
                    "severity": "error",
                    "project_id": "chonhac",
                    "ticket_id": "GH-5",
                    "plan_id": "pm-gh-1",
                    "work_order_id": "C1",
                    "summary": "Newest alert",
                    "github_url": None,
                    "status": "pending",
                    "attempts": 0,
                    "created_at": NOW,
                    "sent_at": None,
                },
                {
                    "id": 2,
                    "event_type": "provider_quota_exhausted",
                    "severity": "warning",
                    "project_id": "chonhac",
                    "ticket_id": "GH-5",
                    "plan_id": "pm-gh-1",
                    "work_order_id": "C1",
                    "summary": "Second alert",
                    "github_url": None,
                    "status": "sent",
                    "attempts": 1,
                    "created_at": NOW,
                    "sent_at": NOW,
                },
                {
                    "id": 1,
                    "event_type": "manual_merge_required",
                    "severity": "warning",
                    "project_id": "chonhac",
                    "ticket_id": "GH-5",
                    "plan_id": "pm-gh-1",
                    "work_order_id": "C1",
                    "summary": "Third alert",
                    "github_url": "https://example.invalid/pr/1",
                    "status": "sent",
                    "attempts": 1,
                    "created_at": NOW,
                    "sent_at": NOW,
                },
            ])
        raise AssertionError(query)


class _Storage:
    @contextmanager
    def connect(self):
        yield _Connection()

    def get(self, job_id):
        return _job() if job_id == "job-1" else None

    def list(self, limit=50):
        assert limit == 500
        return [_job()]

    def recent_events(self, job_ids, per_job_limit=40):
        assert job_ids == ["job-1"]
        assert per_job_limit == 40
        return [
            {
                "id": 7,
                "job_id": "job-1",
                "event_type": "executor_started",
                "phase": "MALICIOUS PHASE",
                "level": "MALICIOUS LEVEL",
                "message": "PRIVATE AGENT OUTPUT",
                "data": {
                    "from_status": "routing",
                    "to_status": "executing",
                    "raw_prompt": "SUPER SECRET RAW TASK",
                },
                "created_at": NOW,
            },
            {
                "id": 8,
                "job_id": "job-1",
                "event_type": "executor_started",
                "phase": "MALICIOUS PHASE 2",
                "level": "MALICIOUS LEVEL 2",
                "message": "PRIVATE AGENT OUTPUT 2",
                "data": {
                    "from_status": "executing",
                    "to_status": "verifying",
                    "raw_prompt": "SUPER SECRET RAW TASK 2",
                },
                "created_at": NOW,
            },
        ]


class _Store:
    def ensure(self):
        pass

    def work_orders(self, plan_id):
        return [{
            "work_order_id": "C1",
            "sequence_no": 0,
            "execution_mode": "agent",
            "state": "running",
            "job_id": "job-1",
            "pr_number": None,
            "pr_url": None,
            "updated_at": NOW,
        }]


def test_snapshot_orders_activity_newest_first_and_limits_alerts():
    snapshot = build_dashboard_snapshot(_Storage(), _Store())
    assert snapshot["summary"]["active_plans"] == 1
    assert snapshot["summary"]["active_jobs"] == 1
    assert snapshot["summary"]["standalone_jobs"] == 0
    assert snapshot["standalone_jobs"] == []
    assert snapshot["current_plan_id"] == "pm-gh-1"
    assert snapshot["plans"][0]["token_totals"]["input_budget_tokens"] == 668_037

    events = snapshot["plans"][0]["work_orders"][0]["job"]["recent_events"]
    assert [event["seq"] for event in events] == [8, 7]
    assert events[0]["phase"] == "execution"
    assert events[0]["level"] == "info"
    assert events[0]["message"] == "Executor started"
    assert events[0]["data"] == {"from_status": "executing", "to_status": "verifying"}

    assert [alert["id"] for alert in snapshot["alerts"]] == [3, 2, 1]
    assert "provider_quotas" not in snapshot

    encoded = json.dumps(snapshot)
    assert "NOT FOR DASHBOARD" not in encoded
    assert "SUPER SECRET RAW TASK" not in encoded
    assert "PRIVATE AGENT OUTPUT" not in encoded
    assert "MALICIOUS PHASE" not in encoded
    assert "MALICIOUS LEVEL" not in encoded



def _standalone_job(status):
    job = _job()
    job.update(
        id="standalone-job",
        status=status,
        branch="ai/standalone-job",
    )
    return job


class _StandaloneStorage(_Storage):
    def __init__(self, status):
        self.status = status

    def list(self, limit=50):
        assert limit == 500
        return [_job(), _standalone_job(self.status)]

    def recent_events(self, job_ids, per_job_limit=40):
        assert job_ids == ["job-1", "standalone-job"]
        assert per_job_limit == 40
        return [{
            "id": 9,
            "job_id": "standalone-job",
            "event_type": "executor_started",
            "phase": "PRIVATE PHASE",
            "level": "PRIVATE LEVEL",
            "message": "PRIVATE STANDALONE OUTPUT",
            "data": {
                "from_status": "routing",
                "to_status": self.status,
                "raw_prompt": "PRIVATE STANDALONE PROMPT",
            },
            "created_at": NOW,
        }]


@pytest.mark.parametrize(
    ("job_status", "expected_active_jobs"),
    [
        ("queued", 2),
        ("routing", 2),
        ("executing", 2),
        ("verifying", 2),
        ("evaluating", 2),
        ("delivering", 2),
        ("blocked", 1),
        ("interrupted", 1),
    ],
)
def test_dashboard_surfaces_standalone_runtime_jobs_without_double_counting(
    job_status,
    expected_active_jobs,
):
    snapshot = build_dashboard_snapshot(_StandaloneStorage(job_status), _Store())

    assert snapshot["summary"]["active_jobs"] == expected_active_jobs
    assert snapshot["summary"]["standalone_jobs"] == 1
    assert len(snapshot["standalone_jobs"]) == 1

    standalone = snapshot["standalone_jobs"][0]
    assert standalone["id"] == "standalone-job"
    assert standalone["project_id"] == "chonhac"
    assert standalone["status"] == job_status
    assert standalone["branch"] == "ai/standalone-job"
    assert [event["seq"] for event in standalone["recent_events"]] == [9]
    assert standalone["recent_events"][0]["message"] == "Executor started"

    encoded = json.dumps(standalone)
    assert "PRIVATE STANDALONE OUTPUT" not in encoded
    assert "PRIVATE STANDALONE PROMPT" not in encoded
    assert "PRIVATE PHASE" not in encoded
    assert "PRIVATE LEVEL" not in encoded


def test_dashboard_does_not_duplicate_orchestrated_job_as_standalone():
    snapshot = build_dashboard_snapshot(_Storage(), _Store())

    assert snapshot["summary"]["active_jobs"] == 1
    assert snapshot["summary"]["standalone_jobs"] == 0
    assert snapshot["standalone_jobs"] == []


class _SupersededConnection(_Connection):
    def execute(self, query, params=None):
        if "FROM cp_plan_orchestrations" in query:
            return _Result(rows=[{
                "plan_id": "pm-gh-original",
                "project_id": "chonhac",
                "status": "blocked",
                "lifecycle": "superseded",
                "superseded_at": NOW,
                "ticket_id": "GH-14",
                "ticket_title": "Responsive regression matrix",
                "github_url": "https://example.invalid/issues/14",
                "baseline_revision": "mvp-v1",
                "baseline_source_commit": "afc0901",
                "created_at": NOW,
                "updated_at": NOW,
            }])
        if "COUNT(*)" in query:
            return _Result(row={"count": 0})
        return super().execute(query, params)


class _SupersededStorage(_Storage):
    @contextmanager
    def connect(self):
        yield _SupersededConnection()


class _SupersededStore(_Store):
    def work_orders(self, plan_id):
        row = super().work_orders(plan_id)[0]
        row.update(
            work_order_id="UI-CL-1-responsive-regression-matrix",
            state="blocked",
            lifecycle="superseded",
            job_id="job-1",
            superseded_by_plan_id="pm-gh-5772402026",
            superseded_by_work_order_id="UI-CL-1-responsive-regression-matrix-r2",
            superseded_at=NOW,
            supersession_reason="replaced_after_router_false_positive_fix",
        )
        return [row]


def test_dashboard_keeps_superseded_history_visible_but_not_actionable():
    snapshot = build_dashboard_snapshot(_SupersededStorage(), _SupersededStore())

    assert snapshot["summary"]["active_plans"] == 0
    assert snapshot["summary"]["active_jobs"] == 0
    assert snapshot["summary"]["blocked_plans"] == 0
    assert snapshot["summary"]["superseded_plans"] == 1
    plan = snapshot["plans"][0]
    work_order = plan["work_orders"][0]
    assert plan["status"] == "blocked"
    assert plan["lifecycle"] == "superseded"
    assert work_order["state"] == "blocked"
    assert work_order["lifecycle"] == "superseded"
    assert work_order["superseded_by_work_order_id"] == (
        "UI-CL-1-responsive-regression-matrix-r2"
    )
    assert work_order["job"] is not None
    assert work_order["job"]["status"] == "executing"


class _BlockedConnection(_Connection):
    def execute(self, query, params=None):
        if "FROM cp_plan_orchestrations" in query:
            row = dict(super().execute(query, params).rows[0])
            row["status"] = "blocked"
            return _Result(rows=[row])
        return super().execute(query, params)


class _BlockedStorage(_Storage):
    @contextmanager
    def connect(self):
        yield _BlockedConnection()


class _BlockedStore(_Store):
    def work_orders(self, plan_id):
        row = super().work_orders(plan_id)[0]
        row["state"] = "blocked"
        return [row]

    def progress_snapshot(self, plan_id):
        blocked = {
            "id": 1, "checkpoint_key": "wo:blocked:dashboard", "plan_id": plan_id,
            "work_order_id": "C1", "kind": "blocked", "state": "blocked",
            "job_id": "job-1", "created_at": NOW, "evidence": {
                "branch": "ai/job-1", "reason": "no_effect",
                "verification": {"passed": False, "stderr": "PRIVATE STDERR"},
                "prompt": "PRIVATE PROMPT",
            },
        }
        return {
            "orchestration": {"plan_id": plan_id, "plan": {"work_orders": [{"id": "C1"}]}},
            "work_orders": [{"work_order_id": "C1", "state": "blocked", "job_id": "job-1"}],
            "completed_checkpoints": [], "blocked_checkpoint": blocked,
            "last_good_checkpoint": None, "last_checkpoint": blocked,
        }


def test_dashboard_read_model_surfaces_bounded_blocked_plan_evidence():
    snapshot = build_dashboard_snapshot(_BlockedStorage(), _BlockedStore())
    pack = snapshot["plans"][0]["blocked_evidence"]
    assert pack["current"] == {
        "work_order_id": "C1", "job_id": "job-1", "branch": "ai/job-1",
        "checkpoint_id": 1, "checkpoint_key": "wo:blocked:dashboard",
    }
    assert pack["reason"] == "no_effect"
    assert pack["latest_verification"] == {"passed": False}
    assert pack["next_safe_action"] == "repair"
    assert "PRIVATE" not in json.dumps(pack)


class _SupervisedConnection(_Connection):
    def execute(self, query, params=None):
        if "FROM cp_plan_orchestrations" in query:
            row = dict(super().execute(query, params).rows[0])
            row.update(
                status="supervised_hold",
                lifecycle="active",
                plan={"execution_mode": "supervised"},
                supervision_generation=4,
                supervision_state="held",
                supervision_checkpoint_id=92,
                supervision_checkpoint_key="wo:completed:exact",
                supervision_checkpoint_work_order_id="C1",
                supervision_ready_work_order_ids=["C2"],
                supervision_continuation_key="plan:continue:" + "b" * 64,
            )
            return _Result(rows=[row])
        return super().execute(query, params)


class _SupervisedStorage(_Storage):
    @contextmanager
    def connect(self):
        yield _SupervisedConnection()


class _SupervisedStore(_Store):
    def work_orders(self, plan_id):
        return [
            {
                "work_order_id": "C1", "sequence_no": 0, "execution_mode": "agent",
                "state": "completed", "lifecycle": "active", "job_id": None,
                "pr_number": None, "pr_url": None, "updated_at": NOW,
            },
            {
                "work_order_id": "C2", "sequence_no": 1, "execution_mode": "agent",
                "state": "pending", "lifecycle": "active", "job_id": None,
                "pr_number": None, "pr_url": None, "updated_at": NOW,
            },
        ]


def test_dashboard_uses_durable_supervised_hold_identity():
    snapshot = build_dashboard_snapshot(_SupervisedStorage(), _SupervisedStore())
    assert snapshot["summary"]["supervised_holds"] == 1
    assert snapshot["plans"][0]["supervision"] == {
        "mode": "supervised",
        "state": "held",
        "generation": 4,
        "checkpoint": {
            "id": 92,
            "checkpoint_key": "wo:completed:exact",
            "work_order_id": "C1",
        },
        "ready_work_order_ids": ["C2"],
        "continuation_key": "plan:continue:" + "b" * 64,
    }


def test_dashboard_ui_prioritizes_live_developer_console_and_keeps_audit_timeline():
    assert "Live Developer Console" in DASHBOARD_HTML
    assert "Developer transcript" in DASHBOARD_HTML
    assert "Execution timeline" in DASHBOARD_HTML
    assert "Standalone jobs" in DASHBOARD_HTML
    assert "standalone_jobs" in DASHBOARD_HTML
    assert 'id="standaloneSelect"' in DASHBOARD_HTML
    assert "currentStandalone" in DASHBOARD_HTML
    assert "Supervised holds" in DASHBOARD_HTML
    assert "Supervised checkpoint" in DASHBOARD_HTML
    assert "p.supervision" in DASHBOARD_HTML
    assert "EventSource(" in DASHBOARD_HTML
    assert "raw chain-of-thought and secrets are never exposed" in DASHBOARD_HTML
    assert "Provider quota remaining" not in DASHBOARD_HTML
    assert "providerQuotas" not in DASHBOARD_HTML
    assert ".slice(0,3)" in DASHBOARD_HTML


def test_job_snapshot_exposes_direct_mode_without_workspace_path():
    job = _job()
    job["workspace"] = "/home/sonvh/chonhac"
    job["checkpoint"]["workspace_mode"] = "direct"

    snapshot = _job_snapshot(job)

    assert snapshot["workspace_mode"] == "direct"
    encoded = json.dumps(snapshot)
    assert "/home/sonvh/chonhac" not in encoded
    assert '"workspace"' not in encoded
