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

    def __init__(self, responses):
        self.client = FakeClient(responses)

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
