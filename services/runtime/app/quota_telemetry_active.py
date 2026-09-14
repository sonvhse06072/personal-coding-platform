from __future__ import annotations

from typing import Any
import os

import httpx

from .quota_telemetry import QuotaTelemetryStore, utcnow
from .quota_telemetry_policy import (
    PolicyAntigravityQuotaCollector,
    PolicyCodexQuotaCollector,
    PolicyQuotaTelemetryService,
)


class ActiveAntigravityQuotaCollector(PolicyAntigravityQuotaCollector):
    """Allow enough bounded time for Antigravity's read-only `/usage` refresh."""

    async def _request(self) -> dict[str, Any]:
        base = os.getenv("ANTIGRAVITY_BRIDGE_URL", "").rstrip("/")
        token = os.getenv("ANTIGRAVITY_BRIDGE_TOKEN", "").strip()
        if not base or not token:
            raise RuntimeError("Antigravity bridge quota telemetry is not configured")
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(
                f"{base}/quota",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return dict(response.json())


class ActiveQuotaTelemetryStore(QuotaTelemetryStore):
    def record_collector_result(
        self,
        source: str,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        if status not in {"ok", "no_data", "error"}:
            raise ValueError(f"Unsupported quota collector status: {status}")
        timestamp = utcnow()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_quota_collectors(source,status,last_attempt_at,last_success_at,error)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT(source) DO UPDATE SET
                  status=EXCLUDED.status,
                  last_attempt_at=EXCLUDED.last_attempt_at,
                  last_success_at=CASE WHEN EXCLUDED.status='ok' THEN EXCLUDED.last_success_at ELSE cp_quota_collectors.last_success_at END,
                  error=EXCLUDED.error""",
                (
                    source,
                    status,
                    timestamp,
                    timestamp if status == "ok" else None,
                    (error or "")[:1000] or None,
                ),
            )
            conn.commit()


class ActiveQuotaTelemetryService(PolicyQuotaTelemetryService):
    def __init__(self, store: ActiveQuotaTelemetryStore) -> None:
        super().__init__(store)
        self.collectors = [PolicyCodexQuotaCollector(), ActiveAntigravityQuotaCollector()]

    async def refresh(self) -> None:
        for collector in self.collectors:
            source = (
                "codex_app_server"
                if isinstance(collector, PolicyCodexQuotaCollector)
                and not isinstance(collector, ActiveAntigravityQuotaCollector)
                else "antigravity_quota"
            )
            try:
                snapshots = await collector.collect()
                for snapshot in snapshots:
                    self.store.upsert(snapshot)
                self.store.record_collector_result(
                    source,
                    status="ok" if snapshots else "no_data",
                )
            except Exception as exc:
                self.store.record_collector_result(
                    source,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
