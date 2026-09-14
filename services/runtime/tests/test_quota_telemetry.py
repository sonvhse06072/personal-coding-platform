from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import quota_telemetry
from app.quota_telemetry import (
    ProviderQuotaTelemetry,
    collect_codex_quota,
    normalize_antigravity_usage,
    normalize_codex_rate_limits,
)


NOW = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def list_quota_snapshots(self, provider=None):
        rows = self.rows
        if provider:
            rows = [row for row in rows if row.get("provider") == provider]
        return [dict(row) for row in rows]

    def replace_provider_quota_snapshots(self, provider, snapshots):
        self.rows = [row for row in self.rows if row.get("provider") != provider]
        for snapshot in snapshots:
            row = dict(snapshot)
            row["observed_at"] = datetime.fromisoformat(row["observed_at"])
            if row.get("resets_at"):
                row["resets_at"] = datetime.fromisoformat(row["resets_at"])
            self.rows.append(row)


def test_codex_rate_limits_normalize_primary_and_secondary_windows():
    snapshots = normalize_codex_rate_limits(
        {
            "ordinaryUsageAllowed": True,
            "rateLimitsByLimitId": {
                "codex": {
                    "limitId": "codex",
                    "limitName": "Codex",
                    "primary": {
                        "usedPercent": 72.5,
                        "windowDurationMins": 300,
                        "resetsAt": 1789430400,
                    },
                    "secondary": {
                        "usedPercent": 31.0,
                        "windowDurationMins": 10080,
                        "resetsAt": 1789948800,
                    },
                }
            },
        },
        observed_at=NOW,
    )

    assert len(snapshots) == 2
    primary = next(row for row in snapshots if row["quota_key"] == "codex:primary")
    weekly = next(row for row in snapshots if row["quota_key"] == "codex:secondary")
    assert primary["used_percent"] == 72.5
    assert primary["remaining_percent"] == 27.5
    assert primary["window_minutes"] == 300
    assert primary["quota_group"] == "codex_chatgpt_plus"
    assert primary["available"] is True
    assert weekly["window_minutes"] == 10080
    assert weekly["resets_at"].endswith("+00:00")


def test_codex_null_permission_does_not_claim_recovery_from_percent_only():
    snapshots = normalize_codex_rate_limits(
        {
            "ordinaryUsageAllowed": None,
            "rateLimits": {
                "limitId": "codex",
                "primary": {"usedPercent": 20, "windowDurationMins": 300},
            },
        },
        observed_at=NOW,
    )

    assert snapshots[0]["used_percent"] == 20.0
    assert snapshots[0]["available"] is None


def test_codex_100_percent_is_authoritative_exhaustion_even_without_permission_flag():
    snapshots = normalize_codex_rate_limits(
        {
            "ordinaryUsageAllowed": None,
            "rateLimits": {
                "limitId": "codex",
                "primary": {"usedPercent": 100, "windowDurationMins": 300},
            },
        },
        observed_at=NOW,
    )

    assert snapshots[0]["available"] is False
    assert snapshots[0]["remaining_percent"] == 0.0


def test_antigravity_statusline_bucket_normalizes_remaining_and_reset():
    snapshots = normalize_antigravity_usage(
        {
            "quota": {
                "gemini-weekly": {
                    "remaining_fraction": 0.9378,
                    "reset_time": "2026-09-20T12:00:00Z",
                    "reset_in_seconds": 100,
                }
            }
        },
        observed_at=NOW,
    )

    assert len(snapshots) == 1
    row = snapshots[0]
    assert row["quota_key"] == "gemini-weekly"
    assert row["remaining_percent"] == 93.78
    assert row["used_percent"] == pytest.approx(6.22)
    assert row["quota_group"] == "antigravity_gemini"
    assert row["model_id"] is None
    assert row["resets_at"] == "2026-09-20T12:00:00+00:00"


def test_antigravity_model_specific_quota_maps_to_logical_model():
    snapshots = normalize_antigravity_usage(
        {
            "models": [
                {
                    "model": "gemini-3.1-pro-high",
                    "remaining_fraction": 0.25,
                    "reset_in_seconds": 3600,
                }
            ]
        },
        observed_at=NOW,
    )

    assert len(snapshots) == 1
    row = snapshots[0]
    assert row["model_id"] == "antigravity_gemini_pro"
    assert row["quota_group"] == "antigravity_gemini"
    assert row["used_percent"] == 75.0
    assert row["resets_at"] == "2026-09-15T01:00:00+00:00"


