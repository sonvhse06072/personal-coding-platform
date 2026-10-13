"""F2-C3B exact one-job activation proposal. Pure config checks; NO host/DB/GitHub/model."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

import pytest
import yaml

from app.baseline import ProjectBaselineRegistry
from app.fullpath_worker_only import (
    F2WorkerNotReady, F2_V2_REVISION, F2_V2_SEED,
    require_f2_worker_registry,
)
from app.fullpath_fresh_startup import V2_BRANCH
from app.fullpath_fixture_safety import PROJECT_ID
from app.fullpath_pm_review import _LOGIN


ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "config/fullpath-candidate"
PROPOSAL = CANDIDATE / "one-job-proposal"
REVIEWER = "sonvhse06072"
MUTABLE = {
    "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php",
    "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php",
    "web/modules/custom/pcp_f2_fixture/tests/src/Kernel/WindowOverlapServiceTest.php",
}


def load(directory: Path, name: str) -> dict:
    value = yaml.safe_load((directory / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def frame() -> tuple[dict, dict]:
    return (load(PROPOSAL, "projects.yml"),
            load(PROPOSAL, "project-baselines.yml"))


def test_exact_registry_candidate_is_not_expanded_beyond_intended_fields():
    parked_projects = load(CANDIDATE, "projects.yml")
    parked_baselines = load(CANDIDATE, "project-baselines.yml")
    proposed_projects, proposed_baselines = frame()

    project = proposed_projects["projects"][PROJECT_ID]
    baseline = proposed_baselines["projects"][PROJECT_ID]
    expected_projects = deepcopy(parked_projects)
    expected_baselines = deepcopy(parked_baselines)

    item = expected_projects["projects"][PROJECT_ID]
    item["pm_standalone_review"] = {
        "enabled": True, "reviewer_login": REVIEWER,
    }
    for name in ("allow_commit", "allow_push_ai_branch", "allow_create_pr"):
        item["autonomy"][name] = True
    expected_baselines["projects"][PROJECT_ID]["active_revision"] = F2_V2_REVISION

    assert proposed_projects == expected_projects
    assert proposed_baselines == expected_baselines
    assert set(proposed_projects["projects"]) == {PROJECT_ID}
    assert set(proposed_baselines["projects"]) == {PROJECT_ID}
    assert _LOGIN.fullmatch(REVIEWER)
    assert project["base_branch"] == V2_BRANCH
    assert project["runtime"]["workspace_mode"] == "isolated_clone"
    assert project["runtime"]["exclusive_project_lease"] is False
    assert project["ddev"]["enabled"] is False
    assert project["autonomy"]["allow_auto_merge_low_risk"] is False
    assert project["autonomy"]["allow_production_deploy"] is False
    assert baseline["active_revision"] == F2_V2_REVISION
    assert baseline["revisions"][F2_V2_REVISION]["source_commit"] == F2_V2_SEED

    source_permissions = {
        rule["path"]
        for rule in baseline["revisions"][F2_V2_REVISION]["authority"]
        if rule["authority"] == "mutable_execution"
    }
    assert source_permissions == MUTABLE


def test_proposal_is_accepted_by_existing_f2_worker_registry_only_as_data():
    projects, baselines = frame()
    # Only pure structural checks: no Runtime starts, Storage, Docker, models.
    require_f2_worker_registry(projects, baselines)
    registry = ProjectBaselineRegistry.model_validate(baselines)
    assert set(registry.projects) == {PROJECT_ID}
    assert registry.projects[PROJECT_ID].active_revision == F2_V2_REVISION
    assert registry.projects[PROJECT_ID].revisions[F2_V2_REVISION].status == "approved"


@pytest.mark.parametrize("change", [
    lambda p, b: p["projects"][PROJECT_ID]["autonomy"].update(
        allow_push_ai_branch=False),
    lambda p, b: p["projects"][PROJECT_ID]["autonomy"].update(
        allow_production_deploy=True),
    lambda p, b: p["projects"][PROJECT_ID]["autonomy"].update(
        allow_auto_merge_low_risk=True),
    lambda p, b: p["projects"][PROJECT_ID]["ddev"].update(enabled=True),
    lambda p, b: p["projects"][PROJECT_ID]["runtime"].update(
        workspace_mode="direct"),
    lambda p, b: p["projects"][PROJECT_ID].update(
        base_branch="benchmark/fullpath"),
    lambda p, b: b["projects"][PROJECT_ID].update(active_revision=None),
    lambda p, b: b["projects"][PROJECT_ID]["revisions"][
        F2_V2_REVISION].update(source_commit="a" * 40),
    lambda p, b: p["projects"].update(
        {"chonhac": dict(p["projects"][PROJECT_ID])}),
])
def test_worker_rejects_unbounded_or_inactive_changes(change):
    p, b = frame()
    change(p, b)
    with pytest.raises(F2WorkerNotReady):
        require_f2_worker_registry(p, b)


def test_pm_reviewer_required_and_not_a_privilege_escalation():
    p, _b = frame()
    review = p["projects"][PROJECT_ID]["pm_standalone_review"]
    assert review == {"enabled": True, "reviewer_login": REVIEWER}
    assert bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}",
                             review["reviewer_login"]))
    assert p["projects"][PROJECT_ID]["human_policy"]["routine_review"] is True


def test_actual_parked_files_and_compose_stay_denied():
    parked = load(CANDIDATE, "projects.yml")["projects"][PROJECT_ID]
    assert parked["pm_standalone_review"] == {
        "enabled": False, "reviewer_login": "",
    }
    assert all(parked["autonomy"][k] is False for k in (
        "allow_commit", "allow_push_ai_branch", "allow_create_pr",
    ))
    assert load(CANDIDATE, "project-baselines.yml")["projects"][
        PROJECT_ID]["active_revision"] is None
    assert load(CANDIDATE, "models.yml")["models"] == {}
    assert load(CANDIDATE, "routing-policy.yml")["profiles"] == {}
    cfg = load(PROPOSAL, "models.yml")
    assert set(cfg["models"]) == {"codex_gpt6_luna"}
    assert cfg["models"]["codex_gpt6_luna"]["model"] == "gpt-6-luna"
    router = load(PROPOSAL, "routing-policy.yml")
    assert router["adaptive_budget"]["enabled"] is False
    assert router["profiles"]["fast"]["max_model_calls"] == 2
    assert router["profiles"]["fast"]["max_provider_failovers"] == 0

    compose = yaml.safe_load(
        (ROOT / "deploy/fullpath/compose.c3b-services.yml").read_text(
            encoding="utf-8"))
    assert compose["x-f2-c3b"]["status"] == "not_activated"
    assert set(compose["services"]) == {
        "fullpath-router", "fullpath-executor", "fullpath-runtime",
    }
    assert all(v["profiles"] == ["owner-gated-c3b-one-job"]
               for v in compose["services"].values())
