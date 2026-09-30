from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import pm_planning
from app.adapters.base import AgentRun
from app.baseline import BaselineReferences, ProjectBaseline, SourceReference
from app.pm_planning import ExecutionPlanDocument, PMPlanCreateRequest, PMPlanner


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


class FakeRouter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def staff(self, payload: dict) -> dict:
        self.calls.append(payload)
        return {
            "request_id": payload["request_id"],
            "project_id": payload["project_id"],
            "role": "product_manager",
            "profile": payload["profile"],
            "choice": {
                "id": "codex_terra",
                "provider": "openai",
                "adapter": "codex_cli",
                "model": "gpt-5.6-terra",
                "reasoning_effort": "low",
                "score": 0.9,
                "predicted_success": 0.9,
                "reasons": ["test"],
            },
            "rejected_candidates": {},
            "policy_version": 3,
            "registry_version": 4,
        }


class FakeDdev:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.create_calls: list[dict] = []
        self.remove_calls: list[dict] = []

    async def create_workspace(self, **payload) -> dict:
        self.create_calls.append(payload)
        return {
            "workspace": str(self.workspace),
            "branch": f"ai/{payload['job_id'][:12]}",
            "source_commit": "a" * 40,
            "workspace_mode": "isolated_clone_no_remote",
        }

    async def remove_workspace(self, **payload) -> dict:
        self.remove_calls.append(payload)
        return {"removed": True}


class FakeAdapter:
    def __init__(self, output: dict, *, mutate: bool = False) -> None:
        self.output = output
        self.mutate = mutate
        self.calls: list[dict] = []

    async def run(self, **payload) -> AgentRun:
        self.calls.append(payload)
        if self.mutate:
            Path(payload["workspace"], "pm-mutated.txt").write_text("not allowed", encoding="utf-8")
        return AgentRun(
            adapter="fake",
            model="fake-model",
            returncode=0,
            output=json.dumps(self.output),
            usage={"input_tokens": 100, "output_tokens": 50},
        )


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


def ticket() -> dict:
    return {
        "id": "T-100",
        "title": "Implement bounded feature",
        "description": "Implement the already-approved feature without expanding project scope.",
    }


def work_order(
    work_order_id: str = "WO-1",
    *,
    dependencies: list[str] | None = None,
    source_path: str = "docs/scope.md",
) -> dict:
    return {
        "id": work_order_id,
        "parent_ticket": "T-100",
        "objective": f"Implement {work_order_id}",
        "baseline_revision": "v1",
        "source_references": [{"path": source_path}],
        "in_scope": [f"bounded work for {work_order_id}"],
        "out_of_scope": [f"unrelated work for {work_order_id}"],
        "acceptance_criteria": [
            {"id": f"AC-{work_order_id}", "description": "Requested behavior is covered by tests"}
        ],
        "constraints": ["Do not expand scope"],
        "requested_role": "backend_developer",
        "verification": {"required_phases": ["targeted_tests"]},
        "risk": {"level": "standard", "flags": []},
        "budget": {
            "max_profile": "standard",
            "max_model_calls": 4,
            "max_repair_iterations": 1,
            "max_wall_time_minutes": 20,
            "max_changed_files": 8,
        },
        "dependencies": dependencies or [],
    }


def proposal(*work_orders: dict) -> dict:
    return {
        "scope_assessment": "in_scope",
        "summary": "Ticket is inside the approved project scope.",
        "work_orders": list(work_orders),
        "decision_boundaries": [],
    }


def make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / "docs").mkdir()
    (workspace / "docs" / "scope.md").write_text("# Approved scope\n", encoding="utf-8")
    return workspace


def configure(monkeypatch, tmp_path: Path, output: dict, *, mutate: bool = False):
    workspace = make_workspace(tmp_path)
    storage = FakeStorage()
    router = FakeRouter()
    ddev = FakeDdev(workspace)
    adapter = FakeAdapter(output, mutate=mutate)
    monkeypatch.setattr(pm_planning, "project_config", lambda project_id: project_config())
    monkeypatch.setattr(
        pm_planning,
        "resolve_project_baseline",
        lambda project_id, revision=None: baseline(),
    )
    planner = PMPlanner(
        storage,
        router=router,
        ddev=ddev,
        adapter_builder=lambda adapter_name, model, reasoning_effort=None: adapter,
    )
    request = PMPlanCreateRequest(project_id="demo", ticket=ticket(), baseline_revision="v1")
    return planner, request, storage, router, ddev, adapter


