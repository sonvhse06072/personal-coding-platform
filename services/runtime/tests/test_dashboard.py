import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.dashboard import _job_snapshot, _require_session, _session_value, build_dashboard_snapshot


NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)


def _job():
    return {
        "id": "job-1",
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
    assert snapshot["models"]["current"]["id"] == "codex_terra"
    assert snapshot["models"]["current"]["reasoning_effort"] == "high"
    assert snapshot["tokens"]["input_budget_tokens"] == 668_037
    assert snapshot["tokens"]["last_attempt_gross_input_tokens"] == 7_568_037
    assert snapshot["tokens"]["last_attempt_cached_input_tokens"] == 6_900_000
    encoded = json.dumps(snapshot)
    assert "SUPER SECRET RAW TASK" not in encoded
    assert "DO NOT LEAK" not in encoded
    assert "PRIVATE AGENT OUTPUT" not in encoded
    assert "PRIVATE STDERR" not in encoded


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
            return _Result(rows=[{
                "id": 1,
                "event_type": "manual_merge_required",
                "severity": "warning",
                "project_id": "chonhac",
                "ticket_id": "GH-5",
                "plan_id": "pm-gh-1",
                "work_order_id": "C1",
                "summary": "PR ready for manual merge",
                "github_url": "https://example.invalid/pr/1",
                "status": "sent",
                "attempts": 1,
                "created_at": NOW,
                "sent_at": NOW,
            }])
        raise AssertionError(query)


class _Storage:
    @contextmanager
    def connect(self):
        yield _Connection()

    def get(self, job_id):
        return _job() if job_id == "job-1" else None


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


def test_snapshot_aggregates_plan_progress_without_raw_plan_payloads():
    snapshot = build_dashboard_snapshot(_Storage(), _Store())
    assert snapshot["summary"]["active_plans"] == 1
    assert snapshot["summary"]["active_jobs"] == 1
    assert snapshot["current_plan_id"] == "pm-gh-1"
    assert snapshot["plans"][0]["token_totals"]["input_budget_tokens"] == 668_037
    encoded = json.dumps(snapshot)
    assert "NOT FOR DASHBOARD" not in encoded
    assert "SUPER SECRET RAW TASK" not in encoded
