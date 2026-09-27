from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


_GITHUB_HTTPS_RE = re.compile(r"^https?://(?:[^/@]+@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
_GITHUB_SCP_RE = re.compile(r"^(?:[^@]+@)?github\.com:([^/]+)/([^/]+?)(?:\.git)?$")
_GITHUB_SSH_RE = re.compile(r"^ssh://(?:[^@]+@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
_FAILED_CONCLUSIONS = {"failure", "cancelled", "timed_out", "action_required", "stale", "startup_failure"}
_ENGINEERING_FAILURE = "engineering"
_INFRASTRUCTURE_FAILURE = "infrastructure"
_TRUSTED_EXACT_SHA_CONTEXT = "pcp/exact-sha-ci"
_EXACT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


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
        # GitHub delivery must use only the executor-scoped token above. The
        # executor mounts the host .gitconfig for non-secret identity/settings,
        # but host credential helpers (for example `gh auth git-credential`)
        # must never participate in this privileged publish subprocess.
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
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
        "head_sha": raw.get("head_sha"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "run_started_at": raw.get("run_started_at"),
    }


def _commit_status_creator(raw: dict[str, Any]) -> tuple[str, str]:
    creator = raw.get("creator")
    if not isinstance(creator, dict):
        return "", ""
    return str(creator.get("login") or ""), str(creator.get("type") or "")


def trusted_status_metadata_by_id(
    combined_status: dict[str, Any],
    historical_statuses: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    """Bind creator-bearing history to one combined status by exact ID only."""
    status_id = combined_status.get("id")
    if not isinstance(status_id, int) or isinstance(status_id, bool) or status_id <= 0:
        return None, "invalid_trusted_status_id"
    matches = [
        item
        for item in historical_statuses
        if isinstance(item, dict)
        and type(item.get("id")) is type(status_id)
        and item.get("id") == status_id
    ]
    if not matches:
        return None, "trusted_status_id_not_found"
    if len(matches) != 1:
        return None, "trusted_status_id_ambiguous"
    return matches[0], None


def commit_status_signal(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one legacy commit status into the existing CI signal shape."""
    state = str(raw.get("state") or "")
    creator_login, creator_type = _commit_status_creator(raw)
    return {
        "id": raw.get("id"),
        "source": "commit_status",
        "name": raw.get("context") or "commit status",
        "status": "in_progress" if state == "pending" else "completed",
        "conclusion": state if state and state != "pending" else None,
        "details_url": raw.get("target_url"),
        "description": raw.get("description"),
        "context": raw.get("context"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "creator": creator_login,
        "creator_type": creator_type,
    }


def parse_github_timestamp(value: Any) -> datetime | None:
    """Parse an ordered GitHub timestamp, rejecting missing/naive values."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _validation_run_id(target_url: Any, repository: str) -> int | None:
    """Return the run id only for an exact repository-owned Actions run URL."""
    if not isinstance(target_url, str) or not target_url.strip():
        return None
    parsed = urlparse(target_url.strip())
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "github.com"
        or parsed.username is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    match = re.fullmatch(r"/([^/]+)/([^/]+)/actions/runs/([1-9][0-9]*)/?", parsed.path)
    if not match:
        return None
    url_repository = f"{match.group(1)}/{match.group(2)}"
    if url_repository.casefold() != repository.casefold():
        return None
    return int(match.group(3))


def trusted_exact_sha_status(
    raw: dict[str, Any],
    *,
    repository: str,
    commit: str,
    status_payload_sha: Any,
    metadata_status: dict[str, Any] | None,
    metadata_error: str | None = None,
) -> dict[str, Any] | None:
    """Validate the narrow repository-owned exact-SHA commit-status contract.

    Legacy commit statuses expose less execution metadata than Actions jobs.
    Trust therefore requires every binding they do expose: the exact context,
    exact 40-character endpoint/result SHA, terminal state, creation time, an
    exact-repository GitHub Actions run URL, and creator metadata hydrated only
    from the list-status object with the exact same GitHub status ID.
    """
    if str(raw.get("context") or "") != _TRUSTED_EXACT_SHA_CONTEXT:
        return None

    state = str(raw.get("state") or "")
    target_sha = str(status_payload_sha or "")
    created_at = raw.get("created_at")
    parsed_timestamp = parse_github_timestamp(created_at)
    run_id = _validation_run_id(raw.get("target_url"), repository)
    creator_login, creator_type = _commit_status_creator(metadata_status or {})
    errors: list[str] = []
    if not _EXACT_SHA_RE.fullmatch(commit) or target_sha.lower() != commit.lower():
        errors.append("target_sha_mismatch")
    if state not in {"success", "failure", "error"}:
        errors.append("non_terminal_state")
    if parsed_timestamp is None:
        errors.append("invalid_created_at")
    if run_id is None:
        errors.append("invalid_validation_run_url")
    if metadata_error:
        errors.append(metadata_error)
    elif creator_login != "github-actions[bot]" or creator_type != "Bot":
        errors.append("untrusted_status_creator")

    return {
        "id": raw.get("id"),
        "source": "commit_status",
        "context": _TRUSTED_EXACT_SHA_CONTEXT,
        "state": state,
        "repository": repository,
        "target_sha": target_sha,
        "created_at": created_at,
        "updated_at": raw.get("updated_at"),
        "validation_run_url": raw.get("target_url"),
        "validation_run_id": run_id,
        "creator": creator_login,
        "creator_type": creator_type,
        "creator_status_id": metadata_status.get("id") if metadata_status else None,
        "creator_source": "list_commit_statuses" if metadata_status else None,
        "terminal": state in {"success", "failure", "error"},
        "valid": not errors,
        "validation_errors": errors,
        # This private value is removed from returned audit evidence.
        "_timestamp": parsed_timestamp,
    }


def latest_trusted_exact_sha_evidence(
    evidence: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, bool]:
    """Return the latest valid evidence and whether its order is ambiguous."""
    valid = [item for item in evidence if item.get("valid") and item.get("_timestamp")]
    if not valid:
        return None, False
    latest_time = max(item["_timestamp"] for item in valid)
    latest = [item for item in valid if item["_timestamp"] == latest_time]
    if len({str(item.get("state") or "") for item in latest}) != 1:
        return None, True
    return latest[0], False


def _failure_order_timestamp(failure: dict[str, Any]) -> datetime | None:
    if failure.get("source") == "github_actions":
        return parse_github_timestamp(failure.get("updated_at"))
    return parse_github_timestamp(failure.get("created_at"))


def effective_ci_state(
    signals: list[dict[str, Any]],
    combined_status: str,
    failures: list[dict[str, Any]],
    trusted_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply narrow exact-SHA precedence without discarding audit failures."""
    trusted_contract_invalid = any(not item.get("valid") for item in trusted_evidence)
    latest_trusted, ambiguous_trusted_order = (None, False)
    if not trusted_contract_invalid:
        latest_trusted, ambiguous_trusted_order = latest_trusted_exact_sha_evidence(
            trusted_evidence
        )
    trusted_success_time = None
    if latest_trusted and latest_trusted.get("state") == "success":
        trusted_success_time = latest_trusted.get("_timestamp")

    audit_failures: list[dict[str, Any]] = []
    effective_failures: list[dict[str, Any]] = []
    superseded_failures: list[dict[str, Any]] = []
    for raw in failures:
        item = dict(raw)
        superseded = False
        if (
            trusted_success_time is not None
            and item.get("failure_class") == _INFRASTRUCTURE_FAILURE
        ):
            failed_at = _failure_order_timestamp(item)
            superseded = failed_at is not None and failed_at < trusted_success_time
        item["effective"] = not superseded
        item["superseded_by_trusted_exact_sha"] = superseded
        audit_failures.append(item)
        if superseded:
            superseded_failures.append(item)
        else:
            effective_failures.append(item)

    trusted_contract_errors = sorted({
        str(error)
        for item in trusted_evidence
        if not item.get("valid")
        for error in item.get("validation_errors") or []
        if error
    })
    if trusted_contract_invalid:
        contract_failure = {
            "source": "trusted_status_authentication",
            "name": _TRUSTED_EXACT_SHA_CONTEXT,
            "conclusion": "error",
            "description": ", ".join(trusted_contract_errors),
            "failure_class": _INFRASTRUCTURE_FAILURE,
            "effective": True,
            "superseded_by_trusted_exact_sha": False,
        }
        audit_failures.append(contract_failure)
        effective_failures.append(contract_failure)

    has_pending = combined_status == "pending"
    has_signal = combined_status in {"success", "failure", "error", "pending"}
    for signal in signals:
        has_signal = True
        if str(signal.get("status") or "") != "completed":
            has_pending = True

    raw_status_failure = any(
        signal.get("source") == "commit_status"
        and str(signal.get("conclusion") or "") in {"failure", "error"}
        for signal in signals
    )
    unexplained_combined_failure = (
        combined_status in {"failure", "error"} and not raw_status_failure
    )
    if effective_failures or unexplained_combined_failure or ambiguous_trusted_order:
        state = "failure"
    elif has_pending:
        state = "pending"
    elif has_signal:
        state = "success"
    else:
        state = "none"

    failure_class = None
    if state == "failure":
        failure_class = (
            _INFRASTRUCTURE_FAILURE
            if effective_failures
            and not unexplained_combined_failure
            and not ambiguous_trusted_order
            and all(
                str(item.get("failure_class") or "") == _INFRASTRUCTURE_FAILURE
                for item in effective_failures
            )
            else _ENGINEERING_FAILURE
        )

    return {
        "state": state,
        "failure_class": failure_class,
        "failures": audit_failures,
        "effective_failures": effective_failures,
        "superseded_failures": superseded_failures,
        "infrastructure_failures_superseded": bool(superseded_failures),
        "trusted_contract_invalid": trusted_contract_invalid,
        "trusted_contract_errors": trusted_contract_errors,
        "trusted_order_ambiguous": ambiguous_trusted_order,
        "latest_trusted": latest_trusted,
    }


def _failure_text(failures: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in failures:
        conclusion = str(item.get("conclusion") or "failure")
        if item.get("source") == "github_actions":
            lines.append(f"Workflow failed: {item.get('name')} ({conclusion})")
            for job in item.get("jobs") or []:
                lines.append(
                    f"Job failed: {job.get('name')} ({job.get('conclusion') or 'failure'})"
                )
                if job.get("log_excerpt"):
                    lines.append(str(job["log_excerpt"]))
            continue
        detail = f": {item['description']}" if item.get("description") else ""
        lines.append(
            f"Commit status failed: {item.get('name')} ({conclusion}){detail}"
        )
    return "\n".join(lines)[-30000:]


def _public_trusted_evidence(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {key: value for key, value in item.items() if key != "_timestamp"}


def actions_job_failure_class(raw: dict[str, Any]) -> str:
    """Classify one failed Actions job, defaulting ambiguity to engineering.

    GitHub can report a terminal failure before assigning a runner. The strict
    runnerless/zero-step shape is positive evidence that repository execution
    never began. Missing fields or unavailable logs are not equivalent evidence
    and therefore retain the existing engineering-repair behavior.
    """
    conclusion = str(raw.get("conclusion") or "")
    if conclusion == "startup_failure":
        return _INFRASTRUCTURE_FAILURE

    steps = raw.get("steps")
    runner_id = raw.get("runner_id")
    if (runner_id == 0 or runner_id == "0") and isinstance(steps, list) and not steps:
        return _INFRASTRUCTURE_FAILURE
    return _ENGINEERING_FAILURE


def actions_run_failure_class(
    raw: dict[str, Any],
    failed_jobs: list[dict[str, Any]],
) -> str:
    """Classify one failed workflow run without guessing from absent evidence."""
    if str(raw.get("conclusion") or "") == "startup_failure":
        return _INFRASTRUCTURE_FAILURE
    if failed_jobs and all(
        str(job.get("failure_class") or "") == _INFRASTRUCTURE_FAILURE
        for job in failed_jobs
    ):
        return _INFRASTRUCTURE_FAILURE
    return _ENGINEERING_FAILURE


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

    def reconcile_merged_delivery(
        self,
        *,
        repository: str,
        branch: str,
        base_branch: str,
        source_commit: str,
        expected_commit: str,
    ) -> dict[str, Any] | None:
        """Observe an already-merged PR for a preserved accepted delivery.

        This path is read-only. It is used only by Runtime delivery recovery before
        republishing the preserved accepted commit. A merged descendant head is
        accepted only when GitHub proves both source -> accepted and accepted ->
        merged-head ancestry and CI for the merged head is successful.
        """
        owner = repository.split("/", 1)[0]
        with self._client() as client:
            lookup = client.get(
                f"{self.base}/repos/{repository}/pulls",
                params={
                    "state": "closed",
                    "head": f"{owner}:{branch}",
                    "base": base_branch,
                    "per_page": 20,
                },
            )
            lookup.raise_for_status()
            candidates = [
                dict(raw)
                for raw in list(lookup.json() or [])
                if bool(raw.get("merged")) or raw.get("merged_at")
            ]

            if not candidates:
                return None
            if len(candidates) != 1:
                raise RuntimeError(
                    "Ambiguous merged pull-request history for the preserved AI branch"
                )

            raw = candidates[0]
            head = dict(raw.get("head") or {})
            base = dict(raw.get("base") or {})
            head_repo = str(((head.get("repo") or {}).get("full_name")) or "")
            head_sha = str(head.get("sha") or "")
            if head_repo.lower() != repository.lower():
                raise RuntimeError(
                    "Merged pull request head repository does not match configured project repository"
                )
            if str(head.get("ref") or "") != branch:
                raise RuntimeError(
                    "Merged pull request head branch does not match the preserved AI branch"
                )
            if str(base.get("ref") or "") != base_branch:
                raise RuntimeError(
                    "Merged pull request base branch does not match project policy"
                )
            if not head_sha:
                raise RuntimeError("Merged pull request is missing a head SHA")

            source_compare = client.get(
                f"{self.base}/repos/{repository}/compare/{source_commit}...{expected_commit}"
            )
            source_compare.raise_for_status()
            source_relation = dict(source_compare.json() or {})
            if (
                str((source_relation.get("merge_base_commit") or {}).get("sha") or "")
                != source_commit
                or str(source_relation.get("status") or "") not in {"ahead", "identical"}
            ):
                raise RuntimeError(
                    "Preserved accepted commit is not descended from the pinned job source commit"
                )

            head_compare = client.get(
                f"{self.base}/repos/{repository}/compare/{expected_commit}...{head_sha}"
            )
            head_compare.raise_for_status()
            head_relation = dict(head_compare.json() or {})
            if (
                str((head_relation.get("merge_base_commit") or {}).get("sha") or "")
                != expected_commit
                or str(head_relation.get("status") or "") not in {"ahead", "identical"}
            ):
                raise RuntimeError(
                    "Merged pull request head does not contain the preserved accepted commit"
                )

        ci = self.ci_status(repository=repository, commit=head_sha)
        if str(ci.get("state") or "") != "success":
            raise RuntimeError(
                "Merged pull request head does not have successful GitHub CI"
            )

        return {
            "reconciled": True,
            "repository": repository,
            "number": int(raw["number"]),
            "url": raw.get("html_url"),
            "state": str(raw.get("state") or ""),
            "merged": True,
            "merged_at": raw.get("merged_at"),
            "merge_commit_sha": raw.get("merge_commit_sha"),
            "head": head_sha,
            "head_ref": str(head.get("ref") or ""),
            "base_ref": str(base.get("ref") or ""),
            "accepted_commit": expected_commit,
            "source_commit": source_commit,
            "ancestry": {
                "source_to_accepted": {
                    "status": source_relation.get("status"),
                    "merge_base": (source_relation.get("merge_base_commit") or {}).get("sha"),
                },
                "accepted_to_head": {
                    "status": head_relation.get("status"),
                    "merge_base": (head_relation.get("merge_base_commit") or {}).get("sha"),
                },
            },
            "ci": ci,
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

            status_response = client.get(
                f"{self.base}/repos/{repository}/commits/{commit}/status",
                params={"per_page": 100},
            )
            status_response.raise_for_status()
            status_payload = status_response.json()
            raw_statuses = list(status_payload.get("statuses") or [])
            combined_status = combined_status_signal(status_payload)

            trusted_combined_statuses = [
                raw
                for raw in raw_statuses
                if isinstance(raw, dict)
                and str(raw.get("context") or "") == _TRUSTED_EXACT_SHA_CONTEXT
            ]
            trusted_status_history: list[dict[str, Any]] = []
            trusted_metadata_request_error: str | None = None
            if trusted_combined_statuses:
                metadata_response = client.get(
                    f"{self.base}/repos/{repository}/commits/{commit}/statuses",
                    params={"per_page": 100},
                )
                if not metadata_response.is_success:
                    trusted_metadata_request_error = (
                        f"trusted_status_metadata_http_{metadata_response.status_code}"
                    )
                else:
                    try:
                        metadata_payload = metadata_response.json()
                    except ValueError:
                        metadata_payload = None
                    if not isinstance(metadata_payload, list):
                        trusted_metadata_request_error = (
                            "trusted_status_metadata_invalid_payload"
                        )
                    else:
                        trusted_status_history = [
                            item for item in metadata_payload if isinstance(item, dict)
                        ]

            signals = [action_run_signal(raw) for raw in workflow_runs]
            signals.extend(commit_status_signal(raw) for raw in raw_statuses)
            _, checks = summarize_ci(signals, combined_status)

            failures: list[dict[str, Any]] = []
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
                    "status": raw.get("status"),
                    "created_at": raw.get("created_at"),
                    "updated_at": raw.get("updated_at"),
                    "run_started_at": raw.get("run_started_at"),
                    "jobs": [],
                }
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
                            raw_steps = job.get("steps")
                            job_steps = list(raw_steps) if isinstance(raw_steps, list) else []
                            job_item: dict[str, Any] = {
                                "id": job_id,
                                "name": job.get("name"),
                                "status": job.get("status"),
                                "conclusion": job_conclusion,
                                "details_url": job.get("html_url"),
                                "runner_id": job.get("runner_id"),
                                "runner_name": job.get("runner_name"),
                                "started_at": job.get("started_at"),
                                "completed_at": job.get("completed_at"),
                                "steps": job_steps,
                                "repository_execution_started": (
                                    bool(job_steps) if isinstance(raw_steps, list) else None
                                ),
                                "failure_class": actions_job_failure_class(job),
                                "logs_available": False,
                                "log_excerpt": "",
                            }
                            if job_id:
                                logs_response = client.get(
                                    f"{self.base}/repos/{repository}/actions/jobs/{job_id}/logs"
                                )
                                if logs_response.is_success:
                                    job_item["logs_available"] = True
                                    job_item["log_excerpt"] = logs_response.text[-12000:]
                            run_item["jobs"].append(job_item)
                run_item["failure_class"] = actions_run_failure_class(
                    raw,
                    run_item["jobs"],
                )
                failures.append(run_item)

            for raw in raw_statuses:
                status_state = str(raw.get("state") or "")
                if status_state not in {"failure", "error"}:
                    continue
                creator_login, creator_type = _commit_status_creator(raw)
                failures.append({
                    "source": "commit_status",
                    "id": raw.get("id"),
                    "name": raw.get("context") or "commit status",
                    "context": raw.get("context"),
                    "conclusion": status_state,
                    "details_url": raw.get("target_url"),
                    "description": raw.get("description"),
                    "created_at": raw.get("created_at"),
                    "updated_at": raw.get("updated_at"),
                    "creator": creator_login,
                    "creator_type": creator_type,
                    "target_sha": status_payload.get("sha"),
                    # Commit statuses do not expose runner/step evidence.
                    # Preserve the historical engineering classification.
                    "failure_class": _ENGINEERING_FAILURE,
                })

            trusted_evidence: list[dict[str, Any]] = []
            for raw in trusted_combined_statuses:
                metadata_status = None
                metadata_error = trusted_metadata_request_error
                if metadata_error is None:
                    metadata_status, metadata_error = trusted_status_metadata_by_id(
                        raw,
                        trusted_status_history,
                    )
                evidence = trusted_exact_sha_status(
                    raw,
                    repository=repository,
                    commit=commit,
                    status_payload_sha=status_payload.get("sha"),
                    metadata_status=metadata_status,
                    metadata_error=metadata_error,
                )
                if evidence is not None:
                    trusted_evidence.append(evidence)
            effective = effective_ci_state(
                signals,
                combined_status,
                failures,
                trusted_evidence,
            )
            public_trusted = [
                _public_trusted_evidence(item) for item in trusted_evidence
            ]
            public_latest = _public_trusted_evidence(effective["latest_trusted"])

            return {
                "state": effective["state"],
                "effective_state": effective["state"],
                "failure_class": effective["failure_class"],
                "repository": repository,
                "commit": commit,
                "combined_status": combined_status or "none",
                "checks": checks,
                "actions_runs": [action_run_signal(raw) for raw in workflow_runs],
                "statuses": [commit_status_signal(raw) for raw in raw_statuses],
                "trusted_exact_sha_evidence": public_trusted,
                "latest_trusted_exact_sha_evidence": public_latest,
                "trusted_contract_invalid": effective["trusted_contract_invalid"],
                "trusted_contract_errors": effective["trusted_contract_errors"],
                "trusted_order_ambiguous": effective["trusted_order_ambiguous"],
                "failures": effective["failures"],
                "effective_failures": effective["effective_failures"],
                "superseded_failures": effective["superseded_failures"],
                "infrastructure_failures_superseded": effective[
                    "infrastructure_failures_superseded"
                ],
                "failure_text": _failure_text(effective["effective_failures"]),
                "audit_failure_text": _failure_text(effective["failures"]),
            }
