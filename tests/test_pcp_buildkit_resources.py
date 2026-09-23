from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "pcp-build-images.sh"
GC = ROOT / "scripts" / "pcp-resource-gc.sh"
INVENTORY = ROOT / "scripts" / "pcp-resource-inventory.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_build_helper_is_idempotent_and_explicit(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    state = tmp_path / "builder-created"
    write_executable(
        bin_dir / "docker",
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$DOCKER_LOG"
if [[ "$1 $2" == "buildx inspect" ]]; then
  if [[ ! -f "$BUILDER_STATE" ]]; then exit 1; fi
  printf 'Name:          pcp-builder\\nDriver:        docker-container\\nStatus:           running\\n'
elif [[ "$1 $2" == "buildx create" ]]; then
  : > "$BUILDER_STATE"
elif [[ "$1 $2" == "image inspect" ]]; then
  exit 0
fi
""",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOCKER_LOG": str(log),
        "BUILDER_STATE": str(state),
        "PCP_BUILDX_CONFIG": str(tmp_path / "buildx"),
        "CODEX_VERSION": "codex-test",
        "OPENCODE_VERSION": "opencode-test",
        "DDEV_UID": "1234",
        "DDEV_GID": "5678",
        "DDEV_EXECUTOR_VERSION": "v1.25.4-test",
        "DDEV_EXECUTOR_BUILDX_VERSION": "v0.37.0-test",
    }

    first = subprocess.run(["bash", str(BUILD)], env=env, text=True, capture_output=True)
    second = subprocess.run(["bash", str(BUILD)], env=env, text=True, capture_output=True)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    calls = log.read_text(encoding="utf-8").splitlines()
    assert sum("buildx create --name pcp-builder --driver docker-container" in call for call in calls) == 1
    builds = [call for call in calls if call.startswith("buildx build ")]
    assert len(builds) == 6
    assert all("--builder pcp-builder" in call and "--load" in call for call in builds)
    assert not any("buildx use" in call for call in calls)
    assert not any("prune" in call for call in calls)
    joined = "\n".join(builds)
    for expected in (
        "CODEX_VERSION=codex-test",
        "OPENCODE_VERSION=opencode-test",
        "DDEV_UID=1234",
        "DDEV_GID=5678",
        "DDEV_VERSION=v1.25.4-test",
        "BUILDX_VERSION=v0.37.0-test",
    ):
        assert expected in joined


def test_gc_refuses_active_work_hidden_behind_500_newer_terminal_jobs(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    write_executable(
        bin_dir / "curl",
        """#!/usr/bin/env bash
set -eu
out=''
url=''
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-o" ]]; then out="$2"; shift; fi
  if [[ "$1" == http* ]]; then url="$1"; fi
  shift
done
if [[ "$url" == */v1/jobs/active-count ]]; then
  printf '%s' "$ACTIVE_COUNT_JSON" > "$out"
else
  printf '%s' "$RUNTIME_JSON" > "$out"
fi
""",
    )
    write_executable(
        bin_dir / "docker",
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$DOCKER_LOG"
""",
    )
    newer_terminal_jobs = [
        {
            "id": f"{index:010x}" + "0" * 22,
            "status": "completed",
            "workspace": f"/tmp/workspaces/{index:010x}" + "0" * 22,
        }
        for index in range(1, 501)
    ]
    older_active_job = {
        "id": "f" * 32,
        "status": "executing",
        "workspace": "/tmp/workspaces/" + "f" * 32,
    }
    full_history = [*newer_terminal_jobs, older_active_job]
    authoritative_active_count = sum(
        job["status"] not in {"blocked", "cancelled", "completed", "failed"}
        for job in full_history
    )
    assert len(newer_terminal_jobs) == 500
    assert older_active_job not in newer_terminal_jobs
    assert authoritative_active_count == 1
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUNTIME_API_TOKEN": "test-token",
        "RUNTIME_JSON": json.dumps({"jobs": newer_terminal_jobs}),
        "ACTIVE_COUNT_JSON": json.dumps(
            {"active_engineering_jobs": authoritative_active_count}
        ),
        "DOCKER_LOG": str(docker_log),
        "PCP_BUILDX_CONFIG": str(tmp_path / "buildx"),
    }

    result = subprocess.run(
        ["bash", str(GC), "--execute"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 20
    assert "authoritative Runtime active-work count is not exactly zero" in result.stderr
    assert "AUTHORITATIVE_ACTIVE_ENGINEERING_JOBS=1" in result.stdout
    assert not docker_log.exists()


def test_gc_execute_targets_only_pcp_builder(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    write_executable(
        bin_dir / "curl",
        """#!/usr/bin/env bash
set -eu
out=''
url=''
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-o" ]]; then out="$2"; shift; fi
  if [[ "$1" == http* ]]; then url="$1"; fi
  shift
done
if [[ "$url" == */v1/jobs/active-count ]]; then
  printf '%s' "$ACTIVE_COUNT_JSON" > "$out"
else
  printf '%s' "$RUNTIME_JSON" > "$out"
fi
""",
    )
    write_executable(
        bin_dir / "ddev",
        """#!/usr/bin/env bash
printf '%s' '{"status":"ok","active_jobs":0}'
""",
    )
    write_executable(
        bin_dir / "docker",
        """#!/usr/bin/env bash
set -eu
printf 'BUILDX_CONFIG=%s ARGS=%s\\n' "${BUILDX_CONFIG:-}" "$*" >> "$DOCKER_LOG"
if [[ "$1 $2" == "buildx inspect" ]]; then
  if [[ -n "${BUILDX_CONFIG:-}" ]]; then
    printf 'Name:          pcp-builder\\nDriver:        docker-container\\nStatus:           running\\n'
  else
    printf 'Name:          default\\nDriver:        docker\\nStatus:           running\\n'
  fi
elif [[ "$1 $2" == "buildx du" ]]; then
  printf 'ID RECLAIMABLE SIZE LAST ACCESSED\\nTotal: 0B\\n'
elif [[ "$1 $2" == "buildx prune" ]]; then
  printf 'Total: 0B\\n'
elif [[ "$1 $2" == "image ls" ]]; then
  exit 0
fi
""",
    )
    stable_jobs = {
        "jobs": [{
            "id": "b" * 32,
            "status": "blocked",
            "workspace": "/tmp/workspaces/" + "b" * 32,
        }]
    }
    buildx_dir = tmp_path / "buildx"
    buildx_dir.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUNTIME_API_TOKEN": "test-token",
        "RUNTIME_JSON": json.dumps(stable_jobs),
        "ACTIVE_COUNT_JSON": json.dumps({"active_engineering_jobs": 0}),
        "DOCKER_LOG": str(docker_log),
        "PCP_BUILDX_CONFIG": str(buildx_dir),
    }

    result = subprocess.run(
        ["bash", str(GC), "--execute", "--until", "24h"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    calls = docker_log.read_text(encoding="utf-8").splitlines()
    prune = [call for call in calls if "ARGS=buildx prune" in call]
    assert prune == [
        f"BUILDX_CONFIG={buildx_dir} ARGS=buildx prune --builder pcp-builder --filter until=24h --force"
    ]
    joined = "\n".join(calls)
    assert "system prune" not in joined
    assert "image prune" not in joined
    assert "builder prune" not in joined
    assert "ddev delete images" not in joined


def test_gc_terminal_images_preserve_blocked_and_remove_exact_completed(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    completed_id = "c" * 32
    blocked_id = "d" * 32
    completed_workspace = f"/tmp/workspaces/{completed_id}"
    blocked_workspace = f"/tmp/workspaces/{blocked_id}"
    write_executable(
        bin_dir / "curl",
        """#!/usr/bin/env bash
set -eu
out=''
url=''
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-o" ]]; then out="$2"; shift; fi
  if [[ "$1" == http* ]]; then url="$1"; fi
  shift
done
if [[ "$url" == */v1/jobs/active-count ]]; then
  printf '%s' "$ACTIVE_COUNT_JSON" > "$out"
else
  printf '%s' "$RUNTIME_JSON" > "$out"
fi
""",
    )
    write_executable(
        bin_dir / "ddev",
        """#!/usr/bin/env bash
printf '%s' '{"status":"ok","active_jobs":0}'
""",
    )
    write_executable(
        bin_dir / "docker",
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$DOCKER_LOG"
if [[ "$1 $2" == "buildx inspect" ]]; then
  printf 'Name: pcp-builder\\nDriver: docker-container\\nStatus: running\\n'
elif [[ "$1 $2" == "buildx du" || "$1 $2" == "buildx prune" ]]; then
  printf 'Total: 0B\\n'
elif [[ "$1 $2" == "image ls" ]]; then
  printf '%s\\n' \\
    'ddev/ddev-webserver|v1.25.4-cp-cccccccccc-built|sha256:111' \\
    'ddev/ddev-webserver|v1.25.4-cp-dddddddddd-built|sha256:222'
elif [[ "$1 $2 $3" == "image inspect --format" ]]; then
  image="${@: -1}"
  if [[ "$image" == "sha256:111" ]]; then
    printf 'cp-cccccccccc|ddev|%s\\n' "$COMPLETED_WORKSPACE"
  else
    printf 'cp-dddddddddd|ddev|%s\\n' "$BLOCKED_WORKSPACE"
  fi
elif [[ "$1 $2" == "image rm" ]]; then
  exit 0
elif [[ "$1" == "ps" ]]; then
  exit 0
fi
""",
    )
    jobs = {
        "jobs": [
            {"id": completed_id, "status": "completed", "workspace": completed_workspace},
            {"id": blocked_id, "status": "blocked", "workspace": blocked_workspace},
        ]
    }
    buildx_dir = tmp_path / "buildx"
    buildx_dir.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUNTIME_API_TOKEN": "test-token",
        "RUNTIME_JSON": json.dumps(jobs),
        "ACTIVE_COUNT_JSON": json.dumps({"active_engineering_jobs": 0}),
        "DOCKER_LOG": str(docker_log),
        "COMPLETED_WORKSPACE": completed_workspace,
        "BLOCKED_WORKSPACE": blocked_workspace,
        "PCP_BUILDX_CONFIG": str(buildx_dir),
    }

    result = subprocess.run(
        ["bash", str(GC), "--execute", "--terminal-images"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    removals = [
        call for call in docker_log.read_text(encoding="utf-8").splitlines()
        if call.startswith("image rm ")
    ]
    assert removals == [
        "image rm ddev/ddev-webserver:v1.25.4-cp-cccccccccc-built"
    ]
    assert "STATUS=blocked" in result.stdout
    assert "ACTION=preserve" in result.stdout


def test_inventory_separates_builders_images_volumes_and_references() -> None:
    text = INVENTORY.read_text(encoding="utf-8")
    for heading in (
        "PCP dedicated builder identity",
        "PCP dedicated builder disk usage",
        "Shared/default builder disk usage",
        "PCP platform images",
        "PCP-managed workspace DDEV built images",
        "PCP job volumes",
    ):
        assert heading in text
    assert 'pcp_buildx du --builder "$BUILDER"' in text
    assert "shared_buildx du" in text
    assert 'ancestor=$image_id' in text
    assert 'volume=$volume' in text
