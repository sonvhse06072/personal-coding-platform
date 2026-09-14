from __future__ import annotations

from copy import deepcopy
from typing import Any

from .engine_antigravity import RuntimeEngine as AntigravityRuntimeEngine
from .quota_telemetry import QuotaTelemetryStore, merge_provider_state


class QuotaAwareRouterProxy:
    """Overlay fresh external quota telemetry immediately before Router calls.

    The durable job/provider failure state remains authoritative. Telemetry can
    only add quota pressure/unavailability; it never clears a persisted failure.
    Stale snapshots are omitted by QuotaTelemetryStore.provider_state().
    """

    def __init__(self, delegate: Any, quota_store: QuotaTelemetryStore) -> None:
        self.delegate = delegate
        self.quota_store = quota_store

    async def health(self) -> bool:
        return await self.delegate.health()

    def _payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        updated = deepcopy(payload)
        updated["provider_state"] = merge_provider_state(
            updated.get("provider_state") or {},
            self.quota_store.provider_state(),
        )
        return updated

    async def route(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.route(self._payload(payload))

    async def staff(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.staff(self._payload(payload))

    async def reassess(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.delegate.reassess(payload)


class RuntimeEngine(AntigravityRuntimeEngine):
    def __init__(self, storage: Any, *, quota_store: QuotaTelemetryStore) -> None:
        super().__init__(storage)
        self.router = QuotaAwareRouterProxy(self.router, quota_store)
