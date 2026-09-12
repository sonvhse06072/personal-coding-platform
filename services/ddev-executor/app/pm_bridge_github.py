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

from .github_delivery import GitHubDelivery, github_repository_from_origin


router = APIRouter(prefix="/v1/github/pm-bridge", tags=["pm-bridge"])


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
