import hashlib
import json

import httpx
import pytest
from pydantic import ValidationError

from app import managed_comment_github as managed


REPO = "owner/repo"
BASE = "https://api.github.com"


def key(channel="diagnostic", project_id="demo", issue_number=77, identity="control:123"):
    return hashlib.sha256(
        f"{channel}:{project_id}:{issue_number}:{identity}".encode()
    ).hexdigest()


def payload(**changes):
    values = {
        "project_id": "demo",
        "issue_number": 77,
        "channel": "diagnostic",
        "identity": "control:123",
        "handoff_key": key(),
        "body": "## PCP remote diagnostic\nstatus: blocked",
    }
    values.update(changes)
    return managed.ManagedCommentRequest(**values)


class GitHub:
    base = BASE

    def __init__(self):
        self.comments = {}
        self.calls = []
        self.issue = {
            "number": 77,
            "url": f"{BASE}/repos/{REPO}/issues/77",
            "html_url": f"https://github.com/{REPO}/issues/77",
        }

    def comment(self, number, body=None):
        return {
            "id": number,
            "issue_url": self.issue["url"],
            "url": f"{BASE}/repos/{REPO}/issues/comments/{number}",
            "html_url": (
                f"https://github.com/{REPO}/issues/77#issuecomment-{number}"
            ),
            "body": body or payload().rendered,
        }

    def _client(self):
        return httpx.Client(transport=httpx.MockTransport(self.request))

    def request(self, request):
        path = request.url.path
        method = request.method
        self.calls.append((method, path))
        if method == "GET" and path == f"/repos/{REPO}/issues/77":
            return httpx.Response(200, json=self.issue)
        if path == f"/repos/{REPO}/issues/77/comments":
            if method == "GET":
                return httpx.Response(200, json=list(self.comments.values()))
            assert method == "POST"
            number = 100 + len(self.comments)
            self.comments[number] = self.comment(
                number,
                json.loads(request.content)["body"],
            )
            return httpx.Response(200, json=self.comments[number])
        prefix = f"/repos/{REPO}/issues/comments/"
        assert path.startswith(prefix)
        number = int(path.removeprefix(prefix))
        if number not in self.comments:
            return httpx.Response(404)
        if method == "GET":
            return httpx.Response(200, json=self.comments[number])
        assert method == "PATCH"
        self.comments[number]["body"] = json.loads(request.content)["body"]
        return httpx.Response(200, json=self.comments[number])


def test_managed_comment_create_then_update_exact_identity():
    github = GitHub()

    first = managed.upsert_managed_comment(github, REPO, payload())
    second = managed.upsert_managed_comment(
        github,
        REPO,
        payload(
            known_comment_id=first["comment_id"],
            body="## PCP remote diagnostic\nstatus: completed",
        ),
    )

    assert first["state"] == "created"
    assert second["state"] == "updated"
    assert first["comment_id"] == second["comment_id"]
    assert len(github.comments) == 1
    assert second["observed_body_sha256"] == hashlib.sha256(
        github.comments[first["comment_id"]]["body"].encode()
    ).hexdigest()


def test_managed_comment_rejects_duplicate_marker_without_mutation():
    github = GitHub()
    request = payload()
    github.comments[41] = github.comment(41, request.rendered)
    github.comments[42] = github.comment(42, request.rendered)

    with pytest.raises(ValueError, match="Multiple exact"):
        managed.upsert_managed_comment(github, REPO, request)

    writes = [method for method, _ in github.calls if method in {"POST", "PATCH"}]
    assert writes == []


@pytest.mark.parametrize(
    "changes",
    [
        {"handoff_key": "a" * 64},
        {"channel": "unknown"},
        {"issue_number": 0},
        {"issue_number": True},
        {"body": "<!-- PCP:spoof -->"},
        {"body": "PCP:spoof"},
        {"identity": ""},
    ],
)
def test_managed_comment_request_fails_closed(changes):
    with pytest.raises((ValidationError, ValueError)):
        payload(**changes)


def test_managed_comment_rejects_pr_target():
    github = GitHub()
    github.issue["pull_request"] = {}

    with pytest.raises(ValueError, match="exact configured issue"):
        managed.upsert_managed_comment(github, REPO, payload())
