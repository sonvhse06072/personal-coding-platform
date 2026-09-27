import re

import httpx
import pytest

from app.github_delivery import (
    GitHubDelivery,
    action_run_signal,
    combined_status_signal,
    commit_status_signal,
    github_push_url,
    github_repository_from_origin,
    summarize_ci,
)


EXACT_SHA = "b" * 40
TRUSTED_CONTEXT = "pcp/exact-sha-ci"


def ci_status_result(
    monkeypatch,
    *,
    runs=None,
    statuses=None,
    status_history=None,
    status_history_status=200,
    payload_sha=EXACT_SHA,
    commit=EXACT_SHA,
):
    raw_runs = list(runs or [])
    workflow_runs = [
        {key: value for key, value in run.items() if key != "test_jobs"}
        for run in raw_runs
    ]
    source_statuses = list(statuses or [])
    commit_statuses = [
        {key: value for key, value in status.items() if key != "creator"}
        for status in source_statuses
    ]
    historical_statuses = list(
        source_statuses if status_history is None else status_history
    )
    jobs_by_run = {
        int(run["id"]): list(run.get("test_jobs", []))
        for run in raw_runs
        if run.get("id") is not None
    }
    status_history_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal status_history_requests
        path = request.url.path
        if path == "/repos/acme/demo/actions/runs":
            return httpx.Response(200, json={"workflow_runs": workflow_runs})
        if path == f"/repos/acme/demo/commits/{commit}/status":
            states = {str(item.get("state") or "") for item in commit_statuses}
            if "failure" in states or "error" in states:
                combined = "failure"
            elif "pending" in states:
                combined = "pending"
            elif "success" in states:
                combined = "success"
            else:
                combined = "pending"
            return httpx.Response(
                200,
                json={
                    "sha": payload_sha,
                    "state": combined,
                    "total_count": len(commit_statuses),
                    "statuses": commit_statuses,
                },
            )
        if path == f"/repos/acme/demo/commits/{commit}/statuses":
            status_history_requests += 1
            assert request.url.params["per_page"] == "100"
            return httpx.Response(status_history_status, json=historical_statuses)
        jobs_match = re.fullmatch(
            r"/repos/acme/demo/actions/runs/([0-9]+)/jobs", path
        )
        if jobs_match:
            return httpx.Response(
                200,
                json={"jobs": jobs_by_run.get(int(jobs_match.group(1)), [])},
            )
        if "/actions/jobs/" in path and path.endswith("/logs"):
            return httpx.Response(404)
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    delivery = GitHubDelivery("token")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers),
    )
    result = delivery.ci_status(repository="acme/demo", commit=commit)
    expected_history_requests = int(any(
        status.get("context") == TRUSTED_CONTEXT for status in source_statuses
    ))
    assert status_history_requests == expected_history_requests
    return result


def failed_run(run_id, *, updated_at, infrastructure=True):
    steps = [] if infrastructure else [
        {"name": "Run tests", "status": "completed", "conclusion": "failure"}
    ]
    return {
        "id": run_id,
        "name": "CI",
        "status": "completed",
        "conclusion": "failure",
        "created_at": updated_at,
        "updated_at": updated_at,
        "html_url": f"https://github.com/acme/demo/actions/runs/{run_id}",
        "test_jobs": [{
            "id": run_id * 10,
            "name": "quality",
            "status": "completed",
            "conclusion": "failure",
            "runner_id": 0 if infrastructure else 101,
            "runner_name": "" if infrastructure else "self-hosted",
            "steps": steps,
            "completed_at": updated_at,
        }],
    }


def trusted_status(status_id, *, state="success", created_at="2026-09-24T03:00:00Z"):
    return {
        "id": status_id,
        "context": TRUSTED_CONTEXT,
        "state": state,
        "description": "Exact SHA repository CI validation",
        "target_url": f"https://github.com/acme/demo/actions/runs/{status_id}",
        "created_at": created_at,
        "updated_at": created_at,
        "creator": {"login": "github-actions[bot]", "type": "Bot"},
    }


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


