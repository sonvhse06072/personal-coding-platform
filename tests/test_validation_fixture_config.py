from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "config" / "projects.yml"


def test_pcp_validation_fixture_is_enforcing_and_non_production() -> None:
    data = yaml.safe_load(PROJECTS.read_text(encoding="utf-8"))
    project = data["projects"]["pcp-validation-fixture"]

    assert project["path"] == "${CODING_PROJECTS_ROOT}/pcp-validation-fixture"
    assert project["base_branch"] == "main"

    autonomy = project["autonomy"]
    assert autonomy["allow_commit"] is True
    assert autonomy["allow_push_ai_branch"] is True
    assert autonomy["allow_create_pr"] is True
    assert autonomy["allow_auto_merge_low_risk"] is True
    assert autonomy["allow_production_deploy"] is False

    ddev = project["ddev"]
    assert ddev["enabled"] is True
    assert ddev["preflight"] == ["ddev start -y"]
    assert ddev["targeted_tests"] == ["ddev exec php tools/check-style.php"]
    assert len(ddev["static_analysis"]) == 1
    assert "php -l" in ddev["static_analysis"][0]
    assert ddev["full_tests"] == ["ddev exec php tools/run-tests.php"]
    assert ddev["cleanup"] == ["ddev stop --unlist --omit-snapshot"]

    required = (
        ddev["preflight"]
        + ddev["targeted_tests"]
        + ddev["static_analysis"]
        + ddev["full_tests"]
    )
    assert all("|| true" not in command for command in required)
