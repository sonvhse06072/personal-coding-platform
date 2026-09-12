import httpx
import pytest

from app.executor_client import _raise_for_status_with_detail


def test_delivery_client_preserves_executor_error_detail():
    response = httpx.Response(
        502,
        request=httpx.Request("GET", "http://ddev-executor:8790/v1/github/ci"),
        json={
            "detail": (
                "GitHub API request failed: Resource not accessible by personal access token; "
                "Checks permission read is required"
            )
        },
    )

    with pytest.raises(RuntimeError) as exc_info:
        _raise_for_status_with_detail(response)

    message = str(exc_info.value)
    assert "DDEV executor HTTP 502" in message
    assert "Resource not accessible by personal access token" in message
    assert "Checks permission read is required" in message
