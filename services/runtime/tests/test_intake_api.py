from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import clear_config_cache
from app.engine import RuntimeEngine
from test_intake_policy import small_hints, small_semantic
from test_pm_planning import configure as configure_planner, proposal, ticket, work_order
from test_work_order_contract import CaptureStorage, baseline_doc, configure


def request_payload(**overrides):
    return {
        "project_id": "demo", "ticket": ticket(), "bounded_direct": True,
        "semantic": small_semantic(), "repo_hints": small_hints(), **overrides,
    }


@pytest.fixture
def api(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)

    class TestStorage(CaptureStorage):
        def create(self, row):
            now = datetime.now(timezone.utc)
            super().create({**row, "created_at": now, "updated_at": now})

    storage = TestStorage()
    engine = RuntimeEngine(storage)
    enqueued = []

    async def enqueue(job_id):
        # Observe the initial INSERT, not a subsequent checkpoint update.
        enqueued.append(deepcopy(storage.created))

    engine.enqueue = enqueue
    monkeypatch.setattr(main, "storage", storage)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setenv("RUNTIME_API_TOKEN", "test-intake-token")
    client = TestClient(main.app)  # No application startup or live services.
    client.headers["Authorization"] = "Bearer test-intake-token"
    try:
        yield client, storage, engine, enqueued
    finally:
        client.close()
        clear_config_cache()


