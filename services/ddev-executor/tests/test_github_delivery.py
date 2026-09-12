from app.github_delivery import (
    combined_status_signal,
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
            {"id": 1, "name": "lint", "status": "completed", "conclusion": "success"},
            {"id": 2, "name": "tests", "status": "completed", "conclusion": "failure"},
            {"id": 3, "name": "other", "status": "in_progress", "conclusion": None},
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
        {"id": 1, "name": "tests", "status": "completed", "conclusion": "success"}
    ], "")[0] == "success"


def test_empty_combined_status_payload_is_not_a_ci_signal():
    assert combined_status_signal({"state": "pending", "statuses": [], "total_count": 0}) == ""
    assert combined_status_signal({"state": "success", "statuses": [{"context": "ci"}]}) == "success"
    assert combined_status_signal({"state": "failure", "statuses": [{"context": "ci"}]}) == "failure"
