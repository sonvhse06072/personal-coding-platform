"""Exact-HEAD hosted CI acceptance for a future isolated full-PCP fixture.

Validate only results supplied by the privileged Executor GitHub CI client,
never model-provided JSON. This is not a CI provider or authentication system.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from .fullpath_fixture_safety import PROJECT_ID as FULLPATH_FIXTURE_PROJECT_ID

FULLPATH_FIXTURE_REPO = "sonvhse06072/pcp-g0-fullpath-fixture"
FULLPATH_WORKFLOW = "validation"
# A distinct policy marker, NOT a GitHub workflow name, prevents accepting
# the dispatch run's main head_sha as a candidate commit.
G1_T02_PROJECT = "pcp-benchmark-g1-t02"
G1_T02_FIXTURE_REPO = FULLPATH_FIXTURE_REPO
G1_T02_DISPATCH_POLICY = "validation_workflow_dispatch"


def required_ci_for_project(project_id: str) -> tuple[str, str] | None:
    """Legacy projects are unchanged; new fixture requires exact hosted CI."""
    if project_id == G1_T02_PROJECT:
        return G1_T02_FIXTURE_REPO, G1_T02_DISPATCH_POLICY
    return (
        (FULLPATH_FIXTURE_REPO, FULLPATH_WORKFLOW)
        if project_id == FULLPATH_FIXTURE_PROJECT_ID
        else None
    )


def required_github_actions_pass(
    ci: dict[str, Any],
    *,
    repository: str,
    commit: str,
    workflow_name: str,
) -> bool:
    """A generic success, missing CI or successful other workflow is not enough."""
    if not (
        isinstance(ci, dict)
        and isinstance(repository, str)
        and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        and isinstance(commit, str)
        and re.fullmatch(r"[0-9a-f]{40}", commit)
        and isinstance(workflow_name, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,100}", workflow_name)
    ):
        return False
    if (
        ci.get("state") != "success"
        or ci.get("repository") != repository
        or ci.get("commit") != commit
        or ci.get("trusted_contract_invalid") is True
        or ci.get("trusted_order_ambiguous") is True
        or ci.get("effective_failures")
    ):
        return False
    if workflow_name == G1_T02_DISPATCH_POLICY:
        proof = ci.get("g1_t02_dispatch")
        # Only the authenticated Executor is allowed to construct this
        # sanitized object; no run's main SHA is a candidate SHA.
        return bool(
            repository == G1_T02_FIXTURE_REPO
            and isinstance(proof, dict)
            and proof.get("verdict") == "CI_VERIFIED_WAITING_PM_REVIEW"
            and proof.get("repository") == repository
            and proof.get("candidate_sha") == commit
            and proof.get("source_sha") == "d4f4a56713e95f85ecc08c02bb43a5b5105a86a3"
            and proof.get("workflow_blob_sha") == "a098e80472afc8dc628723bd26cc72204d8f3faf"
            and type(proof.get("workflow_run_id")) is int
            and proof["workflow_run_id"] > 0
            and re.fullmatch(r"[0-9a-f]{40}",
                             str(proof.get("workflow_run_head_sha") or ""))
            and isinstance(proof.get("job_id"), str)
            and re.fullmatch(r"[a-f0-9]{32}", proof["job_id"])
            and proof.get("branch") == "ai/" + proof["job_id"][:12]
            and proof.get("candidate_sha") != proof.get("workflow_run_head_sha")
        )
    runs = ci.get("actions_runs")
    if not isinstance(runs, list) or not runs or len(runs) > 100:
        return False

    valid = []
    for run in runs:
        if not isinstance(run, dict) or run.get("name") != workflow_name:
            continue
        run_id = run.get("run_id")
        if (
            run.get("source") != "github_actions"
            or type(run_id) is not int
            or run_id <= 0
            or type(run.get("id")) is not int
            or run.get("id") != run_id
            or run.get("head_sha") != commit
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            return False
        url = run.get("details_url")
        if not isinstance(url, str):
            return False
        try:
            uri = urlsplit(url)
            url_ok = (
                uri.scheme == "https"
                and uri.netloc == "github.com"
                and uri.path == f"/{repository}/actions/runs/{run_id}"
                and not uri.query and not uri.fragment
            )
        except ValueError:
            return False
        if not url_ok:
            return False
        valid.append(run_id)
    return len(valid) == 1
