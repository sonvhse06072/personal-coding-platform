"""Negative scope tests. No Docker, DDEV, Git, model or owner data access."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main


ROOT = Path(__file__).resolve().parents[3]
PARKED_REGISTRY = ROOT / "config/g0-fixture-only/projects.yml"
FIXTURE = "pcp-g0-drupal-fixture"


@pytest.fixture
def g0(monkeypatch):
    monkeypatch.setenv("PCP_EXECUTOR_PROJECT_SCOPE", FIXTURE)
    monkeypatch.setenv("PROJECTS_FILE", str(PARKED_REGISTRY))
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "test-fixture-token")
    return monkeypatch


def _call(monkeypatch, tmp_path, transform):
    document = yaml.safe_load(PARKED_REGISTRY.read_text(encoding="utf-8"))
    transform(document)
    path = tmp_path / "scoped.yml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    monkeypatch.setenv("PROJECTS_FILE", str(path))


def test_g0_scope_rejects_legacy_project_before_touching_source(g0):
    assert list(main.load_projects()) == [FIXTURE]
    assert main.project(FIXTURE)["base_branch"] == "benchmark/pcp"
    with pytest.raises(HTTPException) as e:
        main.project("chonhac")
    assert e.value.status_code == 403


def test_fixture_api_allowlist_denies_unowned_and_future_endpoints(g0):
    allowed = main.G0_FIXTURE_API_ROUTES
    assert ("GET", "/health") in allowed
    assert allowed == frozenset({("GET", "/health")})
    for item in (
        ("POST", "/v1/cancel"),
        ("POST", "/v1/workspaces/orphan-resources"),
        ("POST", "/v1/direct/sync-base"),
        ("POST", "/v1/preview/start"),
        ("POST", "/v1/workspaces/return-to-base"),
        ("POST", "/v1/workspaces/advance-direct-source"),
        ("POST", "/v1/pm-bridge/github/managed-comment"),
        ("POST", "/v1/pm-bridge/github/pulls/42/merge"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
        ("POST", "/v1/new-future-privileged-endpoint"),
    ):
        assert item not in allowed


def test_scoped_http_denies_generic_mutation_and_pm_bridge(g0, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No process, DDEV, or Docker command may run")

    monkeypatch.setattr(main, "cancel_active", forbidden)
    monkeypatch.setattr(main, "_release_orphan_resources", forbidden)
    monkeypatch.setattr(main, "git", forbidden)

    with TestClient(main.app) as client:
        for method, path in (
            ("POST", "/v1/cancel"),
            ("POST", "/v1/workspaces/orphan-resources"),
            ("POST", "/v1/preview/start"),
            ("POST", "/v1/direct/sync-base"),
            ("GET", "/docs"),
            ("GET", "/openapi.json"),
            ("POST", "/v1/pm-bridge/github/pulls/42/merge"),
            ("POST", "/v1/unrecognized-future-route"),
        ):
            response = client.request(method, path)
            assert response.status_code == 403, (method, path, response.text)
        token = {"Authorization": "Bearer test-fixture-token"}
        other = client.get("/v1/project-state?project_id=chonhac", headers=token)
        assert other.status_code == 403
        missing = client.post("/v1/workspaces", json={
            "job_id": "job123456", "project_id": "chonhac"
        }, headers=token)
        assert missing.status_code == 403
        # Scope alone cannot enable a fixture workspace or any DDEV phase.
        fixture_workspace = client.post("/v1/workspaces", json={
            "job_id": "job123456", "project_id": FIXTURE
        }, headers=token)
        assert fixture_workspace.status_code == 403
        phase = client.post("/v1/phase", json={
            "job_id": "job123456", "project_id": FIXTURE,
            "workspace": "/nonexistent/g0", "phase": "preflight"
        }, headers=token)
        assert phase.status_code == 403
        assert client.get("/v1/project-state?project_id=" + FIXTURE,
                          headers=token).status_code == 403


@pytest.mark.parametrize("transform", [
    lambda d: d["projects"].update({"chonhac": {
        "path": "/never-use", "base_branch": "main"
    }}),
    lambda d: d["projects"][FIXTURE].update(base_branch="main"),
    lambda d: d["projects"][FIXTURE].update(path="/home/sonvh/chonhac"),
    lambda d: d["projects"][FIXTURE]["runtime"].update(workspace_mode="direct"),
    lambda d: d["projects"][FIXTURE]["runtime"].update(exclusive_project_lease=True),
    lambda d: d["projects"].clear(),
])
def test_broadened_or_wrong_registry_blocks_every_http_route(
    g0, tmp_path, transform
):
    _call(g0, tmp_path, transform)
    with pytest.raises(HTTPException) as e:
        main.project(FIXTURE)
    assert e.value.status_code == 503
    with TestClient(main.app) as client:
        for method, path in (
            ("GET", "/health"),
            ("POST", "/v1/workspaces"),
            ("GET", "/v1/project-state?project_id=" + FIXTURE),
        ):
            response = client.request(method, path)
            assert response.status_code == 503


def test_scoped_parked_health_has_no_host_tool_probes(g0, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("PARKED health cannot invoke Docker, DDEV or Buildx")

    monkeypatch.setattr(main.subprocess, "run", forbidden)
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["ddev"] == "PARKED"
    assert body["docker"] == "not_probed"
    assert body["buildx"] == "not_probed"
    assert body["github_delivery_configured"] is False


def test_scoped_health_registry_check_fails_before_any_docker_probe(g0, tmp_path, monkeypatch):
    broken = tmp_path / "broken.yml"
    broken.write_text("projects: [not, a, mapping]\n", encoding="utf-8")
    monkeypatch.setenv("PROJECTS_FILE", str(broken))

    def forbidden(*args, **kwargs):
        raise AssertionError("Health must not reach subprocess when registry is invalid")

    monkeypatch.setattr(main.subprocess, "run", forbidden)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 503


@pytest.mark.parametrize("value", ["unknown", "chonhac", "g0-fixture", " "])
def test_malformed_executor_scope_fails_closed(monkeypatch, value):
    monkeypatch.setenv("PCP_EXECUTOR_PROJECT_SCOPE", value)
    with TestClient(main.app) as client:
        assert client.get("/openapi.json").status_code == 503


def test_default_executor_behavior_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.delenv("PCP_EXECUTOR_PROJECT_SCOPE", raising=False)
    registry = yaml.safe_load(PARKED_REGISTRY.read_text(encoding="utf-8"))
    registry["projects"]["example-project"] = {
        "path": "/synthetic", "base_branch": "main"
    }
    path = tmp_path / "legacy.yml"
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    monkeypatch.setenv("PROJECTS_FILE", str(path))
    assert main.project("example-project")["base_branch"] == "main"
    with TestClient(main.app) as client:
        assert client.get("/openapi.json").status_code == 200



def _g0_activation_test_env(monkeypatch):
    """No real Docker socket or fixture filesystem access from tests."""
    monkeypatch.setenv("PCP_EXECUTOR_PROJECT_SCOPE", FIXTURE)
    monkeypatch.setenv("PROJECTS_FILE", str(PARKED_REGISTRY))
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "test-fixture-token")
    monkeypatch.setenv("PCP_G0_EXECUTION_ENABLED", "owner-approved")
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/g0/sources")
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", "/g0/workspaces")
    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", "/g0/direct-disabled")
    real_exists = Path.exists
    monkeypatch.setattr(main.Path, "exists",
                        lambda self: False if str(self) == "/var/run/docker.sock"
                        else real_exists(self))


def test_g0_workspace_api_optin_remains_exact_and_legacy_still_forbidden(monkeypatch):
    _g0_activation_test_env(monkeypatch)
    assert main._g0_fixture_execution_enabled()
    assert main._g0_fixture_delivery_enabled() is False
    with TestClient(main.app) as client:
        auth = {"Authorization": "Bearer test-fixture-token"}
        assert client.post("/v1/cancel", headers=auth).status_code == 403
        assert client.post("/v1/workspaces/orphan-resources", headers=auth).status_code == 403
        assert client.post("/v1/pm-bridge/github/pulls/42/merge",
                           headers=auth).status_code == 403
        assert client.post("/v1/workspaces",
                           json={"job_id": "f" * 32, "project_id": "chonhac"},
                           headers=auth).status_code == 403
        # Invalid ref is checked *before* source Git or workspace mutation.
        wrong = client.post("/v1/workspaces", json={
            "job_id": "a" * 32, "project_id": FIXTURE,
            "ref": "main", "workspace_mode": "isolated_clone",
        }, headers=auth)
        assert wrong.status_code == 403
        assert "frozen" in wrong.json()["detail"]


@pytest.mark.parametrize("flag", ["yes", "true", "1", "chonhac"])
def test_invalid_g0_activation_flag_fails_closed(monkeypatch, flag):
    _g0_activation_test_env(monkeypatch)
    monkeypatch.setenv("PCP_G0_EXECUTION_ENABLED", flag)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/v1/workspaces", json={
            "job_id": "a" * 32, "project_id": FIXTURE,
            "ref": main.G0_SOURCE_COMMIT,
        }).status_code == 503


def test_g0_activation_refuses_host_socket_or_broadened_mounts(monkeypatch):
    _g0_activation_test_env(monkeypatch)
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/home/sonvh")
    with pytest.raises(HTTPException) as exc:
        main._g0_fixture_execution_enabled()
    assert exc.value.status_code == 503
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/g0/sources")
    monkeypatch.setattr(main.Path, "exists",
                        lambda self: str(self) == "/var/run/docker.sock")
    with pytest.raises(HTTPException) as exc:
        main._g0_fixture_execution_enabled()
    assert exc.value.status_code == 503


def test_g0_exact_fixture_source_repo_and_seed_gate(monkeypatch):
    _g0_activation_test_env(monkeypatch)
    cfg = main.project(FIXTURE)
    monkeypatch.setattr(main, "_configured_project_path", lambda *a: main.G0_SOURCE_PATH)
    monkeypatch.setattr(main, "git", lambda *a, **k: main.G0_SOURCE_COMMIT)
    monkeypatch.setattr(main, "remote_origin",
                        lambda *a: "https://github.com/sonvhse06072/pcp-g0-drupal-fixture.git")
    main._require_g0_source_repository(cfg)
    monkeypatch.setattr(main, "remote_origin",
                        lambda *a: "https://github.com/sonvhse06072/chonhac.git")
    with pytest.raises(HTTPException, match="exact private fixture repository"):
        main._require_g0_source_repository(cfg)


def test_g0_delivery_is_disabled_without_separate_permission(monkeypatch):
    _g0_activation_test_env(monkeypatch)
    assert main._g0_fixture_execution_enabled()
    assert not main._g0_fixture_delivery_enabled()
    with TestClient(main.app) as client:
        auth = {"Authorization": "Bearer test-fixture-token"}
        payload = {
            "job_id": "a" * 32, "project_id": FIXTURE,
            "workspace": "/g0/workspaces/" + "a" * 32,
            "branch": "ai/" + "a" * 12,
            "source_commit": main.G0_SOURCE_COMMIT,
            "expected_commit": "b" * 40,
        }
        assert client.post("/v1/publish-branch", json=payload, headers=auth).status_code == 403
        assert client.post("/v1/github/pull-request", json={
            "job_id": "a" * 32, "project_id": FIXTURE,
            "branch": "ai/" + "a" * 12,
            "expected_commit": "b" * 40, "title": "[G0D-T01] test",
        }, headers=auth).status_code == 403

    monkeypatch.setenv("PCP_G0_DELIVERY_ENABLED", "owner-approved")
    # The route may now be considered, but delivery has extra **fixture repo**
    # and exact job+branch checks, *not* a generic GitHub credential path.
    cfg = main.project(FIXTURE)
    monkeypatch.setattr(main, "_require_g0_source_repository", lambda *a: None)
    main._require_g0_delivery_contract(
        cfg, job_id="a" * 32, branch="ai/" + "a" * 12,
        source_commit=main.G0_SOURCE_COMMIT,
    )
    with pytest.raises(HTTPException, match="match the owning job"):
        main._require_g0_delivery_contract(
            cfg, job_id="a" * 32, branch="ai/foreign",
            source_commit=main.G0_SOURCE_COMMIT,
        )
    with pytest.raises(HTTPException, match="frozen seed"):
        main._require_g0_delivery_contract(
            cfg, job_id="a" * 32, branch="ai/" + "a" * 12,
            source_commit="b" * 40,
        )



def test_g0_privileged_delivery_rechecks_exact_committed_diff(monkeypatch, tmp_path):
    allowed = "\n".join(sorted(main.G0_ALLOWED_CHANGED_FILES))
    calls = []
    def fake_git(repo, *argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ("status", "--porcelain"):
            return ""
        if argv[:2] == ("diff", "--name-only"):
            return allowed
        raise AssertionError(argv)
    monkeypatch.setattr(main, "git", fake_git)
    main._verify_g0_delivered_diff(tmp_path, main.G0_SOURCE_COMMIT, "b" * 40)
    assert ("diff", "--name-only", main.G0_SOURCE_COMMIT, "b" * 40) in calls
    assert all("push" not in cmd for cmd in calls)


def test_g0_privileged_delivery_rejects_changes_outside_frozen_files(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        main, "git", lambda _repo, *argv, **kwargs:
        "composer.lock" if "diff" in argv else ""
    )
    with pytest.raises(HTTPException, match="only the frozen code and test changes"):
        main._verify_g0_delivered_diff(
            tmp_path, main.G0_SOURCE_COMMIT, "b" * 40,
        )
    monkeypatch.setattr(
        main, "git", lambda _repo, *argv, **kwargs:
        " M generated.txt" if "status" in argv else ""
    )
    with pytest.raises(HTTPException, match="must be clean"):
        main._verify_g0_delivered_diff(
            tmp_path, main.G0_SOURCE_COMMIT, "b" * 40,
        )
    with pytest.raises(HTTPException, match="source/commit identity invalid"):
        main._verify_g0_delivered_diff(tmp_path, "a" * 40, "b" * 40)
