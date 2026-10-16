#!/usr/bin/env python3
"""Read-only, fail-closed PCP-light pull-request readiness report."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import PurePosixPath
import re
import subprocess
import sys
from typing import Any

REPO = "sonvhse06072/personal-coding-platform"
OWNER = "sonvhse06072"
MARKER = "<!-- coding-platform:pcp-light:v1 -->"
ALLOWED_PREFIXES = ("scripts/pcp-light-", "tests/test_pcp_light_", "docs/pcp-light/")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED_JOBS = (
    "structure-tests",
    "python-tests (services/router)",
    "python-tests (services/runtime)",
    "python-tests (services/ddev-executor)",
)
MAX_REPAIR_COMMITS = 4
MAX_COMMIT_FILES = 300  # GitHub's per-commit response is capped at 300 files.


class NotReady(Exception):
    def __init__(self, reason: str, status: str = "NOT_READY") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def get_json(endpoint: str) -> Any:
    """Perform one fixed authenticated GET. Never retry or print gh diagnostics."""
    try:
        proc = subprocess.run(
            ["gh", "api", "--method", "GET", endpoint],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NotReady("github_get_unavailable_or_timeout") from exc
    if proc.returncode != 0:
        raise NotReady("github_get_failed")
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise NotReady("github_response_invalid_json") from exc


def exact_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise NotReady(label + "_invalid")
    return value


def issue_contract(body: Any) -> dict[str, Any]:
    """Require the actual immutable PCP-light v1 marker + exact JSON schema.

    The original one-shot coding runner consumes *this* contract, not a
    free-form Markdown 'Allowed files' section. A valid Owner issue may name
    a source parent older than the current PR base tip after a repair-source
    PR has merged; those two distinct Git commit identities stay separate.
    """
    if not isinstance(body, str) or len(body.encode("utf-8")) > 16000:
        raise NotReady("original_issue_body_invalid")
    if (not body.lstrip().startswith(MARKER)
            or body.count(MARKER) != 1):
        raise NotReady("original_issue_marker_invalid")
    try:
        data = json.loads(body.strip()[len(MARKER):].strip())
    except (TypeError, ValueError) as exc:
        raise NotReady("original_issue_json_invalid") from exc
    if (not isinstance(data, dict)
            or set(data) != {
                "version", "key", "base_sha", "model", "reasoning",
                "goal", "allowed_paths",
            }
            or type(data["version"]) is not int
            or data["version"] != 1
            or not isinstance(data["key"], str)
            or re.fullmatch(r"[a-z][a-z0-9-]{2,39}", data["key"]) is None
            or data["key"].startswith(("g0-", "g1-", "f2-", "chonhac-"))
            or not isinstance(data["base_sha"], str)
            or SHA_RE.fullmatch(data["base_sha"]) is None
            or not isinstance(data["model"], str)
            or re.fullmatch(r"gpt-[a-z0-9][a-z0-9._-]{2,63}",
                            data["model"]) is None
            or data["reasoning"] not in {"low", "medium", "high", "xhigh"}
            or not isinstance(data["goal"], str)
            or not 20 <= len(data["goal"]) <= 8000):
        raise NotReady("original_issue_contract_invalid")
    paths = data["allowed_paths"]
    if (not isinstance(paths, list)
            or not 1 <= len(paths) <= 4
            or any(not isinstance(path, str) for path in paths)
            or len(set(paths)) != len(paths)
            or not any(path.startswith("tests/test_pcp_light_")
                       for path in paths)):
        raise NotReady("original_issue_allowed_paths_invalid")
    for value in paths:
        path = PurePosixPath(value)
        if (len(value) > 240 or "\\" in value or path.is_absolute()
                or ".." in path.parts or path.as_posix() != value
                or not value.startswith(ALLOWED_PREFIXES)
                or not value.endswith((".py", ".md"))
                or (value.startswith(ALLOWED_PREFIXES[:2])
                    and len(path.parts) != 2)):
            raise NotReady("original_issue_allowed_paths_invalid")
    return data


def issue_allowed_paths(body: Any) -> list[str]:
    """Return exact Owner-approved paths, refusing all other representations."""
    return issue_contract(body)["allowed_paths"]

def validate_sha(value: str, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise NotReady(label + "_invalid")
    return value


def validate_pr(pr_number: int, expected_head: str, expected_base: str,
                issue_number: int, issue_digest: str) -> dict[str, Any]:
    pr = get_json("repos/{}/pulls/{}".format(REPO, pr_number))
    if not isinstance(pr, dict) or pr.get("number") != pr_number:
        raise NotReady("pull_request_identity_mismatch")
    base_repo = ((pr.get("base") or {}).get("repo") or {}).get("full_name")
    head_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    if base_repo != REPO or head_repo != REPO:
        raise NotReady("pull_request_repository_mismatch")
    if pr.get("merged") is not False or pr.get("state") != "open":
        raise NotReady("pull_request_not_open_unmerged")
    if (not isinstance(pr.get("user"), dict)
            or pr["user"].get("login") != OWNER):
        raise NotReady("pull_request_author_mismatch")
    head = ((pr.get("head") or {}).get("sha"))
    base = ((pr.get("base") or {}).get("sha"))
    if head != expected_head:
        raise NotReady("pull_request_head_sha_mismatch")
    if base != expected_base:
        raise NotReady("pull_request_base_sha_mismatch")

    issue = get_json("repos/{}/issues/{}".format(REPO, issue_number))
    if (not isinstance(issue, dict) or issue.get("number") != issue_number
            or issue.get("state") != "open"
            or "pull_request" in issue
            or (issue.get("user") or {}).get("login") != OWNER
            or issue.get("author_association") != "OWNER"):
        raise NotReady("original_issue_not_owner_authored")
    body = issue.get("body")
    actual_digest = hashlib.sha256(body.encode("utf-8")).hexdigest() if isinstance(body, str) else ""
    if actual_digest != issue_digest:
        raise NotReady("original_issue_body_digest_mismatch")
    contract = issue_contract(body)
    allowed = contract["allowed_paths"]
    source_parent = contract["base_sha"]
    expected_branch = "ai/pcp-light/" + contract["key"]
    if (not isinstance(pr.get("head"), dict)
            or pr["head"].get("ref") != expected_branch):
        raise NotReady("pull_request_branch_mismatch")

    # GitHub PR base.sha is the CURRENT tip of main; an approved one-shot
    # candidate can retain its original (OLDER) pinned source parent if
    # a PM-reviewed helper was merged in the meantime. Compare the one-turn
    # candidate to that original source, NOT to a moving PR base tip.
    compare = get_json("repos/{}/compare/{}...{}".format(
        REPO, source_parent, expected_head))
    commits = compare.get("commits") if isinstance(compare, dict) else None
    if (not isinstance(compare, dict) or compare.get("status") != "ahead"
            or type(compare.get("ahead_by")) is not int
            or not 1 <= compare["ahead_by"] <= MAX_REPAIR_COMMITS
            or type(compare.get("behind_by")) is not int
            or compare["behind_by"] != 0
            or not isinstance(commits, list)
            or len(commits) != compare["ahead_by"]
            or type(compare.get("total_commits")) is not int
            or compare.get("total_commits") != compare["ahead_by"]
            or not isinstance(compare.get("merge_base_commit"), dict)
            or compare["merge_base_commit"].get("sha") != source_parent):
        raise NotReady("candidate_commit_chain_invalid")

    commit_shas: list[str] = []
    for commit in commits:
        if not isinstance(commit, dict):
            raise NotReady("candidate_commit_chain_invalid")
        commit_shas.append(validate_sha(commit.get("sha"), "candidate_commit_sha"))
    if (len(set(commit_shas)) != len(commit_shas)
            or commit_shas[-1] != expected_head):
        raise NotReady("candidate_commit_chain_invalid")

    # A one-commit candidate retains its original fast path. For repairs, get
    # each immutable commit object once: its parent list proves linear ancestry
    # and its bounded files list catches reverted out-of-scope edits.
    if len(commit_shas) > 1:
        previous = source_parent
        for commit_sha in commit_shas:
            detail = get_json("repos/{}/commits/{}".format(REPO, commit_sha))
            parents = detail.get("parents") if isinstance(detail, dict) else None
            changed = detail.get("files") if isinstance(detail, dict) else None
            if (not isinstance(detail, dict) or detail.get("sha") != commit_sha
                    or not isinstance(parents, list) or len(parents) != 1
                    or not isinstance(parents[0], dict)
                    or parents[0].get("sha") != previous):
                raise NotReady("candidate_commit_parent_chain_invalid")
            if (not isinstance(changed, list) or not changed
                    or len(changed) >= MAX_COMMIT_FILES):
                raise NotReady("commit_changed_paths_missing_or_unbounded")
            seen: set[str] = set()
            for entry in changed:
                if (not isinstance(entry, dict)
                        or not isinstance(entry.get("filename"), str)):
                    raise NotReady("commit_changed_path_evidence_invalid")
                path = entry["filename"]
                if path in seen:
                    raise NotReady("commit_changed_paths_duplicate")
                seen.add(path)
                if entry.get("status") not in {"added", "modified"}:
                    raise NotReady("commit_changed_path_status_not_allowed")
                if path not in allowed:
                    raise NotReady("commit_changed_paths_outside_original_issue_scope")
            previous = commit_sha

    files_doc = get_json("repos/{}/pulls/{}/files?per_page=100".format(REPO, pr_number))
    if not isinstance(files_doc, list) or not files_doc or len(files_doc) >= 100:
        raise NotReady("changed_paths_missing_or_unbounded")
    paths: list[str] = []
    for entry in files_doc:
        if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
            raise NotReady("changed_path_evidence_invalid")
        if entry.get("status") not in {"added", "modified"}:
            raise NotReady("changed_path_status_not_allowed")
        paths.append(entry["filename"])
    if len(paths) != len(set(paths)):
        raise NotReady("changed_paths_duplicate")
    if any(path not in allowed for path in paths):
        raise NotReady("changed_paths_outside_original_issue_scope")
    if not any(path.startswith("tests/") for path in paths):
        raise NotReady("changed_test_missing")

    return {
        "head_sha": head, "base_sha": base,
        "original_source_sha": source_parent,
        "changed_paths": sorted(paths),
        "commit_count": len(commit_shas),
        "original_first_commit_sha": commit_shas[0],
        "repair_chain_needs_independent_review": len(commit_shas) > 1,
    }


def validate_ci(head: str) -> dict[str, str]:
    runs_doc = get_json(
        "repos/{}/actions/workflows/tests.yml/runs?head_sha={}&event=pull_request&per_page=100".format(REPO, head)
    )
    runs = runs_doc.get("workflow_runs") if isinstance(runs_doc, dict) else None
    if not isinstance(runs, list):
        raise NotReady("tests_workflow_runs_invalid")
    matching = [run for run in runs if isinstance(run, dict)
                and run.get("head_sha") == head
                and run.get("event") == "pull_request"
                and run.get("name") == "tests"]
    if not matching:
        raise NotReady("tests_workflow_run_missing")
    matching.sort(key=lambda run: (run.get("run_number", 0), run.get("id", 0)), reverse=True)
    run = matching[0]
    if type(run.get("id")) is not int or run["id"] <= 0:
        raise NotReady("tests_workflow_run_identity_invalid")
    jobs_doc = get_json("repos/{}/actions/runs/{}/jobs?per_page=100".format(REPO, run["id"]))
    jobs = jobs_doc.get("jobs") if isinstance(jobs_doc, dict) else None
    if not isinstance(jobs, list):
        raise NotReady("tests_workflow_jobs_invalid")
    by_name: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        if isinstance(job, dict) and isinstance(job.get("name"), str):
            by_name.setdefault(job["name"], []).append(job)
    outcomes: dict[str, str] = {}
    pending = run.get("status") != "completed"
    for name in REQUIRED_JOBS:
        matches = by_name.get(name, [])
        if len(matches) != 1:
            if pending:
                outcomes[name] = "PENDING"
                continue
            raise NotReady("required_ci_job_missing_or_duplicate")
        job = matches[0]
        if job.get("status") != "completed":
            outcomes[name] = "PENDING"
            pending = True
        elif job.get("conclusion") != "success":
            raise NotReady("required_ci_job_not_success")
        else:
            outcomes[name] = "SUCCESS"
    if run.get("status") == "completed" and run.get("conclusion") != "success":
        raise NotReady("tests_workflow_run_not_success")
    if pending:
        raise NotReady("required_ci_jobs_pending", "PENDING")
    return outcomes


def report(pr_number: int, head: str, base: str, issue_number: int, digest: str) -> dict[str, Any]:
    try:
        pr_number = exact_int(pr_number, "pull_request_number")
        issue_number = exact_int(issue_number, "issue_number")
        head = validate_sha(head, "expected_head_sha")
        base = validate_sha(base, "expected_base_sha")
        if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
            raise NotReady("issue_body_sha256_invalid")
        facts = validate_pr(pr_number, head, base, issue_number, digest)
        ci = validate_ci(head)
        status = ("READY_FOR_PM_REVIEW_WITH_REPAIRS"
                  if facts["commit_count"] > 1 else "READY_FOR_PM_REVIEW")
        return {"status": status, "ready": True,
                "pr": pr_number, "issue": issue_number, **facts,
                "workflow": "tests", "required_jobs": ci,
                "authorization": "NONE; PM code review and all normal gates remain required"}
    except NotReady as exc:
        return {"status": exc.status, "ready": False,
                "reason": exc.reason, "authorization": "NONE"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--issue-body-sha256", required=True)
    args = parser.parse_args(argv)
    result = report(args.pr, args.expected_head, args.expected_base,
                    args.issue, args.issue_body_sha256)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
