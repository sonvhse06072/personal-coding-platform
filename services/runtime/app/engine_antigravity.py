from __future__ import annotations

from copy import deepcopy
from typing import Any

from .engine import RuntimeEngine as BaseRuntimeEngine
from .state import checkpoint_from_row, migrate_legacy_antigravity_quota_failure


_REASONING_ORDER = ["low", "medium", "high"]
_REASONING_ADAPTERS = {"codex_cli", "antigravity_host"}
_ANTIGRAVITY_QUOTA_FAILURES = {"quota_exhausted", "rate_limited"}


class RuntimeEngine(BaseRuntimeEngine):
    """Runtime engine with Antigravity model/quota-aware recovery semantics."""

    @staticmethod
    def _next_reasoning_choice(
        current_choice: dict[str, Any],
        strategy: dict[str, Any],
        role: str = "executor",
    ) -> dict[str, Any] | None:
        if current_choice.get("adapter") not in _REASONING_ADAPTERS:
            return None
        current = current_choice.get("reasoning_effort")
        ceiling = (strategy.get("reasoning_ceiling") or {}).get(role)
        if current not in _REASONING_ORDER or ceiling not in _REASONING_ORDER:
            return None
        current_idx = _REASONING_ORDER.index(current)
        ceiling_idx = _REASONING_ORDER.index(ceiling)
        if current_idx >= ceiling_idx:
            return None
        next_choice = dict(current_choice)
        next_choice["reasoning_effort"] = _REASONING_ORDER[current_idx + 1]
        reasons = list(next_choice.get("reasons") or [])
        reasons.append(f"reasoning escalation {current}->{next_choice['reasoning_effort']}")
        next_choice["reasons"] = reasons
        return next_choice

    @staticmethod
    def _mark_provider_failure(
        provider_state: dict[str, Any],
        choice: dict[str, Any],
        kind: str,
    ) -> None:
        """Keep observed Antigravity quota failures below provider scope.

        `/usage` exposes model-specific quota while Antigravity also reports
        broader quota families. A failure from one selected model is therefore
        insufficient evidence that every model in its family is exhausted. Mark
        only `quota:model:<logical-id>` here. A separate authoritative telemetry
        source may populate `quota:<group>` when the shared bucket itself is known
        exhausted. Auth/bridge/provider failures remain provider-wide.
        """
        provider = str(choice.get("provider") or "")
        if provider == "google_antigravity" and kind in _ANTIGRAVITY_QUOTA_FAILURES:
            model_id = str(choice.get("id") or "").strip()
            if model_id:
                key = f"quota:model:{model_id}"
                state = dict(provider_state.get(key) or {})
                state.update(
                    {
                        "healthy": False,
                        "available": False,
                        "error_rate": 1.0,
                        "quota_pressure": 1.0,
                    }
                )
                provider_state[key] = state
                return
        BaseRuntimeEngine._mark_provider_failure(provider_state, choice, kind)

    async def resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool = False,
        reroute: bool = False,
        _allow_failed_orchestrated_resume: bool = False,
    ) -> dict[str, Any]:
        # A preserved reroute from a pre-v1.0.35 job may still carry the old
        # provider-wide Antigravity quota marker. Narrow it before Router sees
        # state so other explicit Antigravity models remain eligible.
        if reroute and not reset_transient_provider_failures:
            row = self.storage.get(job_id)
            if row:
                checkpoint = checkpoint_from_row(row)
                migrated = migrate_legacy_antigravity_quota_failure(
                    checkpoint,
                    deepcopy(row.get("progress") or {}),
                )
                if migrated != checkpoint:
                    self.storage.update(job_id, checkpoint=migrated)

        return await super().resume(
            job_id,
            reset_transient_provider_failures=reset_transient_provider_failures,
            reroute=reroute,
            _allow_failed_orchestrated_resume=_allow_failed_orchestrated_resume,
        )