def test_newer_trusted_exact_sha_success_supersedes_only_historical_infrastructure(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        runs=[failed_run(101, updated_at="2026-09-24T01:00:00Z")],
        statuses=[trusted_status(201)],
    )

    assert result["state"] == "success"
    assert result["effective_state"] == "success"
    assert result["failure_class"] is None
    assert result["infrastructure_failures_superseded"] is True
    assert result["effective_failures"] == []
    assert len(result["failures"]) == 1
    assert result["failures"][0]["effective"] is False
    assert result["failures"][0]["superseded_by_trusted_exact_sha"] is True
    assert result["checks"][0]["conclusion"] == "failure"
    assert result["audit_failure_text"].startswith("Workflow failed: CI")
    assert result["failure_text"] == ""
    trusted = result["latest_trusted_exact_sha_evidence"]
    assert trusted["context"] == TRUSTED_CONTEXT
    assert trusted["target_sha"] == EXACT_SHA
    assert trusted["validation_run_id"] == 201
    assert trusted["creator"] == "github-actions[bot]"
    assert trusted["creator_type"] == "Bot"
    assert trusted["creator_status_id"] == 201
    assert trusted["creator_source"] == "list_commit_statuses"
    assert trusted["valid"] is True
    assert result["statuses"][0]["creator"] == ""


def test_trusted_status_id_missing_from_history_fails_closed(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        statuses=[trusted_status(212)],
        status_history=[],
    )

    assert result["state"] == "failure"
    assert result["failure_class"] == "infrastructure"
    evidence = result["trusted_exact_sha_evidence"][0]
    assert evidence["valid"] is False
    assert evidence["validation_errors"] == ["trusted_status_id_not_found"]


def test_matching_trusted_context_with_different_status_id_fails_closed(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        statuses=[trusted_status(213)],
        status_history=[trusted_status(214)],
    )

    assert result["state"] == "failure"
    evidence = result["trusted_exact_sha_evidence"][0]
    assert evidence["valid"] is False
    assert evidence["validation_errors"] == ["trusted_status_id_not_found"]


def test_generic_or_wrong_context_success_does_not_override_infrastructure_failure(monkeypatch):
    for context in ("ci/success", "pcp/exact-sha-ci-other"):
        generic = trusted_status(202)
        generic["context"] = context
        result = ci_status_result(
            monkeypatch,
            runs=[failed_run(102, updated_at="2026-09-24T01:00:00Z")],
            statuses=[generic],
        )

        assert result["state"] == "failure"
        assert result["failure_class"] == "infrastructure"
        assert result["trusted_exact_sha_evidence"] == []
        assert result["superseded_failures"] == []


def test_trusted_context_bound_to_wrong_sha_does_not_override(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        runs=[failed_run(103, updated_at="2026-09-24T01:00:00Z")],
        statuses=[trusted_status(203)],
        payload_sha="c" * 40,
    )

    assert result["state"] == "failure"
    assert result["failure_class"] == "infrastructure"
    assert result["trusted_exact_sha_evidence"][0]["valid"] is False
    assert result["trusted_exact_sha_evidence"][0]["validation_errors"] == [
        "target_sha_mismatch"
    ]


def test_trusted_context_bound_to_wrong_repository_run_url_does_not_override(monkeypatch):
    trusted = trusted_status(210)
    trusted["target_url"] = "https://github.com/other/demo/actions/runs/210"
    result = ci_status_result(
        monkeypatch,
        runs=[failed_run(110, updated_at="2026-09-24T01:00:00Z")],
        statuses=[trusted],
    )

    assert result["state"] == "failure"
    assert result["failure_class"] == "infrastructure"
    evidence = result["trusted_exact_sha_evidence"][0]
    assert evidence["valid"] is False
    assert evidence["validation_errors"] == ["invalid_validation_run_url"]


