"""Default-OFF B2.2b PCP-local bounded loop: one receipt, no replay.

The installed Runtime does NOT construct a trusted attestor or launcher, and
does NOT start this loop at process startup. Only B2.2c may approve actual
service credentials, model execution and on-host attestation.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
from typing import Any

from .pcp_local_task_queue import (
    LocalSourceQueueStore, LocalSourceTask, TaskStop, verify_issue,
    require, PROJECT_ID, REPOSITORY, MARKER,
)
from .pcp_local_worker_admission import check_worker_admission

EVIDENCE_PARTS = frozenset({"project", "baseline", "isolation", "provider", "budget"})
LAUNCH_RECEIPT_FIELDS = frozenset({
    "job_id", "state", "source_commit", "baseline_revision",
})


def source_worker_flags() -> None:
    """Two independent opt-ins. All are ABSENT from shipped DDEV Compose."""
    require(
        os.getenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "") == "owner-approved"
        and os.getenv("PCP_LOCAL_TASK_WORKER_ENABLED", "") == "owner-approved",
        "pcp_local_worker_disabled",
    )


def operational_flag() -> None:
    source_worker_flags()
    # A source-only project approval must NOT automatically authorize model
    # calls, provider egress, host Docker or a privileged delivery publisher.
    require(
        os.getenv("PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION", "") == "owner-approved",
        "pcp_local_live_activation_not_approved",
    )


def stable_job_id(task: LocalSourceTask) -> str:
    """Stable job identity, does not allocate, authorize, or submit a job."""
    data = (
        f"pcp-local:v1:{task.repository}:{task.issue_number}:"
        f"{task.body_sha256}:{task.base_sha}:{task.baseline_revision}"
    )
    return hashlib.sha256(data.encode("ascii")).hexdigest()[:32]


class LocalWorkerLoop:
    """One-shot bounded scan/verification. NEVER an independent daemon.

    trusted_attestor is a future separately reviewed in-process component,
    not an object/value taken from GitHub or an HTTP request body.
    launcher is a future separately approved Runtime-owned durable job
    adapter. Neither is connected to live Runtime under this source change.
    """

    def __init__(self, *, receipts: LocalSourceQueueStore, github: Any,
                 trusted_attestor: Any | None = None,
                 launcher: Any | None = None) -> None:
        self.receipts = receipts
        self.github = github
        self.trusted_attestor = trusted_attestor
        self.launcher = launcher

    async def _prepare(self) -> tuple[
        LocalSourceTask, dict[str, Any], dict[str, Any], str
    ] | None:
        source_worker_flags()
        # Do not even read DB or GitHub if no approved trusted evidence
        # integration was installed. Model/issue-reported proofs are invalid.
        require(self.trusted_attestor is not None
                and callable(getattr(self.trusted_attestor, "observe", None)),
                "pcp_local_trusted_attestor_not_installed")
        receipt = self.receipts.next_pending()
        if receipt is None:
            return None
        require(receipt.get("project_id") == PROJECT_ID
                and receipt.get("repository") == REPOSITORY
                and receipt.get("state") == "pending"
                and receipt.get("generation") == 0
                and receipt.get("job_id") is None,
                "pcp_local_pending_receipt_changed")
        issue_number = receipt["issue_number"]
        # Executor token stays behind the existing narrow fixed-repo GET API.
        source = await self.github.local_source_issue(issue_number=issue_number)
        require(type(source) is dict, "pcp_local_source_shape_invalid")
        task = verify_issue(
            source,
            issue_number=issue_number,
            body_sha256=receipt["body_sha256"],
            base_sha=receipt["base_sha"],
            baseline_revision=receipt["baseline_revision"],
            baseline_source_commit=receipt["baseline_source_commit"],
        )
        # Independently attest the already-approved ProjectBaseline, source,
        # workspace, lease, provider and budget against live trusted state.
        evidence = self.trusted_attestor.observe(task)
        if inspect.isawaitable(evidence):
            evidence = await evidence
        require(type(evidence) is dict and set(evidence) == EVIDENCE_PARTS,
                "pcp_local_evidence_shape_invalid")
        decision = check_worker_admission(
            task, receipt=receipt,
            project=evidence["project"], baseline=evidence["baseline"],
            isolation=evidence["isolation"], provider=evidence["provider"],
            budget=evidence["budget"],
        )
        require(
            decision.get("status") == "ADMISSION_EVIDENCE_CHECKED_NOT_DISPATCHED"
            and decision.get("can_start_agent") is False
            and decision.get("can_claim_lease") is False
            and decision.get("can_publish_or_merge") is False,
            "pcp_local_admission_not_authorizing",
        )
        # Runtime prompt originates from exactly the digest-checked issue;
        # it may not contain arbitrary runtime flags, secrets or commands.
        body = source["body"]
        try:
            payload = json.loads(body.strip()[len(MARKER):].strip())
            goal = payload["goal"]
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskStop("pcp_local_goal_invalid") from exc
        require(type(goal) is str
                and hashlib.sha256(goal.encode("utf-8")).hexdigest()
                == task.goal_sha256,
                "pcp_local_goal_identity_changed")
        return task, receipt, decision, goal

    async def preview_once(self) -> dict[str, Any]:
        """No claims, no external writes, no model. One oldest pending only."""
        current = await self._prepare()
        if current is None:
            return {"status": "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED",
                    "model_calls": 0}
        task, _, decision, _ = current
        return {
            "status": "PCP_LOCAL_SOURCE_VALIDATED_NOT_DISPATCHED",
            "issue_number": task.issue_number,
            "body_sha256": task.body_sha256,
            "source_commit": task.base_sha,
            "baseline_revision": task.baseline_revision,
            "task_key": task.task_key,
            "job_id_if_authorized": stable_job_id(task),
            "can_start_agent": False,
            "can_claim_lease": False,
            "requires_fresh_live_recheck": decision["requires_fresh_live_recheck"],
            "model_calls": 0,
        }

    async def execute_once(self) -> dict[str, Any]:
        """FUTURE B2.2c ONLY: reserve once, invoke preinstalled trusted adapter.

        This function is NEVER wired into a Runtime endpoint/startup in B2.2b.
        After a durable claim, a crash or uncertain launch is NOT retried:
        an independent operator must reconcile the exact existing job.
        """
        operational_flag()  # Check before DB/GitHub reads, claims or model.
        require(self.launcher is not None
                and callable(getattr(self.launcher, "launch", None)),
                "pcp_local_durable_launcher_not_installed")
        current = await self._prepare()
        if current is None:
            return {"status": "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED",
                    "model_calls": 0}
        task, _, decision, goal = current
        require(decision.get("requires_fresh_live_recheck") is True,
                "pcp_local_live_recheck_required")
        job_id = stable_job_id(task)
        self.receipts.advance(
            task, expected_state="pending", expected_generation=0,
            target_state="claimed", job_id=job_id, worker_authorized=True,
        )
        # The trusted launcher must perform its own just-in-time project/
        # lease/provider checks BEFORE touching Runtime jobs or Codex.
        try:
            result = self.launcher.launch(
                task=task, goal=goal, job_id=job_id,
                evidence=decision,
            )
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            # Do NOT auto-retry: after claim, the actual launch side effect is
            # unknowable. Preserve claimed row, original job and counters.
            raise TaskStop("pcp_local_launch_uncertain_do_not_retry") from exc
        require(type(result) is dict and set(result) == LAUNCH_RECEIPT_FIELDS
                and result.get("job_id") == job_id
                and result.get("state") == "queued"
                and result.get("source_commit") == task.base_sha
                and result.get("baseline_revision") == task.baseline_revision,
                "pcp_local_launch_ack_ambiguous_do_not_retry")
        # Retain claim until independent durable Runtime job confirmation.
        # Never treat an unreviewed PR or successful model turn as delivered.
        return {
            "status": "PCP_LOCAL_CLAIMED_AWAITING_JOB_RECONCILIATION",
            "issue_number": task.issue_number, "job_id": job_id,
            "receipt_generation": 1,
            "source_commit": task.base_sha,
            "model_execution_proof": "NOT_ATTESTED",
            "can_merge": False,
        }
