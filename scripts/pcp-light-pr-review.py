#!/usr/bin/env python3
"""Read-only, fail-closed PCP-light pull-request readiness report."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from typing import Any

REPO = "sonvhse06072/personal-coding-platform"
OWNER = "sonvhse06072"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
REQUIRED_JOBS = (
    "structure-tests",
    "python-tests (services/router)",
    "python-tests (services/runtime)",
    "python-tests (services/ddev-executor)",
)


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


def issue_allowed_paths(body: Any) -> list[str]:
    if not isinstance(body, str):
        raise NotReady("issue_body_invalid")
    lines = body.splitlines()
    headers = [i for i, line in enumerate(lines)
               if re.fullmatch(r"\s*Allowed (?:files|paths)(?: \(modify ONLY these\))?:\s*", line, re.I)]
    if len(headers) != 1:
        raise NotReady("issue_allowed_paths_missing_or_ambiguous")
    paths: list[str] = []
    for line in lines[headers[0] + 1:]:
        if not line.strip():
            if paths:
                break
            continue
        match = re.fullmatch(r"\s*[-*]\s+`?([^`\s]+)`?\s*", line)
        if not match:
            if paths:
                break
            raise NotReady("issue_allowed_paths_malformed")
        paths.append(match.group(1))
    if not paths or len(paths) != len(set(paths)):
        raise NotReady("issue_allowed_paths_empty_or_duplicate")
    for path in paths:
        if (path.startswith("/") or "\\" in path or ".." in path.split("/")
                or any(ord(c) < 32 or ord(c) == 127 for c in path)):
            raise NotReady("issue_allowed_paths_malformed")
    return paths


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
    head = ((pr.get("head") or {}).get("sha"))
    base = ((pr.get("base") or {}).get("sha"))
    if head != expected_head:
        raise NotReady("pull_request_head_sha_mismatch")
    if base != expected_base:
        raise NotReady("pull_request_base_sha_mismatch")

    issue = get_json("repos/{}/issues/{}".format(REPO, issue_number))
    if (not isinstance(issue, dict) or issue.get("number") != issue_number
            or (issue.get("user") or {}).get("login") != OWNER
            or issue.get("author_association") != "OWNER"):
        raise NotReady("original_issue_not_owner_authored")
    body = issue.get("body")
    actual_digest = hashlib.sha256(body.encode("utf-8")).hexdigest() if isinstance(body, str) else ""
    if actual_digest != issue_digest:
        raise NotReady("original_issue_body_digest_mismatch")
    allowed = issue_allowed_paths(body)

    compare = get_json("repos/{}/compare/{}...{}".format(REPO, expected_base, expected_head))
    commits = compare.get("commits") if isinstance(compare, dict) else None
    if (not isinstance(compare, dict) or compare.get("status") != "ahead"
            or compare.get("ahead_by") != 1 or not isinstance(commits, list)
            or len(commits) != 1 or not isinstance(commits[0], dict)
            or (commits[0].get("sha") != expected_head)):
        raise NotReady("candidate_not_exactly_one_commit_after_base")

    files_doc = get_json("repos/{}/pulls/{}/files?per_page=100".format(REPO, pr_number))
    if not isinstance(files_doc, list) or not files_doc or len(files_doc) >= 100:
        raise NotReady("changed_paths_missing_or_unbounded")
    paths: list[str] = []
    for entry in files_doc:
        if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
            raise NotReady("changed_path_evidence_invalid")
        paths.append(entry["filename"])
    if len(paths) != len(set(paths)):
        raise NotReady("changed_paths_duplicate")
    if any(path not in allowed for path in paths):
        raise NotReady("changed_paths_outside_original_issue_scope")
    if not any(path.startswith("tests/") for path in paths):
        raise NotReady("changed_test_missing")

    return {"head_sha": head, "base_sha": base, "changed_paths": sorted(paths)}


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
        return {"status": "READY_FOR_PM_REVIEW", "ready": True,
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
