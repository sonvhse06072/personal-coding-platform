from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.quota_telemetry import merge_provider_state
from app.quota_telemetry_policy import (
    PolicyAntigravityQuotaCollector,
    PolicyCodexQuotaCollector,
    _expires_at,
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
    assert by_window["primary"]["state_key"] == "quota:codex_chatgpt_plus"
    assert by_window["primary"]["remaining_percent"] == 8.0
    assert by_window["primary"]["available"] is True
    assert by_window["secondary"]["remaining_percent"] == 0.0
    assert by_window["secondary"]["available"] is False
    assert by_window["secondary"]["metadata"]["window_duration_mins"] == 10080




def test_current_codex_generation_slugs_keep_shared_subscription_quota_group():
    collector = PolicyCodexQuotaCollector(ttl_seconds=600)

    for slug in ("gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol"):
        snapshots = collector.normalize(
            {
                "ordinaryUsageAllowed": True,
                "rateLimitsByLimitId": {
                    slug: {
                        "normalModelSlug": slug,
                        "primary": {
                            "usedPercent": 25,
                            "resetsAt": 1789428000,
                        },
                        "secondary": None,
                    }
                },
            }
        )

        assert len(snapshots) == 1
        assert snapshots[0]["state_key"] == "quota:codex_chatgpt_plus"
        assert snapshots[0]["metadata"]["normal_model_slug"] == slug
        assert snapshots[0]["remaining_percent"] == 75.0


def test_codex_account_bucket_is_codex_quota_not_generic_openai_health():
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
    assert snapshots[0]["state_key"] == "quota:codex_chatgpt_plus"
    assert snapshots[0]["available"] is False
    assert snapshots[0]["used_percent"] == 5.0


def test_snapshot_stops_influencing_router_at_provider_reset_boundary():
    observed = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    reset = observed + timedelta(seconds=90)

    assert _expires_at(observed, 600, reset) == reset
    assert _expires_at(observed, 60, reset) == observed + timedelta(seconds=60)


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


def test_newer_authoritative_quota_snapshot_rehabilitates_only_quota_failure():
    durable = {
        "quota:codex_chatgpt_plus": {
            "healthy": False,
            "available": False,
            "quota_pressure": 1.0,
            "error_rate": 1.0,
            "failure_kind": "quota_exhausted",
            "failed_at": "2026-09-20T01:00:00+00:00",
        }
    }
    telemetry = {
        "quota:codex_chatgpt_plus": {
            "healthy": True,
            "available": True,
            "quota_pressure": 0.15,
            "error_rate": 0.0,
            "latency_ms": 0,
            "predicted_success": 0.9,
            "authoritative": True,
            "observed_at": "2026-09-20T01:05:00+00:00",
        }
    }

    merged = merge_provider_state(durable, telemetry)

    assert merged["quota:codex_chatgpt_plus"]["available"] is True
    assert merged["quota:codex_chatgpt_plus"]["healthy"] is True
    assert merged["quota:codex_chatgpt_plus"]["rehabilitated_from"] == "2026-09-20T01:00:00+00:00"


def test_stale_authoritative_snapshot_cannot_rehabilitate_newer_quota_failure():
    durable = {
        "quota:codex_chatgpt_plus": {
            "healthy": False,
            "available": False,
            "quota_pressure": 1.0,
            "error_rate": 1.0,
            "failure_kind": "quota_exhausted",
            "failed_at": "2026-09-20T01:05:00+00:00",
        }
    }
    telemetry = {
        "quota:codex_chatgpt_plus": {
            "healthy": True,
            "available": True,
            "quota_pressure": 0.1,
            "error_rate": 0.0,
            "authoritative": True,
            "observed_at": "2026-09-20T01:00:00+00:00",
        }
    }

    merged = merge_provider_state(durable, telemetry)

    assert merged["quota:codex_chatgpt_plus"]["available"] is False
    assert merged["quota:codex_chatgpt_plus"]["healthy"] is False


def test_telemetry_cannot_clear_durable_provider_auth_failure():
    durable = {
        "provider:openai": {
            "healthy": False,
            "available": False,
            "quota_pressure": 0.0,
            "error_rate": 1.0,
            "failure_kind": "authentication",
            "failed_at": "2026-09-20T01:00:00+00:00",
        }
    }
    telemetry = {
        "provider:openai": {
            "healthy": True,
            "available": True,
            "quota_pressure": 0.0,
            "error_rate": 0.0,
            "authoritative": True,
            "observed_at": "2026-09-20T02:00:00+00:00",
        }
    }

    merged = merge_provider_state(durable, telemetry)

    assert merged["provider:openai"]["available"] is False
    assert merged["provider:openai"]["healthy"] is False
