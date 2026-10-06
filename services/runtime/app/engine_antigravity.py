from __future__ import annotations

from copy import deepcopy
from typing import Any

from .engine import RuntimeEngine as BaseRuntimeEngine
from .quota_runtime import quota_coordinator
from .state import checkpoint_from_row, migrate_legacy_provider_quota_failure


class RuntimeEngine(BaseRuntimeEngine):
    """Runtime engine with Antigravity model/quota-aware recovery semantics."""

    async def start(self) -> None:
        await super().start()
        # Provider allowance is platform telemetry, independent of any WorkOrder.
        # Coordinator startup is fail-open and never prevents Runtime readiness.
        await quota_coordinator.start()

    async def stop(self) -> None:
        # Stop the advisory collector before Runtime tears down its worker loop.
        await quota_coordinator.stop()
        await super().stop()

    @staticmethod
    def _mark_provider_failure(
        provider_state: dict[str, Any],
        choice: dict[str, Any],
        kind: str,
    ) -> None:
        # Core now owns provider/quota scoping. It keeps Antigravity direct quota
        # failures model-scoped while using registered shared quota groups for
        # providers such as Codex/OpenAI.
        BaseRuntimeEngine._mark_provider_failure(provider_state, choice, kind)

    async def resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool = False,
        reroute: bool = False,
        verification_only_after_pm_handoff: bool = False,
        _allow_failed_orchestrated_resume: bool = False,
        _require_changed_file_headroom: bool = False,
    ) -> dict[str, Any]:
        # A preserved pre-fix reroute may still carry a provider-wide marker for
        # a proven quota/rate-limit failure. Narrow only that proven marker before
        # Router sees state; auth/config/provider failures stay provider-wide.
        if reroute and not reset_transient_provider_failures:
            row = self.storage.get(job_id)
            if row:
                checkpoint = checkpoint_from_row(row)
                migrated = migrate_legacy_provider_quota_failure(
                    checkpoint,
                    deepcopy(row.get("progress") or {}),
                    failed_at=row.get("updated_at"),
                )
                if migrated != checkpoint:
                    self.storage.update(job_id, checkpoint=migrated)

        return await super().resume(
            job_id,
            reset_transient_provider_failures=reset_transient_provider_failures,
            reroute=reroute,
            verification_only_after_pm_handoff=verification_only_after_pm_handoff,
            _allow_failed_orchestrated_resume=_allow_failed_orchestrated_resume,
            _require_changed_file_headroom=_require_changed_file_headroom,
        )
