from __future__ import annotations

from typing import Any

from .control_actions import _BUDGET_EXTENSION_SPECS
from .control_actions_live import ControlActionService as LiveControlActionService


_PROVIDER_BLOCK_REASONS = {
    "planner_provider_failure_without_fallback",
    "provider_failure_without_fallback",
    "evaluator_provider_failure_without_fallback",
}


class ControlActionService(LiveControlActionService):
    """Owner controls with provider-aware reroute semantics.

    A reroute means the current provider/model route is not usable. Preserve the
    durable provider health marker while Router selects a replacement so a
    quota-exhausted/unhealthy provider cannot immediately win the fresh route.

    If a provider block coexists with one live exhausted Runtime budget, do not
    enqueue a reroute that cannot safely start. Materialize one explicit combined
    owner action that extends only that bounded dimension and reroutes the same
    job while preserving failed-provider state.
    """

    @classmethod
    def _provider_budget_dimension(cls, job: dict[str, Any]) -> str | None:
        result = dict(job.get("result") or {})
        if str(result.get("reason") or "") not in _PROVIDER_BLOCK_REASONS:
            return None
        return cls._live_budget_dimension(job, "")

    @classmethod
    def _is_budget_recovery_state(cls, job: dict[str, Any]) -> bool:
        return super()._is_budget_recovery_state(job) or cls._provider_budget_dimension(job) is not None

    def blocked_advisory(self, work_order: dict[str, Any], job: dict[str, Any] | None) -> dict[str, Any]:
        current_job = dict(job or {})
        advisory = super().blocked_advisory(work_order, current_job)
        dimension = self._provider_budget_dimension(current_job)
        if dimension is None:
            return advisory

        spec = _BUDGET_EXTENSION_SPECS[dimension]
        safe_actions: list[dict[str, Any]] = []
        for item in advisory.get("action_specs") or []:
            if not isinstance(item, dict):
                continue
            action_type = str(item.get("action_type") or "")
            if action_type == "budget_extend":
                item = dict(item)
                item["label"] = self._combined_budget_reroute_label(
                    dimension,
                    int(spec["increment"]),
                )
                safe_actions.append(item)
            elif action_type in {"details", "keep_blocked"}:
                safe_actions.append(item)
        advisory["action_specs"] = safe_actions
        advisory["recommended"] = (
            f"Phê duyệt action kết hợp +{spec['increment']} cho budget đang cạn và chuyển provider; "
            "Runtime vẫn giữ nguyên cùng job/workspace/counters."
        )
        return advisory

    @staticmethod
    def _combined_budget_reroute_label(dimension: str, increment: int) -> str:
        if dimension == "max_wall_time_minutes":
            return f"➕ +{increment} phút + chuyển provider"
        labels = {
            "max_model_calls": "lượt gọi model",
            "max_tool_calls": "lượt gọi công cụ",
            "max_test_runs": "lượt chạy test",
            "max_repair_iterations": "lượt sửa",
            "max_iterations": "vòng lặp",
        }
        return f"➕ +{increment} {labels.get(dimension, 'ngân sách')} + chuyển provider"

    async def _dispatch(self, action: dict[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("action_type") or "")
        job_id = str(action.get("job_id") or "")

        if action_type == "budget_extend" and job_id:
            job = self.storage.get(job_id)
            if job and self._provider_budget_dimension(dict(job)) is not None:
                authorization = self._apply_budget_extension(action)
                row = await self._resume(
                    job_id,
                    reset_transient_provider_failures=False,
                    reroute=True,
                )
                result = self._resume_result(
                    action,
                    row,
                    "Bounded budget extension approved; the same job was rerouted while preserving failed-provider state.",
                )
                result["budget_authorization"] = authorization
                return result

        if action_type in {"reroute_provider", "reroute_retry", "resume_reroute"}:
            row = await self._resume(
                job_id,
                reset_transient_provider_failures=False,
                reroute=True,
            )
            return self._resume_result(
                action,
                row,
                "The same job was resumed through a fresh eligible route while preserving failed-provider state.",
            )
        return await super()._dispatch(action)
