from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .g1_ddev_isolation import (
    PROJECT_ID as G1_PROJECT_ID, G1IsolationStop, require_g1_isolated_ddev,
)
from .g1_pilot_ddev_identity import (
    PROJECT_ID as G1_PILOT_ID,
    SOURCE_SHA as G1_PILOT_SHA,
    require_pilot_workspace_identity,
    require_g1_pilot_isolated_ddev,
)
from .g1_t02_ddev_identity import (
    PROJECT_ID as G1_T02_ID,
    SOURCE_SHA as G1_T02_SHA,
    require_t02_workspace_identity,
    require_g1_t02_isolated_ddev,
)
from .github_delivery import (
    GitHubDelivery,
    github_git_env,
    github_push_url,
    github_repository_from_origin,
    g1_t02_ci_status,
    FIXTURE_REPO as G1_T02_DELIVERY_REPO,
    SEED_SHA as G1_T02_DELIVERY_SEED,
    ALLOWED_PATHS as G1_T02_DELIVERY_PATHS,
)
from .pm_bridge_github import router as pm_bridge_github_router


Phase = Literal["preflight", "targeted_tests", "static_analysis", "frontend_quality", "visual_quality", "full_tests", "cleanup"]
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class PhaseRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    phase: Phase
    timeout_seconds: int | None = Field(default=None, ge=10, le=3600)


class WorkspaceRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    ref: str | None = Field(default=None, max_length=200)
    workspace_mode: Literal["project_default", "isolated_clone"] = "project_default"


class SyncDirectBaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=200)
    expected_remote_head: str = Field(pattern=r"^[0-9a-fA-F]{40}$")


class PublishBranchRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    branch: str = Field(min_length=1, max_length=200)
    source_commit: str = Field(min_length=7, max_length=64)
    expected_commit: str = Field(min_length=7, max_length=64)
    review_repair_pr_number: int | None = Field(default=None, ge=1)
    review_repair_previous_commit: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{40}$",
    )


class PullRequestRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    branch: str = Field(min_length=1, max_length=200)
    expected_commit: str = Field(min_length=7, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=30000)
    expected_pr_number: int | None = Field(default=None, ge=1)


class ReconcileDeliveryRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    branch: str = Field(min_length=1, max_length=200)
    source_commit: str = Field(min_length=7, max_length=64)
    expected_commit: str = Field(min_length=7, max_length=64)


class ReviewRepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    branch: str = Field(min_length=1, max_length=200)
    source_commit: str = Field(min_length=7, max_length=64)
    expected_commit: str = Field(min_length=7, max_length=64)
    pr_number: int = Field(ge=1)


class CancelRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)


class QuiesceWorkspaceRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    remove_data: bool = False


class OrphanResourcesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str | None = Field(default=None, max_length=2000)
    execute: bool = False


class ReturnDirectWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    branch: str = Field(min_length=1, max_length=200)


class AdvanceDirectWorkspaceSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    branch: str = Field(min_length=1, max_length=200)
    old_source: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    new_source: str = Field(pattern=r"^[0-9a-fA-F]{40}$")


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    target: Literal["frontend", "backend", "both"]


class CommandOutput(BaseModel):
    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class PhaseResponse(BaseModel):
    passed: bool
    phase: Phase
    commands: list[CommandOutput]
    infrastructure: list[CommandOutput] = Field(default_factory=list)


_ACTIVE: dict[str, subprocess.Popen] = {}
_ACTIVE_LOCK = threading.Lock()
_ORPHAN_RESOURCE_LOCK = threading.Lock()


def auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("PLATFORM_INTERNAL_TOKEN", "").strip()
    if not expected or expected in {"CHANGE_ME", "change-me"}:
        raise HTTPException(503, "PLATFORM_INTERNAL_TOKEN is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    if not secrets.compare_digest(authorization.removeprefix("Bearer ").strip(), expected):
        raise HTTPException(401, "Invalid bearer token")


G0_FIXTURE_PROJECT_ID = "pcp-g0-drupal-fixture"
G0_FIXTURE_PATH = "${CODING_PROJECTS_ROOT}/pcp-g0-fixtures/pcp-g0-drupal-fixture"
# Parked G0 registration authorizes no local work. A separate protected
# activation patch must explicitly enable project-bound operations; merely
# setting the G0 scope cannot create workspaces, run DDEV or send deliveries.
# Generic cancel/orphan/PM Bridge/host operations stay outside that boundary.
G0_FIXTURE_API_ROUTES = frozenset({("GET", "/health")})
G0_SOURCE_COMMIT = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
G0_FIXTURE_REPOSITORY = "sonvhse06072/pcp-g0-drupal-fixture"
G0_SOURCE_PATH = Path("/g0/sources/pcp-g0-fixtures/pcp-g0-drupal-fixture")
G0_WORKSPACE_PATH = Path("/g0/workspaces")
G0_EXECUTION_ROUTES = frozenset({("POST", "/v1/workspaces")})
G0_DELIVERY_ROUTES = frozenset({
    ("POST", "/v1/publish-branch"),
    ("POST", "/v1/github/pull-request"),
    ("GET", "/v1/github/ci"),
})


# F2 source is independently pinned to the NEW v2 fixture, never G0D-T01.
# Live Compose is still /bin/false with this activation variable ABSENT.
# The C3A code path is a future C3B attachment point, not an OCI permission.
F2_PARKED_EXECUTOR_ENV = {
    "PCP_EXECUTOR_PROJECT_SCOPE": "pcp-g0-fullpath-fixture",
    "PROJECTS_FILE": "/fullpath/config/projects.yml",
    "CODING_PROJECTS_ROOT": "/fullpath/sources",
    "CODING_WORKSPACES_ROOT": "/fullpath/workspaces",
    "CODING_DIRECT_PROJECT_ROOT": "/fullpath/direct-disabled",
}
F2_FIXTURE_REPOSITORY = "sonvhse06072/pcp-g0-fullpath-fixture"
F2_FIXTURE_SOURCE = "3165b76d44b738c4709c3ca74f87297ff66dd397"
F2_FIXTURE_BRANCH = "benchmark/fullpath-v2"
F2_FIXTURE_PATH = Path("/fullpath/sources/pcp-g0-fullpath-fixture")
F2_GIT_ONLY_ROUTES = frozenset({
    ("GET", "/health"),
    ("POST", "/v1/workspaces"),
    ("POST", "/v1/publish-branch"),
    ("POST", "/v1/github/pull-request"),
    ("GET", "/v1/github/ci"),
    ("POST", "/v1/github/reconcile-delivery"),
    ("POST", "/v1/github/review-repair"),
})
F2_ALLOWED_CHANGED_FILES = frozenset({
    "web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php",
    "web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php",
    "web/modules/custom/pcp_f2_fixture/tests/src/Kernel/WindowOverlapServiceTest.php",
})


def _f2_git_only_route_allowed(method: str, path: str) -> bool:
    if (method, path) in F2_GIT_ONLY_ROUTES:
        return True
    if method != "GET":
        return False
    return bool(re.fullmatch(
        r"/v1/github/pm-bridge/pulls/[1-9][0-9]*"
        r"(?:/reviews/[1-9][0-9]*)?", path,
    ))


def _f2_scope_present() -> bool:
    """Any F2 root marker implies ALL roots; a partial env fails closed."""
    matched = any(
        os.getenv(key) == expected
        for key, expected in F2_PARKED_EXECUTOR_ENV.items()
    )
    if not matched:
        return False
    if any(
        os.getenv(key) != expected
        for key, expected in F2_PARKED_EXECUTOR_ENV.items()
    ):
        raise HTTPException(503, "F2 Executor source-only identity mismatch")
    return True


def _f2_git_only_scoped() -> bool:
    if not _f2_scope_present():
        return False
    flag = os.getenv("PCP_F2_GIT_ONLY_ENABLED", "")
    if not flag:
        return False
    if flag != "owner-approved":
        raise HTTPException(503, "F2 Git-only activation value invalid")
    if Path("/var/run/docker.sock").exists():
        raise HTTPException(503, "F2 must never mount host Docker socket")
    if any(os.getenv(k) for k in (
        "PCP_G0_EXECUTION_ENABLED", "PCP_G0_DELIVERY_ENABLED",
        "ANTIGRAVITY_BRIDGE_TOKEN", "PCP_FULLPATH_OPERATIONAL_ACTIVATION",
    )):
        raise HTTPException(503, "F2 cannot inherit legacy activation or provider secret")
    return True


def _f2_parked_executor_scope() -> bool:
    """Existing parked source still denies every route, including direct calls."""
    return _f2_scope_present() and not _f2_git_only_scoped()


def _require_f2_source_repository(cfg: dict[str, Any]) -> None:
    # Source mounts must be a pinned, immutable v2 clone and exact fixture origin.
    raw = Path(os.path.expandvars(str(cfg.get("path", ""))))
    if raw.is_symlink() or raw.resolve() != F2_FIXTURE_PATH:
        raise HTTPException(403, "F2 source mount identity mismatch")
    source = _configured_project_path(cfg)
    if source != F2_FIXTURE_PATH or source.is_symlink():
        raise HTTPException(403, "F2 source path identity mismatch")
    if git(source, "rev-parse", "HEAD") != F2_FIXTURE_SOURCE:
        raise HTTPException(409, "F2 fixture source differs from pinned v2 seed")
    origin = remote_origin(source)
    if github_repository_from_origin(origin or "") != F2_FIXTURE_REPOSITORY:
        raise HTTPException(403, "F2 source remote is outside exact fixture repository")


def _validate_f2_registry(projects: Any) -> None:
    if not isinstance(projects, dict) or set(projects) != {"pcp-g0-fullpath-fixture"}:
        raise HTTPException(503, "F2 requires singleton fixture registry")
    cfg = projects["pcp-g0-fullpath-fixture"]
    if not isinstance(cfg, dict) or (
        cfg.get("path") != "${CODING_PROJECTS_ROOT}/pcp-g0-fullpath-fixture"
        or cfg.get("base_branch") != F2_FIXTURE_BRANCH
        or not isinstance(cfg.get("runtime"), dict)
        or cfg["runtime"].get("workspace_mode") != "isolated_clone"
        or cfg["runtime"].get("exclusive_project_lease") is not False
        or cfg["runtime"].get("branch_prefix") != "ai"
        or not isinstance(cfg.get("ddev"), dict)
        or cfg["ddev"].get("enabled") is not False
        or not isinstance(cfg.get("autonomy"), dict)
        or not all(cfg["autonomy"].get(k) is True for k in (
            "allow_commit", "allow_push_ai_branch", "allow_create_pr"
        ))
        or cfg["autonomy"].get("allow_auto_merge_low_risk") is not False
        or cfg["autonomy"].get("allow_production_deploy") is not False
    ):
        raise HTTPException(503, "F2 candidate registry has not been separately activated")
    _require_f2_source_repository(cfg)


def _require_f2_delivery_contract(
    cfg: dict[str, Any], *, job_id: str, branch: str,
    source_commit: str | None = None,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(403, "F2 delivery requires exact job UUID")
    if branch != "ai/" + job_id[:12]:
        raise HTTPException(403, "F2 branch must match the exact job")
    if source_commit is not None and source_commit != F2_FIXTURE_SOURCE:
        raise HTTPException(403, "F2 delivery source differs from pinned seed")
    _require_f2_source_repository(cfg)


def _verify_f2_delivered_diff(
    workspace: Path, source_commit: str, expected_commit: str,
) -> None:
    if source_commit != F2_FIXTURE_SOURCE or not re.fullmatch(
        r"[0-9a-f]{40}", expected_commit
    ):
        raise HTTPException(403, "F2 diff source/head identity invalid")
    if git(workspace, "status", "--porcelain", check=False):
        raise HTTPException(409, "F2 delivery workspace must be clean")
    changed = git(
        workspace, "diff", "--name-only", source_commit, expected_commit
    ).splitlines()
    if (not changed or len(changed) != len(set(changed))
            or not set(changed).issubset(F2_ALLOWED_CHANGED_FILES)):
        raise HTTPException(403, "F2 diff includes unapproved or missing source/test files")


def _g0_fixture_activation_flag(name: str) -> bool:
    value = os.getenv(name, "")
    if not value:
        return False
    if value != "owner-approved":
        raise HTTPException(503, "Invalid G0 fixture activation flag")
    if not _g0_fixture_scoped():
        raise HTTPException(503, "G0 activation requires isolated Executor scope")
    if Path("/var/run/docker.sock").exists():
        raise HTTPException(503, "G0 Executor must not mount the host Docker socket")
    if (os.getenv("CODING_PROJECTS_ROOT") != "/g0/sources"
            or os.getenv("CODING_WORKSPACES_ROOT") != "/g0/workspaces"
            or os.getenv("CODING_DIRECT_PROJECT_ROOT") != "/g0/direct-disabled"):
        raise HTTPException(503, "G0 Executor roots are not isolated")
    return True


def _g0_fixture_execution_enabled() -> bool:
    return _g0_fixture_activation_flag("PCP_G0_EXECUTION_ENABLED")


def _g0_fixture_delivery_enabled() -> bool:
    return (
        _g0_fixture_execution_enabled()
        and _g0_fixture_activation_flag("PCP_G0_DELIVERY_ENABLED")
    )


def _require_g0_source_repository(cfg: dict[str, Any]) -> None:
    source = _configured_project_path(cfg)
    if source != G0_SOURCE_PATH or source.is_symlink():
        raise HTTPException(403, "G0 source checkout identity mismatch")
    head = git(source, "rev-parse", "HEAD")
    if head != G0_SOURCE_COMMIT:
        raise HTTPException(409, "G0 source checkout differs from frozen seed")
    origin = remote_origin(source)
    if github_repository_from_origin(origin or "") != G0_FIXTURE_REPOSITORY:
        raise HTTPException(403, "G0 source is not the exact private fixture repository")



def _g0_fixture_scoped() -> bool:
    """Optional narrower executor surface; never a host Docker security boundary."""
    if _f2_git_only_scoped():
        return False
    scope = os.getenv("PCP_EXECUTOR_PROJECT_SCOPE", "")
    if not scope:
        return False
    if scope != G0_FIXTURE_PROJECT_ID:
        raise HTTPException(503, "Invalid Executor project scope")
    return True


def _validate_g0_registry(projects: Any) -> None:
    if not isinstance(projects, dict) or set(projects) != {G0_FIXTURE_PROJECT_ID}:
        raise HTTPException(503, "Executor scoped registry must contain only the G0 fixture")
    cfg = projects[G0_FIXTURE_PROJECT_ID]
    if not isinstance(cfg, dict) or (
        cfg.get("path") != G0_FIXTURE_PATH
        or cfg.get("base_branch") != "benchmark/pcp"
        or not isinstance(cfg.get("runtime"), dict)
        or cfg["runtime"].get("workspace_mode") != "isolated_clone"
        or cfg["runtime"].get("exclusive_project_lease") is not False
    ):
        raise HTTPException(503, "Executor scoped fixture identity is invalid")


def load_projects() -> dict[str, Any]:
    if _f2_parked_executor_scope():
        # No read of an unapproved F2 mount or generic multi-project registry.
        raise HTTPException(503, "F2 Executor remains source-only (PARKED)")
    with open(os.getenv("PROJECTS_FILE", "/config/projects.yml"), "r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    if not isinstance(document, dict):
        raise HTTPException(503, "Invalid executor project registry")
    projects = document.get("projects", {})
    if _f2_git_only_scoped():
        _validate_f2_registry(projects)
    elif _g0_fixture_scoped():
        _validate_g0_registry(projects)
    return projects


def expand(value: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(value))).resolve()


def project(project_id: str) -> dict[str, Any]:
    if _f2_parked_executor_scope():
        raise HTTPException(503, "F2 Executor remains source-only (PARKED)")
    # This check also protects direct internal handler calls that bypass HTTP.
    if _f2_git_only_scoped() and project_id != "pcp-g0-fullpath-fixture":
        raise HTTPException(403, "Project outside isolated F2 Executor scope")
    if _g0_fixture_scoped() and project_id != G0_FIXTURE_PROJECT_ID:
        raise HTTPException(403, "Project outside isolated G0 Executor scope")
    projects = load_projects()
    if project_id not in projects:
        raise HTTPException(404, "Unknown project")
    return projects[project_id]


def _require_ddev_enabled(cfg: dict[str, Any]) -> None:
    """A PARKED project cannot execute DDEV phases even via direct API calls.

    Require the YAML boolean true, not merely a truthy string. This gate
    precedes workspace mutation and any DDEV process; authorization, project
    registry and job-specific workspace ownership remain separate checks.
    """
    ddev = cfg.get("ddev")
    if not isinstance(ddev, dict) or ddev.get("enabled") is not True:
        raise HTTPException(409, "Project DDEV is disabled (PARKED)")


def _workspace_mode(cfg: dict[str, Any]) -> str:
    runtime = cfg.get("runtime", {}) or {}
    mode = str(runtime.get("workspace_mode") or "isolated_clone").strip()
    if mode not in {"isolated_clone", "direct"}:
        raise HTTPException(500, f"Unsupported configured workspace_mode: {mode!r}")
    if mode == "direct":
        if not bool(runtime.get("exclusive_project_lease", False)):
            raise HTTPException(500, "Direct workspace mode requires exclusive_project_lease=true")
        approved = os.getenv("CODING_DIRECT_PROJECT_ROOT", "").strip()
        if not approved:
            raise HTTPException(500, "CODING_DIRECT_PROJECT_ROOT is not configured")
        configured = expand(str(cfg.get("path", "")))
        if configured != expand(approved):
            raise HTTPException(
                500,
                "Direct workspace path must match CODING_DIRECT_PROJECT_ROOT exactly",
            )
    return mode


def _configured_project_path(cfg: dict[str, Any]) -> Path:
    path = expand(str(cfg.get("path", "")))
    if not is_git_repo(path):
        raise HTTPException(422, f"Configured path is not a git repository: {path}")
    return path


def allowed_workspace(path: Path) -> bool:
    root = Path(os.environ["CODING_WORKSPACES_ROOT"]).resolve()
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise HTTPException(422, proc.stderr.strip() or proc.stdout.strip() or "git command failed")
    return proc.stdout.strip()


def is_git_repo(repo: Path) -> bool:
    if not repo.exists() or not repo.is_dir():
        return False
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-dir"],
        text=True,
        capture_output=True,
    )
    return proc.returncode == 0


def _has_git_commit(repo: Path, commit: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", commit + "^{commit}"],
        text=True,
        capture_output=True,
    )
    return proc.returncode == 0


def _materialize_commit_from_source_refs(
    source_repo: Path,
    workspace: Path,
    source_commit: str,
    *,
    base_branch: str,
) -> None:
    """Materialize one exact source commit without mutating the source worktree.

    A direct project may be parked on a historical AI branch while a newer
    governed baseline exists only under refs/remotes/origin/*. A normal clone
    of the local repository advertises local heads/tags, so that newer commit
    can be absent even though the source object store can resolve it. Fetch one
    containing source ref by name into a private workspace ref, then remove it
    after the exact commit is checked out.
    """
    if _has_git_commit(workspace, source_commit):
        return

    refs = [
        value
        for value in git(
            source_repo,
            "for-each-ref",
            "--format=%(refname)",
            "--contains",
            source_commit,
            "refs/remotes/origin",
            "refs/heads",
            "refs/tags",
            check=False,
        ).splitlines()
        if value
    ]
    preferred = f"refs/remotes/origin/{base_branch}"
    refs.sort(
        key=lambda value: (
            0 if value == preferred else
            1 if value.startswith("refs/remotes/origin/") else
            2 if value.startswith("refs/heads/") else
            3,
            value,
        )
    )
    if not refs:
        raise HTTPException(
            422,
            f"Exact source commit {source_commit} is not reachable from any trusted local source ref",
        )

    temp_ref = "refs/pcp/materialized-source"
    failures: list[str] = []
    for source_ref in refs:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(workspace),
                "fetch",
                "--no-tags",
                "origin",
                f"+{source_ref}:{temp_ref}",
            ],
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0 and _has_git_commit(workspace, source_commit):
            return
        detail = (proc.stderr or proc.stdout or "fetch failed").strip()
        failures.append(f"{source_ref}: {detail[-1000:]}")

    raise HTTPException(
        422,
        (
            f"Exact source commit {source_commit} could not be materialized "
            f"from trusted local source refs: {'; '.join(failures)[:8000]}"
        ),
    )


