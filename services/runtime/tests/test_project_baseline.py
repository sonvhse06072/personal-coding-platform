from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.baseline import SourceReference, resolve_project_baseline
from app.config import clear_config_cache
from app.engine import RuntimeEngine
from app.main import view


def references() -> dict:
    return {
        "goals": [{"path": "docs/project/charter.md", "section": "Goals"}],
        "non_goals": [{"path": "docs/project/charter.md", "section": "Non-goals"}],
        "requirements": [{"path": "docs/project/requirements.md"}],
        "architecture_constraints": [{"path": "docs/project/architecture.md", "section": "Constraints"}],
        "quality_policy": [{"path": "docs/project/quality.md"}],
        "security_policy": [{"path": "docs/project/security.md"}],
        "budget_policy": [{"path": "docs/project/budget.md"}],
        "roadmap_frame": [{"path": "docs/project/roadmap.md"}],
    }


def revision(
    status: str = "approved",
    commit: str = "a" * 40,
    authority: list[dict] | None = None,
) -> dict:
    return {
        "status": status,
        "source_commit": commit,
        "authority": authority or [],
        "references": references(),
    }


def configure(monkeypatch, tmp_path: Path, *, baselines: dict, projects: dict | None = None) -> None:
    baselines_file = tmp_path / "project-baselines.yml"
    baselines_file.write_text(yaml.safe_dump(baselines, sort_keys=False), encoding="utf-8")
    projects_file = tmp_path / "projects.yml"
    projects_file.write_text(
        yaml.safe_dump(
            projects
            or {
                "version": 1,
                "projects": {
                    "demo": {"path": "/tmp/demo", "base_branch": "main"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_BASELINES_FILE", str(baselines_file))
    monkeypatch.setenv("PROJECTS_FILE", str(projects_file))
    clear_config_cache()


@pytest.fixture(autouse=True)
def reset_config_cache():
    clear_config_cache()
    yield
    clear_config_cache()


def test_source_reference_requires_repository_relative_posix_path() -> None:
    ref = SourceReference(path=" docs/project/requirements.md ", section=" Requirements ")
    assert ref.path == "docs/project/requirements.md"
    assert ref.section == "Requirements"

    for invalid in ("/etc/passwd", "../secret.md", "docs/../secret.md", r"docs\secret.md"):
        with pytest.raises(ValidationError):
            SourceReference(path=invalid)


def test_active_approved_revision_is_resolved_and_pinned(monkeypatch, tmp_path: Path) -> None:
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "v2",
                    "revisions": {
                        "v1": revision("superseded", "1" * 40),
                        "v2": revision("approved", "2" * 40),
                    },
                }
            },
        },
    )

    baseline = resolve_project_baseline("demo")

    assert baseline is not None
    assert baseline.project_id == "demo"
    assert baseline.revision == "v2"
    assert baseline.status == "approved"
    assert baseline.source_commit == "2" * 40
    assert baseline.references.requirements[0].path == "docs/project/requirements.md"


def test_baseline_authority_rules_are_resolved_and_persisted(monkeypatch, tmp_path: Path) -> None:
    authority = [
        {
            "path": "docs/project/constitution.md",
            "authority": "human_owner_protected",
            "note": "Project frame",
        },
        {
            "path": "docs/design.md",
            "authority": "delegated_design_owner",
        },
    ]
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "v1",
                    "revisions": {
                        "v1": revision("approved", "d" * 40, authority=authority),
                    },
                }
            },
        },
    )

    baseline = resolve_project_baseline("demo")
    assert baseline is not None
    assert [rule.model_dump(mode="json") for rule in baseline.authority] == [
        {
            "path": "docs/project/constitution.md",
            "authority": "human_owner_protected",
            "note": "Project frame",
        },
        {
            "path": "docs/design.md",
            "authority": "delegated_design_owner",
            "note": None,
        },
    ]

    storage = CaptureStorage()
    RuntimeEngine(storage).create_job(job_payload())
    assert storage.created is not None
    assert storage.created["checkpoint"]["project_baseline"]["authority"][0]["authority"] == (
        "human_owner_protected"
    )


def test_duplicate_authority_path_is_rejected(monkeypatch, tmp_path: Path) -> None:
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "v1",
                    "revisions": {
                        "v1": revision(
                            authority=[
                                {
                                    "path": "docs/project/constitution.md",
                                    "authority": "human_owner_protected",
                                },
                                {
                                    "path": "docs/project/constitution.md",
                                    "authority": "mutable_execution",
                                },
                            ]
                        ),
                    },
                }
            },
        },
    )

    with pytest.raises(ValidationError, match="authority path .* is duplicated"):
        resolve_project_baseline("demo")


