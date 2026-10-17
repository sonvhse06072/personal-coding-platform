"""Owner-approved, default-off G1 Codex developer tool scope.

Only a new disposable singleton fixture can receive the narrowly scoped phase
broker token. This is NOT trusted_local (host shell), and must never grant
the Executor control-plane bearer or Docker/GitHub credentials to Codex.
"""
from __future__ import annotations

import os
import re
import hashlib
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from .config import projects_doc

_JOB = re.compile(r"^[a-f0-9]{32}$")
_SHA = re.compile(r"^[a-f0-9]{40}$")
_DISPOSABLE = re.compile(r"^pcp-benchmark-[a-z0-9-]{2,80}$")
_SMOKE_ID = "pcp-benchmark-g1-smoke"
_PILOT_ID = "pcp-benchmark-g1-pilot"
_T02_ID = "pcp-benchmark-g1-t02"
_SEED_SHA = "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
_PILOT_DDEV_SEED_SHA = "7a3e97a2a35fc8e67b67021365e7e91c448b52c9"
_PILOT_NAME_OVERRIDE = "override_config: true\nname: pcp-g1-codex-pilot\n"
_PILOT_CACHE_FILE = "docker-compose.g1-pilot.yaml"
_PILOT_CACHE_COMPOSE = (
    "# G1-T01 private DDEV cache; never model editable.\n"
    "services:\n"
    "  web:\n"
    "    volumes:\n"
    "      - g1-pilot-private-cache:/mnt/ddev-global-cache\n"
    "  db:\n"
    "    volumes:\n"
    "      - g1-pilot-private-cache:/mnt/ddev-global-cache\n"
    "volumes:\n"
    "  g1-pilot-private-cache:\n"
    "    external: true\n"
    "    name: pcp-g1-pilot-cache\n"
)
_T02_NAME_OVERRIDE = "override_config: true\nname: pcp-g1-codex-t02\n"
_T02_CACHE_FILE = "docker-compose.g1-t02.yaml"
_T02_CACHE_COMPOSE = (
    "# G1-T02 private DDEV cache; never model editable.\n"
    "services:\n"
    "  web:\n"
    "    volumes:\n"
    "      - g1-t02-private-cache:/mnt/ddev-global-cache\n"
    "  db:\n"
    "    volumes:\n"
    "      - g1-t02-private-cache:/mnt/ddev-global-cache\n"
    "volumes:\n"
    "  g1-t02-private-cache:\n"
    "    external: true\n"
    "    name: pcp-g1-t02-cache\n"
)
_ALLOWED_HOSTS = frozenset({"ddev-executor", "pcp-dev-executor"})
_PROTECTED_ENV = (
    "PLATFORM_INTERNAL_TOKEN", "ROUTER_API_TOKEN",
    "RUNTIME_API_TOKEN", "GITHUB_DELIVERY_TOKEN",
    "ANTIGRAVITY_BRIDGE_TOKEN",
)


