#!/usr/bin/env python3
"""Fail-closed, GET-only PCP-light postmerge CI evidence (never approves a PR).

Pin the merged pull request, exact squash/merge SHA and workflow run ID.
Verify live GitHub records, four actual full hosted job results and runner
attestation. No models, retries, runner operations, merge or deployment.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import re
import subprocess
import sys
from typing import Any

REPO = "sonvhse06072/personal-coding-platform"
OWNER = "sonvhse06072"
WORKFLOW_PATH = ".github/workflows/tests.yml"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
HOSTED_RE = re.compile(r"GitHub Actions [0-9]+\Z")
REQUIRED_JOBS = (
    "structure-tests",
    "python-tests (services/router)",
    "python-tests (services/runtime)",
    "python-tests (services/ddev-executor)",
)
ROOT_TEST_STEP = "Run python -m pytest -q -p no:cacheprovider tests"
HOSTED_STEP = "Verify ephemeral GitHub-hosted runner"
MAX_RESPONSE_CHARS = 1_000_000


class NotVerified(Exception):
    def __init__(self, reason: str, status: str = "NOT_VERIFIED") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def get_json(endpoint: str) -> Any:
    """Fetch only a fixed read-only endpoint; never retry or expose diagnostics."""
    try:
        proc = subprocess.run(
            ["gh", "api", "--method", "GET", endpoint],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NotVerified("github_get_unavailable_or_timeout") from exc
    if (proc.returncode or not isinstance(proc.stdout, str)
            or len(proc.stdout) > MAX_RESPONSE_CHARS):
        raise NotVerified("github_get_failed_or_unbounded")
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise NotVerified("github_response_not_json") from exc


def require_id(value: Any, reason: str) -> int:
    if type(value) is not int or value <= 0:
        raise NotVerified(reason)
    return value


def sha(value: Any) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise NotVerified("expected_merge_sha_invalid")
    return value


def _repo_name(value: Any) -> str | None:
    return value.get("full_name") if isinstance(value, dict) else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _duration(start: Any, end: Any) -> int | None:
    first, last = _timestamp(start), _timestamp(end)
    if first is None or last is None:
        return None
    seconds = (last - first).total_seconds()
    if not math.isfinite(seconds) or seconds < 0 or seconds > 86400:
        return None
    return round(seconds)


def _passed_step(steps: Any, name: str) -> bool:
    if not isinstance(steps, list):
        return False
    matching = [step for step in steps if isinstance(step, dict)
                and step.get("name") == name]
    return len(matching) == 1 and (
        matching[0].get("status") == "completed"
        and matching[0].get("conclusion") == "success"
    )


def validate(pr_number: int, merge_sha: str, run_id: int) -> dict[str, Any]:
    pr_number = require_id(pr_number, "pull_request_number_invalid")
    run_id = require_id(run_id, "workflow_run_id_invalid")
    merge_sha = sha(merge_sha)

    pr = get_json(f"repos/{REPO}/pulls/{pr_number}")
    if (not isinstance(pr, dict) or type(pr.get("number")) is not int
            or pr.get("number") != pr_number):
        raise NotVerified("pull_request_identity_mismatch")
    base = pr.get("base") if isinstance(pr.get("base"), dict) else {}
    head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
    if (pr.get("state") != "closed" or pr.get("merged") is not True
            or pr.get("merge_commit_sha") != merge_sha):
        raise NotVerified("pull_request_not_merged_at_expected_sha")
    if (not isinstance(pr.get("user"), dict)
            or pr["user"].get("login") != OWNER
            or base.get("ref") != "main"
            or _repo_name(base.get("repo")) != REPO
            or _repo_name(head.get("repo")) != REPO):
        raise NotVerified("pull_request_repository_or_author_mismatch")

    run = get_json(f"repos/{REPO}/actions/runs/{run_id}")
    if (not isinstance(run, dict) or type(run.get("id")) is not int
            or run.get("id") != run_id
            or run.get("name") != "tests"
            or run.get("path") != WORKFLOW_PATH
            or run.get("event") != "push"
            or run.get("head_branch") != "main"
            or run.get("head_sha") != merge_sha
            or _repo_name(run.get("repository")) != REPO
            or _repo_name(run.get("head_repository")) != REPO):
        raise NotVerified("postmerge_workflow_identity_mismatch")
    attempt = require_id(run.get("run_attempt"), "workflow_attempt_invalid")
    if run.get("status") != "completed":
        raise NotVerified("postmerge_workflow_pending", "PENDING")
    if run.get("conclusion") != "success":
        raise NotVerified("postmerge_workflow_not_success")

    jobs_doc = get_json(
        f"repos/{REPO}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"
    )
    jobs = jobs_doc.get("jobs") if isinstance(jobs_doc, dict) else None
    if (not isinstance(jobs, list) or type(jobs_doc.get("total_count")) is not int
            or jobs_doc["total_count"] != len(REQUIRED_JOBS)
            or len(jobs) != len(REQUIRED_JOBS)):
        raise NotVerified("required_jobs_missing_duplicate_or_truncated")
    by_name: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if (not isinstance(job, dict) or not isinstance(job.get("name"), str)
                or job["name"] in by_name):
            raise NotVerified("required_jobs_missing_duplicate_or_truncated")
        by_name[job["name"]] = job
    if set(by_name) != set(REQUIRED_JOBS):
        raise NotVerified("required_jobs_missing_duplicate_or_truncated")

    durations: dict[str, int | None] = {}
    for name in REQUIRED_JOBS:
        job = by_name[name]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise NotVerified("required_job_not_success")
        runner = job.get("runner_name")
        if (not isinstance(runner, str) or HOSTED_RE.fullmatch(runner) is None
                or job.get("runner_group_name") != "GitHub Actions"):
            raise NotVerified("required_job_not_hosted")
        if not _passed_step(job.get("steps"), HOSTED_STEP):
            raise NotVerified("required_hosted_attestation_not_success")
        test_step = ROOT_TEST_STEP if name == "structure-tests" else "Run tests"
        if not _passed_step(job.get("steps"), test_step):
            raise NotVerified("required_full_tests_not_executed")
        durations[name] = _duration(job.get("started_at"), job.get("completed_at"))

    minutes = (sum(max(1, math.ceil(seconds / 60))
                   for seconds in durations.values())
               if all(seconds is not None for seconds in durations.values())
               else None)
    return {
        "pr": pr_number,
        "merge_sha": merge_sha,
        "run_id": run_id,
        "run_attempt": attempt,
        "workflow": "tests",
        "required_jobs": {name: "SUCCESS" for name in REQUIRED_JOBS},
        "runner": "GITHUB_HOSTED_VERIFIED",
        "workflow_elapsed_seconds": _duration(
            run.get("created_at"), run.get("updated_at")),
        "job_elapsed_seconds": durations,
        "estimated_rounded_runner_minutes": minutes,
        "provider_cash_cost": "UNAVAILABLE",
    }


def report(pr_number: int, merge_sha: str, run_id: int) -> dict[str, Any]:
    try:
        evidence = validate(pr_number, merge_sha, run_id)
        return {
            "status": "POSTMERGE_CI_VERIFIED",
            "verified": True,
            **evidence,
            "authorization": "NONE; PM acceptance and all other gates remain required",
        }
    except NotVerified as exc:
        return {
            "status": exc.status,
            "verified": False,
            "reason": exc.reason,
            "authorization": "NONE",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-merge-sha", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    args = parser.parse_args(argv)
    result = report(args.pr, args.expected_merge_sha, args.run_id)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
