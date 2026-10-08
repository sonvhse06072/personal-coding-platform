"""Exercise the mounted, argv-safe Chợ Nhạc selector with a strict DDEV stub."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "config" / "scripts" / "chonhac-targeted-tests.sh"


def _command(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, str], Path, Path]:
    repo = tmp_path / "chonhac"
    repo.mkdir()
    unit = repo / "web/modules/custom/demo/tests/src/Unit/DemoTest.php"
    kernel = repo / "web/modules/custom/demo/tests/src/Kernel/DemoKernelTest.php"
    functional = repo / "web/modules/custom/demo/tests/src/Functional/DemoFunctionalTest.php"
    tracked = repo / "web/modules/custom/demo/src/Demo.php"
    for path in (unit, kernel, functional, tracked):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<?php\n// baseline\n")

    phpunit = repo / "vendor/bin/phpunit"
    phpunit.parent.mkdir(parents=True)
    phpunit.write_text(
        '#!/usr/bin/env bash\n'
        'set -euo pipefail\n'
        'printf "PHPUNIT:%s\\n" "$*" >> "$PCP_PHPUNIT_LOG"\n'
        'printf "OUTPUT:%s\\n" "$BROWSERTEST_OUTPUT_DIRECTORY" >> "$PCP_PHPUNIT_LOG"\n'
        'exit "$PCP_FAKE_PHPUNIT_EXIT"\n'
    )
    phpunit.chmod(0o755)
    _command("git", "init", "-b", "main", cwd=repo)
    _command("git", "config", "user.email", "pcp-test@example.invalid", cwd=repo)
    _command("git", "config", "user.name", "PCP Test", cwd=repo)
    _command("git", "add", ".", cwd=repo)
    _command("git", "commit", "-m", "baseline", cwd=repo)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_ddev = bindir / "ddev"
    fake_ddev.write_text(
        '#!/usr/bin/env bash\n'
        'set -euo pipefail\n'
        '[[ "${1:-}" == exec && "${2:-}" == --raw && "${3:-}" == -- ]] || exit 85\n'
        'shift 3\n'
        'printf "ARGV:" >> "$PCP_DDEV_LOG"\n'
        'printf "<%q>" "$@" >> "$PCP_DDEV_LOG"\n'
        'printf "\\n" >> "$PCP_DDEV_LOG"\n'
        'if [[ "${1:-}" == id && "${2:-}" == -u ]]; then\n'
        '  printf "%s\\n" "$PCP_FAKE_WEB_UID"\n'
        '  exit 0\n'
        'fi\n'
        '[[ "${1:-}" != bash ]] || exit 86\n'
        'exec "$@"\n'
    )
    fake_ddev.chmod(0o755)
    env = dict(os.environ)
    env.update(
        PATH=f"{bindir}:{os.environ.get('PATH', '')}",
        PCP_DDEV_LOG=str(tmp_path / "ddev.log"),
        PCP_PHPUNIT_LOG=str(tmp_path / "phpunit.log"),
        PCP_FAKE_WEB_UID=str(90000000 + os.getpid() % 9000000),
        PCP_FAKE_PHPUNIT_EXIT="0",
    )
    return repo, env, tracked, tmp_path / "phpunit.log"


def _run(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=35,
    )


def test_no_backend_diff_returns_zero_without_false_failure(tmp_path):
    repo, env, _tracked, phpunit = _fixture(tmp_path)
    result = _run(repo, env)

    assert result.returncode == 0, result.stderr
    assert "No changed custom Drupal modules" in result.stdout
    assert not phpunit.exists()
    assert not (tmp_path / "ddev.log").exists()


def test_tracked_and_untracked_module_tests_use_raw_argv(tmp_path):
    repo, env, tracked, phpunit = _fixture(tmp_path)
    tracked.write_text("<?php\n// tracked change\n")
    new_test = repo / "web/modules/custom/newmodule/tests/src/Unit/NewTest.php"
    new_test.parent.mkdir(parents=True)
    new_test.write_text("<?php\n// untracked module\n")
    result = _run(repo, env)

    assert result.returncode == 0, result.stderr
    assert "Running targeted tests for demo" in result.stdout
    assert "Running targeted tests for newmodule" in result.stdout
    logs = phpunit.read_text()
    assert "DemoTest.php" in logs
    assert "DemoKernelTest.php" in logs
    assert "DemoFunctionalTest.php" in logs
    assert "NewTest.php" in logs
    assert logs.count("PHPUNIT:") == 4
    assert "OUTPUT:/tmp/pcp-chonhac-browser-output-" in logs
    argv = (tmp_path / "ddev.log").read_text()
    assert "bash-lc" not in argv
    assert "vendor/bin/phpunit" in argv
    assert "BROWSERTEST_OUTPUT_DIRECTORY" in argv


def test_phpunit_nonzero_is_not_hidden_by_selector(tmp_path):
    repo, env, tracked, phpunit = _fixture(tmp_path)
    tracked.write_text("<?php\n// tracked change\n")
    env["PCP_FAKE_PHPUNIT_EXIT"] = "9"
    result = _run(repo, env)

    assert result.returncode == 9
    assert "Running Unit tests for demo" in result.stdout
    assert "DemoTest.php" in phpunit.read_text()
    assert "DemoKernelTest.php" not in phpunit.read_text()


def test_staged_custom_module_change_is_detected(tmp_path):
    repo, env, tracked, phpunit = _fixture(tmp_path)
    tracked.write_text("<?php\n// staged change\n")
    _command("git", "add", "web/modules/custom/demo/src/Demo.php", cwd=repo)
    result = _run(repo, env)

    assert result.returncode == 0, result.stderr
    assert "Running targeted tests for demo" in result.stdout
    assert "DemoTest.php" in phpunit.read_text()


def test_failed_module_selector_tool_is_not_treated_as_no_backend_diff(tmp_path):
    repo, env, tracked, phpunit = _fixture(tmp_path)
    tracked.write_text("<?php\n// changed\n")
    awk = tmp_path / "bin" / "awk"
    awk.write_text("#!/usr/bin/env sh\nexit 19\n")
    awk.chmod(0o755)
    result = _run(repo, env)

    assert result.returncode == 19
    assert "No changed custom Drupal modules" not in result.stdout
    assert not phpunit.exists()
    assert not (tmp_path / "ddev.log").exists()


def test_failed_find_must_not_silently_skip_phpunit(tmp_path):
    repo, env, tracked, phpunit = _fixture(tmp_path)
    tracked.write_text("<?php\n// changed\n")
    failing_find = tmp_path / "bin" / "find"
    failing_find.write_text("#!/usr/bin/env sh\nexit 17\n")
    failing_find.chmod(0o755)
    result = _run(repo, env)

    assert result.returncode == 17
    assert "Running targeted tests for demo" in result.stdout
    assert not phpunit.exists()
