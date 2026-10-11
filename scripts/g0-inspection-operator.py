#!/usr/bin/env python3
"""Owner-only G0 inspection activation; never starts legacy PCP or DDEV.

Usage:
  python3 scripts/g0-inspection-operator.py preflight --expected-sha COMMIT
  python3 scripts/g0-inspection-operator.py activate  --expected-sha COMMIT
  python3 scripts/g0-inspection-operator.py status
  python3 scripts/g0-inspection-operator.py stop

This needs the Owner's explicit DEC-G0-INSPECTION-ACT-01 approval, recorded at
PCP #595. It never dispatches jobs or enables the parked fixture.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys

import yaml


SOURCE_SHA = re.compile(r"^[a-f0-9]{40}$")
PROJECT = "pcp-g0d01"
PROFILE = "owner-gated-g0"
SEED = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
EXPECTED_REPO = "sonvhse06072/personal-coding-platform"
EXPECTED_FIXTURE = "sonvhse06072/pcp-g0-drupal-fixture"
G0_SERVICES = ("db", "router", "executor", "runtime")
BASE_IMAGES = {
    "router": "personal-coding-platform-router:local",
    "executor": "personal-coding-platform-ddev-executor:local",
    "runtime": "personal-coding-platform-coding-runtime:local",
}
SERVICE_CONTEXTS = {
    "router": "services/router",
    "executor": "services/ddev-executor",
    "runtime": "services/runtime",
}
NAMES = {
    "db": "pcp-g0d01-postgres",
    "router": "pcp-g0d01-router-1",
    "executor": "pcp-g0d01-executor-1",
    "runtime": "pcp-g0d01-runtime-1",
}
NETWORK = "pcp-g0d01-private"
DATA_VOLUME = "pcp-g0d01-postgres-data"


class GateError(Exception):
    """Stop at the first unproved resource, image, source or ownership gate."""


def run(argv: list[str], *, env: dict[str, str] | None = None,
        stdin: str | None = None, timeout: int = 40,
        label: str = "command") -> str:
    try:
        result = subprocess.run(
            argv, input=stdin, text=True, capture_output=True,
            env=env, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(label + "_unavailable_or_timeout") from exc
    if result.returncode:
        # Never echo stdout/stderr: a Compose error can contain an env secret.
        raise GateError(label + "_failed")
    return result.stdout.strip()


def inspect(kind: str, name: str) -> dict:
    if kind not in {"container", "image", "volume", "network"}:
        raise GateError("unsupported_docker_inspect")
    try:
        result = json.loads(run(
            ["docker", kind, "inspect", name],
            label="docker_" + kind + "_inspect",
        ))
    except (json.JSONDecodeError, TypeError) as exc:
        raise GateError("invalid_docker_inspection") from exc
    if not isinstance(result, list) or len(result) != 1:
        raise GateError("unexpected_inspection_count")
    return result[0]


def exists(kind: str, name: str) -> bool:
    if kind not in {"container", "image", "volume", "network"}:
        raise GateError("unsupported_docker_inspect")
    try:
        subprocess_result = subprocess.run(
            ["docker", kind, "inspect", name],
            text=True, capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError("docker_inspection_unavailable") from exc
    if subprocess_result.returncode == 0:
        return True
    message = (subprocess_result.stderr or "").lower()
    if any(token in message for token in (
        "no such object", "no such image", "no such container",
        "no such volume", "no such network", "not found",
    )):
        return False
    raise GateError("docker_inspection_unexpected_error")


def require_exact_repo(root: Path, repository: str, branch: str,
                       source_sha: str | None = None) -> str:
    if root.is_symlink() or not root.is_dir():
        raise GateError("git_checkout_missing_or_symlink")
    remote = run(["git", "-C", str(root), "remote", "get-url", "origin"],
                 label="git_remote")
    allowed = {
        "https://github.com/" + repository,
        "https://github.com/" + repository + ".git",
        "git@github.com:" + repository,
        "git@github.com:" + repository + ".git",
    }
    if remote not in allowed:
        raise GateError("git_origin_identity_mismatch")
    current_branch = run(
        ["git", "-C", str(root), "branch", "--show-current"],
        label="git_branch",
    )
    if current_branch != branch:
        raise GateError("git_branch_mismatch")
    head = run(["git", "-C", str(root), "rev-parse", "HEAD"], label="git_head")
    if not SOURCE_SHA.fullmatch(head):
        raise GateError("invalid_git_sha")
    if source_sha and head != source_sha:
        raise GateError("source_head_not_expected")
    if run(["git", "-C", str(root), "status", "--porcelain=v1"],
           label="git_worktree"):
        raise GateError("git_worktree_dirty")
    return head


def guard_source(repo: Path, fixture: Path) -> None:
    for relative in (
        "deploy/g0/compose.candidate.yml",
        "config/g0-fixture-only/projects.yml",
        "config/g0-fixture-only/project-baselines.yml",
        "config/g0-fixture-only/source-contract.yml",
        "config/models.yml",
        "config/routing-policy.yml",
    ):
        path = repo / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(repo):
            raise GateError("source_file_missing_or_symlink")
    staged = yaml.safe_load(
        (repo / "deploy/g0/compose.candidate.yml").read_text(encoding="utf-8")
    )
    if not isinstance(staged, dict) or staged.get("name") != PROJECT:
        raise GateError("unexpected_compose_project")
    if set(staged.get("services") or {}) != set(G0_SERVICES):
        raise GateError("unexpected_compose_services")
    if staged.get("x-g0-contract", {}).get("ready_to_dispatch_g0d_t01") is not False:
        raise GateError("unexpected_compose_activation")
    for svc in staged["services"].values():
        if svc.get("profiles") != [PROFILE] or svc.get("restart") != "no":
            raise GateError("unexpected_compose_lifecycle")
        if svc.get("pull_policy") != "never" or "ports" in svc or "build" in svc:
            raise GateError("unexpected_compose_build_or_ports")
    if staged["services"]["runtime"]["environment"]["PCP_RUNTIME_STARTUP_MODE"] != "inspect":
        raise GateError("runtime_not_in_inspection_mode")
    if staged["services"]["executor"]["environment"]["PCP_EXECUTOR_PROJECT_SCOPE"] != "pcp-g0-drupal-fixture":
        raise GateError("executor_scope_mismatch")
    if staged["networks"]["g0-private"] != {"name": NETWORK, "internal": True}:
        raise GateError("g0_network_not_private")
    if staged["volumes"]["g0-db"] != {"name": DATA_VOLUME}:
        raise GateError("g0_db_volume_mismatch")

    validator = repo / "scripts/g0-fixture-isolation-contract.py"
    spec = importlib.util.spec_from_file_location("g0_fixture_contract", validator)
    if spec is None or spec.loader is None:
        raise GateError("g0_contract_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    status = module.validate(repo)
    if status.get("ready_to_activate") is not False or (
        status.get("ready_to_dispatch_g0d_t01") is not False
    ):
        raise GateError("fixture_not_parked")


def resource_names(source_sha: str) -> dict[str, str]:
    short = source_sha[:12]
    return {svc: f"pcp-g0d01-{svc}:{short}"
            for svc in ("router", "executor", "runtime")}


def compose_env(repo: Path, fixture: Path, workspace: Path,
                source_sha: str, password: str) -> dict[str, str]:
    # Avoid passing host Codex/GitHub/provider secrets into Compose CLI at all.
    # The local engine requires only a minimal Docker client environment.
    allowed = {
        "PATH", "HOME", "USER", "LANG", "LC_ALL",
        "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
        "XDG_RUNTIME_DIR",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    images = resource_names(source_sha)
    env.update({
        "COMPOSE_PARALLEL_LIMIT": "1",
        "PCP_G0_REPO_ROOT": str(repo),
        "PCP_G0_FIXTURE_ROOT": str(fixture),
        "PCP_G0_WORKSPACE_ROOT": str(workspace),
        "PCP_G0_UID": str(os.getuid()),
        "PCP_G0_GID": str(os.getgid()),
        "PCP_G0_DB_PASSWORD": password,
        "PCP_G0_POSTGRES_IMAGE": "postgres:17",
        "PCP_G0_ROUTER_IMAGE": images["router"],
        "PCP_G0_EXECUTOR_IMAGE": images["executor"],
        "PCP_G0_RUNTIME_IMAGE": images["runtime"],
    })
    return env


def compose_args(repo: Path) -> list[str]:
    return [
        "docker", "compose", "-p", PROJECT,
        "-f", str(repo / "deploy/g0/compose.candidate.yml"),
        "--profile", PROFILE,
    ]


def require_headroom(repo: Path) -> None:
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        match = re.search(r"(?m)^MemAvailable:\s*(\d+) kB$", meminfo)
        available_kib = int(match.group(1)) if match else 0
        disk = shutil.disk_usage(repo)
    except (OSError, ValueError) as exc:
        raise GateError("host_capacity_unavailable") from exc
    if available_kib < 4 * 1024 * 1024 or disk.free < 6 * 1024**3:
        raise GateError("insufficient_shared_host_headroom")


def require_no_g0_collision(source_sha: str) -> None:
    for name in NAMES.values():
        if exists("container", name):
            raise GateError("g0_container_identity_already_exists")
    if exists("volume", DATA_VOLUME):
        raise GateError("g0_data_volume_already_exists")
    if exists("network", NETWORK):
        raise GateError("g0_network_already_exists")
    images = resource_names(source_sha)
    for svc, name in images.items():
        if exists("image", name):
            raise GateError("g0_image_tag_already_exists")
        base = inspect("image", BASE_IMAGES[svc])
        identity = str(base.get("Id") or "")
        if not identity.startswith("sha256:") or len(identity) != 71:
            raise GateError("base_image_identity_invalid")
        base_alias = f"pcp-g0d01-base-{svc}:{identity[7:19]}"
        if exists("image", base_alias):
            raise GateError("g0_base_alias_already_exists")
    if not exists("image", "postgres:17"):
        raise GateError("postgres17_not_cached_no_implicit_pull")
    # Explicitly query only containers belonging to the reserved G0 label.
    count = run([
        "docker", "ps", "-a", "-q", "--filter",
        "label=com.docker.compose.project=" + PROJECT,
    ], label="g0_container_label_inspection")
    if count:
        raise GateError("g0_compose_project_label_collision")


def preflight(repo: Path, fixture: Path, expected_sha: str) -> dict[str, str | bool]:
    if not SOURCE_SHA.fullmatch(expected_sha):
        raise GateError("expected_source_sha_required")
    if os.environ.get("DOCKER_HOST", "").strip().startswith(("tcp:", "ssh:")):
        raise GateError("remote_docker_host_not_authorized")
    require_exact_repo(repo, EXPECTED_REPO, "main", expected_sha)
    require_exact_repo(fixture, EXPECTED_FIXTURE, "benchmark/pcp", SEED)
    guard_source(repo, fixture)
    require_headroom(repo)
    if (Path.home() / ".pcp-g0d01").exists():
        raise GateError("g0_private_state_already_exists")
    for base in BASE_IMAGES.values():
        if not exists("image", base):
            raise GateError("pcp_base_image_not_cached")
    require_no_g0_collision(expected_sha)
    # Validate Compose syntax and all interpolations before any host mutation.
    environment = compose_env(
        repo, fixture, Path.home() / ".pcp-g0d01/workspaces",
        expected_sha, "PREFLIGHT_ONLY_NOT_A_REAL_PASSWORD",
    )
    run(compose_args(repo) + ["config", "--quiet"],
        env=environment, label="compose_config", timeout=40)
    return {
        "status": "PASS",
        "phase": "preflight",
        "project": PROJECT,
        "source_sha": expected_sha,
        "fixture_source_sha": SEED,
        "base_images": "cached",
        "reserved_resources": "absent",
        "runtime_mode": "inspect",
        "executor_mode": "health_only",
        "ready_to_dispatch_g0d_t01": False,
    }


def build_g0_overlays(repo: Path, source_sha: str) -> None:
    for svc in ("router", "executor", "runtime"):
        base_id = inspect("image", BASE_IMAGES[svc])["Id"]
        alias = f"pcp-g0d01-base-{svc}:{base_id[7:19]}"
        tag = resource_names(source_sha)[svc]
        run(["docker", "tag", base_id, alias], label="g0_tag_base_" + svc)
        dockerfile = (
            f"FROM {alias}\n"
            "COPY app /app/app\n"
            f'LABEL org.opencontainers.image.revision="{source_sha}"\n'
            'LABEL org.opencontainers.image.pcp.g0="inspection-only"\n'
        )
        run([
            "docker", "build", "--pull=false", "--network=none",
            "-f", "-", "-t", tag,
            str(repo / SERVICE_CONTEXTS[svc]),
        ], stdin=dockerfile, timeout=180, label="g0_build_" + svc)
        labels = (inspect("image", tag).get("Config") or {}).get("Labels") or {}
        if labels.get("org.opencontainers.image.revision") != source_sha or (
            labels.get("org.opencontainers.image.pcp.g0") != "inspection-only"
        ):
            raise GateError("g0_built_image_provenance_mismatch")


def save_private_state(root: Path, password: str, source_sha: str) -> Path:
    state = root / ".pcp-g0d01"
    if state.exists():
        raise GateError("g0_private_state_already_exists")
    state.mkdir(mode=0o700)
    workspace = state / "workspaces"
    workspace.mkdir(mode=0o700)
    record = state / "owner-state.json"
    fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"source_sha": source_sha, "password": password}, stream)
    except BaseException:
        raise GateError("g0_secret_file_write_failed")
    return workspace


def read_private_state(root: Path) -> tuple[str, str, Path]:
    state = root / ".pcp-g0d01"
    record = state / "owner-state.json"
    workspace = state / "workspaces"
    if state.is_symlink() or not state.is_dir() or record.is_symlink() or not record.is_file():
        raise GateError("g0_private_state_invalid")
    if workspace.is_symlink() or not workspace.is_dir():
        raise GateError("g0_workspace_root_invalid")
    if state.stat().st_mode & 0o077 or record.stat().st_mode & 0o077:
        raise GateError("g0_private_state_permissions_unsafe")
    try:
        value = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError("g0_private_state_unreadable") from exc
    sha, password = value.get("source_sha"), value.get("password")
    if not isinstance(sha, str) or not SOURCE_SHA.fullmatch(sha):
        raise GateError("g0_recorded_source_invalid")
    if not isinstance(password, str) or not re.fullmatch("[a-f0-9]{48}", password):
        raise GateError("g0_recorded_password_invalid")
    return sha, password, workspace


PROBE_PY = """import json, sys, urllib.request, urllib.error
base, expected, write_path, denial = sys.argv[1:]
with urllib.request.urlopen(base + "/health", timeout=12) as response:
    health = json.load(response)
