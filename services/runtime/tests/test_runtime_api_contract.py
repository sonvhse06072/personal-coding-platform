import pytest
from fastapi import HTTPException

from app.main import auth
from app.schemas import HumanDecisionRequest, JobRunRequest


def test_run_request_defaults_to_preserving_provider_failures():
    assert JobRunRequest().reset_transient_provider_failures is False


def test_human_decision_request_is_explicit():
    assert HumanDecisionRequest(action="approve", note="ok").action == "approve"


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