def remote_origin(repo: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
    )
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and value else None


def _workspace_instance_mode(
    cfg: dict[str, Any],
    *,
    job_id: str,
    path: Path,
) -> str:
    """Classify the concrete workspace, not only the project's default mode.

    Direct projects may intentionally request a disposable isolated clone for
    read-only internal work such as PM planning. Those clones keep the normal
    job-id/root boundary and must still be removable/quiesceable as isolated
    workspaces.
    """
    configured_mode = _workspace_mode(cfg)
    if configured_mode == "direct":
        configured = _configured_project_path(cfg)
        if path == configured:
            return "direct"

    root = Path(os.environ["CODING_WORKSPACES_ROOT"]).resolve()
    if allowed_workspace(path) and path.name == job_id and path.parent == root:
        return "isolated_clone"
    if configured_mode == "direct":
        raise HTTPException(
            403,
            "Workspace is neither the configured direct project nor the exact isolated job workspace",
        )
    raise HTTPException(403, "Workspace is outside configured root or does not match job")


def _validate_workspace(
    job_id: str,
    project_id: str,
    workspace: str,
    *,
    require_git: bool = True,
) -> Path:
    cfg = project(project_id)
    path = Path(workspace).resolve()
    mode = _workspace_instance_mode(cfg, job_id=job_id, path=path)
    if mode == "direct":
        return path
    if not path.exists():
        raise HTTPException(404, "Workspace does not exist")
    if require_git and not is_git_repo(path):
        raise HTTPException(404, "Workspace is not a git repository")
    return path


_PREVIEW_OVERRIDE_REL = Path(".ddev/config.pcp-preview.local.yaml")
_PREVIEW_MARKER = "# PCP-managed direct live preview; do not commit."
_PREVIEW_EXCLUDE = ".ddev/config.pcp-preview.local.yaml"
_DIRECT_NODE_OVERRIDE_REL = Path(".ddev/config.pcp-node.local.yaml")
_DIRECT_NODE_MARKER = "# PCP-managed direct Node runtime; do not commit."
_DIRECT_NODE_EXCLUDE = ".ddev/config.pcp-node.local.yaml"


def _direct_nodejs_version(cfg: dict[str, Any]) -> str:
    value = str((cfg.get("ddev") or {}).get("workspace_nodejs_version") or "").strip()
    if not value:
        raise HTTPException(
            500,
            "Direct frontend preview/verification requires ddev.workspace_nodejs_version",
        )
    if not re.fullmatch(r"\d{1,2}(?:\.\d{1,2})?", value):
        raise HTTPException(500, "Invalid configured workspace_nodejs_version")
    return value


