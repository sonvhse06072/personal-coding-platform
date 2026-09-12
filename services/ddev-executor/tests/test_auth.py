import pytest
from fastapi import HTTPException

from app.main import auth


@pytest.mark.parametrize("configured", [None, "", "   ", "CHANGE_ME", "change-me"])
def test_auth_fails_closed_when_internal_token_is_not_configured(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("PLATFORM_INTERNAL_TOKEN", raising=False)
    else:
        monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", configured)

    with pytest.raises(HTTPException) as exc_info:
        auth("Bearer anything")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "PLATFORM_INTERNAL_TOKEN is not configured"


def test_auth_rejects_missing_bearer_when_token_is_configured(monkeypatch):
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "real-internal-token")

    with pytest.raises(HTTPException) as exc_info:
        auth(None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing bearer token"


def test_auth_rejects_wrong_bearer_when_token_is_configured(monkeypatch):
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "real-internal-token")

    with pytest.raises(HTTPException) as exc_info:
        auth("Bearer wrong-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid bearer token"


def test_auth_accepts_matching_bearer(monkeypatch):
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "real-internal-token")

    assert auth("Bearer real-internal-token") is None
