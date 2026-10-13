"""F2 one-job proposed Router policy: pure routing, ZERO provider/host calls."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.engine_review import RouterEngine
from app.schemas import RoutingRequest
from app.model_capabilities import validate_model_registry


ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "config/fullpath-candidate/one-job-proposal"
PROJECT = "pcp-g0-fullpath-fixture"
SEED = "3165b76d44b738c4709c3ca74f87297ff66dd397"
REV = "f2-c1-window-v2-2026-10-12"


def docs():
    return {
        "models": yaml.safe_load((DIR / "models.yml").read_text(encoding="utf-8")),
        "policy": yaml.safe_load((DIR / "routing-policy.yml").read_text(encoding="utf-8")),
        "projects": yaml.safe_load(
            (ROOT / "config/fullpath-candidate/projects.yml").read_text(encoding="utf-8")
        ),
    }


def request(*, dangerous=False, available=True):
    repo = {
        "estimated_files": 3,
        "affected_components": 1,
        "dependency_depth": 0,
        "tests_available": True,
        "existing_pattern": True,
        "historical_churn": 0,
        "related_commits_found": 1,
        "destructive_migration": dangerous,
    }
    return RoutingRequest.model_validate({
        "job_id": "a" * 32,
        "project_id": PROJECT,
        "repository": PROJECT,
        "source_commit": SEED,
        "task": {
            "title": "F2-T01 crossing-midnight overlap repair",
            "description": "Small PHP implementation and two regression tests",
            "semantic": {
                "ambiguity": 10,
                "architecture_impact": 10,
                "verification_difficulty": 10,
                "risk": 10,
                "context_requirement": 10,
                "novelty": 10,
                "reasoning_requirement": 10,
            },
            "flags": [],
        },
        "repo": repo,
        "provider_state": {
            "codex_gpt6_luna": {"available": available, "healthy": available},
        },
    })


def test_proposal_is_one_untrusted_model_pending_host_credential_proof():
    data = docs()
    validate_model_registry(data["models"])
    models = data["models"]["models"]
    assert set(models) == {"codex_gpt6_luna"}
    only = models["codex_gpt6_luna"]
    assert only["adapter"] == "codex_cli"
    assert only["model"] == "gpt-6-luna"
    assert only["provider"] == "openai"
    assert only["reasoning_efforts"] == ["low", "medium"]
    assert only["allowed_profiles"] == ["fast"]
    assert set(only["roles"]) == {
        "explore", "executor", "repair", "reviewer", "test_writer",
    }
    assert only["privacy"]["private_code_allowed"] is True
    assert only["privacy"]["training_allowed"] is False


def test_router_real_engine_offline_selects_bounded_fast_no_authority():
    cfg = docs()
    result = RouterEngine(cfg).route(request())
    strategy = result.strategy
    budget = strategy.budget
    assert result.project_id == PROJECT and result.source_commit == SEED
    assert strategy.profile == "fast"
    assert strategy.executor.id == "codex_gpt6_luna"
    assert strategy.executor.model == "gpt-6-luna"
    assert strategy.executor.reasoning_effort == "medium"
    assert strategy.planner is None
    assert strategy.budget_mode != "adaptive"
    assert strategy.reasoning_ceiling["executor"] == "medium"
    assert budget.max_model_calls == 2
    assert budget.max_iterations == 2
    assert budget.max_provider_failovers == 0
    assert budget.max_model_failovers == 0
    assert budget.max_wall_time_minutes == 15
    assert budget.hard_cost_usd == 0.5
    assert budget.max_changed_files == 3
    assert budget.max_test_runs == 1
    assert all(strategy.permissions[k] is False for k in (
        "commit", "push_ai_branch", "create_pr",
    ))
    assert strategy.human_decision.required is False


@pytest.mark.parametrize("dangerous,available", [
    (True, True), (False, False),
])
def test_f2_proposal_never_routes_protected_or_unavailable_model(
    dangerous, available,
):
    with pytest.raises(RuntimeError):
        RouterEngine(docs()).route(request(
            dangerous=dangerous, available=available,
        ))


def test_candidate_active_files_remain_parked_and_without_model():
    base = ROOT / "config/fullpath-candidate"
    registry = yaml.safe_load((base / "models.yml").read_text(encoding="utf-8"))
    assert registry["models"] == {}
    policy = yaml.safe_load((base / "routing-policy.yml").read_text(encoding="utf-8"))
    assert policy.get("profiles") == {}
    project = yaml.safe_load((base / "projects.yml").read_text(encoding="utf-8"))[
        "projects"
    ][PROJECT]
    assert project["pm_standalone_review"]["enabled"] is False
    assert all(project["autonomy"][item] is False for item in (
        "allow_commit", "allow_push_ai_branch", "allow_create_pr",
    ))
    assert project["ddev"]["enabled"] is False
    baseline = yaml.safe_load(
        (base / "project-baselines.yml").read_text(encoding="utf-8")
    )["projects"][PROJECT]
    assert baseline["active_revision"] is None
    assert baseline["revisions"][REV]["source_commit"] == SEED

    compose = yaml.safe_load((
        ROOT / "deploy/fullpath/compose.c3b-services.yml"
    ).read_text(encoding="utf-8"))
    assert compose["x-f2-c3b"]["status"] == "not_activated"
    for service in compose["services"].values():
        assert service["profiles"] == ["owner-gated-c3b-one-job"]