def _preview_contract(cfg: dict[str, Any], target: str) -> dict[str, Any]:
    preview = cfg.get("preview") or {}
    if not isinstance(preview, dict):
        raise HTTPException(500, "Configured preview contract must be an object")
    backend = preview.get("backend") or {}
    frontend = preview.get("frontend") or {}
    if target in {"backend", "both"} and not bool(
        isinstance(backend, dict) and backend.get("enabled", False)
    ):
        raise HTTPException(409, "Backend preview is not enabled for this project")
    if target in {"backend", "both"} and not _safe_preview_url(backend.get("url")):
        raise HTTPException(500, "Backend preview requires a local DDEV URL")
    if target in {"frontend", "both"}:
        _direct_nodejs_version(cfg)
        if not bool(isinstance(frontend, dict) and frontend.get("enabled", False)):
            raise HTTPException(409, "Frontend preview is not enabled for this project")
        daemon = frontend.get("daemon") or {}
        if not isinstance(daemon, dict):
            raise HTTPException(500, "Frontend preview daemon config is invalid")
        required = ("name", "command", "directory", "container_port", "http_port", "https_port")
        if any(daemon.get(key) is None or daemon.get(key) == "" for key in required):
            raise HTTPException(500, "Frontend preview daemon config is incomplete")
        daemon_name = str(daemon.get("name") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", daemon_name):
            raise HTTPException(500, "Frontend preview daemon name is invalid")
        directory = str(daemon.get("directory") or "").strip()
        if not (
            directory == "/var/www/html"
            or directory.startswith("/var/www/html/")
        ):
            raise HTTPException(500, "Frontend preview daemon directory must stay under /var/www/html")
        for key in ("container_port", "http_port", "https_port"):
            value = daemon.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
                raise HTTPException(500, f"Frontend preview {key} must be a valid port")
        prepare = frontend.get("prepare") or []
        if (
            not isinstance(prepare, list)
            or any(not isinstance(item, str) or not item.strip() for item in prepare)
        ):
            raise HTTPException(500, "Frontend preview prepare must be a list of configured commands")
        if not _safe_preview_url(frontend.get("url")):
            raise HTTPException(500, "Frontend preview requires a local DDEV URL")
        if target == "both" and not _safe_preview_url(frontend.get("api_origin_on_both")):
            raise HTTPException(500, "Both preview requires a local DDEV API origin")
    return {"backend": dict(backend), "frontend": dict(frontend)}


def _safe_preview_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > 500:
        raise HTTPException(500, "Preview URL must be bounded")
    parsed = urlsplit(text)
    hostname = str(parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".ddev.site")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(500, "Preview URL must be a local HTTPS DDEV URL")
    return text


def _preview_override_path(workspace: Path) -> Path:
    return (workspace / _PREVIEW_OVERRIDE_REL).resolve()


def _ensure_local_git_exclude(workspace: Path, entry: str) -> None:
    git_dir_text = git(workspace, "rev-parse", "--git-dir")
    git_dir = Path(git_dir_text)
    if not git_dir.is_absolute():
        git_dir = (workspace / git_dir).resolve()
    expected = (workspace / ".git").resolve()
    if git_dir.resolve() != expected:
        raise HTTPException(409, "Direct preview requires the repository's normal .git directory")
    info = git_dir / "info"
    info.mkdir(parents=True, exist_ok=True)
    exclude = info / "exclude"
    current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    lines = current.splitlines()
    if entry not in lines:
        suffix = "" if not current or current.endswith("\n") else "\n"
        exclude.write_text(
            current + suffix + entry + "\n",
            encoding="utf-8",
        )


def _direct_node_override_path(workspace: Path) -> Path:
    return (workspace / _DIRECT_NODE_OVERRIDE_REL).resolve()


def _write_direct_node_override(workspace: Path, nodejs_version: str) -> Path:
    path = _direct_node_override_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_local_git_exclude(workspace, _DIRECT_NODE_EXCLUDE)
    content = (
        _DIRECT_NODE_MARKER
        + "\n"
        + f'nodejs_version: "{nodejs_version}"\n'
    )
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")
    return path


def _remove_managed_direct_node_override(workspace: Path) -> bool:
    path = _direct_node_override_path(workspace)
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    if not content.startswith(_DIRECT_NODE_MARKER + "\n"):
        raise HTTPException(409, "Existing direct Node override is not PCP-owned")
    path.unlink()
    return True


def _remove_managed_preview_override(workspace: Path) -> bool:
    path = _preview_override_path(workspace)
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    if not content.startswith(_PREVIEW_MARKER + "\n"):
        raise HTTPException(409, "Existing preview override is not PCP-owned")
    path.unlink()
    return True


def _write_preview_override(
    workspace: Path,
    *,
    frontend: dict[str, Any],
    target: str,
    nodejs_version: str,
) -> Path:
    daemon = dict(frontend.get("daemon") or {})
    command = str(daemon["command"]).strip()
    if target == "both":
        api_origin = _safe_preview_url(frontend.get("api_origin_on_both"))
        if api_origin:
            command = f"NEXT_PUBLIC_DRUPAL_API_ORIGIN={api_origin} {command}"

    payload = {
        "nodejs_version": nodejs_version,
        "web_extra_daemons": [
            {
                "name": str(daemon["name"]),
                "command": command,
                "directory": str(daemon["directory"]),
            }
        ],
        "web_extra_exposed_ports": [
            {
                "name": str(daemon["name"]),
                "container_port": int(daemon["container_port"]),
                "http_port": int(daemon["http_port"]),
                "https_port": int(daemon["https_port"]),
            }
        ],
    }
    path = _preview_override_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_local_git_exclude(workspace, _PREVIEW_EXCLUDE)
    path.write_text(
        _PREVIEW_MARKER + "\n" + yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _preview_run(
    job_id: str,
    argv: list[str],
    *,
    workspace: Path,
    timeout: int,
) -> CommandOutput:
    returncode, stdout, stderr, timed_out = run_tracked(
        job_id,
        argv,
        cwd=workspace,
        timeout=timeout,
        env=_ddev_subprocess_env(),
    )
    return CommandOutput(
        command=" ".join(argv),
        returncode=returncode,
        stdout=stdout[-12000:],
        stderr=stderr[-12000:],
        timed_out=timed_out,
    )


def _preview_health(
    job_id: str,
    workspace: Path,
    port: int,
) -> CommandOutput:
    """Probe the frontend without nesting another shell inside DDEV exec.

    `ddev exec` performs shell interpretation by default. Passing a complex
    `bash -lc` script through that boundary caused DDEV to reconstruct the
    command and corrupt redirections/variables before curl ever ran. Use raw
    argv execution and keep all retry/control flow in Python.
    """
    attempts: list[CommandOutput] = []
    url = f"http://127.0.0.1:{port}/"
    for attempt in range(15):
        result = _preview_run(
            job_id,
            [
                "ddev",
                "exec",
                "--raw",
                "--",
                "curl",
                "--noproxy",
                "*",
                "-fsS",
                "--max-time",
                "3",
                "-o",
                "/dev/null",
                url,
            ],
            workspace=workspace,
            timeout=8,
        )
        attempts.append(result)
        if result.returncode == 0:
            return result
        if attempt < 14:
            time.sleep(1)

    diagnostics: list[CommandOutput] = []
    for argv in (
        [
            "ddev",
            "exec",
            "--raw",
            "--",
            "supervisorctl",
            "status",
            "webextradaemons:*",
        ],
        ["ddev", "exec", "--raw", "--", "ss", "-ltnp"],
    ):
        try:
            diagnostics.append(
                _preview_run(
                    job_id,
                    argv,
                    workspace=workspace,
                    timeout=8,
                )
            )
        except Exception:
            pass

    last = attempts[-1]
    evidence_parts = [
        (
            f"attempt {index + 1}: rc={item.returncode} timed_out={item.timed_out}\n"
            f"{item.stderr or item.stdout}"
        )[-3000:]
        for index, item in enumerate(attempts[-3:])
    ]
    evidence_parts.extend(
        (
            f"diagnostic: {item.command}\n"
            f"rc={item.returncode} timed_out={item.timed_out}\n"
            f"{item.stderr or item.stdout}"
        )[-4000:]
        for item in diagnostics
    )
    evidence = "\n\n".join(evidence_parts)
    return last.model_copy(update={"stderr": evidence[-12000:]})


def _reconcile_preview_topology(
    job_id: str,
    workspace: Path,
) -> CommandOutput:
    """Re-apply the host DDEV config after a PCP preview override is removed."""
    return _preview_run(
        job_id,
        ["ddev", "start", "-y"],
        workspace=workspace,
        timeout=600,
    )


def _frontend_preview_present(workspace: Path) -> bool:
    path = _preview_override_path(workspace)
    if not path.exists():
        return False
    try:
        return path.read_text(encoding="utf-8").startswith(_PREVIEW_MARKER + "\n")
    except OSError:
        return False


def _stop_frontend_preview_process(
    job_id: str,
    workspace: Path,
    frontend: dict[str, Any],
) -> CommandOutput:
    daemon = dict(frontend.get("daemon") or {})
    name = str(daemon.get("name") or "").strip()
    result = _preview_run(
        job_id,
        ["ddev", "exec", "supervisorctl", "stop", f"webextradaemons:{name}"],
        workspace=workspace,
        timeout=60,
    )
    if result.returncode != 0:
        detail = f"{result.stdout}\n{result.stderr}".lower()
        if "not running" in detail or "no such process" in detail:
            return result.model_copy(update={"returncode": 0, "timed_out": False})
    return result


def _pause_frontend_preview(
    job_id: str,
    workspace: Path,
    frontend: dict[str, Any],
) -> CommandOutput | None:
    if not _frontend_preview_present(workspace):
        return None
    stopped = _stop_frontend_preview_process(job_id, workspace, frontend)
    if stopped.returncode == 0:
        _remove_managed_preview_override(workspace)
    return stopped


def _reconcile_workspace_ddev_identity(
    workspace: Path,
    job_id: str,
    *,
    project_id: str = "",
    nodejs_version: str | None = None,
) -> Path | None:
    """Keep one deterministic private DDEV identity/runtime per workspace.

    Source repositories may commit their own project name/runtime settings in
    .ddev/config.yaml. The executor must not edit that tracked source file, so
    it owns one private config.*.yaml override instead. Rewriting the override
    before every DDEV phase upgrades preserved/resumed workspaces in place.
    """
    ddev_dir = workspace / ".ddev"
    if project_id == G1_PROJECT_ID:
        # The G1 broker only accepts the immutable fixture config. Do not
        # create the generic untracked identity override while acquiring its
        # first workspace, running preflight, or quiescing it.
        original = ddev_dir / "config.yaml"
        override = ddev_dir / "config.coding-platform.yaml"
        if (
            not ddev_dir.is_dir()
            or ddev_dir.is_symlink()
            or original.is_symlink()
            or not original.is_file()
            or override.exists() or override.is_symlink()
            or git(workspace, "hash-object", "--", ".ddev/config.yaml")
            != "7a3e97a2a35fc8e67b67021365e7e91c448b52c9"
        ):
            raise HTTPException(409, "G1 immutable DDEV fixture identity mismatch")
        return None
    if project_id == G1_PILOT_ID:
        # The pilot operator, not the generic Executor, writes the ONLY two
        # reviewed overlay files. During acquisition they may both be absent;
        # after operator isolation they must be byte-for-byte unchanged.
        if os.getenv("PCP_G1_PILOT_IDENTITY_ENABLED") != "owner-approved":
            raise HTTPException(403, "G1 pilot identity gate is OFF")
        try:
            require_pilot_workspace_identity(workspace, prepared=False)
        except G1IsolationStop as exc:
            raise HTTPException(409, str(exc)) from None
        return None
    if project_id == G1_T02_ID:
        # T02 does not inherit T01's flag or write a cp-* identity.
        if os.getenv("PCP_G1_T02_IDENTITY_ENABLED") != "owner-approved":
            raise HTTPException(403, "G1 T02 identity gate is OFF")
        try:
            require_t02_workspace_identity(workspace, prepared=False)
        except G1IsolationStop as exc:
            raise HTTPException(409, str(exc)) from None
        return None
    if not ddev_dir.is_dir():
        return None

    safe_name = re.sub(r"[^a-z0-9-]", "-", f"cp-{job_id[:10]}")
    lines = [
        "# PCP-managed isolated workspace identity; do not commit.",
        "override_config: true",
        f"name: {safe_name}",
    ]
    normalized_node = str(nodejs_version or "").strip()
    if normalized_node:
        if not re.fullmatch(r"\d{1,2}(?:\.\d{1,2})?", normalized_node):
            raise HTTPException(500, "Invalid configured workspace_nodejs_version")
        lines.append(f'nodejs_version: "{normalized_node}"')

    override = ddev_dir / "config.coding-platform.yaml"
    content = "\n".join(lines) + "\n"
    if not override.exists() or override.read_text(encoding="utf-8") != content:
        override.write_text(content, encoding="utf-8")
    return override


def _validate_ai_branch(cfg: dict[str, Any], branch: str) -> None:
    prefix = str(cfg.get("runtime", {}).get("branch_prefix", "ai")).strip("/")
    expected_prefix = f"{prefix}/"
    if not _BRANCH_RE.fullmatch(branch) or ".." in branch or not branch.startswith(expected_prefix):
        raise HTTPException(422, f"Branch must be a bounded {expected_prefix}* branch")


def _source_origin(cfg: dict[str, Any]) -> tuple[Path, str]:
    source_repo = expand(str(cfg.get("path", "")))
    if not is_git_repo(source_repo):
        raise HTTPException(422, "Configured source repository is unavailable")
    origin = remote_origin(source_repo)
    if not origin:
        raise HTTPException(422, "Source repository has no origin remote")
    return source_repo, origin


# G1-T02: separate, default-off capability for exactly one NEW disposable
# fixture candidate. This does not provision any token, job or Docker service.
def _require_t02_delivery_identity(
    cfg: dict[str, Any], *, job_id: str, branch: str,
) -> None:
    flags_ok = (
        os.getenv("PCP_G1_T02_IDENTITY_ENABLED") == "owner-approved"
        and os.getenv("PCP_G1_T02_DELIVERY_ENABLED") == "owner-approved"
        and os.getenv("PCP_TRUSTED_CODEX_PROJECT_ID") == G1_T02_ID
        and os.getenv("PCP_TRUSTED_CODEX_SOURCE_SHA") == G1_T02_DELIVERY_SEED
        and os.getenv("PCP_TRUSTED_CODEX_JOB_ID") == job_id
    )
    rights = cfg.get("autonomy") if isinstance(cfg, dict) else None
    runtime = cfg.get("runtime") if isinstance(cfg, dict) else None
    ddev = cfg.get("ddev") if isinstance(cfg, dict) else None
    if not (
        flags_ok and re.fullmatch(r"[a-f0-9]{32}", job_id)
        and branch == "ai/" + job_id[:12]
        and isinstance(rights, dict)
        and all(rights.get(p) is True for p in (
            "allow_commit", "allow_push_ai_branch", "allow_create_pr",
        ))
        and all(rights.get(p) is False for p in (
            "allow_auto_merge_low_risk", "allow_production_deploy",
        ))
        and isinstance(runtime, dict)
        and runtime.get("pilot_identity") == "g1-t02-pcp"
        and runtime.get("developer_permission_mode") == "trusted_project"
        and runtime.get("workspace_mode") == "isolated_clone"
        and runtime.get("exclusive_project_lease") is False
        and runtime.get("branch_prefix") == "ai"
        and isinstance(ddev, dict) and ddev.get("enabled") is True
        and cfg.get("base_branch") == "benchmark/g1-codex-smoke-v1"
        and set(load_projects()) == {G1_T02_ID}
    ):
        raise HTTPException(403, "G1 T02 delivery capability not authorized")
    # Git remote comes ONLY from the project-owned pinned fixture source.
    # A foreign git origin is denied before any publication/network call.
    # Check the configured path before _source_origin resolves symlinks.
    source = Path(os.path.expanduser(os.path.expandvars(str(cfg.get("path", "")))))
    if source.is_symlink():
        raise HTTPException(403, "G1 T02 delivery source repository mismatch")
    _, origin = _source_origin(cfg)
    if github_repository_from_origin(origin) != G1_T02_DELIVERY_REPO:
        raise HTTPException(403, "G1 T02 delivery source repository mismatch")


def _verify_t02_local_candidate(
    workspace: Path, source_sha: str, candidate_sha: str,
) -> None:
    """All checks are read-only local Git commands, before any push."""
    if (
        source_sha != G1_T02_DELIVERY_SEED
        or not re.fullmatch(r"[a-f0-9]{40}", candidate_sha)
        or candidate_sha == "78f2beeb4604659b95893bfd8f1e019a9b4e094e"
        or git(workspace, "status", "--porcelain", "--untracked-files=all")
        or git(workspace, "rev-list", "--parents", "-n", "1", candidate_sha)
           != candidate_sha + " " + G1_T02_DELIVERY_SEED
        or git(workspace, "rev-list", "--count",
               G1_T02_DELIVERY_SEED + ".." + candidate_sha) != "1"
    ):
        raise HTTPException(403, "G1 T02 candidate parent/worktree invalid")
    changes = git(workspace, "diff", "--name-status",
                  G1_T02_DELIVERY_SEED, candidate_sha).splitlines()
    expected = {"M\t" + path for path in G1_T02_DELIVERY_PATHS}
    if len(changes) != 2 or set(changes) != expected:
        raise HTTPException(403, "G1 T02 candidate changed paths invalid")
    git(workspace, "diff", "--check", G1_T02_DELIVERY_SEED, candidate_sha)


def _verify_t02_remote_candidate(
    delivery: GitHubDelivery, repository: str,
    candidate_sha: str, branch: str,
) -> None:
    """Privileged GitHub READ verification before an existing PR mutation."""
    if (delivery.repository_scope != G1_T02_DELIVERY_REPO
            or repository != G1_T02_DELIVERY_REPO
            or not re.fullmatch(r"[a-f0-9]{40}", candidate_sha)
            or not re.fullmatch(r"ai/[a-f0-9]{12}", branch)
            or candidate_sha == "78f2beeb4604659b95893bfd8f1e019a9b4e094e"):
        raise HTTPException(403, "G1 T02 remote candidate identity invalid")
    try:
        with delivery._client() as client:
            def get(path: str) -> dict:
                response = client.get(
                    f"{delivery.base}/repos/{repository}/{path}"
                )
                response.raise_for_status()
                return response.json()
            remote = get("branches/" + branch)
            commit = get("git/commits/" + candidate_sha)
            compare = get("compare/" + G1_T02_DELIVERY_SEED + "..." + candidate_sha)
    except (httpx.HTTPError, ValueError, OSError, TypeError):
        raise HTTPException(503, "G1 T02 remote candidate unavailable") from None
    if not (
        isinstance(remote, dict) and isinstance(remote.get("commit"), dict)
        and remote["commit"].get("sha") == candidate_sha
        and isinstance(commit, dict) and commit.get("sha") == candidate_sha
        and isinstance(commit.get("parents"), list)
        and len(commit["parents"]) == 1
        and isinstance(commit["parents"][0], dict)
        and commit["parents"][0].get("sha") == G1_T02_DELIVERY_SEED
        and isinstance(compare, dict)
        and compare.get("status") == "ahead"
        and type(compare.get("ahead_by")) is int and compare["ahead_by"] == 1
        and type(compare.get("behind_by")) is int and compare["behind_by"] == 0
        and type(compare.get("total_commits")) is int and compare["total_commits"] == 1
        and isinstance(compare.get("base_commit"), dict)
        and compare["base_commit"].get("sha") == G1_T02_DELIVERY_SEED
        and isinstance(compare.get("commits"), list)
        and len(compare["commits"]) == 1
        and isinstance(compare["commits"][0], dict)
        and compare["commits"][0].get("sha") == candidate_sha
        and isinstance(compare.get("files"), list)
        and len(compare["files"]) == 2
        and all(isinstance(x, dict) and isinstance(x.get("filename"), str)
                for x in compare["files"])
        and {x.get("filename") for x in compare["files"]} == G1_T02_DELIVERY_PATHS
        and all(x.get("status") == "modified" for x in compare["files"])
    ):
        raise HTTPException(403, "G1 T02 remote candidate ancestry/scope invalid")


def _github_context(cfg: dict[str, Any]) -> tuple[GitHubDelivery, str]:
    _, origin = _source_origin(cfg)
    repository = github_repository_from_origin(origin)
    if not repository:
        raise HTTPException(422, "Source origin is not a supported github.com repository")
    if _f2_git_only_scoped() and repository != F2_FIXTURE_REPOSITORY:
        raise HTTPException(403, "F2 GitHub origin outside fixture repository")
    delivery = (
        GitHubDelivery(repository_scope=F2_FIXTURE_REPOSITORY)
        if _f2_git_only_scoped() else
        GitHubDelivery(repository_scope=G1_T02_DELIVERY_REPO)
        if (cfg.get("runtime") or {}).get("pilot_identity") == "g1-t02-pcp"
        else GitHubDelivery()
    )
    if not delivery.configured:
        raise HTTPException(503, "GITHUB_DELIVERY_TOKEN is not configured")
    return delivery, repository


def _fetch_remote_base_head(
    cfg: dict[str, Any],
    repo: Path,
    *,
    job_id: str,
) -> str:
    """Fetch the configured base branch without rewriting local branches."""

    base_branch = str(cfg.get("base_branch", "main")).strip()
    if not base_branch:
        raise HTTPException(500, "Direct project base branch is not configured")
    _, origin = _source_origin(cfg)
    repository = github_repository_from_origin(origin)
    fetch_target = origin
    fetch_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if repository:
        if _f2_git_only_scoped():
            raise HTTPException(403, "F2 cannot run direct workspace base sync")
        delivery = GitHubDelivery()
        if not delivery.configured:
            raise HTTPException(
                503,
                "GITHUB_DELIVERY_TOKEN is not configured for direct-workspace base synchronization",
            )
        fetch_target = github_push_url(repository)
        fetch_env = github_git_env(delivery.token)

    returncode, stdout, stderr, timed_out = run_tracked(
        job_id,
        [
            "git",
            "-C",
            str(repo),
            "fetch",
            "--no-tags",
            "--no-recurse-submodules",
            fetch_target,
            f"refs/heads/{base_branch}:refs/remotes/origin/{base_branch}",
        ],
        cwd=repo,
        timeout=300,
        env=fetch_env,
    )
    if returncode != 0:
        detail = (stderr or stdout or "git fetch failed")[-12000:]
        raise HTTPException(504 if timed_out else 502, detail)
    return git(repo, "rev-parse", f"refs/remotes/origin/{base_branch}")


def _assert_fast_forward(repo: Path, old: str, new: str, *, message: str) -> None:
    ancestry = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", old, new],
        text=True,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        raise HTTPException(409, message)


def _sync_clean_direct_base(
    cfg: dict[str, Any],
    repo: Path,
    *,
    job_id: str,
) -> str:
    """Fast-forward a clean direct base branch to the authoritative remote head."""

    base_branch = str(cfg.get("base_branch", "main")).strip()
    current_branch = git(repo, "branch", "--show-current", check=False)
    if current_branch != base_branch:
        raise HTTPException(
            409,
            "Direct workspace must be on the configured base branch before a new job starts",
        )
    if git(repo, "status", "--porcelain", check=False):
        raise HTTPException(
            409,
            "Direct workspace repository is dirty; PCP will not reset, clean or stash Human Owner changes",
        )

    local_head = git(repo, "rev-parse", base_branch)
    remote_head = _fetch_remote_base_head(cfg, repo, job_id=job_id)
    if local_head == remote_head:
        return local_head

    _assert_fast_forward(
        repo,
        local_head,
        remote_head,
        message=(
            "Direct workspace base diverged from the authoritative remote base; "
            "PCP will not reset or rewrite local history"
        ),
    )
    git(repo, "merge", "--ff-only", remote_head)
    updated = git(repo, "rev-parse", "HEAD")
    if updated != remote_head:
        raise HTTPException(409, "Direct workspace base fast-forward did not reach the remote head")
    return updated


def _zlist(repo: Path, *args: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or b"git command failed").decode("utf-8", "replace")
        raise HTTPException(422, detail[-12000:])
    return [
        item.decode("utf-8", "surrogateescape")
        for item in proc.stdout.split(b"\0")
        if item
    ]


def _dirty_paths(repo: Path) -> set[str]:
    return set(_zlist(repo, "diff", "--name-only", "-z", "HEAD", "--")) | set(
        _zlist(repo, "ls-files", "--others", "--exclude-standard", "-z")
    )


def _worktree_fingerprint(repo: Path, paths: set[str]) -> dict[str, Any]:
    result: dict[str, str] = {}
    for rel in sorted(paths):
        path = repo / rel
        if path.is_symlink():
            payload = ("symlink:" + os.readlink(path)).encode("utf-8", "surrogateescape")
            result[rel] = hashlib.sha256(payload).hexdigest()
        elif path.is_file():
            result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif not path.exists():
            result[rel] = "missing"
        else:
            raise HTTPException(409, f"Unsupported dirty path type during source advance: {rel}")

    status = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        text=False,
        capture_output=True,
    )
    if status.returncode != 0:
        detail = (status.stderr or status.stdout or b"git status failed").decode(
            "utf-8",
            "replace",
        )
        raise HTTPException(422, detail[-12000:])
    return {
        "files": result,
        "status_sha256": hashlib.sha256(status.stdout).hexdigest(),
    }


def _github_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = exc.response.text[-12000:] if exc.response is not None else str(exc)
        return HTTPException(502, f"GitHub API request failed: {detail}")
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(502, f"GitHub API unavailable: {exc}")
    return HTTPException(409, str(exc))


def _register(job_id: str, proc: subprocess.Popen) -> None:
    with _ACTIVE_LOCK:
        previous = _ACTIVE.get(job_id)
        if previous is not None and previous.poll() is None:
            raise RuntimeError(f"Job {job_id} already has an active executor process")
        _ACTIVE[job_id] = proc


def _unregister(job_id: str, proc: subprocess.Popen) -> None:
    with _ACTIVE_LOCK:
        if _ACTIVE.get(job_id) is proc:
            _ACTIVE.pop(job_id, None)


def _terminate_process_group(proc: subprocess.Popen, grace_seconds: float = 3.0) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def cancel_active(job_id: str) -> bool:
    with _ACTIVE_LOCK:
        proc = _ACTIVE.get(job_id)
    if proc is None:
        return False
    _terminate_process_group(proc)
    return True


def _job_has_active_process(job_id: str) -> bool:
    with _ACTIVE_LOCK:
        proc = _ACTIVE.get(job_id)
        return proc is not None and proc.poll() is None


def _orphan_site_name(job_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(422, "Orphan cleanup requires the full 32-character Runtime job id")
    return f"cp-{job_id[:10]}"


def _docker_output(argv: list[str], *, timeout: int = 60) -> str:
    try:
        result = subprocess.run(
            ["docker", *argv],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, f"Docker command timed out: {' '.join(argv[:3])}") from exc
    if result.returncode != 0:
        raise HTTPException(
            502,
            (result.stderr or result.stdout or "Docker command failed")[-12000:],
        )
    return result.stdout or ""


def _docker_lines(argv: list[str]) -> list[str]:
    return [line.strip() for line in _docker_output(argv).splitlines() if line.strip()]


def _inspect_orphan_resources(
    *,
    job_id: str,
    project_id: str,
    workspace: str | None,
) -> dict[str, Any]:
    if project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_preserve_owned_resources')
    cfg = project(project_id)
    if not bool((cfg.get("ddev") or {}).get("enabled", False)):
        raise HTTPException(409, "Project does not enable DDEV resource management")
    if _job_has_active_process(job_id):
        raise HTTPException(409, "Orphan resources cannot be inspected while an executor command is active")

    site = _orphan_site_name(job_id)
    expected_workspace = str(Path(workspace).resolve()) if workspace else None

    container_ids = _docker_lines([
        "ps",
        "-a",
        "--filter",
        f"label=com.ddev.site-name={site}",
        "--format",
        "{{.ID}}",
    ])
    containers: list[dict[str, Any]] = []
    for container_id in container_ids:
        detail = _docker_output([
            "inspect",
            "--format",
            '{{.Id}}|{{.Name}}|{{.State.Running}}|{{ index .Config.Labels "com.ddev.site-name" }}|{{ index .Config.Labels "com.ddev.platform" }}',
            container_id,
        ]).strip()
        parts = detail.split("|", 4)
        if len(parts) != 5:
            raise HTTPException(409, "Could not prove exact DDEV container ownership")
        exact_id, name, running_text, label_site, platform = parts
        if label_site != site or platform != "ddev":
            raise HTTPException(409, "Container ownership labels do not match the exact PCP job project")
        containers.append({
            "id": exact_id,
            "name": name.removeprefix("/"),
            "running": running_text.strip().lower() == "true",
            "site": label_site,
        })

    if any(item["running"] for item in containers):
        raise HTTPException(409, "Exact PCP orphan project still has a running container")

    exact_container_ids = set(container_ids)

    volumes: list[dict[str, Any]] = []
    for name in _docker_lines(["volume", "ls", "--format", "{{.Name}}"]):
        if not name.startswith(site + "-"):
            continue
        detail = _docker_output([
            "volume",
            "inspect",
            "--format",
            '{{.Name}}|{{with .Labels}}{{with index . "com.ddev.site-name"}}{{.}}{{end}}{{end}}',
            name,
        ]).strip()
        parts = detail.split("|", 1)
        if len(parts) != 2 or parts[0] != name:
            raise HTTPException(409, "Could not prove exact PCP orphan volume identity")
        label_site = parts[1].strip()
        if label_site and label_site != site:
            raise HTTPException(409, "Volume label conflicts with exact PCP orphan project")
        references = set(_docker_lines([
            "ps",
            "-a",
            "--filter",
            f"volume={name}",
            "--format",
            "{{.ID}}",
        ]))
        foreign = sorted(references - exact_container_ids)
        if foreign:
            raise HTTPException(409, "Exact PCP orphan volume is referenced by an unrelated container")
        volumes.append({
            "name": name,
            "site_label": label_site or None,
            "container_references": sorted(references),
        })

    images: list[dict[str, Any]] = []
    for line in _docker_lines([
        "image",
        "ls",
        "--no-trunc",
        "--format",
        "{{.Repository}}|{{.Tag}}|{{.ID}}",
    ]):
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        repository, tag, image_id = parts
        if not tag.endswith(f"-{site}-built"):
            continue
        detail = _docker_output([
            "image",
            "inspect",
            "--format",
            '{{.Id}}|{{ index .Config.Labels "com.ddev.site-name" }}|{{ index .Config.Labels "com.ddev.platform" }}|{{ index .Config.Labels "com.ddev.approot" }}',
            image_id,
        ]).strip()
        image_parts = detail.split("|", 3)
        if len(image_parts) != 4:
            raise HTTPException(409, "Could not prove exact DDEV image ownership")
        exact_id, label_site, platform, approot = image_parts
        if label_site != site or platform != "ddev":
            raise HTTPException(409, "Image ownership labels do not match the exact PCP job project")
        if expected_workspace and approot and str(Path(approot).resolve()) != expected_workspace:
            raise HTTPException(409, "Image approot does not match the Runtime job workspace identity")
        references = set(_docker_lines([
            "ps",
            "-a",
            "--filter",
            f"ancestor={image_id}",
            "--format",
            "{{.ID}}",
        ]))
        foreign = sorted(references - exact_container_ids)
        if foreign:
            raise HTTPException(409, "Exact PCP orphan image is referenced by an unrelated container")
        images.append({
            "id": exact_id,
            "ref": f"{repository}:{tag}",
            "site": label_site,
            "approot": approot or None,
            "container_references": sorted(references),
        })

    return {
        "job_id": job_id,
        "project_id": project_id,
        "site": site,
        "workspace": workspace,
        "containers": containers,
        "volumes": volumes,
        "images": images,
        "resource_count": len(containers) + len(volumes) + len(images),
    }


def _release_orphan_resources(payload: OrphanResourcesRequest) -> dict[str, Any]:
    before = _inspect_orphan_resources(
        job_id=payload.job_id,
        project_id=payload.project_id,
        workspace=payload.workspace,
    )
    if not payload.execute:
        return {
            "mode": "inspect",
            "released": False,
            "before": before,
            "after": before,
        }

    # Revalidate immediately before mutation so a prior inspection never acts
    # as stale authorization.
    before = _inspect_orphan_resources(
        job_id=payload.job_id,
        project_id=payload.project_id,
        workspace=payload.workspace,
    )

    container_ids = [str(item["id"]) for item in before["containers"]]
    if container_ids:
        _docker_output(["rm", *container_ids], timeout=120)

    volume_names = [str(item["name"]) for item in before["volumes"]]
    if volume_names:
        _docker_output(["volume", "rm", *volume_names], timeout=120)

    image_refs = [str(item["ref"]) for item in before["images"]]
    if image_refs:
        _docker_output(["image", "rm", *image_refs], timeout=180)

    after = _inspect_orphan_resources(
        job_id=payload.job_id,
        project_id=payload.project_id,
        workspace=payload.workspace,
    )
    if after["resource_count"] != 0:
        raise HTTPException(409, "Exact PCP orphan resources remain after bounded cleanup")

    return {
        "mode": "execute",
        "released": before["resource_count"] > 0,
        "before": before,
        "after": after,
    }


def _ddev_subprocess_env() -> dict[str, str]:
    """Select PCP's isolated builder only for executor-owned DDEV commands."""
    return {
        **os.environ,
        "DDEV_NO_TUI": "true",
        "BUILDX_BUILDER": os.getenv("PCP_BUILDX_BUILDER", "pcp-builder"),
        "BUILDX_CONFIG": os.getenv(
            "PCP_BUILDX_CONFIG",
            "/home/coder/.pcp-buildx",
        ),
    }


def _effective_ddev_start_timeout(phase_timeout: int) -> int:
    """Use an explicit finite cold-start policy within the existing phase budget."""
    configured = os.getenv("DDEV_START_TIMEOUT_SECONDS", "600").strip()
    if re.fullmatch(r"[0-9]{1,4}", configured) is None:
        raise HTTPException(
            500,
            "DDEV_START_TIMEOUT_SECONDS must be an integer between 10 and 1800",
        )
    start_limit = int(configured)
    if not 10 <= start_limit <= 1800:
        raise HTTPException(
            500,
            "DDEV_START_TIMEOUT_SECONDS must be an integer between 10 and 1800",
        )
    return min(phase_timeout, start_limit)


def _ddev_start_failure_hint(
    stdout: str, stderr: str, *, timed_out: bool, timeout: int,
) -> str:
    """Provide a bounded stage hint without claiming a Docker root cause."""
    stage = (
        "image_build"
        if "Building project images" in (stdout + stderr)
        else "startup_other"
    )
    outcome = "timeout" if timed_out else "command_failure"
    return (
        f"pcp_infrastructure_failure=ddev_start_{outcome} "
        f"stage_hint={stage} effective_timeout_seconds={timeout}"
    )


def run_tracked(
    job_id: str,
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str, bool]:
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    _register(job_id, proc)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return int(proc.returncode or 0), stdout or "", stderr or "", False
        except subprocess.TimeoutExpired:
            _terminate_process_group(proc)
            stdout, stderr = proc.communicate()
            return 124, stdout or "", (stderr or "") + f"\nCommand timed out after {timeout}s", True
    finally:
        _unregister(job_id, proc)


DDEV_EXECUTOR_VERSION = "1.0.35"

app = FastAPI(title="Constrained DDEV/Git Executor", version=DDEV_EXECUTOR_VERSION)


@app.middleware("http")
async def fixture_only_http_scope(request: Request, call_next):
    try:
        if _f2_parked_executor_scope():
            # Deny ALL HTTP methods/paths, including health and API docs.
            # The current F2 Compose still has entrypoint /bin/false.
            return JSONResponse(
                status_code=503,
                content={"detail": "F2 Executor is source-only (PARKED)"},
            )
        if _f2_git_only_scoped():
            # Inspect exact source registry even for /health; never touch host DDEV.
            load_projects()
            if not _f2_git_only_route_allowed(request.method, request.url.path):
                return JSONResponse(
                    status_code=403, content={"detail": "F2 Git-only endpoint denied"}
                )
        elif _g0_fixture_scoped():
            # Re-read the small, mounted G0-only registry on every request.
            # A canonical/legacy multi-project mount must fail closed even
            # for health; never assume a supplied project_id is trustworthy.
            load_projects()
            allowed = G0_FIXTURE_API_ROUTES
            if _g0_fixture_execution_enabled():
                allowed = allowed | G0_EXECUTION_ROUTES
            if _g0_fixture_delivery_enabled():
                allowed = allowed | G0_DELIVERY_ROUTES
            if (request.method, request.url.path) not in allowed:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Endpoint outside isolated G0 Executor scope"},
                )
    except (HTTPException, OSError, ValueError, TypeError, yaml.YAMLError):
        return JSONResponse(
            status_code=503,
            content={"detail": "G0 Executor scope configuration unavailable"},
        )
    return await call_next(request)


app.include_router(pm_bridge_github_router)


@app.get("/v1/project-state", dependencies=[Depends(auth)])
def project_state(
    project_id: str = Query(..., min_length=1, max_length=200),
) -> dict[str, Any]:
    cfg = project(project_id)
    repo = _configured_project_path(cfg)
    branch = git(repo, "branch", "--show-current", check=False)
    head = git(repo, "rev-parse", "HEAD")
    porcelain = git(repo, "status", "--porcelain", check=False)
    base_branch = str(cfg.get("base_branch") or "main")
    origin_base = git(
        repo,
        "rev-parse",
        f"refs/remotes/origin/{base_branch}",
        check=False,
    )
    return {
        "project_id": project_id,
        "workspace_mode": _workspace_mode(cfg),
        "branch": branch or None,
        "head": head,
        "clean": not bool(porcelain.strip()),
        "base_branch": base_branch,
        "origin_base_head": origin_base or None,
    }


@app.post("/v1/direct/sync-base", dependencies=[Depends(auth)])
def sync_direct_base(payload: SyncDirectBaseRequest) -> dict[str, Any]:
    cfg = project(payload.project_id)
    if _workspace_mode(cfg) != "direct":
        raise HTTPException(409, "Remote source sync requires configured direct workspace mode")
    with _ACTIVE_LOCK:
        if _ACTIVE:
            raise HTTPException(409, "DDEV executor has active jobs; source sync is not allowed")

    repo = _configured_project_path(cfg)
    base_branch = str(cfg.get("base_branch") or "main").strip()
    current_branch = git(repo, "branch", "--show-current", check=False)
    if current_branch != base_branch:
        raise HTTPException(409, "Direct workspace is not on configured base branch")
    if git(repo, "status", "--porcelain", check=False):
        raise HTTPException(
            409,
            "Direct workspace is dirty; PCP will not reset, clean or stash Human Owner changes",
        )

    local_head = git(repo, "rev-parse", "HEAD")
    operation_id = (
        "pm-sync-"
        + hashlib.sha256(
            f"{payload.project_id}:{payload.expected_remote_head}".encode("utf-8")
        ).hexdigest()[:24]
    )
    remote_head = _fetch_remote_base_head(
        cfg,
        repo,
        job_id=operation_id,
    )
    if remote_head != payload.expected_remote_head:
        raise HTTPException(409, "Fetched remote base does not match expected exact SHA")

    if local_head != remote_head:
        _assert_fast_forward(
            repo,
            local_head,
            remote_head,
            message=(
                "Direct workspace base diverged from expected remote base; "
                "PCP will not reset or rewrite local history"
            ),
        )
        git(repo, "merge", "--ff-only", remote_head)

    final_head = git(repo, "rev-parse", "HEAD")
    if final_head != remote_head:
        raise HTTPException(409, "Direct source sync did not reach exact expected remote SHA")
    if git(repo, "status", "--porcelain", check=False):
        raise HTTPException(409, "Direct source sync postcondition is not clean")

    return {
        "project_id": payload.project_id,
        "base_branch": base_branch,
        "old_head": local_head,
        "remote_head": remote_head,
        "head": final_head,
        "fast_forwarded": local_head != final_head,
        "clean": True,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    if _f2_parked_executor_scope():
        # Direct Python calls must not probe host Docker/DDEV either.
        raise HTTPException(503, "F2 Executor is source-only (PARKED)")
    if _f2_git_only_scoped():
        load_projects()
        with _ACTIVE_LOCK:
            active_jobs = len(_ACTIVE)
        return {
            "status": "ok", "service": "ddev-executor",
            "version": DDEV_EXECUTOR_VERSION,
            "ddev": "DISABLED", "docker": "not_probed",
            "buildx": "not_probed", "active_jobs": active_jobs,
            "github_delivery_configured": bool(os.getenv("GITHUB_DELIVERY_TOKEN")),
        }
    if _g0_fixture_scoped():
        # A PARKED fixture must not even probe the shared host Docker daemon.
        # The scoped registry is already validated by the HTTP middleware.
        with _ACTIVE_LOCK:
            active_jobs = len(_ACTIVE)
        return {
            "status": "degraded",
            "service": "ddev-executor",
            "version": DDEV_EXECUTOR_VERSION,
            "ddev": "PARKED",
            "docker": "not_probed",
            "buildx": "not_probed",
            "active_jobs": active_jobs,
            "github_delivery_configured": False,
        }
    result = subprocess.run(["ddev", "version"], text=True, capture_output=True)
    docker = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], text=True, capture_output=True)
    buildx = subprocess.run(["docker", "buildx", "version"], text=True, capture_output=True)
    ok = result.returncode == 0 and docker.returncode == 0 and buildx.returncode == 0
    with _ACTIVE_LOCK:
        active_jobs = len(_ACTIVE)
    return {
        "status": "ok" if ok else "degraded",
        "service": "ddev-executor",
        "version": DDEV_EXECUTOR_VERSION,
        "ddev": (result.stdout or result.stderr).strip(),
        "docker": (docker.stdout or docker.stderr).strip(),
        "buildx": (buildx.stdout or buildx.stderr).strip(),
        "active_jobs": active_jobs,
        "github_delivery_configured": GitHubDelivery().configured,
    }


