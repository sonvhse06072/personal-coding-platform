from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from .adapters.antigravity import cancel_all_antigravity_runs
from .fullpath_fixture_safety import MODE as FULLPATH_CANDIDATE_MODE, refuse_source_only_startup
from .config import project_config
from .executor_client import DdevExecutorClient
from .preview import PreviewManager
from .review_repair_churn import (
    DECISION_SOURCE as REVIEW_REPAIR_CHURN_DECISION_SOURCE,
    EPOCH_KEY as REVIEW_REPAIR_CHURN_EPOCH_KEY,
    GATE_KEY as REVIEW_REPAIR_CHURN_GATE_KEY,
    RESULT_REASON as REVIEW_REPAIR_CHURN_RESULT_REASON,
    ReviewRepairChurnIntegrityError,
    ReviewRepairChurnPaused,
    decision_identity as review_repair_churn_decision_identity,
    ensure_legacy_epoch,
    evidence as review_repair_churn_evidence,
    integrity_evidence as review_repair_churn_integrity_evidence,
    validate_epoch as validate_review_repair_churn_epoch,
)
from .router_client import RouterClient
from .standalone_antiloop_epoch import effective_reassessment_progress
from .state import (
    checkpoint_from_row,
    clear_transient_provider_failures,
    decision_key,
    provider_failure_state_key,
    set_failure_context,
)
from .storage import Storage, now
from .work_order_checkpoints import orchestrator_launch
from .usage import estimated_cost_usd, normalize_usage


FINAL = {"completed", "failed", "cancelled"}
PAUSED = {"blocked", "waiting_human", "interrupted"}
STABLE = FINAL | PAUSED


