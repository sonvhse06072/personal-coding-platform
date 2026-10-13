"""F2 C3A: exact repo-only Executor source; no real Git, provider or Docker."""
from __future__ import annotations

from io import StringIO
from pathlib import Path
import builtins

import pytest
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = "pcp-g0-fullpath-fixture"
SEED_CONFIG = ROOT / "config/fullpath-candidate/projects.yml"
REPOSITORY = "sonvhse06072/pcp-g0-fullpath-fixture"


@pytest.fixture
def f2_gitonly(monkeypatch):
    for name, value in main.F2_PARKED_EXECUTOR_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PCP_F2_GIT_ONLY_ENABLED", "owner-approved")
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "synthetic-f2-internal")
    monkeypatch.setenv("GITHUB_DELIVERY_TOKEN", "synthetic-repo-scoped")
    for name in (
        "PCP_G0_EXECUTION_ENABLED", "PCP_G0_DELIVERY_ENABLED",
        "ANTIGRAVITY_BRIDGE_TOKEN", "PCP_FULLPATH_OPERATIONAL_ACTIVATION",
    ):
        monkeypatch.delenv(name, raising=False)

    # The approved candidate file stays OFF on disk. Only the test copy is active.
    cfg = yaml.safe_load(SEED_CONFIG.read_text(encoding="utf-8"))
    enabled = cfg["projects"][FIXTURE]["autonomy"]
    enabled["allow_commit"] = True
    enabled["allow_push_ai_branch"] = True
    enabled["allow_create_pr"] = True
    original_open = builtins.open

    def open_registry(file, *args, **kwargs):
        if str(file) == main.F2_PARKED_EXECUTOR_ENV["PROJECTS_FILE"]:
            return StringIO(yaml.safe_dump(cfg))
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", open_registry)
    real_exists = Path.exists
    monkeypatch.setattr(
        main.Path, "exists",
        lambda self: False if str(self) == "/var/run/docker.sock"
        else real_exists(self),
    )
    monkeypatch.setattr(
        main, "_require_f2_source_repository", lambda cfg: None,
    )
    assert main._f2_git_only_scoped() is True
    assert main._f2_parked_executor_scope() is False
    return cfg


def test_f2_source_registry_stays_parked_until_both_activation_and_policy(monkeypatch):
    for name, value in main.F2_PARKED_EXECUTOR_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PCP_F2_GIT_ONLY_ENABLED", "owner-approved")
    # CI runners legitimately have a Docker socket. Test the separately
    # guarded registry policy directly without connecting to that socket.
    source = yaml.safe_load(SEED_CONFIG.read_text(encoding="utf-8"))
    with pytest.raises(HTTPException) as error:
        main._validate_f2_registry(source["projects"])
    assert error.value.status_code == 503
    assert "separately activated" in error.value.detail


@pytest.mark.parametrize("wrong", [
    {"kind": "foreign"}, {"kind": "bad_branch"}, {"kind": "ddev"},
    {"kind": "direct"}, {"kind": "production"}, {"kind": "weak_autonomy"},
])
def test_active_f2_rejects_broadened_registry(f2_gitonly, monkeypatch, wrong):
    cfg = f2_gitonly
    entry = cfg["projects"][FIXTURE]
    if wrong["kind"] == "foreign":
        cfg["projects"]["chonhac"] = dict(entry)
    elif wrong["kind"] == "bad_branch":
        entry["base_branch"] = "main"
    elif wrong["kind"] == "ddev":
        entry["ddev"]["enabled"] = True
    elif wrong["kind"] == "direct":
        entry["runtime"]["workspace_mode"] = "direct"
    elif wrong["kind"] == "production":
        entry["autonomy"]["allow_production_deploy"] = True
    elif wrong["kind"] == "weak_autonomy":
        entry["autonomy"]["allow_create_pr"] = False
    with pytest.raises(HTTPException) as error:
        main.load_projects()
    assert error.value.status_code == 503
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 503


@pytest.mark.parametrize("bad", ["true", "1", "pending", "owner-approval"])
def test_invalid_activation_flag_fails_closed(f2_gitonly, monkeypatch, bad):
    monkeypatch.setenv("PCP_F2_GIT_ONLY_ENABLED", bad)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/v1/workspaces").status_code == 503


def test_f2_rejects_host_socket_and_legacy_provider_flags(f2_gitonly, monkeypatch):
    monkeypatch.setattr(
        main.Path, "exists",
        lambda self: str(self) == "/var/run/docker.sock",
    )
    with pytest.raises(HTTPException, match="Docker socket"):
        main._f2_git_only_scoped()
    monkeypatch.setattr(main.Path, "exists", lambda self: False)
    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "foreign-provider-secret")
    with pytest.raises(HTTPException, match="legacy activation"):
        main._f2_git_only_scoped()