def test_pm_creates_ready_dependency_aware_plan(monkeypatch, tmp_path):
    output = proposal(
        work_order("WO-1"),
        work_order("WO-2", dependencies=["WO-1"]),
    )
    planner, request, storage, router, ddev, adapter = configure(monkeypatch, tmp_path, output)

    row = asyncio.run(planner.create_plan(request))

    assert row["status"] == "ready"
    assert row["plan"]["ready_work_order_ids"] == ["WO-1"]
    assert row["baseline_revision"] == "v1"
    assert row["baseline_source_commit"] == "a" * 40
    assert row["staffing"]["choice"]["id"] == "codex_terra"
    assert row["usage"]["model_calls"] == 1
    assert len(router.calls) == 1
    assert router.calls[0]["role"] == "product_manager"
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["mode"] == "plan"
    assert "docs/scope.md" in adapter.calls[0]["prompt"]
    assert "T-100" in adapter.calls[0]["prompt"]
    assert ddev.create_calls[0]["ref"] == "a" * 40
    assert ddev.create_calls[0]["workspace_mode"] == "isolated_clone"
    assert len(ddev.remove_calls) == 1


def test_execution_mode_is_caller_policy_and_legacy_plans_default_autonomous(monkeypatch, tmp_path):
    output = proposal(work_order("WO-1"), work_order("WO-2", dependencies=["WO-1"]))
    planner, request, *_ = configure(monkeypatch, tmp_path, output)
    assert request.execution_mode == "autonomous"
    request.execution_mode = "supervised"

    row = asyncio.run(planner.create_plan(request))

    assert row["plan"]["execution_mode"] == "supervised"
    legacy = dict(row["plan"])
    legacy.pop("execution_mode")
    assert ExecutionPlanDocument.model_validate(legacy).execution_mode == "autonomous"


def test_pm_model_cannot_choose_or_override_execution_mode(monkeypatch, tmp_path):
    output = {**proposal(work_order()), "execution_mode": "supervised"}
    planner, request, *_ = configure(monkeypatch, tmp_path, output)

    row = asyncio.run(planner.create_plan(request))

    assert request.execution_mode == "autonomous"
    assert row["status"] == "failed"
    assert "extra_forbidden" in row["error"]


def test_pm_persists_out_of_scope_without_work_orders(monkeypatch, tmp_path):
    output = {
        "scope_assessment": "out_of_scope",
        "summary": "The request is explicitly outside the approved product scope.",
        "work_orders": [],
        "decision_boundaries": [],
    }
    planner, request, *_ = configure(monkeypatch, tmp_path, output)

    row = asyncio.run(planner.create_plan(request))

    assert row["status"] == "out_of_scope"
    assert row["plan"]["work_orders"] == []
    assert row["plan"]["ready_work_order_ids"] == []


def test_pm_decision_boundary_is_not_executable(monkeypatch, tmp_path):
    output = {
        "scope_assessment": "in_scope",
        "summary": "Implementation requires a human-owned architecture decision first.",
        "work_orders": [work_order("WO-1")],
        "decision_boundaries": [
            {
                "id": "D-1",
                "category": "architecture",
                "reason": "Two approved-compatible storage approaches have materially different project impact.",
                "source_references": [{"path": "docs/scope.md"}],
            }
        ],
    }
    planner, request, *_ = configure(monkeypatch, tmp_path, output)

    row = asyncio.run(planner.create_plan(request))

    assert row["status"] == "human_decision"
    assert row["plan"]["ready_work_order_ids"] == []


def test_pm_rejects_dependency_cycle(monkeypatch, tmp_path):
    output = proposal(
        work_order("WO-1", dependencies=["WO-2"]),
        work_order("WO-2", dependencies=["WO-1"]),
    )
    planner, request, *_ = configure(monkeypatch, tmp_path, output)

    row = asyncio.run(planner.create_plan(request))

    assert row["status"] == "failed"
    assert "dependency graph contains a cycle" in row["error"]


