from __future__ import annotations

import base64
import os
import re
import secrets
import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .github_delivery import GitHubDelivery
from .github_merge import merge_pull_request


router = APIRouter(prefix="/continuity", tags=["continuity"])

_MANAGED_START = "<!-- PCP:CONTINUITY:START -->"
_MANAGED_END = "<!-- PCP:CONTINUITY:END -->"
_CONTINUITY_PATH = "docs/project/current-state.md"
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ContinuityApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    continuity_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_type: Literal["pr_merged"]
    project_id: str = Field(min_length=1, max_length=200)
    managed_section: str = Field(min_length=1, max_length=20000)
    ci_wait_seconds: int = Field(default=240, ge=15, le=300)


def auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("PLATFORM_INTERNAL_TOKEN", "").strip()
    if not expected or expected in {"CHANGE_ME", "change-me"}:
        raise HTTPException(503, "PLATFORM_INTERNAL_TOKEN is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid bearer token")


def _config() -> tuple[str, str]:
    repository = os.getenv("CONTINUITY_GITHUB_REPOSITORY", "").strip()
    if not _REPOSITORY_RE.fullmatch(repository):
        raise HTTPException(503, "CONTINUITY_GITHUB_REPOSITORY is not configured")
    base_branch = os.getenv("CONTINUITY_BASE_BRANCH", "main").strip()
    if not base_branch or len(base_branch) > 200 or ".." in base_branch:
        raise HTTPException(503, "CONTINUITY_BASE_BRANCH is invalid")
    return repository, base_branch


def _validate_managed_section(value: str) -> str:
    section = value.strip("\n")
    if section.count(_MANAGED_START) != 1 or section.count(_MANAGED_END) != 1:
        raise HTTPException(422, "Managed continuity section must contain exactly one marker pair")
    if not section.startswith(_MANAGED_START) or not section.endswith(_MANAGED_END):
        raise HTTPException(422, "Managed continuity section may not contain content outside the marker pair")
    if section.index(_MANAGED_START) >= section.index(_MANAGED_END):
        raise HTTPException(422, "Managed continuity markers are out of order")
    return section


def _replace_managed(existing: str, section: str) -> str:
    if existing.count(_MANAGED_START) != 1 or existing.count(_MANAGED_END) != 1:
        raise RuntimeError("current-state.md is missing exactly one managed continuity marker pair")
    start = existing.index(_MANAGED_START)
    end = existing.index(_MANAGED_END, start) + len(_MANAGED_END)
    return existing[:start] + section + existing[end:]


