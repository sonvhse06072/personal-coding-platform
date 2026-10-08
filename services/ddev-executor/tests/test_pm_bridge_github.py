import pytest
from fastapi import HTTPException

from app import pm_bridge_github


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params=None):
        self.calls.append((url, params))
        return FakeResponse(self.responses.pop(0))


class FakeDelivery:
    base = "https://api.github.test"

    def __init__(self, responses=None):
        self.client = FakeClient(responses or [])

    def _client(self):
        return self.client


def test_recent_comments_are_bounded_and_normalized(monkeypatch):
    delivery = FakeDelivery([
        [
            {
                "id": 123,
                "issue_url": "https://api.github.com/repos/example/repo/issues/4",
                "user": {"login": "owner"},
                "body": "<!-- coding-platform:pm-plan:v1 -->\n{}",
                "html_url": "https://github.com/example/repo/issues/4#issuecomment-123",
                "created_at": "2026-09-13T00:00:00Z",
                "updated_at": "2026-09-13T00:00:00Z",
            }
        ]
    ])
    monkeypatch.setattr(pm_bridge_github, "_repository", lambda project_id: (delivery, "example/repo"))

    result = pm_bridge_github.recent_issue_comments("demo", 25)

    assert result["repository"] == "example/repo"
    assert result["comments"] == [
        {
            "id": 123,
            "issue_number": 4,
            "author": "owner",
            "body": "<!-- coding-platform:pm-plan:v1 -->\n{}",
            "html_url": "https://github.com/example/repo/issues/4#issuecomment-123",
            "created_at": "2026-09-13T00:00:00Z",
            "updated_at": "2026-09-13T00:00:00Z",
        }
    ]
    assert delivery.client.calls[0][1]["per_page"] == 25


def test_issue_metadata_marks_pull_requests(monkeypatch):
    delivery = FakeDelivery([
        {
            "number": 9,
            "title": "Canonical title",
            "body": "Canonical body",
            "state": "open",
            "html_url": "https://github.com/example/repo/pull/9",
            "pull_request": {"url": "https://api.github.com/example"},
        }
    ])
    monkeypatch.setattr(pm_bridge_github, "_repository", lambda project_id: (delivery, "example/repo"))

    result = pm_bridge_github.issue(9, "demo")

    assert result["number"] == 9
    assert result["title"] == "Canonical title"
    assert result["body"] == "Canonical body"
    assert result["is_pull_request"] is True


def test_pull_request_status_exposes_only_merge_gate_metadata(monkeypatch):
    delivery = FakeDelivery([
        {
            "number": 12,
            "state": "closed",
            "merged": True,
            "merged_at": "2026-09-13T03:00:00Z",
            "merge_commit_sha": "abc123",
            "html_url": "https://github.com/example/repo/pull/12",
            "head": {"sha": "head123", "ref": "ai/job"},
            "base": {"ref": "main"},
            "body": "must not leak through bounded response",
        }
    ])
    monkeypatch.setattr(pm_bridge_github, "_repository", lambda project_id: (delivery, "example/repo"))

    result = pm_bridge_github.pull_request(12, "demo")

    assert result == {
        "project_id": "demo",
        "repository": "example/repo",
        "number": 12,
        "state": "closed",
        "merged": True,
        "merged_at": "2026-09-13T03:00:00Z",
        "merge_commit_sha": "abc123",
        "html_url": "https://github.com/example/repo/pull/12",
        "head": "head123",
        "head_ref": "ai/job",
        "base_ref": "main",
    }
    assert delivery.client.calls == [("https://api.github.test/repos/example/repo/pulls/12", None)]


def test_exact_pr_review_is_fetched_and_bounded(monkeypatch):
    body = '<!-- coding-platform:pm-chat-review:v1 -->\\n{"verdict":"pass"}'
    delivery = FakeDelivery([{
        "id": 45, "state": "COMMENTED", "commit_id": "a" * 40,
        "user": {"login": "owner"}, "body": body,
        "html_url": "https://github.com/example/repo/pull/12#pullrequestreview-45",
        "submitted_at": "2026-10-08T10:00:00Z",
    }])
    monkeypatch.setattr(pm_bridge_github, "_repository", lambda project_id: (delivery, "example/repo"))
    result = pm_bridge_github.pull_request_review(12, 45, "demo")
    assert result["author"] == "owner"
    assert result["commit_id"] == "a" * 40
    assert result["pr_number"] == 12
    assert result["body"] == body
    assert delivery.client.calls == [
        ("https://api.github.test/repos/example/repo/pulls/12/reviews/45", None),
    ]


def test_exact_pr_review_rejects_mismatched_id_and_oversized_body(monkeypatch):
    delivery = FakeDelivery([{"id": 46, "body": "ok"}])
    monkeypatch.setattr(pm_bridge_github, "_repository", lambda project_id: (delivery, "example/repo"))
    with pytest.raises(HTTPException):
        pm_bridge_github.pull_request_review(12, 45, "demo")
    delivery = FakeDelivery([{"id": 45, "body": "x" * 16385}])
    monkeypatch.setattr(pm_bridge_github, "_repository", lambda project_id: (delivery, "example/repo"))
    with pytest.raises(HTTPException):
        pm_bridge_github.pull_request_review(12, 45, "demo")


def test_merge_bridge_preserves_project_opt_out(monkeypatch):
    monkeypatch.setattr(
        pm_bridge_github,
        "_project",
        lambda project_id: {
            "base_branch": "main",
            "runtime": {"branch_prefix": "ai"},
            "autonomy": {"allow_auto_merge_low_risk": False},
        },
    )
    payload = pm_bridge_github.MergePullRequestRequest(
        job_id="job-12345678",
        branch="ai/job-123456",
        source_commit="a" * 40,
        expected_head="b" * 40,
    )

    with pytest.raises(HTTPException) as exc:
        pm_bridge_github.merge_pr(7, payload, "demo")
    assert exc.value.status_code == 403


def test_merge_bridge_passes_only_bounded_project_derived_context(monkeypatch):
    delivery = FakeDelivery()
    captured = {}
    monkeypatch.setattr(
        pm_bridge_github,
        "_project",
        lambda project_id: {
            "base_branch": "develop",
            "runtime": {"branch_prefix": "ai"},
            "autonomy": {"allow_auto_merge_low_risk": True},
        },
    )
    monkeypatch.setattr(pm_bridge_github, "_repository", lambda project_id: (delivery, "example/repo"))

    def fake_merge(delivery_arg, **kwargs):
        assert delivery_arg is delivery
        captured.update(kwargs)
        return {"merged": True, "merge_commit_sha": "c" * 40}

    monkeypatch.setattr(pm_bridge_github, "merge_pull_request", fake_merge)
    payload = pm_bridge_github.MergePullRequestRequest(
        job_id="job-12345678",
        branch="ai/job-123456",
        source_commit="a" * 40,
        expected_head="b" * 40,
    )

    result = pm_bridge_github.merge_pr(7, payload, "demo")

    assert captured == {
        "repository": "example/repo",
        "pr_number": 7,
        "branch": "ai/job-123456",
        "base_branch": "develop",
        "source_commit": "a" * 40,
        "expected_head": "b" * 40,
    }
    assert result["project_id"] == "demo"
    assert result["job_id"] == "job-12345678"
    assert result["merged"] is True
