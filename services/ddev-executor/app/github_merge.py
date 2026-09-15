from __future__ import annotations

from typing import Any

import httpx

from .github_delivery import GitHubDelivery


def _pull_request(delivery: GitHubDelivery, repository: str, pr_number: int) -> dict[str, Any]:
    with delivery._client() as client:
        response = client.get(f"{delivery.base}/repos/{repository}/pulls/{pr_number}")
        response.raise_for_status()
        raw = response.json()
    return dict(raw) if isinstance(raw, dict) else {}


def _assert_pr_state(
    raw: dict[str, Any],
    *,
    repository: str,
    branch: str,
    base_branch: str,
    expected_head: str,
) -> None:
    if bool(raw.get("merged")):
        raise RuntimeError("Pull request is already merged; replayed merge request rejected")
    if str(raw.get("state") or "") != "open":
        raise RuntimeError("Pull request is not open")
    head = raw.get("head") or {}
    base = raw.get("base") or {}
    head_repo = (head.get("repo") or {}).get("full_name")
    if str(head_repo or "").lower() != repository.lower():
        raise RuntimeError("Pull request head repository does not match configured project repository")
    if str(head.get("sha") or "") != expected_head:
        raise RuntimeError("Pull request head SHA changed; stale merge request rejected")
    if str(head.get("ref") or "") != branch:
        raise RuntimeError("Pull request head branch does not match the expected AI branch")
    if str(base.get("ref") or "") != base_branch:
        raise RuntimeError("Pull request base branch does not match project policy")


def _assert_source_ancestry(
    delivery: GitHubDelivery,
    *,
    repository: str,
    source_commit: str,
    expected_head: str,
) -> dict[str, Any]:
    with delivery._client() as client:
        response = client.get(
            f"{delivery.base}/repos/{repository}/compare/{source_commit}...{expected_head}"
        )
        response.raise_for_status()
        comparison = response.json()
    merge_base = str((comparison.get("merge_base_commit") or {}).get("sha") or "")
    status = str(comparison.get("status") or "")
    if merge_base != source_commit or status not in {"ahead", "identical"}:
        raise RuntimeError("Expected PR head is not descended from the pinned job source commit")
    return {
        "status": status,
        "ahead_by": comparison.get("ahead_by"),
        "behind_by": comparison.get("behind_by"),
        "merge_base": merge_base,
    }


def merge_pull_request(
    delivery: GitHubDelivery,
    *,
    repository: str,
    pr_number: int,
    branch: str,
    base_branch: str,
    source_commit: str,
    expected_head: str,
) -> dict[str, Any]:
    """Merge one exact verified PR and confirm GitHub's resulting state.

    Every mutable request uses the expected head SHA. CI and PR state are read
    immediately before the merge, and PR state is read once more after CI to
    close the race between CI observation and the mutation request.
    """
    raw = _pull_request(delivery, repository, pr_number)
    _assert_pr_state(
        raw,
        repository=repository,
        branch=branch,
        base_branch=base_branch,
        expected_head=expected_head,
    )
    ancestry = _assert_source_ancestry(
        delivery,
        repository=repository,
        source_commit=source_commit,
        expected_head=expected_head,
    )
    ci = delivery.ci_status(repository=repository, commit=expected_head)
    if str(ci.get("state") or "") != "success":
        raise RuntimeError(f"Current GitHub CI state is not successful: {ci.get('state') or 'none'}")

    fresh = _pull_request(delivery, repository, pr_number)
    _assert_pr_state(
        fresh,
        repository=repository,
        branch=branch,
        base_branch=base_branch,
        expected_head=expected_head,
    )

    with delivery._client() as client:
        response = client.put(
            f"{delivery.base}/repos/{repository}/pulls/{pr_number}/merge",
            json={"sha": expected_head, "merge_method": "merge"},
        )
        response.raise_for_status()
        merge_response = response.json()
    if not bool(merge_response.get("merged")):
        message = str(merge_response.get("message") or "GitHub did not merge the pull request")
        raise RuntimeError(message)

    confirmed = _pull_request(delivery, repository, pr_number)
    if not bool(confirmed.get("merged")) or not confirmed.get("merged_at"):
        raise RuntimeError("GitHub merge response was not confirmed by a fresh pull-request read")
    return {
        "merged": True,
        "repository": repository,
        "number": pr_number,
        "expected_head": expected_head,
        "branch": branch,
        "base_branch": base_branch,
        "source_commit": source_commit,
        "merge_commit_sha": confirmed.get("merge_commit_sha") or merge_response.get("sha"),
        "merged_at": confirmed.get("merged_at"),
        "html_url": confirmed.get("html_url"),
        "ci": {"state": ci.get("state"), "commit": ci.get("commit")},
        "ancestry": ancestry,
    }


__all__ = ["merge_pull_request"]
