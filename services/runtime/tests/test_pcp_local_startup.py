"""B2.2c0 source-only startup regression: no real state or external systems."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import runpy

import httpx
import pytest
import yaml

from app import main as runtime_main
from app.baseline import ProjectBaselineRegistry, resolve_project_baseline

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "config/projects.pcp-local.yml"
BASELINE = ROOT / "config/project-baselines.pcp-local.yml"


def setup_drafts(monkeypatch, tmp_path):
    project = tmp_path / PROJECT.name
    baseline = tmp_path / BASELINE.name
    p = yaml.safe_load(PROJECT.read_text(encoding="utf-8"))
    b = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    project.write_text(yaml.safe_dump(p), encoding="utf-8")
    baseline.write_text(yaml.safe_dump(b), encoding="utf-8")
    monkeypatch.setenv("PROJECTS_FILE", str(project))
    monkeypatch.setenv("PROJECT_BASELINES_FILE", str(baseline))
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "pcp_local_inspect")
    monkeypatch.delenv("PCP_FULLPATH_SOURCE_ONLY", raising=False)
    for key in runtime_main._PCP_LOCAL_FLAGS:
        monkeypatch.delenv(key, raising=False)
    return project, baseline, p, b


def forbid_external(monkeypatch):
    calls = []
    async def blocked(*args, **kwargs):
        calls.append("unsafe")
        raise AssertionError("Legacy DB/job/engine/publisher invocation")
    monkeypatch.setattr(
        runtime_main, "harden_runtime_process_secret_boundary",
        lambda: calls.append("harden"),
    )
    for item in (
        runtime_main.engine, runtime_main.plan_orchestrator,
        runtime_main.progress_publisher, runtime_main.job_status_publisher,
    ):
        monkeypatch.setattr(item, "start", blocked)
        monkeypatch.setattr(item, "stop", blocked)
    return calls


def assert_fail_start():
    async def run():
        with pytest.raises(RuntimeError, match="PCP-local"):
            async with runtime_main.lifespan(runtime_main.app):
                pytest.fail("invalid PCP-local startup entered")
    asyncio.run(run())


def test_committed_drafts_have_no_authority(monkeypatch, tmp_path):
    _, _, p, b = setup_drafts(monkeypatch, tmp_path)
    runtime_main._validate_pcp_local_inspection()
    assert list(p["projects"]) == ["pcp-local"]
    assert p["projects"]["pcp-local"]["path"] is None
    assert all(v is False for v in p["projects"]["pcp-local"]["autonomy"].values())
    assert ProjectBaselineRegistry.model_validate(b).projects["pcp-local"].active_revision is None
    monkeypatch.setattr("app.baseline.project_baselines_doc", lambda: b)
    assert resolve_project_baseline("pcp-local") is None
    with pytest.raises(ValueError, match="no ProjectBaseline"):
        resolve_project_baseline("pcp-local", "fake")


def test_parked_lifespan_and_middleware_have_zero_external_effects(monkeypatch, tmp_path):
    setup_drafts(monkeypatch, tmp_path)
    calls = forbid_external(monkeypatch)
    async def forbid_health():
        calls.append("network")
        raise AssertionError("health may not touch Router/Executor")
    monkeypatch.setattr(runtime_main.engine.router, "health", forbid_health)
    monkeypatch.setattr(runtime_main.engine.ddev, "health", forbid_health)

    async def run():
        transport = httpx.ASGITransport(app=runtime_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/health")).status_code == 503
        async with runtime_main.lifespan(runtime_main.app):
            assert runtime_main.app.state.pcp_local_inspection_ready is True
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                result = await client.get("/health")
                assert result.status_code == 200
                assert result.json()["status"] == "degraded"
                assert result.json()["router"] == "not_checked"
                for method, url in [
                    ("GET", "/v1/jobs"), ("GET", "/v1/quota"),
                    ("GET", "/dashboard"),
                    ("GET", "/v1/pm-bridge/local-source/candidates"),
                    ("POST", "/v1/intake"), ("POST", "/v1/jobs"),
                    ("POST", "/v1/g0-fixture/prepare"),
                ]:
                    assert (await client.request(method, url)).status_code == 503
                # Changing an env variable cannot unpark a live process.
                monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
                assert (await client.get("/health")).status_code == 503
                assert (await client.post("/v1/jobs")).status_code == 503
        assert runtime_main.app.state.pcp_local_inspection_ready is False
    asyncio.run(run())
    assert calls == []


@pytest.mark.parametrize("mode", [
    "normal", "inspect", "g0_fixture_run", "g0_fullpath_candidate",
    "g0_fullpath_worker",
])
def test_wrong_mode_does_not_touch_legacy(monkeypatch, tmp_path, mode):
    setup_drafts(monkeypatch, tmp_path)
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", mode)
    calls = forbid_external(monkeypatch)
    assert_fail_start()
    assert calls == []


@pytest.mark.parametrize("flag", runtime_main._PCP_LOCAL_FLAGS)
def test_flag_only_cannot_activate_mode(monkeypatch, tmp_path, flag):
    setup_drafts(monkeypatch, tmp_path)
    monkeypatch.setenv(flag, "owner-approved")
    calls = forbid_external(monkeypatch)
    assert_fail_start()
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    assert_fail_start()
    assert calls == []


@pytest.mark.parametrize("mutate", [
    lambda p,b: p["projects"].update({"chonhac": {}}),
    lambda p,b: p["projects"].update({"historical-fixture": {}}),
    lambda p,b: p["projects"]["pcp-local"].update(path="/owner/old/jobs"),
    lambda p,b: p["projects"]["pcp-local"].update(registration_status="approved"),
    lambda p,b: p["projects"]["pcp-local"].update(repository="other/repo"),
    lambda p,b: p["projects"]["pcp-local"].update(base_branch="release"),
    lambda p,b: p["projects"]["pcp-local"]["autonomy"].update(allow_commit=True),
    lambda p,b: p["projects"]["pcp-local"]["autonomy"].update(allow_create_pr=True),
    lambda p,b: p["projects"]["pcp-local"]["autonomy"].update(allow_production_deploy=True),
    lambda p,b: p["projects"]["pcp-local"]["runtime"].update(workspace_mode="direct"),
    lambda p,b: p["projects"]["pcp-local"]["runtime"].update(developer_permission_mode="trusted_project"),
    lambda p,b: p["projects"]["pcp-local"]["ddev"].update(enabled=True),
    lambda p,b: b["projects"].update({"chonhac": {}}),
    lambda p,b: b["projects"]["pcp-local"].update(active_revision="fake"),
    lambda p,b: b["projects"]["pcp-local"].update(revisions={"fake": {"status": "approved"}}),
    lambda p,b: b["projects"]["pcp-local"].pop("active_revision"),
    lambda p,b: b["projects"]["pcp-local"].pop("revisions"),
    lambda p,b: b.update(version=2),
])
def test_draft_promotion_or_cross_project_injection_denied(monkeypatch, tmp_path, mutate):
    project, baseline, p, b = setup_drafts(monkeypatch, tmp_path)
    p, b = deepcopy(p), deepcopy(b)
    mutate(p, b)
    project.write_text(yaml.safe_dump(p), encoding="utf-8")
    baseline.write_text(yaml.safe_dump(b), encoding="utf-8")
    calls = forbid_external(monkeypatch)
    assert_fail_start()
    assert calls == []


@pytest.mark.parametrize("fault", [
    "missing_project", "missing_baseline", "bad_project", "bad_baseline",
    "symlink", "different_parent", "wrong_name", "relative",
])
def test_broken_or_foreign_files_denied(monkeypatch, tmp_path, fault):
    project, baseline, _, _ = setup_drafts(monkeypatch, tmp_path)
    if fault == "missing_project":
        project.unlink()
    if fault == "missing_baseline":
        baseline.unlink()
    if fault == "bad_project":
        project.write_text("version: [\n", encoding="utf-8")
    if fault == "bad_baseline":
        baseline.write_text("version: [\n", encoding="utf-8")
    if fault == "symlink":
        copied = tmp_path / "not-checked.yml"
        project.rename(copied)
        project.symlink_to(copied)
    if fault == "different_parent":
        other = tmp_path / "other"
        other.mkdir()
        moved = other / baseline.name
        baseline.rename(moved)
        monkeypatch.setenv("PROJECT_BASELINES_FILE", str(moved))
    if fault == "wrong_name":
        monkeypatch.setenv("PROJECTS_FILE", str(baseline))
    if fault == "relative":
        monkeypatch.setenv("PROJECTS_FILE", project.name)
    calls = forbid_external(monkeypatch)
    assert_fail_start()
    assert calls == []


def test_direct_legacy_control_helpers_denied(monkeypatch, tmp_path):
    setup_drafts(monkeypatch, tmp_path)
    calls = forbid_external(monkeypatch)
    async def run():
        for function in (
            runtime_main._start_legacy_control_plane,
            runtime_main._stop_legacy_control_plane,
        ):
            with pytest.raises(RuntimeError, match="PCP-local"):
                await function()
    asyncio.run(run())
    assert calls == []


def test_protected_paths_are_registered():
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    for path in (
        "config/projects.pcp-local.yml",
        "config/project-baselines.pcp-local.yml",
        "services/runtime/app/main.py",
    ):
        assert policy["classify_path"](path) == "protected"