def test_pm_rejects_work_order_reference_outside_baseline(monkeypatch, tmp_path):
    output = proposal(work_order(source_path="docs/not-approved.md"))
    planner, request, *_ = configure(monkeypatch, tmp_path, output)

    row = asyncio.run(planner.create_plan(request))

    assert row["status"] == "failed"
    assert "not authorized by ProjectBaseline" in row["error"]


def test_pm_workspace_mutation_fails_closed(monkeypatch, tmp_path):
    planner, request, storage, router, ddev, adapter = configure(
        monkeypatch,
        tmp_path,
        proposal(work_order()),
        mutate=True,
    )

    row = asyncio.run(planner.create_plan(request))

    assert row["status"] == "failed"
    assert "modified the read-only planning workspace" in row["error"]
    assert len(adapter.calls) == 1
    assert len(ddev.remove_calls) == 1


def test_pm_planning_rejects_invalid_staffing_before_workspace_or_model_call(
    monkeypatch,
    tmp_path,
):
    planner, request, _, _, ddev, adapter = configure(
        monkeypatch,
        tmp_path,
        proposal(work_order()),
    )

    class InvalidStaffingRouter:
        async def staff(self, payload: dict) -> dict:
            return {
                "request_id": payload["request_id"],
                "project_id": payload["project_id"],
                "role": "product_manager",
                "profile": payload["profile"],
                "choice": {
                    "id": "antigravity_free",
                    "provider": "google_antigravity",
                    "adapter": "antigravity_host",
                    "model": "gemini-3.8-flash-medium",
                    "reasoning_effort": "max",
                },
                "policy_version": 19,
                "registry_version": 10,
            }

    planner.router = InvalidStaffingRouter()
    row = asyncio.run(planner.create_plan(request))

    assert row["status"] == "failed"
    assert "unsupported" in row["error"]
    assert row["usage"] is None
    assert ddev.create_calls == []
    assert adapter.calls == []


def test_pm_requires_approved_baseline_before_persistence(monkeypatch, tmp_path):
    storage = FakeStorage()
    monkeypatch.setattr(pm_planning, "project_config", lambda project_id: project_config())
    monkeypatch.setattr(pm_planning, "resolve_project_baseline", lambda project_id, revision=None: None)
    planner = PMPlanner(storage, router=FakeRouter(), ddev=FakeDdev(make_workspace(tmp_path)))
    request = PMPlanCreateRequest(project_id="legacy", ticket=ticket())

    with pytest.raises(ValueError, match="approved ProjectBaseline"):
        asyncio.run(planner.create_plan(request))

    assert storage.plans == {}


@pytest.mark.parametrize("required,count,status", [(False, 1, "ready"), (True, 1, "failed"), (True, 2, "ready")])
def test_decomposition_contract_validates_before_ready(monkeypatch, tmp_path, required, count, status):
    output = proposal(*[work_order(f"WO-{index + 1}") for index in range(count)])
    planner, request, storage, router, ddev, adapter = configure(monkeypatch, tmp_path, output)
    request.decomposition_required = required
    row = asyncio.run(planner.create_plan(request))
    assert row["status"] == status
    assert ("DECOMPOSITION_REQUIRED" in adapter.calls[0]["prompt"]) is required
    if status == "failed":
        assert "at least two WorkOrders" in row["error"]
        assert row["plan"] is None


@pytest.mark.parametrize("scope", ["out_of_scope", "ambiguous", "in_scope"])
def test_decomposition_never_invents_work_orders_for_scope_or_decisions(monkeypatch, tmp_path, scope):
    output = {
        "scope_assessment": scope, "summary": "Needs scope triage", "work_orders": [],
        "decision_boundaries": [] if scope == "out_of_scope" else [
            {"id": "D-1", "category": "ambiguity", "reason": "Owner scope choice required"}
        ],
    }
    planner, request, *_ = configure(monkeypatch, tmp_path, output)
    request.decomposition_required = True
    row = asyncio.run(planner.create_plan(request))
    assert row["status"] == ("out_of_scope" if scope == "out_of_scope" else "human_decision")
    assert row["plan"]["work_orders"] == row["plan"]["ready_work_order_ids"] == []
