import os
from pathlib import Path

import yaml


def projects_file() -> Path:
    configured = os.getenv("PROJECTS_FILE")
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        raise RuntimeError(f"PROJECTS_FILE does not exist: {path}")

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / "projects.yml"
        if candidate.is_file():
            return candidate

    raise RuntimeError("Unable to locate config/projects.yml")


PROJECTS_FILE = projects_file()


def test_chonhac_targeted_verification_follows_changed_module_test_layers() -> None:
    data = yaml.safe_load(PROJECTS_FILE.read_text(encoding="utf-8"))
    chonhac = data["projects"]["chonhac"]
    ddev = chonhac["ddev"]

    assert list(ddev["targeted_tests"]) == [
        "ddev drush cr",
        "bash /config/scripts/chonhac-targeted-tests.sh",
    ]

    # The selector is mounted with projects.yml and executes from the
    # Executor's Chợ Nhạc workspace, not inside a nested DDEV login shell.
    script = (PROJECTS_FILE.parent / "scripts" / "chonhac-targeted-tests.sh").read_text(
        encoding="utf-8"
    )
    assert "set -euo pipefail" in script
    assert "git diff --name-only HEAD -- web/modules/custom" in script
    assert "git ls-files --others --exclude-standard -- web/modules/custom" in script
    assert 'for module in "${modules[@]}"' in script
    assert "for layer in Unit Kernel Functional" in script
    assert 'web/modules/custom/$module/tests/src/$layer' in script
    assert "vendor/bin/phpunit -c web/core/phpunit.xml.dist" in script
    assert "ddev exec --raw -- env" in script
    assert "ddev exec --raw -- bash -lc" not in script
    assert "ShowDomainTest.php" not in script
    assert "cho_nhac_show/tests" not in script
    assert "|| true" not in script

    assert any(
        "vendor/bin/phpcs web/modules/custom" in command
        for command in ddev["static_analysis"]
    )


def test_projects_file_prefers_runtime_mount(monkeypatch, tmp_path) -> None:
    mounted = tmp_path / "projects.yml"
    mounted.write_text("projects: {}\\n", encoding="utf-8")
    monkeypatch.setenv("PROJECTS_FILE", str(mounted))

    assert projects_file() == mounted


def test_projects_file_fails_closed_for_missing_explicit_mount(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "missing.yml"
    monkeypatch.setenv("PROJECTS_FILE", str(missing))

    try:
        projects_file()
    except RuntimeError as exc:
        assert "PROJECTS_FILE does not exist" in str(exc)
    else:
        raise AssertionError("Missing explicit PROJECTS_FILE was accepted")