if health.get("status") != expected:
    raise SystemExit(2)
try:
    urllib.request.urlopen(urllib.request.Request(
        base + write_path, data=b"{}", method="POST"), timeout=12)
except urllib.error.HTTPError as exc:
    if exc.code != int(denial):
        raise SystemExit(3)
else:
    raise SystemExit(4)
print(json.dumps({"health": expected, "write_denied": int(denial)}))
"""


def verify_inspection(repo: Path, env: dict[str, str]) -> dict[str, str | bool]:
    for svc in G0_SERVICES:
        obj = inspect("container", NAMES[svc])
        labels = (obj.get("Config") or {}).get("Labels") or {}
        if (labels.get("com.docker.compose.project") != PROJECT or
                labels.get("com.docker.compose.service") != svc):
            raise GateError("g0_container_ownership_mismatch")
        if (obj.get("State") or {}).get("Running") is not True:
            raise GateError("g0_service_not_running")
        networks = set((obj.get("NetworkSettings") or {}).get("Networks") or {})
        if networks != {NETWORK}:
            raise GateError("g0_container_wrong_network")
        host = obj.get("HostConfig") or {}
        if host.get("Privileged") is not False or host.get("PortBindings"):
            raise GateError("g0_container_privileged_or_public")
        for m in obj.get("Mounts") or []:
            if m.get("Destination") == "/var/run/docker.sock":
                raise GateError("g0_container_docker_socket_exposed")
    if (inspect("network", NETWORK).get("Internal")) is not True:
        raise GateError("g0_network_not_internal")
    volume_labels = inspect("volume", DATA_VOLUME).get("Labels") or {}
    if volume_labels.get("com.docker.compose.project") != PROJECT:
        raise GateError("g0_volume_ownership_mismatch")

    cmd = compose_args(repo) + ["exec", "-T"]
    run(cmd + ["db", "pg_isready", "-U", "g0", "-d", "g0"],
        env=env, label="g0_db_ready", timeout=25)
    probes = {
        # Router has no API token mounted in inspection mode: route is 503.
        "router": ("http://127.0.0.1:8090", "ok", "/v1/route", "503"),
        "executor": ("http://127.0.0.1:8790", "degraded", "/v1/workspaces", "403"),
        "runtime": ("http://127.0.0.1:8787", "degraded", "/v1/jobs", "503"),
    }
    for svc, (url, status, path, code) in probes.items():
        run(cmd + [svc, "python3", "-c", PROBE_PY,
                   url, status, path, code],
            env=env, label="g0_" + svc + "_inspection_health", timeout=30)
    return {
        "status": "PASS",
        "phase": "inspection_activation",
        "project": PROJECT,
        "container_count": "4",
        "private_network": True,
        "new_g0_db": "healthy",
        "router": "ok",
        "executor": "degraded_health_only",
        "runtime": "degraded_inspection_only",
        "published_ports": "0",
        "ready_to_dispatch_g0d_t01": False,
    }


def activate(repo: Path, fixture: Path, expected_sha: str) -> dict:
    preflight(repo, fixture, expected_sha)
    build_g0_overlays(repo, expected_sha)
    workspace = save_private_state(Path.home(), secrets.token_hex(24), expected_sha)
    _, password, _ = read_private_state(Path.home())
    env = compose_env(repo, fixture, workspace, expected_sha, password)
    run(compose_args(repo) + ["config", "--quiet"],
        env=env, label="compose_config", timeout=40)
    run(compose_args(repo) + [
        "up", "-d", "--no-build", "--pull", "never", "--no-recreate",
        "--wait", "--wait-timeout", "120",
    ], env=env, label="g0_compose_up", timeout=170)
    return verify_inspection(repo, env)


def existing_env(repo: Path, fixture: Path) -> dict[str, str]:
    source, password, workspace = read_private_state(Path.home())
    require_exact_repo(repo, EXPECTED_REPO, "main", source)
    require_exact_repo(fixture, EXPECTED_FIXTURE, "benchmark/pcp", SEED)
    guard_source(repo, fixture)
    return compose_env(repo, fixture, workspace, source, password)


def stop_g0(repo: Path, fixture: Path) -> dict:
    """Rollback only currently running exact-name, exact-owned G0 containers.

    Works after a partial startup without needing passwords or a complete
    Compose topology. Deliberately leaves the DB volume and all source intact.
    """
    owned: list[str] = []
    for svc in G0_SERVICES:
        name = NAMES[svc]
        if not exists("container", name):
            continue
        obj = inspect("container", name)
        labels = (obj.get("Config") or {}).get("Labels") or {}
        if (labels.get("com.docker.compose.project") != PROJECT or
                labels.get("com.docker.compose.service") != svc):
            raise GateError("g0_stop_identity_mismatch")
        if (obj.get("State") or {}).get("Running") is True:
            owned.append(name)
    if owned:
        run(["docker", "stop", "--time", "15", *owned],
            label="g0_exact_owned_stop", timeout=95)
    return {
        "status": "PASS",
        "phase": "g0_only_stopped",
        "running_g0_services_stopped": len(owned),
        "legacy_services_touched": False,
        "g0_db_volume_preserved": True,
        "ready_to_dispatch_g0d_t01": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "activate", "status", "stop"))
    parser.add_argument("--expected-sha", default="")
    args = parser.parse_args()
    repo = Path.home() / "personal-coding-platform-v1"
    fixture = Path.home() / "pcp-g0-fixtures/pcp-g0-drupal-fixture"
    try:
        if args.mode == "preflight":
            outcome = preflight(repo, fixture, args.expected_sha)
        elif args.mode == "activate":
            outcome = activate(repo, fixture, args.expected_sha)
        elif args.mode == "status":
            outcome = verify_inspection(repo, existing_env(repo, fixture))
        else:
            outcome = stop_g0(repo, fixture)
    except (GateError, OSError, KeyError, TypeError, ValueError,
            yaml.YAMLError) as exc:
        # Report one stable blocker class, never raw Docker/Git/Compose output.
        print(json.dumps({
            "status": "STOP",
            "mode": args.mode,
            "reason": str(exc) if isinstance(exc, GateError)
                      else "unexpected_metadata_or_source_error",
            "do_not_retry_blindly": True,
            "ready_to_dispatch_g0d_t01": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
