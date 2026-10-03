from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_chonhac_targeted_verification_follows_changed_custom_modules() -> None:
    config = yaml.safe_load((ROOT / "config" / "projects.yml").read_text(encoding="utf-8"))
    commands = config["projects"]["chonhac"]["ddev"]["targeted_tests"]

    assert commands[0] == "ddev drush cr"
    joined = "\n".join(commands[1:])

    assert "git diff --name-only HEAD -- web/modules/custom" in joined
    assert "awk -F/" in joined
    assert "{print \\$4}" in joined
    assert "ddev exec --raw -- bash -lc" in joined
    assert "for module in $modules" in joined
    assert "for layer in Unit Kernel Functional" in joined
    assert 'web/modules/custom/$module/tests/src/$layer' in joined

    assert "ShowDomainTest.php" not in joined
    assert "cho_nhac_show/tests" not in joined
    assert "cho_nhac_profile/tests" not in joined
    assert "cho_nhac_event/tests" not in joined
    assert "|| true" not in joined
