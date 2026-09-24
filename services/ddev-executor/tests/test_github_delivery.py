import httpx

from app.github_delivery import (
    GitHubDelivery,
    action_run_signal,
    combined_status_signal,
    commit_status_signal,
    github_push_url,
    github_repository_from_origin,
    summarize_ci,
)


def test_github_repository_from_origin_strips_credentials_and_transport():
    assert github_repository_from_origin("https://user:token@github.com/acme/demo.git") == "acme/demo"
    assert github_repository_from_origin("git@github.com:acme/demo.git") == "acme/demo"
    assert github_repository_from_origin("ssh://git@github.com/acme/demo.git") == "acme/demo"
    assert github_repository_from_origin("/tmp/local.git") is None


def test_github_push_url_is_credential_free():
    assert github_push_url("acme/demo") == "https://github.com/acme/demo.git"


def test_ci_summary_prefers_failure_over_pending():
    state, checks = summarize_ci(
        [
            action_run_signal({"id": 1, "name": "lint", "status": "completed", "conclusion": "success"}),
            action_run_signal({"id": 2, "name": "tests", "status": "completed", "conclusion": "failure"}),
            action_run_signal({"id": 3, "name": "other", "status": "in_progress", "conclusion": None}),
        ],
        "pending",
    )
    assert state == "failure"
    assert len(checks) == 3


def test_ci_summary_handles_none_pending_and_success():
    assert summarize_ci([], "")[0] == "none"
    assert summarize_ci([], "pending")[0] == "pending"
    assert summarize_ci([], "success")[0] == "success"
    assert summarize_ci([
        action_run_signal({"id": 1, "name": "tests", "status": "completed", "conclusion": "success"})
    ], "")[0] == "success"


def test_empty_combined_status_payload_is_not_a_ci_signal():
    assert combined_status_signal({"state": "pending", "statuses": [], "total_count": 0}) == ""
    assert combined_status_signal({"state": "success", "statuses": [{"context": "ci"}]}) == "success"
    assert combined_status_signal({"state": "failure", "statuses": [{"context": "ci"}]}) == "failure"


def test_commit_status_signal_normalizes_pending_and_failure():
    pending = commit_status_signal({"id": 1, "context": "external", "state": "pending"})
    failed = commit_status_signal({"id": 2, "context": "external", "state": "failure"})
    assert pending["status"] == "in_progress"
    assert pending["conclusion"] is None
    assert failed["status"] == "completed"
    assert failed["conclusion"] == "failure"


def test_ci_status_uses_actions_and_statuses_without_check_runs(monkeypatch):
    requested_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/repos/acme/demo/actions/runs":
            assert request.url.params["head_sha"] == "abc1234"
            return httpx.Response(200, json={"total_count": 0, "workflow_runs": []})
        if request.url.path == "/repos/acme/demo/commits/abc1234/status":
            return httpx.Response(200, json={"state": "pending", "total_count": 0, "statuses": []})
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    transport = httpx.MockTransport(handler)
    delivery = GitHubDelivery("token")
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers, follow_redirects=True),
    )

    result = delivery.ci_status(repository="acme/demo", commit="abc1234")

    assert result["state"] == "none"
    assert result["combined_status"] == "none"
    assert result["checks"] == []
    assert result["actions_runs"] == []
    assert result["statuses"] == []
    assert not any("check-runs" in path for path in requested_paths)


def test_actions_failure_collects_failed_job_logs_for_repair(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/actions/runs":
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 11,
                            "name": "tests",
                            "status": "completed",
                            "conclusion": "failure",
                            "html_url": "https://github.com/acme/demo/actions/runs/11",
                        }
                    ]
                },
            )
        if path == "/repos/acme/demo/commits/abc1234/status":
            return httpx.Response(200, json={"state": "pending", "total_count": 0, "statuses": []})
        if path == "/repos/acme/demo/actions/runs/11/jobs":
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 22,
                            "name": "phpunit",
                            "status": "completed",
                            "conclusion": "failure",
                            "html_url": "https://github.com/acme/demo/actions/runs/11/job/22",
                            "runner_id": 101,
                            "runner_name": "GitHub Actions 101",
                            "started_at": "2026-09-24T01:00:00Z",
                            "completed_at": "2026-09-24T01:01:00Z",
                            "steps": [
                                {
                                    "name": "Run PHPUnit",
                                    "status": "completed",
                                    "conclusion": "failure",
                                }
                            ],
                        }
                    ]
                },
            )
        if path == "/repos/acme/demo/actions/jobs/22/logs":
            return httpx.Response(200, text="Assertion failed in ExampleTest")
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    transport = httpx.MockTransport(handler)
    delivery = GitHubDelivery("token")
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers, follow_redirects=True),
    )

    result = delivery.ci_status(repository="acme/demo", commit="abc1234")

    assert result["state"] == "failure"
    assert result["failure_class"] == "engineering"
    assert result["failures"][0]["source"] == "github_actions"
    job = result["failures"][0]["jobs"][0]
    assert job["name"] == "phpunit"
    assert job["runner_id"] == 101
    assert job["repository_execution_started"] is True
    assert job["failure_class"] == "engineering"
    assert job["logs_available"] is True
    assert "Assertion failed in ExampleTest" in result["failure_text"]


