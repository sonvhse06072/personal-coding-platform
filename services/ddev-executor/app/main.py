from __future__ import annotations

import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
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


Phase = Literal["preflight", "targeted_tests", "static_analysis", "frontend_quality", "full_tests", "cleanup"]
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


class PublishBranchRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    branch: str = Field(min_length=1, max_length=200)
    source_commit: str = Field(min_length=7, max_length=64)
    expected_commit: str = Field(min_length=7, max_length=64)


class PullRequestRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    branch: str = Field(min_length=1, max_length=200)
    expected_commit: str = Field(min_length=7, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=30000)


class CancelRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)


class QuiesceWorkspaceRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    remove_data: bool = False


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
    script = (
        "for i in $(seq 1 30); do "
        f"curl -fsS http://127.0.0.1:{port}/ >/dev/null 2>&1 && exit 0; "
        "sleep 1; done; exit 1"
    )
    return _preview_run(
        job_id,
        ["ddev", "exec", "bash", "-lc", script],
        workspace=workspace,
        timeout=45,
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


app = FastAPI(title="Constrained DDEV/Git Executor", version="1.0.19")
app.include_router(pm_bridge_github_router)


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
        "version": "1.0.19",
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

    started = _preview_run(
        payload.job_id,
        ["ddev", "start", "-y"],
        workspace=workspace,
        timeout=600,
    )
    infrastructure.append(started)
    if started.returncode != 0:
        raise HTTPException(502, (started.stderr or started.stdout or "ddev start failed")[-12000:])

    if payload.target in {"frontend", "both"}:
        for command in frontend.get("prepare") or []:
            result = _preview_run(
                payload.job_id,
                ["bash", "-lc", command],
                workspace=workspace,
                timeout=1800,
            )
            infrastructure.append(result)
            if result.returncode != 0:
                raise HTTPException(502, (result.stderr or result.stdout or "preview prepare failed")[-12000:])

        _write_preview_override(
            workspace,
            frontend=frontend,
            target=payload.target,
            nodejs_version=_direct_nodejs_version(cfg),
        )
        restarted = _preview_run(
            payload.job_id,
            ["ddev", "restart", "-y"],
            workspace=workspace,
            timeout=600,
        )
        infrastructure.append(restarted)
        if restarted.returncode != 0:
            _remove_managed_preview_override(workspace)
            raise HTTPException(502, (restarted.stderr or restarted.stdout or "preview restart failed")[-12000:])

        daemon = dict(frontend.get("daemon") or {})
        health = _preview_health(
            payload.job_id,
            workspace,
            int(daemon["container_port"]),
        )
        infrastructure.append(health)
        if health.returncode != 0:
            # A failed preview must not leave a managed daemon/config behind.
            # Cleanup is exact and best-effort; the coding project's normal DDEV
            # runtime remains running.
            try:
                _pause_frontend_preview(
                    payload.job_id,
                    workspace,
                    frontend,
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
            "Frontend is pointed at the local backend; credentialed browser flows still depend on the project's existing CORS/auth policy."
            if payload.target == "both"
            else None
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
    _remove_managed_direct_node_override(workspace)
    return {
        "job_id": payload.job_id,
        "project_id": payload.project_id,
        "target": payload.target,
        "status": "stopped",
        "frontend_url": None,
        "backend_url": None,
    }


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
    source_commit = git(repo, "rev-parse", ref)
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
        git(repo, "checkout", "-b", branch, source_commit)
        return {
            "workspace": str(repo),
            "branch": branch,
            "source_commit": source_commit,
            "workspace_mode": "direct",
        }

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
        if remote_origin(workspace):
            git(workspace, "remote", "remove", "origin")
        git(workspace, "checkout", "-b", branch, source_commit)
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
            branch=payload.branch,
            base_branch=base_branch,
            expected_commit=payload.expected_commit,
            title=payload.title,
            body=payload.body,
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
        if (
            _workspace_instance_mode(
                cfg,
                job_id=payload.job_id,
                path=workspace,
            ) == "direct"
            and payload.phase == "frontend_quality"
        ):
            _remove_managed_direct_node_override(workspace)
        if returncode != 0:
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

    return PhaseResponse(
        passed=passed,
        phase=payload.phase,
        commands=outputs,
        infrastructure=infrastructure,
    )
