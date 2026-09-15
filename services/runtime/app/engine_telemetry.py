from __future__ import annotations

from typing import Any

from .engine_antigravity import RuntimeEngine as AntigravityRuntimeEngine


class TelemetryRouterProxy:
    """Add sparse historical evidence to routing without owning routing policy."""

    def __init__(self, delegate: Any, storage: Any) -> None:
        self.delegate = delegate
        self.storage = storage

    async def health(self) -> bool:
        return await self.delegate.health()

    async def staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.staff(payload)

    async def reassess(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.reassess(payload)

    async def route(self, payload: dict[str, Any]) -> dict[str, Any]:
        updated = dict(payload)
        job_id = str(updated.get("job_id") or "")
        project_id = str(updated.get("project_id") or "")
        task = updated.get("task") or {}
        task_type = str(task.get("task_type") or "unknown")
        row = self.storage.get(job_id) if job_id else None
        checkpoint = (row or {}).get("checkpoint") or {}
        work_order = checkpoint.get("work_order") or {}
        role = str(work_order.get("requested_role") or "developer")

        try:
            calibration = self.storage.calibration_hint(
                project_id=project_id,
                task_type=task_type,
                role=role,
            )
        except Exception:
            # Telemetry is advisory. A metrics-store/read failure must not turn
            # into a routing outage or weaken the existing deterministic policy.
            calibration = {
                "sample_size": 0,
                "minimum_sample_size": 5,
                "sufficient_sample": False,
                "resource_multipliers": {},
                "model_success": {},
            }

        if calibration.get("sufficient_sample"):
            provider_state = {
                key: dict(value) if isinstance(value, dict) else value
                for key, value in (updated.get("provider_state") or {}).items()
            }
            for model_id, evidence in (calibration.get("model_success") or {}).items():
                if not isinstance(evidence, dict):
                    continue
                state = dict(provider_state.get(model_id) or {})
                state["predicted_success"] = evidence.get("success_rate")
                provider_state[model_id] = state
            updated["provider_state"] = provider_state

        updated["calibration"] = {
            "sample_size": int(calibration.get("sample_size", 0) or 0),
            "minimum_sample_size": int(calibration.get("minimum_sample_size", 5) or 5),
            "resource_multipliers": dict(calibration.get("resource_multipliers") or {}),
            "source": "project_task_role_history",
        }
        return await self.delegate.route(updated)


class RuntimeEngine(AntigravityRuntimeEngine):
    def __init__(self, storage: Any) -> None:
        super().__init__(storage)
        self.router = TelemetryRouterProxy(self.router, self.storage)


__all__ = ["RuntimeEngine", "TelemetryRouterProxy"]
