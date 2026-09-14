from datetime import datetime, timezone

from app.dashboard import _public_job_events, create_dashboard_router


NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


class _Storage:
    def events_after(self, job_id, after_id=0, limit=100):
        assert job_id == "job-1"
        assert after_id == 7
        assert limit == 50
        return [
            {
                "id": 8,
                "job_id": "job-1",
                "event_type": "developer_message",
                "phase": "PRIVATE",
                "level": "PRIVATE",
                "message": "PRIVATE",
                "data": {"text": "Inspecting runner.py", "raw_prompt": "DO NOT LEAK"},
                "created_at": NOW,
            },
            {
                "id": 9,
                "job_id": "job-1",
                "event_type": "raw_agent_output",
                "phase": "execution",
                "level": "info",
                "message": "secret",
                "data": {},
                "created_at": NOW,
            },
        ]


class _Store:
    pass


def test_replay_feed_rebuilds_public_contract_and_drops_unknown_events():
    events = _public_job_events(_Storage(), "job-1", after=7, limit=50)
    assert len(events) == 1
    assert events[0]["seq"] == 8
    assert events[0]["message"] == "Inspecting runner.py"
    assert events[0]["data"] == {"text": "Inspecting runner.py"}


def test_dashboard_router_exposes_read_only_replay_and_sse_routes():
    router = create_dashboard_router(_Storage(), _Store())
    paths = {route.path for route in router.routes}
    assert "/v1/dashboard/jobs/{job_id}/events" in paths
    assert "/v1/dashboard/jobs/{job_id}/stream" in paths
    methods = {
        route.path: route.methods
        for route in router.routes
        if route.path in {
            "/v1/dashboard/jobs/{job_id}/events",
            "/v1/dashboard/jobs/{job_id}/stream",
        }
    }
    assert methods["/v1/dashboard/jobs/{job_id}/events"] == {"GET"}
    assert methods["/v1/dashboard/jobs/{job_id}/stream"] == {"GET"}