def test_trusted_context_from_non_workflow_creator_does_not_override(monkeypatch):
    trusted = trusted_status(211)
    trusted["creator"] = {"login": "octocat", "type": "User"}
    result = ci_status_result(
        monkeypatch,
        runs=[failed_run(111, updated_at="2026-09-24T01:00:00Z")],
        statuses=[trusted],
    )

    assert result["state"] == "failure"
    evidence = result["trusted_exact_sha_evidence"][0]
    assert evidence["valid"] is False
    assert evidence["validation_errors"] == ["untrusted_status_creator"]


def test_trusted_context_with_missing_creator_does_not_override(monkeypatch):
    trusted = trusted_status(215)
    history = dict(trusted)
    history.pop("creator")
    result = ci_status_result(
        monkeypatch,
        runs=[failed_run(115, updated_at="2026-09-24T01:00:00Z")],
        statuses=[trusted],
        status_history=[history],
    )

    assert result["state"] == "failure"
    evidence = result["trusted_exact_sha_evidence"][0]
    assert evidence["valid"] is False
    assert evidence["validation_errors"] == ["untrusted_status_creator"]


def test_different_bot_status_cannot_lend_creator_identity(monkeypatch):
    trusted = trusted_status(216)
    other = trusted_status(217)
    other["context"] = "ci/other"
    result = ci_status_result(
        monkeypatch,
        statuses=[trusted],
        status_history=[other],
    )

    assert result["state"] == "failure"
    evidence = result["trusted_exact_sha_evidence"][0]
    assert evidence["creator"] == ""
    assert evidence["valid"] is False
    assert evidence["validation_errors"] == ["trusted_status_id_not_found"]


def test_trusted_status_history_api_failure_fails_closed(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        statuses=[trusted_status(218)],
        status_history_status=503,
    )

    assert result["combined_status"] == "success"
    assert result["state"] == "failure"
    assert result["failure_class"] == "infrastructure"
    assert result["trusted_contract_errors"] == [
        "trusted_status_metadata_http_503"
    ]
    evidence = result["trusted_exact_sha_evidence"][0]
    assert evidence["valid"] is False
    assert evidence["validation_errors"] == [
        "trusted_status_metadata_http_503"
    ]


def test_trusted_success_older_than_infrastructure_failure_does_not_override(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        runs=[failed_run(104, updated_at="2026-09-24T04:00:00Z")],
        statuses=[trusted_status(204, created_at="2026-09-24T03:00:00Z")],
    )

    assert result["state"] == "failure"
    assert result["failure_class"] == "infrastructure"
    assert result["failures"][0]["effective"] is True


def test_trusted_success_with_missing_or_invalid_timestamp_fails_closed(monkeypatch):
    for timestamp in (None, "not-a-timestamp"):
        trusted = trusted_status(205)
        trusted["created_at"] = timestamp
        result = ci_status_result(
            monkeypatch,
            runs=[failed_run(105, updated_at="2026-09-24T01:00:00Z")],
            statuses=[trusted],
        )

        assert result["state"] == "failure"
        assert result["failure_class"] == "infrastructure"
        assert result["trusted_exact_sha_evidence"][0]["valid"] is False
        assert "invalid_created_at" in result["trusted_exact_sha_evidence"][0][
            "validation_errors"
        ]


def test_newer_engineering_failure_cannot_be_masked_by_trusted_success(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        runs=[
            failed_run(106, updated_at="2026-09-24T01:00:00Z"),
            failed_run(
                107,
                updated_at="2026-09-24T04:00:00Z",
                infrastructure=False,
            ),
        ],
        statuses=[trusted_status(206, created_at="2026-09-24T03:00:00Z")],
    )

    assert result["state"] == "failure"
    assert result["failure_class"] == "engineering"
    assert len(result["superseded_failures"]) == 1
    assert len(result["effective_failures"]) == 1
    assert result["effective_failures"][0]["failure_class"] == "engineering"