def test_explicit_approved_non_active_revision_can_be_resolved(monkeypatch, tmp_path: Path) -> None:
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "v2",
                    "revisions": {
                        "v2": revision("approved", "2" * 40),
                        "v3-candidate": revision("approved", "3" * 40),
                    },
                }
            },
        },
    )

    baseline = resolve_project_baseline("demo", "v3-candidate")
    assert baseline is not None
    assert baseline.revision == "v3-candidate"
    assert baseline.source_commit == "3" * 40


@pytest.mark.parametrize("requested,status", [("draft-v2", "draft"), ("old-v1", "superseded")])
def test_unapproved_revision_is_rejected_for_new_work(
    monkeypatch,
    tmp_path: Path,
    requested: str,
    status: str,
) -> None:
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "current",
                    "revisions": {
                        "current": revision("approved", "a" * 40),
                        requested: revision(status, "b" * 40),
                    },
                }
            },
        },
    )

    with pytest.raises(ValueError, match="is not approved"):
        resolve_project_baseline("demo", requested)


def test_unknown_explicit_revision_is_rejected(monkeypatch, tmp_path: Path) -> None:
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "v1",
                    "revisions": {"v1": revision()},
                }
            },
        },
    )

    with pytest.raises(ValueError, match="Unknown ProjectBaseline revision"):
        resolve_project_baseline("demo", "missing")


def test_active_revision_must_exist_and_be_approved(monkeypatch, tmp_path: Path) -> None:
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "draft-v1",
                    "revisions": {"draft-v1": revision("draft")},
                }
            },
        },
    )

    with pytest.raises(ValidationError, match="must be approved"):
        resolve_project_baseline("demo")


def test_legacy_project_without_baseline_remains_valid(monkeypatch, tmp_path: Path) -> None:
    configure(monkeypatch, tmp_path, baselines={"version": 1, "projects": {}})
    assert resolve_project_baseline("demo") is None


class CaptureStorage:
    def __init__(self) -> None:
        self.created: dict | None = None

    def create(self, row: dict) -> None:
        self.created = deepcopy(row)


def job_payload(**overrides) -> dict:
    payload = {
        "project_id": "demo",
        "task": {"title": "bounded task", "description": "test"},
        "source_commit": None,
        "baseline_revision": None,
        "repo_hints": {},
        "provider_state": {},
        "dry_run": False,
    }
    payload.update(overrides)
    return payload


def test_job_creation_persists_baseline_snapshot_in_initial_checkpoint(monkeypatch, tmp_path: Path) -> None:
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "v1",
                    "revisions": {"v1": revision("approved", "c" * 40)},
                }
            },
        },
    )
    storage = CaptureStorage()
    engine = RuntimeEngine(storage)

    engine.create_job(job_payload())

    assert storage.created is not None
    snapshot = storage.created["checkpoint"]["project_baseline"]
    assert snapshot["project_id"] == "demo"
    assert snapshot["revision"] == "v1"
    assert snapshot["source_commit"] == "c" * 40
    assert snapshot["references"]["security_policy"][0]["path"] == "docs/project/security.md"


def test_job_creation_rejects_unknown_revision_before_storage_write(monkeypatch, tmp_path: Path) -> None:
    configure(
        monkeypatch,
        tmp_path,
        baselines={
            "version": 1,
            "projects": {
                "demo": {
                    "active_revision": "v1",
                    "revisions": {"v1": revision()},
                }
            },
        },
    )
    storage = CaptureStorage()
    engine = RuntimeEngine(storage)

    with pytest.raises(ValueError, match="Unknown ProjectBaseline revision"):
        engine.create_job(job_payload(baseline_revision="missing"))

    assert storage.created is None


def test_legacy_job_creation_has_no_baseline_snapshot(monkeypatch, tmp_path: Path) -> None:
    configure(monkeypatch, tmp_path, baselines={"version": 1, "projects": {}})
    storage = CaptureStorage()
    engine = RuntimeEngine(storage)

    engine.create_job(job_payload())

    assert storage.created is not None
    assert "project_baseline" not in storage.created["checkpoint"]


def test_job_view_exposes_pinned_baseline_revision() -> None:
    timestamp = datetime(2026, 9, 13, tzinfo=timezone.utc)
    row = {
        "id": "job12345",
        "project_id": "demo",
        "status": "queued",
        "source_commit": None,
        "branch": None,
        "workspace": None,
        "route": None,
        "checkpoint": {"project_baseline": {"revision": "v7"}},
        "result": None,
        "error": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    assert view(row).baseline_revision == "v7"