def _json(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("GitHub returned an unexpected response shape")
    return value


def _ref_sha(client: httpx.Client, delivery: GitHubDelivery, repository: str, branch: str) -> str | None:
    response = client.get(f"{delivery.base}/repos/{repository}/git/ref/heads/{branch}")
    if response.status_code == 404:
        return None
    raw = _json(response)
    return str((raw.get("object") or {}).get("sha") or "") or None


def _file(client: httpx.Client, delivery: GitHubDelivery, repository: str, ref: str) -> tuple[str, str]:
    raw = _json(
        client.get(
            f"{delivery.base}/repos/{repository}/contents/{_CONTINUITY_PATH}",
            params={"ref": ref},
        )
    )
    if str(raw.get("encoding") or "") != "base64" or not raw.get("content") or not raw.get("sha"):
        raise RuntimeError("GitHub current-state.md response is missing content/blob identity")
    content = base64.b64decode(str(raw["content"]).encode("ascii")).decode("utf-8")
    return content, str(raw["sha"])


def _pulls_for_branch(
    client: httpx.Client,
    delivery: GitHubDelivery,
    repository: str,
    branch: str,
    base_branch: str,
) -> list[dict[str, Any]]:
    owner = repository.split("/", 1)[0]
    response = client.get(
        f"{delivery.base}/repos/{repository}/pulls",
        params={"state": "all", "head": f"{owner}:{branch}", "base": base_branch, "per_page": 10},
    )
    response.raise_for_status()
    value = response.json()
    return [dict(item) for item in value] if isinstance(value, list) else []


def _assert_one_file_pr(client: httpx.Client, delivery: GitHubDelivery, repository: str, number: int) -> None:
    response = client.get(
        f"{delivery.base}/repos/{repository}/pulls/{number}/files",
        params={"per_page": 100},
    )
    response.raise_for_status()
    files = response.json()
    names = [str(item.get("filename") or "") for item in files] if isinstance(files, list) else []
    if names != [_CONTINUITY_PATH]:
        raise RuntimeError("Continuity PR must change exactly docs/project/current-state.md")


def _github_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = exc.response.text[-12000:] if exc.response is not None else str(exc)
        return HTTPException(502, f"GitHub API request failed: {detail}")
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(502, f"GitHub API unavailable: {exc}")
    if isinstance(exc, HTTPException):
        return exc
    return HTTPException(409, str(exc))


@router.post("/apply", dependencies=[Depends(auth)])
def apply_continuity(payload: ContinuityApplyRequest) -> dict[str, Any]:
    """Apply one rendered pr_merged snapshot through a one-file PR and CI gate."""
    repository, base_branch = _config()
    section = _validate_managed_section(payload.managed_section)
    delivery = GitHubDelivery()
    if not delivery.configured:
        raise HTTPException(503, "GITHUB_DELIVERY_TOKEN is not configured")

    branch = f"ai/continuity/{payload.continuity_key[:12]}"
    try:
        with delivery._client() as client:
            base_sha = _ref_sha(client, delivery, repository, base_branch)
            if not base_sha:
                raise RuntimeError("Configured continuity base branch is missing")

            branch_sha = _ref_sha(client, delivery, repository, branch)
            if branch_sha is None:
                _json(
                    client.post(
                        f"{delivery.base}/repos/{repository}/git/refs",
                        json={"ref": f"refs/heads/{branch}", "sha": base_sha},
                    )
                )
                branch_sha = base_sha

            current, blob_sha = _file(client, delivery, repository, branch)
            desired = _replace_managed(current, section)
            if current != desired:
                if branch_sha != base_sha:
                    raise RuntimeError("Existing continuity branch does not match the requested rendered snapshot")
                update = _json(
                    client.put(
                        f"{delivery.base}/repos/{repository}/contents/{_CONTINUITY_PATH}",
                        json={
                            "message": f"docs: apply {payload.event_type} continuity",
                            "content": base64.b64encode(desired.encode("utf-8")).decode("ascii"),
                            "sha": blob_sha,
                            "branch": branch,
                        },
                    )
                )
                head_sha = str((update.get("commit") or {}).get("sha") or "")
                if not head_sha:
                    raise RuntimeError("GitHub continuity commit did not return a commit SHA")
            else:
                head_sha = str(_ref_sha(client, delivery, repository, branch) or "")

            pulls = _pulls_for_branch(client, delivery, repository, branch, base_branch)
            if pulls:
                raw_pr = pulls[0]
                if bool(raw_pr.get("merged")) or raw_pr.get("merged_at"):
                    return {
                        "state": "merged",
                        "repository": repository,
                        "path": _CONTINUITY_PATH,
                        "branch": branch,
                        "head": str((raw_pr.get("head") or {}).get("sha") or head_sha),
                        "pr_number": int(raw_pr["number"]),
                        "merge_commit_sha": raw_pr.get("merge_commit_sha"),
                        "merged_at": raw_pr.get("merged_at"),
                    }
                if str(raw_pr.get("state") or "") != "open":
                    raise RuntimeError("Existing continuity PR is closed without merge")
            else:
                raw_pr = _json(
                    client.post(
                        f"{delivery.base}/repos/{repository}/pulls",
                        json={
                            "title": f"docs: apply {payload.event_type} continuity",
                            "body": (
                                "Automated mutable continuity update.\n\n"
                                f"- Event project: `{payload.project_id}`\n"
                                f"- Continuity key: `{payload.continuity_key}`\n"
                                f"- Mutable target only: `{_CONTINUITY_PATH}`\n\n"
                                "No durable architecture, policy or production authority is changed."
                            ),
                            "head": branch,
                            "base": base_branch,
                            "draft": False,
                        },
                    )
                )

            pr_number = int(raw_pr["number"])
            pr_head = str((raw_pr.get("head") or {}).get("sha") or "")
            if pr_head != head_sha:
                raise RuntimeError("Continuity PR head does not match the exact rendered commit")
            _assert_one_file_pr(client, delivery, repository, pr_number)

        deadline = time.monotonic() + payload.ci_wait_seconds
        while True:
            ci = delivery.ci_status(repository=repository, commit=head_sha)
            state = str(ci.get("state") or "none")
            if state == "success":
                break
            if state == "failure":
                return {
                    "state": "ci_failure",
                    "repository": repository,
                    "path": _CONTINUITY_PATH,
                    "branch": branch,
                    "head": head_sha,
                    "pr_number": pr_number,
                    "ci": ci,
                }
            if time.monotonic() >= deadline:
                return {
                    "state": "ci_pending",
                    "repository": repository,
                    "path": _CONTINUITY_PATH,
                    "branch": branch,
                    "head": head_sha,
                    "pr_number": pr_number,
                    "ci": ci,
                }
            time.sleep(5)

        with delivery._client() as client:
            fresh_base = _ref_sha(client, delivery, repository, base_branch)
            if fresh_base != base_sha:
                return {
                    "state": "base_moved",
                    "repository": repository,
                    "path": _CONTINUITY_PATH,
                    "branch": branch,
                    "head": head_sha,
                    "pr_number": pr_number,
                    "source_commit": base_sha,
                    "current_base": fresh_base,
                }
            _assert_one_file_pr(client, delivery, repository, pr_number)

        result = merge_pull_request(
            delivery,
            repository=repository,
            pr_number=pr_number,
            branch=branch,
            base_branch=base_branch,
            source_commit=base_sha,
            expected_head=head_sha,
        )
        return {
            "state": "merged",
            "repository": repository,
            "path": _CONTINUITY_PATH,
            "pr_number": pr_number,
            **result,
        }
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError) as exc:
        raise _github_error(exc) from exc


__all__ = ["router"]
