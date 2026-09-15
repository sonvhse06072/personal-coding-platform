from __future__ import annotations

import json

import httpx
import pytest

from app.github_delivery import GitHubDelivery
from app.github_merge import merge_pull_request


HEAD = "b" * 40
SOURCE = "a" * 40


def pr_payload(*, merged: bool = False, head: str = HEAD) -> dict:
    return {
        "number": 7,
        "state": "closed" if merged else "open",
        "merged": merged,
        "merged_at": "2026-09-15T12:00:00Z" if merged else None,
        "merge_commit_sha": "c" * 40 if merged else None,
        "html_url": "https://github.com/acme/demo/pull/7",
        "head": {
            "sha": head,
            "ref": "ai/job-123456",
            "repo": {"full_name": "acme/demo"},
        },
        "base": {"ref": "main"},
    }


def install_transport(monkeypatch, delivery: GitHubDelivery, handler) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers, follow_redirects=True),
    )


def test_merge_revalidates_pr_ancestry_ci_expected_head_and_confirmation(monkeypatch) -> None:
    delivery = GitHubDelivery("token")
    state = {"merged": False, "merge_calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/pulls/7" and request.method == "GET":
            return httpx.Response(200, json=pr_payload(merged=state["merged"]))
        if path == f"/repos/acme/demo/compare/{SOURCE}...{HEAD}":
            return httpx.Response(
                200,
                json={
                    "status": "ahead",
                    "ahead_by": 1,
                    "behind_by": 0,
                    "merge_base_commit": {"sha": SOURCE},
                },
            )
        if path == "/repos/acme/demo/actions/runs":
            return httpx.Response(
                200,
                json={"workflow_runs": [{"id": 1, "name": "tests", "status": "completed", "conclusion": "success"}]},
            )
        if path == f"/repos/acme/demo/commits/{HEAD}/status":
            return httpx.Response(200, json={"state": "success", "total_count": 1, "statuses": [{"id": 2, "context": "ci", "state": "success"}]})
        if path == "/repos/acme/demo/pulls/7/merge" and request.method == "PUT":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["sha"] == HEAD
            assert payload["merge_method"] == "merge"
            state["merge_calls"] += 1
            state["merged"] = True
            return httpx.Response(200, json={"merged": True, "sha": "c" * 40, "message": "merged"})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    install_transport(monkeypatch, delivery, handler)
    result = merge_pull_request(
        delivery,
        repository="acme/demo",
        pr_number=7,
        branch="ai/job-123456",
        base_branch="main",
        source_commit=SOURCE,
        expected_head=HEAD,
    )

    assert state["merge_calls"] == 1
    assert result["merged"] is True
    assert result["expected_head"] == HEAD
    assert result["ci"]["state"] == "success"
    assert result["ancestry"]["merge_base"] == SOURCE
    assert result["merge_commit_sha"] == "c" * 40


def test_stale_head_is_rejected_before_merge(monkeypatch) -> None:
    delivery = GitHubDelivery("token")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/acme/demo/pulls/7":
            return httpx.Response(200, json=pr_payload(head="d" * 40))
        raise AssertionError("no other request is allowed after stale head detection")

    install_transport(monkeypatch, delivery, handler)
    with pytest.raises(RuntimeError, match="head SHA changed"):
        merge_pull_request(
            delivery,
            repository="acme/demo",
            pr_number=7,
            branch="ai/job-123456",
            base_branch="main",
            source_commit=SOURCE,
            expected_head=HEAD,
        )


def test_non_descendant_source_or_non_success_ci_fails_closed(monkeypatch) -> None:
    delivery = GitHubDelivery("token")

    def bad_ancestry(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/pulls/7":
            return httpx.Response(200, json=pr_payload())
        if path == f"/repos/acme/demo/compare/{SOURCE}...{HEAD}":
            return httpx.Response(200, json={"status": "diverged", "merge_base_commit": {"sha": "e" * 40}})
        raise AssertionError("CI must not run after ancestry failure")

    install_transport(monkeypatch, delivery, bad_ancestry)
    with pytest.raises(RuntimeError, match="not descended"):
        merge_pull_request(
            delivery,
            repository="acme/demo",
            pr_number=7,
            branch="ai/job-123456",
            base_branch="main",
            source_commit=SOURCE,
            expected_head=HEAD,
        )

    def bad_ci(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/pulls/7":
            return httpx.Response(200, json=pr_payload())
        if path == f"/repos/acme/demo/compare/{SOURCE}...{HEAD}":
            return httpx.Response(200, json={"status": "ahead", "merge_base_commit": {"sha": SOURCE}})
        if path == "/repos/acme/demo/actions/runs":
            return httpx.Response(200, json={"workflow_runs": []})
        if path == f"/repos/acme/demo/commits/{HEAD}/status":
            return httpx.Response(200, json={"state": "pending", "total_count": 0, "statuses": []})
        raise AssertionError("merge PUT must not run without successful CI")

    install_transport(monkeypatch, delivery, bad_ci)
    with pytest.raises(RuntimeError, match="CI state is not successful"):
        merge_pull_request(
            delivery,
            repository="acme/demo",
            pr_number=7,
            branch="ai/job-123456",
            base_branch="main",
            source_commit=SOURCE,
            expected_head=HEAD,
        )


def test_already_merged_pr_is_replay_rejected(monkeypatch) -> None:
    delivery = GitHubDelivery("token")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/acme/demo/pulls/7":
            return httpx.Response(200, json=pr_payload(merged=True))
        raise AssertionError("replay must stop at the first PR read")

    install_transport(monkeypatch, delivery, handler)
    with pytest.raises(RuntimeError, match="replayed merge request rejected"):
        merge_pull_request(
            delivery,
            repository="acme/demo",
            pr_number=7,
            branch="ai/job-123456",
            base_branch="main",
            source_commit=SOURCE,
            expected_head=HEAD,
        )
