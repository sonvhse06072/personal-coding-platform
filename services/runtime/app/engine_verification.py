from __future__ import annotations

from pathlib import Path
from typing import Any

from .developer_stream import runtime_activity_event
from .engine_execution import RuntimeEngine as ExecutionRuntimeEngine
from .work_order import work_order_snapshot


class RuntimeEngine(ExecutionRuntimeEngine):
    """Add WorkOrder-aware progressive verification and retry attribution.

    Legacy WorkOrders have no intermediate phases and delegate to the historical
    verification path unchanged. New WorkOrders gate expensive final checks behind
    explicitly declared cheap/intermediate phases. The final required phases still
    determine acceptance; a narrow check only avoids wasting later checks in a
    repair cycle that is already known to be bad.
    """

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
        await super().run_job(job_id)

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
        # Preserve the historical complex/critical acceptance strength even when
        # the PM omitted full_tests from a newer contract.
        if profile in {"complex", "critical"} and "full_tests" not in required:
            required.append("full_tests")

        entries: list[tuple[str, str]] = []
        seen: set[str] = set()
        for phase in intermediate:
            if phase not in seen:
                entries.append((phase, "intermediate"))
                seen.add(phase)
        for phase in required:
            # The governance facade historically owns the extra full_tests call
            # for fast/standard WorkOrders; leave that one phase to it so this
            # layer remains backward-compatible with the existing final gate.
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
                progress["tool_calls"] + tool_calls + count > int(budget["max_tool_calls"])
                or progress["test_runs"] + test_runs + count > int(budget["max_test_runs"])
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
                # Progressive gate: a known-bad candidate does not spend the
                # remaining focused/full verification budget in this repair loop.
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
