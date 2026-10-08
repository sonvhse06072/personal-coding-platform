"""Owner-delegated PM-chat review: authenticated, exact-head manual trust path.

This is intentionally NOT an independent model-provider review. Its separate
audit type is enabled only by explicit project configuration and an authenticated
owner GitHub control. No reviewer model is invoked, no job history is rewritten,
and all original protected decisions and merge gates remain authoritative.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import project_config
from .pm_bridge import bridge_project_config
from .pm_control import PMControlEventStore
from .pm_late_review import registered_review_capacity
from .pm_merge import PMChatReviewProof, evaluate_pm_merge
from .pm_review_capacity_diagnostic import probe_reviewer_capacity
from .storage import now


PM_CHAT_REVIEW_MARKER = "<!-- coding-platform:pm-chat-review:v1 -->"

PM_CHAT_REVIEW_DDL = """
CREATE TABLE IF NOT EXISTS cp_pm_chat_review_attestations (
  id BIGSERIAL PRIMARY KEY,
  project_id TEXT NOT NULL,
  plan_id TEXT NOT NULL,
  work_order_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  expected_head TEXT NOT NULL,
  checkpoint_id BIGINT NOT NULL,
  pr_number INTEGER NOT NULL,
  review_id BIGINT NOT NULL,
  control_comment_id BIGINT NOT NULL,
  payload JSONB NOT NULL,
  payload_sha256 TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE (plan_id, work_order_id, job_id, expected_head, checkpoint_id),
  UNIQUE (project_id, pr_number, review_id)
);
"""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


class PMChatReviewReport(BaseModel):
    """A standalone structured GitHub review; never supplied by PM Bridge JSON."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    project_id: str = Field(min_length=1, max_length=200)
    plan_id: str = Field(min_length=1, max_length=200)
    work_order_id: str = Field(min_length=1, max_length=200)
    job_id: str = Field(min_length=8, max_length=100)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    branch: str = Field(min_length=1, max_length=200)
    pr_number: int = Field(ge=1)
    checkpoint_id: int = Field(ge=1)
    checkpoint_key: str = Field(min_length=1, max_length=500)
    verdict: Literal["pass", "fail"]
    summary: str = Field(min_length=80, max_length=4000)
    findings: list[str] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_findings(self) -> "PMChatReviewReport":
        if (self.verdict == "pass" and self.findings) or (self.verdict == "fail" and not self.findings):
            raise ValueError("A passing PM-chat review must have zero blocking findings; FAIL requires findings")
        if any(not item.strip() or len(item) > 800 for item in self.findings):
            raise ValueError("Review findings must be concise and nonempty")
        return self