def test_fresh_quota_pressure_is_projected_into_router_provider_state(monkeypatch):
    observed = datetime.now(timezone.utc)
    store = FakeStore([
        {
            "provider": "openai",
            "quota_key": "codex:primary",
            "model_id": None,
            "quota_group": "codex_chatgpt_plus",
            "used_percent": 82.0,
            "remaining_percent": 18.0,
            "available": True,
            "resets_at": None,
            "window_minutes": 300,
            "observed_at": observed,
            "source": "codex_app_server",
            "status": "fresh",
            "details": {},
        }
    ])
    telemetry = ProviderQuotaTelemetry(store)

    state = telemetry.apply_to_provider_state({})

    assert state["quota:codex_chatgpt_plus"]["quota_pressure"] == pytest.approx(0.82)
    assert state["quota:codex_chatgpt_plus"]["available"] is True


def test_fresh_capacity_can_reconcile_only_transient_quota_marker():
    observed = datetime.now(timezone.utc)
    store = FakeStore([
        {
            "provider": "google_antigravity",
            "quota_key": "gemini-weekly",
            "model_id": None,
            "quota_group": "antigravity_gemini",
            "used_percent": 5.0,
            "remaining_percent": 95.0,
            "available": True,
            "resets_at": None,
            "window_minutes": None,
            "observed_at": observed,
            "source": "antigravity_usage",
            "status": "fresh",
            "details": {},
        }
    ])
    telemetry = ProviderQuotaTelemetry(store)
    original = {
        "quota:antigravity_gemini": {
            "healthy": False,
            "available": False,
            "quota_pressure": 1.0,
            "error_rate": 1.0,
        },
        "provider:google_antigravity": {
            "healthy": False,
            "available": False,
        },
    }

    state = telemetry.apply_to_provider_state(original)

    assert state["quota:antigravity_gemini"]["available"] is True
    assert state["quota:antigravity_gemini"]["quota_pressure"] == pytest.approx(0.05)
    # Provider/auth/bridge health is a different authority boundary and quota
    # telemetry must never clear it.
    assert state["provider:google_antigravity"]["available"] is False


def test_stale_snapshot_does_not_change_provider_state():
    store = FakeStore([
        {
            "provider": "openai",
            "quota_key": "codex:primary",
            "model_id": None,
            "quota_group": "codex_chatgpt_plus",
            "used_percent": 100.0,
            "remaining_percent": 0.0,
            "available": False,
            "resets_at": None,
            "window_minutes": 300,
            "observed_at": datetime.now(timezone.utc) - timedelta(hours=1),
            "source": "codex_app_server",
            "status": "fresh",
            "details": {},
        }
    ])
    telemetry = ProviderQuotaTelemetry(store)
    telemetry.stale_seconds = 600

    assert telemetry.apply_to_provider_state({}) == {}
    assert telemetry.snapshots()[0]["status"] == "stale"


def test_codex_collector_uses_app_server_rate_limits_protocol(monkeypatch):
    writes = []

    class FakeStdin:
        closed = False

        def write(self, data):
            writes.append(data.decode("utf-8"))

        async def drain(self):
            return None

        def is_closing(self):
            return self.closed

        def close(self):
            self.closed = True

    class FakeStdout:
        def __init__(self):
            self.lines = [
                json.dumps({"id": 1, "result": {}}).encode() + b"\n",
                json.dumps({
                    "id": 2,
                    "result": {
                        "ordinaryUsageAllowed": True,
                        "rateLimits": {
                            "limitId": "codex",
                            "primary": {
                                "usedPercent": 44,
                                "windowDurationMins": 300,
                                "resetsAt": 1789430400,
                            },
                        },
                    },
                }).encode() + b"\n",
            ]

        async def readline(self):
            return self.lines.pop(0) if self.lines else b""

    class FakeProc:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = FakeStdout()
            self.stderr = FakeStdout()
            self.returncode = 0

        async def wait(self):
            return 0

        def terminate(self):
            self.returncode = 0

        def kill(self):
            self.returncode = 0

    async def fake_exec(*args, **kwargs):
        assert args[-1] == "app-server"
        return FakeProc()

    monkeypatch.setattr(quota_telemetry.shutil, "which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr(quota_telemetry.asyncio, "create_subprocess_exec", fake_exec)

    rows = asyncio.run(collect_codex_quota())

    messages = [json.loads(line) for line in writes]
    assert messages[0]["method"] == "initialize"
    assert messages[1]["method"] == "notifications/initialized"
    assert messages[2]["method"] == "account/rateLimits/read"
    assert messages[2]["params"]["excludeResetCreditDetails"] is True
    assert rows[0]["used_percent"] == 44.0
