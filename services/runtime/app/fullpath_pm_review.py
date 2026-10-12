"""Exact-HEAD PM acknowledgement for a FUTURE standalone full-path fixture.

Read live GitHub PR/CI/review via the existing privileged Executor. A single
PostgreSQL row lock on the already-owned Runtime cp_jobs row makes completion
durable, conflict-free and idempotent. No new review server, agent token,
repository writer, plan fabrication or automatic GitHub merge.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .activity import status_transition_event
from .baseline import resolve_project_baseline
from .config import project_config, projects_doc, project_baselines_doc
from .fullpath_ci_deferred import WAITING_PM
from .fullpath_fixture_safety import (
    FIXED_ENV, PROJECT_ID, _database_uri, _service_uri,
)
from .required_ci import required_ci_for_project, required_github_actions_pass
from .scope_guard import changed_path_protected_signals
from .storage import _insert_job_event, now


MARKER = "<!-- coding-platform:fullpath-pm-review:v1 -->"
FINISHED = "pm_review_accepted"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIFF = re.compile(r"^[0-9a-f]{64}$")
_JOB = re.compile(r"^[0-9a-f]{32}$")
_LOGIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")


class FullpathPMReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    branch: str = Field(min_length=4, max_length=180, pattern=r"^ai/[a-zA-Z0-9._/-]+$")
    baseline_revision: str = Field(min_length=1, max_length=100)
    pr_number: int = Field(ge=1)
    review_id: int = Field(ge=1)


class FullpathPMReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    project_id: Literal["pcp-g0-fullpath-fixture"]
    job_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    branch: str = Field(min_length=4, max_length=180, pattern=r"^ai/[a-zA-Z0-9._/-]+$")
    baseline_revision: str = Field(min_length=1, max_length=100)
    pr_number: int = Field(ge=1)
    ci_run_id: int = Field(ge=1)
    diff_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    verdict: Literal["pass", "fail"]
    summary: str = Field(min_length=80, max_length=4000)
    findings: list[str] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_findings(self) -> "FullpathPMReport":
        if (self.verdict == "pass" and self.findings) or (
            self.verdict == "fail" and not self.findings
        ):
            raise ValueError("PASS requires zero findings; FAIL needs findings")
        if any(not s.strip() or len(s) > 800 for s in self.findings):
            raise ValueError("Findings must be bounded non-empty strings")
        return self


def parse_review_body(body: str) -> FullpathPMReport:
    if (
        not isinstance(body, str)
        or len(body.encode("utf-8")) > 16384
        or body.count(MARKER) != 1
    ):
        raise ValueError("Fullpath PM review marker or size is invalid")
    before, after = body.split(MARKER, 1)
    if before.strip() or not after.strip():
        raise ValueError("Review must contain marker followed only by JSON")
    try:
        data = json.loads(after.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid fullpath PM review JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Fullpath PM review must be a JSON object")
    return FullpathPMReport.model_validate(data)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str,
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _date(value: Any) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("pm_fullpath_review_timestamp_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("pm_fullpath_review_timestamp_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError("pm_fullpath_review_timestamp_naive")
    result = parsed.astimezone(timezone.utc)
    if result > datetime.now(timezone.utc):
        raise RuntimeError("pm_fullpath_review_timestamp_future")
    return result


def require_isolated_review_environment(env: Mapping[str, str]) -> None:
    """No GitHub fetch and no database reads if invoked on a legacy stack."""
    required = {
        "PCP_RUNTIME_STARTUP_MODE": "normal",
        "PCP_FULLPATH_PM_FINALIZATION_ENABLED": "owner-approved",
        **{
            key: val for key, val in FIXED_ENV.items()
            if key != "PCP_RUNTIME_STARTUP_MODE"
        },
    }
    if (
        any(env.get(key) != val for key, val in required.items())
        or not _database_uri(env.get("DATABASE_URL", ""))
        or not _service_uri(
            env.get("ROUTER_URL", ""), host="fullpath-router", port=8090,
        )
        or not _service_uri(
            env.get("DDEV_EXECUTOR_URL", ""), host="fullpath-executor",
            port=8790,
        )
        or any(env.get(key) for key in (
            "ANTIGRAVITY_BRIDGE_URL", "ANTIGRAVITY_BRIDGE_TOKEN",
            "PCP_G0_EXECUTION_ENABLED", "PCP_G0_DELIVERY_ENABLED",
            "GITHUB_DELIVERY_TOKEN",
        ))
        or os.path.exists("/var/run/docker.sock")
    ):
        raise RuntimeError("pm_fullpath_isolated_runtime_not_authorized")


def require_eligible_job(
    row: dict[str, Any], request: FullpathPMReviewRequest,
    *, job_id: str, baseline_source: str,
) -> None:
    """Fail closed on an unapproved standalone job or incomplete verification."""
    result = row.get("result") or {}
    checkpoint = row.get("checkpoint") or {}
    progress = row.get("progress") or {}
    delivery = result.get("delivery") or {}
    verification = result.get("verification") or {}
    pr = delivery.get("pull_request") or {}
    route = result.get("route") or {}
    strategy = route.get("strategy") or {}
    permissions = strategy.get("permissions") or {}
    intake = checkpoint.get("canonical_intake") or {}
    pm_evidence = result.get("pm_evidence") or {}
    reviewer = result.get("review") or {}
    baseline = checkpoint.get("project_baseline") or {}
    changed = (result.get("diff") or {}).get("changed_files")
    analysis = row.get("repo_analysis") or {}
    sensitive = (
        "security_sensitive", "authentication_change",
        "authorization_change", "destructive_migration",
        "production_write",
    )
    required = required_ci_for_project(PROJECT_ID)
    if not (
        _JOB.fullmatch(job_id)
        and row.get("id") == job_id
        and row.get("project_id") == PROJECT_ID
        and row.get("status") == "waiting_human"
        and row.get("source_commit") == request.source_commit == baseline_source
        and row.get("branch") == request.branch
        and result.get("branch") == request.branch
        and result.get("commit") == request.expected_head
        and result.get("status") == "accepted"
        and result.get("acceptance_phase") == WAITING_PM
        and result.get("delivery_finalized") is False
        and checkpoint.get("acceptance_phase") == WAITING_PM
        and baseline.get("revision") == request.baseline_revision
        and baseline.get("source_commit") == baseline_source
        and intake.get("mode") == "direct"
        and intake.get("bounded_direct") is True
        and intake.get("decomposition_required") is False
        and not checkpoint.get("work_order")
        and not checkpoint.get("orchestrator_launch")
        and not checkpoint.get("pending_decision")
        and not checkpoint.get("pending_pm_reassessment")
        and not checkpoint.get("pending_review_findings")
        and not checkpoint.get("pending_review_repair")
        and isinstance(changed, list) and bool(changed)
        and not changed_path_protected_signals(changed, checkpoint)
        and not any(analysis.get(key) for key in sensitive)
        and not progress.get("important_decision_flags")
        and progress.get("required_checks_passed") is True
        and progress.get("tests_passed") is True
        and progress.get("unexpected_scope") is False
        and verification.get("verification_mode") == "hosted_ci"
        and verification.get("passed") is True
        and verification.get("tests_passed") is True
        and verification.get("hosted_ci_passed") is True
        and verification.get("hosted_ci_pending") is False
        and verification.get("local_tests_executed") is False
        and verification.get("test_runs", 0) == 0
        and verification.get("hosted_ci_commit") == request.expected_head
        and delivery.get("state") == "ci_success"
        and required is not None
        and required_github_actions_pass(
            delivery.get("ci") or {},
            repository=required[0], commit=request.expected_head,
            workflow_name=required[1],
        )
        and type(pr.get("number")) is int
        and pr.get("number") == request.pr_number
        and pr.get("repository") == required[0]
        and pr.get("head") == request.expected_head
        and pr.get("head_ref") == request.branch
        and pr.get("base_ref") == "benchmark/fullpath"
        and pr.get("merged") is not True
        and reviewer.get("verdict") == "pass"
        and reviewer.get("protocol_valid") is not False
        and not reviewer.get("findings")
        and not pm_evidence.get("unresolved_risks")
        and not pm_evidence.get("protected_decision_flags")
        and not (strategy.get("human_decision") or {}).get("required")
        and all(permissions.get(key) is True for key in (
            "commit", "push_ai_branch", "create_pr",
        ))
        and not result.get("fullpath_pm_review")
    ):
        raise RuntimeError("pm_fullpath_job_not_eligible")


def validate_live_proof(
    row: dict[str, Any],
    request: FullpathPMReviewRequest,
    *, job_id: str,
    reviewer_login: str,
    pr: dict[str, Any],
    ci: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    """Bind all external facts to original job and original GitHub review."""
    requirement = required_ci_for_project(PROJECT_ID)
    if requirement is None:
        raise RuntimeError("pm_fullpath_required_ci_unknown")
    repo, workflow = requirement
    if not (
        isinstance(pr, dict) and isinstance(ci, dict) and isinstance(review, dict)
        and pr.get("project_id") == PROJECT_ID
        and pr.get("repository") == repo
        and type(pr.get("number")) is int and pr["number"] == request.pr_number
        and pr.get("state") == "open" and pr.get("merged") is False
        and pr.get("head") == request.expected_head
        and pr.get("head_ref") == request.branch
        and pr.get("base_ref") == "benchmark/fullpath"
        and pr.get("html_url") == f"https://github.com/{repo}/pull/{request.pr_number}"
        and required_github_actions_pass(
            ci, repository=repo, commit=request.expected_head,
            workflow_name=workflow,
        )
        and review.get("project_id") == PROJECT_ID
        and review.get("repository") == repo
        and type(review.get("pr_number")) is int
        and review.get("pr_number") == request.pr_number
        and type(review.get("id")) is int
        and review.get("id") == request.review_id
        and review.get("state") == "COMMENTED"
        and review.get("commit_id") == request.expected_head
        and review.get("author") == reviewer_login
        and review.get("html_url") == (
            f"https://github.com/{repo}/pull/{request.pr_number}"
            f"#pullrequestreview-{request.review_id}"
        )
    ):
        raise RuntimeError("pm_fullpath_github_identity_or_ci_invalid")

    report = parse_review_body(review.get("body"))
    diff = (row.get("result") or {}).get("diff") or {}
    if (
        report.verdict != "pass" or report.findings
        or report.project_id != PROJECT_ID or report.job_id != job_id
        or report.source_commit != request.source_commit
        or report.expected_head != request.expected_head
        or report.branch != request.branch
        or report.baseline_revision != request.baseline_revision
        or report.pr_number != request.pr_number
        or report.diff_hash != diff.get("diff_hash")
        or not _DIFF.fullmatch(report.diff_hash)
    ):
        raise RuntimeError("pm_fullpath_review_report_binding_invalid")

    runs = [
        run for run in (ci.get("actions_runs") or [])
        if isinstance(run, dict) and run.get("name") == workflow
    ]
    if len(runs) != 1 or report.ci_run_id != runs[0].get("run_id"):
        raise RuntimeError("pm_fullpath_review_ci_run_mismatch")
    reviewed_at = _date(review.get("submitted_at"))
    ci_completed_at = _date(runs[0].get("updated_at"))
    if reviewed_at <= ci_completed_at:
        raise RuntimeError("pm_fullpath_review_precedes_ci")
    record = {
        "project_id": PROJECT_ID, "job_id": job_id,
        "source_commit": request.source_commit,
        "expected_head": request.expected_head,
        "branch": request.branch,
        "baseline_revision": request.baseline_revision,
        "repository": repo, "pr_number": request.pr_number,
        "review_id": request.review_id,
        "review_author": reviewer_login,
        "review_body_sha256": hashlib.sha256(
            review["body"].encode("utf-8")
        ).hexdigest(),
        "review_submitted_at": review["submitted_at"],
        "review_url": review["html_url"],
        "ci_run_id": report.ci_run_id,
        "ci_commit": request.expected_head,
        "diff_hash": report.diff_hash,
        "verdict": report.verdict,
        "decision": "pm_review_pass",
    }
    record["receipt_sha256"] = digest(record)
    return record


class FullpathPMReviewService:
    def __init__(self, storage: Any, executor: Any) -> None:
        self.storage = storage
        self.executor = executor

    async def finalize(
        self, job_id: str, request: FullpathPMReviewRequest,
        *, env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        require_isolated_review_environment(env if env is not None else os.environ)
        if not isinstance(job_id, str) or not _JOB.fullmatch(job_id):
            raise RuntimeError("pm_fullpath_job_id_invalid")
        # Require an exact singleton project/baseline registry before any job
        # store access, not merely the expected file path.
        registered = projects_doc().get("projects")
        registered_baselines = project_baselines_doc().get("projects")
        if (
            not isinstance(registered, dict)
            or set(registered) != {PROJECT_ID}
            or not isinstance(registered_baselines, dict)
            or set(registered_baselines) != {PROJECT_ID}
        ):
            raise RuntimeError("pm_fullpath_foreign_project_registry")
        project = project_config(PROJECT_ID)
        review_policy = project.get("pm_standalone_review") or {}
        reviewer_login = (
            review_policy.get("reviewer_login")
            if isinstance(review_policy, dict) else None
        )
        if (
            not isinstance(review_policy, dict)
            or review_policy.get("enabled") is not True
            or not isinstance(reviewer_login, str)
            or not _LOGIN.fullmatch(reviewer_login)
            or project.get("base_branch") != "benchmark/fullpath"
            or (project.get("autonomy") or {}).get("allow_production_deploy") is not False
            or (project.get("runtime") or {}).get("workspace_mode") != "isolated_clone"
            or (project.get("ddev") or {}).get("enabled") is not False
        ):
            raise RuntimeError("pm_fullpath_review_project_authority_missing")
        baseline = resolve_project_baseline(PROJECT_ID, request.baseline_revision)
        if (
            baseline is None or baseline.revision != request.baseline_revision
            or baseline.source_commit != request.source_commit
        ):
            raise RuntimeError("pm_fullpath_review_baseline_unapproved")

        row = self.storage.get(job_id)
        if not row or row.get("project_id") != PROJECT_ID:
            raise RuntimeError("pm_fullpath_job_not_found")
        original_digest = digest(row)
        # The original receipt is re-verified from live GitHub even on a replay.
        if row.get("status") != "completed":
            require_eligible_job(
                row, request, job_id=job_id,
                baseline_source=baseline.source_commit,
            )
        else:
            saved = (row.get("result") or {}).get("fullpath_pm_review") or {}
            if (
                (row.get("result") or {}).get("acceptance_phase") != FINISHED
                or not saved or saved.get("expected_head") != request.expected_head
                or saved.get("pr_number") != request.pr_number
                or saved.get("review_id") != request.review_id
                or saved.get("source_commit") != request.source_commit
                or saved.get("baseline_revision") != request.baseline_revision
                or saved.get("branch") != request.branch
            ):
                raise RuntimeError("pm_fullpath_conflicting_finalization_replay")

        pr = await self.executor.github_pull_request(
            project_id=PROJECT_ID, pr_number=request.pr_number,
        )
        ci = await self.executor.github_ci(
            project_id=PROJECT_ID, commit=request.expected_head,
        )
        review = await self.executor.github_pull_request_review(
            project_id=PROJECT_ID, pr_number=request.pr_number,
            review_id=request.review_id,
        )
        receipt = validate_live_proof(
            row, request, job_id=job_id, reviewer_login=reviewer_login,
            pr=pr, ci=ci, review=review,
        )
        return self.commit_receipt(
            job_id=job_id, request=request,
            baseline_source=baseline.source_commit,
            original_digest=original_digest, receipt=receipt,
        )

    def commit_receipt(
        self, *, job_id: str, request: FullpathPMReviewRequest,
        baseline_source: str, original_digest: str, receipt: dict[str, Any],
    ) -> dict[str, Any]:
        """DB transaction: serialize competing reviews; one receipt per job."""
        with self.storage.connect() as conn:
            locked = conn.execute(
                "SELECT * FROM cp_jobs WHERE id=%s FOR UPDATE", (job_id,),
            ).fetchone()
            if not locked or locked.get("project_id") != PROJECT_ID:
                raise RuntimeError("pm_fullpath_locked_job_not_found")
            current_result = locked.get("result") or {}
            if locked.get("status") == "completed":
                stored = current_result.get("fullpath_pm_review") or {}
                if (
                    current_result.get("acceptance_phase") == FINISHED
                    and current_result.get("delivery_finalized") is True
                    and stored == receipt
                ):
                    return {
                        "status": "completed", "job_id": job_id,
                        "expected_head": receipt["expected_head"],
                        "pr_number": receipt["pr_number"],
                        "receipt_sha256": receipt["receipt_sha256"],
                        "idempotent_replay": True,
                        "github_pr_merged": False,
                    }
                raise RuntimeError("pm_fullpath_receipt_conflict")
            if digest(locked) != original_digest:
                raise RuntimeError("pm_fullpath_job_changed_during_review")
            require_eligible_job(
                locked, request, job_id=job_id,
                baseline_source=baseline_source,
            )
            result = deepcopy(current_result)
            checkpoint = deepcopy(locked.get("checkpoint") or {})
            progress = deepcopy(locked.get("progress") or {})
            result["fullpath_pm_review"] = deepcopy(receipt)
            result["acceptance_phase"] = FINISHED
            result["delivery_finalized"] = True
            checkpoint["fullpath_pm_review"] = deepcopy(receipt)
            checkpoint["acceptance_phase"] = FINISHED
            progress["pm_review_finalized"] = True

            updated = conn.execute(
                """UPDATE cp_jobs SET status='completed', result=%s::jsonb,
                checkpoint=%s::jsonb, progress=%s::jsonb, updated_at=%s
                WHERE id=%s AND status='waiting_human' RETURNING id""",
                (
                    json.dumps(result, sort_keys=True),
                    json.dumps(checkpoint, sort_keys=True),
                    json.dumps(progress, sort_keys=True),
                    now(), job_id,
                ),
            ).fetchone()
            if updated is None:
                raise RuntimeError("pm_fullpath_atomic_transition_conflict")
            event = status_transition_event("waiting_human", "completed")
            if event:
                _insert_job_event(conn, job_id, event)
            conn.commit()
            return {
                "status": "completed", "job_id": job_id,
                "expected_head": receipt["expected_head"],
                "pr_number": receipt["pr_number"],
                "receipt_sha256": receipt["receipt_sha256"],
                "idempotent_replay": False,
                "github_pr_merged": False,
            }
