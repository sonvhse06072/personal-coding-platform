"""Portable B1.1 shell tests: fake Docker/DDEV only; no live containers."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pcp-portable-bootstrap.sh"
BRIDGE = ROOT / "scripts" / "antigravity-bridge.sh"
SUFFIXES = ("router", "coding-runtime", "ddev-executor", "n8n", "host")


def write_exec(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body + "\n")
    path.chmod(0o755)


@pytest.fixture
def portable(tmp_path):
    repo = tmp_path / "personal-coding-platform"
    for folder in ("scripts", ".ddev", "config"):
        (repo / folder).mkdir(parents=True)
    for p in ("scripts/pcp-portable-bootstrap.sh",
              "scripts/antigravity-bridge.sh",
              "scripts/scope-service-secrets.sh",
              "scripts/n8n-control-plane.sh"):
        (repo / p).write_bytes((ROOT / p).read_bytes())
    for p in (".ddev/.env.example", "config/tool-versions.env"):
        (repo / p).write_bytes((ROOT / p).read_bytes())

    binaries = tmp_path / "fake-bin"
    binaries.mkdir()
    write_exec(binaries / "docker", textwrap.dedent(r'''
        if [[ "$1" == "version" ]]; then echo '24.0.0'; exit 0; fi
        [[ "$1" == "run" ]] || exit 51
        printf '%s\n' "$@" >> "$FAKE_DOCKER_LOG"
        if [[ "$FAKE_DOCKER_FAIL" == 1 ]]; then exit 37; fi
        if [[ "$FAKE_DOCKER_CREATE_ENV" == 1 ]]; then
          for suffix in router coding-runtime ddev-executor n8n host; do
            file="$FAKE_REPO/.ddev/.env.$suffix.local"
            if [[ ! -e "$file" ]]; then
              printf 'MOCK_TOKEN=fixture_only\n' > "$file"
              chmod 600 "$file"
            fi
          done
        fi
    '''))
    write_exec(binaries / "ddev", textwrap.dedent(r'''
        if [[ "$1" == "version" ]]; then echo 'v1.25.4'; exit 0; fi
        if [[ "$1" == "start" ]]; then
          echo START >> "$FAKE_DDEV_LOG"
          exit 0
        fi
        exit 52
    '''))
    # Never talk to a real host Docker socket in the fixture.
    write_exec(binaries / "stat", textwrap.dedent(r'''
        if [[ "$*" == "-c %g /var/run/docker.sock" ]]; then
          echo 999
          exit 0
        fi
        exec /usr/bin/stat "$@"
    '''))

    home = tmp_path / "home"
    home.mkdir()
    docker_log = tmp_path / "docker-argv"
    ddev_log = tmp_path / "ddev-argv"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": str(binaries) + os.pathsep + os.environ.get("PATH", ""),
        "FAKE_REPO": str(repo),
        "FAKE_DOCKER_LOG": str(docker_log),
        "FAKE_DDEV_LOG": str(ddev_log),
        "FAKE_DOCKER_FAIL": "0",
        "FAKE_DOCKER_CREATE_ENV": "1",
    }
    return repo, home, env, docker_log, ddev_log


def run_portable(p, action="--check", **updates):
    repo, _, env, _, _ = p
    return subprocess.run(
        ["bash", str(repo / "scripts/pcp-portable-bootstrap.sh"), action],
        cwd=repo, env={**env, **updates},
        capture_output=True, text=True, check=False, timeout=15,
    )


def assert_stop(result, reason):
    assert result.returncode == 2
    assert "PCP_PORTABLE_SETUP=STOP_" + reason in result.stderr


def test_fresh_check_is_strictly_read_only(portable):
    repo, home, _, docker_log, ddev_log = portable
    before = set(str(p) for p in repo.rglob("*"))
    result = run_portable(portable)
    assert result.returncode == 0, result.stderr
    assert "PCP_PORTABLE_PREFLIGHT=PASS" in result.stdout
    assert "PCP_PORTABLE_INSTALL_STATE=FRESH" in result.stdout
    assert not (repo / ".ddev/.env").exists()
    assert not (home / ".coding-platform").exists()
    assert before == set(str(p) for p in repo.rglob("*"))
    assert not docker_log.exists() and not ddev_log.exists()


def test_prepare_secrets_uses_one_isolated_nonroot_docker_container(portable):
    repo, home, _, docker_log, ddev_log = portable
    result = run_portable(portable, "--prepare")
    assert result.returncode == 0, result.stderr
    assert "PCP_PORTABLE_PREPARE=PASS" in result.stdout
    assert "PCP_PORTABLE_HOST_PYTHON=NOT_REQUIRED" in result.stdout
    assert "PCP_PORTABLE_HOST_AGY=DISABLED" in result.stdout
    assert "PCP_PORTABLE_DDEV_START=NOT_RUN" in result.stdout
    assert "MOCK_TOKEN" not in result.stdout
    envfile = repo / ".ddev/.env"
    envbody = envfile.read_text()
    assert "PCP_ANTIGRAVITY_MODE=disabled" in envbody
    assert "HOST_HOME=" + str(home) in envbody
    assert "CHANGE_ME" not in envbody
    pin = (repo / "config/tool-versions.env").read_text().strip().split("=", 1)[1]
    assert "CODEX_VERSION=" + pin in envbody
    assert stat.S_IMODE(envfile.stat().st_mode) == 0o600
    for suffix in SUFFIXES:
        path = repo / (".ddev/.env." + suffix + ".local")
        assert path.exists()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not ddev_log.exists()
    arguments = docker_log.read_text().splitlines()
    assert arguments.count("run") == 1
    for flag in ("--network=none", "--read-only", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges", "--rm", "--pull=missing",
                 "--user", "--tmpfs", "--mount", "--workdir", "--env"):
        assert flag in arguments
    assert "python:3.13-slim-bookworm" in arguments
    assert "HOME=/tmp" in arguments
    assert all("docker.sock" not in arg and str(home) not in arg
               for arg in arguments)


def test_second_prepare_preserves_portable_env_and_scoped_secrets(portable):
    repo, _, _, _, _ = portable
    assert run_portable(portable, "--prepare").returncode == 0
    files = [repo / ".ddev/.env"] + [
        repo / (".ddev/.env." + suffix + ".local") for suffix in SUFFIXES
    ]
    snapshots = [f.read_bytes() for f in files]
    result = run_portable(portable, "--prepare")
    assert result.returncode == 0, result.stderr
    assert "PCP_PORTABLE_INSTALL_STATE=PORTABLE_EXISTING" in result.stdout
    assert [f.read_bytes() for f in files] == snapshots


def test_start_requires_explicit_argument(portable):
    _, _, _, _, ddev_log = portable
    assert run_portable(portable, "--prepare").returncode == 0
    assert not ddev_log.exists()
    result = run_portable(portable, "--start")
    assert result.returncode == 0, result.stderr
    assert "PCP_PORTABLE_DDEV_START=PASS" in result.stdout
    assert "PCP_RUNTIME_FUNCTIONAL_UAT=NOT_RUN" in result.stdout
    assert ddev_log.read_text().splitlines() == ["START"]


def test_legacy_install_is_never_adopted(portable):
    repo, _, _, docker_log, _ = portable
    legacy = repo / ".ddev/.env"
    legacy.write_text("HOST_HOME=/home/legacy\n", encoding="utf-8")
    legacy.chmod(0o600)
    assert_stop(run_portable(portable, "--prepare"), "LEGACY_INSTALL_NO_MIGRATION")
    assert legacy.read_text() == "HOST_HOME=/home/legacy\n"
    assert not docker_log.exists()


def test_existing_foreign_service_env_stops_before_env_creation(portable):
    repo, _, _, docker_log, _ = portable
    (repo / ".ddev/.env.host.local").symlink_to(repo / ".ddev/.env.example")
    assert_stop(run_portable(portable, "--prepare"),
                "EXISTING_SERVICE_ENV_NO_MIGRATION")
    assert not (repo / ".ddev/.env").exists()
    assert not docker_log.exists()


def test_docker_failure_never_starts_ddev(portable):
    repo, _, _, _, ddev_log = portable
    result = run_portable(portable, "--start", FAKE_DOCKER_FAIL="1")
    assert_stop(result, "CONTAINER_SETUP_FAILED")
    assert not ddev_log.exists()
    assert not any((repo / (".ddev/.env." + s + ".local")).exists()
                   for s in SUFFIXES)


def test_missing_container_secret_proof_fails_closed(portable):
    _, _, _, _, ddev_log = portable
    result = run_portable(portable, "--start", FAKE_DOCKER_CREATE_ENV="0")
    assert_stop(result, "CONTAINER_CREDENTIALS_INCOMPLETE")
    assert not ddev_log.exists()


def test_unexpected_cli_argument_is_noop(portable):
    repo, _, _, docker_log, _ = portable
    assert_stop(run_portable(portable, "--force"), "USAGE")
    assert not (repo / ".ddev/.env").exists() and not docker_log.exists()


def test_host_path_symlink_stops_preparation(portable):
    _, home, _, docker_log, _ = portable
    external = home.parent / "unrelated"
    external.mkdir()
    (home / ".coding-platform").symlink_to(external, target_is_directory=True)
    assert_stop(run_portable(portable, "--prepare"), "HOST_PATH_SYMLINK")
    assert list(external.iterdir()) == []
    assert not docker_log.exists()


@pytest.mark.parametrize("action,expected_rc", [
    ("start", 0), ("stop", 0), ("status", 1), ("bad-command", 2),
])
def test_portable_antigravity_host_bridge_never_starts(action, expected_rc, portable):
    repo, home, env, _, _ = portable
    global_env = repo / ".ddev/.env"
    global_env.write_text("PCP_ANTIGRAVITY_MODE=disabled\n", encoding="utf-8")
    global_env.chmod(0o600)
    result = subprocess.run(
        ["bash", str(repo / "scripts/antigravity-bridge.sh"), action],
        env=env, cwd=repo, capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == expected_rc
    assert not (home / ".coding-platform").exists()
    assert not (home / ".gemini").exists()
    if action in {"start", "stop"}:
        assert "PCP_ANTIGRAVITY_HOST_BRIDGE=DISABLED" in result.stdout
    elif action == "status":
        assert '"status":"disabled"' in result.stdout


def test_unrecognized_agent_mode_denied_early(portable):
    repo, home, env, _, _ = portable
    (repo / ".ddev/.env").write_text(
        "PCP_ANTIGRAVITY_MODE=unknown\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(repo / "scripts/antigravity-bridge.sh"), "start"],
        env=env, capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 2
    assert "STOP_ANTIGRAVITY_MODE_INVALID" in result.stderr
    assert not (home / ".coding-platform").exists()


def test_source_never_calls_host_python_or_restarts_legacy_jobs():
    text = SCRIPT.read_text()
    assert "python3 " not in text and "codex exec" not in text
    assert "docker compose up" not in text and "docker restart" not in text
    assert "--network=none" in text and "--read-only" in text
    assert "scripts/scope-service-secrets.sh" in text
    assert "scripts/n8n-control-plane.sh prepare-env" in text
