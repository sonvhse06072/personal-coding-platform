from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_chonhac_targeted_verification_follows_changed_module_test_layers() -> None:
    data = yaml.safe_load((REPO_ROOT / "config" / "projects.yml").read_text(encoding="utf-8"))
    chonhac = data["projects"]["chonhac"]
    ddev = chonhac["ddev"]

    commands = list(ddev["targeted_tests"])
    assert len(commands) >= 2

    joined = "\n".join(commands)
    assert "git diff --name-only HEAD -- web/modules/custom" in joined
    assert "for module in $modules" in joined
    assert "for layer in Unit Kernel Functional" in joined
    assert 'web/modules/custom/$module/tests/src/$layer' in joined
    assert "vendor/bin/phpunit -c web/core/phpunit.xml.dist" in joined
    assert "ShowDomainTest.php" not in joined
    assert "cho_nhac_show/tests" not in joined
    assert "|| true" not in joined

    assert any(
        "vendor/bin/phpcs web/modules/custom" in command
        for command in ddev["static_analysis"]
    )