@app.post("/v1/cancel", dependencies=[Depends(auth)])
def cancel(payload: CancelRequest) -> dict[str, Any]:
    return {"job_id": payload.job_id, "cancelled": cancel_active(payload.job_id)}


@app.post("/v1/preview/start", dependencies=[Depends(auth)])
def start_preview(payload: PreviewRequest) -> dict[str, Any]:
    if payload.project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_dedicated_operation_required')
    cfg = project(payload.project_id)
    if _workspace_mode(cfg) != "direct":
        raise HTTPException(409, "Live preview MVP requires a direct workspace")
    workspace = _validate_workspace(
        payload.job_id,
        payload.project_id,
        payload.workspace,
    )
    if _job_has_active_process(payload.job_id):
        raise HTTPException(409, "Preview cannot start while an executor command is active")

    contract = _preview_contract(cfg, payload.target)
    backend = contract["backend"]
    frontend = contract["frontend"]
    previous_frontend = _frontend_preview_present(workspace)

    infrastructure: list[CommandOutput] = []
    if previous_frontend:
        stopped = _pause_frontend_preview(
            payload.job_id,
            workspace,
            frontend,
        )
        if stopped is not None:
            infrastructure.append(stopped)
            if stopped.returncode != 0:
                raise HTTPException(
                    502,
                    (stopped.stderr or stopped.stdout or "preview reset failed")[-12000:],
                )

    frontend_target = payload.target in {"frontend", "both"}
    nodejs_version = _direct_nodejs_version(cfg) if frontend_target else None
    if frontend_target and nodejs_version:
        _write_direct_node_override(workspace, nodejs_version)

    started = _preview_run(
        payload.job_id,
        ["ddev", "start", "-y"],
        workspace=workspace,
        timeout=600,
    )
    infrastructure.append(started)
    if started.returncode != 0:
        if frontend_target:
            _remove_managed_direct_node_override(workspace)
        raise HTTPException(502, (started.stderr or started.stdout or "ddev start failed")[-12000:])

    if frontend_target:
        for command in frontend.get("prepare") or []:
            result = _preview_run(
                payload.job_id,
                ["bash", "-lc", command],
                workspace=workspace,
                timeout=1800,
            )
            infrastructure.append(result)
            if result.returncode != 0:
                _remove_managed_direct_node_override(workspace)
                raise HTTPException(502, (result.stderr or result.stdout or "preview prepare failed")[-12000:])

        _write_preview_override(
            workspace,
            frontend=frontend,
            target=payload.target,
            nodejs_version=nodejs_version,
        )
        _remove_managed_direct_node_override(workspace)
        restarted = _preview_run(
            payload.job_id,
            ["ddev", "restart", "-y"],
            workspace=workspace,
            timeout=600,
        )
        infrastructure.append(restarted)
        if restarted.returncode != 0:
            _remove_managed_preview_override(workspace)
            _remove_managed_direct_node_override(workspace)
            raise HTTPException(502, (restarted.stderr or restarted.stdout or "preview restart failed")[-12000:])

        daemon = dict(frontend.get("daemon") or {})
        health = _preview_health(
            payload.job_id,
            workspace,
            int(daemon["container_port"]),
        )
        infrastructure.append(health)
        if health.returncode != 0:
            # A failed preview must not leave a managed daemon/config or stale
            # live DDEV port topology behind. Stop only the PCP-owned daemon,
            # remove only the PCP-owned override, then reconcile the project
            # against the remaining host config.
            try:
                stopped = _pause_frontend_preview(
                    payload.job_id,
                    workspace,
                    frontend,
                )
                if stopped is None or stopped.returncode == 0:
                    infrastructure.append(
                        _reconcile_preview_topology(payload.job_id, workspace)
                    )
            except Exception:
                pass
            raise HTTPException(502, "Frontend preview did not become healthy")

    return {
        "job_id": payload.job_id,
        "project_id": payload.project_id,
        "target": payload.target,
        "status": "ready",
        "frontend_url": (
            _safe_preview_url(frontend.get("url"))
            if payload.target in {"frontend", "both"}
            else None
        ),
        "backend_url": (
            _safe_preview_url(backend.get("url"))
            if payload.target in {"backend", "both"}
            else None
        ),
        "integration_note": (
            "Backend preview uses the shared direct-workspace DDEV runtime; Stop Preview does not stop DDEV or remove its data. "
            "Frontend is pointed at the local backend; credentialed browser flows still depend on the project's existing CORS/auth policy."
            if payload.target == "both"
            else (
                "Backend preview uses the shared direct-workspace DDEV runtime; Stop Preview does not stop DDEV or remove its data."
                if payload.target == "backend"
                else None
            )
        ),
    }


