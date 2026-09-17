from __future__ import annotations

from copy import deepcopy
from typing import Any

from .control_actions_reroute import ControlActionService as BaseControlActionService
from .state import checkpoint_from_row
from .storage import now


_INPUT_TOKEN_DIMENSION = "max_input_tokens"
_INPUT_TOKEN_COUNTER = "input_tokens"
_INPUT_TOKEN_INCREMENT = 1_000_000
_INPUT_TOKEN_HARD_MAX = 4_000_000
_INPUT_TOKEN_FAILURE_REASONS = {
    "input-token budget exceeded",
    "input-token budget exhausted",
}
_BUDGET_BLOCK_REASONS = {
    "planner_budget_exhausted",
    "preflight_budget_exhausted",
    "execution_budget_exhausted",
}
_REASSESSMENT_BUDGET_SIGNALS = {
    "hard_budget_guard",
    "hard_budget_overrun",
}


class ControlActionService(BaseControlActionService):
    """Add explicit Human Owner recovery for input-token emergency exhaustion.

    Input-token limits remain hard Router/profile ceilings during autonomous
    execution. This layer adds only the same durable, monotonic owner-approved
    extension semantics used by existing Runtime budget controls. Consumed usage,
    WorkOrder scope and job/workspace identity are never reset.
    """

    @staticmethod
    def _numeric(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _input_token_budget_block(cls, job: dict[str, Any]) -> bool:
        if str(job.get("status") or "") != "blocked":
            return False

        result = dict(job.get("result") or {})
        top_reason = str(result.get("reason") or "")
        failure_reason = ""

        if top_reason in _BUDGET_BLOCK_REASONS:
            failure_reason = str(result.get("last_failure") or "")
        elif top_reason == "reassessment_stopped":
            reassess = dict(result.get("reassess") or {})
            signals = {str(value) for value in reassess.get("signals") or []}
            if str(reassess.get("action") or "") != "stop":
                return False
            if not signals.intersection(_REASSESSMENT_BUDGET_SIGNALS):
                return False
            failure_reason = str(reassess.get("reason") or "")
        else:
            return False

        if failure_reason not in _INPUT_TOKEN_FAILURE_REASONS:
            return False

        route = dict(job.get("route") or {})
        budget = dict((route.get("strategy") or {}).get("budget") or {})
        progress = dict(job.get("progress") or {})
        used = cls._numeric(progress.get(_INPUT_TOKEN_COUNTER))
        limit = cls._numeric(budget.get(_INPUT_TOKEN_DIMENSION))
        return used is not None and limit is not None and used >= limit

    @classmethod
    def _input_token_extension_target(
        cls,
        job: dict[str, Any],
    ) -> tuple[int, int, int] | None:
        route = dict(job.get("route") or {})
        budget = dict((route.get("strategy") or {}).get("budget") or {})
        progress = dict(job.get("progress") or {})
        used_value = cls._numeric(progress.get(_INPUT_TOKEN_COUNTER))
        limit_value = cls._numeric(budget.get(_INPUT_TOKEN_DIMENSION))
        if used_value is None or limit_value is None:
            return None

        used = int(used_value)
        previous_limit = int(limit_value)
        new_limit = min(previous_limit + _INPUT_TOKEN_INCREMENT, _INPUT_TOKEN_HARD_MAX)
        if new_limit <= previous_limit or new_limit <= used:
            return None
        return previous_limit, used, new_limit

    @classmethod
    def _input_token_metric(cls, job: dict[str, Any]) -> dict[str, Any] | None:
        route = dict(job.get("route") or {})
        budget = dict((route.get("strategy") or {}).get("budget") or {})
        progress = dict(job.get("progress") or {})
        used = cls._numeric(progress.get(_INPUT_TOKEN_COUNTER))
        limit = cls._numeric(budget.get(_INPUT_TOKEN_DIMENSION))
        if used is None or limit is None:
            return None
        return {
            "key": _INPUT_TOKEN_DIMENSION,
            "label": "Input token",
            "used": int(used),
            "limit": int(limit),
        }

    def blocked_advisory(
        self,
        work_order: dict[str, Any],
        job: dict[str, Any] | None,
    ) -> dict[str, Any]:
        advisory = super().blocked_advisory(work_order, job)
        current_job = dict(job or {})
        if not self._input_token_budget_block(current_job):
            return advisory

        metric = self._input_token_metric(current_job)
        metrics = [
            dict(item)
            for item in advisory.get("metrics") or []
            if not (
                isinstance(item, dict)
                and item.get("key") == _INPUT_TOKEN_DIMENSION
            )
        ]
        if metric is not None:
            metrics.insert(0, metric)
        advisory["metrics"] = metrics

        safe_actions = [
            dict(item)
            for item in advisory.get("action_specs") or []
            if isinstance(item, dict)
            and str(item.get("action_type") or "") in {"details", "keep_blocked"}
        ]
        target = self._input_token_extension_target(current_job)
        if target is not None:
            safe_actions.insert(
                0,
                {
                    "action_type": "budget_extend",
                    "label": "➕ +1.000.000 input token",
                    "payload": {
                        "dimension": _INPUT_TOKEN_DIMENSION,
                        "increment": _INPUT_TOKEN_INCREMENT,
                    },
                },
            )
        advisory["action_specs"] = safe_actions
        advisory["summary"] = "Runtime đã chạm giới hạn input-token cứng của route hiện tại."
        advisory["cause"] = (
            "Input-token usage đã được tính theo telemetry cache-aware hiện có và live counter "
            "đã vượt giới hạn hiện tại; Runtime giữ blocked cho đến khi Human Owner phê duyệt "
            "một mở rộng có giới hạn."
        )
        if target is not None:
            advisory["recommended"] = (
                "Chỉ phê duyệt +1.000.000 input token nếu WorkOrder hiện tại vẫn cần hoàn tất "
                "verification/review; usage đã tiêu thụ không bị reset và tổng limit không thể vượt 4.000.000."
            )
        else:
            advisory["recommended"] = (
                "Giữ WorkOrder blocked: +1.000.000 không thể tạo runnable headroom trong hard maximum 4.000.000. "
                "Không reset counter, không tăng trần tự động và không force-complete."
            )
        return advisory

    def _apply_budget_extension(self, action: dict[str, Any]) -> dict[str, Any]:
        payload = dict(action.get("payload") or {})
        dimension = str(payload.get("dimension") or "")
        if dimension != _INPUT_TOKEN_DIMENSION:
            return super()._apply_budget_extension(action)

        job_id = str(action.get("job_id") or "")
        if not job_id:
            raise RuntimeError("Budget extension requires a Runtime job")
        job = self.storage.get(job_id)
        if not job:
            raise RuntimeError("Unknown job")
        job = dict(job)
        if not self._input_token_budget_block(job):
            raise RuntimeError(
                "Input-token budget extension no longer matches the live blocked state"
            )

        increment = int(payload.get("increment") or 0)
        if increment != _INPUT_TOKEN_INCREMENT:
            raise RuntimeError("Input-token budget extension increment is not authorized")

        target = self._input_token_extension_target(job)
        if target is None:
            raise RuntimeError(
                "Input-token budget extension cannot restore runnable headroom within the platform hard maximum"
            )
        previous_limit, used, new_limit = target

        route = deepcopy(job.get("route") or {})
        strategy = dict(route.get("strategy") or {})
        budget = dict(strategy.get("budget") or {})
        if _INPUT_TOKEN_DIMENSION not in budget:
            raise RuntimeError("Current route does not expose max_input_tokens")

        budget[_INPUT_TOKEN_DIMENSION] = new_limit
        strategy["budget"] = budget
        route["strategy"] = strategy

        checkpoint = checkpoint_from_row(job)
        authorizations = list(checkpoint.get("budget_authorizations") or [])
        authorizations.append(
            {
                "action_id": action["action_id"],
                "channel": "telegram",
                "dimension": _INPUT_TOKEN_DIMENSION,
                "previous_limit": previous_limit,
                "new_limit": new_limit,
                "used": used,
                "approved_at": now().isoformat(),
            }
        )
        checkpoint["budget_authorizations"] = authorizations[-20:]
        self.storage.update(job_id, route=route, checkpoint=checkpoint)
        return {
            "dimension": _INPUT_TOKEN_DIMENSION,
            "previous_limit": previous_limit,
            "new_limit": new_limit,
            "used": used,
        }


__all__ = ["ControlActionService"]
