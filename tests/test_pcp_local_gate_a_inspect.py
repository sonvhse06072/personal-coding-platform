"""B2.2c1-A1: fake-only adversarial shell tests; zero real Docker or DDEV."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pcp-local-gate-a-inspect.sh"
INPUTS = (
    "scripts/pcp-local-gate-a-inspect.sh",
    "config/projects.pcp-local.yml",
    "config/project-baselines.pcp-local.yml",
    ".ddev/docker-compose.platform.yaml",
    ".ddev/config.yaml",
    "config/tool-versions.env",
)


def _exe(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" +
                    textwrap.dedent(body) + "\n", encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def readonly(tmp_path):
    repo = tmp_path / "pcp"
    for folder in ("scripts", ".ddev", "config", ".git"):
        (repo / folder).mkdir(parents=True)
    for filename in INPUTS:
        shutil.copy2(ROOT / filename, repo / filename)
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    audit_log = tmp_path / "command-calls.log"
    home = tmp_path / "fresh-home"
    home.mkdir()
    _exe(bin_dir / "git", r'''
        printf 'git %s\n' "$*" >> "$FAKE_LOG"
        [[ "${1:-}" == "-C" && "${2:-}" == "$FAKE_REPO" ]] || exit 96
        shift 2
        case "${1:-}" in
          rev-parse)
            case "${2:-}" in
              --show-toplevel) printf '%s\n' "$FAKE_REPO" ;;
              HEAD) printf '%040d\n' 0 | tr 0 a ;;
              HEAD:*) printf '%040d\n' 0 | tr 0 b ;;
              *) exit 90 ;;
            esac ;;
          remote)
            [[ "${2:-}" == "get-url" && "${3:-}" == "origin" ]] || exit 91
            printf '%s\n' "$FAKE_GIT_ORIGIN" ;;
          hash-object)
            [[ "${2:-}" == "--" ]] || exit 92
            if [[ "$FAKE_SOURCE_DRIFT" == 1 ]]; then
              printf '%040d\n' 0 | tr 0 c
            else
              printf '%040d\n' 0 | tr 0 b
            fi ;;
          *) exit 97 ;;
        esac
    ''')
    _exe(bin_dir / "docker", r'''
        printf 'docker %s\n' "$*" >> "$FAKE_LOG"
        if [[ "${FAKE_DOCKER_FAIL:-}" == "${1:-}" ]]; then exit 44; fi
        if [[ "${1:-}" == context && "${2:-}" == show && $# == 2 ]]; then
          printf '%s\n' "$FAKE_CONTEXT"
        elif [[ "${1:-}" == context && "${2:-}" == inspect && $# == 5 &&
                "${4:-}" == "--format" &&
                "${5:-}" == '{{.Endpoints.docker.Host}}' ]]; then
          printf '%s\n' "$FAKE_ENDPOINT"
        elif [[ "${1:-}" == info && "${2:-}" == "--format" && $# == 3 &&
                "${3:-}" == '{{.ID}}|{{.OperatingSystem}}|{{.ServerVersion}}' ]]; then
          printf '%s\n' "$FAKE_DOCKER_INFO"
        else
          exit 98
        fi
    ''')
    _exe(bin_dir / "ddev", "printf 'ddev invoked\\n' >> \"$FAKE_LOG\"; exit 99")
    _exe(bin_dir / "id", r'''
        [[ "$*" == "-u" ]] || exit 99
        printf '%s\n' "$FAKE_UID"
    ''')
    _exe(bin_dir / "uname", r'''
        [[ "$*" == "-s" ]] && { echo Linux; exit 0; }
        [[ "$*" == "-r" ]] && { echo 6.6.0-microsoft-standard-WSL2; exit 0; }
        exit 99
    ''')
    env = {**os.environ}
    for key in (
        "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH", "DOCKER_CONFIG", "PCP_RUNTIME_STARTUP_MODE",
        "PCP_LOCAL_TASK_SOURCE_ENABLED", "PCP_LOCAL_TASK_WORKER_ENABLED",
        "PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION",
    ):
        env.pop(key, None)
    env.update({
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "FAKE_REPO": str(repo),
        "FAKE_LOG": str(audit_log),
        "FAKE_UID": "1000",
        "FAKE_GIT_ORIGIN": "https://github.com/sonvhse06072/personal-coding-platform.git",
        "FAKE_SOURCE_DRIFT": "0",
        "FAKE_CONTEXT": "default",
        "FAKE_ENDPOINT": "unix:///var/run/docker.sock",
        "FAKE_DOCKER_INFO": "daemon-test-000000012345|Ubuntu 24.04|28.1.1",
        "FAKE_DOCKER_FAIL": "",
    })
    return repo, env, audit_log


def _run(sandbox, *args, **env_change):
    repo, env, _ = sandbox
    proc = subprocess.run(
        ["bash", str(repo / "scripts/pcp-local-gate-a-inspect.sh"),
         *(args or ("--check",))],
        cwd=repo, env={**env, **env_change}, capture_output=True,
        text=True, timeout=12, check=False,
    )
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "PCP_GATE_A_RESULT=STOP" in proc.stdout
    assert "PCP_B22C1_LIVE=STOP" in proc.stdout
    assert "PCP_GATE_A_PHYSICAL_ISOLATION=NOT_ATTESTED" in proc.stdout
    return proc


def _reason(proc):
    return proc.stdout.split("PCP_GATE_A_REASON=", 1)[1].splitlines()[0]


def _calls(sandbox):
    log = sandbox[2]
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_clean_synthetic_metadata_is_still_stop_and_does_not_mutate(readonly):
    repo, _, _ = readonly
    before = {str(p.relative_to(repo)): p.read_bytes()
              for p in repo.rglob("*") if p.is_file()}
    output = _run(readonly)
    assert _reason(output) == "PHYSICAL_ISOLATION_NOT_ATTESTED"
    assert "PCP_GATE_A_DOCKER_SCOPE=UNIX_LOCAL_METADATA_ONLY" in output.stdout
    assert "PCP_GATE_A_SOURCE_STATUS=REVIEWED_FILES_UNMODIFIED" in output.stdout
    assert "PCP_GATE_A_LEGACY_COMPOSE=UNSAFE_NOT_STARTED" in output.stdout
    assert "PCP_GATE_A_KERNEL_CLASS=WSL_KERNEL_UNATTESTED" in output.stdout
    assert "PCP_GATE_A_DAEMON_FINGERPRINT_SHA256=" in output.stdout
    assert not output.stderr
    after = {str(p.relative_to(repo)): p.read_bytes()
             for p in repo.rglob("*") if p.is_file()}
    assert before == after
    calls = _calls(readonly)
    assert len([x for x in calls if x.startswith("docker ")]) == 3
    assert "docker context show" in calls
    assert any(x.startswith("docker context inspect default") for x in calls)
    assert any(x.startswith("docker info --format") for x in calls)
    assert not any(x.startswith("ddev ") for x in calls)
    assert not any(x.startswith("docker container") or
                   x.startswith("docker volume") or
                   x.startswith("docker network") or
                   x.startswith("docker run") or
                   x.startswith("docker build") for x in calls)
    assert not any(" -w " in x or "git fetch" in x or "git checkout" in x
                   for x in calls)


@pytest.mark.parametrize(("changes", "expected"), [
    ({"DOCKER_HOST": "ssh://external-host"}, "DOCKER_ENV_OVERRIDE"),
    ({"DOCKER_CONTEXT": "other"}, "DOCKER_ENV_OVERRIDE"),
    ({"DOCKER_TLS_VERIFY": "1"}, "DOCKER_ENV_OVERRIDE"),
    ({"DOCKER_CONFIG": "/shared/credentials"}, "DOCKER_ENV_OVERRIDE"),
    ({"PCP_RUNTIME_STARTUP_MODE": "normal"}, "ACTIVATION_FLAG_PRESENT"),
    ({"PCP_LOCAL_TASK_SOURCE_ENABLED": "owner-approved"}, "ACTIVATION_FLAG_PRESENT"),
    ({"PCP_LOCAL_TASK_WORKER_ENABLED": "owner-approved"}, "ACTIVATION_FLAG_PRESENT"),
    ({"PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION": "owner-approved"}, "ACTIVATION_FLAG_PRESENT"),
    ({"FAKE_UID": "0"}, "ROOT_FORBIDDEN"),
])
def test_untrusted_host_or_activation_environment_rejected_before_docker(
    readonly, changes, expected,
):
    result = _run(readonly, **changes)
    assert _reason(result) == expected
    assert not any(x.startswith("docker ") for x in _calls(readonly))
    assert "FAKE_" not in result.stdout


@pytest.mark.parametrize(("changes", "expected"), [
    ({"FAKE_CONTEXT": "desktop-linux|unexpected"}, "DOCKER_CONTEXT_UNSAFE"),
    ({"FAKE_ENDPOINT": "ssh://legacy-user@remote:22"}, "DOCKER_ENDPOINT_NOT_LOCAL"),
    ({"FAKE_ENDPOINT": "tcp://127.0.0.1:2375"}, "DOCKER_ENDPOINT_NOT_LOCAL"),
    ({"FAKE_ENDPOINT": "unix:///mnt/wsl/docker-desktop/shared-sockets/docker.sock"},
     "DOCKER_ENDPOINT_NOT_LOCAL"),
    ({"FAKE_ENDPOINT": "unix:///run/user/abc/docker.sock"}, "DOCKER_ENDPOINT_NOT_LOCAL"),
    ({"FAKE_DOCKER_INFO": "daemon-test-000000012345|Docker Desktop|28.1.1"},
     "DOCKER_DESKTOP_SHARED"),
    ({"FAKE_DOCKER_INFO": "bad"}, "DOCKER_METADATA_INVALID"),
    ({"FAKE_DOCKER_FAIL": "info"}, "DOCKER_METADATA_UNAVAILABLE"),
    ({"FAKE_DOCKER_FAIL": "context"}, "DOCKER_CONTEXT_UNAVAILABLE"),
])
def test_ambiguous_remote_or_shared_daemon_metadata_denied(
    readonly, changes, expected,
):
    result = _run(readonly, **changes)
    assert _reason(result) == expected
    assert "DAEMON_FINGERPRINT" not in result.stdout
    assert not any(x.startswith("ddev ") for x in _calls(readonly))


@pytest.mark.parametrize(("changes", "expected"), [
    ({"FAKE_GIT_ORIGIN": "https://token@github.com/sonvhse06072/personal-coding-platform.git"},
     "SOURCE_REMOTE_NOT_CANONICAL"),
    ({"FAKE_GIT_ORIGIN": "git@github.com:other/repo.git"}, "SOURCE_REMOTE_NOT_CANONICAL"),
    ({"FAKE_SOURCE_DRIFT": "1"}, "SOURCE_FILE_DRIFT"),
])
def test_untrusted_checkout_fails_before_daemon_metadata(readonly, changes, expected):
    result = _run(readonly, **changes)
    assert _reason(result) == expected
    assert not any(x.startswith("docker ") for x in _calls(readonly))
    assert "token" not in result.stdout and "token" not in result.stderr


@pytest.mark.parametrize(("file", "before", "after", "expected"), [
    ("config/projects.pcp-local.yml", "    path: null", "    path: /old/host/workspace",
     "DRAFT_PROJECT_PATH_NOT_NULL"),
    ("config/project-baselines.pcp-local.yml", "    active_revision: null",
     "    active_revision: approved", "DRAFT_BASELINE_NOT_INACTIVE"),
    (".ddev/docker-compose.platform.yaml", "/config/projects.yml",
     "/config/projects.pcp-local.yml", "LEGACY_COMPOSE_LAYOUT_CHANGED"),
    (".ddev/docker-compose.platform.yaml", "${HOST_HOME}/.codex",
     "${HOME}/.codex", "HOST_CREDENTIAL_MOUNT_LAYOUT_CHANGED"),
    (".ddev/docker-compose.platform.yaml", "/var/run/docker.sock:/var/run/docker.sock",
     "/tmp/no-socket", "EXECUTOR_SOCKET_LAYOUT_CHANGED"),
])
def test_source_layout_drift_refuses_even_if_fake_git_claims_clean(
    readonly, file, before, after, expected,
):
    path = readonly[0] / file
    original = path.read_text(encoding="utf-8")
    assert before in original
    path.write_text(original.replace(before, after), encoding="utf-8")
    result = _run(readonly)
    assert _reason(result) == expected
    assert not any(x.startswith("docker ") for x in _calls(readonly))


def test_missing_source_symlink_and_invalid_arg_do_not_reach_docker(readonly):
    p = readonly[0] / "config/projects.pcp-local.yml"
    p.unlink()
    result = _run(readonly)
    assert _reason(result) == "SOURCE_FILE_UNSAFE"
    source = ROOT / "config/projects.pcp-local.yml"
    p.symlink_to(source)
    result = _run(readonly)
    assert _reason(result) == "SOURCE_FILE_UNSAFE"
    result = _run(readonly, "--start")
    assert _reason(result) == "USAGE"
    assert not any(x.startswith("docker ") for x in _calls(readonly))


def test_document_authority_classifies_protected_inspector():
    import runpy
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    assert policy["classify_path"]("scripts/pcp-local-gate-a-inspect.sh") == "protected"
