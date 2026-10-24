"""B2.2c1-A2 shared Docker read-only ownership preflight (fake CLI ONLY)."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pcp-shared-docker-ownership-check.sh"
INPUTS = (
    "scripts/pcp-shared-docker-ownership-check.sh",
    "config/projects.pcp-local.yml",
    "config/project-baselines.pcp-local.yml",
    ".ddev/config.yaml",
    ".ddev/docker-compose.platform.yaml",
)


def executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" +
                    textwrap.dedent(body) + "\n", encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def fake_host(tmp_path):
    repo = tmp_path / "personal-coding-platform"
    for folder in ("scripts", "config", ".ddev", ".git"):
        (repo / folder).mkdir(parents=True)
    for item in INPUTS:
        shutil.copy2(ROOT / item, repo / item)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    log = tmp_path / "calls.log"
    home = tmp_path / "home"
    home.mkdir()

    executable(fake_bin / "git", r'''
        printf 'git %s\n' "$*" >> "$FAKE_CALLS"
        [[ "${1:-}" == "-C" && "${2:-}" == "$FAKE_REPO" ]] || exit 41
        shift 2
        case "${1:-}" in
          rev-parse)
            case "${2:-}" in
              --show-toplevel) printf '%s\n' "$FAKE_REPO" ;;
              HEAD) printf '%040d\n' 0 | tr 0 a ;;
              HEAD:*) printf '%040d\n' 0 | tr 0 b ;;
              *) exit 42 ;;
            esac ;;
          remote)
            [[ "${2:-}" == "get-url" && "${3:-}" == "origin" ]] || exit 43
            printf '%s\n' "$FAKE_REMOTE" ;;
          hash-object)
            [[ "${2:-}" == "--" ]] || exit 44
            if [[ "$FAKE_DRIFT" == yes ]]; then
              printf '%040d\n' 0 | tr 0 c
            else
              printf '%040d\n' 0 | tr 0 b
            fi ;;
          *) exit 45 ;;
        esac
    ''')
    executable(fake_bin / "docker", r'''
        printf 'docker %s\n' "$*" >> "$FAKE_CALLS"
        [[ "${FAKE_FAIL_ON:-}" != "${1:-}" ]] || exit 48
        case "$*" in
          'context show') echo desktop-linux ;;
          'context inspect desktop-linux --format {{.Endpoints.docker.Host}}')
            echo "$FAKE_ENDPOINT" ;;
          'info --format {{.OperatingSystem}}')
            echo "$FAKE_PROVIDER" ;;
          'ps -a --filter label=com.ddev.site-name=personal-coding-platform --format {{.ID}}')
            [[ "$FAKE_LEGACY_CONTAINERS" == zero ]] ||
              echo '0123456789ab' ;;
          'volume ls --filter label=com.docker.compose.project=ddev-personal-coding-platform --format {{.Name}}')
            [[ "$FAKE_LEGACY_VOLUMES" == zero ]] ||
              echo 'ddev-personal-coding-platform-db' ;;
          'ps -a --filter label=com.ddev.site-name=pcp-local --format {{.ID}}')
            [[ "$FAKE_NEW_CONTAINERS" == zero ]] ||
              echo 'abcdef012345' ;;
          'volume ls --filter label=com.docker.compose.project=ddev-pcp-local --format {{.Name}}')
            [[ "$FAKE_NEW_VOLUMES" == zero ]] ||
              echo 'ddev-pcp-local-db' ;;
          'network ls --filter label=com.docker.compose.project=ddev-pcp-local --format {{.ID}}')
            [[ "$FAKE_NEW_NETWORKS" == zero ]] ||
              echo 'badcab012345' ;;
          *) exit 49 ;;
        esac
    ''')
    executable(fake_bin / "id", r'''
        [[ "$*" == "-u" ]] || exit 50
        echo "$FAKE_UID"
    ''')
    executable(fake_bin / "ddev", r'''
        printf 'ddev WAS_INVOKED\n' >> "$FAKE_CALLS"
        exit 51
    ''')
    env = dict(os.environ)
    for key in (
        "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
        "DOCKER_CONFIG", "PCP_RUNTIME_STARTUP_MODE",
        "PCP_LOCAL_TASK_SOURCE_ENABLED", "PCP_LOCAL_TASK_WORKER_ENABLED",
        "PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION",
    ):
        env.pop(key, None)
    env.update({
        "HOME": str(home),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "FAKE_REPO": str(repo),
        "FAKE_CALLS": str(log),
        "FAKE_REMOTE": "https://github.com/sonvhse06072/personal-coding-platform.git",
        "FAKE_DRIFT": "no",
        "FAKE_ENDPOINT": "unix:///var/run/docker.sock",
        "FAKE_PROVIDER": "Docker Desktop",
        "FAKE_UID": "1000",
        "FAKE_FAIL_ON": "",
        "FAKE_LEGACY_CONTAINERS": "one",
        "FAKE_LEGACY_VOLUMES": "one",
        "FAKE_NEW_CONTAINERS": "zero",
        "FAKE_NEW_VOLUMES": "zero",
        "FAKE_NEW_NETWORKS": "zero",
    })
    return repo, env, log


def run(fake_host, *args: str, **changes: str) -> subprocess.CompletedProcess[str]:
    repo, env, _ = fake_host
    result = subprocess.run(
        ["bash", str(repo / "scripts/pcp-shared-docker-ownership-check.sh"),
         *(args or ("--check",))],
        cwd=repo, env={**env, **changes},
        text=True, capture_output=True, timeout=12, check=False,
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "PCP_A2_RESULT=STOP" in result.stdout
    assert "PCP_A2_CLEANUP=NOT_AUTHORIZED" in result.stdout
    assert "PCP_B22C1_LIVE=STOP" in result.stdout
    assert not result.stderr
    return result


def reason(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout.split("PCP_A2_REASON=", 1)[1].splitlines()[0]


def calls(fake_host) -> list[str]:
    log = fake_host[2]
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_shared_desktop_counts_are_redacted_and_never_authorize(fake_host):
    repo = fake_host[0]
    before = {str(p.relative_to(repo)): p.read_bytes()
              for p in repo.rglob("*") if p.is_file()}
    result = run(fake_host)
    assert reason(result) == "OWNER_REVIEW_REQUIRED_SHARED_DOCKER"
    assert "PCP_A2_PROVIDER=DOCKER_DESKTOP_SHARED_OWNER_ACCEPTED_RISK" in result.stdout
    assert "PCP_A2_LEGACY_PLATFORM_CONTAINER_CANDIDATES=1" in result.stdout
    assert "PCP_A2_LEGACY_PLATFORM_VOLUME_CANDIDATES=1" in result.stdout
    assert "PCP_A2_NEW_NAMESPACE_CONTAINER_CANDIDATES=0" in result.stdout
    assert "PCP_A2_NEW_NAMESPACE_VOLUME_CANDIDATES=0" in result.stdout
    assert "PCP_A2_NEW_NAMESPACE_NETWORK_CANDIDATES=0" in result.stdout
    assert "PCP_A2_UNLABELED_RESOURCES=NOT_VERIFIED" in result.stdout
    assert "ddev-personal-coding-platform-db" not in result.stdout
    assert "0123456789ab" not in result.stdout
    assert not any("host" in x or "token" in x for x in result.stdout.splitlines())
    after = {str(p.relative_to(repo)): p.read_bytes()
             for p in repo.rglob("*") if p.is_file()}
    assert before == after
    commands = calls(fake_host)
    assert len([s for s in commands if s.startswith("docker ")]) == 8
    assert not any(s.startswith("ddev ") or "docker exec " in s or
                   "docker run " in s or "docker build " in s or
                   "docker rm " in s or "docker system " in s or
                   "docker compose " in s for s in commands)
    assert not any("chonhac" in s or "prune" in s for s in commands)
    filtered = [s for s in commands if s.startswith(
        ("docker ps ", "docker volume ", "docker network "))]
    assert len(filtered) == 5
    assert all(" --filter label=" in s for s in filtered)


@pytest.mark.parametrize(("changes", "expected"), [
    ({"DOCKER_HOST": "tcp://127.0.0.1:2375"}, "ENV_OVERRIDE_OR_ACTIVATION"),
    ({"DOCKER_CONTEXT": "old-context"}, "ENV_OVERRIDE_OR_ACTIVATION"),
    ({"PCP_RUNTIME_STARTUP_MODE": "normal"}, "ENV_OVERRIDE_OR_ACTIVATION"),
    ({"PCP_LOCAL_TASK_SOURCE_ENABLED": "owner-approved"}, "ENV_OVERRIDE_OR_ACTIVATION"),
    ({"PCP_LOCAL_TASK_WORKER_ENABLED": "owner-approved"}, "ENV_OVERRIDE_OR_ACTIVATION"),
    ({"FAKE_UID": "0"}, "ROOT_FORBIDDEN"),
    ({"FAKE_REMOTE": "https://token@github.com/sonvhse06072/personal-coding-platform.git"},
     "SOURCE_NOT_PCP"),
    ({"FAKE_DRIFT": "yes"}, "SOURCE_FILE_DRIFT"),
])
def test_precondition_rejects_before_docker(fake_host, changes, expected):
    output = run(fake_host, **changes)
    assert reason(output) == expected
    assert not any(s.startswith("docker ") for s in calls(fake_host))
    assert "token" not in output.stdout


@pytest.mark.parametrize(("changes", "expected"), [
    ({"FAKE_ENDPOINT": "ssh://otherhost"}, "ENDPOINT_NOT_LOCAL"),
    ({"FAKE_ENDPOINT": "tcp://localhost:2375"}, "ENDPOINT_NOT_LOCAL"),
    ({"FAKE_PROVIDER": "Ubuntu 24.04"}, "PROVIDER_NOT_DESKTOP"),
    ({"FAKE_FAIL_ON": "info"}, "DAEMON_UNAVAILABLE"),
    ({"FAKE_FAIL_ON": "ps"}, "FILTERED_DOCKER_QUERY_FAILED"),
    ({"FAKE_NEW_CONTAINERS": "one"}, "NEW_NAMESPACE_COLLISION_REVIEW_REQUIRED"),
    ({"FAKE_NEW_VOLUMES": "one"}, "NEW_NAMESPACE_COLLISION_REVIEW_REQUIRED"),
    ({"FAKE_NEW_NETWORKS": "one"}, "NEW_NAMESPACE_COLLISION_REVIEW_REQUIRED"),
])
def test_provider_failure_and_namespace_collision_stay_stop(
    fake_host, changes, expected,
):
    output = run(fake_host, **changes)
    assert reason(output) == expected
    assert "PCP_B22C1_LIVE=STOP" in output.stdout
    assert not any(s.startswith("ddev ") for s in calls(fake_host))


@pytest.mark.parametrize(("source", "old", "new", "expected"), [
    ("config/projects.pcp-local.yml", "    path: null",
     "    path: /home/other", "PCP_PROJECT_ALREADY_ACTIVE"),
    ("config/project-baselines.pcp-local.yml", "    active_revision: null",
     "    active_revision: approved", "PCP_BASELINE_ALREADY_ACTIVE"),
    (".ddev/docker-compose.platform.yaml", "/config/projects.yml",
     "/config/projects.pcp-local.yml", "UNREVIEWED_LEGACY_COMPOSE_CHANGE"),
])
def test_source_contract_drift_stop_before_docker(
    fake_host, source, old, new, expected,
):
    path = fake_host[0] / source
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")
    output = run(fake_host)
    assert reason(output) == expected
    assert not any(s.startswith("docker ") for s in calls(fake_host))


def test_deleted_or_symlinked_config_and_wrong_arg_stop(fake_host):
    path = fake_host[0] / "config/projects.pcp-local.yml"
    path.unlink()
    assert reason(run(fake_host)) == "SOURCE_FILE_UNSAFE"
    path.symlink_to(ROOT / "config/projects.pcp-local.yml")
    assert reason(run(fake_host)) == "SOURCE_FILE_UNSAFE"
    assert reason(run(fake_host, "--delete-all")) == "USAGE"
    assert not any(s.startswith("docker ") for s in calls(fake_host))


def test_future_inspector_is_classified_protected():
    import runpy
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    assert policy["classify_path"](
        "scripts/pcp-shared-docker-ownership-check.sh") == "protected"