@pytest.mark.parametrize("auto_run", [True, False])
def test_direct_creates_one_job_with_atomic_evidence_and_no_plan(api, monkeypatch, auto_run):
    client, storage, engine, enqueued = api
    planner = AsyncMock(side_effect=AssertionError("Direct must not create a plan"))
    monkeypatch.setattr(main.pm_planner, "create_plan", planner)
    providers = {"provider:unavailable-test": {"healthy": False, "available": False}}
    payload = request_payload(auto_run=auto_run, provider_state=providers)
    response = client.post("/v1/intake", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "direct" and "plan" not in result
    assert result["job"]["status"] == "queued"
    assert len(storage.rows) == 1
    row = storage.get(result["job"]["id"])
    assert row["task"]["title"] == payload["ticket"]["title"]
    assert row["task"]["description"] == payload["ticket"]["description"]
    assert row["task"]["semantic"] == payload["semantic"]
    checkpoint = row["checkpoint"]
    assert checkpoint["project_baseline"]["revision"] == "v1"
    assert checkpoint["hints"] == {**payload["repo_hints"], "likely_change_types": None, "candidate_modules": None, "related_commits_found": None}
    assert checkpoint["provider_state"]["provider:unavailable-test"]["available"] is False
    assert checkpoint["canonical_intake"] == {
        "policy_version": 1, "mode": "direct", "bounded_direct": True,
        "reasons": ["bounded_direct_eligible"], "material_signals": [],
        "decomposition_required": False, "baseline_revision": "v1",
    }
    assert len(enqueued) == int(auto_run)
    if auto_run:
        assert enqueued[0]["checkpoint"]["canonical_intake"] == checkpoint["canonical_intake"]
    planner.assert_not_awaited()


@pytest.mark.parametrize("material", [False, True])
def test_planning_uses_existing_planner_and_tick_without_direct_job(api, monkeypatch, tmp_path, material):
    client, storage, engine, enqueued = api
    planner, _, plans, router, ddev, adapter = configure_planner(
        monkeypatch, tmp_path, proposal(work_order(), work_order("WO-2", dependencies=["WO-1"])),
    )
    monkeypatch.setattr(main, "pm_planner", planner)
    tick = AsyncMock()
    monkeypatch.setattr(main.plan_orchestrator, "tick", tick)
    payload = request_payload()
    if material:
        payload["semantic"].update(risk=50, ambiguity=50)
    else:
        payload.pop("semantic")
        payload.pop("repo_hints")
    response = client.post("/v1/intake", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "planning" and "job" not in result
    assert result["plan"]["status"] == "ready"
    assert result["decomposition_required"] is material
    assert len(plans.plans) == 1 and storage.rows == {} and enqueued == []
    assert ("DECOMPOSITION_REQUIRED" in adapter.calls[0]["prompt"]) is material
    if material:
        assert '"risk": 50' in adapter.calls[0]["prompt"]
    tick.assert_awaited_once()
    assert "staffing" not in result and "provider_state" not in result


def test_supervised_planning_is_accepted_and_persisted(api, monkeypatch, tmp_path):
    client, storage, _, enqueued = api
    planner, _, plans, *_ = configure_planner(
        monkeypatch,
        tmp_path,
        proposal(work_order(), work_order("WO-2", dependencies=["WO-1"])),
    )
    monkeypatch.setattr(main, "pm_planner", planner)
    tick = AsyncMock()
    monkeypatch.setattr(main.plan_orchestrator, "tick", tick)
    payload = request_payload(execution_mode="supervised")
    payload.pop("semantic")
    payload.pop("repo_hints")

    response = client.post("/v1/intake", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "planning"
    assert next(iter(plans.plans.values()))["plan"]["execution_mode"] == "supervised"
    assert storage.rows == {} and enqueued == []
    tick.assert_awaited_once()


def test_supervised_direct_classification_fails_closed_without_job_or_plan(api, monkeypatch):
    client, storage, _, enqueued = api
    planner = AsyncMock(side_effect=AssertionError("Direct classification must not be forced to planning"))
    monkeypatch.setattr(main.pm_planner, "create_plan", planner)

    response = client.post(
        "/v1/intake",
        json=request_payload(execution_mode="supervised"),
    )

    assert response.status_code == 422
    assert "requires planning intake" in response.json()["detail"]
    assert storage.rows == {} and enqueued == []
    planner.assert_not_awaited()


def test_ordinary_plans_api_still_accepts_single_work_order(api, monkeypatch, tmp_path):
    client, *_ = api
    planner, request, *_ = configure_planner(monkeypatch, tmp_path, proposal(work_order()))
    monkeypatch.setattr(main, "pm_planner", planner)
    tick = AsyncMock()
    monkeypatch.setattr(main.plan_orchestrator, "tick", tick)
    response = client.post("/v1/plans", json={"project_id": "demo", "ticket": ticket()})
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert len(response.json()["plan"]["work_orders"]) == 1
    tick.assert_awaited_once()


def test_ordinary_jobs_api_keeps_manual_contract(api):
    client, storage, _, enqueued = api
    response = client.post("/v1/jobs", json={
        "project_id": "demo", "task": {"title": "Explicit manual job"}, "auto_run": False,
    })
    assert response.status_code == 200
    assert len(storage.rows) == 1 and enqueued == []
    assert "canonical_intake" not in storage.created["checkpoint"]


@pytest.mark.parametrize("bounded_direct", [True, False])
@pytest.mark.parametrize("revision", [None, "unknown", "draft"])
def test_missing_or_unapproved_baseline_fails_before_side_effects(api, monkeypatch, tmp_path, bounded_direct, revision):
    client, storage, _, enqueued = api
    baselines = baseline_doc()
    project = baselines["projects"]["demo"]
    project["active_revision"] = None
    project["revisions"] = {"draft": {**project["revisions"]["v1"], "status": "draft"}}
    configure(monkeypatch, tmp_path, baselines=baselines)
    response = client.post("/v1/intake", json=request_payload(
        bounded_direct=bounded_direct, baseline_revision=revision,
    ))
    assert response.status_code == 422
    assert storage.rows == {} and enqueued == []


@pytest.mark.parametrize("field,value", [
    ("commands", ["touch /tmp/unauthorized"]), ("workspace", "/tmp/arbitrary"),
    ("workspace_mode", "direct"), ("model", "chosen-model"), ("provider", "chosen-provider"),
    ("github_token", "secret"), ("allow_merge", True), ("allow_production_deploy", True),
    ("_intake_decision", {}), ("decomposition_required", False), ("dry_run", True),
])
def test_canonical_request_rejects_capability_fields(api, field, value):
    client, storage, *_ = api
    response = client.post("/v1/intake", json=request_payload(**{field: value}))
    assert response.status_code == 422
    assert storage.rows == {}


@pytest.mark.parametrize("field", ["semantic", "repo_hints"])
def test_nested_signal_extras_cannot_supply_authority(api, field):
    client, *_ = api
    payload = request_payload()
    payload[field]["commands"] = ["arbitrary"]
    assert client.post("/v1/intake", json=payload).status_code == 422


def test_intake_requires_authentication(api):
    client, storage, *_ = api
    client.headers.pop("Authorization")
    assert client.post("/v1/intake", json=request_payload()).status_code == 401
    assert storage.rows == {}


def test_ticket_text_never_changes_classification(api):
    client, *_ = api
    payload = request_payload(auto_run=False)
    payload["ticket"]["description"] = "Security schema production large complex multi-service: merely prose."
    response = client.post("/v1/intake", json=payload)
    assert response.json()["mode"] == "direct"
