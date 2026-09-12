from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx


_GITHUB_HTTPS_RE = re.compile(r"^https?://(?:[^/@]+@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
_GITHUB_SCP_RE = re.compile(r"^(?:[^@]+@)?github\.com:([^/]+)/([^/]+?)(?:\.git)?$")
_GITHUB_SSH_RE = re.compile(r"^ssh://(?:[^@]+@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
_FAILED_CONCLUSIONS = {"failure", "cancelled", "timed_out", "action_required", "stale", "startup_failure"}


def github_repository_from_origin(origin: str) -> str | None:
    """Return owner/repo for supported github.com remotes without credentials."""
    value = (origin or "").strip()
    for pattern in (_GITHUB_HTTPS_RE, _GITHUB_SCP_RE, _GITHUB_SSH_RE):
        match = pattern.fullmatch(value)
        if match:
            owner, repo = match.groups()
            return f"{owner}/{repo}"
    return None


def github_push_url(repository: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository slug")
    return f"https://github.com/{repository}.git"


def ensure_askpass_script() -> str:
    path = Path("/tmp/coding-platform-github-askpass")
    content = """#!/bin/sh
case \"${1:-}\" in
  *Username*) printf '%s\\n' 'x-access-token' ;;
  *Password*) printf '%s\\n' \"${GITHUB_DELIVERY_TOKEN:-}\" ;;
  *) exit 1 ;;
esac
"""
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o700)
    return str(path)


def github_git_env(token: str) -> dict[str, str]:
    if not token:
        raise RuntimeError("GITHUB_DELIVERY_TOKEN is not configured")
    return {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS_REQUIRE": "force",
        "GIT_ASKPASS": ensure_askpass_script(),
        "GITHUB_DELIVERY_TOKEN": token,
    }


def summarize_ci(check_runs: list[dict[str, Any]], combined_status: str) -> tuple[str, list[dict[str, Any]]]:
    """Normalize GitHub checks/statuses into none|pending|success|failure."""
    checks: list[dict[str, Any]] = []
    has_failure = combined_status in {"failure", "error"}
    has_pending = combined_status == "pending"
    has_signal = combined_status in {"success", "failure", "error", "pending"}

    for raw in check_runs:
        status = str(raw.get("status") or "")
        conclusion = raw.get("conclusion")
        conclusion_text = str(conclusion) if conclusion is not None else None
        item = {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "status": status,
            "conclusion": conclusion_text,
            "details_url": raw.get("details_url"),
        }
        checks.append(item)
        has_signal = True
        if status != "completed":
            has_pending = True
        elif conclusion_text in _FAILED_CONCLUSIONS:
            has_failure = True

    if has_failure:
        return "failure", checks
    if has_pending:
        return "pending", checks
    if has_signal:
        return "success", checks
    return "none", checks


class GitHubDelivery:
    def __init__(self, token: str | None = None) -> None:
        self.token = token if token is not None else os.getenv("GITHUB_DELIVERY_TOKEN", "")
        self.base = "https://api.github.com"

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("GITHUB_DELIVERY_TOKEN is not configured")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=30, headers=self.headers, follow_redirects=True)

    def assert_branch_commit(self, repository: str, branch: str, expected_commit: str) -> None:
        with self._client() as client:
            response = client.get(f"{self.base}/repos/{repository}/git/ref/heads/{branch}")
            response.raise_for_status()
            sha = str((response.json().get("object") or {}).get("sha") or "")
        if sha != expected_commit:
            raise RuntimeError("Published GitHub branch does not match the expected verified commit")

    def upsert_pull_request(
        self,
        *,
        repository: str,
        branch: str,
        base_branch: str,
        expected_commit: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        owner = repository.split("/", 1)[0]
        self.assert_branch_commit(repository, branch, expected_commit)
        with self._client() as client:
            lookup = client.get(
                f"{self.base}/repos/{repository}/pulls",
                params={"state": "open", "head": f"{owner}:{branch}", "base": base_branch},
            )
            lookup.raise_for_status()
            existing = lookup.json()
            if existing:
                number = int(existing[0]["number"])
                response = client.patch(
                    f"{self.base}/repos/{repository}/pulls/{number}",
                    json={"title": title, "body": body, "base": base_branch},
                )
                created = False
            else:
                response = client.post(
                    f"{self.base}/repos/{repository}/pulls",
                    json={"title": title, "body": body, "head": branch, "base": base_branch, "draft": False},
                )
                created = True
            response.raise_for_status()
            data = response.json()
        return {
            "created": created,
            "number": int(data["number"]),
            "url": data.get("html_url"),
            "state": data.get("state"),
            "head": (data.get("head") or {}).get("sha"),
            "head_ref": (data.get("head") or {}).get("ref"),
            "base_ref": (data.get("base") or {}).get("ref"),
            "repository": repository,
        }

    def ci_status(self, *, repository: str, commit: str) -> dict[str, Any]:
        with self._client() as client:
            checks_response = client.get(
                f"{self.base}/repos/{repository}/commits/{commit}/check-runs",
                params={"per_page": 100},
            )
            checks_response.raise_for_status()
            check_runs = list(checks_response.json().get("check_runs") or [])

            status_response = client.get(f"{self.base}/repos/{repository}/commits/{commit}/status")
            status_response.raise_for_status()
            combined_status = str(status_response.json().get("state") or "")

            state, checks = summarize_ci(check_runs, combined_status)
            failures: list[dict[str, Any]] = []
            failure_lines: list[str] = []
            if state == "failure":
                for raw in check_runs:
                    conclusion = str(raw.get("conclusion") or "")
                    if conclusion not in _FAILED_CONCLUSIONS:
                        continue
                    item = {
                        "id": raw.get("id"),
                        "name": raw.get("name"),
                        "conclusion": conclusion,
                        "details_url": raw.get("details_url"),
                        "annotations": [],
                    }
                    check_id = raw.get("id")
                    if check_id:
                        annotations_response = client.get(
                            f"{self.base}/repos/{repository}/check-runs/{check_id}/annotations",
                            params={"per_page": 50},
                        )
                        if annotations_response.is_success:
                            annotations = annotations_response.json()
                            for annotation in annotations[:50]:
                                normalized = {
                                    "path": annotation.get("path"),
                                    "start_line": annotation.get("start_line"),
                                    "end_line": annotation.get("end_line"),
                                    "annotation_level": annotation.get("annotation_level"),
                                    "message": annotation.get("message"),
                                    "raw_details": annotation.get("raw_details"),
                                }
                                item["annotations"].append(normalized)
                    failures.append(item)
                    failure_lines.append(f"Check failed: {item['name']} ({conclusion})")
                    for annotation in item["annotations"]:
                        location = annotation.get("path") or "unknown path"
                        if annotation.get("start_line"):
                            location += f":{annotation['start_line']}"
                        message = annotation.get("message") or annotation.get("raw_details") or ""
                        failure_lines.append(f"- {location}: {message}")

            return {
                "state": state,
                "repository": repository,
                "commit": commit,
                "combined_status": combined_status or "none",
                "checks": checks,
                "failures": failures,
                "failure_text": "\n".join(failure_lines)[-30000:],
            }
