"""Fully offline tests for the read-only PCP-light PR readiness reporter."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pcp_light_pr_review", ROOT / "scripts/pcp-light-pr-review.py"
)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)

REPO = review.REPO
HEAD = "a" * 40
BASE = "b" * 40
ISSUE_TASK = {
    "version": 1,
    "key": "pr-readiness-report-v1",
    "base_sha": BASE,
    "model": "gpt-6-luna",
    "reasoning": "medium",
    "goal": "Implement a read-only readiness report, giữ đủ quyền và bằng chứng.",
    "allowed_paths": [
        "scripts/pcp-light-pr-review.py",
        "tests/test_pcp_light_pr_review.py",
    ],
}
ISSUE_BODY = review.MARKER + "\n" + json.dumps(
    ISSUE_TASK, sort_keys=True, ensure_ascii=False, indent=2
)
DIGEST = hashlib.sha256(ISSUE_BODY.encode("utf-8")).hexdigest()


def valid_responses():
    return {
        f"repos/{REPO}/pulls/12": {
            "number": 12, "state": "open", "merged": False,
            "user": {"login": "sonvhse06072"}, "author_association": "OWNER",
            "head": {"sha": HEAD, "ref": "ai/pcp-light/pr-readiness-report-v1",
                     "repo": {"full_name": REPO}},
            "base": {"sha": BASE, "repo": {"full_name": REPO}},
            # This mutable PR body deliberately claims false success.
            "body": '{"ci":"SUCCESS","merged":true,"commit":"' + "f" * 40 + '"}',
        },
        f"repos/{REPO}/issues/9": {
            "number": 9, "state": "open", "user": {"login": "sonvhse06072"},
            "author_association": "OWNER", "body": ISSUE_BODY,
        },
        f"repos/{REPO}/compare/{BASE}...{HEAD}": {
            "status": "ahead", "ahead_by": 1, "total_commits": 1, "behind_by": 0,
            "merge_base_commit": {"sha": BASE},
            "commits": [{"sha": HEAD}],
        },
        f"repos/{REPO}/pulls/12/files?per_page=100": [
            {"filename": "scripts/pcp-light-pr-review.py", "status": "added"},
            {"filename": "tests/test_pcp_light_pr_review.py", "status": "added"},
        ],
        f"repos/{REPO}/actions/workflows/tests.yml/runs?head_sha={HEAD}&event=pull_request&per_page=100": {
            "workflow_runs": [{"id": 88, "run_number": 17, "name": "tests",
                               "event": "pull_request", "head_sha": HEAD,
                               "status": "completed", "conclusion": "success"}],
        },
        f"repos/{REPO}/actions/runs/88/jobs?per_page=100": {
            "total_count": len(review.REQUIRED_JOBS),
            "jobs": [{
                "name": name, "status": "completed", "conclusion": "success",
                "runner_name": f"GitHub Actions {1000002630 + index}",
                "runner_group_name": "GitHub Actions",
                "steps": [
                    {"name": review.HOSTED_STEP, "status": "completed",
                     "conclusion": "success"},
                    {"name": (review.ROOT_PYTEST_STEP
                              if name == "structure-tests" else "Run tests"),
                     "status": "completed", "conclusion": "success"},
                ],
            } for index, name in enumerate(review.REQUIRED_JOBS)],
        },
    }


class GhMock:
    def __init__(self, responses=None):
        self.responses = valid_responses() if responses is None else responses
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        assert argv[:3] == ["gh", "api", "--method"]
        assert argv[3] == "GET"
        endpoint = argv[4]
        if endpoint not in self.responses:
            return SimpleNamespace(returncode=1, stdout="", stderr="secret token leaked")
        return SimpleNamespace(returncode=0,
                               stdout=json.dumps(self.responses[endpoint]), stderr="")


@pytest.fixture
def gh(monkeypatch):
    mock = GhMock()
    monkeypatch.setattr(review.subprocess, "run", mock)
    return mock


def run(**kwargs):
    return review.report(kwargs.get("pr", 12), kwargs.get("head", HEAD),
                         kwargs.get("base", BASE), kwargs.get("issue", 9),
                         kwargs.get("digest", DIGEST))


def test_exact_sha_and_live_api_facts_are_ready(gh):
    result = run()
    assert result["status"] == "READY_FOR_PM_REVIEW"
    assert result["head_sha"] == HEAD and result["base_sha"] == BASE
    assert result["original_source_sha"] == BASE
    assert result["changed_paths"] == sorted(ISSUE_TASK["allowed_paths"])
    assert result["commit_count"] == 1
    assert result["original_first_commit_sha"] == HEAD
    assert result["repair_chain_needs_independent_review"] is False
    assert result["required_jobs"] == {name: "SUCCESS" for name in review.REQUIRED_JOBS}
    assert result["authorization"].startswith("NONE;")
    assert len(gh.calls) == 6


def test_wrong_pr_repository_is_not_ready(gh):
    gh.responses[f"repos/{REPO}/pulls/12"]["head"]["repo"]["full_name"] = "attacker/other"
    assert run()["reason"] == "pull_request_repository_mismatch"


def test_original_issue_must_be_owner_authored(gh):
    gh.responses[f"repos/{REPO}/issues/9"]["user"]["login"] = "someone-else"
    assert run()["reason"] == "original_issue_not_owner_authored"


def test_real_owner_marker_json_issue_has_valid_scope(gh):
    assert ISSUE_BODY.startswith(review.MARKER)
    assert review.issue_allowed_paths(ISSUE_BODY) == ISSUE_TASK["allowed_paths"]
    assert run()["status"] == "READY_FOR_PM_REVIEW"


def test_current_pr_base_can_move_after_a_reviewed_helper_merges(gh):
    # Source parent is immutable in the issue; GitHub PR base is moving main.
    newest_main = "c" * 40
    gh.responses[f"repos/{REPO}/pulls/12"]["base"]["sha"] = newest_main
    result = run(base=newest_main)
    assert result["ready"] is True
    assert result["base_sha"] == newest_main
    assert result["original_source_sha"] == BASE
    assert f"repos/{REPO}/compare/{BASE}...{HEAD}" in (
        call[0][4] for call in gh.calls
    )


def test_wrong_pr_author_or_original_branch_is_rejected(gh):
    key = f"repos/{REPO}/pulls/12"
    gh.responses[key]["user"]["login"] = "outsider"
    assert run()["reason"] == "pull_request_author_mismatch"
    gh.responses[key]["user"]["login"] = "sonvhse06072"
    gh.responses[key]["head"]["ref"] = "ai/pcp-light/different-job"
    assert run()["reason"] == "pull_request_branch_mismatch"


def test_closed_original_issue_or_wrong_marker_is_rejected(gh):
    key = f"repos/{REPO}/issues/9"
    gh.responses[key]["state"] = "closed"
    assert run()["reason"] == "original_issue_not_owner_authored"
    gh.responses[key]["state"] = "open"
    gh.responses[key]["body"] = "Allowed files:\n- scripts/a.py\n- tests/b.py"
    digest = hashlib.sha256(gh.responses[key]["body"].encode()).hexdigest()
    assert run(digest=digest)["reason"] == "original_issue_marker_invalid"


def test_issue_duplicate_paths_and_unapproved_paths_fail_closed(gh):
    key = f"repos/{REPO}/issues/9"
    for paths in (
        ["scripts/pcp-light-pr-review.py"] * 2,
        ["scripts/pcp-light-pr-review.py", "tests/test_unrelated.py"],
        ["scripts/pcp-light-pr-review.py", "tests/test_pcp_light_../x.py"],
    ):
        issue = {**ISSUE_TASK, "allowed_paths": paths}
        raw = review.MARKER + "\n" + json.dumps(issue, sort_keys=True)
        gh.responses[key]["body"] = raw
        digest = hashlib.sha256(raw.encode()).hexdigest()
        assert run(digest=digest)["reason"] == "original_issue_allowed_paths_invalid"


def test_candidate_source_parent_is_not_pr_base_tip(gh):
    key = f"repos/{REPO}/compare/{BASE}...{HEAD}"
    gh.responses[key]["merge_base_commit"] = {"sha": "f" * 40}
    assert run()["reason"] == "candidate_commit_chain_invalid"


def test_removed_or_renamed_allowed_test_is_not_ready(gh):
    key = f"repos/{REPO}/pulls/12/files?per_page=100"
    for status in ("removed", "renamed"):
        gh.responses[key][1]["status"] = status
        assert run()["reason"] == "changed_path_status_not_allowed"


def test_mutable_forged_pr_body_cannot_supply_ci_or_commit_proof(gh):
    result = run()
    assert result["ready"] is True
    assert result["head_sha"] == HEAD
    assert result["required_jobs"]["structure-tests"] == "SUCCESS"


@pytest.mark.parametrize("mutation,reason", [
    (lambda d: d.update({"ahead_by": 2, "commits": [{"sha": HEAD}, {"sha": "c" * 40}]}),
     "candidate_commit_chain_invalid"),
    (lambda d: d.update({"status": "behind", "ahead_by": 0, "commits": []}),
     "candidate_commit_chain_invalid"),
])
def test_wrong_commit_count_is_not_ready(gh, mutation, reason):
    mutation(gh.responses[f"repos/{REPO}/compare/{BASE}...{HEAD}"])
    assert run()["reason"] == reason


def install_three_commit_chain(gh):
    # Models PR #736's reported shape: original candidate + two PM repairs,
    # rooted at its immutable Owner-approved source SHA.
    source = "86d34a495f87bb17a07fb18fc8ec64cbe4c6ecef"
    shas = ["1" * 40, "2" * 40, "3" * 40]
    issue = {**ISSUE_TASK, "base_sha": source}
    body = review.MARKER + "\n" + json.dumps(issue, sort_keys=True, ensure_ascii=False)
    gh.responses[f"repos/{REPO}/issues/9"]["body"] = body
    gh.responses[f"repos/{REPO}/pulls/12"]["head"]["sha"] = shas[-1]
    gh.responses[f"repos/{REPO}/compare/{source}...{shas[-1]}"] = {
        "status": "ahead", "ahead_by": 3, "total_commits": 3,
        "behind_by": 0, "merge_base_commit": {"sha": source},
        "commits": [{"sha": sha} for sha in shas],
    }
    for index, sha in enumerate(shas):
        parent = source if index == 0 else shas[index - 1]
        gh.responses[f"repos/{REPO}/commits/{sha}"] = {
            "sha": sha, "parents": [{"sha": parent}],
            "files": [{"filename": path, "status": "modified"}
                      for path in ISSUE_TASK["allowed_paths"]],
        }
    gh.responses[f"repos/{REPO}/actions/workflows/tests.yml/runs?head_sha={shas[-1]}&event=pull_request&per_page=100"] = {
        "workflow_runs": [{"id": 88, "run_number": 17, "name": "tests",
                           "event": "pull_request", "head_sha": shas[-1],
                           "status": "completed", "conclusion": "success"}],
    }
    return source, shas, hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_pr736_three_commit_linear_repair_chain_is_ready_for_independent_review(gh):
    source, shas, digest = install_three_commit_chain(gh)
    result = run(head=shas[-1], digest=digest)
    assert result["status"] == "READY_FOR_PM_REVIEW_WITH_REPAIRS"
    assert result["original_source_sha"] == source
    assert result["original_first_commit_sha"] == shas[0]
    assert result["commit_count"] == 3
    assert result["repair_chain_needs_independent_review"] is True
    assert result["required_jobs"] == {name: "SUCCESS" for name in review.REQUIRED_JOBS}
    commit_gets = [call for call in gh.calls if "/commits/" in call[0][4]]
    assert len(commit_gets) == 3
    assert all(call[0][:4] == ["gh", "api", "--method", "GET"] for call in commit_gets)


def test_repair_chain_rejects_non_linear_and_foreign_intermediate_edits(gh):
    _, shas, digest = install_three_commit_chain(gh)
    first = gh.responses[f"repos/{REPO}/commits/{shas[0]}"]
    first["parents"].append({"sha": "4" * 40})
    assert run(head=shas[-1], digest=digest)["reason"] == "candidate_commit_parent_chain_invalid"
    first["parents"] = [{"sha": "86d34a495f87bb17a07fb18fc8ec64cbe4c6ecef"}]
    first["files"].append({"filename": "docs/project/constitution.md", "status": "modified"})
    assert run(head=shas[-1], digest=digest)["reason"] == "commit_changed_paths_outside_original_issue_scope"


def test_repair_chain_rejects_stale_parent_head_base_and_count_mismatch(gh):
    source, shas, digest = install_three_commit_chain(gh)
    key = f"repos/{REPO}/commits/{shas[1]}"
    gh.responses[key]["parents"] = [{"sha": "4" * 40}]
    assert run(head=shas[-1], digest=digest)["reason"] == "candidate_commit_parent_chain_invalid"
    gh.responses[key]["parents"] = [{"sha": shas[0]}]
    compare_key = f"repos/{REPO}/compare/{source}...{shas[-1]}"
    gh.responses[compare_key]["total_commits"] = 2
    assert run(head=shas[-1], digest=digest)["reason"] == "candidate_commit_chain_invalid"


def test_repair_chain_rejects_truncated_or_overlong_commit_file_lists(gh):
    _, shas, digest = install_three_commit_chain(gh)
    gh.responses[f"repos/{REPO}/commits/{shas[0]}"]["files"] = []
    assert run(head=shas[-1], digest=digest)["reason"] == "commit_changed_paths_missing_or_unbounded"
    gh.responses[f"repos/{REPO}/commits/{shas[0]}"]["files"] = [
        {"filename": "tests/test_pcp_light_pr_review.py", "status": "modified"}
    ] * 300
    assert run(head=shas[-1], digest=digest)["reason"] == "commit_changed_paths_missing_or_unbounded"


def test_stale_base_is_not_ready(gh):
    assert run(base="c" * 40)["reason"] == "pull_request_base_sha_mismatch"


def test_duplicate_changed_paths_are_not_ready(gh):
    gh.responses[f"repos/{REPO}/pulls/12/files?per_page=100"].append(
        {"filename": "tests/test_pcp_light_pr_review.py", "status": "added"})
    assert run()["reason"] == "changed_paths_duplicate"


def test_bad_issue_digest_is_not_ready(gh):
    assert run(digest="0" * 64)["reason"] == "original_issue_body_digest_mismatch"


def test_non_owner_issue_is_not_ready(gh):
    gh.responses[f"repos/{REPO}/issues/9"]["author_association"] = "COLLABORATOR"
    assert run()["reason"] == "original_issue_not_owner_authored"


@pytest.mark.parametrize("job_change,reason", [
    ("missing", "required_ci_job_missing_or_duplicate"),
    ("failed", "required_ci_job_not_success"),
    ("skipped", "required_ci_job_not_success"),
    ("partial", "required_ci_job_missing_or_duplicate"),
    ("queued", "required_ci_jobs_pending"),
])
def test_missing_failed_partial_skipped_or_pending_ci_is_never_green(gh, job_change, reason):
    jobs = gh.responses[f"repos/{REPO}/actions/runs/88/jobs?per_page=100"]["jobs"]
    if job_change == "missing":
        jobs.pop()
    elif job_change == "partial":
        jobs[:] = jobs[:2]
    elif job_change == "failed":
        jobs[0]["conclusion"] = "failure"
    elif job_change == "skipped":
        jobs[0]["conclusion"] = "skipped"
    else:
        jobs[0]["status"] = "queued"
    result = run()
    assert result["reason"] == reason
    assert result["status"] == ("PENDING" if job_change == "queued" else "NOT_READY")


@pytest.mark.parametrize("mutation,reason", [
    ("selfhosted_runner", "required_ci_runner_not_hosted"),
    ("untrusted_runner_group", "required_ci_runner_not_hosted"),
    ("hosted_check_missing", "required_ci_hosted_attestation_not_success"),
    ("hosted_check_skipped", "required_ci_hosted_attestation_not_success"),
    ("hosted_check_duplicate", "required_ci_hosted_attestation_not_success"),
    ("pytest_step_skipped", "required_ci_pytest_not_executed"),
    ("pytest_step_failed", "required_ci_pytest_not_executed"),
    ("pytest_step_missing", "required_ci_pytest_not_executed"),
    ("pytest_step_duplicate", "required_ci_pytest_not_executed"),
    ("job_total_truncated", "required_ci_job_missing_or_duplicate"),
    ("job_total_boolean", "required_ci_job_missing_or_duplicate"),
])
def test_four_green_job_conclusions_are_not_sufficient_ci_proof(
    gh, mutation, reason,
):
    evidence = gh.responses[f"repos/{REPO}/actions/runs/88/jobs?per_page=100"]
    job = evidence["jobs"][1]  # Router full pytest required.
    if mutation == "selfhosted_runner":
        job["runner_name"] = "SonVH"
    elif mutation == "untrusted_runner_group":
        job["runner_group_name"] = "Default"
    elif mutation == "hosted_check_missing":
        job["steps"].pop(0)
    elif mutation == "hosted_check_skipped":
        job["steps"][0]["conclusion"] = "skipped"
    elif mutation == "hosted_check_duplicate":
        job["steps"].append(dict(job["steps"][0]))
    elif mutation == "pytest_step_skipped":
        job["steps"][1]["conclusion"] = "skipped"
    elif mutation == "pytest_step_failed":
        job["steps"][1]["conclusion"] = "failure"
    elif mutation == "pytest_step_missing":
        job["steps"].pop(1)
    elif mutation == "pytest_step_duplicate":
        job["steps"].append(dict(job["steps"][1]))
    elif mutation == "job_total_truncated":
        evidence["total_count"] = 5
    else:
        evidence["total_count"] = True
    # Source PR still reports completed SUCCESS and all four job conclusions
    # SUCCESS; attestations/actual full test execution must govern readiness.
    assert all(item["conclusion"] == "success" for item in evidence["jobs"])
    outcome = run()
    assert outcome["status"] == "NOT_READY"
    assert outcome["reason"] == reason


def test_real_740_docs_only_false_green_cannot_pass_pcp_light_readiness(gh):
    # PR #740 had 4/4 job SUCCESS but three services skipped real pytest.
    evidence = gh.responses[f"repos/{REPO}/actions/runs/88/jobs?per_page=100"]
    for job in evidence["jobs"]:
        if job["name"] == "structure-tests":
            continue
        job["steps"][1]["conclusion"] = "skipped"
        job["steps"].append({
            "name": "T1/T3 document-only PR - service suite not applicable",
            "status": "completed", "conclusion": "success",
        })
    assert run()["reason"] == "required_ci_pytest_not_executed"


def test_structure_root_pytest_must_actually_run(gh):
    evidence = gh.responses[f"repos/{REPO}/actions/runs/88/jobs?per_page=100"]
    evidence["jobs"][0]["steps"][1]["conclusion"] = "skipped"
    assert run()["reason"] == "required_ci_pytest_not_executed"


def test_pr_body_cannot_override_live_failed_ci(gh):
    gh.responses[f"repos/{REPO}/actions/runs/88/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
    assert run()["ready"] is False


def test_queued_run_with_not_yet_created_jobs_is_pending(gh):
    runs_key = f"repos/{REPO}/actions/workflows/tests.yml/runs?head_sha={HEAD}&event=pull_request&per_page=100"
    gh.responses[runs_key]["workflow_runs"][0]["status"] = "queued"
    gh.responses[f"repos/{REPO}/actions/runs/88/jobs?per_page=100"]["jobs"] = []
    result = run()
    assert result["status"] == "PENDING"
    assert result["reason"] == "required_ci_jobs_pending"


def test_all_requests_are_fixed_get_only_calls(gh):
    run()
    assert all(call[0][:4] == ["gh", "api", "--method", "GET"] for call in gh.calls)
    assert all(call[1]["stdin"] is review.subprocess.DEVNULL for call in gh.calls)


@pytest.mark.parametrize("kwargs", [
    {"head": "a" * 39}, {"base": "G" * 40}, {"digest": "xyz"},
    {"pr": True}, {"issue": 0},
])
def test_invalid_explicit_pins_fail_before_github_calls(gh, kwargs):
    assert run(**kwargs)["ready"] is False
    assert gh.calls == []
