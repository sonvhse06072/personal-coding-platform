from __future__ import annotations

from copy import deepcopy
from typing import Any

from .control_actions import _BUDGET_EXTENSION_SPECS
from .control_actions_live import ControlActionService as LiveControlActionService
from .state import checkpoint_from_row
from .storage import now


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

    If a provider block coexists with one or more exhausted Runtime budgets, do
    not enqueue a reroute that cannot safely start. Materialize one explicit
    owner action that extends exactly the exhausted bounded dimensions and then
    reroutes the same job while preserving failed-provider state.
    """

    @classmethod
    def _provider_budget_dimensions(cls, job: dict[str, Any]) -> list[str]:
        result = dict(job.get("result") or {})
        if str(result.get("reason") or "") not in _PROVIDER_BLOCK_REASONS:
            return []

        route = dict(job.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        budget = dict(strategy.get("budget") or {})
        progress = dict(job.get("progress") or {})
        exhausted: list[str] = []
        for dimension, spec in _BUDGET_EXTENSION_SPECS.items():
            if dimension not in budget:
                continue
            used = cls._numeric(progress.get(spec["counter"], 0))
            limit = cls._numeric(budget.get(dimension))
            if used is None or limit is None:
                continue
            if used >= limit:
                exhausted.append(dimension)

        if exhausted:
            return exhausted

        # Preserve the existing near-wall recovery behavior when no counter has
        # crossed its limit yet but less than the live recovery threshold remains.
        dimension = cls._live_budget_dimension(job, "")
        return [dimension] if dimension else []

    @classmethod
    def _provider_budget_dimension(cls, job: dict[str, Any]) -> str | None:
        """Backward-compatible single-dimension view used by older callers/tests."""
        dimensions = cls._provider_budget_dimensions(job)
        return dimensions[0] if len(dimensions) == 1 else None

    @classmethod
    def _is_budget_recovery_state(cls, job: dict[str, Any]) -> bool:
        return super()._is_budget_recovery_state(job) or bool(cls._provider_budget_dimensions(job))

    def blocked_advisory(self, work_order: dict[str, Any], job: dict[str, Any] | None) -> dict[str, Any]:
        current_job = dict(job or {})
        advisory = super().blocked_advisory(work_order, current_job)
        dimensions = self._provider_budget_dimensions(current_job)
        if not dimensions:
            return advisory

        # Make every exhausted dimension visible to the owner, including
        # max_iterations which the generic metric appendix intentionally omits.
        for dimension in dimensions:
            if any(
                isinstance(metric, dict) and metric.get("key") == dimension
                for metric in advisory.get("metrics") or []
            ):
                continue
            metric = self._budget_metric(current_job, dimension)
            if metric:
                advisory.setdefault("metrics", []).append(metric)

        safe_actions = [
            dict(item)
            for item in advisory.get("action_specs") or []
            if isinstance(item, dict)
            and str(item.get("action_type") or "") in {"details", "keep_blocked"}
        ]

        if len(dimensions) == 1:
            dimension = dimensions[0]
            spec = _BUDGET_EXTENSION_SPECS[dimension]
            safe_actions.insert(
                0,
                {
                    "action_type": "budget_extend",
                    "label": self._combined_budget_reroute_label(
                        dimension,
                        int(spec["increment"]),
                    ),
                    "payload": {
                        "dimension": dimension,
                        "increment": int(spec["increment"]),
                    },
                },
            )
        else:
            extensions = [
                {
                    "dimension": dimension,
                    "increment": int(_BUDGET_EXTENSION_SPECS[dimension]["increment"]),
                }
                for dimension in dimensions
            ]
            safe_actions.insert(
                0,
                {
                    "action_type": "budget_extend_bundle",
                    "label": self._combined_budget_bundle_reroute_label(extensions),
                    "payload": {"extensions": extensions},
                },
            )

        advisory["action_specs"] = safe_actions
        advisory["recommended"] = (
            "Phê duyệt một action kết hợp để mở đúng các budget đang cạn và chuyển provider; "
            "Runtime vẫn giữ nguyên cùng job/workspace/counters."
        )
        return advisory

    @staticmethod
    def _budget_increment_label(dimension: str, increment: int) -> str:
        labels = {
            "max_model_calls": "lượt gọi model",
            "max_tool_calls": "lượt gọi công cụ",
            "max_test_runs": "lượt chạy test",
            "max_wall_time_minutes": "phút",
            "max_repair_iterations": "lượt sửa",
            "max_iterations": "vòng lặp",
        }
        return f"+{increment} {labels.get(dimension, 'ngân sách')}"

    @classmethod
    def _combined_budget_reroute_label(cls, dimension: str, increment: int) -> str:
        return f"➕ {cls._budget_increment_label(dimension, increment)} + chuyển provider"

    @classmethod
    def _combined_budget_bundle_reroute_label(cls, extensions: list[dict[str, Any]]) -> str:
        pieces = [
            cls._budget_increment_label(
                str(item.get("dimension") or ""),
                int(item.get("increment") or 0),
            )
            for item in extensions
        ]
        return f"➕ {', '.join(pieces)} + chuyển provider"

    def _apply_budget_extension_bundle(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        job_id = str(action.get("job_id") or "")
        if not job_id:
            raise RuntimeError("Budget extension bundle requires a Runtime job")
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")

        payload = dict(action.get("payload") or {})
        requested = list(payload.get("extensions") or [])
        if len(requested) < 2:
            raise RuntimeError("Budget extension bundle requires multiple dimensions")

        live_dimensions = self._provider_budget_dimensions(dict(job))
        requested_dimensions = [
            str(item.get("dimension") or "")
            for item in requested
            if isinstance(item, dict)
        ]
        if requested_dimensions != live_dimensions:
            raise RuntimeError("Budget extension bundle no longer matches live exhausted dimensions")
        if len(set(requested_dimensions)) != len(requested_dimensions):
            raise RuntimeError("Budget extension bundle contains duplicate dimensions")

        route = deepcopy(job.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        budget = dict(strategy.get("budget") or {})
        progress = dict(job.get("progress") or {})
        authorizations: list[dict[str, Any]] = []

        # Validate every extension before mutating the durable route so the bundle
        # is all-or-nothing from the job's perspective.
        for item in requested:
            dimension = str(item.get("dimension") or "")
            spec = _BUDGET_EXTENSION_SPECS.get(dimension)
            if spec is None:
                raise RuntimeError("Unsupported budget extension dimension")
            increment = int(item.get("increment") or 0)
            if increment != int(spec["increment"]):
                raise RuntimeError("Budget extension increment is not authorized")
            if dimension not in budget:
                raise RuntimeError("Current route does not expose the requested budget dimension")

            previous_limit = (
                float(budget[dimension])
                if dimension == "max_wall_time_minutes"
                else int(budget[dimension])
            )
            new_limit = min(previous_limit + increment, spec["hard_max"])
            if new_limit <= previous_limit:
                raise RuntimeError("Budget extension reached the platform hard maximum")
            used = progress.get(spec["counter"], 0)
            budget[dimension] = new_limit
            authorizations.append({
                "action_id": action["action_id"],
                "channel": "telegram",
                "dimension": dimension,
                "previous_limit": previous_limit,
                "new_limit": new_limit,
                "used": used,
                "approved_at": now().isoformat(),
                "bundle": True,
            })

        strategy["budget"] = budget
        route["strategy"] = strategy
        checkpoint = checkpoint_from_row(job)
        existing = list(checkpoint.get("budget_authorizations") or [])
        checkpoint["budget_authorizations"] = (existing + authorizations)[-20:]
        self.storage.update(job_id, route=route, checkpoint=checkpoint)
        return authorizations

    async def _dispatch(self, action: dict[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("action_type") or "")
        job_id = str(action.get("job_id") or "")

        if action_type == "budget_extend_bundle" and job_id:
            authorizations = self._apply_budget_extension_bundle(action)
            row = await self._resume(
                job_id,
                reset_transient_provider_failures=False,
                reroute=True,
            )
            result = self._resume_result(
                action,
                row,
                "Bounded budget extensions approved atomically; the same job was rerouted while preserving failed-provider state.",
            )
            result["budget_authorizations"] = authorizations
            return result

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
