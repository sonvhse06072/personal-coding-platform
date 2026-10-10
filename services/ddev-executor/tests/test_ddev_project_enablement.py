"""PARKED DDEV guard: fixture/other projects cannot run phases while disabled.

All tests use a synthetic projects.yml and fake workspace callbacks; no Docker,
DDEV, Chợ Nhạc, local PCP workspace or network is accessed.
"""

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from app import main as executor


def _synthetic_project(monkeypatch, tmp_path: Path, *, enabled, mode="isolated_clone"):
    projects = {
        "projects": {
            "fixture_only": {
                "path": str(tmp_path / "synthetic-fixture"),
                "base_branch": "benchmark/pcp",
                "runtime": {"workspace_mode": mode, "branch_prefix": "ai"},
                "ddev": {
                    "enabled": enabled,
                    "targeted_tests": ["ddev exec vendor/bin/phpunit"],
                    "cleanup": ["ddev stop --unlist --omit-snapshot"],
                },
            },
        },
    }
    cfg = tmp_path / "projects.yml"
    cfg.write_text(yaml.safe_dump(projects), encoding="utf-8")
    monkeypatch.setenv("PROJECTS_FILE", str(cfg))

    def unexpected(*_args, **_kwargs):
        pytest.fail("disabled DDEV project must not access workspaces or spawn commands")

    monkeypatch.setattr(executor, "_validate_workspace", unexpected)
    monkeypatch.setattr(executor, "_reconcile_workspace_ddev_identity", unexpected)
    monkeypatch.setattr(executor, "run_tracked", unexpected)
    return tmp_path / "no-fixture-workspace"


@pytest.mark.parametrize("enabled", [False, None, "false", "true", 0, 1])
@pytest.mark.parametrize("phase_name", ["preflight", "targeted_tests", "cleanup"])
def test_parked_fixture_never_runs_a_ddev_phase(
    tmp_path, monkeypatch, enabled, phase_name,
):
    workspace = _synthetic_project(
        monkeypatch, tmp_path, enabled=enabled,
    )
    with pytest.raises(HTTPException) as error:
        executor.phase(
            executor.PhaseRequest(
                job_id="fixturejob123",
                project_id="fixture_only",
                workspace=str(workspace),
                phase=phase_name,
            )
        )
    assert error.value.status_code == 409
    assert "PARKED" in error.value.detail


@pytest.mark.parametrize("remove_data", [False, True])
def test_parked_isolated_fixture_refuses_even_destructive_quiesce(
    tmp_path, monkeypatch, remove_data,
):
    workspace = _synthetic_project(
        monkeypatch, tmp_path, enabled=False,
    )
    with pytest.raises(HTTPException) as error:
        executor.quiesce_workspace(
            executor.QuiesceWorkspaceRequest(
                job_id="fixturejob123",
                project_id="fixture_only",
                workspace=str(workspace),
                remove_data=remove_data,
            )
        )
    assert error.value.status_code == 409
    assert "PARKED" in error.value.detail


@pytest.mark.parametrize("enabled", [False, None, "false", "true", 0, 1])
def test_enabled_guard_only_accepts_literal_boolean_true(enabled):
    with pytest.raises(HTTPException) as error:
        executor._require_ddev_enabled({"ddev": {"enabled": enabled}})
    assert error.value.status_code == 409


def test_explicit_true_passes_only_the_enablement_check():
    # This is not permission for host-wide DDEV access. Remaining workspace,
    # source, lease, authorization and separate activation gates still apply.
    assert executor._require_ddev_enabled({"ddev": {"enabled": True}}) is None


def test_invalid_ddev_config_fails_closed():
    for malformed in (None, [], "true", 123):
        with pytest.raises(HTTPException):
            executor._require_ddev_enabled({"ddev": malformed})


def test_parked_fixture_source_state_has_no_enabled_bypass(monkeypatch, tmp_path):
    # Direct invocations of the API method cannot override YAML authority.
    path = _synthetic_project(monkeypatch, tmp_path, enabled=False)
    with pytest.raises(HTTPException) as error:
        executor.phase(
            executor.PhaseRequest(
                job_id="fixturejob123",
                project_id="fixture_only",
                workspace=str(path),
                phase="targeted_tests",
                timeout_seconds=1800,
            )
        )
    assert error.value.status_code == 409
