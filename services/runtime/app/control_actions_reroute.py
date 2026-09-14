from __future__ import annotations

from typing import Any

from .control_actions_live import ControlActionService as LiveControlActionService


class ControlActionService(LiveControlActionService):
    """Owner controls with provider-aware reroute semantics.

    A reroute means the current provider/model route is not usable. Preserve the
    durable provider health marker while Router selects a replacement so a
    quota-exhausted/unhealthy provider cannot immediately win the fresh route.

    Explicit recovery assertions such as provider_quota_reset and
    provider_credentials_fixed remain implemented by the base class and still
    clear provider failure state before retrying/rerouting.
    """

    async def _dispatch(self, action: dict[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("action_type") or "")
        if action_type in {"reroute_provider", "reroute_retry", "resume_reroute"}:
            job_id = str(action.get("job_id") or "")
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
