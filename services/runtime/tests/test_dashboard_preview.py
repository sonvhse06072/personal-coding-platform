from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dashboard import create_dashboard_router


class FakeStorage:
    pass


class FakeStore:
    pass


class FakeProjectPreviewManager:
    def __init__(self):
        self.started = []
        self.stopped = []

    def projects(self):
        return [{
            "project_id": "chonhac",
            "workspace_mode": "direct",
            "base_branch": "main",
            "targets": ["frontend", "backend", "both"],
        }]

    async def status(self, project_id):
        return {
            "project_id": project_id,
            "workspace_mode": "direct",
            "supported": True,
            "base_branch": "main",
            "branch": "main",
            "clean": True,
            "ownership": "idle",
            "active_job_id": None,
            "controls_enabled": True,
            "target": "both",
            "status": "ready",
            "generation": 2,
            "frontend_status": "ready",
            "backend_status": "ready",
            "frontend_url": "https://chonhac.ddev.site:3100",
            "backend_url": "https://chonhac.ddev.site",
            "error": None,
        }

    async def start(self, project_id, target):
        self.started.append((project_id, target))
        result = await self.status(project_id)
        result["target"] = target
        return result

    async def stop(self, project_id):
        self.stopped.append(project_id)
        result = await self.status(project_id)
        result.update(
            target="frontend",
            status="stopped",
            frontend_status="stopped",
            frontend_url=None,
        )
        return result


class FakePreviewManager:
    def __init__(self):
        self.started = []
        self.stopped = []

    async def status(self, job_id):
        return {
            "job_id": job_id,
            "workspace_mode": "direct",
            "supported": True,
            "target": "frontend",
            "status": "ready",
            "generation": 1,
            "frontend_url": "https://chonhac.ddev.site:3100",
            "backend_url": None,
            "integration_note": None,
            "error": None,
            "updated_at": None,
            "stopped_at": None,
        }

    async def start(self, job_id, target):
        self.started.append((job_id, target))
        result = await self.status(job_id)
        result["target"] = target
        return result

    async def stop(self, job_id):
        self.stopped.append(job_id)
        result = await self.status(job_id)
        result.update(
            status="stopped",
            frontend_url=None,
            backend_url=None,
        )
        return result


def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_READ_TOKEN", "read-secret")
    monkeypatch.setenv("DASHBOARD_CONTROL_TOKEN", "control-secret")
    preview = FakePreviewManager()
    project_preview = FakeProjectPreviewManager()
    preview.project_preview = project_preview
    app = FastAPI()
    app.include_router(
        create_dashboard_router(
            FakeStorage(),
            FakeStore(),
            preview_manager=preview,
            project_preview_manager=project_preview,
        )
    )
    return TestClient(app, base_url="https://testserver"), preview


def unlock_read(client):
    response = client.post(
        "/v1/dashboard/session",
        json={"token": "read-secret"},
    )
    assert response.status_code == 200


def test_read_session_can_observe_preview_but_cannot_mutate(monkeypatch):
    http, preview = client(monkeypatch)
    unlock_read(http)

    observed = http.get("/v1/dashboard/jobs/job-preview/preview")
    blocked = http.post(
        "/v1/dashboard/jobs/job-preview/preview",
        json={"target": "frontend"},
    )
    blocked_delete = http.delete("/v1/dashboard/jobs/job-preview/preview")

    assert observed.status_code == 200
    assert observed.json()["frontend_url"] == "https://chonhac.ddev.site:3100"
    assert blocked.status_code == 401
    assert blocked_delete.status_code == 401
    assert preview.started == []
    assert preview.stopped == []


def test_control_session_unlocks_only_bounded_preview_mutations(monkeypatch):
    http, preview = client(monkeypatch)
    unlock_read(http)

    unlocked = http.post(
        "/v1/dashboard/control-session",
        json={"token": "control-secret"},
    )
    started = http.post(
        "/v1/dashboard/jobs/job-preview/preview",
        json={"target": "both"},
    )
    stopped = http.delete("/v1/dashboard/jobs/job-preview/preview")

    assert unlocked.status_code == 200
    assert started.status_code == 200
    assert preview.started == [("job-preview", "both")]
    assert stopped.status_code == 200
    assert preview.stopped == ["job-preview"]


def test_preview_request_rejects_browser_command_path_port_and_env(monkeypatch):
    http, preview = client(monkeypatch)
    unlock_read(http)
    assert http.post(
        "/v1/dashboard/control-session",
        json={"token": "control-secret"},
    ).status_code == 200

    response = http.post(
        "/v1/dashboard/jobs/job-preview/preview",
        json={
            "target": "frontend",
            "command": "rm -rf /",
            "workspace": "/tmp/elsewhere",
            "path": "/tmp/elsewhere",
            "port": 9999,
            "hostname": "0.0.0.0",
            "env": {"TOKEN": "leak"},
        },
    )

    assert response.status_code == 422
    assert preview.started == []


def test_control_unlock_requires_existing_read_session(monkeypatch):
    http, _preview = client(monkeypatch)

    response = http.post(
        "/v1/dashboard/control-session",
        json={"token": "control-secret"},
    )

    assert response.status_code == 401


