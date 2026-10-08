from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_chonhac_targeted_verification_follows_worktree_module_changes() -> None:
    config = yaml.safe_load((ROOT / "config" / "projects.yml").read_text(encoding="utf-8"))
    commands = config["projects"]["chonhac"]["ddev"]["targeted_tests"]
    assert commands == [
        "ddev drush cr",
        "bash /config/scripts/chonhac-targeted-tests.sh",
    ]

    script = (ROOT / "config" / "scripts" / "chonhac-targeted-tests.sh").read_text()
    assert "set -euo pipefail" in script
    assert "git diff --name-only HEAD -- web/modules/custom" in script
    assert "git ls-files --others --exclude-standard -- web/modules/custom" in script
    assert "for module in" in script and "for layer in Unit Kernel Functional" in script
    assert "BROWSERTEST_OUTPUT_DIRECTORY" in script
    assert "ddev exec --raw -- id -u" in script
    assert "ddev exec --raw -- env" in script
    assert 'vendor/bin/phpunit -c web/core/phpunit.xml.dist' in script
    assert "ddev exec --raw -- bash -lc" not in script
    assert "|| true" not in script
    assert "chmod 777" not in script
    assert "ddev exec -u root" not in script
    assert "ShowDomainTest.php" not in script
    assert "cho_nhac_profile/tests" not in script
