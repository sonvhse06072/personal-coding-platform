import asyncio
import httpx
import pytest

from app.executor_client import DdevExecutorClient, _raise_for_status_with_detail


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


def test_create_workspace_preserves_executor_422_detail(monkeypatch):
    response = httpx.Response(
        422,
        request=httpx.Request("POST", "http://ddev-executor:8790/v1/workspaces"),
        json={
            "detail": (
                "fatal: ambiguous argument "
                "'aa8e68dd9aea6740de446151eb97615931de9b40': unknown revision"
            )
        },
    )

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return response

    monkeypatch.setattr(
        "app.executor_client.httpx.AsyncClient",
        lambda *args, **kwargs: FakeClient(),
    )

    client = DdevExecutorClient()
    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(
            client.create_workspace(
                job_id="pm-9a3d224d78904bf0bb057c03abb9ddb9",
                project_id="chonhac",
                ref="aa8e68dd9aea6740de446151eb97615931de9b40",
                workspace_mode="isolated_clone",
            )
        )

    message = str(exc_info.value)
    assert "DDEV executor HTTP 422" in message
    assert "aa8e68dd9aea6740de446151eb97615931de9b40" in message
    assert "unknown revision" in message
