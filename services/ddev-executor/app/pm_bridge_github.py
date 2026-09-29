from __future__ import annotations

import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .continuity_github import router as continuity_router
from .github_delivery import GitHubDelivery, github_repository_from_origin
from .github_merge import merge_pull_request
from .plan_progress_github import ProgressRequest, upsert_progress


router = APIRouter(prefix="/v1/github/pm-bridge", tags=["pm-bridge"])
router.include_router(continuity_router)
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class MergePullRequestRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=100)
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


def _load_projects() -> dict[str, Any]:
    path = os.getenv("PROJECTS_FILE", "/config/projects.yml")
    with open(path, "r", encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("projects", {})


def _project(project_id: str) -> dict[str, Any]:
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(404, "Unknown project")
    return dict(projects[project_id])


def _repository(project_id: str) -> tuple[GitHubDelivery, str]:
    cfg = _project(project_id)
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


def _github_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = exc.response.text[-12000:] if exc.response is not None else str(exc)
        return HTTPException(502, f"GitHub API request failed: {detail}")
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(502, f"GitHub API unavailable: {exc}")
    return HTTPException(409, str(exc))


def _issue_number(issue_url: str) -> int:
    match = re.search(r"/issues/(\d+)$", issue_url or "")
    if not match:
        raise ValueError("GitHub comment does not reference a bounded issue URL")
    return int(match.group(1))


@router.post("/progress", dependencies=[Depends(auth)])
def progress(payload: ProgressRequest) -> dict[str, Any]:
    delivery, repository = _repository(payload.project_id)
    try:
        return upsert_progress(delivery, repository, payload)
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError) as exc:
        # Never reflect GitHub response bodies or credentials into Runtime errors.
        raise HTTPException(502 if isinstance(exc, httpx.HTTPError) else 409,
                            f"Progress publication failed ({type(exc).__name__})") from exc


def _validate_ai_branch(cfg: dict[str, Any], branch: str) -> None:
    prefix = str(cfg.get("runtime", {}).get("branch_prefix", "ai")).strip("/")
    expected_prefix = f"{prefix}/"
    if not _BRANCH_RE.fullmatch(branch) or ".." in branch or not branch.startswith(expected_prefix):
        raise HTTPException(422, f"Branch must be a bounded {expected_prefix}* branch")


@router.get("/comments", dependencies=[Depends(auth)])
def recent_issue_comments(
    project_id: str = Query(..., min_length=1, max_length=200),
    per_page: int = Query(100, ge=1, le=100),
) -> dict[str, Any]:
    delivery, repository = _repository(project_id)
    try:
        with delivery._client() as client:
            response = client.get(
                f"{delivery.base}/repos/{repository}/issues/comments",
                params={
                    "sort": "created",
                    "direction": "desc",
                    "per_page": per_page,
                },
            )
            response.raise_for_status()
            comments = []
            for raw in list(response.json() or []):
                comments.append(
                    {
                        "id": int(raw["id"]),
                        "issue_number": _issue_number(str(raw.get("issue_url") or "")),
                        "author": str((raw.get("user") or {}).get("login") or ""),
                        "body": str(raw.get("body") or ""),
                        "html_url": raw.get("html_url"),
                        "created_at": raw.get("created_at"),
                        "updated_at": raw.get("updated_at"),
                    }
                )
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError) as exc:
        raise _github_error(exc) from exc
    return {"project_id": project_id, "repository": repository, "comments": comments}


@router.get("/issues/{issue_number}", dependencies=[Depends(auth)])
def issue(
    issue_number: int,
    project_id: str = Query(..., min_length=1, max_length=200),
) -> dict[str, Any]:
    if issue_number < 1:
        raise HTTPException(422, "issue_number must be positive")
    delivery, repository = _repository(project_id)
    try:
        with delivery._client() as client:
            response = client.get(f"{delivery.base}/repos/{repository}/issues/{issue_number}")
            response.raise_for_status()
            raw = response.json()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise _github_error(exc) from exc
    return {
        "project_id": project_id,
        "repository": repository,
        "number": int(raw["number"]),
        "title": str(raw.get("title") or ""),
        "body": str(raw.get("body") or ""),
        "state": str(raw.get("state") or ""),
        "html_url": raw.get("html_url"),
        "is_pull_request": bool(raw.get("pull_request")),
    }


@router.get("/pulls/{pr_number}", dependencies=[Depends(auth)])
def pull_request(
    pr_number: int,
    project_id: str = Query(..., min_length=1, max_length=200),
) -> dict[str, Any]:
    """Return the minimum read-only PR state needed by Runtime orchestration."""
    if pr_number < 1:
        raise HTTPException(422, "pr_number must be positive")
    delivery, repository = _repository(project_id)
    try:
        with delivery._client() as client:
            response = client.get(f"{delivery.base}/repos/{repository}/pulls/{pr_number}")
            response.raise_for_status()
            raw = response.json()
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise _github_error(exc) from exc
    return {
        "project_id": project_id,
        "repository": repository,
        "number": int(raw["number"]),
        "state": str(raw.get("state") or ""),
        "merged": bool(raw.get("merged")),
        "merged_at": raw.get("merged_at"),
        "merge_commit_sha": raw.get("merge_commit_sha"),
        "html_url": raw.get("html_url"),
        "head": (raw.get("head") or {}).get("sha"),
        "head_ref": (raw.get("head") or {}).get("ref"),
        "base_ref": (raw.get("base") or {}).get("ref"),
    }


@router.post("/pulls/{pr_number}/merge", dependencies=[Depends(auth)])
def merge_pr(
    pr_number: int,
    payload: MergePullRequestRequest,
    project_id: str = Query(..., min_length=1, max_length=200),
) -> dict[str, Any]:
    """Merge one exact low-risk PR after revalidating GitHub state.

    Runtime decides PM eligibility from durable task evidence. This boundary does
    not trust that decision for GitHub facts: repository, branch, base, ancestry,
    current CI and expected head are independently re-read here.
    """
    if pr_number < 1:
        raise HTTPException(422, "pr_number must be positive")
    cfg = _project(project_id)
    autonomy = dict(cfg.get("autonomy") or {})
    if not bool(autonomy.get("allow_auto_merge_low_risk", False)):
        raise HTTPException(403, "Project policy does not allow constrained PM auto-merge")
    _validate_ai_branch(cfg, payload.branch)
    delivery, repository = _repository(project_id)
    try:
        result = merge_pull_request(
            delivery,
            repository=repository,
            pr_number=pr_number,
            branch=payload.branch,
            base_branch=str(cfg.get("base_branch") or "main"),
            source_commit=payload.source_commit,
            expected_head=payload.expected_head,
        )
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise _github_error(exc) from exc
    return {"project_id": project_id, "job_id": payload.job_id, **result}
