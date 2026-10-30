from __future__ import annotations

import time
from pathlib import Path
from copy import deepcopy
from typing import Any

from .delivery import DeliveryError, deliver_verified_work, pull_request_body
from .fullpath_ci_deferred import ci_passed_awaiting_review, stage_delivery_update
from .fullpath_fixture_safety import PROJECT_ID as FULLPATH_FIXTURE_PROJECT_ID
from .required_ci import (
    G1_T02_PROJECT, G1_T02_DISPATCH_POLICY, required_ci_for_project,
    required_github_actions_pass,
)
import os
import re
from .engine_verification import RuntimeEngine as ExecutionRuntimeEngine
from .engine_core import require_legacy_job
from .fingerprint import failure_fingerprint
from .legacy_delivery_recovery import (
    LEGACY_RECOVERY_BLOCK_REASON,
    recover_legacy_accepted_result,
)
from .review_repair_churn import archive_epoch as archive_review_repair_churn_epoch
from .review_repair_churn import ReviewRepairChurnPaused


class DeliveryAwareStorage:
    """Prevent a verified job from becoming externally final before delivery.

    The execution engine owns coding/verification. When it reaches its existing
    `completed` transition, this proxy converts that transition to `delivering`
    only when branch publishing is enabled. The delivery engine then publishes,
    monitors CI, and performs the real terminal transition. This avoids a race
    where API clients could observe `completed` before GitHub delivery finishes.
    """

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    def __getattr__(self, name: str) -> Any:
        return getattr(self.backend, name)

    @staticmethod
    def _requires_delivery(fields: dict[str, Any]) -> bool:
        if fields.get("status") != "completed":
            return False
        result = fields.get("result") or {}
        if result.get("dry_run") or result.get("delivery_finalized"):
            return False
        route = result.get("route") or {}
        permissions = (route.get("strategy") or {}).get("permissions") or {}
        return bool(permissions.get("push_ai_branch", False))

    def update(self, job_id: str, **fields: Any) -> None:
        values = dict(fields)
        if values.get("status") == "completed":
            # Future fixture alone: no completed/passed state can escape before
            # exact hosted CI and a separate trusted PM review action.
            row = self.backend.get(job_id) or {}
            values = stage_delivery_update(row, values)
            if row.get("project_id") == G1_T02_PROJECT and not (
                (values.get("result") or {}).get("dry_run")
            ):
                result = values.get("result") or {}
                strategy = (result.get("route") or {}).get("strategy") or {}
                rights = strategy.get("permissions") or {}
                if not (
                    os.getenv("PCP_G1_T02_IDENTITY_ENABLED") == "owner-approved"
                    and os.getenv("PCP_G1_T02_DELIVERY_ENABLED") == "owner-approved"
                    and all(rights.get(key) is True for key in (
                        "commit", "push_ai_branch", "create_pr",
                    ))
                    and rights.get("auto_merge_low_risk") is False
                    and rights.get("production_deploy") is False
                    and isinstance(result.get("commit"), str)
                    and re.fullmatch(r"[0-9a-f]{40}", result["commit"])
                    # A previously finalized result cannot be re-admitted.
                    and result.get("delivery_finalized") is not True
                ):
                    values["status"] = "blocked"
                    values["error"] = "g1_t02_delivery_admission_denied"
                    values["result"] = {
                        "reason": "g1_t02_delivery_admission_denied",
                        # Preserve audit without exposing a resumable
                        # accepted_result to delivery-recovery machinery.
                        "provisional_result": deepcopy(result),
                    }
                else:
                    # Persist an explicit non-final result without changing caller input.
                    values["result"] = {**result, "delivery_finalized": False}
                    values["status"] = "delivering"
        if self._requires_delivery(values):
            values["status"] = "delivering"
        self.backend.update(job_id, **values)


