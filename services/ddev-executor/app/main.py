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

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field


Phase = Literal["preflight", "targeted_tests", "static_analysis", "full_tests", "cleanup"]
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


class PublishBranchRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=2000)
    branch: str = Field(min_length=1, max_length=200)
    source_commit: str = Field(min_length=7, max_length=64)
    expected_commit: str = Field(min_length=7, max_length=64)


class CancelRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)


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


_ACTIVE: dict[str, subprocess.Popen] = {}
_ACTIVE_LOCK = threading.Lock()


def auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("PLATFORM_INTERNAL_TOKEN", "change-me")
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


def _validate_workspace(job_id: str, workspace: str) -> Path:
    path = Path(workspace).resolve()
    root = Path(os.environ["CODING_WORKSPACES_ROOT"]).resolve()
    if not allowed_workspace(path) or path.name != job_id or path.parent != root:
        raise HTTPException(403, "Workspace is outside configured root or does not match job")
    if not path.exists() or not is_git_repo(path):
        raise HTTPException(404, "Workspace does not exist or is not a git repository")
    return path


def _validate_ai_branch(cfg: dict[str, Any], branch: str) -> None:
    prefix = str(cfg.get("runtime", {}).get("branch_prefix", "ai")).strip("/")
    expected_prefix = f"{prefix}/"
    if not _BRANCH_RE.fullmatch(branch) or ".." in branch or not branch.startswith(expected_prefix):
        raise HTTPException(422, f"Branch must be a bounded {expected_prefix}* branch")


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


app = FastAPI(title="Constrained DDEV/Git Executor", version="1.0.12")


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
        "version": "1.0.12",
        "ddev": (result.stdout or result.stderr).strip(),
        "docker": (docker.stdout or docker.stderr).strip(),
        "buildx": (buildx.stdout or buildx.stderr).strip(),
        "active_jobs": active_jobs,
    }


@app.post("/v1/cancel", dependencies=[Depends(auth)])
def cancel(payload: CancelRequest) -> dict[str, Any]:
    return {"job_id": payload.job_id, "cancelled": cancel_active(payload.job_id)}


@app.post("/v1/workspaces", dependencies=[Depends(auth)])
def create_workspace(payload: WorkspaceRequest) -> dict[str, Any]:
    """Create a self-contained clone for one job without exposing source remotes."""
    cfg = project(payload.project_id)
    repo = expand(str(cfg.get("path", "")))
    if not is_git_repo(repo):
        raise HTTPException(422, f"Configured path is not a git repository: {repo}")

    ref = payload.ref or str(cfg.get("base_branch", "main"))
    source_commit = git(repo, "rev-parse", ref)

    root = Path(os.environ["CODING_WORKSPACES_ROOT"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    workspace = (root / payload.job_id).resolve()
    if not allowed_workspace(workspace) or workspace.parent != root:
        raise HTTPException(403, "Invalid workspace path")
    if workspace.exists():
        raise HTTPException(409, "Workspace already exists")

    # --no-local prevents hard-linked Git objects from being shared with the
    # source repository. The local clone creates an `origin` that points at the
    # source path; remove it before the agent sees the workspace. Source remote
    # URLs (which may contain credentials) stay confined to this privileged API.
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
        prefix = str(cfg.get("runtime", {}).get("branch_prefix", "ai"))
        branch = f"{prefix}/{payload.job_id[:12]}"
        git(workspace, "checkout", "-b", branch, source_commit)

        if (workspace / ".ddev").exists():
            safe_name = re.sub(r"[^a-z0-9-]", "-", f"cp-{payload.job_id[:10]}")
            (workspace / ".ddev" / "config.coding-platform.yaml").write_text(
                f"name: {safe_name}\n", encoding="utf-8"
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

    workspace = _validate_workspace(payload.job_id, payload.workspace)
    _validate_ai_branch(cfg, payload.branch)

    current_branch = git(workspace, "branch", "--show-current")
    if current_branch != payload.branch:
        raise HTTPException(409, "Workspace branch does not match requested publish branch")
    head = git(workspace, "rev-parse", "HEAD")
    expected = git(workspace, "rev-parse", payload.expected_commit)
    source_commit = git(workspace, "rev-parse", payload.source_commit)
    if head != expected:
        raise HTTPException(409, "Workspace HEAD does not match expected commit")
    if git(workspace, "remote", check=False).strip():
        raise HTTPException(409, "Workspace must not contain git remotes during publish")

    ancestry = subprocess.run(
        ["git", "-C", str(workspace), "merge-base", "--is-ancestor", source_commit, expected],
        text=True,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        raise HTTPException(409, "Expected commit is not descended from the job source commit")

    source_repo = expand(str(cfg.get("path", "")))
    if not is_git_repo(source_repo):
        raise HTTPException(422, "Configured source repository is unavailable")
    origin = remote_origin(source_repo)
    if not origin:
        raise HTTPException(422, "Source repository has no origin remote")

    returncode, stdout, stderr, timed_out = run_tracked(
        payload.job_id,
        [
            "git", "-C", str(workspace), "push", "--porcelain", origin,
            f"{expected}:refs/heads/{payload.branch}",
        ],
        timeout=300,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if returncode != 0:
        detail = (stderr or stdout or "git push failed")[-12000:]
        raise HTTPException(502 if not timed_out else 504, detail)

    return {
        "published": True,
        "branch": payload.branch,
        "commit": expected,
        "source_commit": source_commit,
    }


@app.delete("/v1/workspaces", dependencies=[Depends(auth)])
def remove_workspace(job_id: str, project_id: str, workspace: str = Query(...)) -> dict[str, Any]:
    project(project_id)
    path = Path(workspace).resolve()
    root = Path(os.environ["CODING_WORKSPACES_ROOT"]).resolve()
    if not allowed_workspace(path) or path.name != job_id or path.parent != root:
        raise HTTPException(403, "Workspace mismatch")
    if path.exists():
        shutil.rmtree(path)
    return {"removed": True, "workspace": str(path)}


@app.post("/v1/phase", response_model=PhaseResponse, dependencies=[Depends(auth)])
def phase(payload: PhaseRequest) -> PhaseResponse:
    cfg = project(payload.project_id)
    workspace = Path(payload.workspace).resolve()
    root = Path(os.environ["CODING_WORKSPACES_ROOT"]).resolve()
    if not allowed_workspace(workspace) or workspace.name != payload.job_id or workspace.parent != root:
        raise HTTPException(403, "Workspace is outside configured root or does not match job")
    if not workspace.exists():
        raise HTTPException(404, "Workspace does not exist")

    commands = cfg.get("ddev", {}).get(payload.phase, []) or []
    if not isinstance(commands, list) or any(not isinstance(command, str) for command in commands):
        raise HTTPException(500, f"Configured phase {payload.phase!r} must be a list of command strings")

    outputs: list[CommandOutput] = []
    passed = True
    timeout = min(
        int(os.getenv("DDEV_COMMAND_TIMEOUT_SECONDS", "1800")),
        payload.timeout_seconds or 1800,
    )
    for command in commands:
        returncode, stdout, stderr, timed_out = run_tracked(
            payload.job_id,
            ["bash", "-lc", command],
            cwd=workspace,
            timeout=timeout,
            env={**os.environ, "DDEV_NO_TUI": "true"},
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

    return PhaseResponse(passed=passed, phase=payload.phase, commands=outputs)
