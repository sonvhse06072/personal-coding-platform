from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.preview import PreviewManager, ready_preview_context
from app.prompts import evaluator_prompt, execution_prompt


NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


class FakeStorage:
    def __init__(self, *, direct=True, lease=True):
        self.job = {
            "id": "job-preview-1234",
            "project_id": "chonhac",
            "status": "executing",
            "workspace": "/home/sonvh/chonhac",
            "checkpoint": {
                "workspace_mode": "direct" if direct else "isolated_clone",
            },
            "progress": {
                "model_calls": 3,
                "repair_iterations": 1,
            },
        }
        self.preview = None
        self.lease_enabled = lease
        self.job_updates = []

    def get(self, job_id):
        return deepcopy(self.job) if job_id == self.job["id"] else None

    def update(self, job_id, **fields):
        self.job_updates.append((job_id, deepcopy(fields)))
        raise AssertionError("Preview must never mutate coding job state")

    def project_lease(self, project_id):
        if not self.lease_enabled:
            return None
        return {
            "project_id": project_id,
            "owner_job_id": self.job["id"],
            "state": "active",
            "generation": 1,
        }

    def preview_state(self, job_id):
        return deepcopy(self.preview) if job_id == self.job["id"] else None

    def upsert_preview_state(
        self,
        *,
        job_id,
        project_id,
        target,
        status,
        generation,
        frontend_url=None,
        backend_url=None,
        integration_note=None,
        error=None,
        stopped=False,
    ):
        created_at = (self.preview or {}).get("created_at", NOW)
        self.preview = {
            "job_id": job_id,
            "project_id": project_id,
            "target": target,
            "status": status,
            "generation": generation,
            "frontend_url": frontend_url,
            "backend_url": backend_url,
            "integration_note": integration_note,
            "error": error,
            "created_at": created_at,
            "updated_at": NOW,
            "stopped_at": NOW if stopped else None,
        }
        return deepcopy(self.preview)


class FakeDdev:
    def __init__(self, *, fail_start=False, failure_message="preview build failed safely"):
        self.fail_start = fail_start
        self.failure_message = failure_message
        self.starts = []
        self.statuses = []
        self.stops = []
        self.observed_status = "ready"

    async def preview_start(self, **payload):
        self.starts.append(deepcopy(payload))
        if self.fail_start:
            raise RuntimeError(self.failure_message)
        target = payload["target"]
        return {
            "status": "ready",
            "frontend_url": (
                "https://chonhac.ddev.site:3100"
                if target in {"frontend", "both"}
                else None
            ),
            "backend_url": (
                "https://chonhac.ddev.site"
                if target in {"backend", "both"}
                else None
            ),
            "integration_note": "bounded note" if target == "both" else None,
        }

    async def preview_status(self, **payload):
        self.statuses.append(deepcopy(payload))
        return {
            "status": self.observed_status,
            "frontend_url": (
                "https://chonhac.ddev.site:3100"
                if self.observed_status == "ready"
                and payload["target"] in {"frontend", "both"}
                else None
            ),
            "backend_url": (
                "https://chonhac.ddev.site"
                if self.observed_status == "ready"
                and payload["target"] in {"backend", "both"}
                else None
            ),
        }

    async def preview_stop(self, **payload):
        self.stops.append(deepcopy(payload))
        return {"status": "stopped"}


def configure_project(monkeypatch, *, direct=True):
    monkeypatch.setattr(
        "app.preview.project_config",
        lambda project_id: {
            "runtime": {
                "workspace_mode": "direct" if direct else "isolated_clone",
                "exclusive_project_lease": direct,
            },
            "preview": {
                "backend": {"enabled": True},
                "frontend": {"enabled": True},
            },
        },
    )