def parse_pm_chat_review(body: str) -> PMChatReviewReport:
    if len(body.encode("utf-8")) > 16384 or body.count(PM_CHAT_REVIEW_MARKER) != 1:
        raise ValueError("PM-chat review must contain exactly one bounded, versioned marker")
    payload = body.split(PM_CHAT_REVIEW_MARKER, 1)
    if payload[0].strip() or not payload[1].strip():
        raise ValueError("PM-chat review must be a marker followed only by structured JSON")
    try:
        data = json.loads(payload[1].strip())
    except (ValueError, TypeError) as exc:
        raise ValueError("PM-chat review is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("PM-chat review must be a JSON object")
    return PMChatReviewReport.model_validate(data)




class PMChatReviewStore:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def ensure(self) -> None:
        with self.storage.connect() as conn:
            conn.execute(PM_CHAT_REVIEW_DDL)
            conn.commit()

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Append only: identical controls are idempotent; conflicts fail closed."""
        self.ensure()
        digest = _digest(payload)
        keys = (
            payload["project_id"], payload["plan_id"], payload["work_order_id"],
            payload["job_id"], payload["expected_head"], payload["checkpoint_id"],
            payload["pr_number"], payload["review_id"], payload["control_comment_id"],
            json.dumps(payload, sort_keys=True, ensure_ascii=False), digest, now(),
        )
        with self.storage.connect() as conn:
            row = conn.execute(
                """INSERT INTO cp_pm_chat_review_attestations
                (project_id, plan_id, work_order_id, job_id, expected_head,
                 checkpoint_id, pr_number, review_id, control_comment_id,
                 payload, payload_sha256, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                ON CONFLICT (plan_id, work_order_id, job_id, expected_head, checkpoint_id)
                DO NOTHING RETURNING *""",
                keys,
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """SELECT * FROM cp_pm_chat_review_attestations
                    WHERE plan_id=%s AND work_order_id=%s AND job_id=%s
                      AND expected_head=%s AND checkpoint_id=%s""",
                    (payload["plan_id"], payload["work_order_id"], payload["job_id"],
                     payload["expected_head"], payload["checkpoint_id"]),
                ).fetchone()
            conn.commit()
        if row is None or row["payload_sha256"] != digest or dict(row["payload"]) != payload:
            raise RuntimeError("pm_chat_review_replay_or_identity_conflict")
        return dict(row)

    def get(self, attestation_id: int) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT * FROM cp_pm_chat_review_attestations WHERE id=%s",
                (attestation_id,),
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        if _digest(dict(value["payload"])) != value["payload_sha256"]:
            raise RuntimeError("pm_chat_review_attestation_integrity_failure")
        return value


class PMChatReviewService:
    def __init__(self, storage: Any, engine: Any, orchestrator: Any) -> None:
        self.storage = storage
        self.engine = engine
        self.orchestrator = orchestrator
        self.store = PMChatReviewStore(storage)
        self.control_events = PMControlEventStore(storage)

    def _owner_author(self, project_id: str) -> str:
        config = bridge_project_config(project_id)
        manual = config.get("pm_chat_review") or {}
        author = manual.get("owner_author") if isinstance(manual, dict) else None
        if (
            not isinstance(manual, dict) or manual.get("enabled") is not True
            or not isinstance(author, str) or not author
            or author not in config["allowed_authors"]
        ):
            raise RuntimeError("pm_chat_review_not_owner_authorized_for_project")
        return author

    def _control(self, *, project_id: str, comment_id: int, issue_number: int, owner: str) -> dict[str, Any]:
        record = self.control_events.get(project_id, comment_id)
        if (
            not record or record.get("author") != owner
            or int(record.get("issue_number") or 0) != issue_number
            or int(record.get("comment_id") or 0) != comment_id
        ):
            raise RuntimeError("pm_chat_review_control_author_not_authorized")
        return dict(record)

    async def _capacity(self, job: dict[str, Any]) -> str:
        registry = registered_review_capacity(job)
        if (
            registry.get("status") != "registry_evaluated"
            or not registry.get("writer_providers")
            or registry.get("strict_higher_tier_registry_model_ids")
        ):
            # If a potentially eligible stronger model exists, the manual path
            # does not guess whether it has capacity. Keep the automated gate.
            raise RuntimeError("pm_chat_review_reviewer_capacity_not_exhausted")
        probe = await probe_reviewer_capacity(job=job, router=self.engine.router)
        status = str(probe.get("status") or "")
        if status not in {"no_eligible_cross_provider_now", "no_registered_cross_provider_candidate"}:
            # "staffing_unverifiable", Router/auth/network failures, and staffed
            # cross-provider candidates must never be treated as no capacity.
            raise RuntimeError("pm_chat_review_reviewer_capacity_not_verified")
        return status

    @staticmethod
    def _review_identity(
        review: dict[str, Any], *, project_id: str, repo: str, owner: str,
        pr_number: int, review_id: int, expected_head: str,
    ) -> PMChatReviewReport:
        url = f"https://github.com/{repo}/pull/{pr_number}#pullrequestreview-{review_id}"
        if (
            review.get("project_id") != project_id
            or review.get("repository") != repo
            or review.get("pr_number") != pr_number
            or type(review.get("id")) is not int or review.get("id") != review_id
            or review.get("state") != "COMMENTED"
            or review.get("author") != owner
            or review.get("commit_id") != expected_head
            or review.get("html_url") != url
            or not review.get("submitted_at")
        ):
            raise RuntimeError("pm_chat_review_github_provenance_invalid")
        return parse_pm_chat_review(str(review.get("body") or ""))

    async def _github_review(
        self, *, project_id: str, repo: str, owner: str,
        pr_number: int, review_id: int, expected_head: str,
    ) -> tuple[dict[str, Any], PMChatReviewReport]:
        review = await self.engine.ddev.github_pull_request_review(
            project_id=project_id, pr_number=pr_number, review_id=review_id,
        )
        report = self._review_identity(
            review, project_id=project_id, repo=repo, owner=owner,
            pr_number=pr_number, review_id=review_id, expected_head=expected_head,
        )
        return review, report

    @staticmethod
    def _report_matches(report: PMChatReviewReport, envelope: Any) -> bool:
        fields = (
            "project_id", "plan_id", "work_order_id", "job_id", "source_commit",
            "expected_head", "branch", "pr_number", "checkpoint_id", "checkpoint_key",
        )
        return all(getattr(report, field) == getattr(envelope, field) for field in fields)

    async def record(self, envelope: Any, *, comment_id: int, issue_number: int) -> dict[str, Any]:
        """Ingest exactly one owner-authorized PR review; do not trigger merge."""
        owner = self._owner_author(envelope.project_id)
        control = self._control(
            project_id=envelope.project_id, comment_id=comment_id,
            issue_number=issue_number, owner=owner,
        )
        plan, _, job, extra, _ = await self.orchestrator.late_reviews._preflight(envelope)
        if str(plan.get("ticket_id") or "") != f"GH-{issue_number}":
            raise RuntimeError("pm_chat_review_control_issue_not_canonical_ticket")
        if control.get("repository") != extra["pr"].get("repository"):
            raise RuntimeError("pm_chat_review_control_repository_mismatch")
        repo = str(extra["pr"]["repository"])
        review, report = await self._github_review(
            project_id=envelope.project_id, repo=repo, owner=owner,
            pr_number=envelope.pr_number, review_id=envelope.review_id,
            expected_head=envelope.expected_head,
        )
        if not self._report_matches(report, envelope):
            raise RuntimeError("pm_chat_review_report_identity_mismatch")
        capacity = await self._capacity(job)
        data = {
            "review_mode": "pm_chat_manual_review",
            "project_id": envelope.project_id,
            "plan_id": envelope.plan_id,
            "work_order_id": envelope.work_order_id,
            "job_id": envelope.job_id,
            "source_commit": envelope.source_commit,
            "branch": envelope.branch,
            "expected_head": envelope.expected_head,
            "pr_number": envelope.pr_number,
            "checkpoint_id": envelope.checkpoint_id,
            "checkpoint_key": envelope.checkpoint_key,
            "diff_hash": str((job["result"]["diff"] or {}).get("diff_hash") or ""),
            "review_id": envelope.review_id,
            "review_author": owner,
            "review_body_sha256": hashlib.sha256(review["body"].encode("utf-8")).hexdigest(),
            "review_submitted_at": review["submitted_at"],
            "review_url": review["html_url"],
            "control_comment_id": comment_id,
            "control_body_sha256": control["body_sha256"],
            "capacity_status": capacity,
            "verdict": report.verdict,
            "finding_count": len(report.findings),
            "report_sha256": _digest(report.model_dump()),
        }
        row = self.store.append(data)
        return {
            "status": "attested" if report.verdict == "pass" else "review_failed",
            "attestation_id": int(row["id"]),
            "review_mode": "pm_chat_manual_review",
            "expected_head": envelope.expected_head,
        }

    def trusted_proof(
        self, *, plan: dict[str, Any], tracked: dict[str, Any], job: dict[str, Any],
        attestation_id: int, checkpoint_id: int, checkpoint_key: str,
    ) -> PMChatReviewProof | None:
        row = self.store.get(attestation_id)
        if row is None:
            return None
        data = dict(row["payload"])
        if (
            data.get("verdict") != "pass" or data.get("finding_count") != 0
            or data.get("capacity_status") not in {
                "no_eligible_cross_provider_now", "no_registered_cross_provider_candidate"
            }
            or data.get("checkpoint_id") != checkpoint_id
            or data.get("checkpoint_key") != checkpoint_key
            or self._owner_author(str(data.get("project_id") or "")) != data.get("review_author")
            or any(row.get(field) != data.get(field) for field in (
                "project_id", "plan_id", "work_order_id", "job_id", "expected_head",
                "checkpoint_id", "pr_number", "review_id", "control_comment_id",
            ))
        ):
            raise RuntimeError("pm_chat_review_attestation_identity_invalid")
        proof = PMChatReviewProof(
            attestation_id=int(row["id"]),
            project_id=data["project_id"], plan_id=data["plan_id"],
            work_order_id=data["work_order_id"], job_id=data["job_id"],
            source_commit=data["source_commit"], branch=data["branch"],
            expected_head=data["expected_head"], pr_number=data["pr_number"],
            diff_hash=data["diff_hash"], checkpoint_id=data["checkpoint_id"],
            checkpoint_key=data["checkpoint_key"], review_id=data["review_id"],
            review_author=data["review_author"],
            review_body_sha256=data["review_body_sha256"],
            control_comment_id=data["control_comment_id"],
            verdict="pass",
        )
        return proof if proof.matches(plan, tracked, job) else None

    async def verify_live(self, proof: PMChatReviewProof, repo: str) -> None:
        """Fail closed if an already-attested review was edited or revoked."""
        review, report = await self._github_review(
            project_id=proof.project_id, repo=repo, owner=proof.review_author,
            pr_number=proof.pr_number, review_id=proof.review_id,
            expected_head=proof.expected_head,
        )
        if (
            hashlib.sha256(review["body"].encode("utf-8")).hexdigest() != proof.review_body_sha256
            or report.verdict != "pass" or report.findings
        ):
            raise RuntimeError("pm_chat_review_live_review_changed")

    async def release(self, envelope: Any, *, comment_id: int, issue_number: int) -> dict[str, Any]:
        """Move the same blocked checkpoint to normal constrained PM merge."""
        owner = self._owner_author(envelope.project_id)
        control = self._control(
            project_id=envelope.project_id, comment_id=comment_id,
            issue_number=issue_number, owner=owner,
        )
        plan, tracked, job, extra, _ = await self.orchestrator.late_reviews._preflight(envelope)
        if (
            str(plan.get("ticket_id") or "") != f"GH-{issue_number}"
            or control.get("repository") != extra["pr"].get("repository")
        ):
            raise RuntimeError("pm_chat_review_release_origin_mismatch")
        proof = self.trusted_proof(
            plan=plan, tracked=tracked, job=job,
            attestation_id=int(envelope.attestation_id),
            checkpoint_id=int(envelope.checkpoint_id),
            checkpoint_key=str(envelope.checkpoint_key),
        )
        if proof is None:
            raise RuntimeError("pm_chat_review_no_valid_attestation")
        await self.verify_live(proof, str(extra["pr"]["repository"]))
        await self._capacity(job)
        decision = evaluate_pm_merge(
            project=project_config(envelope.project_id),
            plan=plan, tracked=tracked, job=job, pr=extra["pr"],
            current_ci=extra["ci"], pm_chat_review_proof=proof,
        )
        if not decision.eligible or decision.requires_human or decision.blockers:
            raise RuntimeError("pm_chat_review_other_merge_gates_not_satisfied")
        if self.orchestrator.merge_audit.get(
            plan_id=envelope.plan_id, work_order_id=envelope.work_order_id,
            expected_head=envelope.expected_head,
        ) is not None:
            raise RuntimeError("pm_chat_review_existing_merge_audit")
        detail = dict(tracked.get("detail") or {})
        detail["pm_chat_review_release"] = {
            "attestation_id": proof.attestation_id,
            "checkpoint_id": proof.checkpoint_id,
            "checkpoint_key": proof.checkpoint_key,
            "head": proof.expected_head,
            "review_mode": proof.review_mode,
            "control_comment_id": comment_id,
        }
        detail.pop("reason", None)
        checkpoint = self.orchestrator._checkpoint_transition(
            tracked, kind="pm_chat_review_released",
            state="awaiting_merge", job=job, pr=extra["pr"], detail=detail,
        )
        self.orchestrator.store.update_plan(envelope.plan_id, status="waiting_merge")
        return {
            "status": "released", "attestation_id": proof.attestation_id,
            "checkpoint_id": checkpoint["id"], "head": proof.expected_head,
            "review_mode": proof.review_mode,
        }