def test_ambiguously_ordered_engineering_failure_remains_fail_closed(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        runs=[
            failed_run(108, updated_at=None, infrastructure=False),
        ],
        statuses=[trusted_status(207)],
    )

    assert result["state"] == "failure"
    assert result["failure_class"] == "engineering"
    assert result["effective_failures"][0]["failure_class"] == "engineering"


def test_newer_trusted_exact_sha_failure_wins_over_prior_success(monkeypatch):
    prior_success = trusted_status(208, created_at="2026-09-24T02:00:00Z")
    latest_failure = trusted_status(
        209,
        state="failure",
        created_at="2026-09-24T03:00:00Z",
    )
    result = ci_status_result(
        monkeypatch,
        statuses=[latest_failure],
        status_history=[latest_failure, prior_success],
    )

    assert result["state"] == "failure"
    assert result["failure_class"] == "engineering"
    assert result["latest_trusted_exact_sha_evidence"]["state"] == "failure"
    assert result["effective_failures"][0]["context"] == TRUSTED_CONTEXT
    assert len(result["statuses"]) == 1
    assert len(result["trusted_exact_sha_evidence"]) == 1


def test_historical_trusted_statuses_do_not_become_ordinary_ci_signals(monkeypatch):
    latest_success = trusted_status(219, created_at="2026-09-24T03:00:00Z")
    historical_failure = trusted_status(
        220,
        state="failure",
        created_at="2026-09-24T02:00:00Z",
    )
    result = ci_status_result(
        monkeypatch,
        statuses=[latest_success],
        status_history=[latest_success, historical_failure],
    )

    assert result["combined_status"] == "success"
    assert result["state"] == "success"
    assert result["failure_class"] is None
    assert result["failures"] == []
    assert len(result["statuses"]) == 1
    assert result["statuses"][0]["id"] == 219
    assert len(result["checks"]) == 1
    assert len(result["trusted_exact_sha_evidence"]) == 1
    assert result["latest_trusted_exact_sha_evidence"]["id"] == 219


def test_ordinary_current_workflow_success_remains_success(monkeypatch):
    result = ci_status_result(
        monkeypatch,
        runs=[{
            "id": 212,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "head_sha": EXACT_SHA,
            "created_at": "2026-09-24T02:00:00Z",
            "updated_at": "2026-09-24T02:05:00Z",
        }],
    )

    assert result["state"] == "success"
    assert result["effective_state"] == "success"
    assert result["failure_class"] is None
    assert result["failures"] == []
    assert result["trusted_exact_sha_evidence"] == []


def test_live_shaped_historical_runnerless_failures_are_audited_after_trusted_success(monkeypatch):
    accepted_sha = "0a9f0f09660d8d61cd99fa1e341c2c4debc6a25e"
    runs = [
        failed_run(35920237209, updated_at="2026-09-23T20:36:43Z"),
        failed_run(35923484857, updated_at="2026-09-23T21:10:12Z"),
        failed_run(35964005524, updated_at="2026-09-24T01:15:02Z"),
    ]
    statuses = [trusted_status(35970000001, created_at="2026-09-24T03:00:00Z")]
    result = ci_status_result(
        monkeypatch,
        runs=runs,
        statuses=statuses,
        payload_sha=accepted_sha,
        commit=accepted_sha,
    )

    assert result["commit"] == accepted_sha
    assert result["state"] == "success"
    assert len(result["failures"]) == 3
    assert len(result["superseded_failures"]) == 3
    assert result["effective_failures"] == []
    for failure in result["failures"]:
        job = failure["jobs"][0]
        assert failure["failure_class"] == "infrastructure"
        assert job["runner_id"] == 0
        assert job["runner_name"] == ""
        assert job["steps"] == []