class RuntimeEngineCore:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.router = RouterClient()
        self.ddev = DdevExecutorClient()
        self.workspace_root = Path(os.getenv("CODING_WORKSPACES_ROOT", "/workspaces")).resolve()
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker_task: asyncio.Task | None = None
        self.active_jobs: dict[str, asyncio.Task[None]] = {}
        self._queued_orchestrated_jobs: set[str] = set()
        self._stopping = False

    async def start(self) -> None:
        if os.getenv("PCP_RUNTIME_STARTUP_MODE") == FULLPATH_CANDIDATE_MODE:
            # Direct method calls cannot bypass main.lifespan and accidentally
            # mutate an arbitrary DB or call the global Antigravity cancel-all.
            refuse_source_only_startup()
        self.storage.init()
        self._stopping = False
        await cancel_all_antigravity_runs()
        for job in self.storage.list(limit=500):
            if job["status"] == "queued":
                marker = orchestrator_launch(job)
                if not marker or marker["state"] != "held":
                    await self.enqueue(job["id"])
            elif job["status"] not in STABLE:
                self.storage.update(
                    job["id"],
                    status="interrupted",
                    error="Runtime restarted during an in-flight job; explicit resume required.",
                )
                await self.ddev.cancel(job_id=job["id"])
        terminal_lease_lookup = getattr(
            self.storage,
            "terminal_active_project_leases",
            None,
        )
        terminal_lease_rows = (
            terminal_lease_lookup()
            if callable(terminal_lease_lookup)
            else []
        )
        if callable(terminal_lease_lookup):
            for lease in terminal_lease_rows:
                owner_job_id = str(lease.get("owner_job_id") or "")
                preview_retired = await self._retire_terminal_direct_preview(owner_job_id)
                workspace_restored = await self._restore_terminal_direct_workspace(
                    owner_job_id
                )
                if preview_retired and workspace_restored:
                    self._release_terminal_direct_lease(owner_job_id)
        else:
            self.storage.reconcile_terminal_project_leases()
        self.worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        self._stopping = True
        tasks = list(self.active_jobs.items())
        for job_id, task in tasks:
            row = self.storage.get(job_id)
            if row and row["status"] not in FINAL:
                self.storage.update(
                    job_id,
                    status="interrupted",
                    error="Runtime stopped during an in-flight job; explicit resume required.",
                )
            await self.ddev.cancel(job_id=job_id)
            task.cancel()
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        self.worker_task = None

    async def enqueue(self, job_id: str) -> None:
        marker = orchestrator_launch(self.storage.get(job_id) or {})
        if marker:
            if marker["state"] == "held":
                raise RuntimeError("Orchestrator launch is held until its started checkpoint commits")
            if job_id in self._queued_orchestrated_jobs or job_id in self.active_jobs:
                return
            self._queued_orchestrated_jobs.add(job_id)
        await self.queue.put(job_id)

    async def _quiesce_stable_manual_job(self, job_id: str) -> None:
        """Best-effort DDEV cleanup for non-orchestrated stable jobs.

        Orchestrated WorkOrders are quiesced by PlanOrchestrator so its durable
        detail/notifications can record the resource action. Manual jobs still
        need the same resource discipline, otherwise their per-job DDEV project
        can remain running forever.
        """
        row = self.storage.get(job_id)
        if not row:
            return
        if orchestrator_launch(row) is not None:
            return
        status = str(row.get("status") or "")
        if status not in STABLE:
            return
        workspace = str(row.get("workspace") or "").strip()
        if not workspace:
            return
        project = project_config(str(row["project_id"]))
        if not project.get("ddev", {}).get("enabled", False):
            return

        remove_data = status in {"completed", "cancelled"}
        try:
            result = await self.ddev.quiesce_workspace(
                job_id=job_id,
                project_id=str(row["project_id"]),
                workspace=workspace,
                remove_data=remove_data,
            )
            detail = {
                "quiesced": bool(result.get("quiesced", False)),
                "data_removed": bool(result.get("data_removed", False)),
                "status": status,
            }
        except Exception as exc:
            detail = {
                "quiesced": False,
                "data_removed": False,
                "status": status,
                "error": str(exc)[-2000:],
            }

        latest = self.storage.get(job_id)
        if not latest:
            return
        checkpoint = checkpoint_from_row(latest)
        checkpoint["resource_quiesce"] = detail
        self.storage.update(job_id, checkpoint=checkpoint)

    async def _retire_terminal_direct_preview(self, job_id: str) -> bool:
        if not job_id:
            return True
        row = self.storage.get(job_id)
        if not row or str(row.get("status") or "") not in FINAL:
            return True
        checkpoint = checkpoint_from_row(row)
        if str(checkpoint.get("workspace_mode") or "isolated_clone") != "direct":
            return True
        preview_lookup = getattr(self.storage, "preview_state", None)
        if not callable(preview_lookup):
            return True
        preview_state = preview_lookup(job_id)
        if not preview_state:
            return True
        if str(preview_state.get("status") or "") in {"stopped", "not_built"}:
            return True
        try:
            result = await PreviewManager(self.storage, self.ddev).stop(job_id)
        except Exception:
            return False
        return str(result.get("status") or "") in {"stopped", "not_built"}

    async def _restore_terminal_direct_workspace(self, job_id: str) -> bool:
        if not job_id:
            return True
        row = self.storage.get(job_id)
        if not row or str(row.get("status") or "") not in FINAL:
            return True
        checkpoint = checkpoint_from_row(row)
        if str(checkpoint.get("workspace_mode") or "isolated_clone") != "direct":
            return True

        workspace = str(row.get("workspace") or "").strip()
        branch = str(row.get("branch") or "").strip()
        if not workspace or not branch:
            return False

        try:
            result = await self.ddev.return_direct_workspace_to_base(
                job_id=job_id,
                project_id=str(row["project_id"]),
                workspace=workspace,
                branch=branch,
            )
        except Exception as exc:
            latest = self.storage.get(job_id)
            if latest:
                latest_checkpoint = checkpoint_from_row(latest)
                latest_checkpoint["direct_base_restore"] = {
                    "restored": False,
                    "error": str(exc)[-2000:],
                }
                self.storage.update(job_id, checkpoint=latest_checkpoint)
            return False

        restored = bool(result.get("returned", False))
        latest = self.storage.get(job_id)
        if latest:
            latest_checkpoint = checkpoint_from_row(latest)
            latest_checkpoint["direct_base_restore"] = {
                "restored": restored,
                "branch": result.get("branch"),
                "head": result.get("head"),
                "reused": bool(result.get("reused", False)),
            }
            self.storage.update(job_id, checkpoint=latest_checkpoint)
        return restored

    def _release_terminal_direct_lease(self, job_id: str) -> bool:
        row = self.storage.get(job_id)
        if not row or str(row.get("status") or "") not in FINAL:
            return False
        checkpoint = checkpoint_from_row(row)
        if str(checkpoint.get("workspace_mode") or "isolated_clone") != "direct":
            return False
        return self.storage.release_project_lease(str(row["project_id"]), job_id)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self.queue.get()
            run_task = asyncio.create_task(self.run_job(job_id))
            self.active_jobs[job_id] = run_task
            try:
                await run_task
            except asyncio.CancelledError:
                row = self.storage.get(job_id)
                if row and row["status"] not in FINAL and row["status"] != "interrupted":
                    if row["status"] != "cancelled":
                        self.storage.update(
                            job_id,
                            status="interrupted",
                            error="Job execution was interrupted; explicit resume required.",
                        )
            except Exception as exc:
                row = self.storage.get(job_id)
                if row and row["status"] != "cancelled":
                    self.storage.update(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
            finally:
                if not self._stopping:
                    preview_retired = await self._retire_terminal_direct_preview(job_id)
                    await self._quiesce_stable_manual_job(job_id)
                    workspace_restored = await self._restore_terminal_direct_workspace(job_id)
                    if preview_retired and workspace_restored:
                        self._release_terminal_direct_lease(job_id)
                self.active_jobs.pop(job_id, None)
                self._queued_orchestrated_jobs.discard(job_id)
                self.queue.task_done()

    def create_job(self, payload: dict[str, Any]) -> str:
        project_config(payload["project_id"])
        job_id = uuid.uuid4().hex
        checkpoint = {
            "hints": payload.get("repo_hints", {}),
            "provider_state": payload.get("provider_state", {}),
            "route_history": [],
            "approved_decisions": [],
        }
        self.storage.create({
            "id": job_id,
            "project_id": payload["project_id"],
            "status": "queued",
            "source_commit": payload.get("source_commit"),
            "task": payload["task"],
            "repo_analysis": None,
            "progress": self._new_progress(),
            "checkpoint": checkpoint,
            "dry_run": bool(payload.get("dry_run", False)),
        })
        return job_id

    async def advance_direct_job_source(
        self,
        job_id: str,
        *,
        expected_old_source: str,
        expected_new_source: str,
        _allow_failed_orchestrated_recovery: bool = False,
    ) -> dict[str, Any]:
        """Advance one preserved blocked direct job onto an exact newer base.

        The executor performs the filesystem mutation first under strict
        fast-forward/no-overlap guards. Runtime updates durable source identity
        only after that proof succeeds. A retry is idempotent when the durable
        source was already advanced by an earlier successful call.
        """

        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        status = str(row["status"])
        failed_orchestrated_recovery = (
            status == "failed" and _allow_failed_orchestrated_recovery
        )
        if status not in {"blocked", "interrupted"} and not failed_orchestrated_recovery:
            raise RuntimeError(
                "Direct source advance requires blocked/interrupted status or an "
                f"explicitly tracked failed orchestrated recovery, got {status}"
            )

        active = self.active_jobs.get(job_id)
        if active is not None and not active.done():
            raise RuntimeError("Direct source advance requires no active Runtime worker")

        old_source = str(expected_old_source).lower()
        new_source = str(expected_new_source).lower()
        checkpoint = checkpoint_from_row(row)
        if str(checkpoint.get("workspace_mode") or "") != "direct":
            raise RuntimeError("Direct source advance requires a durably direct workspace")

        current_source = str(row.get("source_commit") or "").lower()
        last_advance = dict(checkpoint.get("last_source_advance") or {})
        if current_source == new_source:
            if (
                str(last_advance.get("old_source") or "").lower() == old_source
                and str(last_advance.get("new_source") or "").lower() == new_source
            ):
                return row
            raise RuntimeError(
                "Job already has the requested new source without matching source-advance evidence"
            )
        if current_source != old_source:
            raise RuntimeError(
                "Job source commit does not match the exact expected old source"
            )

        workspace = str(row.get("workspace") or "").strip()
        branch = str(row.get("branch") or "").strip()
        if not workspace or not branch:
            raise RuntimeError("Direct source advance requires persisted workspace and branch")

        proof = await self.ddev.advance_direct_workspace_source(
            job_id=job_id,
            project_id=str(row["project_id"]),
            workspace=workspace,
            branch=branch,
            old_source=old_source,
            new_source=new_source,
        )
        if (
            str(proof.get("old_source") or "").lower() != old_source
            or str(proof.get("new_source") or "").lower() != new_source
            or str(proof.get("branch") or "") != branch
            or str(proof.get("workspace") or "") != workspace
        ):
            raise RuntimeError("Executor source-advance proof does not match the preserved job")

        invalidated: list[str] = []
        for key in (
            "deterministic_verification_failure_streak",
            "last_verification_summary",
            "last_review_report",
            "last_pm_reassessment",
            "pending_pm_reassessment",
            "pending_review_findings",
            "review_repair_churn_epoch",
            "review_repair_churn_gate",
            "pm_baseline_covered_protected_authorizations",
        ):
            if key in checkpoint:
                invalidated.append(key)
                checkpoint.pop(key, None)

        record = {
            "old_source": old_source,
            "new_source": new_source,
            "branch": branch,
            "dirty_path_count": len(proof.get("dirty_paths") or []),
            "dependency_path_count": len(proof.get("dependency_paths") or []),
            "already_advanced": bool(proof.get("already_advanced", False)),
            "invalidated_exact_diff_state": invalidated,
        }
        history = [
            deepcopy(item)
            for item in checkpoint.get("source_advance_history") or []
            if isinstance(item, dict)
        ]
        history.append(record)
        checkpoint["source_advance_history"] = history[-8:]
        checkpoint["last_source_advance"] = record
        set_failure_context(
            checkpoint,
            kind="semantic_repair",
            source="source_advance",
            message=(
                "PCP_SOURCE_ADVANCED: The preserved direct-workspace job was "
                f"fast-forwarded from {old_source} to dependency/base {new_source}. "
                "Keep the same WorkOrder and preserved worktree changes, re-read the "
                "current backend/API source, and re-evaluate the current diff before "
                "continuing repair or verification."
            ),
        )

        self.storage.update(
            job_id,
            source_commit=new_source,
            repo_analysis=None,
            checkpoint=checkpoint,
        )
        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    async def resume(self, job_id: str, *, reset_transient_provider_failures: bool = False) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        if row["status"] not in {"queued", "interrupted", "blocked"}:
            raise RuntimeError(f"Job cannot be resumed from status={row['status']}")
        checkpoint = checkpoint_from_row(row)
        if reset_transient_provider_failures:
            checkpoint = clear_transient_provider_failures(checkpoint)
        self.storage.update(job_id, status="queued", error=None, checkpoint=checkpoint)
        await self.enqueue(job_id)
        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    async def cancel(self, job_id: str) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        if row["status"] in {"completed", "failed"}:
            raise RuntimeError(f"Job cannot be cancelled from status={row['status']}")
        if row["status"] != "cancelled":
            self.storage.update(job_id, status="cancelled", error=None)
        await self.ddev.cancel(job_id=job_id)
        active = self.active_jobs.get(job_id)
        if active and not active.done():
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
        preview_retired = await self._retire_terminal_direct_preview(job_id)
        await self._quiesce_stable_manual_job(job_id)
        workspace_restored = await self._restore_terminal_direct_workspace(job_id)
        if preview_retired and workspace_restored:
            self._release_terminal_direct_lease(job_id)
        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    async def resolve_human_decision(
        self,
        job_id: str,
        *,
        action: str,
        note: str = "",
        expected_decision_key: str | None = None,
    ) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        if row["status"] != "waiting_human":
            raise RuntimeError(f"Job is not waiting for a human decision (status={row['status']})")
        checkpoint = checkpoint_from_row(row)
        pending = dict(checkpoint.get("pending_decision") or {})
        decision = dict(pending.get("decision") or {})
        key = str(pending.get("key") or decision_key(decision))
        source = str(pending.get("source") or "")
        if expected_decision_key is not None and str(expected_decision_key) != key:
            raise RuntimeError("Human decision key is stale or does not match")
        if source == REVIEW_REPAIR_CHURN_DECISION_SOURCE:
            if not expected_decision_key:
                raise RuntimeError(
                    "Review-repair churn decisions require the exact decision key"
                )
            return await self._resolve_review_repair_churn_decision(
                job_id=job_id,
                row=row,
                checkpoint=checkpoint,
                pending=pending,
                decision=decision,
                key=key,
                action=action,
                note=note,
            )
        history = list(checkpoint.get("decision_history") or [])
        record = {"key": key, "action": action, "note": note}
        history.append(record)
        checkpoint["decision_history"] = history[-20:]
        checkpoint.pop("pending_decision", None)

        if action == "reject":
            source = str(pending.get("source") or "")
            pm_boundary = dict(checkpoint.get("pending_pm_reassessment") or {})
            if source == "pm_reassessment" and pm_boundary:
                repair_note = (note or "").strip() or str(
                    decision.get("reason") or pm_boundary.get("summary") or "Human Owner rejected the requested boundary."
                )
                rejection_failure = (
                    "PCP_HUMAN_DECISION_REJECTED: "
                    + json.dumps(
                        {
                            "decision_key": key,
                            "human_note": repair_note,
                            "decision": decision,
                            "pm_boundary": pm_boundary,
                            "instruction": (
                                "Do not expand the rejected boundary. Repair or revert the "
                                "implementation so the approved WorkOrder and ProjectBaseline are satisfied."
                            ),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )[-30000:]
                set_failure_context(
                    checkpoint,
                    kind="semantic_repair",
                    source="human_rejection",
                    message=rejection_failure,
                    diff_hash=str(pm_boundary.get("diff_hash") or ""),
                    decision_key_value=key,
                )
                self.storage.update(
                    job_id,
                    status="queued",
                    checkpoint=checkpoint,
                    result={
                        "reason": "human_decision_rejected_repair",
                        "decision": decision,
                        "resolution": record,
                    },
                    error=None,
                )
                await self.enqueue(job_id)
            else:
                self.storage.update(
                    job_id,
                    status="blocked",
                    checkpoint=checkpoint,
                    result={"reason": "human_decision_rejected", "decision": decision, "resolution": record},
                    error=None,
                )
        elif action == "approve":
            approved = list(checkpoint.get("approved_decisions") or [])
            if key and key not in approved:
                approved.append(key)
            checkpoint["approved_decisions"] = approved[-20:]
            self.storage.update(
                job_id,
                status="queued",
                checkpoint=checkpoint,
                result={"reason": "human_decision_approved", "decision": decision, "resolution": record},
                error=None,
            )
            await self.enqueue(job_id)
        else:
            raise RuntimeError(f"Unsupported decision action: {action}")

        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    async def _resolve_review_repair_churn_decision(
        self,
        *,
        job_id: str,
        row: dict[str, Any],
        checkpoint: dict[str, Any],
        pending: dict[str, Any],
        decision: dict[str, Any],
        key: str,
        action: str,
        note: str,
    ) -> dict[str, Any]:
        epoch = validate_review_repair_churn_epoch(checkpoint)
        gate = dict(checkpoint.get(REVIEW_REPAIR_CHURN_GATE_KEY) or {})
        if epoch is None or not gate:
            raise RuntimeError("Review-repair churn decision is missing its durable gate")
        request_id = str(epoch.get("request_id") or "")
        generation = int(epoch.get("generation") or 0)
        expected_key = review_repair_churn_decision_identity(request_id, generation)
        if (
            key != expected_key
            or str(gate.get("request_id") or "") != request_id
            or int(gate.get("generation", -1)) != generation
            or str(pending.get("key") or "") != expected_key
        ):
            raise RuntimeError(
                "Review-repair churn decision identity no longer matches its request generation"
            )

        history = list(checkpoint.get("decision_history") or [])
        record = {
            "key": key,
            "action": action,
            "note": note,
            "source": REVIEW_REPAIR_CHURN_DECISION_SOURCE,
            "request_id": request_id,
            "generation": generation,
        }
        history.append(record)
        checkpoint["decision_history"] = history[-20:]
        checkpoint.pop("pending_decision", None)

        if action == "reject":
            self.storage.update(
                job_id,
                status="blocked",
                checkpoint=checkpoint,
                result={
                    "reason": REVIEW_REPAIR_CHURN_RESULT_REASON,
                    "source": REVIEW_REPAIR_CHURN_DECISION_SOURCE,
                    "decision": decision,
                    "evidence": deepcopy(gate),
                    "resolution": record,
                },
                error=None,
            )
        elif action == "approve":
            progress = dict(row.get("progress") or self._new_progress())
            prior = {
                "generation": generation,
                "baseline": deepcopy(epoch.get("baseline") or {}),
                "authorized_at": now().isoformat(),
                "decision_key": key,
                "note": note,
            }
            authorizations = [
                deepcopy(item)
                for item in (epoch.get("authorizations") or [])
                if isinstance(item, dict)
            ]
            authorizations.append(prior)
            epoch["authorizations"] = authorizations[-20:]
            epoch["generation"] = generation + 1
            epoch["baseline"] = {
                "repair_iterations": max(
                    0, int(progress.get("repair_iterations", 0) or 0)
                ),
                "verification_attempts": max(
                    0, int(progress.get("verification_attempts", 0) or 0)
                ),
            }
            epoch["started_at"] = now().isoformat()
            epoch["baseline_origin"] = "human_authorized_window"
            for field in (
                "latest_diff_hash",
                "latest_review_summary",
                "latest_verification_summary",
            ):
                epoch.pop(field, None)
            checkpoint[REVIEW_REPAIR_CHURN_EPOCH_KEY] = epoch
            checkpoint.pop(REVIEW_REPAIR_CHURN_GATE_KEY, None)
            self.storage.update(
                job_id,
                status="queued",
                checkpoint=checkpoint,
                result={
                    "reason": "review_repair_churn_authorized",
                    "source": REVIEW_REPAIR_CHURN_DECISION_SOURCE,
                    "request_id": request_id,
                    "generation": generation + 1,
                    "resolution": record,
                },
                error=None,
            )
            await self.enqueue(job_id)
        else:
            raise RuntimeError(f"Unsupported decision action: {action}")

        updated = self.storage.get(job_id)
        assert updated is not None
        return updated

    def _progress_for_reassessment(
        self,
        *,
        job_id: str,
        checkpoint: dict[str, Any],
        progress: dict[str, Any],
    ) -> dict[str, Any]:
        effective, changed = effective_reassessment_progress(
            checkpoint,
            progress,
        )
        if changed:
            self.storage.update(job_id, checkpoint=checkpoint)
        return effective

    @staticmethod
    def _new_progress() -> dict[str, Any]:
        return {
            "iteration": 0, "repair_iterations": 0, "escalations": 0,
            "provider_failovers": 0, "model_failovers": 0, "model_calls": 0,
            "tool_calls": 0, "test_runs": 0, "input_tokens": 0, "output_tokens": 0,
            "elapsed_minutes": 0.0, "cost_usd": 0.0,
            "changed_files": 0, "failure_fingerprints": [], "diff_hashes": [],
            "progress_markers": [], "tests_passed": False,
            "required_checks_passed": False, "material_change_present": False,
            "agent_succeeded": False, "last_agent_failure_kind": None,
            "unexpected_scope": False, "important_decision_flags": [],
            "provider_failures": [], "agent_attempts": [], "pm_reassessments": 0,
        }

    def _ensure_review_repair_churn_epoch(
        self,
        *,
        job_id: str,
        checkpoint: dict[str, Any],
        progress: dict[str, Any],
    ) -> bool:
        try:
            migrated = ensure_legacy_epoch(checkpoint, progress)
        except ReviewRepairChurnIntegrityError as exc:
            self._block_review_repair_churn_integrity(job_id, checkpoint, progress, exc)
            raise ReviewRepairChurnPaused() from exc
        if migrated:
            self.storage.update(job_id, checkpoint=checkpoint, progress=progress)
        return migrated

    def _block_review_repair_churn_integrity(
        self,
        job_id: str,
        checkpoint: dict[str, Any],
        progress: dict[str, Any],
        error: ReviewRepairChurnIntegrityError,
    ) -> None:
        # No replacement epoch/gate or approval identity can be inferred from
        # inconsistent state. Preserve it for inspection instead of re-arming.
        self.storage.update(
            job_id,
            status="blocked",
            checkpoint=checkpoint,
            progress=progress,
            result={
                "reason": REVIEW_REPAIR_CHURN_RESULT_REASON,
                "source": REVIEW_REPAIR_CHURN_DECISION_SOURCE,
                "evidence": review_repair_churn_integrity_evidence(checkpoint, error),
            },
            error=None,
        )

    def _review_repair_churn_guard(
        self,
        *,
        job_id: str,
        checkpoint: dict[str, Any],
        progress: dict[str, Any],
    ) -> bool:
        try:
            hit, evidence = review_repair_churn_evidence(checkpoint, progress)
        except ReviewRepairChurnIntegrityError as exc:
            self._block_review_repair_churn_integrity(job_id, checkpoint, progress, exc)
            return True
        if not hit:
            return False
        key = str(evidence["decision_key"])
        decision = {
            "required": True,
            "triggers": [key],
            "reason": (
                "Review-repair activity reached its bounded anomaly window; "
                "another model or deterministic verification cycle requires "
                "an exact Human Owner authorization."
            ),
        }
        checkpoint[REVIEW_REPAIR_CHURN_GATE_KEY] = deepcopy(evidence)
        checkpoint["pending_decision"] = {
            "key": key,
            "decision": decision,
            "source": REVIEW_REPAIR_CHURN_DECISION_SOURCE,
            "request_id": evidence["request_id"],
            "generation": evidence["generation"],
        }
        self.storage.update(
            job_id,
            status="waiting_human",
            progress=progress,
            checkpoint=checkpoint,
            result={
                "reason": REVIEW_REPAIR_CHURN_RESULT_REASON,
                "source": REVIEW_REPAIR_CHURN_DECISION_SOURCE,
                "decision": decision,
                "evidence": evidence,
            },
            error=None,
        )
        return True

    @classmethod
    def _remaining_seconds(
        cls,
        strategy: dict[str, Any],
        started: float,
        per_call_cap: int,
    ) -> int:
        # Effective adaptive WorkOrders treat total elapsed wall time as
        # telemetry/calibration. Keep each individual operation bounded by its
        # existing phase cap so one command/model call still cannot hang forever.
        if cls._adaptive_work_shape_nonblocking(strategy):
            return max(10, int(per_call_cap))

        total = int(strategy["budget"]["max_wall_time_minutes"] * 60)
        remaining = total - int(time.monotonic() - started)
        if remaining <= 0:
            raise RuntimeError("Job wall-time budget exhausted before next operation")
        return max(10, min(per_call_cap, remaining))

    @staticmethod
    def _update_elapsed(progress: dict[str, Any], started: float) -> None:
        progress["elapsed_minutes"] = round((time.monotonic() - started) / 60.0, 3)

    @staticmethod
    def _adaptive_work_shape_nonblocking(strategy: dict[str, Any]) -> bool:
        """Whether static execution counters are telemetry rather than stop gates.

        This includes cumulative input/output token totals and total elapsed
        wall time on effective adaptive WorkOrders. Individual operation
        timeouts, hard cost, provider quota/context enforcement, scope and
        behavioral circuit-breakers remain bounded. Missing markers fail closed
        so persisted/legacy routes retain historical behavior.
        """
        return str(strategy.get("budget_mode") or "") == "adaptive"

    @classmethod
    def _pre_model_budget_reason(
        cls,
        progress: dict[str, Any],
        strategy: dict[str, Any],
        *,
        include_iteration: bool,
    ) -> str | None:
        budget = strategy["budget"]

        # Hard monetary cost remains a standalone material ceiling. Cumulative
        # input/output token totals are telemetry on effective adaptive jobs:
        # they are not per-request context limits and eventually grow for any
        # sufficiently long healthy task.
        checks = [
            (progress["cost_usd"] >= float(budget["hard_cost_usd"]), "hard cost budget exhausted"),
        ]

        # Static counters, including cumulative token totals and total elapsed
        # wall time, are telemetry on effective adaptive jobs. Explicit
        # legacy-hard routes preserve the historical strict token/wall/work-shape
        # ceilings.
        if not cls._adaptive_work_shape_nonblocking(strategy):
            checks.extend([
                (progress["input_tokens"] >= int(budget["max_input_tokens"]), "input-token budget exhausted"),
                (progress["output_tokens"] >= int(budget["max_output_tokens"]), "output-token budget exhausted"),
                (progress["elapsed_minutes"] >= float(budget["max_wall_time_minutes"]), "wall-time budget exhausted"),
                (progress["model_calls"] >= int(budget["max_model_calls"]), "model-call budget exhausted"),
                (progress["tool_calls"] >= int(budget["max_tool_calls"]), "tool-call budget exhausted"),
                (progress["test_runs"] >= int(budget["max_test_runs"]), "test-run budget exhausted"),
                (progress["repair_iterations"] >= int(budget["max_repair_iterations"]), "repair budget exhausted"),
            ])
            if include_iteration:
                checks.append(
                    (progress["iteration"] >= int(budget["max_iterations"]), "iteration budget exhausted")
                )

        for hit, reason in checks:
            if hit:
                return reason
        return None

    @staticmethod
    def _record_usage(progress: dict[str, Any], model_id: str, raw_usage: dict[str, Any] | None) -> None:
        usage = normalize_usage(raw_usage)
        progress["input_tokens"] += int(usage["input_tokens"])
        progress["output_tokens"] += int(usage["output_tokens"])
        progress["cost_usd"] = round(float(progress.get("cost_usd", 0.0)) + estimated_cost_usd(model_id, raw_usage), 8)

    def _cancelled(self, job_id: str) -> bool:
        current = self.storage.get(job_id)
        return bool(current and current["status"] == "cancelled")

    @staticmethod
    def _decision_approved(checkpoint: dict[str, Any], decision: dict[str, Any] | None) -> bool:
        key = decision_key(decision)
        return bool(key) and key in set(checkpoint.get("approved_decisions") or [])

    def _pause_for_decision(self, *, job_id: str, checkpoint: dict[str, Any], progress: dict[str, Any], decision: dict[str, Any], route_history: list[dict[str, Any]], source: str) -> None:
        key = decision_key(decision)
        checkpoint["pending_decision"] = {"key": key, "decision": decision, "source": source}
        checkpoint["route_history"] = route_history
        self.storage.update(
            job_id,
            status="waiting_human",
            progress=progress,
            checkpoint=checkpoint,
            result={"reason": "human_decision_required", "decision": decision, "source": source, "route_history": route_history},
            error=None,
        )

    def _block(self, *, job_id: str, progress: dict[str, Any], checkpoint: dict[str, Any], reason: str, last_failure: str | None = None, **extra: Any) -> None:
        result = {
            "reason": reason,
            "last_failure": last_failure,
            "route_history": checkpoint.get("route_history", []),
            "agent_attempts": progress.get("agent_attempts", []),
            **extra,
        }
        self.storage.update(job_id, status="blocked", progress=progress, checkpoint=checkpoint, result=result, error=None)

    @staticmethod
    def _mark_provider_failure(provider_state: dict[str, Any], choice: dict[str, Any], kind: str) -> None:
        key = provider_failure_state_key(choice, kind)
        state = dict(provider_state.get(key) or {})
        state.update({
            "healthy": False,
            "available": False,
            "error_rate": 1.0,
            "failure_kind": str(kind or "provider_unavailable"),
            "failed_at": now().isoformat(),
        })
        if kind in {"quota_exhausted", "rate_limited"}:
            state["quota_pressure"] = 1.0
        provider_state[key] = state

    @staticmethod
    def _mark_model_failure(provider_state: dict[str, Any], choice: dict[str, Any], reason: str) -> None:
        model_id = str(choice.get("id") or "")
        if not model_id:
            return
        state = dict(provider_state.get(model_id) or {})
        state.update({"healthy": False, "available": False, "error_rate": 1.0})
        provider_state[model_id] = state

    @staticmethod
    def _rehabilitate_successful_choice(
        provider_state: dict[str, Any],
        choice: dict[str, Any],
    ) -> list[str]:
        """Remove only stale health markers contradicted by one successful run."""
        removed: list[str] = []
        provider = str(choice.get("provider") or "").strip()
        model_id = str(choice.get("id") or "").strip()
        for key in (
            f"provider:{provider}" if provider else "",
            model_id,
        ):
            if key and key in provider_state:
                provider_state.pop(key, None)
                removed.append(key)
        return removed

    @staticmethod
    def _record_agent_attempt(progress: dict[str, Any], choice: dict[str, Any], run: Any) -> None:
        attempts = progress.setdefault("agent_attempts", [])
        attempts.append({
            "iteration": progress.get("iteration", 0),
            "model": choice.get("id"),
            "provider": choice.get("provider"),
            "adapter": choice.get("adapter"),
            "returncode": run.returncode,
            "failure_kind": run.failure_kind,
            "output_excerpt": (run.output or "")[-4000:],
            "stderr_excerpt": (run.stderr or "")[-4000:],
            "usage": normalize_usage(run.usage),
        })
        if len(attempts) > 12:
            del attempts[:-12]

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
        if (
            not self._adaptive_work_shape_nonblocking(strategy)
            and progress.get("model_failovers", 0) >= int(strategy["budget"].get("max_model_failovers", 2))
        ):
            return None, None
        # Adaptive model-failover counts are telemetry. Durable failed-model state
        # makes recovery finite because Router must select a distinct eligible model.
        self._mark_model_failure(provider_state, current_choice, reason)
        payload = dict(route_payload)
        payload["provider_state"] = provider_state
        try:
            reroute = await self.router.route(payload)
        except Exception:
            return None, None
        candidate = reroute.get("strategy", {}).get(role)
        if not candidate or candidate.get("id") == current_choice.get("id"):
            return None, reroute
        progress["model_failovers"] = int(progress.get("model_failovers", 0)) + 1
        return candidate, reroute

    async def _provider_failover(self, *, route_payload: dict[str, Any], provider_state: dict[str, Any], current_choice: dict[str, Any], failure_kind: str, progress: dict[str, Any], strategy: dict[str, Any], role: str = "executor") -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        # Provider-failover counts are durable telemetry/planning priors, not a
        # Human Owner continuation gate. Each observed failure is first written
        # into provider/model/quota health and Router must return a distinct
        # eligible choice. Preserved failed-capacity state makes this sequence
        # finite; no eligible route or a contradictory same-choice route still
        # fails closed without resetting the consumed counter.
        self._mark_provider_failure(provider_state, current_choice, failure_kind)
        payload = dict(route_payload)
        payload["provider_state"] = provider_state
        try:
            reroute = await self.router.route(payload)
        except Exception:
            return None, None
        candidate = reroute.get("strategy", {}).get(role)
        if not candidate or candidate.get("id") == current_choice.get("id"):
            return None, reroute
        progress["provider_failovers"] = int(progress.get("provider_failovers", 0)) + 1
        return candidate, reroute

    @staticmethod
    def _effective_route(route: dict[str, Any], executor_choice: dict[str, Any]) -> dict[str, Any]:
        value = deepcopy(route)
        value.setdefault("strategy", {})["executor"] = deepcopy(executor_choice)
        return value
