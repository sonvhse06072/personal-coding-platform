from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .adapters import build_adapter
from .capability_context import agent_verification_capability_context
from .config import project_config
from .engine_core import RuntimeEngineCore
from .evidence_packs import developer_repair_evidence_pack, pm_evidence_pack
from .fingerprint import failure_fingerprint
from .incident_learning import incident_learning_candidate
from .model_capabilities import validate_model_choice
from .preview import ProjectPreviewManager, ready_preview_context
from .pm_reassessment import (
    baseline_covered_protected_authorized_signals,
    changed_file_reassessment_state,
    has_pm_changed_file_authorization,
    run_pm_reassessment,
    validate_baseline_covered_protected_approval,
)
from .prompts import evaluator_prompt, execution_prompt, planning_prompt
from .developer_permissions import trusted_local_developer_enabled
from .repo import analyze_repo, commit_changes, diff_state
from .review_repair_churn import record_observation as record_review_repair_churn_observation
from .review import (
    mark_actioned_review_findings,
    parse_review_output,
    record_review_telemetry,
    review_report_summary,
    should_run_review,
)
from .scope_guard import changed_path_protected_signals
from .state import (
    checkpoint_from_row,
    clear_failure_context,
    existing_repo_analysis,
    merge_progress,
    review_repair_prompt_failure,
    semantic_response_only_turn_allowed,
    set_failure_context,
    validate_workspace,
)
from .work_order_checkpoints import orchestrator_launch, verification_checkpoint_summary

_VALID_WORKSPACE_MODES = {"direct", "isolated_clone"}


def reusable_passed_review(
    checkpoint: dict[str, Any],
    verification: dict[str, Any],
    *,
    diff_hash: str,
) -> bool:
    marker = checkpoint.get("reuse_passed_review_once")
    review = checkpoint.get("last_review_report")
    return bool(
        isinstance(marker, dict)
        and verification.get("passed") is True
        and str(marker.get("diff_hash") or "") == str(diff_hash or "")
        and isinstance(review, dict)
        and str(review.get("verdict") or "") == "pass"
        and review.get("protocol_valid") is not False
    )


def invalidate_review_reuse_on_verification_failure(
    checkpoint: dict[str, Any],
    verification: dict[str, Any],
) -> bool:
    if (
        isinstance(checkpoint.get("reuse_passed_review_once"), dict)
        and verification.get("passed") is not True
    ):
        checkpoint.pop("reuse_passed_review_once", None)
        return True
    return False


def effective_workspace_mode(
    job: dict[str, Any],
    checkpoint: dict[str, Any],
    project: dict[str, Any],
    workspace_root: Path,
) -> str:
    """Keep an existing workspace on the durable mode that created it.

    Live project configuration governs only workspace acquisition for jobs that
    do not yet own a workspace. Reinterpreting a persisted workspace after a
    config change can violate path validation and direct-project lease safety.
    """
    live_mode = str(
        ((project.get("runtime") or {}).get("workspace_mode") or "isolated_clone")
    )
    if live_mode not in _VALID_WORKSPACE_MODES:
        raise RuntimeError(f"Unsupported project workspace mode: {live_mode}")

    if not job.get("workspace"):
        return live_mode

    persisted_mode = str(checkpoint.get("workspace_mode") or "")
    if persisted_mode in _VALID_WORKSPACE_MODES:
        return persisted_mode

    workspace = Path(str(job["workspace"])).resolve()
    project_path = Path(str(project.get("path") or "")).resolve()
    isolated_path = (workspace_root.resolve() / str(job["id"])).resolve()

    if workspace == project_path:
        return "direct"
    if workspace == isolated_path:
        return "isolated_clone"

    raise RuntimeError(
        "Persisted workspace is missing a valid durable workspace mode "
        "and its path cannot be safely classified"
    )



_DETERMINISTIC_VERIFICATION_STREAK_KEY = "deterministic_verification_failure_streak"


def deterministic_verification_failure_signature(
    verification: dict[str, Any],
    *,
    diff_hash: str,
) -> str:
    """Return a stable signature for failed deterministic verification commands.

    Volatile stdout/stderr is deliberately excluded so repeated failures of the
    same command on the same diff cannot evade the circuit breaker merely
    because PHPUnit timing/order/output text changed.
    """

    failures: list[dict[str, Any]] = []
    for raw_phase in verification.get("phases") or []:
        phase = dict(raw_phase) if isinstance(raw_phase, dict) else {}
        if bool(phase.get("passed", False)):
            continue
        failed_commands: list[dict[str, Any]] = []
        for raw_command in phase.get("commands") or []:
            if isinstance(raw_command, dict):
                returncode = raw_command.get("returncode")
                timed_out = bool(raw_command.get("timed_out", False))
                if returncode == 0 and not timed_out:
                    continue
                failed_commands.append(
                    {
                        "command": str(raw_command.get("command") or ""),
                        "returncode": returncode,
                        "timed_out": timed_out,
                    }
                )
            else:
                failed_commands.append(
                    {
                        "command": str(raw_command),
                        "returncode": None,
                        "timed_out": False,
                    }
                )
        failures.append(
            {
                "phase": str(phase.get("phase") or ""),
                "commands": failed_commands,
            }
        )
    stable = {
        "diff_hash": str(diff_hash or ""),
        "failures": failures,
    }
    return failure_fingerprint(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)
    )


def record_deterministic_verification_failure_streak(
    checkpoint: dict[str, Any],
    verification: dict[str, Any],
    *,
    diff_hash: str,
    limit: int,
) -> dict[str, Any] | None:
    """Track repeated deterministic failures independently from review churn."""

    if bool(verification.get("passed", False)):
        checkpoint.pop(_DETERMINISTIC_VERIFICATION_STREAK_KEY, None)
        return None

    signature = deterministic_verification_failure_signature(
        verification,
        diff_hash=diff_hash,
    )
    previous = checkpoint.get(_DETERMINISTIC_VERIFICATION_STREAK_KEY)
    previous = dict(previous) if isinstance(previous, dict) else {}
    if (
        str(previous.get("diff_hash") or "") == str(diff_hash or "")
        and str(previous.get("signature") or "") == signature
    ):
        count = int(previous.get("count") or 0) + 1
    else:
        count = 1

    failing_phases = [
        str(item.get("phase") or "")
        for item in verification.get("phases") or []
        if isinstance(item, dict) and not bool(item.get("passed", False))
    ]
    state = {
        "diff_hash": str(diff_hash or ""),
        "signature": signature,
        "count": count,
        "limit": max(1, int(limit)),
        "failing_phases": failing_phases,
        "verification_attempt": int(verification.get("verification_attempt") or 0),
    }
    checkpoint[_DETERMINISTIC_VERIFICATION_STREAK_KEY] = state
    return state


