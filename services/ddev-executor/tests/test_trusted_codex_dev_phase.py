"""G1 disposable Codex broker security boundaries; never runs Docker/DDEV."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app import main as executor

JOB = "a" * 32
SHA = "b" * 40
PROJECT = "pcp-benchmark-synthetic"
DEV = "c" * 48
INTERNAL = "d" * 48


@pytest.fixture
def fixture(monkeypatch, tmp_path: Path):
    root = tmp_path / "isolated-workspaces"
    root.mkdir()
    workspace = root / JOB
    workspace.mkdir()
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", str(root))
    monkeypatch.setenv("PCP_TRUSTED_CODEX_BROKER_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_TRUSTED_CODEX_PROJECT_ID", PROJECT)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_JOB_ID", JOB)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_SOURCE_SHA", SHA)
    monkeypatch.setenv("PCP_TRUSTED_CODEX_DEV_TOKEN", DEV)
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", INTERNAL)
    monkeypatch.delenv("PCP_EXECUTOR_PROJECT_SCOPE", raising=False)
    for name in (
        "PCP_F2_GIT_ONLY_ENABLED", "PCP_G0_EXECUTION_ENABLED",
        "PCP_G0_DELIVERY_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    cfg = {
        "runtime": {
            "developer_permission_mode": "trusted_project",
            "workspace_mode": "isolated_clone",
            "exclusive_project_lease": False,
            "branch_prefix": "ai",
        },
        "ddev": {"enabled": True},
        "autonomy": {
            "allow_auto_merge_low_risk": False,
            "allow_production_deploy": False,
        },
        "trusted_codex_tools": {
            "targeted_tests": [
                ["ddev", "exec", "vendor/bin/phpunit", "-c",
                 "web/core/phpunit.xml.dist", "tests/src/Unit"],
            ],
            "static_analysis": [
                ["ddev", "exec", "vendor/bin/phpcs", "--standard=Drupal"],
            ],
            "frontend_quality": [
                ["ddev", "exec", "npm", "run", "build"],
            ],
        },
    }
    registry = {PROJECT: cfg}
    monkeypatch.setattr(executor, "load_projects", lambda: registry)
    monkeypatch.setattr(executor, "is_git_repo", lambda _path: True)
    monkeypatch.setattr(executor, "git", lambda _path, *args, **_kw: (
        str(workspace) if "--show-toplevel" in args else
        "ai/" + JOB[:12] if "--show-current" in args else
        "" if "--porcelain" in args else SHA
    ))

    original_subprocess = executor.subprocess.run
    def fake_run(args, *a, **kw):
        if len(args) >= 4 and args[:3] == ["git", "-C", str(workspace)]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return original_subprocess(args, *a, **kw)
    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    executor._TRUSTED_DEV_CALLS.clear()
    return workspace, registry, cfg


def payload(ws: Path, **alter):
    data = {
        "job_id": JOB, "project_id": PROJECT, "workspace": str(ws),
        "source_commit": SHA, "phase": "targeted_tests",
    }
    data.update(alter)
    return executor.TrustedCodexPhaseRequest(**data)


def test_broker_requires_distinct_capability_not_internal_auth(fixture):
    with TestClient(executor.app) as client:
        path = "/v1/codex-dev/phase"
        data = payload(fixture[0]).model_dump()
        assert client.post(path, json=data).status_code == 401
        assert client.post(path, json=data, headers={
            "Authorization": "Bearer " + INTERNAL,
        }).status_code == 401
        # Developer token cannot access the normal control/cancel endpoint.
        assert client.post("/v1/cancel", json={"job_id": JOB}, headers={
            "Authorization": "Bearer " + DEV,
        }).status_code == 401


def test_broker_refuses_activation_without_owner_gate(fixture, monkeypatch):
    monkeypatch.delenv("PCP_TRUSTED_CODEX_BROKER_ENABLED")
    with TestClient(executor.app) as client:
        result = client.post(
            "/v1/codex-dev/phase", json=payload(fixture[0]).model_dump(),
            headers={"Authorization": "Bearer " + DEV},
        )
        assert result.status_code == 503


@pytest.mark.parametrize("change", [
    {"job_id": "f" * 32}, {"project_id": "chonhac"},
    {"project_id": "pcp-benchmark-other"},
    {"source_commit": "e" * 40},
])
def test_wrong_job_project_source_denied_before_command(fixture, monkeypatch, change):
    monkeypatch.setattr(executor, "run_tracked", lambda *_a, **_kw: pytest.fail(
        "Wrong scope must not execute any DDEV command",
    ))
    # Pydantic rejects foreign project names at the HTTP schema boundary;
    # valid-looking but wrong fixture IDs reach the deeper scope check.
    with pytest.raises((HTTPException, ValidationError)):
        executor._trusted_dev_plan(payload(fixture[0], **change))


def test_workspace_and_registry_fail_closed(fixture, monkeypatch, tmp_path):
    ws, registry, cfg = fixture
    outsider = tmp_path / "chonhac"
    outsider.mkdir()
    with pytest.raises(HTTPException):
        executor._trusted_dev_plan(payload(outsider))
    alias = ws.parent / "link"
    alias.symlink_to(ws, target_is_directory=True)
    with pytest.raises(HTTPException):
        executor._trusted_dev_plan(payload(alias))
    registry["chonhac"] = cfg
    with pytest.raises(HTTPException):
        executor._trusted_dev_plan(payload(ws))


@pytest.mark.parametrize("mutate", [
    lambda c: c["runtime"].update(workspace_mode="direct"),
    lambda c: c["runtime"].update(developer_permission_mode="trusted_local"),
    lambda c: c["ddev"].update(enabled=False),
    lambda c: c["autonomy"].update(allow_production_deploy=True),
    lambda c: c["autonomy"].update(allow_auto_merge_low_risk=True),
    lambda c: c["trusted_codex_tools"].update(targeted_tests=[
        ["bash", "-lc", "docker ps"],
    ]),
    lambda c: c["trusted_codex_tools"].update(targeted_tests=[
        ["ddev", "exec", "bash", "-lc", "docker ps"],
    ]),
])
def test_untrusted_project_or_host_shell_command_denied(fixture, mutate):
    ws, _, cfg = fixture
    mutate(cfg)
    with pytest.raises(HTTPException):
        executor._trusted_dev_plan(payload(ws))


def test_broker_blocks_modified_or_untracked_ddev_config(fixture, monkeypatch):
    ws = fixture[0]
    old_git = executor.git
    monkeypatch.setattr(executor, "git", lambda p, *args, **kwargs: (
        " M .ddev/config.yaml" if "status" in args else old_git(p, *args, **kwargs)
    ))
    with pytest.raises(HTTPException, match="DDEV configuration is dirty"):
        executor._trusted_dev_plan(payload(ws))


def test_broker_never_runs_arbitrary_host_command_and_redacts_env(fixture, monkeypatch):
    ws = fixture[0]
    expected = fixture[2]["trusted_codex_tools"]["targeted_tests"][0]
    seen = []
    def fake_command(job_id, argv, *, cwd, timeout, env):
        seen.append((job_id, argv, cwd, timeout, env))
        assert "PLATFORM_INTERNAL_TOKEN" not in env
        assert "PCP_TRUSTED_CODEX_DEV_TOKEN" not in env
        assert argv == expected
        return 0, "PHPUnit PASS " + DEV, "", False
    monkeypatch.setattr(executor, "run_tracked", fake_command)
    result = executor.trusted_codex_dev_phase(payload(ws))
    assert result["passed"] is True
    assert result["tool_calls_used"] == 1
    assert len(seen) == 1 and seen[0][2] == ws
    assert DEV not in result["commands"][0]["stdout"]
    assert "[REDACTED]" in result["commands"][0]["stdout"]


def test_at_most_eight_bounded_phase_calls(fixture, monkeypatch):
    ws = fixture[0]
    monkeypatch.setattr(executor, "run_tracked",
                        lambda *_a, **_kw: (0, "", "", False))
    for i in range(8):
        assert executor.trusted_codex_dev_phase(payload(ws))["tool_calls_used"] == i + 1
    with pytest.raises(HTTPException) as err:
        executor.trusted_codex_dev_phase(payload(ws))
    assert err.value.status_code == 429