def test_direct_preview_start_is_independent_from_job_state(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    ddev = FakeDdev()
    manager = PreviewManager(storage, ddev)
    original_job = deepcopy(storage.job)

    result = asyncio.run(manager.start(storage.job["id"], "both"))

    assert result["status"] == "ready"
    assert result["generation"] == 1
    assert result["frontend_url"] == "https://chonhac.ddev.site:3100"
    assert result["backend_url"] == "https://chonhac.ddev.site"
    assert len(ddev.starts) == 1
    assert storage.job == original_job
    assert storage.job_updates == []


def test_preview_rebuild_increments_its_own_generation_only(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    ddev = FakeDdev()
    manager = PreviewManager(storage, ddev)

    first = asyncio.run(manager.start(storage.job["id"], "frontend"))
    second = asyncio.run(manager.start(storage.job["id"], "frontend"))

    assert first["generation"] == 1
    assert second["generation"] == 2
    assert storage.job["progress"] == {
        "model_calls": 3,
        "repair_iterations": 1,
    }


def test_preview_start_requires_exact_active_lease(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage(lease=False)
    manager = PreviewManager(storage, FakeDdev())

    with pytest.raises(RuntimeError, match="exact active project lease"):
        asyncio.run(manager.start(storage.job["id"], "frontend"))

    assert storage.preview is None


def test_preview_failure_stays_in_preview_state(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    manager = PreviewManager(storage, FakeDdev(fail_start=True))
    original_job = deepcopy(storage.job)

    result = asyncio.run(manager.start(storage.job["id"], "frontend"))

    assert result["status"] == "failed"
    assert result["error"] == "Preview operation failed."
    assert storage.job == original_job
    assert storage.job_updates == []




def test_preview_failure_summary_never_exposes_executor_paths_tokens_or_commands(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    ddev = FakeDdev(
        fail_start=True,
        failure_message=(
            "DDEV executor HTTP 502: command='bash -lc env' "
            "workspace=/home/sonvh/chonhac "
            "RUNTIME_API_TOKEN=super-secret"
        ),
    )
    manager = PreviewManager(storage, ddev)

    result = asyncio.run(manager.start(storage.job["id"], "frontend"))

    assert result["status"] == "failed"
    assert result["error"] == "Preview infrastructure operation failed (executor HTTP 502)."
    serialized = repr(result)
    assert "/home/sonvh/chonhac" not in serialized
    assert "super-secret" not in serialized
    assert "bash -lc env" not in serialized


def test_status_retires_preview_after_lease_loss(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    ddev = FakeDdev()
    manager = PreviewManager(storage, ddev)

    asyncio.run(manager.start(storage.job["id"], "frontend"))
    storage.lease_enabled = False

    result = asyncio.run(manager.status(storage.job["id"]))

    assert result["status"] == "stopped"
    assert "lease is no longer active" in result["error"]
    assert len(ddev.stops) == 1


def test_status_reconciles_executor_pause_after_frontend_quality(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    ddev = FakeDdev()
    manager = PreviewManager(storage, ddev)

    asyncio.run(manager.start(storage.job["id"], "frontend"))
    ddev.observed_status = "stopped"

    result = asyncio.run(manager.status(storage.job["id"]))

    assert result["status"] == "stopped"
    assert result["frontend_url"] is None


def test_isolated_job_is_visible_as_unsupported_but_cannot_start(monkeypatch):
    configure_project(monkeypatch, direct=False)
    storage = FakeStorage(direct=False)
    manager = PreviewManager(storage, FakeDdev())

    status = asyncio.run(manager.status(storage.job["id"]))

    assert status["workspace_mode"] == "isolated_clone"
    assert status["supported"] is False
    assert status["status"] == "unsupported"

    with pytest.raises(RuntimeError, match="direct-workspace jobs"):
        asyncio.run(manager.start(storage.job["id"], "frontend"))


def test_stop_is_idempotent_for_never_built_direct_preview(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    manager = PreviewManager(storage, FakeDdev())

    result = asyncio.run(manager.stop(storage.job["id"]))

    assert result["status"] == "not_built"
    assert result["generation"] == 0



def test_ready_preview_context_is_reconciled_and_browser_safe(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    ddev = FakeDdev()
    manager = PreviewManager(storage, ddev)
    asyncio.run(manager.start(storage.job["id"], "both"))

    context = asyncio.run(
        ready_preview_context(storage, ddev, storage.job["id"])
    )

    assert context == {
        "status": "ready",
        "target": "both",
        "frontend_url": "https://chonhac.ddev.site:3100",
        "backend_url": "https://chonhac.ddev.site",
        "integration_note": "bounded note",
        "usage_note": (
            "This URL is available for bounded local review where tooling supports it. "
            "Availability alone is not evidence that visual/browser review occurred."
        ),
    }
    serialized = repr(context)
    for forbidden in ("workspace", "command", "env", "token", "secret"):
        assert forbidden not in serialized.lower()


def test_ready_preview_context_disappears_when_executor_reports_stopped(monkeypatch):
    configure_project(monkeypatch)
    storage = FakeStorage()
    ddev = FakeDdev()
    manager = PreviewManager(storage, ddev)
    asyncio.run(manager.start(storage.job["id"], "frontend"))
    ddev.observed_status = "stopped"

    context = asyncio.run(
        ready_preview_context(storage, ddev, storage.job["id"])
    )

    assert context is None
    assert storage.preview["status"] == "stopped"


def test_developer_and_evaluator_prompts_label_preview_as_optional_not_evidence():
    context = {
        "status": "ready",
        "target": "frontend",
        "frontend_url": "https://chonhac.ddev.site:3100",
        "usage_note": "Availability alone is not evidence that visual/browser review occurred.",
    }
    route = {
        "strategy": {
            "profile": "standard",
            "definition_of_done": {"required": ["material_change"]},
        }
    }

    developer = execution_prompt(
        task={"title": "Preview task", "description": "Bounded local UI change"},
        route=route,
        repo_analysis={},
        preview_context=context,
    )
    evaluator = evaluator_prompt(
        task={"title": "Preview task", "description": "Bounded local UI change"},
        diff="diff --git a/a b/a",
        verification={"passed": True},
        preview_context=context,
    )

    assert "https://chonhac.ddev.site:3100" in developer
    assert "Do not claim visual/browser review unless you actually performed it" in developer
    assert "https://chonhac.ddev.site:3100" in evaluator
    assert "not proof that visual/browser review occurred" in evaluator