def _git_read(workspace: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(workspace), *args],
            capture_output=True, text=True, timeout=8,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def trusted_codex_phase_broker(
    *,
    job_id: str,
    project_id: str,
    source_commit: str,
    workspace: Path,
    mode: str,
    adapter: str,
) -> dict[str, str] | None:
    """Admit precisely one isolated execute/repair job; never implicitly enable."""
    flag = os.getenv("PCP_TRUSTED_CODEX_BROKER_ENABLED", "")
    if not flag:
        return None
    if flag != "owner-approved":
        return None
    if mode not in {"execute", "repair"} or adapter != "codex_cli":
        return None
    configured_project = os.getenv("PCP_TRUSTED_CODEX_PROJECT_ID", "")
    configured_job = os.getenv("PCP_TRUSTED_CODEX_JOB_ID", "")
    configured_sha = os.getenv("PCP_TRUSTED_CODEX_SOURCE_SHA", "")
    token = os.getenv("PCP_TRUSTED_CODEX_DEV_TOKEN", "")
    url = os.getenv("PCP_TRUSTED_CODEX_BROKER_URL", "")
    root_text = os.getenv("CODING_WORKSPACES_ROOT", "")
    deadline = os.getenv("PCP_TRUSTED_CODEX_DEADLINE_EPOCH", "")
    now_epoch = int(time.time())
    if not (deadline.isascii() and deadline.isdecimal() and len(deadline) <= 12):
        return None
    seconds_remaining = int(deadline) - now_epoch
    if not 0 < seconds_remaining <= 1800:
        return None
    if not (
        _DISPOSABLE.fullmatch(project_id)
        and configured_project == project_id
        and _JOB.fullmatch(job_id) and configured_job == job_id
        and _SHA.fullmatch(source_commit)
        and configured_sha == source_commit
        and re.fullmatch(r"[A-Za-z0-9_-]{40,128}", token)
        and root_text
    ):
        return None
    if token in {os.getenv(k, "") for k in _PROTECTED_ENV}:
        return None
    try:
        parsed = urlsplit(url)
        if not (
            parsed.scheme == "http"
            and parsed.hostname in _ALLOWED_HOSTS
            and parsed.port == 8790
            and not (parsed.username or parsed.password or parsed.path
                     or parsed.query or parsed.fragment)
        ):
            return None
    except ValueError:
        return None

    try:
        root = Path(root_text).resolve(strict=True)
        expected = root / job_id
        if (
            workspace.is_symlink()
            or expected.is_symlink()
            or workspace.resolve(strict=True) != expected.resolve(strict=True)
            or workspace.resolve(strict=True).parent != root
        ):
            return None
    except (OSError, RuntimeError):
        return None

    if project_id not in {_SMOKE_ID, _PILOT_ID, _T02_ID}:
        return None
    if project_id == _PILOT_ID:
        if (
            os.getenv("PCP_G1_PILOT_IDENTITY_ENABLED") != "owner-approved"
            or source_commit != _SEED_SHA
        ):
            return None
        # Runtime reads only its job workspace. The executor performs its own
        # independent Docker attestation at each phase. This is a source-only
        # admission check, not evidence that a model may be dispatched.
        ddev = workspace / ".ddev"
        try:
            seed = (ddev / "config.yaml").read_bytes()
            blob = hashlib.sha1(
                b"blob " + str(len(seed)).encode() + b"\0" + seed
            ).hexdigest()
            if blob != _PILOT_DDEV_SEED_SHA or ddev.is_symlink():
                return None
            overrides = {
                "config.g1-pilot.yaml": _PILOT_NAME_OVERRIDE,
                _PILOT_CACHE_FILE: _PILOT_CACHE_COMPOSE,
            }
            for name, exact in overrides.items():
                f = ddev / name
                if f.is_symlink() or f.read_text(encoding="utf-8") != exact:
                    return None
            if any(p.is_symlink() for p in ddev.rglob("*")):
                return None
            if (ddev / "commands").exists() or (ddev / "hooks").exists():
                return None
            if ({p.name for p in ddev.glob("config*.y*ml")} -
                {"config.yaml", "config.g1-pilot.yaml"}):
                return None
            if ({p.name for p in ddev.glob("docker-compose*.y*ml")} -
                {_PILOT_CACHE_FILE}):
                return None
        except (OSError, UnicodeError):
            return None

    if project_id == _T02_ID:
        # T02 cannot inherit T01 identity; both flags and DDEV overrides
        # are independent, and live Docker attestation remains Executor-owned.
        if (os.getenv("PCP_G1_T02_IDENTITY_ENABLED") != "owner-approved"
                or source_commit != _SEED_SHA):
            return None
        ddev = workspace / ".ddev"
        try:
            if ddev.is_symlink() or not ddev.is_dir():
                return None
            seed = ddev / "config.yaml"
            if seed.is_symlink():
                return None
            data = seed.read_bytes()
            blob = hashlib.sha1(
                b"blob " + str(len(data)).encode() + b"\0" + data
            ).hexdigest()
            if blob != _PILOT_DDEV_SEED_SHA:
                return None
            for name, expected_text in {
                "config.g1-t02.yaml": _T02_NAME_OVERRIDE,
                _T02_CACHE_FILE: _T02_CACHE_COMPOSE,
            }.items():
                item = ddev / name
                if item.is_symlink() or item.read_text(encoding="utf-8") != expected_text:
                    return None
            if (ddev / "commands").exists() or (ddev / "hooks").exists():
                return None
            if any(item.is_symlink() for item in ddev.rglob("*")):
                return None
            if ({item.name for item in ddev.glob("config*.y*ml")}
                    - {"config.yaml", "config.g1-t02.yaml"}):
                return None
            if ({item.name for item in ddev.glob("docker-compose*.y*ml")}
                    - {_T02_CACHE_FILE}):
                return None
        except (OSError, UnicodeError):
            return None

    registry = projects_doc().get("projects")
    if not isinstance(registry, dict) or set(registry) != {project_id}:
        return None
    project = registry[project_id]
    runtime = project.get("runtime") if isinstance(project, dict) else None
    ddev = project.get("ddev") if isinstance(project, dict) else None
    autonomy = project.get("autonomy") if isinstance(project, dict) else None
    if not (
        isinstance(runtime, dict)
        and runtime.get("developer_permission_mode") == "trusted_project"
        and runtime.get("workspace_mode") == "isolated_clone"
        and runtime.get("exclusive_project_lease") is False
        and runtime.get("branch_prefix") == "ai"
        and isinstance(ddev, dict) and ddev.get("enabled") is True
        and isinstance(autonomy, dict)
        and autonomy.get("allow_auto_merge_low_risk") is False
        and autonomy.get("allow_production_deploy") is False
    ):
        return None

    if project_id == _PILOT_ID and not (
        runtime.get("pilot_identity") == "g1-t01-pcp"
        and project.get("base_branch") == "benchmark/g1-codex-smoke-v1"
    ):
        return None

    if project_id == _T02_ID and not (
        runtime.get("pilot_identity") == "g1-t02-pcp"
        and project.get("base_branch") == "benchmark/g1-codex-smoke-v1"
        and all(autonomy.get(k) is False for k in (
            "allow_commit", "allow_push_ai_branch", "allow_create_pr"
        ))
    ):
        return None

    if (
        _git_read(workspace, "rev-parse", "--show-toplevel") != str(expected)
        or _git_read(workspace, "branch", "--show-current") != "ai/" + job_id[:12]
        or _git_read(workspace, "rev-parse", "HEAD") != source_commit
    ):
        return None
    return {
        "PCP_DEV_BROKER_URL": url,
        "PCP_DEV_BROKER_TOKEN": token,
        "PCP_DEV_JOB_ID": job_id,
        "PCP_DEV_PROJECT_ID": project_id,
        "PCP_DEV_WORKSPACE": str(expected),
        "PCP_DEV_SOURCE_SHA": source_commit,
    }
