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


def combined_status_signal(payload: dict[str, Any]) -> str:
    """Return a commit-status state only when at least one status exists.

    GitHub's combined-status endpoint reports `pending` when a commit has zero
    statuses. That is not a real CI signal and must not keep no-CI repositories
    waiting forever.
    """
    statuses = payload.get("statuses") or []
    if not statuses:
        return ""
    return str(payload.get("state") or "")


def action_run_signal(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one GitHub Actions workflow run into the existing CI signal shape."""
    return {
        "id": raw.get("id"),
        "run_id": raw.get("id"),
        "source": "github_actions",
        "name": raw.get("name") or raw.get("display_title") or "GitHub Actions",
        "status": str(raw.get("status") or ""),
        "conclusion": str(raw.get("conclusion")) if raw.get("conclusion") is not None else None,
        "details_url": raw.get("html_url"),
    }


def commit_status_signal(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one legacy commit status into the existing CI signal shape."""
    state = str(raw.get("state") or "")
    return {
        "id": raw.get("id"),
        "source": "commit_status",
        "name": raw.get("context") or "commit status",
        "status": "in_progress" if state == "pending" else "completed",
        "conclusion": state if state and state != "pending" else None,
        "details_url": raw.get("target_url"),
        "description": raw.get("description"),
    }


def summarize_ci(signals: list[dict[str, Any]], combined_status: str) -> tuple[str, list[dict[str, Any]]]:
    """Normalize Actions runs and commit statuses into none|pending|success|failure."""
    checks: list[dict[str, Any]] = []
    has_failure = combined_status in {"failure", "error"}
    has_pending = combined_status == "pending"
    has_signal = combined_status in {"success", "failure", "error", "pending"}

    for raw in signals:
        status = str(raw.get("status") or "")
        conclusion = raw.get("conclusion")
        conclusion_text = str(conclusion) if conclusion is not None else None
        item = dict(raw)
        checks.append(item)
        has_signal = True
        if status != "completed":
            has_pending = True
        elif conclusion_text in _FAILED_CONCLUSIONS or conclusion_text in {"failure", "error"}:
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
        """Read CI using fine-grained-PAT-compatible Actions and status APIs.

        Fine-grained PATs cannot currently be granted the Checks repository
        permission in GitHub's token UI. GitHub Actions (`Actions: read`) and
        legacy commit statuses (`Commit statuses: read`) therefore form the
        bounded delivery contract. Repositories that publish only Check Runs
        require a future GitHub App integration.
        """
        with self._client() as client:
            actions_response = client.get(
                f"{self.base}/repos/{repository}/actions/runs",
                params={"head_sha": commit, "per_page": 100},
            )
            actions_response.raise_for_status()
            workflow_runs = list(actions_response.json().get("workflow_runs") or [])

            status_response = client.get(f"{self.base}/repos/{repository}/commits/{commit}/status")
            status_response.raise_for_status()
            status_payload = status_response.json()
            raw_statuses = list(status_payload.get("statuses") or [])
            combined_status = combined_status_signal(status_payload)

            signals = [action_run_signal(raw) for raw in workflow_runs]
            signals.extend(commit_status_signal(raw) for raw in raw_statuses)
            state, checks = summarize_ci(signals, combined_status)

            failures: list[dict[str, Any]] = []
            failure_lines: list[str] = []
            if state == "failure":
                for raw in workflow_runs:
                    conclusion = str(raw.get("conclusion") or "")
                    if conclusion not in _FAILED_CONCLUSIONS:
                        continue
                    run_id = raw.get("id")
                    run_item: dict[str, Any] = {
                        "source": "github_actions",
                        "run_id": run_id,
                        "name": raw.get("name") or raw.get("display_title") or "GitHub Actions",
                        "conclusion": conclusion,
                        "details_url": raw.get("html_url"),
                        "jobs": [],
                    }
                    failure_lines.append(f"Workflow failed: {run_item['name']} ({conclusion})")
                    if run_id:
                        jobs_response = client.get(
                            f"{self.base}/repos/{repository}/actions/runs/{run_id}/jobs",
                            params={"filter": "latest", "per_page": 100},
                        )
                        if jobs_response.is_success:
                            for job in list(jobs_response.json().get("jobs") or []):
                                job_conclusion = str(job.get("conclusion") or "")
                                if job_conclusion not in _FAILED_CONCLUSIONS:
                                    continue
                                job_id = job.get("id")
                                job_item: dict[str, Any] = {
                                    "id": job_id,
                                    "name": job.get("name"),
                                    "conclusion": job_conclusion,
                                    "details_url": job.get("html_url"),
                                    "log_excerpt": "",
                                }
                                if job_id:
                                    logs_response = client.get(
                                        f"{self.base}/repos/{repository}/actions/jobs/{job_id}/logs"
                                    )
                                    if logs_response.is_success:
                                        job_item["log_excerpt"] = logs_response.text[-12000:]
                                run_item["jobs"].append(job_item)
                                failure_lines.append(
                                    f"Job failed: {job_item['name']} ({job_conclusion})"
                                )
                                if job_item["log_excerpt"]:
                                    failure_lines.append(job_item["log_excerpt"])
                    failures.append(run_item)

                for raw in raw_statuses:
                    status_state = str(raw.get("state") or "")
                    if status_state not in {"failure", "error"}:
                        continue
                    item = {
                        "source": "commit_status",
                        "id": raw.get("id"),
                        "name": raw.get("context") or "commit status",
                        "conclusion": status_state,
                        "details_url": raw.get("target_url"),
                        "description": raw.get("description"),
                    }
                    failures.append(item)
                    detail = f": {item['description']}" if item.get("description") else ""
                    failure_lines.append(
                        f"Commit status failed: {item['name']} ({status_state}){detail}"
                    )

            return {
                "state": state,
                "repository": repository,
                "commit": commit,
                "combined_status": combined_status or "none",
                "checks": checks,
                "actions_runs": [action_run_signal(raw) for raw in workflow_runs],
                "statuses": [commit_status_signal(raw) for raw in raw_statuses],
                "failures": failures,
                "failure_text": "\n".join(failure_lines)[-30000:],
            }
