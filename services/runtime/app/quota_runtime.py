from __future__ import annotations

import asyncio
import time
from typing import Any

from .quota_telemetry import merge_provider_state
from .quota_telemetry_active import ActiveQuotaTelemetryService, ActiveQuotaTelemetryStore


class QuotaTelemetryCoordinator:
    """Maintain proactive quota snapshots and enrich route/staff decisions, fail-open."""

    def __init__(self) -> None:
        self.store = ActiveQuotaTelemetryStore()
        self.service = ActiveQuotaTelemetryService(self.store)
        self._initialized = False
        self._lock = asyncio.Lock()
        self._last_refresh_monotonic = 0.0
        self._started = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self.store.init()
        self._initialized = True

    async def start(self) -> None:
        """Start an independent fail-open collector loop.

        Quota polling is platform telemetry, not a WorkOrder action: it does not
        increment model/tool/test counters and it does not depend on a job being
        runnable. The service persists collector errors instead of raising them
        into Runtime startup/execution semantics.
        """
        if self._started:
            return
        try:
            self._ensure_initialized()
            await self.service.start()
            self._last_refresh_monotonic = time.monotonic()
            self._started = True
        except Exception:
            # A missing database/provider telemetry surface must never stop Runtime.
            self._started = False

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self.service.stop()
        finally:
            self._started = False

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