def _merged_delivery_fixture(
    monkeypatch,
    *,
    head,
    pulls=None,
    ci_state="success",
    source_ok=True,
    head_ok=True,
    source_status=200,
):
    expected = "b" * 40
    source = "a" * 40
    raw_pulls = pulls if pulls is not None else [{
        "number": 27,
        "state": "closed",
        "merged": True,
        "merged_at": "2026-09-27T17:03:22Z",
        "merge_commit_sha": "e" * 40,
        "html_url": "https://github.com/acme/demo/pull/27",
        "body": "Automated coding-platform delivery.\n\n- Job: `job12345`",
        "head": {"sha": head, "ref": "ai/job12345", "repo": {"full_name": "acme/demo"}},
        "base": {"ref": "main"},
    }]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/demo/pulls":
            assert request.url.params["state"] == "closed"
            assert request.url.params["head"] == "acme:ai/job12345"
            assert request.url.params["base"] == "main"
            return httpx.Response(200, json=raw_pulls)
        if path == f"/repos/acme/demo/compare/{source}...{expected}":
            if source_status != 200:
                return httpx.Response(source_status, json={"message": "Not Found"})
            return httpx.Response(200, json={
                "status": "ahead" if source_ok else "diverged",
                "merge_base_commit": {"sha": source if source_ok else "f" * 40},
            })
        if path.startswith(f"/repos/acme/demo/compare/{expected}..."):
            compared_head = path.rsplit("...", 1)[1]
            relation_ok = (
                head_ok.get(compared_head, True)
                if isinstance(head_ok, dict)
                else head_ok
            )
            return httpx.Response(200, json={
                "status": (
                    "identical"
                    if compared_head == expected and relation_ok
                    else ("ahead" if relation_ok else "diverged")
                ),
                "merge_base_commit": {
                    "sha": expected if relation_ok else "f" * 40
                },
            })
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    delivery = GitHubDelivery("token")
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        delivery,
        "_client",
        lambda: httpx.Client(transport=transport, headers=delivery.headers),
    )
    monkeypatch.setattr(
        delivery,
        "ci_status",
        lambda **kwargs: {"state": ci_state, "commit": kwargs["commit"]},
    )
    return delivery, source, expected


def test_reconcile_merged_delivery_accepts_exact_verified_head(monkeypatch):
    expected = "b" * 40
    delivery, source, expected = _merged_delivery_fixture(
        monkeypatch,
        head=expected,
    )

    result = delivery.reconcile_merged_delivery(
        repository="acme/demo",
        job_id="job12345",
        branch="ai/job12345",
        base_branch="main",
        source_commit=source,
        expected_commit=expected,
    )

    assert result is not None
    assert result["number"] == 27
    assert result["head"] == expected
    assert result["accepted_commit"] == expected
    assert result["ci"]["state"] == "success"


def test_reconcile_merged_delivery_accepts_green_descendant_head(monkeypatch):
    head = "d" * 40
    delivery, source, expected = _merged_delivery_fixture(
        monkeypatch,
        head=head,
    )

    result = delivery.reconcile_merged_delivery(
        repository="acme/demo",
        job_id="job12345",
        branch="ai/job12345",
        base_branch="main",
        source_commit=source,
        expected_commit=expected,
    )

    assert result is not None
    assert result["head"] == head
    assert result["ancestry"]["accepted_to_head"]["merge_base"] == expected


