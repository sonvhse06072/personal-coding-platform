from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_chonhac_targeted_verification_covers_unit_and_kernel_phpunit() -> None:
    data = yaml.safe_load((REPO_ROOT / "config" / "projects.yml").read_text(encoding="utf-8"))
    chonhac = data["projects"]["chonhac"]
    ddev = chonhac["ddev"]

    commands = list(ddev["targeted_tests"])
    assert len(commands) >= 2

    joined = "\n".join(commands)
    assert '*/tests/src/Unit/*Test.php' in joined
    assert "web/modules/custom/cho_nhac_show/tests/src/Kernel/ShowDomainTest.php" in joined
    assert "SIMPLETEST_DB=pgsql://db:db@db:5432/db" in joined
    assert joined.count("vendor/bin/phpunit -c web/core/phpunit.xml.dist") >= 2

    assert any(
        "vendor/bin/phpcs web/modules/custom" in command
        for command in ddev["static_analysis"]
    )
