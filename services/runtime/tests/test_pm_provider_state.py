from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app import pm_planning
from app.baseline import BaselineReferences, ProjectBaseline, SourceReference
from app.pm_planning import PMPlanCreateRequest, PMPlanner


class FakeStorage:
    def __init__(self) -> None:
        self.plans: dict[str, dict] = {}

    def create_execution_plan(self, row: dict) -> None:
        now = datetime.now(timezone.utc)
        self.plans[row["id"]] = {**row, "created_at": now, "updated_at": now}

    def update_execution_plan(self, plan_id: str, **fields) -> None:
        self.plans[plan_id].update(fields)
        self.plans[plan_id]["updated_at"] = datetime.now(timezone.utc)

    def get_execution_plan(self, plan_id: str):
        return self.plans.get(plan_id)


class AvailabilityAwareRouter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def staff(self, payload: dict) -> dict:
        self.calls.append(payload)
        codex = payload["provider_state"].get("codex_plus", {})
        choice_id = "antigravity_free" if codex.get("available") is False else "codex_plus"
        return {
            "request_id": payload["request_id"],
            "project_id": payload["project_id"],
            "role": "product_manager",
            "profile": payload["profile"],
            "choice": {
                "id": choice_id,
                "provider": "google_antigravity" if choice_id == "antigravity_free" else "openai",
                "adapter": "fake",
                "model": "fake-model",
                "score": 0.9,
                "predicted_success": 0.9,
                "reasons": ["test availability"],
            },
            "rejected_candidates": {},
            "policy_version": 3,
            "registry_version": 4,
        }


class StopAfterStaffingDdev:
    async def create_workspace(self, **payload):
        raise RuntimeError("stop after staffing")


def baseline() -> ProjectBaseline:
    ref = [SourceReference(path="docs/scope.md")]
    return ProjectBaseline(
        project_id="demo",
        revision="v1",
        source_commit="a" * 40,
        references=BaselineReferences(
            goals=ref,
            non_goals=ref,
            requirements=ref,
            architecture_constraints=ref,
            quality_policy=ref,
            security_policy=ref,
            budget_policy=ref,
            roadmap_frame=ref,
        ),
    )


def project_config() -> dict:
    return {
        "ddev": {
            "enabled": True,
            "targeted_tests": ["test-targeted"],
            "static_analysis": ["test-static"],
            "full_tests": [],
        }
    }


def request(**overrides) -> PMPlanCreateRequest:
    payload = {
        "project_id": "demo",
        "baseline_revision": "v1",
        "ticket": {
            "id": "T-QUOTA",
            "title": "Plan bounded work",
            "description": "Plan approved work while one staffing candidate is temporarily unavailable.",
        },
    }
    payload.update(overrides)
    return PMPlanCreateRequest.model_validate(payload)


def planner(monkeypatch):
    storage = FakeStorage()
    router = AvailabilityAwareRouter()
    monkeypatch.setattr(pm_planning, "project_config", lambda project_id: project_config())
    monkeypatch.setattr(
        pm_planning,
        "resolve_project_baseline",
        lambda project_id, revision=None: baseline(),
    )
    return PMPlanner(storage, router=router, ddev=StopAfterStaffingDdev()), router


def test_pm_defaults_to_empty_provider_state(monkeypatch) -> None:
    service, router = planner(monkeypatch)

    row = asyncio.run(service.create_plan(request()))

    assert row["status"] == "failed"
    assert router.calls[0]["provider_state"] == {}
    assert row["staffing"]["choice"]["id"] == "codex_plus"


def test_pm_forwards_codex_unavailability_and_allows_staffing_fallback(monkeypatch) -> None:
    service, router = planner(monkeypatch)

    row = asyncio.run(
        service.create_plan(
            request(
                provider_state={
                    "codex_plus": {
                        "healthy": False,
                        "available": False,
                        "quota_pressure": 1.0,
                    }
                }
            )
        )
    )

    forwarded = router.calls[0]["provider_state"]["codex_plus"]
    assert forwarded == {
        "healthy": False,
        "quota_pressure": 1.0,
        "error_rate": 0.0,
        "latency_ms": 0,
        "predicted_success": None,
        "available": False,
    }
    assert row["staffing"]["choice"]["id"] == "antigravity_free"


def test_pm_provider_state_rejects_unknown_fields_and_invalid_ranges() -> None:
    with pytest.raises(ValidationError):
        request(provider_state={"codex_plus": {"available": False, "model": "forced"}})

    with pytest.raises(ValidationError):
        request(provider_state={"codex_plus": {"quota_pressure": 1.01}})
