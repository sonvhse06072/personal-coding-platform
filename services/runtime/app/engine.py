"""Governance-aware facade for the checkpointed Runtime engine.

The implementation remains split into engine_core (lifecycle/state transitions),
engine_execution (coding/verification loop), and engine_delivery (bounded GitHub
branch/PR/CI delivery). This facade owns project-governance metadata that must be
validated and pinned atomically when a job row is first created.
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from .baseline import resolve_project_baseline
from .config import project_config
from .engine_delivery import RuntimeEngine as _RuntimeEngine
from .intake_policy import IntakeDecision
from .model_capabilities import next_supported_effort
from .repo import diff_state
from .preview import ProjectPreviewManager
from .review_repair_churn import EPOCH_KEY as REVIEW_REPAIR_CHURN_EPOCH_KEY
from .review_repair_churn import INITIALIZED_KEY as REVIEW_REPAIR_CHURN_INITIALIZED_KEY
from .review_repair_churn import new_epoch as new_review_repair_churn_epoch
from .shell import CommandTimeoutError
from .state import (
    checkpoint_from_row,
    clear_routing_choices_for_resume,
    clear_transient_provider_failures,
    set_failure_context,
)
from .storage import now
from .work_order_checkpoints import launch_identity, orchestrator_launch
from .work_order import (
    WorkOrderPolicyError,
    apply_work_order_budget,
    canonical_task_from_work_order,
    rehydrate_task_from_work_order,
    validate_work_order_against_baseline,
    work_order_snapshot,
)


_OWNER_BUDGET_HARD_MAX = {
    "max_model_calls": 100,
    "max_tool_calls": 500,
    "max_test_runs": 100,
    "max_wall_time_minutes": 240,
    "max_repair_iterations": 20,
    "max_iterations": 30,
}
_AGENT_TIMEOUT_CAP_BY_STATUS = {
    "planning": 1800,
    "executing": 2400,
    "evaluating": 1200,
}


def _apply_owner_budget_authorizations(
    route: dict[str, Any], checkpoint: dict[str, Any]
) -> dict[str, Any]:
    """Overlay explicit owner extensions after normal Router/WorkOrder ceilings.

    The WorkOrder remains immutable. Only audited Telegram authorizations created
    by Runtime may raise a named effective limit, and platform hard maxima still
    apply. This makes an approved extension survive later provider reroutes.
    """
    updated = deepcopy(route)
    strategy = updated.get("strategy") or {}
    budget = dict(strategy.get("budget") or {})
    for authorization in checkpoint.get("budget_authorizations") or []:
        if not isinstance(authorization, dict):
            continue
        if authorization.get("channel") != "telegram" or not authorization.get("action_id"):
            continue
        dimension = str(authorization.get("dimension") or "")
        hard_max = _OWNER_BUDGET_HARD_MAX.get(dimension)
        if hard_max is None or dimension not in budget:
            continue
        try:
            previous_limit = float(authorization["previous_limit"])
            new_limit = float(authorization["new_limit"])
            current = float(budget[dimension])
        except (KeyError, TypeError, ValueError):
            continue
        if new_limit <= previous_limit:
            continue
        authorized = min(new_limit, float(hard_max))
        effective = max(current, authorized)
        if dimension == "max_wall_time_minutes":
            budget[dimension] = effective
        else:
            budget[dimension] = int(effective)
    strategy["budget"] = budget
    updated["strategy"] = strategy
    return updated


class WorkOrderRouterProxy:
    """Apply per-job WorkOrder ceilings to every Router decision without global state."""

    def __init__(self, delegate: Any, storage: Any) -> None:
        self.delegate = delegate
        self.storage = storage

    async def health(self) -> bool:
        return await self.delegate.health()

    async def route(self, payload: dict[str, Any]) -> dict[str, Any]:
        route = await self.delegate.route(payload)
        row = self.storage.get(str(payload.get("job_id") or ""))
        if not row:
            return route
        checkpoint = row.get("checkpoint") or {}
        work_order = work_order_snapshot(checkpoint.get("work_order"))
        if work_order is None:
            return route
        if checkpoint.get("legacy_adaptive_adoptions"):
            # The durable WorkOrder snapshot intentionally stays immutable and
            # therefore remains normalized as legacy_hard. A successful recovery
            # writes this internal audit marker only after proving raw pre-adaptive
            # provenance and healthy current-policy reassessment. Reuse adaptive
            # semantics for later reroutes so they cannot silently re-clamp the
            # same job to obsolete ceilings. Missing adaptive Router metadata
            # still fails closed inside apply_work_order_budget().
            work_order = work_order.model_copy(deep=True)
            work_order.budget.mode = "adaptive"
        bounded = apply_work_order_budget(route, work_order)
        return _apply_owner_budget_authorizations(bounded, checkpoint)

    async def staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.staff(payload)

    async def reassess(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.reassess(payload)


class RuntimeEngine(_RuntimeEngine):
    def __init__(self, storage: Any) -> None:
        super().__init__(storage)
        self.router = WorkOrderRouterProxy(self.router, self.storage)

    @staticmethod
    def _next_reasoning_choice(
        current_choice: dict[str, Any], strategy: dict[str, Any], role: str = "executor"
    ) -> dict[str, Any] | None:
        current = current_choice.get("reasoning_effort")
        ceiling = (strategy.get("reasoning_ceiling") or {}).get(role)
        next_effort = next_supported_effort(current_choice, ceiling)
        if next_effort is None:
            return None
        next_choice = dict(current_choice)
        next_choice["reasoning_effort"] = next_effort
        reasons = list(next_choice.get("reasons") or [])
        reasons.append(f"reasoning escalation {current}->{next_choice['reasoning_effort']}")
        next_choice["reasons"] = reasons
        return next_choice

    async def _model_failover(
        self,
        *,
        route_payload: dict[str, Any],
        provider_state: dict[str, Any],
        current_choice: dict[str, Any],
        progress: dict[str, Any],
        strategy: dict[str, Any],
        reason: str,
        role: str = "executor",
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        # A deterministic/no-effect repair is cheaper to retry with more reasoning
        # on the same Codex model before consuming a stronger model tier. Provider
        # failures deliberately bypass this path and still use provider failover.
        if progress.get("escalations", 0) < int(strategy["budget"].get("max_escalations", 0)):
            boosted = self._next_reasoning_choice(current_choice, strategy)
            if boosted is not None:
                progress["escalations"] = int(progress.get("escalations", 0)) + 1
                return boosted, {
                    "reason": "reasoning_effort_escalation",
                    "strategy": {role: boosted},
                }
        return await super()._model_failover(
            route_payload=route_payload,
            provider_state=provider_state,
            current_choice=current_choice,
            progress=progress,
            strategy=strategy,
            reason=reason,
            role=role,
        )

    def _record_agent_attempt(self, progress: dict[str, Any], choice: dict[str, Any], run: Any) -> None:
        super()._record_agent_attempt(progress, choice, run)
        attempts = progress.get("agent_attempts") or []
        if attempts:
            attempts[-1]["reasoning_effort"] = choice.get("reasoning_effort")

    def _block_wall_budget_command_timeout(
        self,
        job_id: str,
        exc: CommandTimeoutError,
    ) -> bool:
        """Turn only wall-budget-bounded agent timeouts into recoverable blocks.

        Planner/executor/evaluator calls receive one of the phase caps below via
        `_remaining_seconds()`. A timeout shorter than that cap is therefore
        bounded by the job's remaining wall-time budget. Exact-cap timeouts are
        treated as wall-bounded only when the persisted remaining wall time also
        matches that deadline. Ordinary per-call timeouts keep their existing
        terminal-failure semantics.
        """
        row = self.storage.get(job_id)
        if not row:
            return False
        status = str(row.get("status") or "")
        phase_cap = _AGENT_TIMEOUT_CAP_BY_STATUS.get(status)
        if phase_cap is None:
            return False

        route = dict(row.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        if self._adaptive_work_shape_nonblocking(strategy):
            # Adaptive calls are bounded by their per-operation caps rather than
            # remaining total wall time, so a CommandTimeoutError is not a
            # wall-budget recovery event.
            return False
        budget = dict(strategy.get("budget") or {})
        try:
            wall_limit = float(budget["max_wall_time_minutes"])
        except (KeyError, TypeError, ValueError):
            return False

        progress = dict(row.get("progress") or self._new_progress())
        try:
            elapsed = float(progress.get("elapsed_minutes", 0.0))
        except (TypeError, ValueError):
            return False

        remaining_seconds = max(0.0, (wall_limit - elapsed) * 60.0)
        wall_limited = (
            exc.timeout < float(phase_cap)
            or remaining_seconds <= exc.timeout + 1.0
        )
        if not wall_limited:
            return False

        # The command consumed its complete wall-bounded deadline. Persist at
        # least the wall limit before blocking so recovery selection observes an
        # actually exhausted wall-time dimension rather than stale pre-call time.
        progress["elapsed_minutes"] = round(
            max(elapsed + exc.timeout / 60.0, wall_limit),
            3,
        )
        checkpoint = checkpoint_from_row(row)
        reason = "planner_budget_exhausted" if status == "planning" else "execution_budget_exhausted"
        self._block(
            job_id=job_id,
            progress=progress,
            checkpoint=checkpoint,
            reason=reason,
            last_failure="wall-time budget exhausted",
        )
        return True

    async def resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool = False,
        reroute: bool = False,
        _allow_failed_orchestrated_resume: bool = False,
        _require_changed_file_headroom: bool = False,
    ) -> dict[str, Any]:
        """Resume a paused job, optionally replacing only its stale route state.

        Explicit reroute preserves the deterministic job/workspace, WorkOrder,
        plan and all progress/budget counters. A fresh route is resolved before
        the job is made runnable, so a Router failure leaves the job blocked.
        """
        self._restore_work_order_task(job_id)
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        resumable_statuses = {"queued", "interrupted", "blocked"}
        # Only main.py may set this after it has confirmed that this exact job
        # belongs to a blocked agent WorkOrder in a blocked orchestration plan.
        # It is deliberately not part of the public run request contract.
        if _allow_failed_orchestrated_resume:
            resumable_statuses.add("failed")
        if row["status"] not in resumable_statuses:
            raise RuntimeError(f"Job cannot be resumed from status={row['status']}")

        checkpoint = checkpoint_from_row(row)
        if reset_transient_provider_failures:
            checkpoint = clear_transient_provider_failures(checkpoint)

        fields: dict[str, Any] = {
            "status": "queued",
            "error": None,
            "checkpoint": checkpoint,
        }
        if reroute:
            repo_analysis = row.get("repo_analysis")
            source_commit = str(row.get("source_commit") or "").strip()
            if not isinstance(repo_analysis, dict) or "estimated_files" not in repo_analysis:
                raise RuntimeError("Explicit reroute requires persisted repository analysis")
            if not source_commit:
                raise RuntimeError("Explicit reroute requires a persisted source commit")

            checkpoint = clear_routing_choices_for_resume(checkpoint)
            provider_state = dict(checkpoint.get("provider_state") or {})
            fresh_route = await self.router.route({
                "job_id": job_id,
                "project_id": row["project_id"],
                "repository": row["project_id"],
                "source_commit": source_commit,
                "task": row["task"],
                "repo": repo_analysis,
                "provider_state": provider_state,
            })

            if _require_changed_file_headroom:
                strategy = dict(fresh_route.get("strategy") or {})
                if strategy.get("budget_mode") != "adaptive":
                    raise RuntimeError(
                        "Changed-file scope recovery requires an effective adaptive route"
                    )
                adaptive = dict(strategy.get("adaptive_budget") or {})
                dimensions = dict(adaptive.get("dimensions") or {})
                envelope = dict(dimensions.get("max_changed_files") or {})
                try:
                    working_target = int(float(envelope["working_target"]))
                    emergency_limit = int(float(envelope["emergency_limit"]))
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeError(
                        "Fresh adaptive route does not expose changed-file headroom"
                    ) from exc

                progress = dict(row.get("progress") or {})
                changed_files = int(progress.get("changed_files") or 0)
                if changed_files <= working_target:
                    raise RuntimeError(
                        "Changed-file scope recovery is stale; the working target is not exceeded"
                    )
                if changed_files > emergency_limit:
                    raise RuntimeError(
                        "Changed-file scope recovery exceeds the fresh emergency ceiling"
                    )

            route_history = list(checkpoint.get("route_history") or [])
            route_history.append({
                "reason": (
                    "changed_file_scope_policy_refresh"
                    if _require_changed_file_headroom
                    else "explicit_resume_reroute"
                ),
                "route": fresh_route,
            })
            checkpoint["route_history"] = route_history
            checkpoint["provider_state"] = provider_state
            fields["route"] = fresh_route
            fields["checkpoint"] = checkpoint

        self.storage.update(job_id, **fields)
        await self.enqueue(job_id)
        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    async def request_review_repair(
        self,
        job_id: str,
        *,
        expected_commit: str,
        finding: str,
        evidence: dict[str, Any] | None = None,
        references: list[str] | None = None,
    ) -> dict[str, Any]:
        """Govern one PM-owned repair of an exact delivered, unmerged PR."""
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        if row.get("status") not in {"blocked", "completed"}:
            raise RuntimeError(
                f"Review repair cannot be requested from status={row.get('status')}"
            )
        if job_id in self.active_jobs:
            raise RuntimeError("Review repair cannot be requested while the job is active")

        delivered = self._delivered_result_for_review_repair(row)
        if delivered is None:
            raise RuntimeError("Review repair requires a delivered accepted result with a pull request")
        if row.get("status") == "blocked":
            reason = str((row.get("result") or {}).get("reason") or "")
            if reason not in {
                "github_ci_timeout",
                "github_ci_infrastructure_failure",
                "github_delivery_failed",
                "github_delivery_budget_exhausted",
            }:
                raise RuntimeError("Blocked job is not paused in a delivery-recovery state")

        delivered_commit = str(delivered.get("commit") or "")
        if delivered_commit.lower() != expected_commit.lower():
            raise RuntimeError("Expected commit does not match the delivered accepted result")
        delivery = dict(delivered.get("delivery") or {})
        pull_request = dict(delivery.get("pull_request") or {})
        try:
            pr_number = int(pull_request["number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Delivered result is missing an exact pull-request number") from exc

        branch = str(row.get("branch") or delivered.get("branch") or "")
        workspace = str(row.get("workspace") or "")
        source_commit = str(row.get("source_commit") or "")
        if not branch or not workspace or not source_commit:
            raise RuntimeError("Review repair requires the persisted job workspace/branch/source identity")
        if pull_request.get("head") and str(pull_request.get("head")) != delivered_commit:
            raise RuntimeError("Persisted pull-request head does not match the delivered commit")
        if pull_request.get("head_ref") and str(pull_request.get("head_ref")) != branch:
            raise RuntimeError("Persisted pull-request branch does not match the Runtime job branch")

        checkpoint = checkpoint_from_row(row)
        if isinstance(checkpoint.get("pending_review_repair"), dict):
            raise RuntimeError("A PM review repair is already pending for this job")
        if isinstance(checkpoint.get("active_review_repair"), dict):
            raise RuntimeError("A PM review repair is already in delivery for this job")
        if isinstance(checkpoint.get(REVIEW_REPAIR_CHURN_EPOCH_KEY), dict):
            raise RuntimeError(
                "A prior review-repair churn epoch remains active for this job"
            )

        workspace_mode = str(checkpoint.get("workspace_mode") or "")
        if workspace_mode not in {"direct", "isolated_clone"}:
            project = project_config(str(row["project_id"]))
            workspace_mode = (
                "direct"
                if Path(workspace).resolve() == Path(str(project.get("path") or "")).resolve()
                else "isolated_clone"
            )
        lease_reused = True
        lease: dict[str, Any] | None = None
        prepared: dict[str, Any] | None = None
        transition_persisted = False
        try:
            if workspace_mode == "direct":
                lease = self.storage.acquire_project_lease(str(row["project_id"]), job_id)
                lease_reused = bool(lease.get("reused", False))
                await ProjectPreviewManager(self.storage, self.ddev).handoff_to_job(
                    str(row["project_id"]), job_id
                )

            prepared = await self.ddev.prepare_review_repair(
                job_id=job_id,
                project_id=str(row["project_id"]),
                workspace=workspace,
                branch=branch,
                source_commit=source_commit,
                expected_commit=delivered_commit,
                pr_number=pr_number,
            )
            observed_pr = dict(prepared.get("pull_request") or {})
            if (
                str(prepared.get("workspace") or "") != workspace
                or str(prepared.get("branch") or "") != branch
                or str(prepared.get("expected_commit") or "") != delivered_commit
                or str(prepared.get("workspace_mode") or "") != workspace_mode
                or int(observed_pr.get("number") or 0) != pr_number
                or str(observed_pr.get("head") or "") != delivered_commit
                or str(observed_pr.get("head_ref") or "") != branch
                or str(observed_pr.get("state") or "") != "open"
                or bool(observed_pr.get("merged"))
            ):
                raise RuntimeError("Executor returned mismatched review-repair PR evidence")

            latest = self.storage.get(job_id)
            if not latest or latest.get("status") != row.get("status"):
                raise RuntimeError("Job state changed while the review repair was being validated")
            latest_delivered = self._delivered_result_for_review_repair(latest)
            if not latest_delivered or str(latest_delivered.get("commit") or "") != delivered_commit:
                raise RuntimeError("Delivered result changed while the review repair was being validated")

            checkpoint = checkpoint_from_row(latest)
            request_id = uuid.uuid4().hex
            delivered_diff_hash = str(
                (delivered.get("diff") or {}).get("diff_hash")
                or f"commit:{delivered_commit}"
            )
            message = (
                "PCP_PM_REVIEW_REPAIR: "
                + json.dumps(
                    {
                        "finding": finding,
                        "evidence": evidence or {},
                        "references": references or [],
                        "expected_delivered_commit": delivered_commit,
                        "pull_request": pr_number,
                        "instruction": (
                            "Make the smallest in-scope repair on the existing job branch. "
                            "Do not rewrite the WorkOrder or ProjectBaseline."
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )[-30000:]
            requested_at = now().isoformat()
            record = {
                "request_id": request_id,
                "state": "pending",
                "requested_at": requested_at,
                "expected_commit": delivered_commit,
                "delivered_diff_hash": delivered_diff_hash,
                "pr_number": pr_number,
                "finding": finding,
                "evidence": deepcopy(evidence or {}),
                "references": list(references or []),
                "message": message,
                "executor_verification": deepcopy(prepared),
            }
            checkpoint["pending_review_repair"] = deepcopy(record)
            checkpoint[REVIEW_REPAIR_CHURN_EPOCH_KEY] = (
                new_review_repair_churn_epoch(
                    request_id,
                    dict(latest.get("progress") or {}),
                    started_at=requested_at,
                    legacy_baseline_migrated=False,
                )
            )
            checkpoint[REVIEW_REPAIR_CHURN_INITIALIZED_KEY] = {"request_id": request_id}
            history = [
                deepcopy(item)
                for item in (checkpoint.get("review_repair_history") or [])
                if isinstance(item, dict)
            ]
            history.append(deepcopy(record))
            checkpoint["review_repair_history"] = history
            accepted_history = list(checkpoint.get("accepted_result_history") or [])
            accepted_history.append({
                "reason": "pm_review_repair",
                "request_id": request_id,
                "result": deepcopy(delivered),
            })
            checkpoint["accepted_result_history"] = accepted_history
            delivery_history = list(checkpoint.get("delivery_history") or [])
            delivery_history.append({
                "reason": "pm_review_repair",
                "request_id": request_id,
                "delivery": deepcopy(delivery),
            })
            checkpoint["delivery_history"] = delivery_history
            if lease is not None:
                checkpoint["project_lease_generation"] = int(lease.get("generation") or 0)
            set_failure_context(
                checkpoint,
                kind="semantic_repair",
                source="pm_review_repair",
                message=message,
                diff_hash=delivered_diff_hash,
            )
            visible_result = deepcopy(latest.get("result") or {})
            visible_result["review_repair_pending"] = {
                "request_id": request_id,
                "expected_commit": delivered_commit,
                "pr_number": pr_number,
                "finding": finding,
            }
            self.storage.update(
                job_id,
                status="queued",
                checkpoint=checkpoint,
                result=visible_result,
                error=None,
            )
            transition_persisted = True
        except Exception:
            if workspace_mode == "direct" and lease is not None and not lease_reused and not transition_persisted:
                try:
                    await self.ddev.return_direct_workspace_to_base(
                        job_id=job_id,
                        project_id=str(row["project_id"]),
                        workspace=workspace,
                        branch=branch,
                    )
                except Exception:
                    pass
                self.storage.release_project_lease(str(row["project_id"]), job_id)
            raise

        self._runtime_event(
            job_id,
            kind="pm_review_repair",
            message="PM requested a bounded repair of the exact delivered PR head",
            phase="review_repair",
            status="queued",
            output={
                "request_id": checkpoint["pending_review_repair"]["request_id"],
                "expected_commit": delivered_commit,
                "pr_number": pr_number,
            },
        )
        await self.enqueue(job_id)
        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    def create_job(
        self, payload: dict[str, Any], *,
        _orchestration: tuple[str, str] | None = None,
        _intake_decision: IntakeDecision | None = None,
    ) -> str:
        """Create one job with its governing baseline/contract in the same write.

        `_job_id` is an internal-only idempotency hook used by the durable plan
        orchestrator. Public API models never expose it. Reusing the same id is
        accepted only when the persisted project and WorkOrder identity match.
        `_orchestration` is a private keyword (not a payload field): it reserves
        the queued job until its exact durable started checkpoint releases it.
        """

        project = project_config(payload["project_id"])
        work_order = work_order_snapshot(payload.get("work_order"))
        requested_revision = (
            work_order.baseline_revision if work_order is not None else payload.get("baseline_revision")
        )
        baseline = resolve_project_baseline(payload["project_id"], requested_revision)

        if work_order is not None:
            validate_work_order_against_baseline(work_order, baseline, project)
            task = canonical_task_from_work_order(work_order)
        else:
            task = payload.get("task")
            if not isinstance(task, dict):
                raise ValueError("Legacy job creation requires task when work_order is absent")

        requested_job_id = str(payload.get("_job_id") or "").strip()
        job_id = requested_job_id or uuid.uuid4().hex
        launch = launch_identity(*_orchestration) if _orchestration is not None else None
        if launch and (job_id != launch["job_id"] or work_order is None or work_order.id != launch["work_order_id"]):
            raise RuntimeError("Orchestrator launch requires its exact deterministic job/WorkOrder")
        if requested_job_id:
            try:
                uuid.UUID(hex=requested_job_id)
            except ValueError as exc:
                raise ValueError("Internal orchestrator job id must be a UUID hex value") from exc
            existing = self.storage.get(job_id)
            if existing is not None:
                existing_checkpoint = existing.get("checkpoint") or {}
                existing_work_order = work_order_snapshot(existing_checkpoint.get("work_order"))
                if (
                    existing.get("project_id") != payload["project_id"]
                    or work_order is None
                    or existing_work_order is None
                    or existing_work_order.id != work_order.id
                    or existing_work_order.baseline_revision != work_order.baseline_revision
                ):
                    raise RuntimeError("Deterministic orchestrator job id collides with different job metadata")
                if launch:
                    marker = orchestrator_launch(existing)
                    if marker is None or any(marker.get(key) != value for key, value in launch.items()):
                        raise RuntimeError("Deterministic job lacks its exact orchestrator launch reservation")
                return job_id

        checkpoint = {
            "hints": payload.get("repo_hints", {}),
            "provider_state": payload.get("provider_state", {}),
            "route_history": [],
            "approved_decisions": [],
        }
        if baseline is not None:
            checkpoint["project_baseline"] = baseline.model_dump(mode="json")
        if work_order is not None:
            checkpoint["work_order"] = work_order.model_dump(mode="json")
        if launch:
            checkpoint["orchestrator_launch"] = {**launch, "state": "held"}
        if _intake_decision is not None:
            if baseline is None or _intake_decision.mode != "direct" or not _intake_decision.bounded_direct:
                raise ValueError("Canonical direct intake requires an approved baseline and direct decision")
            # Same INSERT as the job: startup can never see an unaudited queued
            # canonical job. This private keyword is not a caller payload field.
            checkpoint["canonical_intake"] = {
                **_intake_decision.model_dump(mode="json"),
                "baseline_revision": baseline.revision,
            }

        self.storage.create({
            "id": job_id,
            "project_id": payload["project_id"],
            "status": "queued",
            "source_commit": payload.get("source_commit"),
            "task": task,
            "repo_analysis": None,
            "progress": self._new_progress(),
            "checkpoint": checkpoint,
            "dry_run": bool(payload.get("dry_run", False)),
        })
        return job_id

    def _restore_work_order_task(self, job_id: str) -> None:
        row = self.storage.get(job_id)
        if not row:
            return
        checkpoint = row.get("checkpoint") or {}
        work_order = work_order_snapshot(checkpoint.get("work_order"))
        if work_order is None:
            return
        canonical = rehydrate_task_from_work_order(row.get("task"), work_order)
        if canonical != row.get("task"):
            self.storage.update(job_id, task=canonical)

    async def run_job(self, job_id: str) -> None:
        marker = orchestrator_launch(self.storage.get(job_id) or {})
        if marker and marker["state"] == "held":
            raise RuntimeError("Orchestrator launch is held until its started checkpoint commits")
        self._restore_work_order_task(job_id)
        try:
            await super().run_job(job_id)
        except CommandTimeoutError as exc:
            if self._block_wall_budget_command_timeout(job_id, exc):
                return
            raise
        except WorkOrderPolicyError as exc:
            row = self.storage.get(job_id)
            if not row:
                raise
            checkpoint = dict(row.get("checkpoint") or {})
            progress = dict(row.get("progress") or self._new_progress())
            self._block(
                job_id=job_id,
                progress=progress,
                checkpoint=checkpoint,
                reason="work_order_policy_rejected",
                last_failure=str(exc),
            )

    async def _verify(
        self,
        job_id: str,
        project_id: str,
        workspace: Any,
        project: dict[str, Any],
        strategy: dict[str, Any],
        started: float,
        progress: dict[str, Any],
    ) -> dict[str, Any]:
        result = await super()._verify(
            job_id,
            project_id,
            workspace,
            project,
            strategy,
            started,
            progress,
        )
        if not result.get("passed", False):
            return result

        row = self.storage.get(job_id)
        checkpoint = (row or {}).get("checkpoint") or {}
        work_order = work_order_snapshot(checkpoint.get("work_order"))

        ddev_cfg = project.get("ddev", {}) or {}
        required_order = list(work_order.verification.required_phases) if work_order else []
        required = set(required_order)

        # Project-owned final checks may be required by the shape of the actual
        # diff for legacy jobs without a WorkOrder as well as older immutable
        # WorkOrders that predate a phase. Path scoping avoids charging
        # backend-only work for frontend verification.
        auto_rules = ddev_cfg.get("auto_required_phases", []) or []
        changed_files: list[str] = []
        if auto_rules:
            current_diff = diff_state(
                Path(workspace),
                int(project.get("runtime", {}).get("max_diff_bytes", 750000)),
            )
            changed_files = list(current_diff.get("changed_files") or [])
        for rule in auto_rules:
            if not isinstance(rule, dict):
                continue
            phase = str(rule.get("phase") or "").strip()
            prefixes = [
                str(item).strip()
                for item in (rule.get("path_prefixes") or [])
                if str(item).strip()
            ]
            if (
                phase
                and prefixes
                and any(
                    path.startswith(prefix)
                    for path in changed_files
                    for prefix in prefixes
                )
                and phase not in required
            ):
                required.add(phase)
                required_order.append(phase)

        for phase in required_order:
            if not (ddev_cfg.get(phase, []) or []):
                result["passed"] = False
                result["tests_passed"] = False
                result["failure_text"] = (
                    str(result.get("failure_text") or "")
                    + f"\n{phase}: required verification has no configured commands"
                ).strip()[-30000:]
                return result
            if any(
                isinstance(item, dict)
                and item.get("phase") == phase
                and not item.get("commands")
                for item in (result.get("phases") or [])
            ):
                result["passed"] = False
                result["tests_passed"] = False
                result["failure_text"] = (
                    str(result.get("failure_text") or "")
                    + f"\n{phase}: required verification has no executed commands"
                ).strip()[-30000:]
                return result

        # Base/layered verification may already have executed a phase that the
        # WorkOrder or project auto-rule makes authoritative for final
        # acceptance. Normalize that existing evidence at the point where the
        # authoritative required order is known; do not rerun or reinterpret it.
        for item in result.get("phases") or []:
            if (
                isinstance(item, dict)
                and str(item.get("phase") or "") in required
            ):
                item["required_for_final"] = True

        completed_phases = {
            str(item.get("phase") or "")
            for item in (result.get("phases") or [])
            if isinstance(item, dict)
        }
        extra_phases = [
            phase
            for phase in required_order
            if phase not in completed_phases
        ]

        for phase in extra_phases:
            commands = ddev_cfg.get(phase, []) or []
            count = len(commands)
            budget = strategy["budget"]
            if (
                not self._adaptive_work_shape_nonblocking(strategy)
                and (
                    progress["tool_calls"] + int(result.get("tool_calls", 0)) + count
                    > int(budget["max_tool_calls"])
                    or progress["test_runs"] + int(result.get("test_runs", 0)) + count
                    > int(budget["max_test_runs"])
                )
            ):
                result["passed"] = False
                result["tests_passed"] = False
                result["failure_text"] = (
                    str(result.get("failure_text") or "")
                    + f"\n{phase}: WorkOrder-required verification would exceed execution budget"
                ).strip()[-30000:]
                return result

            phase_result = await self.ddev.phase(
                job_id=job_id,
                project_id=project_id,
                workspace=str(workspace),
                phase=phase,
                timeout_seconds=self._remaining_seconds(strategy, started, 1200),
            )
            annotated = dict(phase_result)
            annotated["verification_layer"] = "final"
            annotated["required_for_final"] = True
            result.setdefault("phases", []).append(annotated)
            result["tool_calls"] = int(result.get("tool_calls", 0)) + len(phase_result.get("commands", []))
            result["test_runs"] = int(result.get("test_runs", 0)) + len(phase_result.get("commands", []))
            if not phase_result.get("passed", False):
                result["passed"] = False
                result["tests_passed"] = False
                result["failure_text"] = (
                    str(result.get("failure_text") or "") + "\n" + str(phase_result)
                ).strip()[-30000:]
                return result
            if not phase_result.get("commands"):
                result["passed"] = False
                result["tests_passed"] = False
                result["failure_text"] = (
                    str(result.get("failure_text") or "")
                    + f"\n{phase}: required verification has no executed commands"
                ).strip()[-30000:]
                return result

        return result


__all__ = ["RuntimeEngine"]