@app.post("/v1/preview/status", dependencies=[Depends(auth)])
def preview_status(payload: PreviewRequest) -> dict[str, Any]:
    if payload.project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_dedicated_operation_required')
    cfg = project(payload.project_id)
    if _workspace_mode(cfg) != "direct":
        raise HTTPException(409, "Live preview MVP requires a direct workspace")
    workspace = _validate_workspace(
        payload.job_id,
        payload.project_id,
        payload.workspace,
    )
    contract = _preview_contract(cfg, payload.target)
    backend = contract["backend"]
    frontend = contract["frontend"]

    backend_ready = False
    frontend_ready = False
    if payload.target in {"backend", "both"}:
        backend_probe = _preview_run(
            payload.job_id,
            ["ddev", "exec", "true"],
            workspace=workspace,
            timeout=30,
        )
        backend_ready = backend_probe.returncode == 0
    if payload.target in {"frontend", "both"} and _frontend_preview_present(workspace):
        daemon = dict(frontend.get("daemon") or {})
        frontend_probe = _preview_health(
            payload.job_id,
            workspace,
            int(daemon["container_port"]),
        )
        frontend_ready = frontend_probe.returncode == 0

    ready = (
        frontend_ready if payload.target == "frontend"
        else backend_ready if payload.target == "backend"
        else backend_ready and frontend_ready
    )
    return {
        "job_id": payload.job_id,
        "project_id": payload.project_id,
        "target": payload.target,
        "status": "ready" if ready else "stopped",
        "frontend_url": (
            _safe_preview_url(frontend.get("url"))
            if frontend_ready and payload.target in {"frontend", "both"}
            else None
        ),
        "backend_url": (
            _safe_preview_url(backend.get("url"))
            if backend_ready and payload.target in {"backend", "both"}
            else None
        ),
    }


@app.post("/v1/preview/stop", dependencies=[Depends(auth)])
def stop_preview(payload: PreviewRequest) -> dict[str, Any]:
    if payload.project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_dedicated_operation_required')
    cfg = project(payload.project_id)
    if _workspace_mode(cfg) != "direct":
        raise HTTPException(409, "Live preview MVP requires a direct workspace")
    workspace = _validate_workspace(
        payload.job_id,
        payload.project_id,
        payload.workspace,
    )
    if _job_has_active_process(payload.job_id):
        raise HTTPException(409, "Preview cannot stop while an executor command is active")

    contract = _preview_contract(cfg, payload.target)
    frontend = contract["frontend"]
    if _frontend_preview_present(workspace):
        stopped = _pause_frontend_preview(
            payload.job_id,
            workspace,
            frontend,
        )
        if stopped is not None and stopped.returncode != 0:
            raise HTTPException(
                502,
                (stopped.stderr or stopped.stdout or "preview stop failed")[-12000:],
            )
        reconciled = _reconcile_preview_topology(payload.job_id, workspace)
        if reconciled.returncode != 0:
            raise HTTPException(
                502,
                (
                    reconciled.stderr
                    or reconciled.stdout
                    or "preview topology reconciliation failed"
                )[-12000:],
            )
    _remove_managed_direct_node_override(workspace)
    return {
        "job_id": payload.job_id,
        "project_id": payload.project_id,
        "target": payload.target,
        "status": "stopped",
        "frontend_url": None,
        "backend_url": None,
    }


@app.post("/v1/workspaces/orphan-resources", dependencies=[Depends(auth)])
def orphan_resources(payload: OrphanResourcesRequest) -> dict[str, Any]:
    with _ORPHAN_RESOURCE_LOCK:
        return _release_orphan_resources(payload)


@app.post("/v1/workspaces/quiesce", dependencies=[Depends(auth)])
def quiesce_workspace(payload: QuiesceWorkspaceRequest) -> dict[str, Any]:
    if payload.project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_dedicated_operation_required')
    cfg = project(payload.project_id)
    # Direct project quiesce is a safe no-op, even when verification is off.
    # An isolated project's quiesce executes DDEV stop and needs an explicit
    # project-level enablement before consulting/mutating its workspace.
    if _workspace_mode(cfg) != "direct":
        _require_ddev_enabled(cfg)
    workspace = _validate_workspace(payload.job_id, payload.project_id, payload.workspace)

    if _workspace_instance_mode(cfg, job_id=payload.job_id, path=workspace) == "direct":
        return {
            "job_id": payload.job_id,
            "project_id": payload.project_id,
            "workspace": str(workspace),
            "quiesced": False,
            "data_removed": False,
            "preserved": True,
            "reason": "direct_workspace_preserved",
            "stdout": "",
            "stderr": "",
        }

    if _job_has_active_process(payload.job_id):
        raise HTTPException(
            409,
            "Workspace cannot be quiesced while an executor command is active",
        )

    _reconcile_workspace_ddev_identity(
        workspace,
        payload.job_id,
        project_id=payload.project_id,
        nodejs_version=cfg.get("ddev", {}).get("workspace_nodejs_version"),
    )

    argv = ["ddev", "stop", "--unlist", "--omit-snapshot"]
    if payload.remove_data:
        argv.append("--remove-data")

    returncode, stdout, stderr, timed_out = run_tracked(
        payload.job_id,
        argv,
        cwd=workspace,
        timeout=300,
        env=_ddev_subprocess_env(),
    )
    if returncode != 0:
        detail = (stderr or stdout or "ddev stop failed")[-12000:]
        raise HTTPException(504 if timed_out else 502, detail)

    return {
        "job_id": payload.job_id,
        "project_id": payload.project_id,
        "workspace": str(workspace),
        "quiesced": True,
        "data_removed": bool(payload.remove_data),
        "stdout": stdout[-12000:],
        "stderr": stderr[-12000:],
    }


@app.post("/v1/workspaces", dependencies=[Depends(auth)])
def create_workspace(payload: WorkspaceRequest) -> dict[str, Any]:
    """Prepare either the configured direct repo or one isolated clone."""
    cfg = project(payload.project_id)
    if payload.project_id == 'pcp-local':
        _pcp_identity(payload.job_id, payload.ref)
        if payload.ref is None or payload.workspace_mode != 'isolated_clone':
            raise HTTPException(403, 'pcp_local_exact_workspace_required')
    if _f2_git_only_scoped():
        if (payload.ref != F2_FIXTURE_SOURCE
                or payload.workspace_mode != "isolated_clone"
                or not re.fullmatch(r"[0-9a-f]{32}", payload.job_id)):
            raise HTTPException(403, "F2 requires exact pinned seed and isolated job UUID")
        _require_f2_source_repository(cfg)
    if _g0_fixture_scoped():
        if not _g0_fixture_execution_enabled():
            raise HTTPException(403, "G0 workspace creation not approved")
        if payload.ref != G0_SOURCE_COMMIT or payload.workspace_mode != "isolated_clone":
            raise HTTPException(403, "G0 workspace requires frozen source and isolated clone")
        if not re.fullmatch(r"[0-9a-f]{32}", payload.job_id):
            raise HTTPException(403, "G0 requires an exact job UUID")
        _require_g0_source_repository(cfg)
    repo = _configured_project_path(cfg)
    configured_mode = _workspace_mode(cfg)
    mode = (
        "isolated_clone"
        if payload.workspace_mode == "isolated_clone"
        else configured_mode
    )
    ref = payload.ref or str(cfg.get("base_branch", "main"))
    prefix = str(cfg.get("runtime", {}).get("branch_prefix", "ai"))
    branch = f"{prefix}/{payload.job_id[:12]}"
    _validate_ai_branch(cfg, branch)

    if mode == "direct":
        status = git(repo, "status", "--porcelain", check=False)
        current_branch = git(repo, "branch", "--show-current", check=False)
        current_head = git(repo, "rev-parse", "HEAD", check=False)
        existing_branch = subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            text=True,
            capture_output=True,
        ).returncode == 0

        if current_branch == branch:
            source_commit = (
                git(repo, "rev-parse", ref)
                if payload.ref is not None
                else git(repo, "rev-parse", str(cfg.get("base_branch", "main")))
            )
            if status or current_head != source_commit:
                raise HTTPException(
                    409,
                    "Direct workspace retry requires the prepared AI branch to remain clean at the pinned source commit",
                )
            return {
                "workspace": str(repo),
                "branch": branch,
                "source_commit": source_commit,
                "workspace_mode": "direct",
            }

        if status:
            raise HTTPException(
                409,
                "Direct workspace repository is dirty; PCP will not reset, clean or stash Human Owner changes",
            )
        if existing_branch:
            raise HTTPException(409, "Direct workspace AI branch already exists")
        source_commit = (
            _sync_clean_direct_base(cfg, repo, job_id=payload.job_id)
            if payload.ref is None
            else git(repo, "rev-parse", ref)
        )
        git(repo, "checkout", "-b", branch, source_commit)
        return {
            "workspace": str(repo),
            "branch": branch,
            "source_commit": source_commit,
            "workspace_mode": "direct",
        }

    source_commit = git(repo, "rev-parse", ref)
    root = Path(os.environ["CODING_WORKSPACES_ROOT"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if _f2_git_only_scoped() and any(root.iterdir()):
        raise HTTPException(409, "F2 only allows one active isolated workspace")
    workspace = (root / payload.job_id).resolve()
    if not allowed_workspace(workspace) or workspace.parent != root:
        raise HTTPException(403, "Invalid workspace path")
    if workspace.exists():
        raise HTTPException(409, "Workspace already exists")

    returncode, stdout, stderr, _ = run_tracked(
        payload.job_id,
        ["git", "clone", "--no-local", "--no-checkout", str(repo), str(workspace)],
        timeout=300,
    )
    if returncode != 0:
        shutil.rmtree(workspace, ignore_errors=True)
        raise HTTPException(422, stderr.strip() or stdout.strip() or "git clone failed")

    try:
        _materialize_commit_from_source_refs(
            repo,
            workspace,
            source_commit,
            base_branch=str(cfg.get("base_branch", "main")).strip() or "main",
        )
        if remote_origin(workspace):
            git(workspace, "remote", "remove", "origin")
        git(workspace, "checkout", "-b", branch, source_commit)
        git(workspace, "update-ref", "-d", "refs/pcp/materialized-source", check=False)
        if payload.project_id == 'pcp-local':
            # Sparse omission preserves the source tree/diff without materializing
            # executable legacy DDEV files into the developer workspace.
            git(workspace, 'sparse-checkout', 'set', '--no-cone', '/*', '!/.ddev/')
        elif not (_g0_fixture_scoped() or _f2_git_only_scoped()):
            _reconcile_workspace_ddev_identity(
                workspace,
                payload.job_id,
                project_id=payload.project_id,
                nodejs_version=cfg.get("ddev", {}).get("workspace_nodejs_version"),
            )
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise

    return {
        "workspace": str(workspace),
        "branch": branch,
        "source_commit": source_commit,
        "workspace_mode": "isolated_clone_no_remote",
    }


G0_ALLOWED_CHANGED_FILES = frozenset({
    "web/modules/custom/pcp_g0_fixture/src/EventLabelNormalizer.php",
    "web/modules/custom/pcp_g0_fixture/tests/src/Unit/EventLabelNormalizerTest.php",
    "web/modules/custom/pcp_g0_fixture/tests/src/Kernel/EventLabelServiceTest.php",
})


def _verify_g0_delivered_diff(
    workspace: Path, source_commit: str, expected_commit: str,
) -> None:
    """Recheck the exact committed fixture diff at the privileged Git boundary."""
    if source_commit != G0_SOURCE_COMMIT or not re.fullmatch(
        r"[0-9a-f]{40}", expected_commit
    ):
        raise HTTPException(403, "G0 delivery source/commit identity invalid")
    if git(workspace, "status", "--porcelain", check=False):
        raise HTTPException(409, "G0 delivery workspace must be clean")
    changed = git(
        workspace, "diff", "--name-only", source_commit, expected_commit
    ).splitlines()
    if (len(changed) != len(G0_ALLOWED_CHANGED_FILES)
            or set(changed) != G0_ALLOWED_CHANGED_FILES):
        raise HTTPException(403, "G0 commit must contain only the frozen code and test changes")


def _require_g0_delivery_contract(
    cfg: dict[str, Any], *, job_id: str, branch: str,
    source_commit: str | None = None,
) -> None:
    if not _g0_fixture_delivery_enabled():
        raise HTTPException(403, "G0 fixture delivery is not activated")
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(403, "G0 delivery requires an exact job UUID")
    if branch != f"ai/{job_id[:12]}":
        raise HTTPException(403, "G0 delivery branch must match the owning job")
    if source_commit is not None and source_commit != G0_SOURCE_COMMIT:
        raise HTTPException(403, "G0 delivery cannot advance the frozen seed")
    _require_g0_source_repository(cfg)
    if cfg.get("ddev", {}).get("enabled") is not False:
        raise HTTPException(403, "G0 delivery may not activate DDEV")


@app.post("/v1/publish-branch", dependencies=[Depends(auth)])
def publish_branch(payload: PublishBranchRequest) -> dict[str, Any]:
    """Push exactly one verified AI branch without adding a remote to the workspace."""
    cfg = project(payload.project_id)
    if payload.project_id == G1_T02_ID:
        _require_t02_delivery_identity(cfg, job_id=payload.job_id,
                                       branch=payload.branch)
    scoped = _g0_fixture_scoped()
    if _f2_git_only_scoped():
        _require_f2_delivery_contract(
            cfg, job_id=payload.job_id, branch=payload.branch,
            source_commit=payload.source_commit,
        )
    if scoped:
        _require_g0_delivery_contract(
            cfg, job_id=payload.job_id, branch=payload.branch,
            source_commit=payload.source_commit,
        )
        if payload.review_repair_pr_number is not None or payload.review_repair_previous_commit:
            raise HTTPException(403, "G0 review-repair delivery is not enabled")
    autonomy = cfg.get("autonomy", {}) or {}
    if not scoped and not bool(autonomy.get("allow_push_ai_branch", False)):
        raise HTTPException(403, "Project policy does not allow AI branch publishing")
    guarded_repair = payload.review_repair_pr_number is not None
    if guarded_repair != (payload.review_repair_previous_commit is not None):
        raise HTTPException(422, "Review-repair publish guard requires exact PR and previous commit")
    if guarded_repair and not bool(autonomy.get("allow_create_pr", False)):
        raise HTTPException(403, "Project policy does not allow pull-request delivery")

    workspace = _validate_workspace(payload.job_id, payload.project_id, payload.workspace)
    mode = _workspace_instance_mode(
        cfg,
        job_id=payload.job_id,
        path=workspace,
    )
    _validate_ai_branch(cfg, payload.branch)

    current_branch = git(workspace, "branch", "--show-current")
    if current_branch != payload.branch:
        raise HTTPException(409, "Workspace branch does not match requested publish branch")
    head = git(workspace, "rev-parse", "HEAD")
    expected = git(workspace, "rev-parse", payload.expected_commit)
    source_commit = git(workspace, "rev-parse", payload.source_commit)
    if head != expected:
        raise HTTPException(409, "Workspace HEAD does not match expected commit")
    if mode == "isolated_clone" and git(workspace, "remote", check=False).strip():
        raise HTTPException(409, "Isolated workspace must not contain git remotes during publish")

    ancestry = subprocess.run(
        ["git", "-C", str(workspace), "merge-base", "--is-ancestor", source_commit, expected],
        text=True,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        raise HTTPException(409, "Expected commit is not descended from the job source commit")
    if scoped:
        _verify_g0_delivered_diff(workspace, source_commit, expected)
    if _f2_git_only_scoped():
        _verify_f2_delivered_diff(workspace, source_commit, expected)
    if payload.project_id == G1_T02_ID:
        _verify_t02_local_candidate(workspace, source_commit, expected)
        try:
            require_g1_t02_isolated_ddev(workspace)
        except G1IsolationStop as exc:
            raise HTTPException(403, "G1 T02 delivery isolation invalid") from exc

    _, origin = _source_origin(cfg)
    repository = github_repository_from_origin(origin)
    if payload.project_id == G1_T02_ID and repository != G1_T02_DELIVERY_REPO:
        raise HTTPException(403, "G1 T02 delivery source repository mismatch")
    push_target = origin
    push_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if repository:
        if _f2_git_only_scoped() and repository != F2_FIXTURE_REPOSITORY:
            raise HTTPException(403, "F2 publishing origin outside fixture repository")
        delivery = (
            GitHubDelivery(repository_scope=F2_FIXTURE_REPOSITORY)
            if _f2_git_only_scoped() else
            GitHubDelivery(repository_scope=G1_T02_DELIVERY_REPO)
            if payload.project_id == G1_T02_ID else GitHubDelivery()
        )
        if not delivery.configured:
            raise HTTPException(503, "GITHUB_DELIVERY_TOKEN is not configured for GitHub publishing")
        push_target = github_push_url(repository)
        push_env = github_git_env(delivery.token)
    elif guarded_repair:
        raise HTTPException(409, "Review-repair publication requires a GitHub repository")

    if guarded_repair:
        try:
            delivery.verify_review_repair(
                repository=repository,
                job_id=payload.job_id,
                pr_number=int(payload.review_repair_pr_number),
                branch=payload.branch,
                base_branch=str(cfg.get("base_branch", "main")),
                source_commit=source_commit,
                expected_commit=str(payload.review_repair_previous_commit),
            )
        except RuntimeError as previous_error:
            try:
                delivery.verify_review_repair(
                    repository=repository,
                    job_id=payload.job_id,
                    pr_number=int(payload.review_repair_pr_number),
                    branch=payload.branch,
                    base_branch=str(cfg.get("base_branch", "main")),
                    source_commit=source_commit,
                    expected_commit=expected,
                )
            except httpx.HTTPError as exc:
                raise _github_error(exc) from exc
            except (RuntimeError, ValueError):
                raise _github_error(previous_error) from previous_error
            return {
                "published": True,
                "already_published": True,
                "branch": payload.branch,
                "commit": expected,
                "source_commit": source_commit,
                "repository": repository,
            }
        except (httpx.HTTPError, ValueError) as exc:
            raise _github_error(exc) from exc

    returncode, stdout, stderr, timed_out = run_tracked(
        payload.job_id,
        [
            "git", "-C", str(workspace), "push", "--porcelain", push_target,
            f"{expected}:refs/heads/{payload.branch}",
        ],
        timeout=300,
        env=push_env,
    )
    if returncode != 0:
        detail = (stderr or stdout or "git push failed")[-12000:]
        raise HTTPException(502 if not timed_out else 504, detail)

    return {
        "published": True,
        "branch": payload.branch,
        "commit": expected,
        "source_commit": source_commit,
        "repository": repository,
    }


@app.post("/v1/github/reconcile-delivery", dependencies=[Depends(auth)])
def reconcile_delivery(payload: ReconcileDeliveryRequest) -> dict[str, Any]:
    """Observe an already-merged PR before retrying a preserved delivery."""
    if payload.project_id == G1_T02_ID:
        raise HTTPException(403, "T02 delivery reconciliation requires separate approval")
    cfg = project(payload.project_id)
    if _f2_git_only_scoped():
        _require_f2_delivery_contract(
            cfg, job_id=payload.job_id, branch=payload.branch,
            source_commit=payload.source_commit,
        )
    autonomy = cfg.get("autonomy", {}) or {}
    if not bool(autonomy.get("allow_push_ai_branch", False)):
        raise HTTPException(403, "Project policy does not allow AI branch publishing")
    if not bool(autonomy.get("allow_create_pr", False)):
        raise HTTPException(403, "Project policy does not allow pull-request delivery")
    _validate_ai_branch(cfg, payload.branch)
    delivery, repository = _github_context(cfg)
    try:
        observed = delivery.reconcile_merged_delivery(
            repository=repository,
            job_id=payload.job_id,
            branch=payload.branch,
            base_branch=str(cfg.get("base_branch", "main")),
            source_commit=payload.source_commit,
            expected_commit=payload.expected_commit,
        )
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise _github_error(exc) from exc
    return {
        "job_id": payload.job_id,
        "reconciled": observed is not None,
        "delivery": observed,
    }


@app.post("/v1/github/review-repair", dependencies=[Depends(auth)])
def prepare_review_repair(payload: ReviewRepairRequest) -> dict[str, Any]:
    """Revalidate one delivered PR and restore its exact job branch for repair."""
    if payload.project_id == G1_T02_ID:
        raise HTTPException(403, "T02 review repair requires separate approval")
    if payload.project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_dedicated_operation_required')
    cfg = project(payload.project_id)
    if _f2_git_only_scoped():
        _require_f2_delivery_contract(
            cfg, job_id=payload.job_id, branch=payload.branch,
            source_commit=payload.source_commit,
        )
    autonomy = cfg.get("autonomy", {}) or {}
    if not bool(autonomy.get("allow_push_ai_branch", False)):
        raise HTTPException(403, "Project policy does not allow AI branch publishing")
    if not bool(autonomy.get("allow_create_pr", False)):
        raise HTTPException(403, "Project policy does not allow pull-request delivery")

    _validate_ai_branch(cfg, payload.branch)
    workspace = _validate_workspace(payload.job_id, payload.project_id, payload.workspace)
    mode = _workspace_instance_mode(cfg, job_id=payload.job_id, path=workspace)
    if git(workspace, "status", "--porcelain", check=False):
        raise HTTPException(409, "Review repair requires the existing job workspace to be clean")

    local_branch_head = git(
        workspace,
        "rev-parse",
        f"refs/heads/{payload.branch}",
        check=False,
    )
    if local_branch_head != payload.expected_commit:
        raise HTTPException(409, "Existing job branch does not match the expected delivered commit")
    source_commit = git(workspace, "rev-parse", payload.source_commit)
    ancestry = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "merge-base",
            "--is-ancestor",
            source_commit,
            payload.expected_commit,
        ],
        text=True,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        raise HTTPException(409, "Delivered commit is not descended from the job source commit")

    current_branch = git(workspace, "branch", "--show-current", check=False)
    base_branch = str(cfg.get("base_branch", "main"))
    if mode == "direct":
        if current_branch not in {payload.branch, base_branch}:
            raise HTTPException(
                409,
                "Direct workspace is not on the job branch or configured base branch",
            )
    elif current_branch != payload.branch:
        raise HTTPException(409, "Isolated job workspace is not on its exact AI branch")
    if mode == "isolated_clone" and git(workspace, "remote", check=False).strip():
        raise HTTPException(409, "Isolated job workspace must remain remote-free")

    delivery, repository = _github_context(cfg)
    try:
        pull_request = delivery.verify_review_repair(
            repository=repository,
            job_id=payload.job_id,
            pr_number=payload.pr_number,
            branch=payload.branch,
            base_branch=base_branch,
            source_commit=source_commit,
            expected_commit=payload.expected_commit,
        )
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise _github_error(exc) from exc

    if current_branch == base_branch:
        git(workspace, "checkout", payload.branch)
    if git(workspace, "branch", "--show-current") != payload.branch:
        raise HTTPException(409, "Review repair could not restore the exact job branch")
    if git(workspace, "rev-parse", "HEAD") != payload.expected_commit:
        raise HTTPException(409, "Restored job workspace HEAD does not match the delivered commit")
    if git(workspace, "status", "--porcelain", check=False):
        raise HTTPException(409, "Restored job workspace is not clean")

    return {
        "job_id": payload.job_id,
        "workspace": str(workspace),
        "workspace_mode": mode,
        "branch": payload.branch,
        "source_commit": source_commit,
        "expected_commit": payload.expected_commit,
        "pull_request": pull_request,
    }


@app.post("/v1/github/pull-request", dependencies=[Depends(auth)])
def upsert_pull_request(payload: PullRequestRequest) -> dict[str, Any]:
    if payload.project_id == 'pcp-local':
        return _pcp_draft_pr(payload)
    cfg = project(payload.project_id)
    if payload.project_id == G1_T02_ID:
        _require_t02_delivery_identity(cfg, job_id=payload.job_id,
                                       branch=payload.branch)
    if _f2_git_only_scoped():
        _require_f2_delivery_contract(
            cfg, job_id=payload.job_id, branch=payload.branch,
        )
    scoped = _g0_fixture_scoped()
    if scoped:
        _require_g0_delivery_contract(
            cfg, job_id=payload.job_id, branch=payload.branch,
        )
        if (not payload.title.startswith("[G0D-T01]")
                or payload.expected_pr_number is not None):
            raise HTTPException(403, "G0 PR may only create the frozen task delivery")
    autonomy = cfg.get("autonomy", {}) or {}
    if not scoped and not bool(autonomy.get("allow_create_pr", False)):
        raise HTTPException(403, "Project policy does not allow pull-request creation")
    _validate_ai_branch(cfg, payload.branch)
    delivery, repository = _github_context(cfg)
    if payload.project_id == G1_T02_ID:
        _verify_t02_remote_candidate(delivery, repository, payload.expected_commit,
                                     payload.branch)
    base_branch = str(cfg.get("base_branch", "main"))
    try:
        result = delivery.upsert_pull_request(
            repository=repository,
            job_id=payload.job_id,
            branch=payload.branch,
            base_branch=base_branch,
            expected_commit=payload.expected_commit,
            title=payload.title,
            body=payload.body,
            expected_pr_number=payload.expected_pr_number,
        )
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise _github_error(exc) from exc
    return {"job_id": payload.job_id, **result}


@app.get("/v1/github/ci", dependencies=[Depends(auth)])
def github_ci(
    project_id: str = Query(..., min_length=1, max_length=200),
    commit: str = Query(..., min_length=7, max_length=64),
) -> dict[str, Any]:
    cfg = project(project_id)
    if project_id == G1_T02_ID:
        jid = os.getenv("PCP_TRUSTED_CODEX_JOB_ID", "")
        _require_t02_delivery_identity(cfg, job_id=jid,
                                       branch="ai/" + jid[:12])
        delivery, repo = _github_context(cfg)
        return g1_t02_ci_status(delivery, repository=repo,
                                candidate_sha=commit, job_id=jid)
    if _f2_git_only_scoped():
        _require_f2_source_repository(cfg)
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise HTTPException(403, "F2 CI requires exact SHA")
    scoped = _g0_fixture_scoped()
    if scoped:
        if not _g0_fixture_delivery_enabled():
            raise HTTPException(403, "G0 CI observation is not activated")
        _require_g0_source_repository(cfg)
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise HTTPException(403, "G0 CI requires an exact delivered commit")
    autonomy = cfg.get("autonomy", {}) or {}
    if not scoped and not bool(autonomy.get("allow_create_pr", False)):
        raise HTTPException(403, "Project policy does not allow GitHub delivery monitoring")
    delivery, repository = _github_context(cfg)
    try:
        return delivery.ci_status(repository=repository, commit=commit)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise _github_error(exc) from exc


@app.post("/v1/workspaces/return-to-base", dependencies=[Depends(auth)])
def return_direct_workspace_to_base(payload: ReturnDirectWorkspaceRequest) -> dict[str, Any]:
    """Return only a clean, exact direct AI workspace to its configured base branch.

    This never resets, cleans, stashes, deletes the AI branch, or updates the base
    branch from a remote. A mismatch or dirty tree fails closed.
    """
    if payload.project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_dedicated_operation_required')
    cfg = project(payload.project_id)
    workspace = _validate_workspace(
        payload.job_id,
        payload.project_id,
        payload.workspace,
    )
    if _workspace_instance_mode(
        cfg,
        job_id=payload.job_id,
        path=workspace,
    ) != "direct":
        raise HTTPException(409, "Return-to-base is supported only for the configured direct workspace")

    _validate_ai_branch(cfg, payload.branch)
    base_branch = str(cfg.get("base_branch", "main")).strip()
    if not base_branch:
        raise HTTPException(500, "Direct project base branch is not configured")

    status = git(workspace, "status", "--porcelain", check=False)
    if status:
        raise HTTPException(
            409,
            "Direct workspace repository is dirty; PCP will not reset, clean or stash Human Owner changes",
        )

    current_branch = git(workspace, "branch", "--show-current", check=False)
    if current_branch == base_branch:
        return {
            "job_id": payload.job_id,
            "project_id": payload.project_id,
            "workspace": str(workspace),
            "branch": base_branch,
            "head": git(workspace, "rev-parse", "HEAD"),
            "returned": True,
            "reused": True,
        }
    if current_branch != payload.branch:
        raise HTTPException(
            409,
            "Direct workspace branch changed outside the owning job; refusing base restoration",
        )

    base_exists = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{base_branch}",
        ],
        text=True,
        capture_output=True,
    ).returncode == 0
    if not base_exists:
        raise HTTPException(
            409,
            "Configured direct base branch does not exist locally; refusing implicit branch creation",
        )

    git(workspace, "checkout", base_branch)
    final_status = git(workspace, "status", "--porcelain", check=False)
    if final_status:
        raise HTTPException(
            409,
            "Direct workspace became dirty while returning to base; lease must remain held",
        )

    return {
        "job_id": payload.job_id,
        "project_id": payload.project_id,
        "workspace": str(workspace),
        "branch": base_branch,
        "head": git(workspace, "rev-parse", "HEAD"),
        "returned": True,
        "reused": False,
    }


