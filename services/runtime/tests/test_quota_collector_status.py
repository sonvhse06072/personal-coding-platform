from __future__ import annotations

import asyncio

from app.quota_telemetry_active import ActiveQuotaTelemetryService


class FakeStore:
    def __init__(self) -> None:
        self.snapshots = []
        self.results = []

    def upsert(self, snapshot):
        self.snapshots.append(snapshot)

    def record_collector_result(self, source, *, status, error=None):
        self.results.append((source, status, error))


class FakeCollector:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result if result is not None else []
        self.error = error

    async def collect(self):
        if self.error is not None:
            raise self.error
        return list(self.result)


def test_refresh_marks_success_without_snapshots_as_no_data() -> None:
    store = FakeStore()
    service = ActiveQuotaTelemetryService(store)
    service.collectors = [FakeCollector([])]

    asyncio.run(service.refresh())

    assert store.snapshots == []
    assert store.results == [("antigravity_quota", "no_data", None)]


def test_refresh_marks_snapshot_collection_ok() -> None:
    store = FakeStore()
    service = ActiveQuotaTelemetryService(store)
    snapshot = {"snapshot_key": "x"}
    service.collectors = [FakeCollector([snapshot])]

    asyncio.run(service.refresh())

    assert store.snapshots == [snapshot]
    assert store.results == [("antigravity_quota", "ok", None)]


def test_refresh_persists_collector_error_fail_open() -> None:
    store = FakeStore()
    service = ActiveQuotaTelemetryService(store)
    service.collectors = [FakeCollector(error=RuntimeError("quota unavailable"))]

    asyncio.run(service.refresh())

    assert store.snapshots == []
    assert store.results == [
        ("antigravity_quota", "error", "RuntimeError: quota unavailable")
    ]
