import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from app import main
from app.main import WorkOrderSupersessionRequest, auth
from app.schemas import HumanDecisionRequest, JobRunRequest, ReviewRepairRequest


def test_run_request_defaults_to_preserving_provider_failures():
    request = JobRunRequest()
    assert request.reset_transient_provider_failures is False
    assert request.verification_only_after_pm_handoff is False
    assert "allow_failed" not in JobRunRequest.model_fields
    assert "allow_failed_orchestrated_resume" not in JobRunRequest.model_fields


def test_run_api_forwards_explicit_pm_handoff_verification_only(monkeypatch):
    calls = []

    async def resume(job_id, **fields):
        calls.append((job_id, fields))
        timestamp = datetime.now(timezone.utc)
        return {
            "id": job_id,
            "project_id": "demo",
            "status": "queued",
            "source_commit": "a" * 40,
            "route": {},
            "checkpoint": {},
            "result": {"reason": "material_change_missing_without_model_fallback"},
            "error": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    monkeypatch.setattr(main.engine, "resume", resume)
    monkeypatch.setattr(main, "prepare_orchestrated_job_resume", lambda *args: None)
    monkeypatch.setattr(main, "reopen_orchestrated_job", lambda *args: None)

    payload = JobRunRequest(verification_only_after_pm_handoff=True)
    result = asyncio.run(main.run_job("job12345", payload))

    assert result.status == "queued"
    assert calls == [
        (
            "job12345",
            {
                "reset_transient_provider_failures": False,
                "reroute": False,
                "verification_only_after_pm_handoff": True,
                "_allow_failed_orchestrated_resume": False,
            },
        )
    ]


def test_human_decision_request_is_explicit():
    request = HumanDecisionRequest(
        action="approve",
        note="ok",
        decision_key="review_repair_churn:request-1:generation:0",
    )
    assert request.action == "approve"
    assert request.decision_key == "review_repair_churn:request-1:generation:0"


def test_human_decision_api_forwards_exact_decision_key(monkeypatch):
    calls = []

    async def resolve(job_id, **fields):
        calls.append((job_id, fields))
        return {
            "id": job_id,
            "project_id": "demo",
            "status": "queued",
            "source_commit": "a" * 40,
            "route": {},
            "checkpoint": {},
            "result": {"reason": "review_repair_churn_authorized"},
            "error": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    async def tick():
        return None

    monkeypatch.setattr(main.engine, "resolve_human_decision", resolve)
    monkeypatch.setattr(main.plan_orchestrator, "tick", tick)
    payload = HumanDecisionRequest(
        action="approve",
        note="one bounded window",
        decision_key="review_repair_churn:request-1:generation:0",
    )

    result = asyncio.run(main.resolve_decision("job12345", payload))

    assert result.status == "queued"
    assert calls == [
        (
            "job12345",
            {
                "action": "approve",
                "note": "one bounded window",
                "expected_decision_key": (
                    "review_repair_churn:request-1:generation:0"
                ),
            },
        )
    ]


def test_review_repair_request_is_bounded_and_explicit():
    request = ReviewRepairRequest(
        expected_commit="a" * 40,
        finding="Repair one bounded PM finding.",
        evidence={"review": "PM-38"},
        references=["PR #38"],
    )

    assert request.expected_commit == "a" * 40
    assert request.finding == "Repair one bounded PM finding."
    assert "reroute" not in ReviewRepairRequest.model_fields


def test_review_repair_api_uses_dedicated_engine_transition(monkeypatch):
    calls = []

    async def request(job_id, **fields):
        calls.append((job_id, fields))
        return {
            "id": job_id,
            "project_id": "demo",
            "status": "queued",
            "source_commit": "a" * 40,
            "branch": "ai/job12345",
            "workspace": "/workspaces/job12345",
            "route": {},
            "checkpoint": {},
            "result": {"review_repair_pending": True},
            "error": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    monkeypatch.setattr(main.engine, "request_review_repair", request)
    payload = ReviewRepairRequest(
        expected_commit="b" * 40,
        finding="bounded finding",
        evidence={"review": "PM-38"},
        references=["PR #38"],
    )

    result = asyncio.run(main.request_review_repair("job12345", payload))

    assert result.status == "queued"
    assert calls == [(
        "job12345",
        {
            "expected_commit": "b" * 40,
            "finding": "bounded finding",
            "evidence": {"review": "PM-38"},
            "references": ["PR #38"],
        },
    )]


def test_supersession_api_forwards_only_exact_structured_identity(monkeypatch):
    calls = []

    class Store:
        def supersede_work_order(self, **fields):
            calls.append(fields)
            return {"changed": True, "work_order": {"lifecycle": "superseded"}}

    monkeypatch.setattr(main.plan_orchestrator, "store", Store())
    payload = WorkOrderSupersessionRequest(
        reason="explicit replacement",
        superseded_by_plan_id="replacement-plan",
        superseded_by_work_order_id="WO-r2",
    )

    result = main.supersede_orchestrated_work_order("original-plan", "WO", payload)

    assert result["work_order"]["lifecycle"] == "superseded"
    assert calls == [{
        "plan_id": "original-plan",
        "work_order_id": "WO",
        "reason": "explicit replacement",
        "superseded_by_plan_id": "replacement-plan",
        "superseded_by_work_order_id": "WO-r2",
    }]


@pytest.mark.parametrize("configured", [None, "", "   ", "CHANGE_ME", "change-me"])
def test_runtime_auth_fails_closed_when_token_is_not_configured(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("RUNTIME_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("RUNTIME_API_TOKEN", configured)

    with pytest.raises(HTTPException) as exc_info:
        auth("Bearer anything")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "RUNTIME_API_TOKEN is not configured"


def test_runtime_auth_accepts_only_the_configured_bearer_token(monkeypatch):
    monkeypatch.setenv("RUNTIME_API_TOKEN", "runtime-secret")

    auth("Bearer runtime-secret")

    with pytest.raises(HTTPException) as missing:
        auth(None)
    assert missing.value.status_code == 401
    assert missing.value.detail == "Missing bearer token"

    with pytest.raises(HTTPException) as invalid:
        auth("Bearer wrong-secret")
    assert invalid.value.status_code == 401
    assert invalid.value.detail == "Invalid bearer token"


def _historical_execution_plan_row() -> dict:
    timestamp = datetime.now(timezone.utc)
    return {
        "id": "pm-historical",
        "project_id": "demo",
        "status": "ready",
        "baseline_revision": "v1",
        "baseline_source_commit": "a" * 40,
        "ticket": {
            "id": "T-100",
            "title": "Historical plan",
            "description": "Persisted before concrete visual-route enforcement.",
        },
        "staffing": None,
        "plan": {
            "scope_assessment": "in_scope",
            "summary": "Historical persisted plan.",
            "work_orders": [
                {
                    "id": "WO-HIST",
                    "parent_ticket": "T-100",
                    "objective": "Historical bounded work",
                    "baseline_revision": "v1",
                    "source_references": [{"path": "docs/scope.md"}],
                    "in_scope": ["historical bounded work"],
                    "out_of_scope": ["unrelated work"],
                    "acceptance_criteria": [
                        {"id": "AC-1", "description": "Historical acceptance"}
                    ],
                    "constraints": ["Preserve history"],
                    "requested_role": "developer",
                    "verification": {
                        "required_phases": [
                            "targeted_tests",
                            "frontend_quality",
                            "visual_quality",
                        ],
                        "visual_routes": ["/events/[slug]"],
                    },
                    "risk": {"level": "standard", "flags": []},
                    "budget": {
                        "max_profile": "standard",
                        "max_model_calls": 4,
                        "max_repair_iterations": 1,
                        "max_wall_time_minutes": 20,
                        "max_changed_files": 8,
                    },
                    "dependencies": [],
                }
            ],
            "decision_boundaries": [],
            "ready_work_order_ids": ["WO-HIST"],
            "execution_mode": "supervised",
        },
        "usage": {"model_calls": 1},
        "error": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def test_get_execution_plan_serializes_historical_template_routes(monkeypatch):
    row = _historical_execution_plan_row()
    monkeypatch.setattr(main.storage, "get_execution_plan", lambda plan_id: row)

    result = main.get_execution_plan("pm-historical")
    payload = jsonable_encoder(result)

    assert payload["id"] == "pm-historical"
    assert payload["plan"]["work_orders"][0]["verification"]["visual_routes"] == [
        "/events/[slug]"
    ]
    assert row["plan"]["work_orders"][0]["verification"]["visual_routes"] == [
        "/events/[slug]"
    ]


def test_get_execution_plan_keeps_missing_plan_404(monkeypatch):
    monkeypatch.setattr(main.storage, "get_execution_plan", lambda plan_id: None)

    with pytest.raises(HTTPException) as exc_info:
        main.get_execution_plan("missing-plan")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "ExecutionPlan not found"