@app.post("/v1/workspaces/advance-direct-source", dependencies=[Depends(auth)])
def advance_direct_workspace_source(
    payload: AdvanceDirectWorkspaceSourceRequest,
) -> dict[str, Any]:
    """Advance one blocked direct job branch onto an exact newer base safely."""

    if payload.project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_dedicated_operation_required')
    cfg = project(payload.project_id)
    workspace = _validate_workspace(
        payload.job_id,
        payload.project_id,
        payload.workspace,
    )
    if _workspace_instance_mode(
        cfg,
        job_id=payload.job_id,
        path=workspace,
    ) != "direct":
        raise HTTPException(409, "Source advance is supported only for a direct workspace")
    if _job_has_active_process(payload.job_id):
        raise HTTPException(409, "Source advance requires no active executor process")

    _validate_ai_branch(cfg, payload.branch)
    current_branch = git(workspace, "branch", "--show-current", check=False)
    if current_branch != payload.branch:
        raise HTTPException(409, "Direct workspace is not on the exact owning job branch")

    current_head = git(workspace, "rev-parse", "HEAD")
    old_source = git(workspace, "rev-parse", payload.old_source)
    new_source = git(workspace, "rev-parse", payload.new_source)
    if current_head not in {old_source, new_source}:
        raise HTTPException(
            409,
            "Source advance requires the job branch HEAD to remain at the exact old or already-advanced source commit",
        )

    remote_head = _fetch_remote_base_head(cfg, workspace, job_id=payload.job_id)
    if remote_head != payload.new_source:
        raise HTTPException(
            409,
            "Requested new source does not match the authoritative remote base head",
        )
    _assert_fast_forward(
        workspace,
        old_source,
        new_source,
        message="Requested source advance is not a fast-forward of the old job source",
    )

    dirty = _dirty_paths(workspace)
    dependency_paths = set(
        _zlist(
            workspace,
            "diff",
            "--name-only",
            "-z",
            old_source,
            new_source,
            "--",
        )
    )
    overlap = sorted(dirty & dependency_paths)
    if overlap:
        raise HTTPException(
            409,
            "Source advance would overlap preserved worktree changes: "
            + ", ".join(overlap[:20]),
        )

    before = _worktree_fingerprint(workspace, dirty)
    already_advanced = current_head == new_source
    if not already_advanced:
        git(workspace, "merge", "--ff-only", new_source)
    if git(workspace, "rev-parse", "HEAD") != new_source:
        raise HTTPException(409, "Source advance did not reach the requested new source")
    after = _worktree_fingerprint(workspace, dirty)
    if after != before:
        raise HTTPException(
            409,
            "Source advance changed preserved worktree content unexpectedly",
        )

    return {
        "job_id": payload.job_id,
        "project_id": payload.project_id,
        "workspace": str(workspace),
        "branch": payload.branch,
        "old_source": old_source,
        "new_source": new_source,
        "already_advanced": already_advanced,
        "dirty_paths": sorted(dirty)[:200],
        "dependency_paths": sorted(dependency_paths)[:200],
    }


@app.delete("/v1/workspaces", dependencies=[Depends(auth)])
def remove_workspace(job_id: str, project_id: str, workspace: str = Query(...)) -> dict[str, Any]:
    if project_id == 'pcp-local':
        raise HTTPException(403, 'pcp_local_preserve_owned_resources')
    cfg = project(project_id)
    path = _validate_workspace(job_id, project_id, workspace)
    if _workspace_instance_mode(cfg, job_id=job_id, path=path) == "direct":
        return {
            "removed": False,
            "preserved": True,
            "workspace": str(path),
            "reason": "direct_workspace_source_preserved",
        }
    if path.exists():
        shutil.rmtree(path)
    return {"removed": True, "workspace": str(path)}


