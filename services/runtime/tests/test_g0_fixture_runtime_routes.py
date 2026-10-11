"""G0 Runtime mode has no legacy engine, PM scheduler or bridge startup.

Tests use a fake one-job runner; no real model, provider, Docker, DB or GitHub.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main


G0ID = "a" * 32


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "g0_fixture_run")
    monkeypatch.setenv("RUNTIME_API_TOKEN", "g0-test-token")
    lifecycle = []

    monkeypatch.setattr(
        main, "harden_runtime_process_secret_boundary",
        lambda: lifecycle.append("harden"),
    )
    def fake_prepare_startup():
        lifecycle.append("g0_prepare_startup")
    monkeypatch.setattr(main.g0_fixture_runner, "prepare_startup", fake_prepare_startup)

    async def forbidden(*args, **kwargs):
        pytest.fail("Normal Runtime engine, orchestration, bridge or publisher activated")
    for component in (
        main.engine,
        main.plan_orchestrator,
        main.progress_publisher,
        main.job_status_publisher,
    ):
        monkeypatch.setattr(component, "start", forbidden)
        monkeypatch.setattr(component, "stop", forbidden)

    async def health():
        return True
    monkeypatch.setattr(main.engine.router, "health", health)
    monkeypatch.setattr(main.engine.ddev, "health", health)
    return lifecycle


def test_g0_exact_http_surface_ignores_unscoped_and_future_routes():
    assert main.g0_fixture_allowed_route("GET", "/health")
    assert main.g0_fixture_allowed_route("POST", "/v1/g0-fixture/prepare")
    assert main.g0_fixture_allowed_route("GET", "/v1/g0-fixture/jobs/" + G0ID)
    assert main.g0_fixture_allowed_route("POST", "/v1/g0-fixture/jobs/" + G0ID + "/execute")
    assert main.g0_fixture_allowed_route("POST", "/v1/g0-fixture/jobs/" + G0ID + "/deliver")
    for method, uri in (
        ("POST", "/v1/jobs"), ("GET", "/v1/jobs"),
        ("POST", "/v1/pm-bridge/poll"), ("GET", "/v1/dashboard"),
        ("POST", "/v1/orchestrator/tick"), ("POST", "/v1/intake"),
        ("POST", "/v1/g0-fixture/jobs/" + G0ID + "/cancel"),
        ("GET", "/v1/g0-fixture/jobs/" + G0ID + "/execute"),
        ("POST", "/v1/g0-fixture/jobs/abc/execute"),
        ("GET", "/v1/g0-fixture/prepare"), ("GET", "/docs"),
        ("GET", "/openapi.json"),
    ):
        assert not main.g0_fixture_allowed_route(method, uri)


def test_g0_scoped_startup_bypasses_legacy_services(runtime):
    async def exercise():
        async with main.lifespan(main.app):
            assert runtime == ["harden", "g0_prepare_startup"]
    asyncio.run(exercise())


def test_g0_scoped_runtime_http_blocks_every_unscoped_endpoint(runtime):
    with TestClient(main.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "degraded"
        assert client.get("/openapi.json").status_code == 503
        for method, path in (
            ("GET", "/v1/jobs"),
            ("POST", "/v1/jobs"),
            ("GET", "/v1/dashboard"),
            ("POST", "/v1/pm-bridge/poll"),
            ("POST", "/v1/orchestrator/tick"),
            ("POST", "/v1/notifications/42/ack"),
        ):
            answer = client.request(method, path)
            assert answer.status_code == 503, (method, path, answer.text)
        noauth = client.post("/v1/g0-fixture/prepare")
        assert noauth.status_code == 401
        invalid = client.get("/v1/g0-fixture/jobs/" + "ab")
        assert invalid.status_code == 503
    assert runtime == ["harden", "g0_prepare_startup"]


def test_g0_http_job_routes_call_only_explicit_scoped_runner(runtime, monkeypatch):
    calls = []
    async def prepare():
        calls.append("prepare")
        return {"id": G0ID, "project_id": "pcp-g0-drupal-fixture",
                "status": "queued", "source_commit": "s" * 40, "result": None}
    async def execute(job_id):
        calls.append(("execute", job_id))
        return {"id": job_id, "project_id": "pcp-g0-drupal-fixture",
                "status": "waiting_human", "source_commit": "s" * 40,
                "result": {"stage": "awaiting_fixture_only_delivery"}}
    async def deliver(job_id):
        calls.append(("deliver", job_id))
        return {"id": job_id, "project_id": "pcp-g0-drupal-fixture",
                "status": "delivering", "source_commit": "s" * 40,
                "result": {"stage": "awaiting_independent_ci_and_pm_review"}}
    def current(job_id):
        calls.append(("status", job_id))
        return {"id": job_id, "project_id": "pcp-g0-drupal-fixture",
                "status": "delivering", "source_commit": "s" * 40,
                "result": {"stage": "awaiting_independent_ci_and_pm_review"}}
    monkeypatch.setattr(main.g0_fixture_runner, "prepare", prepare)
    monkeypatch.setattr(main.g0_fixture_runner, "execute", execute)
    monkeypatch.setattr(main.g0_fixture_runner, "deliver", deliver)
    monkeypatch.setattr(main.g0_fixture_runner, "current", current)
    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer g0-test-token"}
        assert client.post("/v1/g0-fixture/prepare", headers=headers).status_code == 200
        assert client.post("/v1/g0-fixture/jobs/" + G0ID + "/execute",
                           headers=headers).status_code == 200
        assert client.get("/v1/g0-fixture/jobs/" + G0ID,
                          headers=headers).status_code == 200
        assert client.post("/v1/g0-fixture/jobs/" + G0ID + "/deliver",
                           headers=headers).status_code == 200
    assert calls == ["prepare", ("execute", G0ID), ("status", G0ID), ("deliver", G0ID)]


def test_inspection_mode_remains_health_only_even_after_g0_source(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "inspect")
    assert main.runtime_startup_mode() == "inspect"
    assert main.g0_fixture_allowed_route("POST", "/v1/g0-fixture/prepare")
    # Route pattern availability does not override the existing inspect guard.
    with TestClient(main.app) as client:
        assert client.post("/v1/g0-fixture/prepare").status_code == 503


def test_invalid_g0_mode_cannot_fallback_to_normal(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "g0_fixture_run_extra")
    with pytest.raises(RuntimeError, match="Invalid PCP_RUNTIME_STARTUP_MODE"):
        main.runtime_startup_mode()



def test_g0_routes_remain_inaccessible_from_legacy_normal_runtime(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("RUNTIME_API_TOKEN", "g0-test-token")
    with TestClient(main.app) as client:
        headers = {"Authorization": "Bearer g0-test-token"}
        assert client.post("/v1/g0-fixture/prepare", headers=headers).status_code == 403
        assert client.get("/v1/g0-fixture/jobs/" + G0ID, headers=headers).status_code == 403
        assert client.post("/v1/g0-fixture/jobs/" + G0ID + "/execute",
                           headers=headers).status_code == 403
        assert client.post("/v1/g0-fixture/jobs/" + G0ID + "/deliver",
                           headers=headers).status_code == 403
