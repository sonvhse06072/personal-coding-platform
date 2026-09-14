from __future__ import annotations

import asyncio
import time
from typing import Any

from .quota_telemetry import QuotaTelemetryService, QuotaTelemetryStore, merge_provider_state


class QuotaTelemetryCoordinator:
    """Refresh external quota state before route/staff decisions, fail-open."""

    def __init__(self) -> None:
        self.store = QuotaTelemetryStore()
        self.service = QuotaTelemetryService(self.store)
        self._initialized = False
        self._lock = asyncio.Lock()
        self._last_refresh_monotonic = 0.0

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self.store.init()
        self._initialized = True

    async def refresh_if_due(self) -> None:
        self._ensure_initialized()
        now = time.monotonic()
        if now - self._last_refresh_monotonic < self.service.interval:
            return
        async with self._lock:
            now = time.monotonic()
            if now - self._last_refresh_monotonic < self.service.interval:
                return
            try:
                await self.service.refresh()
            finally:
                # Collector failures are persisted by the service itself. Bound
                # repeated external reads even when both providers are unavailable.
                self._last_refresh_monotonic = time.monotonic()

    async def enrich(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            await self.refresh_if_due()
            telemetry = self.store.provider_state()
        except Exception:
            # Quota telemetry is advisory resource state. It must never become a
            # new execution/control-plane dependency.
            telemetry = {}
        updated = dict(payload)
        updated["provider_state"] = merge_provider_state(
            updated.get("provider_state") or {}, telemetry
        )
        return updated

    def view(self) -> dict[str, Any]:
        try:
            self._ensure_initialized()
            return self.store.view()
        except Exception as exc:
            return {
                "snapshots": [],
                "collectors": [],
                "provider_state": {},
                "error": f"{type(exc).__name__}: {exc}",
            }


quota_coordinator = QuotaTelemetryCoordinator()
