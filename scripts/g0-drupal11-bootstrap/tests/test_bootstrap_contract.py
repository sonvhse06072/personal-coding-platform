"""Offline-only tests: never invoke real DDEV, Composer, GitHub or live projects."""

from pathlib import Path
import json
import os
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "check_ddev_name.py"
SCRIPT = ROOT / "bootstrap.sh"
TEMPLATE = ROOT / "template"
FIXTURE = TEMPLATE / "web/modules/custom/pcp_g0_fixture"


def check(output):
    data = output if isinstance(output, str) else json.dumps(output)
    return subprocess.run(
        [sys.executable, str(CHECKER), "pcp-g0-drupal-fixture"],
        input=data, text=True, capture_output=True, check=False,
    )


def project(name, status="stopped"):
    return {"name": name, "status": status, "type": "drupal11"}


def test_actual_ddev_125_json_raw_array_is_accepted_when_quiescent():
    # Official documented syntax is ``ddev list -j | jq '.raw[]'``.
    assert check({"level": "info", "msg": "OK", "raw": []}).returncode == 0
    assert check({"level": "info", "raw": [project("KCCI"), project("Router", "healthy")]}).returncode == 0


def test_ddev_json_lines_with_informational_messages():
    output = '\n'.join((
        json.dumps({"level": "info", "msg": "Listing DDEV projects"}),
        json.dumps({"level": "info", "raw": [project("environmentaljobs")]}),
    ))
    assert check(output).returncode == 0


def test_active_projects_never_allow_shared_router_start():
    for status in ("running", "OK", "healthy", "paused", "unknown"):
        payload = {"level": "info", "raw": [project("chonhac", status)]}
        result = check(payload)
        assert result.returncode == 4, (status, result.stderr)
        assert "another DDEV project" in result.stderr
    assert check({"raw": [project("chonhac", None)]}).returncode == 3


def test_name_collision_and_malformed_registry_fail_closed():
    assert check({"raw": [project("pcp-g0-drupal-fixture")]}).returncode == 4
    assert check({"raw": [project("PCP-G0-DRUPAL-FIXTURE")]}).returncode == 4
    for payload in ({}, {"raw": None}, {"raw": ["broken"]},
                    {"raw": [{"name": "unnamed"}]}, {"raw": {"projects": None}},
                    {"level": "error", "raw": []}, {"raw": [] , "extra": []}):
        result = check(payload)
        if "extra" in payload:  # Benign irrelevant fields should be ignored.
            assert result.returncode == 0
        else:
            assert result.returncode == 3
    assert check("").returncode == 3
    assert check("not json").returncode == 3
    assert check('{"raw": []}\n{"raw": []}').returncode == 3


def test_legacy_fixture_structure_remains_readable():
    assert check({"raw": {"projects": [project("old", "stopped")]}}).returncode == 0


def test_live_ddev_project_blocks_bootstrap_before_any_mutation(tmp_path):
    # Dummy ddev binary only returns a project inventory. Any attempt to
    # invoke DDEV config/start, or even create the output dir, is a regression.
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    registry = json.dumps({"level": "info", "raw": [
        project("chonhac", "running"), project("Router", "healthy")
    ]})
    fake_ddev = bin_dir / "ddev"
    fake_ddev.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = list ] && [ \"$2\" = -j ]; then\n"
        "  printf '%s\\n' '" + registry + "'\n"
        "  exit 0\n"
        "fi\n"
        "printf '%s\\n' 'UNSAFE DDEV COMMAND' >&2\n"
        "exit 99\n", encoding="utf-8",
    )
    fake_ddev.chmod(0o700)
    # The sandbox may execute tests as root. Mock ONLY id -u for the gate,
    # never grant root privileges to the script under test.
    fake_id = bin_dir / "id"
    fake_id.write_text('#!/bin/sh\n[ "$1" = "-u" ] && { echo 1000; exit 0; }\nexit 99\n')
    fake_id.chmod(0o700)
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[user]\n\tname = Fixture Test\n\temail = fixture@example.invalid\n")
    run = subprocess.run(
        ["bash", str(SCRIPT)],
        env={**os.environ, "HOME": str(home), "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
             "GIT_CONFIG_GLOBAL": str(cfg)},
        capture_output=True, text=True, check=False,
    )
    assert run.returncode == 2, (run.stdout, run.stderr)
    assert "other active project" in run.stderr
    assert "UNSAFE DDEV COMMAND" not in run.stderr
    assert not (home / "pcp-g0-fixtures").exists()


def test_bootstrap_calls_ddev_list_with_supported_json_flag():
    # Observed on the actual GitHub-hosted DDEV 1.25.4 runner: --json is not
    # accepted; DDEV list supports -j or --json-output instead.
    code = SCRIPT.read_text(encoding="utf-8")
    assert 'DDEV_JSON="$(ddev list -j)"' in code
    assert 'ddev list --json' not in code


def test_bash_syntax():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_existing_target_fails_without_touching_it(tmp_path):
    home = tmp_path / "home"
    target = home / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    target.mkdir(parents=True)
    marker = target / "keep.txt"
    marker.write_text("PRESERVE", encoding="utf-8")
    run = subprocess.run(["bash", str(SCRIPT)], env={**os.environ, "HOME": str(home)},
                         capture_output=True, text=True, check=False)
    assert run.returncode == 2
    assert "target already exists" in run.stderr
    assert marker.read_text(encoding="utf-8") == "PRESERVE"
    assert list(target.iterdir()) == [marker]


