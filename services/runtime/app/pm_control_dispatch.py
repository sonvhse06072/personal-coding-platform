from __future__ import annotations

from typing import Any

from .baseline import resolve_project_baseline
from .config import project_config
from .intake_policy import classify_intake
from .pm_control import PMControlEnvelope
from .pm_diagnostics import PMDiagnosticsService
from .pm_merge import evaluate_standalone_pm_merge
from .schemas import JobCreateRequest, TaskInput


_RECHECK_ACTION_TYPES = frozenset({"recheck_orchestration", "recheck_ci"})
_RESUME_ACTION_TYPES = frozenset({
    "pm_scope_reassess",
    "resume_same",
    "retry_delivery",
})


class PMControlDispatcher:
    """Dispatch already-authenticated GitHub PM controls through Runtime gates."""

    def __init__(self, storage: Any, engine: Any, orchestrator: Any) -> None:
        self.storage = storage
        self.engine = engine
        self.orchestrator = orchestrator
        self.controls = orchestrator.controls
        self.diagnostics = PMDiagnosticsService(storage, engine, orchestrator)

    def _job(self, envelope: PMControlEnvelope) -> dict[str, Any]:
        job_id = str(envelope.job_id or "")
        row = self.storage.get(job_id)
        if row is None:
            raise RuntimeError("Unknown job")
        job = dict(row)
        if str(job.get("project_id") or "") != envelope.project_id:
            raise RuntimeError("PM control job project identity mismatch")
        return job

    def _plan(self, envelope: PMControlEnvelope) -> dict[str, Any]:
        plan_id = str(envelope.plan_id or "")
        plan = self.orchestrator.store.orchestration(plan_id)
        if plan is None:
            raise RuntimeError("Unknown orchestration plan")
        plan = dict(plan)
        if str(plan.get("project_id") or "") != envelope.project_id:
            raise RuntimeError("PM control plan project identity mismatch")
        return plan

    async def dispatch(
        self,
        envelope: PMControlEnvelope,
        *,
        comment_id: int,
        issue_number: int,
    ) -> tuple[str, dict[str, Any]]:
        action = envelope.action

        if action == "request_diagnostics":
            result = await self.diagnostics.collect_and_publish(
                project_id=envelope.project_id,
                issue_number=issue_number,
                control_comment_id=comment_id,
                job_id=envelope.job_id,
                plan_id=envelope.plan_id,
                collectors=list(envelope.diagnostic_collectors),
            )
            return (
                "executed",
                {
                    "status": "executed",
                    "action": action,
                    **result,
                },
            )

        if action == "direct_intake":
            project = project_config(envelope.project_id)
            runtime_cfg = dict(project.get("runtime") or {})
            if (
                str(runtime_cfg.get("workspace_mode") or "") != "direct"
                or runtime_cfg.get("exclusive_project_lease") is not True
            ):
                raise RuntimeError(
                    "Remote direct intake requires exclusive direct workspace mode"
                )

            baseline = resolve_project_baseline(
                envelope.project_id,
                envelope.baseline_revision,
            )
            if baseline is None:
                raise RuntimeError(
                    "Remote direct intake requires an approved ProjectBaseline"
                )
            decision = classify_intake(
                bounded_direct=True,
                semantic=envelope.intake_semantic,
                repo_hints=envelope.intake_repo_hints,
            )
            if (
                decision.mode != "direct"
                or decision.bounded_direct is not True
                or decision.decomposition_required
            ):
                raise RuntimeError(
                    "Remote direct intake classifier requires planning; "
                    "no source sync or job creation performed"
                )

            issue = await self.engine.ddev.github_issue(
                project_id=envelope.project_id,
                issue_number=issue_number,
            )
            if bool(issue.get("is_pull_request")):
                raise RuntimeError(
                    "Remote direct intake must target a GitHub issue, not PR"
                )
            if str(issue.get("state") or "") != "open":
                raise RuntimeError("Remote direct intake issue is not open")
            repository = str(issue.get("repository") or "").strip()
            if not repository:
                raise RuntimeError("Remote direct intake issue repository missing")

            lease = self.storage.project_lease(envelope.project_id)
            if lease and str(lease.get("state") or "") == "active":
                raise RuntimeError(
                    "Remote direct intake blocked by active project lease"
                )

            sync = await self.engine.ddev.sync_direct_base(
                project_id=envelope.project_id,
                expected_remote_head=str(envelope.expected_remote_main_sha),
            )
            if (
                str(sync.get("head") or "")
                != str(envelope.expected_remote_main_sha)
                or sync.get("clean") is not True
            ):
                raise RuntimeError(
                    "Remote direct intake source-sync postcondition mismatch"
                )

            request = JobCreateRequest(
                project_id=envelope.project_id,
                task=TaskInput(
                    title=str(issue.get("title") or ""),
                    description=str(issue.get("body") or ""),
                    semantic=envelope.intake_semantic,
                ),
                source_commit=str(envelope.expected_remote_main_sha),
                baseline_revision=baseline.revision,
                repo_hints=envelope.intake_repo_hints,
                provider_state={},
                auto_run=True,
            )
            job_id = self.engine.create_job(
                request.model_dump(mode="json"),
                _intake_decision=decision,
                _remote_binding={
                    "transport": "github_pm_control",
                    "repository": repository,
                    "issue_number": int(issue_number),
                    "control_comment_id": int(comment_id),
                },
            )
            await self.engine.enqueue(job_id)
            row = self.storage.get(job_id)
            if row is None:
                raise RuntimeError("Remote direct intake job disappeared")
            return (
                "executed",
                {
                    "status": "executed",
                    "action": action,
                    "job_id": job_id,
                    "job_status": row.get("status"),
                    "source_commit": row.get("source_commit"),
                    "baseline_revision": baseline.revision,
                    "classification": decision.model_dump(mode="json"),
                    "source_sync": {
                        "head": sync.get("head"),
                        "fast_forwarded": sync.get("fast_forwarded"),
                    },
                },
            )

        if action == "resolve_job_decision":
            job = self._job(envelope)
            row = await self.engine.resolve_human_decision(
                str(envelope.job_id),
                action=str(envelope.decision),
                note=envelope.note or (
                    f"Resolved by GitHub PM control comment {comment_id}"
                ),
                expected_decision_key=str(envelope.decision_key),
            )
            await self.orchestrator.tick()
            return (
                "executed",
                {
                    "status": "executed",
                    "action": action,
                    "job_id": row.get("id"),
                    "job_status": row.get("status"),
                    "source_commit": job.get("source_commit"),
                },
            )

        if action == "review_repair":
            self._job(envelope)
            row = await self.engine.request_review_repair(
                str(envelope.job_id),
                expected_commit=str(envelope.expected_commit),
                finding=str(envelope.finding),
                evidence={
                    "source": "github_pm_control",
                    "comment_id": comment_id,
                    "issue_number": issue_number,
                },
                references=list(envelope.references),
            )
            return (
                "executed",
                {
                    "status": "executed",
                    "action": action,
                    "job_id": row.get("id"),
                    "job_status": row.get("status"),
                },
            )

        if action in {"recheck_blocker", "resume_same_job"}:
            self._job(envelope)
            allowed = (
                _RECHECK_ACTION_TYPES
                if action == "recheck_blocker"
                else _RESUME_ACTION_TYPES
            )
            if envelope.control_action_id:
                control_action = self.controls.get_action(
                    str(envelope.control_action_id)
                )
                if control_action is None:
                    raise RuntimeError("Unknown durable control action")
                underlying = str(control_action.get("action_type") or "")
                if underlying not in allowed:
                    raise RuntimeError(
                        f"{action} cannot execute action_type={underlying}"
                    )
                result = await self.controls.execute_remote(
                    str(envelope.control_action_id),
                    expected_job_id=str(envelope.job_id),
                    expected_generation=str(envelope.blocker_generation),
                )
                control_identity = {
                    "control_action_id": envelope.control_action_id,
                }
            else:
                underlying = str(envelope.recovery_action_type or "")
                if underlying not in allowed:
                    raise RuntimeError(
                        f"{action} cannot execute standalone action_type={underlying}"
                    )
                result = await self.controls.execute_standalone_remote(
                    str(envelope.job_id),
                    expected_generation=str(envelope.blocker_generation),
                    action_type=underlying,
                )
                control_identity = {
                    "recovery_action_type": underlying,
                }
            return (
                "executed",
                {
                    "status": "executed",
                    "action": action,
                    "underlying_action_type": underlying,
                    **control_identity,
                    "result": result,
                },
            )

        if action == "continue_supervised_plan":
            self._plan(envelope)
            result = await self.orchestrator.continue_plan(
                plan_id=str(envelope.plan_id),
                generation=int(envelope.generation),
                continuation_key=str(envelope.continuation_key),
                checkpoint_id=int(envelope.checkpoint_id),
                checkpoint_key=str(envelope.checkpoint_key),
                ready_work_order_ids=list(envelope.ready_work_order_ids),
            )
            return (
                "executed",
                {
                    "status": "executed",
                    "action": action,
                    "plan_id": envelope.plan_id,
                    "generation": envelope.generation,
                    "result": result,
                },
            )

        if action == "merge_standalone_job":
            job = self._job(envelope)
            result = dict(job.get("result") or {})
            verified_commit = str(result.get("commit") or "")
            if str(job.get("source_commit") or "") != str(envelope.source_commit):
                raise RuntimeError("Standalone merge source commit mismatch")
            if verified_commit != str(envelope.expected_commit):
                raise RuntimeError("Standalone merge verified commit mismatch")
            if verified_commit != str(envelope.expected_head):
                raise RuntimeError("Standalone merge expected head mismatch")
            if str(job.get("branch") or "") != str(envelope.branch):
                raise RuntimeError("Standalone merge branch mismatch")

            project = project_config(envelope.project_id)
            expected_base = str(project.get("base_branch") or "main")
            if expected_base != str(envelope.base_branch):
                raise RuntimeError("Standalone merge base branch mismatch")

            pr = await self.engine.ddev.github_pull_request(
                project_id=envelope.project_id,
                pr_number=int(envelope.pr_number),
            )
            current_ci = await self.engine.ddev.github_ci(
                project_id=envelope.project_id,
                commit=verified_commit,
            )
            eligibility = evaluate_standalone_pm_merge(
                project=project,
                job=job,
                pr=pr,
                pr_number=int(envelope.pr_number),
                current_ci=current_ci,
            )
            if not eligibility.eligible:
                category = "human" if eligibility.requires_human else "policy"
                raise RuntimeError(
                    f"Standalone PM merge blocked ({category}): "
                    + ",".join(eligibility.blockers)
                )

            try:
                merge_result = await self.engine.ddev.github_merge_pull_request(
                    job_id=str(envelope.job_id),
                    project_id=envelope.project_id,
                    pr_number=int(envelope.pr_number),
                    branch=str(envelope.branch),
                    source_commit=str(eligibility.source_commit),
                    expected_head=str(eligibility.expected_head),
                )
            except Exception as exc:
                return (
                    "uncertain",
                    {
                        "status": "uncertain",
                        "action": action,
                        "job_id": envelope.job_id,
                        "pr_number": envelope.pr_number,
                        "expected_head": eligibility.expected_head,
                        "error_type": type(exc).__name__,
                        "message": (
                            "Merge mutation may have reached GitHub; "
                            "automatic replay is forbidden."
                        ),
                    },
                )

            confirmed = await self.engine.ddev.github_pull_request(
                project_id=envelope.project_id,
                pr_number=int(envelope.pr_number),
            )
            if (
                not bool(confirmed.get("merged"))
                or str(confirmed.get("head") or "")
                != str(eligibility.expected_head)
                or not confirmed.get("merge_commit_sha")
            ):
                return (
                    "uncertain",
                    {
                        "status": "uncertain",
                        "action": action,
                        "job_id": envelope.job_id,
                        "pr_number": envelope.pr_number,
                        "expected_head": eligibility.expected_head,
                        "merge_result": merge_result,
                        "message": "GitHub merge postcondition was not confirmed.",
                    },
                )
            return (
                "executed",
                {
                    "status": "executed",
                    "action": action,
                    "job_id": envelope.job_id,
                    "pr_number": envelope.pr_number,
                    "expected_head": eligibility.expected_head,
                    "merge_commit_sha": confirmed.get("merge_commit_sha"),
                    "review_reference": envelope.review_reference,
                    "eligibility": eligibility.model_dump(),
                },
            )

        raise RuntimeError(f"Unsupported PM control action: {action}")
