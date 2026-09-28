from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Awaitable, Callable


class DeliveryError(RuntimeError):
    def __init__(self, reason: str, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.metadata = metadata or {}


def pull_request_body(
    *,
    job_id: str,
    branch: str,
    commit: str,
    verification: dict[str, Any],
    evaluator: str | None,
    review: dict[str, Any] | None = None,
) -> str:
    phases = [
        str(item.get("phase"))
        for item in (verification.get("phases") or [])
        if isinstance(item, dict) and item.get("phase")
    ]
    checks = ", ".join(phases) if phases else "local verification"
    evaluator_line = (
        "pass"
        if evaluator or (isinstance(review, dict) and review.get("verdict") == "pass")
        else "not required"
    )
    return (
        "Automated coding-platform delivery.\n\n"
        f"- Job: `{job_id}`\n"
        f"- Branch: `{branch}`\n"
        f"- Verified commit: `{commit}`\n"
        f"- Local checks: {checks}\n"
        f"- Independent evaluator: {evaluator_line}\n\n"
        "This PR is intentionally not auto-merged."
    )


async def deliver_verified_work(
    *,
    ddev: Any,
    job_id: str,
    project_id: str,
    workspace: str,
    branch: str,
    source_commit: str,
    commit: str,
    title: str,
    body: str,
    permissions: dict[str, Any],
    max_wait_seconds: int,
    reconcile_existing: bool = False,
    expected_pr_number: int | None = None,
    expected_previous_commit: str | None = None,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    poll_seconds: float | None = None,
    discovery_seconds: float | None = None,
) -> dict[str, Any]:
    """Publish verified work and monitor CI without ever merging it.

    `none` is allowed after a short discovery grace so repositories without CI do
    not block forever. Once GitHub reports a pending check/status, the function
    waits for a terminal success/failure until the bounded timeout expires.
    """
    metadata: dict[str, Any] = {
        "enabled": False,
        "state": "skipped",
        "branch": branch,
        "commit": commit,
    }
    if not bool(permissions.get("push_ai_branch", False)):
        return metadata

    metadata["enabled"] = True
    metadata["state"] = "publishing"
    try:
        if reconcile_existing and bool(permissions.get("create_pr", False)):
            observed = await ddev.github_reconcile_delivery(
                job_id=job_id,
                project_id=project_id,
                branch=branch,
                source_commit=source_commit,
                expected_commit=commit,
            )
            if bool(observed.get("reconciled")):
                reconciled = dict(observed.get("delivery") or {})
                metadata["state"] = "ci_success"
                metadata["reconciled_external_merge"] = True
                metadata["pull_request"] = {
                    "number": reconciled.get("number"),
                    "url": reconciled.get("url"),
                    "state": reconciled.get("state"),
                    "head": reconciled.get("head"),
                    "head_ref": reconciled.get("head_ref"),
                    "base_ref": reconciled.get("base_ref"),
                    "repository": reconciled.get("repository"),
                    "merged": reconciled.get("merged"),
                    "merged_at": reconciled.get("merged_at"),
                    "merge_commit_sha": reconciled.get("merge_commit_sha"),
                }
                metadata["ci"] = reconciled.get("ci") or {}
                metadata["external_merge"] = reconciled
                return metadata

        published = await ddev.publish_branch(
            job_id=job_id,
            project_id=project_id,
            workspace=workspace,
            branch=branch,
            source_commit=source_commit,
            expected_commit=commit,
            review_repair_pr_number=expected_pr_number,
            review_repair_previous_commit=expected_previous_commit,
        )
        metadata["publish"] = published
        metadata["state"] = "published"

        if not bool(permissions.get("create_pr", False)):
            return metadata

        pr = await ddev.upsert_pull_request(
            job_id=job_id,
            project_id=project_id,
            branch=branch,
            expected_commit=commit,
            title=title,
            body=body,
            expected_pr_number=expected_pr_number,
        )
        metadata["pull_request"] = pr
        metadata["state"] = "ci_waiting"

        poll = max(1.0, float(poll_seconds if poll_seconds is not None else os.getenv("GITHUB_CI_POLL_SECONDS", "5")))
        discovery = max(
            0.0,
            float(discovery_seconds if discovery_seconds is not None else os.getenv("GITHUB_CI_DISCOVERY_SECONDS", "20")),
        )
        timeout = max(1.0, float(max_wait_seconds))
        started = time.monotonic()
        saw_signal = False

        while True:
            ci = await ddev.github_ci(project_id=project_id, commit=commit)
            metadata["ci"] = ci
            state = str(ci.get("state") or "none")
            elapsed = time.monotonic() - started

            if state == "success":
                metadata["state"] = "ci_success"
                return metadata
            if state == "failure":
                metadata["state"] = "ci_failure"
                return metadata
            if state == "pending":
                saw_signal = True
            elif state == "none" and not saw_signal and elapsed >= discovery:
                metadata["state"] = "ci_none"
                return metadata

            if elapsed >= timeout:
                raise DeliveryError(
                    "github_ci_timeout",
                    f"GitHub CI did not reach a terminal state within {int(timeout)} seconds",
                    metadata,
                )
            await sleeper(min(poll, max(0.1, timeout - elapsed)))
    except DeliveryError:
        raise
    except Exception as exc:
        raise DeliveryError("github_delivery_failed", f"{type(exc).__name__}: {exc}", metadata) from exc
