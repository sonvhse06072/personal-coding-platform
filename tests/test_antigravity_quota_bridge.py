from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUOTA_BRIDGE = ROOT / "scripts" / "antigravity-bridge-quota.py"
QUOTA_SINK = ROOT / "scripts" / "antigravity-quota-sink.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_status_sanitizer_exposes_quota_without_account_or_token_data():
    module = load(QUOTA_BRIDGE, "antigravity_bridge_quota")
    payload = {
        "userStatus": {
            "email": "private@example.com",
            "planStatus": {"planInfo": {"planName": "Pro"}},
            "cascadeModelConfigData": {
                "clientModelConfigs": [
                    {
                        "label": "Gemini 3.1 Pro (High)",
                        "modelOrAlias": {"model": "gemini-3.1-pro-high"},
                        "quotaInfo": {
                            "remainingFraction": 0.42,
                            "resetTime": "2026-09-20T01:02:03Z",
                            "secretFutureField": "do-not-copy",
                        },
                    }
                ]
            },
        },
        "csrf_token": "never-copy",
    }

    safe = module._sanitize_local_status(payload)

    assert safe is not None
    assert safe["plan_tier"] == "Pro"
    assert safe["quota"]["Gemini 3.1 Pro (High)"] == {
        "remaining_fraction": 0.42,
        "reset_time": "2026-09-20T01:02:03Z",
        "upstream_model": "gemini-3.1-pro-high",
    }
    text = repr(safe)
    assert "private@example.com" not in text
    assert "never-copy" not in text
    assert "secretFutureField" not in text


def test_statusline_sink_keeps_only_quota_model_plan_and_version():
    module = load(QUOTA_SINK, "antigravity_quota_sink")
    safe = module.sanitize(
        {
            "email": "private@example.com",
            "cwd": "/private/workspace",
            "conversation_id": "secret-conversation",
            "transcript_path": "/private/transcript.jsonl",
            "plan_tier": "Pro",
            "version": "1.2.3",
            "model": {"id": "model-id", "display_name": "Gemini 3.1 Pro"},
            "quota": {
                "gemini-weekly": {
                    "remaining_fraction": 0.8,
                    "reset_time": "2026-09-21T00:00:00Z",
                    "reset_in_seconds": 123,
                    "unknown": "drop-me",
                }
            },
        }
    )

    assert safe is not None
    assert safe["quota"]["gemini-weekly"] == {
        "remaining_fraction": 0.8,
        "reset_time": "2026-09-21T00:00:00Z",
        "reset_in_seconds": 123,
    }
    text = repr(safe)
    assert "private@example.com" not in text
    assert "/private/workspace" not in text
    assert "secret-conversation" not in text
    assert "/private/transcript.jsonl" not in text
    assert "drop-me" not in text
