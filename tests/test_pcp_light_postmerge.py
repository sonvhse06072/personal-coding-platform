"""Offline negative/positive contracts for read-only PCP-light postmerge evidence."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pcp_light_postmerge", ROOT / "scripts/pcp-light-postmerge.py"
)
post = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(post)

REPO = post.REPO
MERGE_SHA = "d" * 40
PR_NUMBER = 745
RUN_ID = 88
PR_KEY = f"repos/{REPO}/pulls/{PR_NUMBER}"
RUN_KEY = f"repos/{REPO}/actions/runs/{RUN_ID}"
JOBS_KEY = f"{RUN_KEY}/jobs?filter=latest&per_page=100"


def success_step(name):
    return {"name": name, "status": "completed", "conclusion": "success"}


def valid_response():
    jobs = []
    for i, name in enumerate(post.REQUIRED_JOBS):
        tests = post.ROOT_TEST_STEP if name == "structure-tests" else "Run tests"
        jobs.append({
            "name": name, "status": "completed", "conclusion": "success",
            "runner_name": f"GitHub Actions {1000002600+i}",
            "runner_group_name": "GitHub Actions",
            "started_at": "2026-10-16T09:02:10Z",
            "completed_at": "2026-10-16T09:02:50Z",
            "steps": [success_step(post.HOSTED_STEP), success_step(tests)],
        })
    return {
        PR_KEY: {
            "number": PR_NUMBER, "state": "closed", "merged": True,
            "merge_commit_sha": MERGE_SHA,
            "user": {"login": post.OWNER},
            "base": {"ref": "main", "repo": {"full_name": REPO}},
            "head": {"repo": {"full_name": REPO}},
            "body": "FORGED success, fabricated cash cost: $0.00",
        },
        RUN_KEY: {
            "id": RUN_ID, "name": "tests", "path": post.WORKFLOW_PATH,
            "event": "push", "head_branch": "main",
            "head_sha": MERGE_SHA,
            "repository": {"full_name": REPO},
            "head_repository": {"full_name": REPO},
            "status": "completed", "conclusion": "success",
            "run_attempt": 1,
            "created_at": "2026-10-16T09:02:04Z",
            "updated_at": "2026-10-16T09:02:54Z",
        },
        JOBS_KEY: {"total_count": len(jobs), "jobs": jobs},
    }


class FakeGitHub:
    def __init__(self, responses=None):
        self.responses = valid_response() if responses is None else responses
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        assert argv[:4] == ["gh", "api", "--method", "GET"]
        assert kwargs.get("timeout") == 30
        assert kwargs.get("stdin") is subprocess.DEVNULL
        endpoint = argv[4]
        if endpoint not in self.responses:
            return SimpleNamespace(returncode=1, stdout="", stderr="PRIVATE_TOKEN")
        return SimpleNamespace(returncode=0,
                               stdout=json.dumps(self.responses[endpoint]),
                               stderr="")


@pytest.fixture
def gh(monkeypatch):
    stub = FakeGitHub()
    monkeypatch.setattr(post.subprocess, "run", stub)
    return stub


def check():
    return post.report(PR_NUMBER, MERGE_SHA, RUN_ID)


def test_real_745_shape_exact_merge_and_four_full_hosted_jobs(gh):
    result = check()
    assert result["status"] == "POSTMERGE_CI_VERIFIED"
    assert result["verified"] is True
    assert result["merge_sha"] == MERGE_SHA
    assert result["required_jobs"] == {
        name: "SUCCESS" for name in post.REQUIRED_JOBS
    }
    assert result["runner"] == "GITHUB_HOSTED_VERIFIED"
    assert result["workflow_elapsed_seconds"] == 50
    assert result["estimated_rounded_runner_minutes"] == 4
    assert result["provider_cash_cost"] == "UNAVAILABLE"
    assert result["authorization"].startswith("NONE;")
    assert len(gh.calls) == 3
    assert all(call[0][3] == "GET" for call in gh.calls)
    assert "FORGED" not in str(result)
    assert "PRIVATE_TOKEN" not in str(result)


def test_740_failed_runtime_postmerge_cannot_be_accepted(gh):
    # Real #740 was PR-CI green, while Runtime on push/main failed.
    gh.responses[RUN_KEY]["conclusion"] = "failure"
    assert check()["reason"] == "postmerge_workflow_not_success"
    gh.responses[RUN_KEY]["conclusion"] = "success"
    gh.responses[JOBS_KEY]["jobs"][2]["conclusion"] = "failure"
    assert check()["reason"] == "required_job_not_success"


@pytest.mark.parametrize("change,reason", [
    (lambda d: d[PR_KEY].update(merged=False), "pull_request_not_merged_at_expected_sha"),
    (lambda d: d[PR_KEY].update(merge_commit_sha="a"*40),
     "pull_request_not_merged_at_expected_sha"),
    (lambda d: d[PR_KEY]["base"].update(ref="other"),
     "pull_request_repository_or_author_mismatch"),
    (lambda d: d[PR_KEY]["base"]["repo"].update(full_name="outside/other"),
     "pull_request_repository_or_author_mismatch"),
    (lambda d: d[PR_KEY]["head"]["repo"].update(full_name="outside/other"),
     "pull_request_repository_or_author_mismatch"),
    (lambda d: d[PR_KEY]["user"].update(login="attacker"),
     "pull_request_repository_or_author_mismatch"),
    (lambda d: d[RUN_KEY].update(head_sha="f"*40),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY].update(event="pull_request"),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY].update(head_branch="feature"),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY].update(head_branch=None),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY].pop("head_branch"),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY]["head_repository"].update(full_name="attacker/fork"),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY].update(head_repository=["malformed"]),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY].update(path=".github/workflows/other.yml"),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY].update(name="pretend-tests"),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY]["repository"].update(full_name="attacker/other"),
     "postmerge_workflow_identity_mismatch"),
    (lambda d: d[RUN_KEY].update(run_attempt=0),
     "workflow_attempt_invalid"),
    (lambda d: d[JOBS_KEY].update(total_count=3),
     "required_jobs_missing_duplicate_or_truncated"),
    (lambda d: d[JOBS_KEY]["jobs"][1].update(name="structure-tests"),
     "required_jobs_missing_duplicate_or_truncated"),
    (lambda d: d[JOBS_KEY]["jobs"][1].update(status="skipped"),
     "required_job_not_success"),
    (lambda d: d[JOBS_KEY]["jobs"][1].update(runner_name="SonVH"),
     "required_job_not_hosted"),
    (lambda d: d[JOBS_KEY]["jobs"][1].update(runner_group_name="Default"),
     "required_job_not_hosted"),
    (lambda d: d[JOBS_KEY]["jobs"][1]["steps"][0].update(conclusion="skipped"),
     "required_hosted_attestation_not_success"),
    (lambda d: d[JOBS_KEY]["jobs"][1]["steps"][1].update(conclusion="skipped"),
     "required_full_tests_not_executed"),
    (lambda d: d[JOBS_KEY]["jobs"][0]["steps"][1].update(name="docs-only skip"),
     "required_full_tests_not_executed"),
])
def test_fail_closed_on_untrusted_pr_run_job_or_runner(gh, change, reason):
    change(gh.responses)
    assert check() == {
        "status": "NOT_VERIFIED", "verified": False,
        "reason": reason, "authorization": "NONE",
    }


def test_pending_run_does_not_claim_acceptance(gh):
    gh.responses[RUN_KEY].update(status="in_progress", conclusion=None)
    result = check()
    assert result["status"] == "PENDING" and result["verified"] is False
    assert result["reason"] == "postmerge_workflow_pending"
    assert len(gh.calls) == 2


def test_retry_attempt_is_reported_not_hidden(gh):
    gh.responses[RUN_KEY]["run_attempt"] = 2
    assert check()["run_attempt"] == 2


def test_real_postmerge_747_provenance_requires_main(gh):
    # Real #747 full hosted push/main had both head_branch=main and
    # head_repository=the private PCP repository (run 38890561213).
    result = check()
    assert result["verified"] is True
    gh.responses[RUN_KEY]["head_branch"] = "ai/feature-only"
    assert check()["reason"] == "postmerge_workflow_identity_mismatch"


def test_missing_or_invalid_timestamps_report_unknown_without_fabrication(gh):
    gh.responses[RUN_KEY]["created_at"] = None
    gh.responses[JOBS_KEY]["jobs"][0]["completed_at"] = "n/a"
    result = check()
    assert result["verified"] is True
    assert result["workflow_elapsed_seconds"] is None
    assert result["job_elapsed_seconds"]["structure-tests"] is None
    assert result["estimated_rounded_runner_minutes"] is None


@pytest.mark.parametrize("args,reason", [
    ((True, MERGE_SHA, RUN_ID), "pull_request_number_invalid"),
    ((PR_NUMBER, "NOT_A_SHA", RUN_ID), "expected_merge_sha_invalid"),
    ((PR_NUMBER, MERGE_SHA, 0), "workflow_run_id_invalid"),
])
def test_bad_pins_fail_without_network(gh, args, reason):
    result = post.report(*args)
    assert result["verified"] is False and result["reason"] == reason
    assert gh.calls == []


def test_unavailable_or_invalid_github_is_fail_closed(monkeypatch):
    def unavailable(argv, **kwargs):
        return SimpleNamespace(returncode=1, stdout="PRIVATE_TOKEN",
                               stderr="PRIVATE_TOKEN")
    monkeypatch.setattr(post.subprocess, "run", unavailable)
    result = check()
    assert result["reason"] == "github_get_failed_or_unbounded"
    assert "PRIVATE_TOKEN" not in str(result)
    monkeypatch.setattr(
        post.subprocess, "run",
        lambda argv, **kw: SimpleNamespace(returncode=0, stdout="not-json",
                                          stderr="PRIVATE_TOKEN"),
    )
    assert check()["reason"] == "github_response_not_json"


def test_full_job_requires_exactly_one_successful_test_step(gh):
    extra = copy.deepcopy(gh.responses[JOBS_KEY]["jobs"][0]["steps"][-1])
    gh.responses[JOBS_KEY]["jobs"][0]["steps"].append(extra)
    assert check()["reason"] == "required_full_tests_not_executed"


def test_malformed_nested_identity_fails_closed_instead_of_crashing(gh):
    gh.responses[PR_KEY]["base"]["repo"] = "invalid-shape"
    assert check()["reason"] == "pull_request_repository_or_author_mismatch"
    gh.responses[PR_KEY] = valid_response()[PR_KEY]
    gh.responses[RUN_KEY]["repository"] = ["invalid-shape"]
    assert check()["reason"] == "postmerge_workflow_identity_mismatch"


def test_github_boolean_identity_cannot_masquerade_as_integer(gh):
    gh.responses[RUN_KEY]["id"] = True
    assert check()["reason"] == "postmerge_workflow_identity_mismatch"
    gh.responses[RUN_KEY] = valid_response()[RUN_KEY]
    gh.responses[JOBS_KEY]["total_count"] = True
    assert check()["reason"] == "required_jobs_missing_duplicate_or_truncated"


def test_cli_reports_sanitized_json_and_nonzero_for_failed_gate(gh, capsys):
    assert post.main(["--pr", str(PR_NUMBER), "--expected-merge-sha",
                      MERGE_SHA, "--run-id", str(RUN_ID)]) == 0
    assert json.loads(capsys.readouterr().out)["verified"] is True
    gh.responses[RUN_KEY]["conclusion"] = "failure"
    assert post.main(["--pr", str(PR_NUMBER), "--expected-merge-sha",
                      MERGE_SHA, "--run-id", str(RUN_ID)]) == 1
    assert json.loads(capsys.readouterr().out)["verified"] is False
