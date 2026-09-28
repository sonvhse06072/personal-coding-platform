import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app import main
from app.main import WorkOrderSupersessionRequest, auth
from app.schemas import HumanDecisionRequest, JobRunRequest, ReviewRepairRequest


def test_run_request_defaults_to_preserving_provider_failures():
    assert JobRunRequest().reset_transient_provider_failures is False
    assert "allow_failed" not in JobRunRequest.model_fields
    assert "allow_failed_orchestrated_resume" not in JobRunRequest.model_fields


def test_human_decision_request_is_explicit():
    assert HumanDecisionRequest(action="approve", note="ok").action == "approve"


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