def test_runnerless_zero_step_failure_is_infrastructure(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/actions/runs":
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 35916265858,
                            "name": "CI",
                            "status": "completed",
                            "conclusion": "failure",
                        }
                    ]
                },
            )
        if path == "/repos/acme/demo/commits/abc1234/status":
            return httpx.Response(200, json={"state": "pending", "statuses": []})
        if path == "/repos/acme/demo/actions/runs/35916265858/jobs":
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 22,
                            "name": "quality",
                            "status": "completed",
                            "conclusion": "failure",
                            "runner_id": 0,
                            "runner_name": "",
                            "steps": [],
                            "started_at": "2026-09-23T20:36:41Z",
                            "completed_at": "2026-09-23T20:36:43Z",
                        }
                    ]
                },
            )
        if path == "/repos/acme/demo/actions/jobs/22/logs":
            return httpx.Response(404)
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    delivery = GitHubDelivery("token")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers),
    )

    result = delivery.ci_status(repository="acme/demo", commit="abc1234")

    assert result["state"] == "failure"
    assert result["failure_class"] == "infrastructure"
    job = result["failures"][0]["jobs"][0]
    assert job["runner_id"] == 0
    assert job["runner_name"] == ""
    assert job["steps"] == []
    assert job["repository_execution_started"] is False
    assert job["logs_available"] is False
    assert job["failure_class"] == "infrastructure"


def test_explicit_startup_failure_is_infrastructure(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/actions/runs":
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 11,
                            "name": "CI",
                            "status": "completed",
                            "conclusion": "startup_failure",
                        }
                    ]
                },
            )
        if path == "/repos/acme/demo/commits/abc1234/status":
            return httpx.Response(200, json={"state": "pending", "statuses": []})
        if path == "/repos/acme/demo/actions/runs/11/jobs":
            return httpx.Response(200, json={"jobs": []})
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    delivery = GitHubDelivery("token")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers),
    )

    result = delivery.ci_status(repository="acme/demo", commit="abc1234")

    assert result["state"] == "failure"
    assert result["failure_class"] == "infrastructure"
    assert result["failures"][0]["failure_class"] == "infrastructure"


def test_ambiguous_actions_failure_remains_engineering(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/actions/runs":
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 11,
                            "name": "CI",
                            "status": "completed",
                            "conclusion": "failure",
                        }
                    ]
                },
            )
        if path == "/repos/acme/demo/commits/abc1234/status":
            return httpx.Response(200, json={"state": "pending", "statuses": []})
        if path == "/repos/acme/demo/actions/runs/11/jobs":
            return httpx.Response(503)
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    delivery = GitHubDelivery("token")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers),
    )

    result = delivery.ci_status(repository="acme/demo", commit="abc1234")

    assert result["state"] == "failure"
    assert result["failure_class"] == "engineering"
    assert result["failures"][0]["jobs"] == []


def test_commit_status_failure_is_self_repair_context(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/actions/runs":
            return httpx.Response(200, json={"workflow_runs": []})
        if path == "/repos/acme/demo/commits/abc1234/status":
            return httpx.Response(
                200,
                json={
                    "state": "failure",
                    "total_count": 1,
                    "statuses": [
                        {
                            "id": 33,
                            "context": "external-ci",
                            "state": "failure",
                            "description": "lint failed",
                            "target_url": "https://ci.example.test/build/1",
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    transport = httpx.MockTransport(handler)
    delivery = GitHubDelivery("token")
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers, follow_redirects=True),
    )

    result = delivery.ci_status(repository="acme/demo", commit="abc1234")

    assert result["state"] == "failure"
    assert result["failure_class"] == "engineering"
    assert result["failures"][0]["source"] == "commit_status"
    assert "external-ci" in result["failure_text"]
    assert "lint failed" in result["failure_text"]
