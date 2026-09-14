from __future__ import annotations

import asyncio

from app.control_actions_reroute import ControlActionService


class Harness(ControlActionService):
    def __init__(self):
        self.calls: list[dict] = []

    async def _resume(
        self,
        job_id: str,
        *,
        reset_transient_provider_failures: bool,
        reroute: bool,
    ) -> dict:
        self.calls.append(
            {
                "job_id": job_id,
                "reset_transient_provider_failures": reset_transient_provider_failures,
                "reroute": reroute,
            }
        )
        return {"id": job_id, "status": "queued"}


def action(action_type: str) -> dict:
    return {
        "action_id": f"action-{action_type}",
        "action_type": action_type,
        "job_id": "job-1",
        "payload": {},
    }


def test_reroute_provider_preserves_failed_provider_state():
    controls = Harness()

    result = asyncio.run(controls._dispatch(action("reroute_provider")))

    assert controls.calls == [
        {
            "job_id": "job-1",
            "reset_transient_provider_failures": False,
            "reroute": True,
        }
    ]
    assert result["job_id"] == "job-1"
    assert result["job_status"] == "queued"
    assert "preserving failed-provider state" in result["message"]


def test_explicit_quota_reset_still_clears_provider_state_before_fresh_route():
    controls = Harness()

    asyncio.run(controls._dispatch(action("provider_quota_reset")))

    assert controls.calls == [
        {
            "job_id": "job-1",
            "reset_transient_provider_failures": True,
            "reroute": True,
        }
    ]


def test_resume_reroute_and_no_effect_reroute_also_preserve_provider_state():
    for action_type in ("resume_reroute", "reroute_retry"):
        controls = Harness()
        asyncio.run(controls._dispatch(action(action_type)))
        assert controls.calls[0]["reset_transient_provider_failures"] is False
        assert controls.calls[0]["reroute"] is True
