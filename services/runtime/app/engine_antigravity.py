from __future__ import annotations

from copy import deepcopy
from typing import Any

from .engine import RuntimeEngine as BaseRuntimeEngine
from .quota_storage import QuotaStorage
from .quota_telemetry import ProviderQuotaTelemetry
from .state import (
    checkpoint_from_row,
    clear_transient_provider_failures,
    migrate_legacy_antigravity_quota_failure,
)


_REASONING_ORDER = ["low", "medium", "high"]
_REASONING_ADAPTERS = {"codex_cli", "antigravity_host"}
_ANTIGRAVITY_QUOTA_FAILURES = {"quota_exhausted", "rate_limited"}
_QUOTA_FAILURES = {"quota_exhausted", "rate_limited"}


class RuntimeEngine(BaseRuntimeEngine):
    """Runtime engine with provider quota-aware routing and recovery semantics."""

    def __init__(self, storage: Any) -> None:
        super().__init__(storage)
        # Quota is platform-wide resource state, not job-owned state. Keep its
        # persistence separate while sharing Runtime's PostgreSQL database.
        self.quota_storage = QuotaStorage()
        self.quota_telemetry = ProviderQuotaTelemetry(self.quota_storage)

    async def start(self) -> None:
        self.quota_storage.ensure_quota_table()
        await super().start()
        await self.quota_telemetry.start()

    async def stop(self) -> None:
        await self.quota_telemetry.stop()
        await super().stop()

    async def _refresh_and_apply_quota_state(self, job_id: str) -> None:
        try:
            await self.quota_telemetry.refresh_if_stale()
        except Exception:
            # Telemetry is deliberately fail-open. Existing durable provider
            # health remains authoritative if collection is unavailable.
            pass
        row = self.storage.get(job_id)
        if not row:
            return
        checkpoint = checkpoint_from_row(row)
        current = dict(checkpoint.get("provider_state") or {})
        effective = self.quota_telemetry.apply_to_provider_state(current)
        if effective != current:
            checkpoint["provider_state"] = effective
            self.storage.update(job_id, checkpoint=checkpoint)

    async def run_job(self, job_id: str) -> None:
        row = self.storage.get(job_id)
        if row and row.get("status") == "queued":
            await self._refresh_and_apply_quota_state(job_id)
        await super().run_job(job_id)

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
        if failure_kind in _QUOTA_FAILURES:
            provider = str(current_choice.get("provider") or "")
            if provider in {"openai", "google_antigravity"}:
                try:
                    await self.quota_telemetry.refresh(providers={provider})
                except Exception:
                    pass
        # Preserve the concrete failure for the current reroute even if the
        # background read reports remaining capacity: a just-failed resource
        # should not immediately win the same failover decision.
        return await super()._provider_failover(
            route_payload=route_payload,
            provider_state=provider_state,
            current_choice=current_choice,
            failure_kind=failure_kind,
            progress=progress,
            strategy=strategy,
            role=role,
        )

    async def resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool = False,
        reroute: bool = False,
        _allow_failed_orchestrated_resume: bool = False,
    ) -> dict[str, Any]:
        row = self.storage.get(job_id)
        if row:
            try:
                await self.quota_telemetry.refresh_if_stale()
            except Exception:
                pass
            checkpoint = checkpoint_from_row(row)
            if reset_transient_provider_failures:
                checkpoint = clear_transient_provider_failures(checkpoint)
            elif reroute:
                # A preserved reroute from a pre-v1.0.35 job may still carry
                # the old provider-wide Antigravity quota marker. Narrow it
                # only when durable failure evidence proves a quota failure.
                checkpoint = migrate_legacy_antigravity_quota_failure(
                    checkpoint,
                    deepcopy(row.get("progress") or {}),
                )
            checkpoint["provider_state"] = self.quota_telemetry.apply_to_provider_state(
                dict(checkpoint.get("provider_state") or {})
            )
            self.storage.update(job_id, checkpoint=checkpoint)

        # We already applied an explicit reset above, then re-added only fresh
        # authoritative quota pressure. Passing reset=True again would erase it.
        return await super().resume(
            job_id,
            reset_transient_provider_failures=False,
            reroute=reroute,
            _allow_failed_orchestrated_resume=_allow_failed_orchestrated_resume,
        )
