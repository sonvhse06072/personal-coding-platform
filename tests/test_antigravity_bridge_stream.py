from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_BRIDGE = ROOT / "scripts" / "antigravity-bridge-live.py"


def load_live_bridge():
    spec = importlib.util.spec_from_file_location("antigravity_bridge_live", LIVE_BRIDGE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stream_filter_drops_prompt_and_unknown_events():
    module = load_live_bridge()
    assert module._safe_stream_event({
        "event": "step_update",
        "step_update": {"step_type": "user_input", "text_delta": "PRIVATE PROMPT"},
    }) is None
    assert module._safe_stream_event({"event": "reasoning", "text": "PRIVATE REASONING"}) is None
    assert module._safe_stream_event({"event": "unknown_future_shape", "data": "PRIVATE"}) is None


def test_stream_filter_allows_only_observable_non_prompt_activity():
    module = load_live_bridge()
    agent = {
        "event": "step_update",
        "step_update": {"step_type": "agent_response", "state": "ACTIVE", "text_delta": "Reviewing tests"},
    }
    tool = {
        "event": "step_update",
        "step_update": {"step_type": "tool", "state": "ACTIVE", "tool_name": "shell"},
    }
    assert module._safe_stream_event({"event": "init", "session_id": "bounded"}) is not None
    assert module._safe_stream_event(agent) == agent
    assert module._safe_stream_event(tool) == tool
    assert module._safe_stream_event({"event": "result", "result": {"status": "SUCCESS"}}) is not None
