from __future__ import annotations

import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from .github_delivery import GitHubDelivery, github_repository_from_origin
from .github_merge import merge_pull_request


router = APIRouter(prefix="/v1/github", tags=["pm-merge"])
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class MergePullRequestRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
    project_id: str = Field(min_length=1, max_length=200)
    pr_number: int = Field(ge=1)
    branch: str = Field(min_length=1, max_length=200)
    source_commit: str = Field(min_length=7, max_length=64)
    expected_head: str = Field(min_length=7, max_length=64)


def auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("PLATFORM_INTERNAL_TOKEN", "").strip()
    if not expected or expected in {"CHANGE_ME", "change-me"}:
        raise HTTPException(503, "PLATFORM_INTERNAL_TOKEN is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid bearer token")


def _projects() -> dict[str, Any]:
    path = os.getenv("PROJECTS_FILE", "/config/projects.yml")
    with open(path, "r", encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("projects", {})


def _project(project_id: str) -> dict[str, Any]:
    projects = _projects()
    if project_id not in projects:
        raise HTTPException(404, "Unknown project")
    return dict(projects[project_id])


def _repository(cfg: dict[str, Any]) -> tuple[GitHubDelivery, str]:
    raw_path = str(cfg.get("path", ""))
    path = Path(os.path.expanduser(os.path.expandvars(raw_path))).resolve()
    proc = subprocess.run(
        ["git", "-C", str(path), "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
    )
    origin = proc.stdout.strip()
    if proc.returncode != 0 or not origin:
        raise HTTPException(422, "Configured source repository has no origin remote")
    repository = github_repository_from_origin(origin)
    if not repository:
        raise HTTPException(422, "Source origin is not a supported github.com repository")
    delivery = GitHubDelivery()
    if not delivery.configured:
        raise HTTPException(503, "GITHUB_DELIVERY_TOKEN is not configured")
    return delivery, repository


def _validate_ai_branch(cfg: dict[str, Any], branch: str) -> None:
    prefix = str(cfg.get("runtime", {}).get("branch_prefix", "ai")).strip("/")
    expected_prefix = f"{prefix}/"
    if not _BRANCH_RE.fullmatch(branch) or ".." in branch or not branch.startswith(expected_prefix):
        raise HTTPException(422, f"Branch must be a bounded {expected_prefix}* branch")


def _github_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = exc.response.text[-12000:] if exc.response is not None else str(exc)
        return HTTPException(502, f"GitHub API request failed: {detail}")
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(502, f"GitHub API unavailable: {exc}")
    return HTTPException(409, str(exc))


@router.post("/merge-pull-request", dependencies=[Depends(auth)])
def merge_pr(payload: MergePullRequestRequest) -> dict[str, Any]:
    cfg = _project(payload.project_id)
    autonomy = dict(cfg.get("autonomy") or {})
    if not bool(autonomy.get("allow_auto_merge_low_risk", False)):
        raise HTTPException(403, "Project policy does not allow constrained PM auto-merge")
    _validate_ai_branch(cfg, payload.branch)
    base_branch = str(cfg.get("base_branch") or "main")
    delivery, repository = _repository(cfg)
    try:
        result = merge_pull_request(
            delivery,
            repository=repository,
            pr_number=payload.pr_number,
            branch=payload.branch,
            base_branch=base_branch,
            source_commit=payload.source_commit,
            expected_head=payload.expected_head,
        )
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise _github_error(exc) from exc
    return {"job_id": payload.job_id, "project_id": payload.project_id, **result}


__all__ = ["MergePullRequestRequest", "router"]