def test_dashboard_logout_clears_control_authority_too(monkeypatch):
    http, preview = client(monkeypatch)
    unlock_read(http)
    assert http.post(
        "/v1/dashboard/control-session",
        json={"token": "control-secret"},
    ).status_code == 200

    assert http.delete("/v1/dashboard/session").status_code == 200
    assert "pcp_dashboard_session" not in http.cookies
    assert "pcp_dashboard_control_session" not in http.cookies

    response = http.post(
        "/v1/dashboard/jobs/job-preview/preview",
        json={"target": "frontend"},
    )

    assert response.status_code == 401
    assert preview.started == []



def test_missing_control_token_config_returns_503(monkeypatch):
    http, _preview = client(monkeypatch)
    unlock_read(http)
    monkeypatch.delenv("DASHBOARD_CONTROL_TOKEN", raising=False)

    response = http.post(
        "/v1/dashboard/control-session",
        json={"token": "control-secret"},
    )

    assert response.status_code == 503


def test_wrong_control_token_never_unlocks_preview_mutations(monkeypatch):
    http, preview = client(monkeypatch)
    unlock_read(http)

    rejected = http.post(
        "/v1/dashboard/control-session",
        json={"token": "wrong-secret"},
    )
    assert rejected.status_code == 401

    mutation = http.post(
        "/v1/dashboard/jobs/job-preview/preview",
        json={"target": "frontend"},
    )
    assert mutation.status_code == 401
    assert preview.started == []


def test_preview_dashboard_payload_contains_no_internal_execution_secrets(monkeypatch):
    http, _preview = client(monkeypatch)
    unlock_read(http)

    response = http.get("/v1/dashboard/jobs/job-preview/preview")
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {
        "job_id",
        "workspace_mode",
        "supported",
        "target",
        "status",
        "generation",
        "frontend_url",
        "backend_url",
        "integration_note",
        "error",
        "updated_at",
        "stopped_at",
    }
    serialized = response.text
    for forbidden in (
        "RUNTIME_API_TOKEN",
        "PLATFORM_INTERNAL_TOKEN",
        "GITHUB_DELIVERY_TOKEN",
        "ANTIGRAVITY_BRIDGE_TOKEN",
        "DASHBOARD_CONTROL_TOKEN",
        '"command"',
        '"workspace"',
        '"environment"',
        "/home/sonvh/chonhac",
    ):
        assert forbidden not in serialized


def test_read_session_can_observe_current_site_but_cannot_mutate(monkeypatch):
    http, preview = client(monkeypatch)
    unlock_read(http)

    listed = http.get("/v1/dashboard/project-previews")
    observed = http.get("/v1/dashboard/projects/chonhac/preview")
    blocked = http.post(
        "/v1/dashboard/projects/chonhac/preview",
        json={"target": "frontend"},
    )
    blocked_delete = http.delete("/v1/dashboard/projects/chonhac/preview")

    assert listed.status_code == 200
    assert listed.json()["projects"][0]["project_id"] == "chonhac"
    assert observed.status_code == 200
    assert observed.json()["frontend_url"] == "https://chonhac.ddev.site:3100"
    assert blocked.status_code == 401
    assert blocked_delete.status_code == 401
    assert preview.project_preview.started == []
    assert preview.project_preview.stopped == []


def test_control_session_unlocks_bounded_current_site_mutations(monkeypatch):
    http, preview = client(monkeypatch)
    unlock_read(http)
    assert http.post(
        "/v1/dashboard/control-session",
        json={"token": "control-secret"},
    ).status_code == 200

    started = http.post(
        "/v1/dashboard/projects/chonhac/preview",
        json={"target": "both"},
    )
    stopped = http.delete("/v1/dashboard/projects/chonhac/preview")

    assert started.status_code == 200
    assert stopped.status_code == 200
    assert preview.project_preview.started == [("chonhac", "both")]
    assert preview.project_preview.stopped == ["chonhac"]


def test_current_site_request_rejects_browser_command_path_port_and_env(monkeypatch):
    http, preview = client(monkeypatch)
    unlock_read(http)
    assert http.post(
        "/v1/dashboard/control-session",
        json={"token": "control-secret"},
    ).status_code == 200

    response = http.post(
        "/v1/dashboard/projects/chonhac/preview",
        json={
            "target": "frontend",
            "command": "rm -rf /",
            "workspace": "/tmp/elsewhere",
            "port": 9999,
            "env": {"TOKEN": "leak"},
        },
    )

    assert response.status_code == 422
    assert preview.project_preview.started == []


def test_current_site_dashboard_payload_contains_no_internal_execution_details(monkeypatch):
    http, _preview = client(monkeypatch)
    unlock_read(http)

    response = http.get("/v1/dashboard/projects/chonhac/preview")

    assert response.status_code == 200
    serialized = response.text
    for forbidden in (
        "/home/sonvh/chonhac",
        "RUNTIME_API_TOKEN",
        "PLATFORM_INTERNAL_TOKEN",
        "DASHBOARD_CONTROL_TOKEN",
        '"command"',
        '"workspace"',
        '"environment"',
    ):
        assert forbidden not in serialized