@app.post("/v1/phase", response_model=PhaseResponse, dependencies=[Depends(auth)])
def phase(payload: PhaseRequest) -> PhaseResponse:
    if payload.project_id == 'pcp-local':
        return _pcp_phase(payload)
    cfg = project(payload.project_id)
    _require_ddev_enabled(cfg)
    workspace = _validate_workspace(
        payload.job_id,
        payload.project_id,
        payload.workspace,
        require_git=False,
    )
    if payload.project_id in {G1_PROJECT_ID, G1_PILOT_ID, G1_T02_ID}:
        # A G1 phase can only use a separately attested running DDEV; never
        # bootstrap/restart the T02 container, even for a normal preflight.
        try:
            if payload.project_id == G1_PROJECT_ID:
                require_g1_isolated_ddev(workspace)
            elif payload.project_id == G1_PILOT_ID:
                if os.getenv("PCP_G1_PILOT_IDENTITY_ENABLED") != "owner-approved":
                    raise HTTPException(403, "G1 pilot identity gate is OFF")
                require_g1_pilot_isolated_ddev(workspace)
            else:
                if os.getenv("PCP_G1_T02_IDENTITY_ENABLED") != "owner-approved":
                    raise HTTPException(403, "G1 T02 identity gate is OFF")
                require_g1_t02_isolated_ddev(workspace)
        except G1IsolationStop as exc:
            raise HTTPException(409, str(exc)) from None

    if _workspace_instance_mode(
        cfg,
        job_id=payload.job_id,
        path=workspace,
    ) == "isolated_clone":
        _reconcile_workspace_ddev_identity(
            workspace,
            payload.job_id,
            project_id=payload.project_id,
            nodejs_version=cfg.get("ddev", {}).get("workspace_nodejs_version"),
        )

    commands = cfg.get("ddev", {}).get(payload.phase, []) or []
    if not isinstance(commands, list) or any(not isinstance(command, str) for command in commands):
        raise HTTPException(500, f"Configured phase {payload.phase!r} must be a list of command strings")

    outputs: list[CommandOutput] = []
    infrastructure: list[CommandOutput] = []
    passed = True

    if (
        _workspace_instance_mode(
            cfg,
            job_id=payload.job_id,
            path=workspace,
        ) == "direct"
        and payload.phase == "frontend_quality"
    ):
        preview = cfg.get("preview") or {}
        frontend = (
            dict(preview.get("frontend") or {})
            if isinstance(preview, dict)
            else {}
        )
        paused = _pause_frontend_preview(
            payload.job_id,
            workspace,
            frontend,
        )
        if paused is not None:
            infrastructure.append(paused)
            if paused.returncode != 0:
                return PhaseResponse(
                    passed=False,
                    phase=payload.phase,
                    commands=[],
                    infrastructure=infrastructure,
                )
        _write_direct_node_override(
            workspace,
            _direct_nodejs_version(cfg),
        )
    timeout = min(
        int(os.getenv("DDEV_COMMAND_TIMEOUT_SECONDS", "1800")),
        payload.timeout_seconds or 1800,
    )

    if payload.phase != "cleanup":
        workspace_mode = _workspace_instance_mode(
            cfg,
            job_id=payload.job_id,
            path=workspace,
        )
        reuse_running_direct_ddev = bool(
            (cfg.get("ddev") or {}).get("reuse_running_direct_ddev", False)
        )
        direct_ddev_config_dirty = bool(
            git(
                workspace,
                "status",
                "--porcelain",
                "--",
                ".ddev",
                check=False,
            ).strip()
        )
        # A G1 workspace has already passed Docker runtime attestation above;
        # do not run the normal mutating ddev start/restart path.
        reused_running_direct_ddev = payload.project_id in {G1_PROJECT_ID, G1_PILOT_ID, G1_T02_ID}

        if (
            workspace_mode == "direct"
            and reuse_running_direct_ddev
            and payload.phase != "frontend_quality"
            and not direct_ddev_config_dirty
        ):
            probe_timeout = max(1, min(timeout, 30))
            returncode, stdout, stderr, timed_out = run_tracked(
                payload.job_id,
                ["ddev", "exec", "true"],
                cwd=workspace,
                timeout=probe_timeout,
                env=_ddev_subprocess_env(),
            )
            infrastructure.append(
                CommandOutput(
                    command="ddev exec true",
                    returncode=returncode,
                    stdout=stdout[-12000:],
                    stderr=stderr[-12000:],
                    timed_out=timed_out,
                )
            )
            reused_running_direct_ddev = returncode == 0

        if not reused_running_direct_ddev:
            start_timeout = _effective_ddev_start_timeout(timeout)
            returncode, stdout, stderr, timed_out = run_tracked(
                payload.job_id,
                ["ddev", "start", "-y"],
                cwd=workspace,
                timeout=start_timeout,
                env=_ddev_subprocess_env(),
            )
            if returncode != 0 or timed_out:
                # This is a diagnostic stage hint, not a proven BuildKit cause.
                hint = _ddev_start_failure_hint(
                    stdout, stderr, timed_out=timed_out, timeout=start_timeout,
                )
                stderr = f"{stderr[-11500:]}\n{hint}"
            infrastructure.append(
                CommandOutput(
                    command="ddev start -y",
                    returncode=returncode,
                    stdout=stdout[-12000:],
                    stderr=stderr[-12000:],
                    timed_out=timed_out,
                )
            )
            if returncode != 0:
                if (
                    workspace_mode == "direct"
                    and payload.phase == "frontend_quality"
                ):
                    _remove_managed_direct_node_override(workspace)
                return PhaseResponse(
                    passed=False,
                    phase=payload.phase,
                    commands=[],
                    infrastructure=infrastructure,
                )

    for command in commands:
        returncode, stdout, stderr, timed_out = run_tracked(
            payload.job_id,
            ["bash", "-lc", command],
            cwd=workspace,
            timeout=timeout,
            env=_ddev_subprocess_env(),
        )
        outputs.append(
            CommandOutput(
                command=command,
                returncode=returncode,
                stdout=stdout[-30000:],
                stderr=stderr[-30000:],
                timed_out=timed_out,
            )
        )
        if returncode != 0:
            passed = False
            break

    if (
        _workspace_instance_mode(
            cfg,
            job_id=payload.job_id,
            path=workspace,
        ) == "direct"
        and payload.phase == "frontend_quality"
    ):
        _remove_managed_direct_node_override(workspace)

    return PhaseResponse(
        passed=passed,
        phase=payload.phase,
        commands=outputs,
        infrastructure=infrastructure,
    )


# G1 disposable fixture tool surface. This is an opt-in broker capability, NOT
# PLATFORM_INTERNAL_TOKEN and not an arbitrary host/Docker command executor.
# The developer may learn the restricted token but it has no other API rights.
_TRUSTED_DEV_PHASES = frozenset({
    "targeted_tests", "static_analysis", "frontend_quality",
})
_TRUSTED_DEV_BINARIES = frozenset({
    "php", "composer", "vendor/bin/phpunit", "vendor/bin/phpcs",
    "npm", "node",
})
_TRUSTED_DEV_CALLS: dict[str, int] = {}
_TRUSTED_DEV_CALLS_LOCK = threading.Lock()


class TrustedCodexPhaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    project_id: str = Field(pattern=r"^pcp-benchmark-[a-z0-9-]{2,80}$")
    workspace: str = Field(min_length=12, max_length=2000)
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    phase: Literal["targeted_tests", "static_analysis", "frontend_quality"]


def _trusted_codex_dev_flags() -> tuple[str, str, str, str]:
    if os.getenv("PCP_TRUSTED_CODEX_BROKER_ENABLED") != "owner-approved":
        raise HTTPException(503, "Trusted Codex broker is not activated")
    pid = os.getenv("PCP_TRUSTED_CODEX_PROJECT_ID", "")
    jid = os.getenv("PCP_TRUSTED_CODEX_JOB_ID", "")
    source = os.getenv("PCP_TRUSTED_CODEX_SOURCE_SHA", "")
    token = os.getenv("PCP_TRUSTED_CODEX_DEV_TOKEN", "")
    deadline = os.getenv("PCP_TRUSTED_CODEX_DEADLINE_EPOCH", "")
    if not (deadline.isascii() and deadline.isdecimal() and len(deadline) <= 12):
        raise HTTPException(503, "Scoped developer capability has no finite deadline")
    seconds_left = int(deadline) - int(time.time())
    if not 0 < seconds_left <= 1800:
        raise HTTPException(503, "Scoped developer capability expired or too long-lived")
    if not (
        re.fullmatch(r"pcp-benchmark-[a-z0-9-]{2,80}", pid)
        and re.fullmatch(r"[a-f0-9]{32}", jid)
        and re.fullmatch(r"[a-f0-9]{40}", source)
        and re.fullmatch(r"[A-Za-z0-9_-]{40,128}", token)
        and token not in {
            os.getenv("PLATFORM_INTERNAL_TOKEN", ""),
            os.getenv("GITHUB_DELIVERY_TOKEN", ""),
            os.getenv("ROUTER_API_TOKEN", ""),
            os.getenv("RUNTIME_API_TOKEN", ""),
        }
        and not os.getenv("PCP_EXECUTOR_PROJECT_SCOPE")
        and not any(os.getenv(k) for k in (
            "PCP_F2_GIT_ONLY_ENABLED", "PCP_G0_EXECUTION_ENABLED",
            "PCP_G0_DELIVERY_ENABLED",
        ))
    ):
        raise HTTPException(503, "Trusted Codex singleton identity not available")
    return pid, jid, source, token


def trusted_codex_dev_auth(
    authorization: str | None = Header(default=None),
) -> None:
    _, _, _, expected = _trusted_codex_dev_flags()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing scoped developer bearer")
    if not secrets.compare_digest(
        authorization.removeprefix("Bearer ").strip(), expected,
    ):
        raise HTTPException(401, "Invalid scoped developer bearer")


def _trusted_dev_plan(payload: TrustedCodexPhaseRequest) -> tuple[Path, list[list[str]]]:
    project_id, job_id, source_sha, _ = _trusted_codex_dev_flags()
    if (
        payload.project_id != project_id
        or payload.job_id != job_id
        or payload.source_commit != source_sha
    ):
        raise HTTPException(403, "Developer job/project/source mismatch")
    registry = load_projects()
    if set(registry) != {project_id}:
        raise HTTPException(403, "Developer fixture registry is not singleton")
    cfg = project(project_id)
    runtime = cfg.get("runtime") or {}
    autonomy = cfg.get("autonomy") or {}
    ddev = cfg.get("ddev") or {}
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
        raise HTTPException(403, "Developer fixture is not allowed to execute")

    root_text = os.getenv("CODING_WORKSPACES_ROOT", "")
    if not root_text:
        raise HTTPException(503, "Dedicated developer workspaces root required")
    root = Path(root_text).resolve()
    raw = Path(payload.workspace)
    target = root / job_id
    if (
        raw.is_symlink()
        or target.is_symlink()
        or raw.resolve() != target.resolve()
        or target.resolve().parent != root
        or not target.is_dir()
        or not is_git_repo(target)
    ):
        raise HTTPException(403, "Developer workspace is not the exact isolated job")
    if (
        git(target, "rev-parse", "--show-toplevel") != str(target)
        or git(target, "branch", "--show-current") != "ai/" + job_id[:12]
        or git(target, "rev-parse", "HEAD") != source_sha
    ):
        raise HTTPException(403, "Developer workspace branch/source provenance changed")

    # A DDEV configuration modified by the model could inject host hooks,
    # arbitrary containers or Docker/socket mounts on the Executor host.
    # This broker NEVER bootstraps/restarts DDEV and refuses changed .ddev files.
    if git(target, "status", "--porcelain", "--", ".ddev", check=False):
        raise HTTPException(403, "Developer DDEV configuration is dirty")
    untracked = subprocess.run(
        ["git", "-C", str(target), "ls-files", "--others",
         "--exclude-standard", "--", ".ddev"],
        capture_output=True, text=True,
    )
    if untracked.returncode != 0 or untracked.stdout.strip():
        raise HTTPException(403, "Developer untracked DDEV configuration")
    ddev_dir = target / ".ddev"
    if ddev_dir.exists() and (
        ddev_dir.is_symlink()
        or any(path.is_symlink() for path in ddev_dir.rglob("*"))
    ):
        raise HTTPException(403, "Developer DDEV symlink refused")
    # DDEV supports pre/post-exec hooks, including exec-host. Such hooks would
    # run outside the approved phase argv even for an unchanged fixture seed.
    # The dedicated benchmark fixture must have NO project DDEV hooks.
    if ddev_dir.exists():
        for configuration in sorted(ddev_dir.glob("config*.yaml")) + sorted(
            ddev_dir.glob("config*.yml")
        ):
            try:
                if configuration.stat().st_size > 65536:
                    raise HTTPException(403, "Developer DDEV config is too large")
                raw_config = yaml.safe_load(configuration.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, yaml.YAMLError) as exc:
                raise HTTPException(403, "Developer DDEV config invalid") from exc
            if not isinstance(raw_config, dict) or "hooks" in raw_config:
                raise HTTPException(403, "Developer DDEV hooks are forbidden")

    if project_id == G1_PROJECT_ID:
        if source_sha != "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3":
            raise HTTPException(403, "G1 fixture source SHA is not pinned")
        try:
            require_g1_isolated_ddev(target)
        except G1IsolationStop as exc:
            raise HTTPException(409, str(exc)) from None
    elif project_id == G1_PILOT_ID:
        if (
            os.getenv("PCP_G1_PILOT_IDENTITY_ENABLED") != "owner-approved"
            or source_sha != G1_PILOT_SHA
            or runtime.get("pilot_identity") != "g1-t01-pcp"
            or cfg.get("base_branch") != "benchmark/g1-codex-smoke-v1"
        ):
            raise HTTPException(403, "G1 pilot identity admission denied")
        try:
            require_g1_pilot_isolated_ddev(target)
        except G1IsolationStop as exc:
            raise HTTPException(409, str(exc)) from None
    elif project_id == G1_T02_ID:
        if (
            os.getenv("PCP_G1_T02_IDENTITY_ENABLED") != "owner-approved"
            or source_sha != G1_T02_SHA
            or runtime.get("pilot_identity") != "g1-t02-pcp"
            or cfg.get("base_branch") != "benchmark/g1-codex-smoke-v1"
            or not (
                (os.getenv("PCP_G1_T02_DELIVERY_ENABLED") == "owner-approved"
                 and all(autonomy.get(key) is True for key in (
                     "allow_commit", "allow_push_ai_branch", "allow_create_pr",
                 )))
                or (os.getenv("PCP_G1_T02_DELIVERY_ENABLED") != "owner-approved"
                    and all(autonomy.get(key) is False for key in (
                        "allow_commit", "allow_push_ai_branch", "allow_create_pr",
                    )))
            )
        ):
            raise HTTPException(403, "G1 T02 identity admission denied")
        try:
            require_g1_t02_isolated_ddev(target)
        except G1IsolationStop as exc:
            raise HTTPException(409, str(exc)) from None
    else:
        raise HTTPException(403, "Foreign benchmark has no trusted tool identity")

    tools = cfg.get("trusted_codex_tools") or {}
    commands = tools.get(payload.phase) if isinstance(tools, dict) else None
    if not isinstance(commands, list) or not 1 <= len(commands) <= 4:
        raise HTTPException(403, "Phase has no approved bounded commands")
    approved: list[list[str]] = []
    for argv in commands:
        if not (
            isinstance(argv, list)
            and 3 <= len(argv) <= 30
            and all(isinstance(x, str) and 0 < len(x) <= 300
                    and "\x00" not in x and "\n" not in x
                    for x in argv)
            and argv[:2] == ["ddev", "exec"]
            and argv[2] in _TRUSTED_DEV_BINARIES
        ):
            raise HTTPException(403, "Trusted developer command not pre-approved")
        approved.append(argv)
    with _ACTIVE_LOCK:
        if any(
            jid != job_id and proc.poll() is None
            for jid, proc in _ACTIVE.items()
        ):
            raise HTTPException(409, "A foreign Executor job is active")
    return target, approved


def _trusted_dev_env() -> dict[str, str]:
    # The controlled Executor needs Docker access for "ddev exec", but code
    # inside the DDEV application container never receives these host tokens.
    # Scrub the Executor's sensitive credential names before subprocess entry.
    return {
        key: value for key, value in _ddev_subprocess_env().items()
        if not any(part in key.upper() for part in (
            "TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL",
        ))
    }


def _trusted_dev_redact(text: str) -> str:
    value = text[-5000:]
    for key, secret_value in os.environ.items():
        if (
            len(secret_value) >= 8
            and any(term in key.upper() for term in (
                "TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL",
            ))
        ):
            value = value.replace(secret_value, "[REDACTED]")
    return value


@app.post(
    "/v1/codex-dev/phase",
    dependencies=[Depends(trusted_codex_dev_auth)],
)
def trusted_codex_dev_phase(payload: TrustedCodexPhaseRequest) -> dict[str, Any]:
    # The handler enforces all constraints independently of HTTP dependencies,
    # so calling it directly cannot bypass the disposable fixture gate.
    workspace, commands = _trusted_dev_plan(payload)
    with _TRUSTED_DEV_CALLS_LOCK:
        used = _TRUSTED_DEV_CALLS.get(payload.job_id, 0)
        if used >= 8:
            raise HTTPException(429, "Scoped developer phase-call ceiling reached")
        _TRUSTED_DEV_CALLS[payload.job_id] = used + 1

    outputs: list[dict[str, Any]] = []
    for args in commands:
        rc, stdout, stderr, timed_out = run_tracked(
            payload.job_id, args, cwd=workspace, timeout=160,
            env=_trusted_dev_env(),
        )
        outputs.append({
            "command": args[2],
            "returncode": rc,
            "stdout": _trusted_dev_redact(stdout),
            "stderr": _trusted_dev_redact(stderr),
            "timed_out": timed_out,
        })
        if rc != 0 or timed_out:
            break
    return {
        "job_id": payload.job_id, "project_id": payload.project_id,
        "phase": payload.phase,
        "passed": len(outputs) == len(commands)
        and all(x["returncode"] == 0 and not x["timed_out"] for x in outputs),
        "commands": outputs,
        "tool_calls_used": used + 1,
        "tool_calls_max": 8,
    }


# GH-815: PCP-only verification uses an Executor-owned copy, never the source
# repository's .ddev. No caller supplies commands, mounts or Compose documents.
_PCP_LOCAL = 'pcp-local'
_PCP_REPOSITORY = 'sonvhse06072/personal-coding-platform'


class PcpLocalObservationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    source_commit: str = Field(pattern=r'^[0-9a-f]{40}$')
    activation_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


def _pcp_digest(value):
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _pcp_activation():
    import json
    path = Path('/config/pcp-local-activation.json')
    if path.is_symlink() or not path.is_file():
        raise HTTPException(403, 'pcp_local_operational_delegation_missing')
    value = json.loads(path.read_text())
    if (value.get('project_id') != _PCP_LOCAL or value.get('repository') != _PCP_REPOSITORY
            or type(value.get('expires_at')) not in (int, float)
            or time.time() >= value['expires_at']):
        raise HTTPException(403, 'pcp_local_operational_delegation_invalid')
    return value


