from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .collaboration import (
    CollaborationCreateRequest,
    CollaborationEvidence,
    CollaborationManager,
    CollaborationRecheckRequest,
    DeveloperCollaborationRequest,
)
from .developer_stream import runtime_activity_event
from .engine_execution import RuntimeEngine as ExecutionRuntimeEngine
from .repo import diff_state
from .review_repair_churn import ReviewRepairChurnPaused
from .shell import run_command
from .work_order import work_order_snapshot


_COLLABORATION_REQUEST_FILE = ".pcp-collaboration-request.json"
_MAX_COLLABORATION_REQUEST_BYTES = 32768


class _CollaborationRequested(RuntimeError):
    def __init__(self, request: DeveloperCollaborationRequest, clean_diff: dict[str, Any]) -> None:
        self.request = request
        self.clean_diff = clean_diff
        super().__init__("Primary developer requested bounded collaboration")


class RuntimeEngine(ExecutionRuntimeEngine):
    """Add layered verification, retry attribution and bounded collaboration.

    A primary developer may emit one temporary structured collaboration artifact.
    Runtime consumes and removes that control artifact before deterministic tests,
    runs one bounded read-only role, then requeues the same job/workspace without
    charging an engineering repair iteration.
    """

    def __init__(self, storage: Any) -> None:
        super().__init__(storage)
        self.collaboration = CollaborationManager(
            self.storage,
            router=self.router,
            ddev=self.ddev,
        )

    def _runtime_event(
        self,
        job_id: str,
        *,
        kind: str,
        message: str,
        phase: str,
        status: str,
        output: Any = None,
        provider: str | None = None,
        model: str | None = None,
        adapter: str | None = None,
    ) -> None:
        row = self.storage.get(job_id) or {}
        workspace = Path(str(row.get("workspace") or "."))
        self.storage.append_event(
            job_id,
            runtime_activity_event(
                kind=kind,
                message=message,
                phase=phase,
                status=status,
                output=output,
                provider=provider,
                model=model,
                adapter=adapter,
                workspace=workspace,
            ),
        )

    async def run_job(self, job_id: str) -> None:
        before = self.storage.get(job_id)
        if before and before.get("status") == "queued":
            result = before.get("result") or {}
            if result.get("reason") == "preflight_failed":
                progress = dict(before.get("progress") or {})
                progress["infrastructure_retry_attempts"] = int(
                    progress.get("infrastructure_retry_attempts", 0)
                ) + 1
                self.storage.update(job_id, progress=progress)
                self._runtime_event(
                    job_id,
                    kind="infrastructure_retry",
                    message="Retrying deterministic preflight after an infrastructure/preflight block",
                    phase="verification",
                    status="preflight_retry",
                    output={"attempt": progress["infrastructure_retry_attempts"]},
                )
        try:
            await super().run_job(job_id)
        except _CollaborationRequested as requested:
            await self._handle_collaboration_request(job_id, requested)
        except ReviewRepairChurnPaused:
            return

    async def _consume_collaboration_request(
        self,
        *,
        job_id: str,
        workspace: Path | str,
        project: dict[str, Any],
        progress: dict[str, Any],
    ) -> _CollaborationRequested | None:
        workspace = Path(workspace)
        request_path = workspace / _COLLABORATION_REQUEST_FILE
        if not request_path.exists():
            return None
        if not request_path.is_file():
            raise RuntimeError("Reserved collaboration request path must be a regular file")
        if request_path.stat().st_size > _MAX_COLLABORATION_REQUEST_BYTES:
            raise RuntimeError("Collaboration request artifact exceeds the 32 KiB limit")

        # Base execution computes a diff before verification. diff_state() uses
        # `git add -N` for untracked files so the control artifact can appear in
        # the index as intent-to-add. That is not a repository-tracked file. Only
        # reject when the reserved path actually exists in the pinned HEAD tree.
        tracked_in_head = await run_command(
            ["git", "cat-file", "-e", f"HEAD:{_COLLABORATION_REQUEST_FILE}"],
            cwd=workspace,
            timeout=20,
        )
        if tracked_in_head.returncode == 0:
            raise RuntimeError(
                f"Reserved collaboration request path {_COLLABORATION_REQUEST_FILE!r} is tracked by the repository"
            )

        try:
            raw = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Collaboration request artifact must contain one valid JSON object") from exc
        if not isinstance(raw, dict):
            raise RuntimeError("Collaboration request artifact must contain one JSON object")
        try:
            request = DeveloperCollaborationRequest.model_validate(raw)
        except ValueError as exc:
            raise RuntimeError(f"Invalid collaboration request artifact: {exc}") from exc

        request_path.unlink()
        reset = await run_command(
            ["git", "reset", "-q", "--", _COLLABORATION_REQUEST_FILE],
            cwd=workspace,
            timeout=20,
        )
        if reset.returncode != 0:
            raise RuntimeError(
                reset.stderr or reset.stdout or "Unable to clear collaboration control artifact from Git index"
            )

        max_diff = int(project.get("runtime", {}).get("max_diff_bytes", 500000))
        clean_diff = diff_state(workspace, max_diff)
        progress["changed_files"] = clean_diff["changed_file_count"]
        progress["material_change_present"] = clean_diff["changed_file_count"] > 0
        hashes = progress.setdefault("diff_hashes", [])
        if hashes:
            hashes[-1] = clean_diff["diff_hash"]
        else:
            hashes.append(clean_diff["diff_hash"])
        self.storage.update(job_id, progress=progress)
        self._runtime_event(
            job_id,
            kind="collaboration_request",
            message="Primary developer requested a bounded read-only collaborator before verification",
            phase="collaboration",
            status=request.action,
            output={
                "action": request.action,
                "role": request.role,
                "thread_id": request.thread_id,
                "changed_files_after_control_artifact_removal": clean_diff["changed_file_count"],
            },
        )
        return _CollaborationRequested(request, clean_diff)

    @staticmethod
    def _runtime_diff_evidence(clean_diff: dict[str, Any]) -> CollaborationEvidence | None:
        changed = int(clean_diff.get("changed_file_count", 0) or 0)
        diff = str(clean_diff.get("diff") or "")
        if changed <= 0 and not diff.strip():
            return None
        summary = (
            f"Runtime-cleaned current diff after removing the collaboration control artifact; "
            f"changed_file_count={changed}.\n{diff[:3200]}"
        )
        return CollaborationEvidence(ref="runtime:current_diff", summary=summary[:4000])

    async def _handle_collaboration_request(
        self,
        job_id: str,
        requested: _CollaborationRequested,
    ) -> None:
        row = self.storage.get(job_id)
        if not row:
            raise RuntimeError("Unknown job")
        checkpoint = dict(row.get("checkpoint") or {})
        progress = dict(row.get("progress") or {})
        request = requested.request
        evidence = list(request.evidence)
        runtime_evidence = self._runtime_diff_evidence(requested.clean_diff)
        if runtime_evidence is not None:
            evidence = evidence[:7] + [runtime_evidence]

        try:
            if request.action == "consult":
                assert request.role is not None
                thread = await self.collaboration.create(
                    job_id,
                    CollaborationCreateRequest(
                        role=request.role,
                        topic=str(request.topic),
                        objective=str(request.objective),
                        question=str(request.question),
                        evidence=evidence,
                        initiator_role="developer",
                        deadline_seconds=request.deadline_seconds,
                    ),
                )
            else:
                assert request.thread_id is not None
                assert request.developer_response is not None
                thread = await self.collaboration.recheck(
                    job_id,
                    request.thread_id,
                    CollaborationRecheckRequest(
                        developer_response=request.developer_response,
                        evidence=evidence,
                        initiator_role="developer",
                        deadline_seconds=request.deadline_seconds,
                    ),
                )
        except Exception as exc:
            latest = self.storage.get(job_id) or row
            self._block(
                job_id=job_id,
                progress=dict(latest.get("progress") or progress),
                checkpoint=dict(latest.get("checkpoint") or checkpoint),
                reason="collaboration_failed",
                last_failure=f"{type(exc).__name__}: {exc}"[-12000:],
                collaboration_request=request.model_dump(mode="json"),
            )
            return

        latest = self.storage.get(job_id)
        if not latest:
            raise RuntimeError("Unknown job")
        progress = dict(latest.get("progress") or progress)
        checkpoint = dict(latest.get("checkpoint") or checkpoint)
        thread_payload = thread.model_dump(mode="json")
        progress.setdefault("progress_markers", []).append(
            f"collaboration:{thread.id}:round:{thread.rounds}:{thread.status}"
        )

        if thread.status == "pm_handoff":
            self._block(
                job_id=job_id,
                progress=progress,
                checkpoint=checkpoint,
                reason="collaboration_pm_handoff",
                last_failure="Bounded collaboration remained unresolved after the maximum dialogue rounds.",
                collaboration=thread_payload,
            )
            return
        if thread.status == "cancelled":
            self._block(
                job_id=job_id,
                progress=progress,
                checkpoint=checkpoint,
                reason="collaboration_cancelled",
                last_failure="Collaboration was cancelled before verification could continue.",
                collaboration=thread_payload,
            )
            return

        previous_failure = checkpoint.get("pre_collaboration_failure")
        if previous_failure is None:
            current_failure = checkpoint.get("last_failure")
            if isinstance(current_failure, str) and not current_failure.startswith("PCP_COLLABORATION_CONTEXT:"):
                previous_failure = current_failure
            checkpoint["pre_collaboration_failure"] = previous_failure
        context = {
            "thread_id": thread.id,
            "role": thread.participant_role,
            "status": thread.status,
            "round": thread.rounds,
            "recommendation": thread.response.recommendation if thread.response else None,
            "risks": thread.response.risks if thread.response else [],
            "suggested_tests": thread.response.suggested_tests if thread.response else [],
            "unresolved": thread.response.unresolved if thread.response else False,
            "previous_failure": previous_failure,
        }
        checkpoint["collaboration_context"] = context
        checkpoint["last_failure"] = "PCP_COLLABORATION_CONTEXT: " + json.dumps(
            context,
            ensure_ascii=False,
            sort_keys=True,
        )
        self.storage.update(
            job_id,
            status="queued",
            progress=progress,
            checkpoint=checkpoint,
            result=None,
            error=None,
        )
        self._runtime_event(
            job_id,
            kind="collaboration_resume",
            message="Returning the structured collaboration artifact to the primary developer",
            phase="collaboration",
            status=thread.status,
            output={"thread_id": thread.id, "round": thread.rounds},
        )
        await self.enqueue(job_id)

    async def _provider_failover(
        self,
        *,
        route_payload: dict[str, Any],
        provider_state: dict[str, Any],
        current_choice: dict[str, Any],
        failure_kind: str,
        progress: dict[str, Any],
        strategy: dict[str, Any],
        role: str = "executor",
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        progress["provider_recovery_attempts"] = int(
            progress.get("provider_recovery_attempts", 0)
        ) + 1
        result = await super()._provider_failover(
            route_payload=route_payload,
            provider_state=provider_state,
            current_choice=current_choice,
            failure_kind=failure_kind,
            progress=progress,
            strategy=strategy,
            role=role,
        )
        next_choice, _ = result
        self._runtime_event(
            str(route_payload.get("job_id") or ""),
            kind="provider_recovery",
            message=(
                f"Provider recovery attempt for {role}: "
                f"{current_choice.get('id') or 'unknown'} -> "
                f"{(next_choice or {}).get('id') or 'no eligible fallback'}"
            ),
            phase="provider",
            status=str(failure_kind or "provider_failure"),
            output={
                "attempt": progress["provider_recovery_attempts"],
                "fallback_selected": bool(next_choice),
            },
            provider=str(current_choice.get("provider") or "") or None,
            model=str(current_choice.get("model") or "") or None,
            adapter=str(current_choice.get("adapter") or "") or None,
        )
        return result

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
        row = self.storage.get(job_id) or {}
        checkpoint = dict(row.get("checkpoint") or {})
        self._ensure_review_repair_churn_epoch(
            job_id=job_id,
            checkpoint=checkpoint,
            progress=progress,
        )
        if self._review_repair_churn_guard(
            job_id=job_id,
            checkpoint=checkpoint,
            progress=progress,
        ):
            raise ReviewRepairChurnPaused()

        collaboration_request = await self._consume_collaboration_request(
            job_id=job_id,
            workspace=workspace,
            project=project,
            progress=progress,
        )
        if collaboration_request is not None:
            raise collaboration_request

        attempt = int(progress.get("verification_attempts", 0)) + 1
        progress["verification_attempts"] = attempt
        if attempt > 1:
            progress["verification_retry_attempts"] = int(
                progress.get("verification_retry_attempts", 0)
            ) + 1
            self._runtime_event(
                job_id,
                kind="verification_retry",
                message="Retrying deterministic verification after an earlier verification cycle",
                phase="verification",
                status="verification_retry",
                output={"attempt": attempt},
            )
        # Charge the cycle before entering DDEV so a Runtime interruption cannot
        # replay an uncounted expensive verification attempt after restart.
        self.storage.update(job_id, progress=progress, checkpoint=checkpoint)

        row = self.storage.get(job_id) or {}
        checkpoint = row.get("checkpoint") or {}
        work_order = work_order_snapshot(checkpoint.get("work_order"))
        if work_order is None or not work_order.verification.intermediate_phases:
            result = await super()._verify(
                job_id,
                project_id,
                workspace,
                project,
                strategy,
                started,
                progress,
            )
            result["verification_mode"] = "legacy"
            result["verification_attempt"] = attempt
            return result

        if not project.get("ddev", {}).get("enabled", False):
            return {
                "passed": True,
                "tests_passed": True,
                "tool_calls": 0,
                "test_runs": 0,
                "phases": [],
                "verification_mode": "layered",
                "verification_attempt": attempt,
            }

        intermediate = list(work_order.verification.intermediate_phases)
        required = list(work_order.verification.required_phases)
        profile = str(strategy.get("profile") or "")
        if profile in {"complex", "critical"} and "full_tests" not in required:
            required.append("full_tests")

        entries: list[tuple[str, str]] = []
        seen: set[str] = set()
        for phase in intermediate:
            if phase not in seen:
                entries.append((phase, "intermediate"))
                seen.add(phase)
        for phase in required:
            if phase == "full_tests" and profile not in {"complex", "critical"}:
                self._runtime_event(
                    job_id,
                    kind="verification_layer",
                    message="Verification final phase delegated to WorkOrder final gate: full_tests",
                    phase="verification",
                    status="pending:final:full_tests",
                    output={
                        "attempt": attempt,
                        "retry": attempt > 1,
                        "required_for_final": True,
                        "delegated_to_governance": True,
                    },
                )
                continue
            if phase not in seen:
                entries.append((phase, "final"))
                seen.add(phase)

        outputs: list[dict[str, Any]] = []
        failures: list[str] = []
        tool_calls = 0
        test_runs = 0
        budget = strategy["budget"]
        required_set = set(required)

        for phase, layer in entries:
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

            self._runtime_event(
                job_id,
                kind="verification_layer",
                message=f"Verification {layer} phase started: {phase}",
                phase="verification",
                status=f"{layer}:{phase}",
                output={
                    "attempt": attempt,
                    "retry": attempt > 1,
                    "required_for_final": phase in required_set,
                },
            )

            phase_result = await self.ddev.phase(
                job_id=job_id,
                project_id=project_id,
                workspace=str(workspace),
                phase=phase,
                timeout_seconds=self._remaining_seconds(strategy, started, 1200),
            )
            annotated = dict(phase_result)
            annotated["verification_layer"] = layer
            annotated["required_for_final"] = phase in required_set
            outputs.append(annotated)
            tool_calls += len(phase_result.get("commands", []))
            test_runs += len(phase_result.get("commands", []))

            if not phase_result.get("passed", False):
                failures.append(str(phase_result))
                self._runtime_event(
                    job_id,
                    kind="verification_layer",
                    message=f"Verification stopped after failed {layer} phase: {phase}",
                    phase="verification",
                    status=f"failed:{layer}:{phase}",
                    output={"attempt": attempt, "later_phases_skipped": True},
                )
                break

        return {
            "passed": not failures,
            "tests_passed": not failures,
            "tool_calls": tool_calls,
            "test_runs": test_runs,
            "phases": outputs,
            "failure_text": "\n".join(failures)[-30000:],
            "verification_mode": "layered",
            "verification_attempt": attempt,
            "verification_retry": attempt > 1,
        }


__all__ = ["RuntimeEngine"]
