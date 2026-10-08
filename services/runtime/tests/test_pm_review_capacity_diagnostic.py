from __future__ import annotations

import asyncio
import json

from app import pm_review_capacity_diagnostic as capacity
from app.pm_review_capacity_diagnostic import probe_reviewer_capacity


JOB = {
    "id": "057f6acff17b501eae3a673cbb6bbe36",
    "project_id": "chonhac",
    "status": "completed",
    "task": {"semantic": {}},
    "checkpoint": {
        "provider_state": {
            "provider:openai": {"available": True},
            "provider:google_antigravity": {
                "healthy": True, "available": True,
            },
        },
    },
}

REGISTRY = {
    "status": "registry_evaluated",
    "writer_providers": ["openai"],
    "cross_provider_registered_model_ids": [
        "antigravity_free",
        "antigravity_gemini_pro",
    ],
}


class FakeRouter:
    def __init__(self, *, outcome="success"):
        self.calls = []
        self.outcome = outcome

    async def staff(self, payload):
        self.calls.append(payload)
        if self.outcome == "no_capacity":
            raise RuntimeError(
                "No eligible model for role=reviewer; rejected={'secret':'DO_NOT_PUBLISH'}"
            )
        if self.outcome == "auth_error":
            raise RuntimeError("Token DO_NOT_PUBLISH /root/.config/secret")
        if self.outcome == "forged":
            model_id = "codex_sol"
            provider = "openai"
            adapter = "codex_cli"
            model = "gpt-5.6-sol"
        else:
            model_id = "antigravity_free"
            provider = "google_antigravity"
            adapter = "antigravity_host"
            model = "gemini-3.8-flash-medium"
        return {
            "request_id": payload["request_id"],
            "role": "reviewer",
            "choice": {
                "id": model_id,
                "provider": provider,
                "adapter": adapter,
                "model": model,
            },
        }


VIEW = {
    "collectors": [
        {
            "source": "antigravity_quota",
            "status": "ok",
            "last_success_at": "2026-10-08T09:00:00Z",
            "error": "DO_NOT_PUBLISH collector path /home/owner/.secret",
        },
    ],
    "provider_state": {
        "quota:model:antigravity_free": {
            "available": True,
            "healthy": True,
        },
        "quota:antigravity_gemini": {"available": False},
    },
    "snapshots": [
        {"quota_id": "DO_NOT_PUBLISH", "remaining_percent": 0.3},
    ],
}


def _run(monkeypatch, *, outcome="success"):
    monkeypatch.setattr(
        capacity, "registered_review_capacity",
        lambda job: dict(REGISTRY),
    )
    router = FakeRouter(outcome=outcome)
    result = asyncio.run(
        probe_reviewer_capacity(
            job=dict(JOB),
            router=router,
            quota_view=dict(VIEW),
        ),
    )
    return result, router


def test_staffing_success_is_not_model_invocation_or_attestation(monkeypatch):
    result, router = _run(monkeypatch)
    assert result["status"] == "eligible_cross_provider_at_probe"
    assert result["staffed_model_id"] == "antigravity_free"
    assert result["staffed_provider"] == "google_antigravity"
    assert result["staffing_checked"] is True
    assert result["staffing_is_model_invocation"] is False
    assert result["quota_is_model_availability_proof"] is False
    assert len(router.calls) == 1
    payload = router.calls[0]
    assert payload["role"] == "reviewer"
    assert payload["profile"] == "critical"
    assert payload["provider_state"]["provider:openai"]["available"] is False
    assert payload["provider_state"]["provider:google_antigravity"]["available"] is True
    assert result["antigravity_collector"] == {
        "status": "ok", "has_successful_collection": True,
    }
    assert result["cross_provider_models"][0]["fresh_model_quota"] == "not_explicitly_blocked"
    assert result["cross_provider_models"][0]["fresh_group_quota"] == "unavailable"
    serialized = json.dumps(result)
    assert "DO_NOT_PUBLISH" not in serialized
    assert "/home/owner/" not in serialized


def test_no_capacity_reports_only_allowlisted_code_and_no_provider_exception(monkeypatch):
    result, router = _run(monkeypatch, outcome="no_capacity")
    assert len(router.calls) == 1
    assert result["status"] == "no_eligible_cross_provider_now"
    assert result["staffing_checked"] is True
    assert "DO_NOT_PUBLISH" not in json.dumps(result)


def test_auth_transport_or_untrusted_staffing_never_claims_eligibility(monkeypatch):
    for outcome in ("auth_error", "forged"):
        result, router = _run(monkeypatch, outcome=outcome)
        assert result["status"] == "staffing_unverifiable"
        assert "staffed_model_id" not in result
        assert len(router.calls) == 1
        assert "DO_NOT_PUBLISH" not in json.dumps(result)


def test_writer_provenance_error_never_contacts_router(monkeypatch):
    monkeypatch.setattr(
        capacity, "registered_review_capacity",
        lambda job: {
            "status": "provenance_unverifiable",
            "reason": "writer_identity_unverifiable",
        },
    )
    router = FakeRouter()
    value = asyncio.run(
        probe_reviewer_capacity(job=dict(JOB), router=router, quota_view={}),
    )
    assert value["status"] == "provenance_unverifiable"
    assert value["staffing_checked"] is False
    assert not router.calls


def test_missing_registered_reviewers_does_not_route(monkeypatch):
    monkeypatch.setattr(
        capacity, "registered_review_capacity",
        lambda job: {
            **REGISTRY, "cross_provider_registered_model_ids": [],
        },
    )
    router = FakeRouter()
    value = asyncio.run(
        probe_reviewer_capacity(job=dict(JOB), router=router, quota_view={}),
    )
    assert value["status"] == "no_registered_cross_provider_candidate"
    assert not router.calls


def test_quota_collector_error_is_bounded_and_cannot_leak_error_text(monkeypatch):
    monkeypatch.setattr(
        capacity, "registered_review_capacity", lambda job: dict(REGISTRY),
    )
    view = {
        "collectors": [
            {"source": "antigravity_quota", "status": "error",
             "error": "DO_NOT_PUBLISH /home/private/token"},
        ],
        "provider_state": {},
    }
    result = asyncio.run(probe_reviewer_capacity(
        job=dict(JOB), router=FakeRouter(outcome="no_capacity"),
        quota_view=view,
    ))
    assert result["antigravity_collector"] == {
        "status": "error", "has_successful_collection": False,
    }
    assert "DO_NOT_PUBLISH" not in json.dumps(result)