def _pcp_identity(job_id, source_commit=None):
    a = _pcp_activation()
    cfg = project(_PCP_LOCAL)
    root = Path(a['root'])
    expected_id = hashlib.sha256((f"pcp-local:v1:{_PCP_REPOSITORY}:{a['issue_number']}:"
        f"{a['body_sha256']}:{a['base_sha']}:{a['baseline_revision']}").encode('ascii')).hexdigest()[:32]
    if (not root.is_absolute() or root.is_symlink() or root.resolve() != root
            or not re.fullmatch(r'pcp-local-[a-z0-9][a-z0-9-]{5,30}', root.name)
            or set(load_projects()) != {_PCP_LOCAL}
            or job_id != expected_id
            or (source_commit is not None and source_commit != a['base_sha'])
            or cfg.get('repository') != _PCP_REPOSITORY
            or cfg.get('registration_status') != 'approved'
            or Path(cfg['path']).resolve() != root / 'sources/personal-coding-platform'
            or Path(os.environ['CODING_WORKSPACES_ROOT']).resolve() != root / 'workspaces'
            or cfg.get('runtime', {}).get('workspace_mode') != 'isolated_clone'
            or cfg.get('runtime', {}).get('developer_permission_mode') != 'bounded'):
        raise HTTPException(403, 'pcp_local_identity_invalid')
    return a, cfg, root


def _pcp_docker(kind, name, *, missing_ok=False):
    import json
    result = subprocess.run(['docker', '--host', 'unix:///var/run/docker.sock',
        kind, 'inspect', name], text=True, capture_output=True, timeout=15, check=False,
        env={'PATH': os.environ.get('PATH', '/usr/bin:/bin')})
    if result.returncode:
        if missing_ok and ('no such' in result.stderr.lower() or 'not found' in result.stderr.lower()):
            return None
        raise HTTPException(409, 'pcp_local_resource_unavailable')
    try:
        items = json.loads(result.stdout)
        if not isinstance(items, list) or len(items) != 1:
            raise ValueError()
        return items[0]
    except (ValueError, TypeError):
        raise HTTPException(409, 'pcp_local_resource_identity_invalid') from None


@app.post('/v1/pcp-local/observe', dependencies=[Depends(auth)])
def pcp_local_observe(payload: PcpLocalObservationRequest):
    a, cfg, root = _pcp_identity(payload.job_id, payload.source_commit)
    if payload.activation_digest != _pcp_digest(a):
        raise HTTPException(403, 'pcp_local_delegation_mismatch')
    state = project_state(_PCP_LOCAL)
    if not state['clean'] or state['head'] != payload.source_commit:
        raise HTTPException(409, 'pcp_local_source_changed')
    name = f'ddev-{root.name}-coding-runtime'
    item = _pcp_docker('container', name)
    host = item.get('HostConfig', {})
    expected = {
        '/config': (str(root / 'instance/config'), False),
        str(root / 'workspaces'): (str(root / 'workspaces'), True),
        '/home/coder': (str(root / 'runtime-home'), True),
    }
    mounts = item.get('Mounts', [])
    if (item.get('Name') != '/' + name or not item.get('State', {}).get('Running')
            or item.get('Image') != a['runtime_image_id']
            or host.get('Privileged') is not False or host.get('PidMode') == 'host'
            or host.get('NetworkMode') == 'host' or host.get('CapAdd')
            or host.get('ReadonlyRootfs') is not True
            or len(mounts) != len(expected)
            or any(m.get('Type') != 'bind' or
                expected.get(m.get('Destination')) != (m.get('Source'), m.get('RW'))
                for m in mounts)):
        raise HTTPException(409, 'pcp_local_runtime_isolation_invalid')
    network_name = a['runtime_network']
    if set(item.get('NetworkSettings', {}).get('Networks', {})) != {network_name}:
        raise HTTPException(409, 'pcp_local_runtime_network_invalid')
    network = _pcp_docker('network', network_name)
    permitted = {f'ddev-{root.name}-{service}' for service in ('coding-runtime','router','ddev-executor','db','web')}
    if any(peer.get('Name') not in permitted for peer in network.get('Containers', {}).values()):
        raise HTTPException(409, 'pcp_local_foreign_network_peer')
    delivery, repository = _github_context(cfg)
    if repository != _PCP_REPOSITORY:
        raise HTTPException(403, 'pcp_local_publisher_repository_invalid')
    with delivery._client() as client:
        response = client.get(f'{delivery.base}/repos/{repository}')
        response.raise_for_status()
        if response.json().get('permissions', {}).get('push') is not True:
            raise HTTPException(403, 'pcp_local_publisher_not_authorized')
    return dict(job_id=payload.job_id, source_commit=payload.source_commit,
        activation_digest=_pcp_digest(a),
        isolation=dict(current_main_sha=state['head'], source_repo_clean=True,
            other_repo_mounts=False, agent_docker_socket=False, isolated_ddev_network=True),
        provider=dict(credential_scoped=True, github_token_in_agent=False,
            host_keyring_mounted=False, provider_network_reviewed=True),
        publisher=dict(project_id=_PCP_LOCAL, repository=repository, executor_only=True,
            allow_create_pr=cfg['autonomy'].get('allow_create_pr'), allow_merge=False,
            credential_in_agent=False))


def _pcp_no_symlinks(path):
    if path.is_symlink() or not path.is_dir() or any(p.is_symlink() for p in path.rglob('*')):
        raise HTTPException(403, 'pcp_local_symlink_denied')


def _pcp_job_config(name, image):
    if not re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', image):
        raise HTTPException(403, 'pcp_local_verification_image_not_pinned')
    return yaml.safe_dump(dict(name=name, type='php', docroot='', php_version='8.4',
        webserver_type='nginx-fpm', webimage=image, use_dns_when_possible=False,
        omit_containers=['db', 'ddev-ssh-agent', 'ddev-router'], web_environment=[]))


def _pcp_verification_copy(payload, a, root):
    """Snapshot code into an exact Executor-only root; exclude ALL legacy DDEV."""
    raw = Path(payload.workspace)
    if raw.is_symlink() or raw != root / 'workspaces' / payload.job_id:
        raise HTTPException(403, 'pcp_local_workspace_identity_invalid')
    workspace = _validate_workspace(payload.job_id, _PCP_LOCAL, payload.workspace)
    _pcp_no_symlinks(workspace)
    if (workspace / '.env').exists():
        raise HTTPException(403, 'pcp_local_inherited_environment_denied')
    if git(workspace, 'merge-base', 'HEAD', a['base_sha']) != a['base_sha']:
        raise HTTPException(403, 'pcp_local_workspace_source_changed')
    # Stable per-content identity makes retries inspect the same owned artifact.
    entries = {}
    for path in sorted(workspace.rglob('*')):
        relative = path.relative_to(workspace)
        if relative.parts[0] in {'.git', '.ddev', '.venv', '__pycache__', '.pytest_cache'}:
            continue
        if path.is_file():
            entries[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    code_digest = _pcp_digest(entries)
    target = root / 'sources/.pcp-local-verification' / payload.job_id / code_digest
    name = 'pcp-local-' + payload.job_id[:12] + '-' + code_digest[:8]
    config = _pcp_job_config(name, a['verification_image'])
    # Reviewed override: one web container, private internal network/cache;
    # no source-provided Compose, ports, sockets or host HOME are included.
    overlay = (
        'services:\n  web:\n    networks: !override [default]\n'
        '    ports: !reset []\n    volumes: !override\n'
        f'      - "{target}:/var/www/html"\n'
        f'      - "{target / ".ddev"}:/mnt/ddev_config"\n'
        '      - pcp-local-cache:/mnt/ddev-global-cache\n'
        'networks: !override\n  default:\n'
        f'    name: {name}-private\n    internal: true\n'
        'volumes: !override\n  pcp-local-cache:\n'
        f'    name: {name}-cache\n'
    )
    files = {'.ddev/config.yaml': config, '.ddev/docker-compose.pcp-local.yaml': overlay,
             '.ddev/web-build/Dockerfile': (
                 'ARG BASE_IMAGE\nFROM ${BASE_IMAGE}\n'
                 'RUN apt-get update && apt-get install -y --no-install-recommends python3-venv '
                 '&& python3 -m venv /opt/pcp-tests '
                 '&& /opt/pcp-tests/bin/pip install --no-cache-dir pytest==8.3.5 PyYAML==6.0.2 '
                 '&& rm -rf /var/lib/apt/lists/*\n'),
             '.pcp-verification.json': __import__('json').dumps(entries, sort_keys=True)}
    if target.exists():
        _pcp_no_symlinks(target)
        for key, text in files.items():
            if not (target / key).is_file() or (target / key).read_text() != text:
                raise HTTPException(409, 'pcp_local_verification_copy_changed')
    else:
        # Refuse a symlink in any existing parent before creating owned files.
        if any(p.is_symlink() for p in [target, *target.parents]):
            raise HTTPException(403, 'pcp_local_verification_parent_symlink')
        target.mkdir(parents=True)
        for key in entries:
            dest = target / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(workspace / key, dest)
        for key, text in files.items():
            dest = target / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
    if (target / '.env').exists():
        raise HTTPException(403, 'pcp_local_inherited_environment_denied')
    for key, checksum in entries.items():
        if hashlib.sha256((target / key).read_bytes()).hexdigest() != checksum:
            raise HTTPException(409, 'pcp_local_verification_source_changed')
    allowed = {'config.yaml', 'docker-compose.pcp-local.yaml', 'web-build',
               '.ddev-docker-compose-base.yaml', '.ddev-docker-compose-full.yaml',
               '.webimageBuild', '.gitignore'}
    if not {p.name for p in (target / '.ddev').iterdir()} <= allowed:
        raise HTTPException(409, 'pcp_local_untrusted_ddev_configuration')
    if {p.name for p in (target / '.ddev/web-build').iterdir()} != {'Dockerfile'}:
        raise HTTPException(403, 'pcp_local_untrusted_image_build')
    return target, name


def _pcp_effective_compose(document, target, name):
    """Validate the rendered document BEFORE ddev start can run a hook/service."""
    services = document.get('services', {})
    if set(services) != {'web'}:
        raise HTTPException(403, 'pcp_local_extra_service')
    web = services['web']
    if (web.get('privileged') or web.get('pid') or web.get('network_mode')
            or web.get('cap_add') or web.get('devices') or web.get('env_file')
            or web.get('container_name') != 'ddev-' + name + '-web'
            or set(web.get('networks', {})) != {'default'}):
        raise HTTPException(403, 'pcp_local_privileged_compose')
    environment = web.get('environment', {})
    if not isinstance(environment, dict) or any(k in environment for k in (
            'GITHUB_DELIVERY_TOKEN', 'GITHUB_TOKEN', 'GH_TOKEN', 'PLATFORM_INTERNAL_TOKEN',
            'RUNTIME_API_TOKEN', 'ROUTER_API_TOKEN', 'OPENAI_API_KEY', 'CODEX_HOME')):
        raise HTTPException(403, 'pcp_local_verification_credentials_denied')
    if not web.get('volumes'):
        raise HTTPException(403, 'pcp_local_verification_mounts_missing')
    for mount in web.get('volumes', []):
        if not isinstance(mount, dict):
            raise HTTPException(403, 'pcp_local_mount_unresolved')
        source, destination = mount.get('source'), mount.get('target')
        if not ((mount.get('type') == 'bind' and source in (str(target), str(target / '.ddev'))
                 and destination in ('/var/www/html', '/mnt/ddev_config'))
                or (mount.get('type') == 'volume' and source == 'pcp-local-cache'
                    and destination == '/mnt/ddev-global-cache')):
            raise HTTPException(403, 'pcp_local_foreign_mount')
    network = document.get('networks', {}).get('default', {})
    if network.get('name') != name + '-private' or network.get('internal') is not True or network.get('external'):
        raise HTTPException(403, 'pcp_local_shared_network')
    if any(p.get('host_ip') != '127.0.0.1' for p in web.get('ports', [])):
        raise HTTPException(403, 'pcp_local_public_port')


def _pcp_resources(target, name, *, running=False):
    web = 'ddev-' + name + '-web'
    for kind, resource in (('container', web), ('network', name + '-private'), ('volume', name + '-cache')):
        item = _pcp_docker(kind, resource, missing_ok=not running)
        if item is None:
            continue
        labels = (item.get('Config', {}).get('Labels') if kind == 'container' else item.get('Labels')) or {}
        if labels.get('com.docker.compose.project') != 'ddev-' + name:
            raise HTTPException(409, 'pcp_local_resource_collision')
        if kind == 'container':
            if labels.get('com.ddev.approot') != str(target):
                raise HTTPException(409, 'pcp_local_resource_collision')
            host = item.get('HostConfig') or {}
            if host.get('Privileged') or host.get('PidMode') == 'host' or host.get('CapAdd'):
                raise HTTPException(403, 'pcp_local_privileged_test_container')
            for mount in item.get('Mounts', []):
                if not ((mount.get('Type') == 'bind' and mount.get('Source') in (str(target), str(target / '.ddev')))
                        or (mount.get('Type') == 'volume' and mount.get('Name') == name + '-cache')):
                    raise HTTPException(403, 'pcp_local_foreign_test_mount')
            if running and (not item.get('State', {}).get('Running') or
                    set(item.get('NetworkSettings', {}).get('Networks', {})) != {name + '-private'}):
                raise HTTPException(409, 'pcp_local_test_container_not_isolated')
        if kind == 'network' and (item.get('Internal') is not True or
                any(peer.get('Name') != web for peer in item.get('Containers', {}).values())):
            raise HTTPException(409, 'pcp_local_foreign_network_peer')


def _pcp_phase(payload):
    a, cfg, root = _pcp_identity(payload.job_id)
    if cfg.get('ddev', {}).get('enabled') is not True or payload.phase not in ('targeted_tests', 'full_tests'):
        raise HTTPException(403, 'pcp_local_verification_phase_denied')
    tests = cfg['ddev'].get(payload.phase)
    if (not isinstance(tests, list) or not tests or any(not isinstance(p, str)
            or not re.fullmatch(r'tests/test_pcp_light_[A-Za-z0-9_]+\.py', p) for p in tests)):
        raise HTTPException(403, 'pcp_local_mandatory_tests_missing')
    target, name = _pcp_verification_copy(payload, a, root)
    _pcp_resources(target, name)
    # DDEV runs with a dedicated empty HOME, no publisher/provider/service env.
    home = root / 'sources/.pcp-local-verification-home'
    if home.is_symlink():
        raise HTTPException(403, 'pcp_local_verification_home_invalid')
    home.mkdir(exist_ok=True)
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(home),
           'DOCKER_HOST': 'unix:///var/run/docker.sock', 'DDEV_NONINTERACTIVE': 'true'}
    timeout = min(payload.timeout_seconds or 900, 900)
    def run(argv):
        return run_tracked(payload.job_id, argv, cwd=target, timeout=timeout, env=env)
    rc, out, _, expired = run(['ddev', 'debug', 'compose-config'])
    if rc or expired:
        raise HTTPException(409, 'pcp_local_compose_render_failed')
    _pcp_effective_compose(yaml.safe_load(out), target, name)
    rc, out, err, expired = run(['ddev', 'start', '-y'])
    if rc or expired:
        return PhaseResponse(passed=False, phase=payload.phase, commands=[], infrastructure=[
            CommandOutput(command='ddev start -y', returncode=rc, stdout=out[-30000:], stderr=err[-30000:], timed_out=expired)])
    _pcp_resources(target, name, running=True)
    command = ['ddev', 'exec', '/opt/pcp-tests/bin/python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *tests]
    rc, out, err, expired = run(command)
    # Pytest's exit code 5 rejects zero collection; also require an actual pass
    # count, rather than accepting an all-skipped run as mandatory evidence.
    passed = rc == 0 and not expired and re.search(r'\b[1-9][0-9]* passed\b', out) is not None
    return PhaseResponse(passed=passed, phase=payload.phase, commands=[
        CommandOutput(command=' '.join(command), returncode=rc, stdout=out[-30000:], stderr=err[-30000:], timed_out=expired)])


def _pcp_draft_pr(payload):
    """Keep the generic publisher intact; PCP-only creation is always Draft."""
    a, cfg, _ = _pcp_identity(payload.job_id)
    if (payload.branch != 'ai/' + payload.job_id[:12]
            or cfg.get('autonomy', {}).get('allow_create_pr') is not True):
        raise HTTPException(403, 'pcp_local_draft_identity_invalid')
    delivery, repository = _github_context(cfg)
    if repository != _PCP_REPOSITORY:
        raise HTTPException(403, 'pcp_local_publisher_repository_invalid')
    delivery.assert_branch_commit(repository, payload.branch, payload.expected_commit)
    with delivery._client() as client:
        endpoint = f'{delivery.base}/repos/{repository}/pulls'
        response = client.get(endpoint, params={'state': 'open',
            'head': repository.split('/')[0] + ':' + payload.branch, 'base': 'main'})
        response.raise_for_status()
        existing = response.json()
        if len(existing) > 1:
            raise HTTPException(409, 'pcp_local_ambiguous_pr')
        if existing:
            data = existing[0]
            # Never overwrite an independently reviewed PR during retry.
            created = False
        else:
            response = client.post(endpoint, json={'head': payload.branch, 'base': 'main',
                'title': payload.title, 'body': payload.body, 'draft': True})
            response.raise_for_status()
            data = response.json()
            created = True
    if (data.get('head', {}).get('sha') != payload.expected_commit
            or data.get('head', {}).get('ref') != payload.branch
            or data.get('base', {}).get('ref') != 'main'
            or data.get('head', {}).get('repo', {}).get('full_name') != repository
            or data.get('draft') is not True):
        raise HTTPException(409, 'pcp_local_draft_proof_invalid')
    return dict(job_id=payload.job_id, created=created, number=data['number'],
        url=data['html_url'], state=data['state'], head=payload.expected_commit,
        head_ref=payload.branch, base_ref='main', repository=repository, draft=True)
