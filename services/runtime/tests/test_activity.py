import json
from datetime import datetime, timezone

from app.activity import public_event, route_selected_event, status_transition_event


def test_status_events_are_semantic_and_not_duplicated():
    assert status_transition_event("executing", "executing") is None
    resumed = status_transition_event("blocked", "queued")
    assert resumed["event_type"] == "job_resumed"
    assert resumed["message"] == "Job resumed"
    verifying = status_transition_event("executing", "verifying")
    assert verifying["event_type"] == "verification_started"


def test_route_event_keeps_only_allow_listed_model_metadata():
    event = route_selected_event({
        "complexity_score": 99,
        "private_reason": "DO NOT LEAK",
        "strategy": {
            "profile": "complex",
            "analysis_depth": 2,
            "executor": {
                "id": "codex_terra",
                "provider": "openai",
                "adapter": "codex_cli",
                "model": "gpt-5.6-terra",
                "reasoning_effort": "medium",
                "reasons": ["PRIVATE ROUTING DETAIL"],
            },
            "budget": {"secret": "PRIVATE BUDGET DETAIL"},
        },
    })
    encoded = json.dumps(event)
    assert event["data"]["executor"] == {
        "id": "codex_terra",
        "provider": "openai",
        "model": "gpt-5.6-terra",
        "reasoning_effort": "medium",
    }
    assert "DO NOT LEAK" not in encoded
    assert "PRIVATE ROUTING DETAIL" not in encoded
    assert "PRIVATE BUDGET DETAIL" not in encoded


def test_public_event_rebuilds_fixed_message_phase_and_level():
    event = public_event({
        "id": 9,
        "job_id": "job-1",
        "event_type": "job_blocked",
        "phase": "PRIVATE PHASE",
        "level": "success",
        "message": "PRIVATE PROVIDER ERROR",
        "data": {
            "raw_error": "PRIVATE PROVIDER ERROR",
            "from_status": "PRIVATE STATUS",
            "to_status": "blocked",
        },
        "created_at": datetime(2026, 9, 13, tzinfo=timezone.utc),
    })
    assert event["phase"] == "blocked"
    assert event["level"] == "error"
    assert event["message"] == "Job blocked"
    assert event["data"] == {"to_status": "blocked"}
    assert "PRIVATE" not in json.dumps(event)


def test_unknown_event_types_are_not_exposed():
    assert public_event({"id": 1, "event_type": "raw_agent_output"}) is None
