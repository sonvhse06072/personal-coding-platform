"""Future F2 Executor is recognized as a *parked* identity, never activated.

No real Docker, DDEV, network, GitHub credentials or fixture operations.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main


ROOT = Path(__file__).resolve().parents[3]
F2_COMPOSE = ROOT / "deploy/fullpath/compose.source-only.yml"


@pytest.fixture
def f2_env(monkeypatch):
    for key, value in main.F2_PARKED_EXECUTOR_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PLATFORM_INTERNAL_TOKEN", "synthetic-f2-token")
    assert main._f2_parked_executor_scope() is True


def _forbidden(*_args, **_kwargs):
    raise AssertionError("PARKED F2 must never call a host or GitHub function")


def test_parked_f2_scope_matches_exact_inert_compose_source(f2_env):
    with F2_COMPOSE.open(encoding="utf-8") as stream:
        compose = yaml.safe_load(stream)
    executor = compose["services"]["fullpath-executor"]
    assert executor["entrypoint"] == ["/bin/false"]
    assert executor["profiles"] == ["owner-gated-f2-source"]
    assert executor["networks"] == ["fullpath-private"]
    assert compose["networks"]["fullpath-private"]["internal"] is True
    assert "GITHUB_DELIVERY_TOKEN" not in executor["environment"]
    for key, value in main.F2_PARKED_EXECUTOR_ENV.items():
        assert executor["environment"][key] == value
    assert not any(
        "/var/run/docker.sock" in str(mount)
        for mount in executor["volumes"]
    )


def test_no_f2_http_route_dispatches_or_exposes_openapi(
    f2_env, monkeypatch,
):
    monkeypatch.setattr(main.subprocess, "run", _forbidden)
    monkeypatch.setattr(main, "cancel_active", _forbidden)
    monkeypatch.setattr(main, "git", _forbidden)
    with TestClient(main.app) as client:
        auth = {"Authorization": "Bearer synthetic-f2-token"}
        for method, path in (
            ("GET", "/health"),
            ("GET", "/docs"),
            ("GET", "/openapi.json"),
            ("POST", "/v1/cancel"),
            ("POST", "/v1/workspaces"),
            ("GET", "/v1/project-state"),
            ("POST", "/v1/publish-branch"),
            ("POST", "/v1/github/pull-request"),
            ("GET", "/v1/github/ci"),
            ("POST", "/v1/pm-bridge/github/pulls/42/merge"),
            ("POST", "/v1/workspaces/orphan-resources"),
            ("GET", "/v1/unknown-future-endpoint"),
        ):
            response = client.request(method, path, headers=auth)
            assert response.status_code == 503, (
                method, path, response.status_code, response.text
            )


@pytest.mark.parametrize("key", list(main.F2_PARKED_EXECUTOR_ENV))
def test_one_changed_f2_identity_marker_fails_closed(
    f2_env, monkeypatch, key,
):
    monkeypatch.setenv(key, "/untrusted-or-legacy")
    with pytest.raises(HTTPException) as exc:
        main._f2_parked_executor_scope()
    assert exc.value.status_code == 503
    with TestClient(main.app) as client:
        assert client.get("/openapi.json").status_code == 503
        assert client.post("/v1/cancel").status_code == 503


@pytest.mark.parametrize("flag", [
    "PCP_G0_EXECUTION_ENABLED", "PCP_G0_DELIVERY_ENABLED",
    "PCP_F2_EXECUTION_ENABLED", "PCP_FULLPATH_OPERATIONAL_ACTIVATION",
])
def test_legacy_or_future_env_flags_cannot_unpark_f2(
    f2_env, monkeypatch, flag,
):
    monkeypatch.setenv(flag, "owner-approved")
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/v1/workspaces").status_code == 503


def test_direct_python_registry_and_health_calls_stop_before_side_effects(
    f2_env, monkeypatch,
):
    monkeypatch.setattr(main.subprocess, "run", _forbidden)
    # A successful lookup would read PROJECTS_FILE, then potentially return a
    # wider registry; the new parked path refuses before reading any file.
    original_open = open
    def reject_open(*args, **kwargs):
        raise AssertionError("F2 registry is PARKED and must not be opened")
    monkeypatch.setattr("builtins.open", reject_open)
    try:
        for func in (
            lambda: main.load_projects(),
            lambda: main.project("pcp-g0-fullpath-fixture"),
            lambda: main.project("unrelated"),
            lambda: main.health(),
        ):
            with pytest.raises(HTTPException) as exc:
                func()
            assert exc.value.status_code == 503
    finally:
        monkeypatch.setattr("builtins.open", original_open)


def test_g0_or_unscoped_default_untouched_by_f2_marker_recognition(
    monkeypatch,
):
    for key in main.F2_PARKED_EXECUTOR_ENV:
        monkeypatch.delenv(key, raising=False)
    assert main._f2_parked_executor_scope() is False
    monkeypatch.setenv("PCP_EXECUTOR_PROJECT_SCOPE", main.G0_FIXTURE_PROJECT_ID)
    monkeypatch.setenv("PROJECTS_FILE", "/g0/config/projects.yml")
    monkeypatch.setenv("CODING_PROJECTS_ROOT", "/g0/sources")
    monkeypatch.setenv("CODING_WORKSPACES_ROOT", "/g0/workspaces")
    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", "/g0/direct-disabled")
    assert main._f2_parked_executor_scope() is False
    assert main._g0_fixture_scoped() is True
