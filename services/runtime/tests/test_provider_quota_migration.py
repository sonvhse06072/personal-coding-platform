from __future__ import annotations

from datetime import datetime, timezone

from app.state import migrate_legacy_provider_quota_failure


def test_legacy_codex_provider_quota_failure_narrows_to_registered_quota_group():
    checkpoint = {
        "provider_state": {
            "provider:openai": {
                "healthy": False,
                "available": False,
                "quota_pressure": 1.0,
                "error_rate": 1.0,
            }
        }
    }
    progress = {
        "provider_failures": [
            {
                "model": "codex_terra",
                "provider": "openai",
                "kind": "quota_exhausted",
            }
        ]
    }

    migrated = migrate_legacy_provider_quota_failure(
        checkpoint,
        progress,
        failed_at=datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc),
    )

    state = migrated["provider_state"]
    assert "provider:openai" not in state
    assert state["quota:codex_chatgpt_plus"]["available"] is False
    assert state["quota:codex_chatgpt_plus"]["failure_kind"] == "quota_exhausted"
    assert state["quota:codex_chatgpt_plus"]["failed_at"] == "2026-09-20T01:00:00+00:00"


def test_later_non_quota_failure_prevents_legacy_provider_marker_migration():
    checkpoint = {
        "provider_state": {
            "provider:openai": {
                "healthy": False,
                "available": False,
                "error_rate": 1.0,
            }
        }
    }
    progress = {
        "provider_failures": [
            {
                "model": "codex_terra",
                "provider": "openai",
                "kind": "quota_exhausted",
            },
            {
                "model": "codex_terra",
                "provider": "openai",
                "kind": "authentication",
            },
        ]
    }

    migrated = migrate_legacy_provider_quota_failure(
        checkpoint,
        progress,
        failed_at="2026-09-20T01:00:00+00:00",
    )

    assert migrated == checkpoint