def test_symlink_target_fails_without_target_mutation(tmp_path):
    home = tmp_path / "home"
    p = home / "pcp-g0-fixtures"
    p.mkdir(parents=True)
    other = tmp_path / "foreign"
    other.mkdir()
    (other / "owner.txt").write_text("SECRET-DO-NOT-TOUCH", encoding="utf-8")
    (p / "pcp-g0-drupal-fixture").symlink_to(other, target_is_directory=True)
    run = subprocess.run(["bash", str(SCRIPT)], env={**os.environ, "HOME": str(home)},
                         capture_output=True, text=True, check=False)
    assert run.returncode == 2
    assert (other / "owner.txt").read_text() == "SECRET-DO-NOT-TOUCH"


def test_php_source_syntax_and_initial_scope():
    php_files = sorted(FIXTURE.rglob("*.php"))
    assert len(php_files) == 3
    for path in php_files:
        r = subprocess.run(["php", "-l", str(path)], capture_output=True, text=True)
        assert r.returncode == 0, f"{path}: {r.stderr}"
    src = (FIXTURE / "src/EventLabelNormalizer.php").read_text()
    assert "return trim($label);" in src
    assert "preg_replace" not in src
    assert "G0D-T01" in src


def test_bootstrap_requires_real_drupal_core_dev_and_phpunit_binary():
    # Official recommended-project may not ship Drupal core's test toolchain.
    # The real hosted run reached PHPCS but did not have vendor/bin/phpunit.
    code = SCRIPT.read_text(encoding="utf-8")
    assert "'drupal/core-dev:^11'" in code
    assert "ddev composer require --dev --with-all-dependencies" in code
    assert "ddev exec test -x vendor/bin/phpunit" in code
    assert "ddev exec test -x vendor/bin/phpcs" in code
    assert code.index("ddev exec test -x vendor/bin/phpunit") < code.index("ddev exec bash -lc")


def test_namespaced_php_class_files_follow_drupal_phpcs_file_comment_rule():
    # A real hosted Drupal PHPCS run rejects @file on namespaced classes.
    for path in sorted(FIXTURE.rglob("*.php")):
        text = path.read_text(encoding="utf-8")
        assert "namespace " in text
        header = text.split("namespace ", 1)[0]
        assert "@file" not in header, path


def test_phpunit_classes_are_real_core_namespaces_not_mock_copies():
    unit = (FIXTURE / "tests/src/Unit/EventLabelNormalizerTest.php").read_text()
    kernel = (FIXTURE / "tests/src/Kernel/EventLabelServiceTest.php").read_text()
    assert r"use Drupal\Tests\UnitTestCase;" in unit
    assert r"use Drupal\KernelTests\KernelTestBase;" in kernel
    assert "RunTestsInSeparateProcesses" in kernel
    assert "testServiceRegistration" in kernel
    assert "assertInstanceOf" in kernel
    assert not (ROOT / "template/vendor").exists()
    assert not (ROOT / "template/web/core").exists()


def test_new_fixture_workflow_is_github_hosted_and_enforcing():
    workflow = yaml.safe_load((TEMPLATE / ".github/workflows/validation.yml").read_text())
    assert workflow["jobs"]["fixture-validation"]["runs-on"] == "ubuntu-latest"
    text = (TEMPLATE / ".github/workflows/validation.yml").read_text()
    assert "pull_request:" in text
    assert "web/core/phpunit.xml.dist" in text
    assert "SIMPLETEST_DB:" in text
    assert "composer install --no-interaction --prefer-dist --no-progress" in text
    assert "--no-scripts" not in text
    assert "vendor/bin/phpcs --standard=Drupal" in text
    assert "|| true" not in text
    assert "self-hosted" not in text


def test_only_isolated_scaffold_commands_are_present():
    code = SCRIPT.read_text()
    assert 'drupal/recommended-project:^11' in code
    assert 'ddev composer require --dev' in code
    assert 'gh repo create "$REMOTE" --private' in code
    assert 'ddev restart' not in code
    assert 'ddev delete' not in code
    assert 'docker system' not in code
    assert 'git reset' not in code
    assert 'git checkout' not in code
    assert 'git pull' not in code
    assert 'git clone' not in code
    assert 'force push' not in code
    assert 'rm -rf' not in code
    assert '|| true' not in code
    assert 'make -C' not in code
    assert '/home/sonvh/chonhac' not in code
    assert "another active project" not in code  # Fail gate handled by checker.
    assert "another DDEV project" in CHECKER.read_text()


def test_yaml_templates_parse():
    info = yaml.safe_load((FIXTURE / "pcp_g0_fixture.info.yml").read_text())
    services = yaml.safe_load((FIXTURE / "pcp_g0_fixture.services.yml").read_text())
    assert info["core_version_requirement"] == "^11"
    assert services["services"]["pcp_g0_fixture.event_label_normalizer"]["class"] == (
        r"Drupal\pcp_g0_fixture\EventLabelNormalizer"
    )


def test_no_preseeded_results_or_developer_creds():
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".pytest_cache" in path.parts or "__pycache__" in path.parts:
            continue
        assert path.suffix not in {".sql", ".sqlite", ".db", ".pem", ".p12", ".key"}
    baseline = (TEMPLATE / "PROJECT-BASELINE.md").read_text()
    assert "CANDIDATE" in baseline
    assert "G0D-T01" in baseline
    assert "NOT part of bootstrap" in baseline