class RuntimeEngine(ExecutionRuntimeEngine):
    def __init__(self, storage: Any) -> None:
        self._delivery_storage_backend = storage
        super().__init__(DeliveryAwareStorage(storage))

    @staticmethod
    def _accepted_result_for_delivery(row: dict[str, Any]) -> dict[str, Any] | None:
        """Return the locally verified result, including from a delivery block.

        Delivery/API failures are infrastructure failures that happen after the
        code has already passed local Definition-of-Done and been committed. The
        block result keeps that verified payload under `accepted_result`; resume
        must continue delivery from it rather than spending another model call.
        """
        result = row.get("result") or {}
        candidate = result
        if candidate.get("status") != "accepted":
            nested = result.get("accepted_result")
            if not isinstance(nested, dict):
                return None
            candidate = nested
        if candidate.get("status") != "accepted" or candidate.get("delivery_finalized"):
            return None
        return deepcopy(candidate)

    @staticmethod
    def _delivered_result_for_review_repair(row: dict[str, Any]) -> dict[str, Any] | None:
        """Return accepted delivery evidence whether finalized or delivery-blocked."""
        result = row.get("result") or {}
        candidate = result
        if candidate.get("status") != "accepted":
            nested = result.get("accepted_result")
            if not isinstance(nested, dict):
                return None
            candidate = nested
        if candidate.get("status") != "accepted" or not candidate.get("commit"):
            return None
        delivery = candidate.get("delivery") or (row.get("checkpoint") or {}).get("delivery")
        pull_request = (delivery or {}).get("pull_request") or {}
        if not pull_request.get("number"):
            return None
        return deepcopy(candidate)

    @staticmethod
    def _update_review_repair_history(
        checkpoint: dict[str, Any],
        request_id: str,
        **updates: Any,
    ) -> None:
        history = [
            deepcopy(item)
            for item in (checkpoint.get("review_repair_history") or [])
            if isinstance(item, dict)
        ]
        for item in reversed(history):
            if str(item.get("request_id") or "") == request_id:
                item.update(deepcopy(updates))
                break
        checkpoint["review_repair_history"] = history

    @classmethod
    def _verified_result_needs_delivery(cls, row: dict[str, Any]) -> bool:
        result = cls._accepted_result_for_delivery(row)
        if not result:
            return False
        delivery = result.get("delivery") or {}
        if (
            delivery.get("state") == "ci_failure"
            and cls._ci_failure_class(delivery) != "infrastructure"
            and not bool((result.get("legacy_delivery_recovery") or {}).get("authorized"))
        ):
            return False
        route = result.get("route") or row.get("route") or {}
        permissions = (route.get("strategy") or {}).get("permissions") or {}
        return bool(permissions.get("push_ai_branch", False)) and bool(result.get("commit"))

    @staticmethod
    def _ci_failure_class(delivery: dict[str, Any]) -> str:
        """Return the bounded CI failure class, defaulting ambiguity to repair."""
        ci = delivery.get("ci") or {}
        if str(ci.get("failure_class") or "") == "infrastructure":
            return "infrastructure"
        return "engineering"

    @classmethod
    def _delivery_wait_seconds(
        cls,
        strategy: dict[str, Any],
        progress: dict[str, Any],
    ) -> int:
        # Adaptive jobs keep delivery bounded by a 15-minute attempt cap without
        # turning accumulated engineering wall time into an owner checkpoint.
        if cls._adaptive_work_shape_nonblocking(strategy):
            return 900

        total = int(float(strategy.get("budget", {}).get("max_wall_time_minutes", 60)) * 60)
        elapsed = int(float(progress.get("elapsed_minutes", 0.0)) * 60)
        remaining = total - elapsed
        if remaining <= 0:
            raise DeliveryError(
                "github_delivery_budget_exhausted",
                "Job wall-time budget was exhausted before GitHub delivery.",
            )
        return max(1, min(900, remaining))

    @staticmethod
    def _charge_delivery_time(progress: dict[str, Any], started: float) -> None:
        spent_minutes = max(0.0, (time.monotonic() - started) / 60.0)
        progress["elapsed_minutes"] = round(
            float(progress.get("elapsed_minutes", 0.0)) + spent_minutes,
            3,
        )

    async def finalize_pcp_local_review(self, payload, *, dry_run=False):
        """Record authenticated independent PM outcome; no merge/model/replay."""
        import json
        from .pcp_local_worker_loop import TrustedReaders, digest
        from .pcp_local_task_queue import PROJECT_ID, REPOSITORY, require
        from .pm_bridge import PMBridgeGitHubClient
        from .pm_merge import evaluate_standalone_pm_merge
        readers = TrustedReaders(self, PMBridgeGitHubClient())
        project, baseline = readers.authority()
        a = readers.activation
        job_id = __import__('hashlib').sha256((f"pcp-local:v1:{REPOSITORY}:{a['issue_number']}:"
            f"{a['body_sha256']}:{a['base_sha']}:{a['baseline_revision']}").encode('ascii')).hexdigest()[:32]
        row = self.storage.get(job_id)
        require(row is not None and row['project_id'] == PROJECT_ID
                and row['source_commit'] == payload.source_commit == a['base_sha']
                and baseline.revision == payload.baseline_revision
                and row['checkpoint']['project_baseline'] == baseline.model_dump(mode='json'),
                'pcp_local_review_job_identity_invalid')
        result = deepcopy(row.get('result') or {})
        require(result.get('commit') == payload.expected_head
                and row.get('branch') == payload.branch
                and result.get('verification', {}).get('passed') is True
                and result.get('verification', {}).get('test_runs', 0) > 0,
                'pcp_local_review_unverified_job')
        require('pcp_local_retirement' not in row['checkpoint'], 'pcp_local_retired_job')
        if row.get('status') == 'completed' and result.get('delivery_finalized') is True:
            require(result.get('review', {}).get('review_id') == payload.review_id,
                    'pcp_local_review_conflicting_retry')
            return dict(job_id=job_id, status='completed', merged=False,
                        pm_merge_eligibility=result['pm_merge_eligibility'])
        from .pcp_local_readiness import operation_snapshot, finalization_ownership
        original, receipt_before, lease_before = operation_snapshot(self.storage, job_id)
        require(original == row, 'pcp_local_review_race')
        finalization_ownership(row, receipt_before, lease_before)
        workspace = Path(row['workspace'])
        require(workspace == self.workspace_root / job_id and not workspace.is_symlink()
                and workspace.resolve() == workspace, 'pcp_local_workspace_identity_invalid')
        execution = row['checkpoint']['pcp_local_execution']
        require(execution.get('state') == 'verified' and execution.get('commit') == payload.expected_head,
                'pcp_local_review_unverified_job')
        proof = await readers.executor('/v1/pcp-local/pm-review', dict(job_id=job_id,
            source_commit=payload.source_commit, expected_head=payload.expected_head,
            activation_digest=digest(a), pr_number=payload.pr_number, review_id=payload.review_id))
        require(proof.get('job_id') == job_id and proof.get('expected_head') == payload.expected_head
                and proof.get('activation_digest') == digest(a)
                and proof.get('report', {}).get('diff_hash') == result.get('diff', {}).get('diff_hash'),
                'pcp_local_review_proof_changed')
        result['review'] = {'verdict': 'pass', 'source': 'authenticated_github_pm',
                            'review_id': payload.review_id, 'report': proof['report']}
        result['delivery_finalized'] = True
        result['delivery']['ci'] = proof['ci']
        result['delivery']['state'] = 'ci_success'
        result['acceptance_phase'] = 'pm_review_accepted'
        candidate = {**row, 'status': 'completed', 'result': result}
        eligibility = evaluate_standalone_pm_merge(project=project, job=candidate,
            pr=proof['pr'], pr_number=payload.pr_number, current_ci=proof['ci'])
        require(not eligibility.blockers, 'pcp_local_pm_merge_gates_not_satisfied')
        result['pm_merge_eligibility'] = json.loads(json.dumps(eligibility.model_dump()))
        from .pcp_local_recovery import reconcile_commit
        from types import SimpleNamespace
        require(reconcile_commit(row, SimpleNamespace(base_sha=payload.source_commit))
                == payload.expected_head, 'pcp_local_review_commit_changed')
        readers.authority()  # Recheck expiry/revocation after Git, before the transaction.
        if dry_run:
            return dict(job_id=job_id, status='ready_for_pm_finalization', merged=False,
                        pm_merge_eligibility=result['pm_merge_eligibility'])
        with self.storage.connect() as conn:
            from .pcp_local_recovery import project_lock
            project_lock(conn)
            current = conn.execute('SELECT * FROM cp_jobs WHERE id=%s FOR UPDATE', (job_id,)).fetchone()
            require(current == row, 'pcp_local_review_race')
            receipt_current = conn.execute('SELECT * FROM cp_pcp_local_source_receipts WHERE job_id=%s AND project_id=%s FOR UPDATE',
                                           (job_id, PROJECT_ID)).fetchone()
            lease_current = conn.execute('SELECT * FROM cp_project_leases WHERE owner_job_id=%s AND project_id=%s FOR UPDATE',
                                         (job_id, PROJECT_ID)).fetchone()
            require(receipt_current == receipt_before, 'pcp_local_review_receipt_changed')
            require(lease_current == lease_before, 'pcp_local_review_lease_changed')
            receipt = conn.execute("UPDATE cp_pcp_local_source_receipts SET state='delivered', "
                "generation=generation+1, updated_at=NOW() WHERE repository=%s AND project_id=%s "
                "AND issue_number=%s AND job_id=%s AND state='running' AND generation=2 "
                "AND body_sha256=%s AND base_sha=%s AND baseline_revision=%s RETURNING job_id",
                (REPOSITORY, PROJECT_ID, a['issue_number'], job_id, a['body_sha256'], a['base_sha'], a['baseline_revision'])).fetchone()
            require(receipt is not None, 'pcp_local_review_receipt_changed')
            lease = conn.execute("UPDATE cp_project_leases SET state='released', updated_at=NOW() "
                "WHERE project_id=%s AND owner_job_id=%s AND state='active' AND generation=%s RETURNING project_id",
                (PROJECT_ID, job_id, row['checkpoint']['pcp_local_execution']['lease_generation'])).fetchone()
            require(lease is not None, 'pcp_local_review_lease_changed')
            conn.execute("UPDATE cp_jobs SET status='completed', result=%s::jsonb, error=NULL, updated_at=NOW() WHERE id=%s",
                         (json.dumps(result), job_id))
            conn.commit()
        return dict(job_id=job_id, status='completed', merged=False,
                    pm_merge_eligibility=result['pm_merge_eligibility'])

    async def deliver_pcp_local(self, job_id, readers, task):
        """Existing publisher/CI machinery; independent PM owns final acceptance."""
        from .pcp_local_worker_loop import TrustedReaders
        from .pcp_local_worker_loop import stable_job_id
        from .pcp_local_task_queue import require, PROJECT_ID, REPOSITORY, TaskStop
        require(type(readers) is TrustedReaders and readers.engine is self
                and stable_job_id(task) == job_id, "pcp_local_delivery_admission_required")
        await readers.refresh_delivery(task)
        row = self.storage.get(job_id)
        result = deepcopy(row.get("result") or {})
        require((result.get('delivery') or {}).get('state') != 'ci_success'
                and result.get('delivery_finalized') is not True,
                'pcp_local_delivery_already_complete')
        checkpoint = deepcopy(row["checkpoint"])
        proof = checkpoint.get("pcp_local_execution") or {}
        verification = result.get("verification") or {}
        require(row["project_id"] == PROJECT_ID and row["source_commit"] == task.base_sha
                and proof.get("state") == "verified" and proof.get("commit") == result.get("commit")
                and verification.get("passed") is True and verification.get("test_runs", 0) > 0,
                "pcp_local_unverified_delivery_denied")
        project, _ = readers.authority()
        rights = project["autonomy"]
        require(all(rights.get(k) is True for k in ("allow_commit", "allow_push_ai_branch", "allow_create_pr"))
                and rights.get("allow_production_deploy") is False, "pcp_local_delivery_rights_revoked")
        body = pull_request_body(job_id=job_id, branch=row["branch"], commit=result["commit"],
            verification=verification, evaluator=None)
        from .invocation_context import local_invocation_context, ContextCannotProve
        try:
            context = local_invocation_context(row, task, role='reviewer')
        except ContextCannotProve as exc:
            checkpoint['invocation_context_failure'] = {'missing': exc.missing}
            self.storage.update(job_id, checkpoint=checkpoint)
            raise TaskStop('pcp_local_context_cannot_prove') from exc
        checkpoint['review_context'] = context['manifest']
        body += '\n\n' + context['text']
        progress = deepcopy(row.get('progress') or {})
        attempts = int(progress.get('delivery_attempts', 0))
        progress['delivery_attempts'] = attempts + 1
        self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
        try:
            delivery = await deliver_verified_work(ddev=self.ddev, job_id=job_id, project_id=PROJECT_ID,
                workspace=row["workspace"], branch=row["branch"], source_commit=task.base_sha,
                commit=result["commit"], title=row["task"]["title"], body=body,
                permissions={"commit": True, "push_ai_branch": True, "create_pr": True,
                             "auto_merge_low_risk": False, "production_deploy": False},
                max_wait_seconds=max(1, min(900, int(readers.activation['budget']['max_wall_seconds']
                    - float(progress.get('elapsed_minutes', 0)) * 60))),
                reconcile_existing=attempts > 0, required_ci=(REPOSITORY, "tests"))
        except DeliveryError as exc:
            # Publication may already have happened. Retain all metadata so the
            # next delivery-only attempt reconciles remote state before writes.
            result['delivery'] = deepcopy(exc.metadata)
            result['delivery']['uncertain'] = True
            checkpoint['pcp_local_execution']['delivery_uncertain'] = True
            checkpoint['delivery'] = deepcopy(result['delivery'])
            try:
                self.storage.update(job_id, status='blocked', result=result, checkpoint=checkpoint,
                                    error=exc.reason)
            except Exception as secondary:
                exc.add_note('Delivery checkpoint also failed: ' + type(secondary).__name__)
            raise
        result["delivery"] = delivery
        result["acceptance_phase"] = "awaiting_independent_pm_review"
        result["delivery_finalized"] = False
        checkpoint["delivery"] = delivery
        self.storage.update(job_id, status="blocked", result=result, checkpoint=checkpoint,
            error="awaiting_independent_pm_review" if delivery.get("state") == "ci_success"
                  else "pcp_local_hosted_ci_not_passed")

    async def run_job(self, job_id: str) -> None:
        # If Runtime restarted or a delivery dependency failed after local
        # verification/commit, resume the idempotent delivery step instead of
        # spending another model call on already-verified work.
        before = self.storage.get(job_id)
        require_legacy_job(before)
        if before:
            checkpoint = deepcopy(before.get("checkpoint") or {})
            progress = deepcopy(before.get("progress") or {})
            try:
                self._ensure_review_repair_churn_epoch(
                    job_id=job_id,
                    checkpoint=checkpoint,
                    progress=progress,
                )
            except ReviewRepairChurnPaused:
                return
            before = self.storage.get(job_id)
            require_legacy_job(before)
        accepted = self._accepted_result_for_delivery(before) if before else None
        pending_review_repair_record = (
            (before.get("checkpoint") or {}).get("pending_review_repair")
            if before
            else None
        )
        pending_review_repair = isinstance(pending_review_repair_record, dict)
        repaired_result_waiting_for_delivery = bool(
            pending_review_repair
            and accepted
            and str(accepted.get("commit") or "")
            != str(pending_review_repair_record.get("expected_commit") or "")
        )
        recovery = (
            recover_legacy_accepted_result(before)
            if (
                before
                and before.get("status") == "queued"
                and accepted is None
                and not pending_review_repair
            )
            else {"candidate": False, "accepted_result": None, "missing_evidence": []}
        )
        if recovery["candidate"] and recovery["accepted_result"] is None:
            checkpoint = deepcopy(before.get("checkpoint") or {})
            progress = deepcopy(before.get("progress") or {})
            self._block(
                job_id=job_id,
                progress=progress,
                checkpoint=checkpoint,
                reason=LEGACY_RECOVERY_BLOCK_REASON,
                last_failure=(
                    "Legacy delivery acceptance cannot be reconstructed from the "
                    "remaining authoritative durable evidence."
                ),
                delivery=deepcopy(checkpoint.get("delivery") or {}),
                legacy_delivery_recovery={
                    "candidate": True,
                    "missing_evidence": recovery["missing_evidence"],
                    "commit": recovery.get("commit"),
                    "branch": recovery.get("branch"),
                    "prior_block": deepcopy(before.get("result") or {}),
                },
            )
            return
        if repaired_result_waiting_for_delivery:
            self.storage.update(job_id, status="delivering", result=accepted, error=None)
        elif recovery["accepted_result"] is not None:
            accepted = recovery["accepted_result"]
            self.storage.update(job_id, status="delivering", result=accepted, error=None)
        elif (
            before
            and before.get("status") == "queued"
            and accepted
            and not pending_review_repair
            and self._verified_result_needs_delivery(before)
        ):
            self.storage.update(job_id, status="delivering", result=accepted, error=None)
        else:
            await super().run_job(job_id)

        repaired = self.storage.get(job_id)
        if repaired is not None:
            require_legacy_job(repaired)
        if repaired and repaired.get("status") == "delivering":
            repaired_checkpoint = deepcopy(repaired.get("checkpoint") or {})
            pending = repaired_checkpoint.get("pending_review_repair")
            if isinstance(pending, dict):
                repaired_result = deepcopy(repaired.get("result") or {})
                previous_commit = str(pending.get("expected_commit") or "")
                new_commit = str(repaired_result.get("commit") or "")
                request_id = str(pending.get("request_id") or "")
                if not new_commit or new_commit == previous_commit:
                    self._block(
                        job_id=job_id,
                        progress=deepcopy(repaired.get("progress") or {}),
                        checkpoint=repaired_checkpoint,
                        reason="review_repair_missing_new_commit",
                        last_failure=(
                            "PM review repair passed execution gates without producing "
                            "a new commit distinct from the delivered head."
                        ),
                    )
                    return
                active = {
                    "request_id": request_id,
                    "expected_pr_number": int(pending["pr_number"]),
                    "previous_commit": previous_commit,
                    "new_commit": new_commit,
                }
                repaired_checkpoint["active_review_repair"] = active
                repaired_checkpoint.pop("pending_review_repair", None)
                self._update_review_repair_history(
                    repaired_checkpoint,
                    request_id,
                    state="delivering",
                    new_commit=new_commit,
                )
                repaired_result["review_repair"] = deepcopy(active)
                self.storage.update(
                    job_id,
                    checkpoint=repaired_checkpoint,
                    result=repaired_result,
                )

        while True:
            row = self.storage.get(job_id)
            if row is not None:
                require_legacy_job(row)
            if not row or row.get("status") != "delivering":
                return

            result = deepcopy(row.get("result") or {})
            route = result.get("route") or row.get("route") or {}
            strategy = route.get("strategy") or {}
            permissions = strategy.get("permissions") or {}
            commit = str(result.get("commit") or "")
            if not commit:
                checkpoint = deepcopy(row.get("checkpoint") or {})
                progress = deepcopy(row.get("progress") or {})
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="delivery_missing_verified_commit",
                    last_failure="GitHub publishing was allowed but the verified result has no commit.",
                    delivery=result.get("delivery"),
                )
                return

            checkpoint = deepcopy(row.get("checkpoint") or {})
            active_review_repair = checkpoint.get("active_review_repair")
            expected_pr_number = (
                int(active_review_repair["expected_pr_number"])
                if isinstance(active_review_repair, dict)
                else None
            )
            expected_previous_commit = (
                str(active_review_repair["previous_commit"])
                if isinstance(active_review_repair, dict)
                else None
            )
            progress = deepcopy(row.get("progress") or {})
            previous_delivery_attempts = int(progress.get("delivery_attempts", 0))
            progress["delivery_attempts"] = previous_delivery_attempts + 1
            if previous_delivery_attempts > 0:
                progress["delivery_retry_attempts"] = int(
                    progress.get("delivery_retry_attempts", 0)
                ) + 1
                self._runtime_event(
                    job_id,
                    kind="delivery_retry",
                    message="Retrying GitHub delivery/CI observation after an earlier delivery attempt",
                    phase="delivery",
                    status="delivery_retry",
                    output={"attempt": progress["delivery_attempts"]},
                )
                prior_result = (before or {}).get("result") or {}
                if prior_result.get("reason") == "github_ci_infrastructure_failure":
                    progress["infrastructure_retry_attempts"] = int(
                        progress.get("infrastructure_retry_attempts", 0)
                    ) + 1
                    self._runtime_event(
                        job_id,
                        kind="infrastructure_retry",
                        message="Retrying GitHub CI after a pre-run infrastructure/startup failure",
                        phase="delivery",
                        status="infrastructure_retry",
                        output={"attempt": progress["infrastructure_retry_attempts"]},
                    )
            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

            verification = result.get("verification") or {}
            evaluator = result.get("evaluator")
            task = row.get("task") or {}
            title = f"AI: {task.get('title') or 'Automated change'}"
            body = pull_request_body(
                job_id=job_id,
                branch=str(row.get("branch") or result.get("branch") or ""),
                commit=commit,
                verification=verification,
                evaluator=evaluator,
                review=result.get("review"),
            )

            delivery_started = time.monotonic()
            try:
                delivery = await deliver_verified_work(
                    ddev=self.ddev,
                    job_id=job_id,
                    project_id=row["project_id"],
                    workspace=str(row.get("workspace") or ""),
                    branch=str(row.get("branch") or result.get("branch") or ""),
                    source_commit=str(row.get("source_commit") or ""),
                    commit=commit,
                    title=title,
                    body=body,
                    permissions=permissions,
                    max_wait_seconds=self._delivery_wait_seconds(strategy, progress),
                    reconcile_existing=previous_delivery_attempts > 0,
                    expected_pr_number=expected_pr_number,
                    expected_previous_commit=expected_previous_commit,
                    required_ci=required_ci_for_project(row["project_id"]),
                )
            except DeliveryError as exc:
                self._charge_delivery_time(progress, delivery_started)
                checkpoint["delivery"] = exc.metadata
                result["delivery"] = exc.metadata
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason=exc.reason,
                    last_failure=str(exc),
                    delivery=exc.metadata,
                    accepted_result=result,
                )
                return

            self._charge_delivery_time(progress, delivery_started)
            checkpoint["delivery"] = delivery
            result["delivery"] = delivery

            if delivery.get("state") == "ci_failure":
                ci = delivery.get("ci") or {}
                failure_text = str(ci.get("failure_text") or "GitHub CI failed")[-30000:]
                last_failure = f"GitHub CI failed for verified commit {commit}:\n{failure_text}"[-30000:]
                if row.get("project_id") == G1_T02_PROJECT:
                    # T02 permits one seed-parented candidate, not the generic
                    # multi-commit repair loop or a fresh model turn on bad proof.
                    self._block(
                        job_id=job_id, progress=progress, checkpoint=checkpoint,
                        reason="g1_t02_dispatch_ci_failed",
                        last_failure=last_failure, delivery=delivery,
                        accepted_result=result,
                    )
                    return
                if self._ci_failure_class(delivery) == "infrastructure":
                    checkpoint["last_failure"] = last_failure
                    checkpoint["delivery"] = delivery
                    result["delivery_finalized"] = False
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="github_ci_infrastructure_failure",
                        last_failure=last_failure,
                        delivery=delivery,
                        accepted_result=result,
                    )
                    return
                progress["ci_failures"] = int(progress.get("ci_failures", 0)) + 1
                # A real CI failure requires engineering repair; delivery/API
                # observation retries are counted separately above and do not
                # consume this counter.
                progress["repair_iterations"] = int(progress.get("repair_iterations", 0)) + 1
                fp = failure_fingerprint(last_failure)
                progress.setdefault("failure_fingerprints", []).append(fp)
                progress.setdefault("progress_markers", []).append(f"ci:{commit[:12]}:{fp[:12]}")
                checkpoint["last_failure"] = last_failure
                checkpoint["delivery"] = delivery
                result["delivery_finalized"] = False
                self.storage.update(
                    job_id,
                    status="queued",
                    result=result,
                    progress=progress,
                    checkpoint=checkpoint,
                    error=None,
                )
                # Continue in the same worker task. Existing pre-model guards
                # enforce the original repair/model/token/time budgets.
                await super().run_job(job_id)
                continue

            if row.get("project_id") == G1_T02_PROJECT:
                # A verified commit, dispatched workflow and an authenticated
                # CI result still do not constitute a PM acceptance or merge.
                requirement = required_ci_for_project(G1_T02_PROJECT)
                pr = delivery.get("pull_request") or {}
                proof = (delivery.get("ci") or {}).get("g1_t02_dispatch") or {}
                if not (
                    requirement is not None
                    and requirement[1] == G1_T02_DISPATCH_POLICY
                    and isinstance(commit, str)
                    and re.fullmatch(r"[0-9a-f]{40}", commit)
                    and delivery.get("state") == "ci_success"
                    and required_github_actions_pass(
                        delivery.get("ci") or {}, repository=requirement[0],
                        commit=commit, workflow_name=requirement[1],
                    )
                    and type(pr.get("number")) is int and pr["number"] > 0
                    and pr.get("repository") == requirement[0]
                    and pr.get("head") == commit
                    and proof.get("job_id") == job_id
                    and proof.get("branch") == row.get("branch")
                    and row.get("source_commit") == proof.get("source_sha")
                    and pr.get("head_ref") == row.get("branch")
                    and pr.get("base_ref") == "benchmark/g1-codex-smoke-v1"
                    and pr.get("state") == "open"
                    and pr.get("merged") is not True
                ):
                    self._block(
                        job_id=job_id, progress=progress,
                        checkpoint=checkpoint,
                        reason="g1_t02_dispatch_ci_or_pr_unverified",
                        last_failure="T02 requires exact candidate dispatch and PR proof",
                        accepted_result=result,
                        delivery=delivery,
                    )
                    return
                result["acceptance_phase"] = "waiting_pm_review"
                result["delivery_finalized"] = False
                result["verification"] = {
                    **(result.get("verification") or {}),
                    "hosted_ci_passed": True,
                    "hosted_ci_commit": commit,
                }
                checkpoint["acceptance_phase"] = "waiting_pm_review"
                self.storage.update(
                    job_id, status="waiting_human", result=result,
                    progress=progress, checkpoint=checkpoint, error=None,
                )
                return

            if row.get("project_id") == FULLPATH_FIXTURE_PROJECT_ID:
                # Even after hosted CI success, PM exact-HEAD code review is
                # not interchangeable with automated CI. No synthetic user
                # authorization or unconditional terminal "completed".
                pending = ci_passed_awaiting_review(
                    row=row, result=result, progress=progress,
                    checkpoint=checkpoint, delivery=delivery,
                )
                if pending is None:
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="fullpath_hosted_ci_or_pr_provenance_invalid",
                        last_failure=(
                            "Full-path fixture cannot advance without an exact "
                            "GitHub Actions and PR identity match."
                        ),
                        accepted_result=result,
                        delivery=delivery,
                    )
                    return
                result, progress, checkpoint = pending
                checkpoint["last_failure"] = None
                self.storage.update(
                    job_id,
                    status="waiting_human",
                    result=result,
                    progress=progress,
                    checkpoint=checkpoint,
                    error=None,
                )
                return

            result["delivery_finalized"] = True
            checkpoint["last_failure"] = None
            if isinstance(active_review_repair, dict):
                request_id = str(active_review_repair.get("request_id") or "")
                self._update_review_repair_history(
                    checkpoint,
                    request_id,
                    state="completed",
                    new_commit=commit,
                    delivery=delivery,
                )
                archive_review_repair_churn_epoch(
                    checkpoint,
                    request_id,
                    state="completed",
                    completed_at=delivery.get("completed_at"),
                    new_commit=commit,
                )
                checkpoint.pop("active_review_repair", None)
            self.storage.update(
                job_id,
                status="completed",
                result=result,
                progress=progress,
                checkpoint=checkpoint,
                error=None,
            )
            return
