from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from .delivery import DeliveryError, deliver_verified_work, pull_request_body
from .engine_execution import RuntimeEngine as ExecutionRuntimeEngine
from .fingerprint import failure_fingerprint


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

    @classmethod
    def _verified_result_needs_delivery(cls, row: dict[str, Any]) -> bool:
        result = cls._accepted_result_for_delivery(row)
        if not result:
            return False
        delivery = result.get("delivery") or {}
        if delivery.get("state") == "ci_failure":
            return False
        route = result.get("route") or row.get("route") or {}
        permissions = (route.get("strategy") or {}).get("permissions") or {}
        return bool(permissions.get("push_ai_branch", False)) and bool(result.get("commit"))

    @staticmethod
    def _delivery_wait_seconds(strategy: dict[str, Any], progress: dict[str, Any]) -> int:
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

    async def run_job(self, job_id: str) -> None:
        # If Runtime restarted or a delivery dependency failed after local
        # verification/commit, resume the idempotent delivery step instead of
        # spending another model call on already-verified work.
        before = self.storage.get(job_id)
        accepted = self._accepted_result_for_delivery(before) if before else None
        if (
            before
            and before.get("status") == "queued"
            and accepted
            and self._verified_result_needs_delivery(before)
        ):
            self.storage.update(job_id, status="delivering", result=accepted, error=None)
        else:
            await super().run_job(job_id)

        while True:
            row = self.storage.get(job_id)
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
            progress = deepcopy(row.get("progress") or {})
            progress["delivery_attempts"] = int(progress.get("delivery_attempts", 0)) + 1
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
                progress["ci_failures"] = int(progress.get("ci_failures", 0)) + 1
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

            result["delivery_finalized"] = True
            checkpoint["last_failure"] = None
            self.storage.update(
                job_id,
                status="completed",
                result=result,
                progress=progress,
                checkpoint=checkpoint,
                error=None,
            )
            return
