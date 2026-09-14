from __future__ import annotations

from app.quota_telemetry import merge_provider_state
from app.quota_telemetry_policy import (
    PolicyAntigravityQuotaCollector,
    PolicyCodexQuotaCollector,
)


def test_codex_multi_bucket_maps_model_and_windows():
    collector = PolicyCodexQuotaCollector(ttl_seconds=600)
    snapshots = collector.normalize(
        {
            "ordinaryUsageAllowed": True,
            "rateLimitsByLimitId": {
                "terra": {
                    "normalModelSlug": "gpt-5.6-terra",
                    "limitName": "Terra quota",
                    "planType": "plus",
                    "primary": {
                        "usedPercent": 92,
                        "windowDurationMins": 300,
                        "resetsAt": 1789428000,
                    },
                    "secondary": {
                        "usedPercent": 100,
                        "windowDurationMins": 10080,
                        "resetsAt": 1789900000,
                    },
                }
            },
        }
    )

    assert len(snapshots) == 2
    by_window = {item["window_name"]: item for item in snapshots}
    assert by_window["primary"]["state_key"] == "quota:model:codex_terra"
    assert by_window["primary"]["remaining_percent"] == 8.0
    assert by_window["primary"]["available"] is True
    assert by_window["secondary"]["remaining_percent"] == 0.0
    assert by_window["secondary"]["available"] is False
    assert by_window["secondary"]["metadata"]["window_duration_mins"] == 10080


def test_codex_backend_denial_wins_even_when_percent_is_low():
    collector = PolicyCodexQuotaCollector()
    snapshots = collector.normalize(
        {
            "ordinaryUsageAllowed": False,
            "rateLimits": {
                "primary": {"usedPercent": 5, "resetsAt": 1789428000},
                "secondary": None,
            },
        }
    )

    assert len(snapshots) == 1
    assert snapshots[0]["state_key"] == "provider:openai"
    assert snapshots[0]["available"] is False
    assert snapshots[0]["used_percent"] == 5.0


def test_antigravity_live_status_maps_human_label_to_logical_model():
    collector = PolicyAntigravityQuotaCollector()
    snapshots = collector.normalize(
        {
            "source": "antigravity_local_status",
            "source_supported": False,
            "snapshot": {
                "captured_at": "2026-09-15T00:00:00Z",
                "plan_tier": "Pro",
                "source_contract": "local_language_server_get_user_status",
                "quota": {
                    "Gemini 3.1 Pro (High)": {
                        "remaining_fraction": 0.25,
                        "reset_time": "2026-09-20T01:02:03Z",
                    }
                },
            },
        }
    )

    assert len(snapshots) == 1
    item = snapshots[0]
    assert item["source"] == "antigravity_local_status"
    assert item["state_key"] == "quota:model:antigravity_gemini_pro"
    assert item["used_percent"] == 75.0
    assert item["remaining_percent"] == 25.0
    assert item["metadata"]["plan_tier"] == "Pro"
    assert item["metadata"]["source_supported"] is False


def test_antigravity_statusline_group_fallback_is_preserved():
    collector = PolicyAntigravityQuotaCollector()
    snapshots = collector.normalize(
        {
            "source": "antigravity_statusline",
            "source_supported": True,
            "snapshot": {
                "captured_at": "2026-09-15T00:00:00Z",
                "quota": {
                    "gemini-weekly": {
                        "remaining_fraction": 0.60,
                        "reset_time": "2026-09-21T00:00:00Z",
                        "reset_in_seconds": 518400,
                    }
                },
            },
        }
    )

    assert len(snapshots) == 1
    assert snapshots[0]["state_key"] == "quota:antigravity_gemini"
    assert snapshots[0]["metadata"]["source_supported"] is True


def test_telemetry_merge_cannot_clear_durable_provider_failure():
    durable = {
        "provider:openai": {
            "healthy": False,
            "available": False,
            "quota_pressure": 1.0,
            "error_rate": 1.0,
            "latency_ms": 0,
            "predicted_success": None,
        }
    }
    telemetry = {
        "provider:openai": {
            "healthy": True,
            "available": True,
            "quota_pressure": 0.15,
            "error_rate": 0.0,
            "latency_ms": 0,
            "predicted_success": 0.9,
        }
    }

    merged = merge_provider_state(durable, telemetry)

    assert merged["provider:openai"]["available"] is False
    assert merged["provider:openai"]["healthy"] is False
    assert merged["provider:openai"]["quota_pressure"] == 1.0
    assert merged["provider:openai"]["error_rate"] == 1.0
