from __future__ import annotations

import hashlib
import json
from typing import Any

from .config import project_config
from .fullpath_fixture_safety import reject_parked_fullpath_side_effects
from .continuity import render_managed_section
from .plan_orchestrator import PlanOrchestrator as CorePlanOrchestrator
from .pm_merge import evaluate_pm_merge
from .pm_merge_audit import PMMergeAuditStore
from .pm_late_review import LateReviewService
from .pm_chat_review import PMChatReviewService


class PlanOrchestrator(CorePlanOrchestrator):
    """Add constrained PM-controlled PR merge after the core delivery gate.

    Core orchestration remains authoritative for launching jobs, waiting on human
    decisions and only advancing dependencies after a WorkOrder is marked
    completed. This layer may mark an awaiting-merge WorkOrder completed only
    after a fresh GitHub read confirms the exact PR was merged.
    """

    def __init__(self, storage: Any, engine: Any, *, store: Any | None = None, progress_handoffs: Any = None) -> None:
        super().__init__(storage, engine, store=store, progress_handoffs=progress_handoffs)
        self.merge_audit = PMMergeAuditStore(storage)
        self.late_reviews = LateReviewService(storage, engine, self)
        self.pm_chat_reviews = PMChatReviewService(storage, engine, self)

    @staticmethod
    def _project_merge_config(project_id: str) -> dict[str, Any]:
        """Resolve project merge policy without turning config gaps into mutation authority.

        Older tests/integrations can carry an orchestration project that is not in
        the local projects file. That state was historically a manual merge gate.
        Preserve it and fail closed instead of crashing or inventing auto-merge
        permission.
        """
        try:
            return project_config(project_id)
        except (KeyError, ValueError):
            return {
                "base_branch": "main",
                "autonomy": {
                    "allow_pm_merge": False,
                    "allow_auto_merge_low_risk": False,
                },
            }

    async def start(self) -> None:
        reject_parked_fullpath_side_effects()
        self.merge_audit.ensure()
        self.late_reviews.store.ensure()
        # Runtime startup follows RuntimeEngine.start(), which cancels host
        # orphan agents. One former 'claimed' attempt may have reached a model:
        # record uncertainty without repeating it or forever blocking Guardian.
        self.late_reviews.store.reconcile_orphan_claims()
        await super().start()

    async def stop(self) -> None:
        await self.late_reviews.stop()
        await super().stop()

    async def _recover_uncertain_merge(
        self,
        *,
        plan: dict[str, Any],
        tracked: dict[str, Any],
        job: dict[str, Any],
        audit: dict[str, Any],
    ) -> bool:
        """Resolve an approved-without-result audit by observation only.

        Reissuing the GitHub mutation would be a replay. If GitHub has already
        merged the exact PR, record that observation and allow core reconciliation
        to complete the WorkOrder. Otherwise block for explicit investigation.
        """
        plan_id = str(plan["plan_id"])
        work_order_id = str(tracked["work_order_id"])
        expected_head = str(audit["expected_head"])
        pr_number = int(tracked["pr_number"])
        pr = await self.engine.ddev.github_pull_request(
            project_id=str(plan["project_id"]),
            pr_number=pr_number,
        )
        if bool(pr.get("merged")) and str(pr.get("head") or "") == expected_head:
            self.merge_audit.finish(
                plan_id=plan_id,
                work_order_id=work_order_id,
                expected_head=expected_head,
                status="observed_merged",
                result={"recovered_by_observation": True, "pr": pr},
            )
            self._record_merge_continuity(plan, job, pr)
            return True

        self.merge_audit.finish(
            plan_id=plan_id,
            work_order_id=work_order_id,
            expected_head=expected_head,
            status="uncertain",
            result={"reason": "approved_merge_has_no_confirmed_result", "pr": pr},
        )
        self._block_tracked(plan, tracked, "uncertain_merge_attempt")
        return False

    async def _reconcile_plan(self, plan: dict[str, Any]) -> None:
        plan_id = str(plan["plan_id"])

        # Recover any prior approved merge attempt before core can reinterpret the
        # WorkOrder. Recovery is read-only: never replay the mutation.
        for tracked_raw in self.store.work_orders(plan_id):
            tracked = dict(tracked_raw)
            if str(tracked.get("lifecycle") or "active") != "active":
                continue
            if str(tracked.get("state") or "") != "awaiting_merge":
                continue
            job_id = str(tracked.get("job_id") or "")
            pr_number = tracked.get("pr_number")
            if not job_id or not pr_number:
                continue
            job_raw = self.storage.get(job_id)
            if not job_raw:
                continue
            job = dict(job_raw)
            expected_head = str((job.get("result") or {}).get("commit") or "")
            if not expected_head:
                continue
            audit = self.merge_audit.get(
                plan_id=plan_id,
                work_order_id=str(tracked["work_order_id"]),
                expected_head=expected_head,
            )
            if audit and str(audit.get("status") or "") == "approved":
                recovered = await self._recover_uncertain_merge(
                    plan=plan,
                    tracked=tracked,
                    job=job,
                    audit=dict(audit),
                )
                if not recovered:
                    return

        # Preserve core behavior first: observe externally/manual merged PRs,
        # closed PRs, decision boundaries and completed jobs.
        await super()._reconcile_plan(plan)

        orchestration = self.store.orchestration(plan_id) or {}
        if str(orchestration.get("status") or "") == "waiting_human":
            return

        merged_any = False
        continuity_apps: list[dict[str, Any]] = []
        for tracked_raw in self.store.work_orders(plan_id):
            tracked = dict(tracked_raw)
            if str(tracked.get("lifecycle") or "active") != "active":
                continue
            if str(tracked.get("state") or "") != "awaiting_merge":
                continue
            detail = dict(tracked.get("detail") or {})
            prior_pm_merge = dict(detail.get("pm_merge") or {})
            # A protected merge that was routed to explicit owner/manual review is
            # intentionally stable until GitHub observes the owner merge. Core ran
            # first above, so a newly merged PR would already be completed.
            if prior_pm_merge.get("owner_required"):
                continue

            job_id = str(tracked.get("job_id") or "")
            pr_number = tracked.get("pr_number")
            if not job_id or not pr_number:
                self._block_tracked(plan, tracked, "pm_merge_missing_job_or_pr")
                return
            job_raw = self.storage.get(job_id)
            if not job_raw:
                self._block_tracked(plan, tracked, "pm_merge_job_missing")
                return
            job = dict(job_raw)
            pr = await self.engine.ddev.github_pull_request(
                project_id=str(plan["project_id"]),
                pr_number=int(pr_number),
            )
            current_ci = None
            result = dict(job.get("result") or {})
            delivery = dict(result.get("delivery") or {})
            persisted_ci = dict(delivery.get("ci") or {})
            if (
                delivery.get("state") == "ci_none"
                and persisted_ci.get("state") == "none"
            ):
                expected_head = str(result.get("commit") or "").strip()
                if expected_head:
                    try:
                        current_ci = await self.engine.ddev.github_ci(
                            project_id=str(plan["project_id"]),
                            commit=expected_head,
                        )
                    except Exception:
                        # A read failure grants no merge authority. Preserve the
                        # merge gate so a later poll may obtain current CI.
                        continue
                    if str(current_ci.get("state") or "") in {"none", "pending"}:
                        # CI may have appeared after the delivery discovery
                        # window. Do not turn an incomplete observation into a
                        # permanent orchestration block.
                        continue
            late_review_proof = None
            release = detail.get("late_review_release")
            if isinstance(release, dict):
                expected_head = str(result.get("commit") or "")
                if release.get("head") != expected_head:
                    self._block_tracked(plan, tracked, "late_review_release_head_mismatch")
                    return
                try:
                    late_review_proof = self.late_reviews.trusted_proof(
                        plan=plan, tracked=tracked, job=job,
                        attestation_id=int(release["attestation_id"]),
                        checkpoint_id=int(release["checkpoint_id"]),
                        checkpoint_key=str(release["checkpoint_key"]),
                    )
                    if late_review_proof is None:
                        raise RuntimeError("Missing late-review proof")
                    # Late recovery always uses a fresh exact-head CI observation,
                    # even if persisted delivery already recorded CI success.
                    current_ci = await self.engine.ddev.github_ci(
                        project_id=str(plan["project_id"]), commit=expected_head,
                    )
                    if (
                        current_ci.get("state") != "success"
                        or current_ci.get("commit") != expected_head
                    ):
                        raise RuntimeError("Late-review fresh exact-head CI is not successful")
                except Exception:
                    self._block_tracked(plan, tracked, "late_review_attestation_or_ci_invalid")
                    return
            # Owner-delegated PM-chat review has separate provenance and a
            # separate merge-gate proof. Never reclassify it as an independent
            # model-provider review or accept both modes simultaneously.
            pm_chat_review_proof = None
            manual_release = detail.get("pm_chat_review_release")
            if manual_release is not None:
                if not isinstance(manual_release, dict) or release is not None:
                    self._block_tracked(plan, tracked, "pm_chat_review_conflicting_release_modes")
                    return
                expected_head = str(result.get("commit") or "")
                if (
                    manual_release.get("head") != expected_head
                    or manual_release.get("review_mode") != "pm_chat_manual_review"
                ):
                    self._block_tracked(plan, tracked, "pm_chat_review_release_head_or_mode_mismatch")
                    return
                try:
                    pm_chat_review_proof = self.pm_chat_reviews.trusted_proof(
                        plan=plan, tracked=tracked, job=job,
                        attestation_id=int(manual_release["attestation_id"]),
                        checkpoint_id=int(manual_release["checkpoint_id"]),
                        checkpoint_key=str(manual_release["checkpoint_key"]),
                    )
                    if pm_chat_review_proof is None:
                        raise RuntimeError("Missing owner-delegated PM-chat proof")
                    await self.pm_chat_reviews.verify_live(
                        pm_chat_review_proof, str(pr.get("repository") or ""),
                    )
                    current_ci = await self.engine.ddev.github_ci(
                        project_id=str(plan["project_id"]), commit=expected_head,
                    )
                    if (
                        current_ci.get("state") != "success"
                        or current_ci.get("commit") != expected_head
                    ):
                        raise RuntimeError("PM-chat review fresh exact-head CI not successful")
                except Exception:
                    self._block_tracked(plan, tracked, "pm_chat_review_attestation_or_ci_invalid")
                    return
            project = self._project_merge_config(str(plan["project_id"]))
            eligibility = evaluate_pm_merge(
                project=project,
                plan=plan,
                tracked=tracked,
                job=job,
                pr=pr,
                current_ci=current_ci,
                late_review_proof=late_review_proof,
                pm_chat_review_proof=pm_chat_review_proof,
            )
            decision = eligibility.model_dump()

            # Project-level opt-out intentionally preserves the pre-#98 manual
            # merge gate and its existing owner notification path. Avoid rewriting
            # unchanged detail every polling cycle.
            if eligibility.manual_only:
                manual = {
                    "eligible": False,
                    "manual_only": True,
                    "owner_required": False,
                    "blockers": list(eligibility.blockers),
                }
                if prior_pm_merge != manual:
                    detail["pm_merge"] = manual
                    self.store.update_work_order(
                        plan_id,
                        str(tracked["work_order_id"]),
                        detail=detail,
                    )
                continue

            if eligibility.requires_human:
                decision["owner_required"] = True
                detail["pm_merge"] = decision
                detail["reason"] = "pm_merge_owner_review_required"
                # Keep awaiting_merge as the stable owner/manual merge gate. A
                # completed coding job cannot meaningfully resume a Runtime human
                # decision; the owner can review/merge the PR, and core will
                # observe that merge before dependencies advance.
                self.store.update_work_order(
                    plan_id,
                    str(tracked["work_order_id"]),
                    detail=detail,
                )
                continue

            if not eligibility.eligible:
                reason = eligibility.blockers[0] if eligibility.blockers else "pm_merge_ineligible"
                self._block_tracked(plan, tracked, f"pm_merge_ineligible:{reason}")
                return

            assert eligibility.expected_head
            assert eligibility.source_commit
            assert eligibility.pr_number
            audit = self.merge_audit.approve(
                plan_id=plan_id,
                work_order_id=str(tracked["work_order_id"]),
                job_id=job_id,
                project_id=str(plan["project_id"]),
                pr_number=eligibility.pr_number,
                expected_head=eligibility.expected_head,
                source_commit=eligibility.source_commit,
                decision=decision,
            )
            if not bool(audit.get("created")):
                self._block_tracked(plan, tracked, "pm_merge_replay_rejected")
                return

            try:
                merge_result = await self.engine.ddev.github_merge_pull_request(
                    job_id=job_id,
                    project_id=str(plan["project_id"]),
                    pr_number=eligibility.pr_number,
                    branch=str(job.get("branch") or ""),
                    source_commit=eligibility.source_commit,
                    expected_head=eligibility.expected_head,
                )
            except Exception as exc:
                # The request may have reached GitHub even if Runtime did not get
                # a response. Record uncertainty and never replay automatically.
                self.merge_audit.finish(
                    plan_id=plan_id,
                    work_order_id=str(tracked["work_order_id"]),
                    expected_head=eligibility.expected_head,
                    status="uncertain",
                    result={"error": f"{type(exc).__name__}: {exc}"[-12000:]},
                )
                self._block_tracked(plan, tracked, "uncertain_merge_attempt")
                return

            confirmed = await self.engine.ddev.github_pull_request(
                project_id=str(plan["project_id"]),
                pr_number=eligibility.pr_number,
            )
            if (
                not bool(confirmed.get("merged"))
                or str(confirmed.get("head") or "") != eligibility.expected_head
                or not confirmed.get("merge_commit_sha")
            ):
                self.merge_audit.finish(
                    plan_id=plan_id,
                    work_order_id=str(tracked["work_order_id"]),
                    expected_head=eligibility.expected_head,
                    status="uncertain",
                    result={
                        "reason": "merge_not_confirmed",
                        "merge_result": merge_result,
                        "confirmed_pr": confirmed,
                    },
                )
                self._block_tracked(plan, tracked, "uncertain_merge_attempt")
                return

            self.merge_audit.finish(
                plan_id=plan_id,
                work_order_id=str(tracked["work_order_id"]),
                expected_head=eligibility.expected_head,
                status="merged",
                result={"merge_result": merge_result, "confirmed_pr": confirmed},
            )
            detail = dict(tracked.get("detail") or {})
            detail.update(
                {
                    "pm_merge": decision,
                    "pm_merge_result": merge_result,
                    "merged_at": confirmed.get("merged_at"),
                    "merge_commit_sha": confirmed.get("merge_commit_sha"),
                }
            )
            self._checkpoint_transition(
                tracked, kind="merged", job=job, pr=confirmed,
                state="completed",
                detail=detail,
            )
            proposal = self._record_merge_continuity(plan, job, confirmed)
            if proposal:
                continuity_apps.append(proposal)
            merged_any = True

        if merged_any:
            # Recompute plan completion/dependency state only after the fresh
            # GitHub confirmation above. This may make the next WorkOrder launch
            # eligible later in the same orchestrator tick.
            await super()._reconcile_plan(plan)

            # Continuity publication happens only after durable orchestration state
            # has reconciled. It is advisory: failure may leave a diagnostic PR or
            # persisted proposal, but it cannot roll back an engineering merge.
            for proposal in continuity_apps:
                await self._apply_merge_continuity(proposal)

    def _record_merge_continuity(
        self,
        plan: dict[str, Any],
        job: dict[str, Any],
        pr: dict[str, Any],
    ) -> dict[str, Any] | None:
        recorder = getattr(self.storage, "record_external_continuity", None)
        if not callable(recorder):
            return None
        try:
            proposal = recorder(
                project_id=str(plan["project_id"]),
                event_type="pr_merged",
                job_id=str(job.get("id") or "") or None,
                payload={
                    "pr_number": pr.get("number"),
                    "merge_commit_sha": pr.get("merge_commit_sha"),
                    "merged_at": pr.get("merged_at"),
                    "authority": "pm_controlled_merge",
                },
            )
            return dict(proposal) if isinstance(proposal, dict) else None
        except Exception:
            # Continuity is advisory evidence. A continuity persistence failure
            # must not invalidate a GitHub merge already confirmed as durable.
            return None

    async def _apply_merge_continuity(self, proposal: dict[str, Any]) -> None:
        if str(proposal.get("event_type") or "") != "pr_merged":
            return
        try:
            encoded = json.dumps(proposal, sort_keys=True, separators=(",", ":"), default=str)
            continuity_key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            await self.engine.ddev.apply_continuity(
                continuity_key=continuity_key,
                event_type="pr_merged",
                project_id=str(proposal.get("project_id") or ""),
                managed_section=render_managed_section(proposal),
            )
        except Exception:
            # Git continuity is deliberately downstream/advisory. The persisted
            # proposal remains authoritative evidence for diagnosis/retry and an
            # already-confirmed engineering merge must never be invalidated here.
            return


__all__ = ["PlanOrchestrator"]