def test_reconcile_merged_delivery_selects_unique_qualifying_candidate_from_history(monkeypatch):
    old_head = "c" * 40
    current_head = "d" * 40

    def merged_pull(number, head, merged_at):
        return {
            "number": number,
            "state": "closed",
            "merged": True,
            "merged_at": merged_at,
            "merge_commit_sha": "e" * 40,
            "html_url": f"https://github.com/acme/demo/pull/{number}",
            "body": "Automated coding-platform delivery.\n\n- Job: `job12345`",
            "head": {
                "sha": head,
                "ref": "ai/job12345",
                "repo": {"full_name": "acme/demo"},
            },
            "base": {"ref": "main"},
        }

    delivery, source, expected = _merged_delivery_fixture(
        monkeypatch,
        head=current_head,
        pulls=[
            merged_pull(27, old_head, "2026-09-27T17:03:22Z"),
            merged_pull(28, current_head, "2026-09-27T18:00:00Z"),
        ],
        head_ok={old_head: False, current_head: True},
    )

    result = delivery.reconcile_merged_delivery(
        repository="acme/demo",
        job_id="job12345",
        branch="ai/job12345",
        base_branch="main",
        source_commit=source,
        expected_commit=expected,
    )

    assert result is not None
    assert result["number"] == 28
    assert result["head"] == current_head
    assert result["ancestry"]["accepted_to_head"]["merge_base"] == expected


def test_reconcile_merged_delivery_fails_closed_when_accepted_commit_is_not_on_github(monkeypatch):
    delivery, source, expected = _merged_delivery_fixture(
        monkeypatch,
        head="d" * 40,
        source_status=404,
    )

    with pytest.raises(RuntimeError, match="not available in the configured GitHub repository"):
        delivery.reconcile_merged_delivery(
            repository="acme/demo",
            job_id="job12345",
            branch="ai/job12345",
            base_branch="main",
            source_commit=source,
            expected_commit=expected,
        )


def test_reconcile_merged_delivery_returns_none_when_no_merged_candidate(monkeypatch):
    delivery, source, expected = _merged_delivery_fixture(
        monkeypatch,
        head="d" * 40,
        pulls=[],
    )

    result = delivery.reconcile_merged_delivery(
        repository="acme/demo",
        job_id="job12345",
        branch="ai/job12345",
        base_branch="main",
        source_commit=source,
        expected_commit=expected,
    )

    assert result is None


def test_reconcile_merged_delivery_fails_closed_when_head_does_not_contain_accepted(monkeypatch):
    delivery, source, expected = _merged_delivery_fixture(
        monkeypatch,
        head="d" * 40,
        head_ok=False,
    )

    with pytest.raises(RuntimeError, match="does not contain the preserved accepted commit"):
        delivery.reconcile_merged_delivery(
            repository="acme/demo",
            job_id="job12345",
            branch="ai/job12345",
            base_branch="main",
            source_commit=source,
            expected_commit=expected,
        )


def test_reconcile_merged_delivery_fails_closed_without_green_head_ci(monkeypatch):
    delivery, source, expected = _merged_delivery_fixture(
        monkeypatch,
        head="d" * 40,
        ci_state="failure",
    )

    with pytest.raises(RuntimeError, match="does not have successful GitHub CI"):
        delivery.reconcile_merged_delivery(
            repository="acme/demo",
            job_id="job12345",
            branch="ai/job12345",
            base_branch="main",
            source_commit=source,
            expected_commit=expected,
        )


def test_reconcile_merged_delivery_fails_closed_on_ambiguous_merged_history(monkeypatch):
    head = "d" * 40
    raw = {
        "number": 27,
        "state": "closed",
        "merged": True,
        "merged_at": "2026-09-27T17:03:22Z",
        "merge_commit_sha": "e" * 40,
        "html_url": "https://github.com/acme/demo/pull/27",
        "body": "Automated coding-platform delivery.\n\n- Job: `job12345`",
        "head": {"sha": head, "ref": "ai/job12345", "repo": {"full_name": "acme/demo"}},
        "base": {"ref": "main"},
    }
    delivery, source, expected = _merged_delivery_fixture(
        monkeypatch,
        head=head,
        pulls=[raw, {**raw, "number": 28}],
    )

    with pytest.raises(RuntimeError, match="Ambiguous qualifying merged pull-request history"):
        delivery.reconcile_merged_delivery(
            repository="acme/demo",
            job_id="job12345",
            branch="ai/job12345",
            base_branch="main",
            source_commit=source,
            expected_commit=expected,
        )
