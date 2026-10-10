"""G0D-01 registry is source-pinned but cannot run on the Owner's shared DDEV.

This protects Chợ Nhạc from accidental cross-project execution while the
approved isolated fixture's PCP executor environment remains unproven.
"""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "pcp-g0-drupal-fixture"
SOURCE_COMMIT = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
REVISION = "g0d01-seed-2026-10-10"


def test_g0_fixture_is_isolated_and_parked_without_ddev_or_delivery():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text(encoding="utf-8"))
    project = doc["projects"][PROJECT_ID]
    assert doc["version"] == 1
    assert project["path"] == (
        "${CODING_PROJECTS_ROOT}/pcp-g0-fixtures/pcp-g0-drupal-fixture"
    )
    assert project["base_branch"] == "benchmark/pcp"
    assert project["runtime"]["workspace_mode"] == "isolated_clone"
    assert project["runtime"]["exclusive_project_lease"] is False
    assert project["runtime"].get("developer_permission_mode", "guarded") != "trusted_local"
    assert project["privacy"]["private_code"] is True
    assert project["privacy"]["allow_training_provider"] is False
    assert project["autonomy"] == {
        "allow_commit": False,
        "allow_push_ai_branch": False,
        "allow_create_pr": False,
        "allow_auto_merge_low_risk": False,
        "allow_production_deploy": False,
    }
    assert project["ddev"] == {
        "enabled": False,
        "preflight": [],
        "targeted_tests": [],
        "static_analysis": [],
        "full_tests": [],
        "cleanup": [],
    }


def test_g0_fixture_baseline_is_exact_owner_approved_seed_not_runner_sha():
    document = yaml.safe_load(
        (ROOT / "config/project-baselines.yml").read_text(encoding="utf-8")
    )
    baseline = document["projects"][PROJECT_ID]
    assert baseline["active_revision"] == REVISION
    assert list(baseline["revisions"]) == [REVISION]
    revision = baseline["revisions"][REVISION]
    assert revision["status"] == "approved"
    assert revision["source_commit"] == SOURCE_COMMIT
    assert len(revision["source_commit"]) == 40
    assert revision["source_commit"] not in (
        "f68541f6edb3642fa4bb18dae773855e1be29e31",
        "66c9f848fd9edcc35dfffe58ed029a12677bff5e",
    )


def test_registered_source_authority_and_eight_reference_categories():
    revision = yaml.safe_load(
        (ROOT / "config/project-baselines.yml").read_text(encoding="utf-8")
    )["projects"][PROJECT_ID]["revisions"][REVISION]
    rules = {r["path"]: r["authority"] for r in revision["authority"]}
    assert rules["PROJECT-BASELINE.md"] == "human_owner_protected"
    assert rules[".github/workflows/validation.yml"] == "human_owner_protected"
    for path in ("composer.json", "composer.lock", ".ddev/config.yaml"):
        assert rules[path] == "human_owner_protected"
    for path in (
        "web/modules/custom/pcp_g0_fixture/src/EventLabelNormalizer.php",
        "web/modules/custom/pcp_g0_fixture/tests/src/Unit/EventLabelNormalizerTest.php",
        "web/modules/custom/pcp_g0_fixture/tests/src/Kernel/EventLabelServiceTest.php",
    ):
        assert rules[path] == "mutable_execution"
    assert set(revision["references"]) == {
        "goals", "non_goals", "requirements", "architecture_constraints",
        "quality_policy", "security_policy", "budget_policy", "roadmap_frame",
    }
    assert all(
        refs and all(ref["path"] == "PROJECT-BASELINE.md" for ref in refs)
        for refs in revision["references"].values()
    )


def test_other_existing_project_definitions_are_unmodified_in_this_stage():
    projects = yaml.safe_load(
        (ROOT / "config/projects.yml").read_text(encoding="utf-8")
    )["projects"]
    baselines = yaml.safe_load(
        (ROOT / "config/project-baselines.yml").read_text(encoding="utf-8")
    )["projects"]
    assert PROJECT_ID in projects and PROJECT_ID in baselines
    # This test checks the known registry identities, not their live lease state.
    for project_id in ("chonhac", "pcp-validation-fixture"):
        assert project_id in projects and project_id in baselines
    assert projects["chonhac"]["runtime"]["workspace_mode"] == "direct"
    assert projects["pcp-validation-fixture"]["base_branch"] == "main"