class RuntimeEngine(RuntimeEngineCore):
    async def run_job(self, job_id: str) -> None:
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")
        if job["status"] != "queued":
            return
        if orchestrator_launch(job):
            job = self.storage.claim_orchestrated_launch(job_id)
            if job is None:
                return

        project = project_config(job["project_id"])
        runtime_cfg = project.get("runtime", {}) or {}
        task = dict(job["task"])
        checkpoint = checkpoint_from_row(job)
        persisted_workspace_mode = str(checkpoint.get("workspace_mode") or "")
        legacy_workspace_mode_inferred = bool(
            job.get("workspace")
            and persisted_workspace_mode not in _VALID_WORKSPACE_MODES
        )
        workspace_mode = effective_workspace_mode(
            job,
            checkpoint,
            project,
            self.workspace_root,
        )
        if workspace_mode == "direct":
            approved_direct_root = os.getenv("CODING_DIRECT_PROJECT_ROOT", "").strip()
            if not approved_direct_root:
                raise RuntimeError("CODING_DIRECT_PROJECT_ROOT is not configured")
            if Path(project["path"]).resolve() != Path(approved_direct_root).resolve():
                raise RuntimeError(
                    "Direct project path does not match the exact mounted CODING_DIRECT_PROJECT_ROOT"
                )
        progress = merge_progress(self._new_progress(), job.get("progress"))
        self._ensure_review_repair_churn_epoch(
            job_id=job_id,
            checkpoint=checkpoint,
            progress=progress,
        )
        started = time.monotonic() - float(progress.get("elapsed_minutes", 0.0)) * 60.0
        hints = dict(checkpoint.get("hints") or {})
        provider_state = dict(checkpoint.get("provider_state") or {})

        if workspace_mode == "direct":
            if job.get("workspace"):
                lease = self.storage.project_lease(str(job["project_id"]))
                if (
                    not lease
                    or str(lease.get("state") or "") != "active"
                    or str(lease.get("owner_job_id") or "") != job_id
                ):
                    raise RuntimeError("Persisted direct workspace is missing its exact active project lease")
            else:
                lease = self.storage.acquire_project_lease(str(job["project_id"]), job_id)
                try:
                    await ProjectPreviewManager(
                        self.storage,
                        self.ddev,
                    ).handoff_to_job(str(job["project_id"]), job_id)
                except Exception:
                    self.storage.release_project_lease(str(job["project_id"]), job_id)
                    raise
            checkpoint["workspace_mode"] = "direct"
            checkpoint["project_lease_generation"] = int(lease.get("generation") or 0)
        else:
            checkpoint["workspace_mode"] = "isolated_clone"
            checkpoint.pop("project_lease_generation", None)

        if job.get("workspace"):
            workspace = validate_workspace(
                self.workspace_root,
                job_id,
                job["workspace"],
                workspace_mode=workspace_mode,
                project_path=project.get("path"),
            )
            branch = str(job.get("branch") or "")
            source_commit = str(job.get("source_commit") or "")
            if not branch or not source_commit:
                raise RuntimeError("Persisted workspace is missing branch/source commit metadata")
            if workspace_mode == "direct":
                current_branch = subprocess.run(
                    ["git", "-C", str(workspace), "branch", "--show-current"],
                    text=True,
                    capture_output=True,
                )
                if current_branch.returncode != 0 or current_branch.stdout.strip() != branch:
                    raise RuntimeError("Direct workspace branch changed outside the owning job")
            if legacy_workspace_mode_inferred:
                self.storage.update(job_id, checkpoint=checkpoint)
        else:
            acquired_direct_lease = workspace_mode == "direct"
            try:
                ws = await self.ddev.create_workspace(
                    job_id=job_id, project_id=job["project_id"], ref=job.get("source_commit")
                )
            except Exception:
                if acquired_direct_lease:
                    self.storage.release_project_lease(str(job["project_id"]), job_id)
                raise
            workspace = Path(ws["workspace"]).resolve()
            branch = ws["branch"]
            source_commit = ws["source_commit"]
            if str(ws.get("workspace_mode") or "").startswith("direct") != (workspace_mode == "direct"):
                if acquired_direct_lease:
                    self.storage.release_project_lease(str(job["project_id"]), job_id)
                raise RuntimeError("Executor workspace mode does not match project configuration")
            self.storage.update(
                job_id,
                workspace=str(workspace),
                branch=branch,
                source_commit=source_commit,
                checkpoint=checkpoint,
            )

        repo_analysis = existing_repo_analysis(job)
        enriched_task = task
        if repo_analysis is None:
            repo_analysis, enriched_task = analyze_repo(workspace, task, hints)
            self.storage.update(job_id, repo_analysis=repo_analysis, task=enriched_task)

        route_payload = {
            "job_id": job_id,
            "project_id": job["project_id"],
            "repository": job["project_id"],
            "source_commit": source_commit,
            "task": enriched_task,
            "repo": repo_analysis,
            "provider_state": provider_state,
        }
        route = job.get("route")
        if not route:
            self.storage.update(job_id, status="routing", progress=progress, checkpoint=checkpoint)
            route = await self.router.route(route_payload)
            self.storage.update(job_id, route=route)
        strategy = route["strategy"]

        if self._review_repair_churn_guard(
            job_id=job_id,
            checkpoint=checkpoint,
            progress=progress,
        ):
            return

        route_history: list[dict[str, Any]] = list(checkpoint.get("route_history") or [])
        if not route_history:
            route_history.append({"reason": "initial", "route": route})
        checkpoint["route_history"] = route_history
        checkpoint["provider_state"] = provider_state

        initial_decision = strategy.get("human_decision") or {}
        if initial_decision.get("required") and not self._decision_approved(checkpoint, initial_decision):
            self._pause_for_decision(
                job_id=job_id,
                checkpoint=checkpoint,
                progress=progress,
                decision=initial_decision,
                route_history=route_history,
                source="initial_route",
            )
            return

        if (
            workspace_mode == "isolated_clone"
            and project.get("ddev", {}).get("enabled", False)
            and (workspace / ".ddev").exists()
        ):
            safe_name = re.sub(r"[^a-z0-9-]", "-", f"cp-{job_id[:10]}")
            (workspace / ".ddev" / "config.coding-platform.yaml").write_text(
                f"name: {safe_name}\n", encoding="utf-8"
            )

        if job.get("dry_run"):
            self.storage.update(
                job_id,
                status="completed",
                result={"dry_run": True, "route": route, "workspace": str(workspace), "branch": branch},
                progress=progress,
                checkpoint=checkpoint,
            )
            return

        max_diff = int(runtime_cfg.get("max_diff_bytes", 500000))
        plan: str | None = checkpoint.get("plan")

        if strategy.get("planner") and not plan:
            choice = dict(checkpoint.get("planner_choice") or strategy["planner"])
            while True:
                self._update_elapsed(progress, started)
                budget_reason = self._pre_model_budget_reason(progress, strategy, include_iteration=False)
                if budget_reason:
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="planner_budget_exhausted",
                        last_failure=budget_reason,
                    )
                    return
                validate_model_choice(choice)
                progress["model_calls"] += 1
                checkpoint["planner_choice"] = choice
                checkpoint["provider_state"] = provider_state
                self.storage.update(job_id, status="planning", progress=progress, checkpoint=checkpoint)
                result = await build_adapter(
                    choice["adapter"], choice["model"], choice.get("reasoning_effort")
                ).run(
                    workspace=workspace,
                    prompt=planning_prompt(task=enriched_task, repo_analysis=repo_analysis),
                    mode="plan",
                    timeout=self._remaining_seconds(strategy, started, 1800),
                )
                self._record_usage(progress, choice["id"], result.usage)
                self._update_elapsed(progress, started)
                self.storage.update(job_id, progress=progress)
                if result.provider_failed:
                    progress["provider_failures"].append({
                        "model": choice["id"],
                        "provider": choice.get("provider"),
                        "kind": result.failure_kind,
                    })
                    next_choice, reroute = await self._provider_failover(
                        route_payload=route_payload,
                        provider_state=provider_state,
                        current_choice=choice,
                        failure_kind=result.failure_kind or "provider_unavailable",
                        progress=progress,
                        strategy=strategy,
                        role="planner",
                    )
                    checkpoint["provider_state"] = provider_state
                    if next_choice:
                        route_history.append({
                            "reason": f"planner_provider_failover:{choice['id']}:{result.failure_kind}",
                            "route": reroute,
                        })
                        choice = next_choice
                        checkpoint["planner_choice"] = choice
                        checkpoint["route_history"] = route_history
                        self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                        continue
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="planner_provider_failure_without_fallback",
                        last_failure=result.failure_message or result.stderr or result.output,
                    )
                    return
                if result.returncode != 0:
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="planner_failed",
                        last_failure=result.stderr or result.output,
                    )
                    return
                removed_health = self._rehabilitate_successful_choice(
                    provider_state,
                    choice,
                )
                if removed_health:
                    checkpoint["provider_state"] = provider_state
                    history = list(
                        checkpoint.get("provider_success_rehabilitations") or []
                    )
                    history.append({
                        "stage": "planner",
                        "model": str(choice.get("id") or ""),
                        "provider": str(choice.get("provider") or ""),
                        "removed_keys": removed_health,
                    })
                    checkpoint["provider_success_rehabilitations"] = history[-20:]
                plan = result.output[-20000:]
                checkpoint["plan"] = plan
                checkpoint.pop("planner_choice", None)
                self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                break

        if project.get("ddev", {}).get("enabled", False):
            commands = project.get("ddev", {}).get("preflight", []) or []
            if (
                not self._adaptive_work_shape_nonblocking(strategy)
                and progress["tool_calls"] + len(commands) > int(strategy["budget"]["max_tool_calls"])
            ):
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="preflight_budget_exhausted",
                    last_failure="tool-call budget would be exceeded by preflight",
                )
                return
            self.storage.update(job_id, status="verifying", progress=progress, checkpoint=checkpoint)
            preflight = await self.ddev.phase(
                job_id=job_id,
                project_id=job["project_id"],
                workspace=str(workspace),
                phase="preflight",
                timeout_seconds=self._remaining_seconds(strategy, started, 900),
            )
            progress["tool_calls"] += len(preflight.get("commands", []))
            self._update_elapsed(progress, started)
            self.storage.update(job_id, progress=progress)
            if not preflight.get("passed", False):
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="preflight_failed",
                    last_failure=str(preflight)[-30000:],
                )
                return

        executor_choice = dict(checkpoint.get("executor_choice") or strategy["executor"])
        last_failure: str | None = checkpoint.get("last_failure")

        while True:
            if self._cancelled(job_id):
                return
            self._update_elapsed(progress, started)
            if self._review_repair_churn_guard(
                job_id=job_id,
                checkpoint=checkpoint,
                progress=progress,
            ):
                return
            budget_reason = self._pre_model_budget_reason(progress, strategy, include_iteration=True)
            if budget_reason:
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="execution_budget_exhausted",
                    last_failure=budget_reason,
                )
                return

            turn_start_diff = diff_state(
                workspace,
                max_diff,
                base_ref=source_commit,
            )
            turn_start_diff_hash = str(turn_start_diff.get("diff_hash") or "")

            validate_model_choice(executor_choice)
            progress["iteration"] += 1
            progress["model_calls"] += 1
            checkpoint.update({
                "executor_choice": executor_choice,
                "last_failure": last_failure,
                "provider_state": provider_state,
                "route_history": route_history,
            })
            self.storage.update(job_id, status="executing", progress=progress, checkpoint=checkpoint)
            adapter = build_adapter(
                executor_choice["adapter"], executor_choice["model"], executor_choice.get("reasoning_effort")
            )
            preview_context = await ready_preview_context(
                self.storage,
                self.ddev,
                job_id,
            )
            run = await adapter.run(
                workspace=workspace,
                prompt=execution_prompt(
                    task=enriched_task,
                    route=route,
                    repo_analysis=repo_analysis,
                    plan=plan,
                    failure=review_repair_prompt_failure(checkpoint, last_failure),
                    work_order=checkpoint.get("work_order"),
                    baseline=checkpoint.get("project_baseline"),
                    collaboration_context=checkpoint.get("collaboration_context"),
                    preview_context=preview_context,
                    capability_context=agent_verification_capability_context(
                        adapter,
                        mode="execute",
                        project=project,
                    ),
                    trusted_local_developer=trusted_local_developer_enabled(
                        workspace,
                        "execute",
                        adapter=str(executor_choice.get("adapter") or ""),
                    ),
                ),
                mode="execute",
                timeout=self._remaining_seconds(strategy, started, 2400),
            )
            self._record_usage(progress, executor_choice["id"], run.usage)
            self._record_agent_attempt(progress, executor_choice, run)
            progress["agent_succeeded"] = run.returncode == 0
            progress["last_agent_failure_kind"] = run.failure_kind
            self._update_elapsed(progress, started)
            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

            if run.provider_failed:
                failure_text = run.failure_message or run.stderr or run.output or f"{executor_choice['id']} provider failure"
                last_failure = (
                    f"Provider failure ({run.failure_kind}) from {executor_choice['id']}:\n{failure_text}"
                )[-30000:]
                fp = failure_fingerprint(last_failure)
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(f"provider:{executor_choice['id']}:{run.failure_kind}")
                progress["provider_failures"].append({
                    "model": executor_choice["id"],
                    "provider": executor_choice.get("provider"),
                    "kind": run.failure_kind,
                })
                next_executor, reroute = await self._provider_failover(
                    route_payload=route_payload,
                    provider_state=provider_state,
                    current_choice=executor_choice,
                    failure_kind=run.failure_kind or "provider_unavailable",
                    progress=progress,
                    strategy=strategy,
                )
                checkpoint["provider_state"] = provider_state
                set_failure_context(
                    checkpoint,
                    kind="route_transient",
                    source="provider",
                    message=last_failure,
                )
                if next_executor:
                    route_history.append({
                        "reason": f"provider_failover:{executor_choice['id']}:{run.failure_kind}",
                        "route": reroute,
                    })
                    executor_choice = next_executor
                    checkpoint["executor_choice"] = executor_choice
                    checkpoint["route_history"] = route_history
                    self.storage.update(job_id, status="routing", progress=progress, checkpoint=checkpoint)
                    continue
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="provider_failure_without_fallback",
                    last_failure=last_failure,
                )
                return

            if run.returncode != 0:
                last_failure = f"Agent command failed ({run.returncode}):\n{run.stderr}\n{run.output}"[-30000:]
            else:
                removed_health = self._rehabilitate_successful_choice(
                    provider_state,
                    executor_choice,
                )
                if removed_health:
                    checkpoint["provider_state"] = provider_state
                    history = list(
                        checkpoint.get("provider_success_rehabilitations") or []
                    )
                    history.append({
                        "stage": "executor",
                        "model": str(executor_choice.get("id") or ""),
                        "provider": str(executor_choice.get("provider") or ""),
                        "removed_keys": removed_health,
                    })
                    checkpoint["provider_success_rehabilitations"] = history[-20:]
            self.storage.update(
                job_id,
                status="verifying",
                progress=progress,
                checkpoint=checkpoint,
            )

            diff = diff_state(
                workspace,
                max_diff,
                base_ref=source_commit,
            )
            progress["changed_files"] = diff["changed_file_count"]
            progress["material_change_present"] = diff["changed_file_count"] > 0
            progress["diff_hashes"].append(diff["diff_hash"])

            # File count is only a work-shape signal on adaptive routes. Actual
            # sensitive changed paths remain an independent decision boundary.
            path_signals = changed_path_protected_signals(
                diff.get("changed_files") or [],
                checkpoint,
            )
            # important_decision_flags describes the current diff, not
            # historical diffs. Decision history is persisted separately in
            # checkpoint; carrying removed path signals forward would create
            # false Human/PM boundaries after a successful repair.
            exact_protected_authorized = baseline_covered_protected_authorized_signals(
                checkpoint,
                diff_hash=str(diff.get("diff_hash") or ""),
                current_signals=path_signals,
                baseline_revision=str(
                    (checkpoint.get("project_baseline") or {}).get("revision") or ""
                ),
            )
            progress["important_decision_flags"] = sorted(
                path_signals - exact_protected_authorized
            )
            mark_actioned_review_findings(
                checkpoint,
                progress,
                current_diff_hash=diff["diff_hash"],
            )
            record_review_repair_churn_observation(
                checkpoint,
                diff_hash=str(diff.get("diff_hash") or ""),
            )
            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

            material_required = "material_change" in strategy.get("definition_of_done", {}).get("required", [])
            turn_effect_present = str(diff.get("diff_hash") or "") != turn_start_diff_hash
            response_only_allowed = semantic_response_only_turn_allowed(checkpoint)
            if isinstance(checkpoint.get("verification_only_resume"), dict):
                # Verification-only PM-handoff authorization is single-use even
                # when the developer makes a material change in this turn.
                checkpoint.pop("verification_only_resume", None)
                self.storage.update(job_id, checkpoint=checkpoint)
            if material_required and not turn_effect_present and not response_only_allowed:
                last_failure = (
                    "Agent completed without changing the cumulative WorkOrder diff "
                    "during this invocation."
                )
                progress["last_agent_failure_kind"] = progress.get("last_agent_failure_kind") or "no_effect"
                fp = failure_fingerprint(
                    last_failure
                    + "\nstart_diff="
                    + turn_start_diff_hash
                    + "\nend_diff="
                    + str(diff.get("diff_hash") or "")
                    + "\n"
                    + (run.output or "")[-4000:]
                )
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(f"no_effect:{executor_choice['id']}")
                next_executor, reroute = await self._model_failover(
                    route_payload=route_payload,
                    provider_state=provider_state,
                    current_choice=executor_choice,
                    progress=progress,
                    strategy=strategy,
                    reason="no_effect",
                )
                checkpoint["provider_state"] = provider_state
                checkpoint["last_failure"] = last_failure
                if next_executor:
                    route_history.append({
                        "reason": f"model_failover:{executor_choice['id']}:no_effect",
                        "route": reroute,
                    })
                    executor_choice = next_executor
                    checkpoint["executor_choice"] = executor_choice
                    checkpoint["route_history"] = route_history
                    self.storage.update(job_id, status="routing", progress=progress, checkpoint=checkpoint)
                    continue
                self._update_elapsed(progress, started)
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="material_change_missing_without_model_fallback",
                    last_failure=last_failure,
                    diff=diff,
                )
                return

            verification = await self._verify(
                job_id, job["project_id"], workspace, project, strategy, started, progress
            )
            verification_summary = verification_checkpoint_summary(verification)
            if verification_summary is not None:
                checkpoint["last_verification_summary"] = verification_summary
            invalidate_review_reuse_on_verification_failure(
                checkpoint,
                verification,
            )
            record_review_repair_churn_observation(
                checkpoint,
                verification=verification,
            )
            progress["tool_calls"] += verification["tool_calls"]
            progress["test_runs"] += verification["test_runs"]
            progress["tests_passed"] = verification["tests_passed"]
            progress["required_checks_passed"] = False
            progress["unexpected_scope"] = diff["changed_file_count"] > int(strategy["budget"]["max_changed_files"])
            self._update_elapsed(progress, started)

            deterministic_streak = record_deterministic_verification_failure_streak(
                checkpoint,
                verification,
                diff_hash=str(diff.get("diff_hash") or ""),
                limit=int(
                    (strategy.get("anti_loop") or {}).get(
                        "same_failure_fingerprint_limit",
                        2,
                    )
                ),
            )
            if (
                deterministic_streak is not None
                and int(deterministic_streak.get("count") or 0)
                > int(deterministic_streak.get("limit") or 0)
            ):
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="repeated_deterministic_verification_failure",
                    last_failure=(
                        verification.get("failure_text")
                        or "Deterministic verification repeatedly failed without a diff/signature change."
                    ),
                    diff=diff,
                    verification=verification,
                    verification_failure_streak=deterministic_streak,
                )
                return

            evaluator_output = None
            evaluator_ok = True
            review_report = None
            review_policy = strategy.get("review_policy") or {}
            if "review_policy" in strategy:
                run_review = should_run_review(
                    review_policy,
                    verification,
                    changed_files=diff["changed_file_count"],
                    unexpected_scope=progress["unexpected_scope"],
                )
            else:
                run_review = bool(strategy.get("evaluator"))

            reuse_review = reusable_passed_review(
                checkpoint,
                verification,
                diff_hash=str(diff.get("diff_hash") or ""),
            )
            if isinstance(checkpoint.get("reuse_passed_review_once"), dict):
                if reuse_review:
                    run_review = False
                else:
                    checkpoint.pop("reuse_passed_review_once", None)

            if verification["passed"] and strategy.get("evaluator") and run_review:
                choice = dict(checkpoint.get("evaluator_choice") or strategy["evaluator"])
                while True:
                    budget_reason = self._pre_model_budget_reason(progress, strategy, include_iteration=False)
                    if budget_reason:
                        last_failure = budget_reason
                        evaluator_ok = False
                        break
                    validate_model_choice(choice)
                    progress["model_calls"] += 1
                    checkpoint["evaluator_choice"] = choice
                    self.storage.update(job_id, status="evaluating", progress=progress, checkpoint=checkpoint)
                    evaluator_preview_context = await ready_preview_context(
                        self.storage,
                        self.ddev,
                        job_id,
                    )
                    evaluator_adapter = build_adapter(
                        choice["adapter"], choice["model"], choice.get("reasoning_effort")
                    )
                    evaluation = await evaluator_adapter.run(
                        workspace=workspace,
                        prompt=evaluator_prompt(
                            task=enriched_task,
                            diff=diff["diff"],
                            verification=verification,
                            work_order=checkpoint.get("work_order"),
                            baseline=checkpoint.get("project_baseline"),
                            developer_report=run.output if run.returncode == 0 else None,
                            preview_context=evaluator_preview_context,
                            capability_context=agent_verification_capability_context(
                                evaluator_adapter,
                                mode="evaluate",
                                project=project,
                                verification=verification,
                            ),
                        ),
                        mode="evaluate",
                        timeout=self._remaining_seconds(strategy, started, 1200),
                    )
                    self._record_usage(progress, choice["id"], evaluation.usage)
                    self._update_elapsed(progress, started)
                    if evaluation.provider_failed:
                        progress["provider_failures"].append({
                            "model": choice["id"],
                            "provider": choice.get("provider"),
                            "kind": evaluation.failure_kind,
                        })
                        next_choice, reroute = await self._provider_failover(
                            route_payload=route_payload,
                            provider_state=provider_state,
                            current_choice=choice,
                            failure_kind=evaluation.failure_kind or "provider_unavailable",
                            progress=progress,
                            strategy=strategy,
                            role="evaluator",
                        )
                        checkpoint["provider_state"] = provider_state
                        if next_choice:
                            route_history.append({
                                "reason": f"evaluator_provider_failover:{choice['id']}:{evaluation.failure_kind}",
                                "route": reroute,
                            })
                            choice = next_choice
                            checkpoint["evaluator_choice"] = choice
                            checkpoint["route_history"] = route_history
                            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                            continue
                        self._block(
                            job_id=job_id,
                            progress=progress,
                            checkpoint=checkpoint,
                            reason="evaluator_provider_failure_without_fallback",
                            last_failure=evaluation.failure_message or evaluation.stderr or evaluation.output,
                            diff=diff,
                        )
                        return
                    if evaluation.returncode == 0:
                        removed_health = self._rehabilitate_successful_choice(
                            provider_state,
                            choice,
                        )
                        if removed_health:
                            checkpoint["provider_state"] = provider_state
                            history = list(
                                checkpoint.get("provider_success_rehabilitations")
                                or []
                            )
                            history.append({
                                "stage": "evaluator",
                                "model": str(choice.get("id") or ""),
                                "provider": str(choice.get("provider") or ""),
                                "removed_keys": removed_health,
                            })
                            checkpoint["provider_success_rehabilitations"] = history[-20:]
                    evaluator_output = evaluation.output[-20000:]
                    review_report = parse_review_output(evaluator_output)
                    record_review_telemetry(
                        progress,
                        review_report,
                        review_level=str(review_policy.get("level") or strategy.get("profile") or "legacy"),
                        model_id=choice.get("id"),
                        provider=choice.get("provider"),
                        raw_usage=evaluation.usage,
                    )
                    checkpoint["last_review_report"] = review_report_summary(review_report)
                    record_review_repair_churn_observation(
                        checkpoint,
                        review=checkpoint["last_review_report"],
                    )

                    if not review_report.protocol_valid:
                        next_choice, reroute = await self._model_failover(
                            route_payload=route_payload,
                            provider_state=provider_state,
                            current_choice=choice,
                            progress=progress,
                            strategy=strategy,
                            reason="malformed_reviewer_output",
                            role="evaluator",
                        )
                        checkpoint["provider_state"] = provider_state
                        if next_choice:
                            route_history.append({
                                "reason": f"evaluator_model_failover:{choice['id']}:malformed_review",
                                "route": reroute,
                            })
                            choice = next_choice
                            checkpoint["evaluator_choice"] = choice
                            checkpoint["route_history"] = route_history
                            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                            continue
                        self._block(
                            job_id=job_id,
                            progress=progress,
                            checkpoint=checkpoint,
                            reason="evaluator_protocol_failure_without_fallback",
                            last_failure=review_report.summary,
                            diff=diff,
                        )
                        return

                    evaluator_ok = evaluation.returncode == 0 and review_report.verdict == "pass"
                    if review_report.verdict == "fail":
                        checkpoint["pending_review_findings"] = {
                            "diff_hash": diff["diff_hash"],
                            "findings": [item.model_dump(mode="json") for item in review_report.findings],
                        }
                    checkpoint.pop("evaluator_choice", None)
                    self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                    break
            elif verification["passed"] and strategy.get("evaluator") and not run_review:
                if reuse_review:
                    progress["review_reused_after_pm_staffing_failure"] = int(
                        progress.get("review_reused_after_pm_staffing_failure", 0)
                    ) + 1
                    checkpoint.pop("reuse_passed_review_once", None)
                    self.storage.update(
                        job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                    )
                else:
                    progress["review_skipped_strong_evidence"] = int(
                        progress.get("review_skipped_strong_evidence", 0)
                    ) + 1
                    checkpoint["last_review_report"] = {
                        "verdict": "skipped",
                        "summary": "Model review skipped by policy because deterministic evidence is strong",
                        "finding_count": 0,
                        "findings": [],
                        "jit_context_used": False,
                    }
                    record_review_repair_churn_observation(
                        checkpoint,
                        review=checkpoint["last_review_report"],
                    )
                    self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

            progress["required_checks_passed"] = verification["passed"] and evaluator_ok and not progress["unexpected_scope"]

            pm_scope_state = changed_file_reassessment_state(
                strategy,
                changed_files=int(progress.get("changed_files") or 0),
            )
            protected_flags = list(progress.get("important_decision_flags") or [])
            pm_scope_needs_review = bool(
                progress["required_checks_passed"]
                and pm_scope_state
                and not has_pm_changed_file_authorization(
                    checkpoint,
                    diff_hash=str(diff.get("diff_hash") or ""),
                    used=int(progress.get("changed_files") or 0),
                )
            )
            pm_protected_needs_review = bool(
                verification["passed"] and protected_flags
            )
            pm_reassessment_needs_review = bool(
                pm_scope_needs_review or pm_protected_needs_review
            )
            pm_signal = (
                "protected_execution_signal"
                if pm_protected_needs_review
                else "changed_file_working_target_exceeded"
            )
            if pm_reassessment_needs_review:
                budget_reason = self._pre_model_budget_reason(
                    progress,
                    strategy,
                    include_iteration=False,
                )
                if budget_reason:
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="execution_budget_exhausted",
                        last_failure=budget_reason,
                        diff=diff,
                    )
                    return

                self.storage.update(
                    job_id,
                    status="evaluating",
                    progress=progress,
                    checkpoint=checkpoint,
                )
                current_review_summary = (
                    review_report_summary(review_report)
                    if review_report is not None
                    else checkpoint.get("last_review_report")
                )
                def precharge_pm_reassessment() -> None:
                    progress["model_calls"] += 1
                    self.storage.update(
                        job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                    )

                try:
                    pm_result = await run_pm_reassessment(
                        router=self.router,
                        ddev=self.ddev,
                        workspace=workspace,
                        job_id=job_id,
                        project_id=job["project_id"],
                        source_commit=source_commit,
                        profile=str(strategy.get("profile") or "standard"),
                        current_executor=executor_choice,
                        provider_state=provider_state,
                        work_order=dict(checkpoint.get("work_order") or {}),
                        baseline=dict(checkpoint.get("project_baseline") or {}),
                        trigger={
                            "signal": pm_signal,
                            **dict(pm_scope_state or {}),
                            "protected_decision_flags": protected_flags,
                        },
                        diff=diff,
                        verification=verification,
                        review_summary=(
                            current_review_summary
                            if isinstance(current_review_summary, dict)
                            else None
                        ),
                        developer_report=run.output if run.returncode == 0 else None,
                        decision_context={
                            "approved_decisions": list(
                                checkpoint.get("approved_decisions") or []
                            )[-20:],
                            "decision_history": list(
                                checkpoint.get("decision_history") or []
                            )[-20:],
                            "prior_pm_boundary": dict(
                                checkpoint.get("pending_pm_reassessment") or {}
                            ),
                        },
                        max_diff_bytes=max_diff,
                        timeout_seconds=self._remaining_seconds(strategy, started, 600),
                        precharge_call=precharge_pm_reassessment,
                    )
                except Exception as exc:
                    self._update_elapsed(progress, started)
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="pm_reassessment_failed",
                        last_failure=str(exc)[-4000:],
                        diff=diff,
                    )
                    return

                self._record_usage(
                    progress,
                    str(pm_result.get("model_id") or ""),
                    pm_result.get("usage"),
                )
                progress["pm_reassessments"] = int(
                    progress.get("pm_reassessments", 0)
                ) + 1
                self._update_elapsed(progress, started)

                pm_decision = dict(pm_result.get("decision") or {})
                checkpoint["last_pm_reassessment"] = {
                    "diff_hash": diff.get("diff_hash"),
                    "signal": pm_signal,
                    "decision": pm_decision,
                    "staffing": pm_result.get("staffing"),
                }
                pm_action = str(pm_decision.get("action") or "")
                if pm_action == "approve_continue":
                    protected_flags = list(
                        progress.get("important_decision_flags") or []
                    )
                    if protected_flags:
                        self._block(
                            job_id=job_id,
                            progress=progress,
                            checkpoint=checkpoint,
                            reason="pm_reassessment_invalid_protected_approval",
                            last_failure=(
                                "Product Manager attempted to approve a diff that "
                                "still contains a Human Owner-protected boundary."
                            ),
                            pm_reassessment=pm_decision,
                            diff=diff,
                        )
                        return
                    checkpoint.pop("pending_pm_reassessment", None)
                    authorizations = list(
                        checkpoint.get("pm_reassessment_authorizations") or []
                    )
                    authorizations.append(
                        {
                            "signal": "changed_file_working_target_exceeded",
                            "diff_hash": str(diff.get("diff_hash") or ""),
                            "used": int((pm_scope_state or {}).get("used") or 0),
                            "working_target": int(
                                (pm_scope_state or {}).get("working_target") or 0
                            ),
                            "emergency_limit": int(
                                (pm_scope_state or {}).get("emergency_limit") or 0
                            ),
                            "approved_by": str(pm_result.get("model_id") or ""),
                            "provider": str(pm_result.get("provider") or ""),
                            "summary": str(pm_decision.get("summary") or "")[:2000],
                        }
                    )
                    checkpoint["pm_reassessment_authorizations"] = authorizations[-20:]
                    self.storage.update(
                        job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                    )
                elif pm_action == "approve_baseline_covered_protected":
                    protected_flags = list(
                        progress.get("important_decision_flags") or []
                    )
                    approval_error = validate_baseline_covered_protected_approval(
                        pm_decision,
                        protected_flags=protected_flags,
                        verification=verification,
                        review_summary=(
                            current_review_summary
                            if isinstance(current_review_summary, dict)
                            else None
                        ),
                        baseline=dict(checkpoint.get("project_baseline") or {}),
                    )
                    if approval_error:
                        self._block(
                            job_id=job_id,
                            progress=progress,
                            checkpoint=checkpoint,
                            reason="pm_reassessment_invalid_protected_approval",
                            last_failure=(
                                "Product Manager baseline-covered protected approval "
                                f"was invalid: {approval_error}."
                            ),
                            pm_reassessment=pm_decision,
                            diff=diff,
                        )
                        return
                    authorized_signals = sorted(
                        {
                            str(item)
                            for item in pm_decision.get(
                                "authorized_protected_signals"
                            )
                            or []
                            if str(item)
                        }
                    )
                    checkpoint.pop("pending_pm_reassessment", None)
                    protected_authorizations = list(
                        checkpoint.get(
                            "pm_baseline_covered_protected_authorizations"
                        )
                        or []
                    )
                    protected_authorizations.append(
                        {
                            "diff_hash": str(diff.get("diff_hash") or ""),
                            "protected_signals": authorized_signals,
                            "approved_by": str(pm_result.get("model_id") or ""),
                            "provider": str(pm_result.get("provider") or ""),
                            "summary": str(pm_decision.get("summary") or "")[:2000],
                            "baseline_authority_refs": list(
                                pm_decision.get("baseline_authority_refs") or []
                            )[:8],
                            "review_verdict": str(
                                (
                                    current_review_summary
                                    if isinstance(current_review_summary, dict)
                                    else {}
                                ).get("verdict")
                                or ""
                            ),
                            "baseline_revision": str(
                                (
                                    checkpoint.get("project_baseline") or {}
                                ).get("revision")
                                or ""
                            ),
                        }
                    )
                    checkpoint[
                        "pm_baseline_covered_protected_authorizations"
                    ] = protected_authorizations[-20:]
                    approved_set = set(authorized_signals)
                    progress["important_decision_flags"] = [
                        item
                        for item in progress.get("important_decision_flags", [])
                        if item not in approved_set
                    ]
                    self.storage.update(
                        job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                    )
                elif pm_action in {"request_developer_response", "request_repair"}:
                    checkpoint.pop("pending_pm_reassessment", None)
                    last_failure = "PCP_PM_REASSESSMENT: " + json.dumps(
                        {
                            "action": pm_action,
                            "summary": pm_decision.get("summary"),
                            "developer_message": pm_decision.get("developer_message"),
                            "unresolved_risks": pm_decision.get("unresolved_risks") or [],
                            "diff_hash": diff.get("diff_hash"),
                            "signal": pm_signal,
                            "protected_decision_flags": protected_flags,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    progress["required_checks_passed"] = False
                    # PM owns the next bounded engineering step. Suppress the
                    # current protected-path signal for this repair/response turn
                    # and return directly to Developer. Generic Router reassess
                    # must not bypass PM and escalate the same removable boundary
                    # to Human before Developer can act.
                    if protected_flags:
                        progress["important_decision_flags"] = [
                            item
                            for item in progress.get("important_decision_flags", [])
                            if item not in set(protected_flags)
                        ]
                    fp = failure_fingerprint(last_failure)
                    progress["failure_fingerprints"].append(fp)
                    progress["progress_markers"].append(fp)
                    progress["repair_iterations"] += 1
                    set_failure_context(
                        checkpoint,
                        kind="semantic_repair",
                        source="pm_reassessment",
                        message=last_failure,
                        diff_hash=str(diff.get("diff_hash") or ""),
                    )
                    self.storage.update(
                        job_id,
                        status="executing",
                        progress=progress,
                        checkpoint=checkpoint,
                    )
                    continue
                elif pm_action == "human_decision":
                    pm_human_decision = {
                        "required": True,
                        "triggers": list(pm_decision.get("human_triggers") or []),
                        "reason": str(pm_decision.get("summary") or ""),
                    }
                    if self._decision_approved(checkpoint, pm_human_decision):
                        self._block(
                            job_id=job_id,
                            progress=progress,
                            checkpoint=checkpoint,
                            reason="pm_reassessment_unresolved_after_human_approval",
                            last_failure=(
                                "Product Manager repeated a Human Owner trigger that "
                                "is already durably approved; current baseline still "
                                "does not authorize automatic completion."
                            ),
                            pm_reassessment=pm_decision,
                            diff=diff,
                        )
                        return
                    checkpoint["pending_pm_reassessment"] = {
                        "signal": pm_signal,
                        "diff_hash": str(diff.get("diff_hash") or ""),
                        **dict(pm_scope_state or {}),
                        "pm_model_id": str(pm_result.get("model_id") or ""),
                        "summary": str(pm_decision.get("summary") or "")[:2000],
                    }
                    self._pause_for_decision(
                        job_id=job_id,
                        checkpoint=checkpoint,
                        progress=progress,
                        decision=pm_human_decision,
                        route_history=route_history,
                        source="pm_reassessment",
                    )
                    return
                else:
                    checkpoint.pop("pending_pm_reassessment", None)
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="pm_reassessment_blocked",
                        last_failure=str(pm_decision.get("summary") or "PM blocked reassessment"),
                        pm_reassessment=pm_decision,
                        diff=diff,
                    )
                    return

            if progress["required_checks_passed"]:
                effective_route = self._effective_route(route, executor_choice)
                while True:
                    reassess = await self.router.reassess({
                        "route": effective_route,
                        "progress": progress,
                        "provider_state": provider_state,
                    })
                    action = reassess["action"]
                    if action != "human_decision":
                        break
                    decision = dict(reassess.get("human_decision") or {})
                    if not self._decision_approved(checkpoint, decision):
                        self._pause_for_decision(
                            job_id=job_id,
                            checkpoint=checkpoint,
                            progress=progress,
                            decision=decision,
                            route_history=route_history,
                            source="reassessment",
                        )
                        return
                    approved = set(decision.get("triggers") or [])
                    progress["important_decision_flags"] = [
                        item for item in progress.get("important_decision_flags", []) if item not in approved
                    ]
                    self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

                if action == "complete":
                    commit_sha = None
                    if strategy.get("permissions", {}).get("commit", False):
                        commit_sha = commit_changes(workspace, f"AI: {enriched_task['title']}")
                    review_summary = (
                        review_report_summary(review_report)
                        if review_report is not None
                        else checkpoint.get("last_review_report")
                    )
                    work_order = checkpoint.get("work_order") or {}
                    incident_candidate = incident_learning_candidate(
                        {
                            **job,
                            "status": "completed",
                            "checkpoint": checkpoint,
                            "progress": progress,
                            "result": {
                                "status": "accepted",
                                "verification": verification,
                                "review": review_summary,
                            },
                        }
                    )
                    pm_pack = pm_evidence_pack(
                        work_order_ref=str(work_order.get("id") or "legacy-task"),
                        outcome="accepted",
                        verification_summary=verification,
                        review_summary=review_summary if isinstance(review_summary, dict) else None,
                        unresolved_risks=[],
                        protected_decision_flags=list(progress.get("important_decision_flags") or []),
                        incident_learning={"candidate": incident_candidate}
                        if incident_candidate
                        else {},
                        baseline_covered_protected_authorizations=[
                            item
                            for item in (
                                checkpoint.get(
                                    "pm_baseline_covered_protected_authorizations"
                                )
                                or []
                            )
                            if isinstance(item, dict)
                            and str(item.get("diff_hash") or "")
                            == str(diff.get("diff_hash") or "")
                        ],
                    )
                    result = {
                        "status": "accepted",
                        "branch": branch,
                        "commit": commit_sha,
                        "diff": diff,
                        "verification": verification,
                        "evaluator": evaluator_output,
                        "review": review_summary,
                        "pm_evidence": pm_pack,
                        "pm_reassessment": checkpoint.get("last_pm_reassessment"),
                        "route": route,
                        "route_history": route_history,
                        "progress": progress,
                    }
                    clear_failure_context(checkpoint)
                    checkpoint["executor_choice"] = executor_choice
                    checkpoint["provider_state"] = provider_state
                    self.storage.update(
                        job_id,
                        status="completed",
                        result=result,
                        progress=progress,
                        checkpoint=checkpoint,
                        error=None,
                    )
                    return
                if action == "stop":
                    self._block(
                        job_id=job_id,
                        progress=progress,
                        checkpoint=checkpoint,
                        reason="reassessment_stopped",
                        last_failure=reassess.get("reason"),
                        reassess=reassess,
                        diff=diff,
                    )
                    return
                if action == "escalate" and reassess.get("next_executor"):
                    progress["escalations"] += 1
                    executor_choice = reassess["next_executor"]
                    last_failure = reassess.get("reason") or "Execution strategy escalated"
                else:
                    if not progress["agent_succeeded"]:
                        last_failure = last_failure or "Agent did not complete successfully."
                    else:
                        last_failure = reassess.get("reason") or "Definition of done is not complete."
            elif not verification["passed"]:
                last_failure = verification.get("failure_text") or last_failure or "Verification failed"
            elif not evaluator_ok:
                findings = [item.model_dump(mode="json") for item in review_report.findings] if review_report else []
                work_order = checkpoint.get("work_order") or {}
                repair_pack = developer_repair_evidence_pack(
                    work_order_ref=str(work_order.get("id") or "legacy-task"),
                    current_diff_ref=f"sha256:{diff['diff_hash']}",
                    failing_check=None,
                    reviewer_findings=findings,
                    relevant_files=list(diff.get("changed_files") or []),
                    prior_attempt_summary=review_report.summary if review_report else evaluator_output,
                )
                last_failure = "PCP_REVIEW_FINDINGS: " + json.dumps(
                    repair_pack,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                set_failure_context(
                    checkpoint,
                    kind="semantic_repair",
                    source="reviewer",
                    message=last_failure,
                    diff_hash=str(diff.get("diff_hash") or ""),
                )
            elif progress["unexpected_scope"]:
                last_failure = "Evaluator completed but the diff exceeded the approved changed-file scope."

            if last_failure:
                fp = failure_fingerprint(last_failure)
                progress["failure_fingerprints"].append(fp)
                progress["progress_markers"].append(fp)
            else:
                progress["progress_markers"].append(diff["diff_hash"][:24])
            progress["repair_iterations"] += 1
            self._update_elapsed(progress, started)
            total_findings = int(progress.get("review_findings", 0))
            actioned = int(progress.get("review_findings_actioned", 0))
            progress["review_useful_finding_yield"] = round(actioned / total_findings, 4) if total_findings else 0.0
            checkpoint.update({
                "executor_choice": executor_choice,
                "last_failure": last_failure,
                "provider_state": provider_state,
                "route_history": route_history,
            })
            self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

            effective_route = self._effective_route(route, executor_choice)
            reassess_progress = progress
            if not verification["passed"] and progress.get("important_decision_flags"):
                reassess_progress = {
                    **progress,
                    "important_decision_flags": [],
                }
            reassess = await self.router.reassess({
                "route": effective_route,
                "progress": reassess_progress,
                "provider_state": provider_state,
            })
            action = reassess["action"]
            if action == "escalate" and reassess.get("next_executor"):
                progress["escalations"] += 1
                executor_choice = reassess["next_executor"]
                checkpoint["executor_choice"] = executor_choice
                self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                continue
            if action == "continue":
                continue
            if action == "human_decision":
                decision = dict(reassess.get("human_decision") or {})
                if self._decision_approved(checkpoint, decision):
                    approved = set(decision.get("triggers") or [])
                    progress["important_decision_flags"] = [
                        item for item in progress.get("important_decision_flags", []) if item not in approved
                    ]
                    self.storage.update(job_id, progress=progress, checkpoint=checkpoint)
                    continue
                self._pause_for_decision(
                    job_id=job_id,
                    checkpoint=checkpoint,
                    progress=progress,
                    decision=decision,
                    route_history=route_history,
                    source="reassessment",
                )
                return
            if action == "complete":
                self._block(
                    job_id=job_id,
                    progress=progress,
                    checkpoint=checkpoint,
                    reason="unsafe_bare_completion",
                    last_failure=last_failure,
                    reassess=reassess,
                    diff=diff,
                )
                return
            self._block(
                job_id=job_id,
                progress=progress,
                checkpoint=checkpoint,
                reason="reassessment_stopped",
                last_failure=last_failure,
                reassess=reassess,
                diff=diff,
            )
            return

    async def _verify(
        self,
        job_id: str,
        project_id: str,
        workspace: Path,
        project: dict[str, Any],
        strategy: dict[str, Any],
        started: float,
        progress: dict[str, Any],
    ) -> dict[str, Any]:
        if not project.get("ddev", {}).get("enabled", False):
            return {"passed": True, "tests_passed": True, "tool_calls": 0, "test_runs": 0, "phases": []}
        phases = ["targeted_tests", "static_analysis"]
        if strategy.get("profile") in {"complex", "critical"}:
            phases.append("full_tests")
        outputs = []
        tool_calls = 0
        test_runs = 0
        failures: list[str] = []
        budget = strategy["budget"]

        for phase in phases:
            commands = project.get("ddev", {}).get(phase, []) or []
            count = len(commands)
            if (
                not self._adaptive_work_shape_nonblocking(strategy)
                and (
                    progress["tool_calls"] + tool_calls + count > int(budget["max_tool_calls"])
                    or progress["test_runs"] + test_runs + count > int(budget["max_test_runs"])
                )
            ):
                failures.append(f"{phase}: verification budget would be exceeded")
                break
            result = await self.ddev.phase(
                job_id=job_id,
                project_id=project_id,
                workspace=str(workspace),
                phase=phase,
                timeout_seconds=self._remaining_seconds(strategy, started, 1200),
            )
            outputs.append(result)
            tool_calls += len(result.get("commands", []))
            test_runs += len(result.get("commands", []))
            if not result.get("passed", False):
                failures.append(str(result))

        return {
            "passed": not failures,
            "tests_passed": not failures,
            "tool_calls": tool_calls,
            "test_runs": test_runs,
            "phases": outputs,
            "failure_text": "\n".join(failures)[-30000:],
        }

    async def cleanup(
        self,
        job_id: str,
        remove_workspace: bool = False,
        release_ddev_data: bool = False,
    ) -> dict[str, Any]:
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")

        workspace = str(job.get("workspace") or "").strip()
        workspace_path = Path(workspace) if workspace else None
        workspace_available = bool(
            workspace_path
            and workspace_path.is_dir()
            and (workspace_path / ".git").exists()
        )
        release_requested = bool(release_ddev_data or remove_workspace)
        project = project_config(job["project_id"])

        cleanup_result = None
        orphan_result = None

        if project.get("ddev", {}).get("enabled", False):
            if workspace_available:
                cleanup_result = await self.ddev.quiesce_workspace(
                    job_id=job_id,
                    project_id=job["project_id"],
                    workspace=workspace,
                    remove_data=release_requested,
                )
            elif release_requested:
                status = str(job.get("status") or "")
                if status not in {"completed", "cancelled"}:
                    raise RuntimeError(
                        "Missing-workspace orphan cleanup is allowed only for completed/cancelled jobs"
                    )
                if not re.fullmatch(r"[0-9a-f]{32}", job_id):
                    raise RuntimeError(
                        "Missing-workspace orphan cleanup requires the full Runtime job id"
                    )
                matches = self.storage.jobs_with_id_prefix(job_id[:10])
                if (
                    len(matches) != 1
                    or str(matches[0].get("id") or "") != job_id
                    or str(matches[0].get("project_id") or "") != str(job["project_id"])
                ):
                    raise RuntimeError(
                        "Missing-workspace orphan cleanup requires an unambiguous exact job prefix"
                    )

                inspection = await self.ddev.orphan_resources(
                    job_id=job_id,
                    project_id=job["project_id"],
                    workspace=workspace or None,
                    execute=False,
                )
                release = await self.ddev.orphan_resources(
                    job_id=job_id,
                    project_id=job["project_id"],
                    workspace=workspace or None,
                    execute=True,
                )
                orphan_result = {
                    "inspection": inspection,
                    "release": release,
                }
            elif not workspace_available:
                return {
                    "cleaned": False,
                    "reason": "workspace unavailable",
                    "workspace": workspace or None,
                }

        if not workspace_available and orphan_result is None:
            return {
                "cleaned": False,
                "reason": "workspace unavailable",
                "workspace": workspace or None,
            }

        remove_result = None
        if remove_workspace and workspace_available:
            remove_result = await self.ddev.remove_workspace(
                job_id=job_id,
                project_id=job["project_id"],
                workspace=workspace,
            )

        workspace_removed = bool(
            remove_result and remove_result.get("removed", False)
        )
        workspace_preserved = bool(
            remove_result and remove_result.get("preserved", False)
        )
        orphan_release = (
            orphan_result.get("release")
            if isinstance(orphan_result, dict)
            else None
        )
        orphan_after = (
            orphan_release.get("after")
            if isinstance(orphan_release, dict)
            else None
        )
        orphan_released_cleanly = bool(
            isinstance(orphan_after, dict)
            and int(orphan_after.get("resource_count") or 0) == 0
        )

        return {
            "cleaned": True,
            "ddev": cleanup_result,
            "ddev_orphan": orphan_result,
            "ddev_data_released": bool(
                (cleanup_result and cleanup_result.get("data_removed", False))
                or orphan_released_cleanly
            ),
            "workspace_removed": workspace_removed,
            "workspace_preserved": workspace_preserved,
            "workspace_result": remove_result,
        }