def test_f2_http_only_git_surface_and_no_ddev_probe(f2_gitonly, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("F2 route attempted forbidden Docker/DDEV/Git operation")
    monkeypatch.setattr(main.subprocess, "run", forbidden)
    monkeypatch.setattr(main, "cancel_active", forbidden)
    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer synthetic-f2-internal"}
        ok = client.get("/health")
        assert ok.status_code == 200
        assert ok.json()["ddev"] == "DISABLED"
        assert ok.json()["docker"] == "not_probed"
        assert ok.json()["active_jobs"] == 0
        for method, path in (
            ("GET", "/docs"),
            ("GET", "/openapi.json"),
            ("GET", "/v1/project-state"),
            ("POST", "/v1/cancel"),
            ("POST", "/v1/phase"),
            ("POST", "/v1/preview/start"),
            ("POST", "/v1/direct/sync-base"),
            ("POST", "/v1/workspaces/orphan-resources"),
            ("DELETE", "/v1/workspaces"),
            ("POST", "/v1/github/pm-bridge/managed-comment"),
            ("POST", "/v1/github/pm-bridge/pulls/1/merge"),
            ("POST", "/v1/foreign"),
        ):
            assert client.request(method, path, headers=headers).status_code == 403
        # Authorized route exists but still requires internal auth.
        assert client.get("/v1/github/ci").status_code == 401
        assert client.get("/v1/github/ci", headers=headers).status_code == 422


def test_f2_private_handlers_require_exact_fixture_project_before_git(f2_gitonly):
    with pytest.raises(HTTPException) as error:
        main.project("chonhac")
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        main.project("pcp-g0-drupal-fixture")
    assert error.value.status_code == 403


def test_f2_workspace_wrong_seed_rejected_before_git(f2_gitonly, monkeypatch):
    monkeypatch.setattr(main, "git", lambda *_args, **_kwargs:
        pytest.fail("Wrong source seed must not run Git"))
    payload = main.WorkspaceRequest(
        job_id="a" * 32, project_id=FIXTURE,
        ref="b" * 40, workspace_mode="isolated_clone",
    )
    with pytest.raises(HTTPException, match="exact pinned seed"):
        main.create_workspace(payload)


def test_github_context_is_exact_repo_scoped(f2_gitonly, monkeypatch):
    monkeypatch.setattr(
        main, "_source_origin",
        lambda _cfg: (main.F2_FIXTURE_PATH,
                      "https://github.com/sonvhse06072/pcp-g0-fullpath-fixture.git"),
    )
    delivery, slug = main._github_context(main.project(FIXTURE))
    assert slug == REPOSITORY
    assert delivery.repository_scope == REPOSITORY
    assert delivery.configured
    monkeypatch.setattr(
        main, "_source_origin",
        lambda _cfg: (main.F2_FIXTURE_PATH,
                      "https://github.com/sonvhse06072/chonhac.git"),
    )
    with pytest.raises(HTTPException, match="outside fixture repository"):
        main._github_context(main.project(FIXTURE))


def test_f2_source_seed_origin_checks_exact_checkout(f2_gitonly, monkeypatch):
    monkeypatch.undo()
    cfg = yaml.safe_load(SEED_CONFIG.read_text(encoding="utf-8"))["projects"][FIXTURE]
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/fullpath/sources")
    monkeypatch.setattr(
        main, "_configured_project_path", lambda _: main.F2_FIXTURE_PATH
    )
    monkeypatch.setattr(main, "git", lambda *_args: main.F2_FIXTURE_SOURCE)
    monkeypatch.setattr(
        main, "remote_origin",
        lambda _: "https://github.com/sonvhse06072/pcp-g0-fullpath-fixture.git"
    )
    main._require_f2_source_repository(cfg)
    monkeypatch.setattr(
        main, "remote_origin",
        lambda _: "https://github.com/sonvhse06072/chonhac.git"
    )
    with pytest.raises(HTTPException, match="outside exact fixture"):
        main._require_f2_source_repository(cfg)


def test_f2_delivery_guard_does_not_call_network_and_rejects_foreign_branches(f2_gitonly):
    cfg = f2_gitonly["projects"][FIXTURE]
    main._require_f2_delivery_contract(
        cfg, job_id="a"*32, branch="ai/" + "a"*12,
        source_commit=main.F2_FIXTURE_SOURCE,
    )
    with pytest.raises(HTTPException, match="exact job"):
        main._require_f2_delivery_contract(
            cfg, job_id="a"*32, branch="ai/foreign",
        )


def test_f2_only_test_source_changes_permitted(f2_gitonly, monkeypatch, tmp_path):
    touched = []
    def fake_git(_repo, *argv, **kwargs):
        touched.append(argv)
        if argv[0] == "status":
            return ""
        if argv[0] == "diff":
            return "\n".join(sorted(main.F2_ALLOWED_CHANGED_FILES))
        raise AssertionError(argv)
    monkeypatch.setattr(main, "git", fake_git)
    main._verify_f2_delivered_diff(tmp_path, main.F2_FIXTURE_SOURCE, "b"*40)
    assert all("push" not in args for args in touched)

    monkeypatch.setattr(
        main, "git",
        lambda _repo, *args, **kwargs:
            "" if args[0]=="status" else "composer.lock",
    )
    with pytest.raises(HTTPException, match="unapproved"):
        main._verify_f2_delivered_diff(tmp_path, main.F2_FIXTURE_SOURCE, "b"*40)
