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
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .github_delivery import (
    GitHubDelivery,
    github_git_env,
    github_push_url,
    github_repository_from_origin,
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


def load_projects() -> dict[str, Any]:
    with open(os.getenv("PROJECTS_FILE", "/config/projects.yml"), "r", encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("projects", {})


def expand(value: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(value))).resolve()


def project(project_id: str) -> dict[str, Any]:
    projects = load_projects()
    if project_id not in projects:
        raise HTTPException(404, "Unknown project")
    return projects[project_id]


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
    nodejs_version: str | None = None,
) -> Path | None:
    """Keep one deterministic private DDEV identity/runtime per workspace.

    Source repositories may commit their own project name/runtime settings in
    .ddev/config.yaml. The executor must not edit that tracked source file, so
    it owns one private config.*.yaml override instead. Rewriting the override
    before every DDEV phase upgrades preserved/resumed workspaces in place.
    """
    ddev_dir = workspace / ".ddev"
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


def _github_context(cfg: dict[str, Any]) -> tuple[GitHubDelivery, str]:
    _, origin = _source_origin(cfg)
    repository = github_repository_from_origin(origin)
    if not repository:
        raise HTTPException(422, "Source origin is not a supported github.com repository")
    delivery = GitHubDelivery()
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


DDEV_EXECUTOR_VERSION = "1.0.32"

app = FastAPI(title="Constrained DDEV/Git Executor", version=DDEV_EXECUTOR_VERSION)
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
    cfg = project(payload.project_id)
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
        _reconcile_workspace_ddev_identity(
            workspace,
            payload.job_id,
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


@app.post("/v1/publish-branch", dependencies=[Depends(auth)])
def publish_branch(payload: PublishBranchRequest) -> dict[str, Any]:
    """Push exactly one verified AI branch without adding a remote to the workspace."""
    cfg = project(payload.project_id)
    autonomy = cfg.get("autonomy", {}) or {}
    if not bool(autonomy.get("allow_push_ai_branch", False)):
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

    _, origin = _source_origin(cfg)
    repository = github_repository_from_origin(origin)
    push_target = origin
    push_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if repository:
        delivery = GitHubDelivery()
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
    cfg = project(payload.project_id)
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
    cfg = project(payload.project_id)
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
    cfg = project(payload.project_id)
    autonomy = cfg.get("autonomy", {}) or {}
    if not bool(autonomy.get("allow_create_pr", False)):
        raise HTTPException(403, "Project policy does not allow pull-request creation")
    _validate_ai_branch(cfg, payload.branch)
    delivery, repository = _github_context(cfg)
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
    autonomy = cfg.get("autonomy", {}) or {}
    if not bool(autonomy.get("allow_create_pr", False)):
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
    cfg = project(payload.project_id)
    workspace = _validate_workspace(
        payload.job_id,
        payload.project_id,
        payload.workspace,
        require_git=False,
    )

    if _workspace_instance_mode(
        cfg,
        job_id=payload.job_id,
        path=workspace,
    ) == "isolated_clone":
        _reconcile_workspace_ddev_identity(
            workspace,
            payload.job_id,
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
        reused_running_direct_ddev = False

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
            returncode, stdout, stderr, timed_out = run_tracked(
                payload.job_id,
                ["ddev", "start", "-y"],
                cwd=workspace,
                timeout=min(timeout, 600),
                env=_ddev_subprocess_env(),
            )
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
