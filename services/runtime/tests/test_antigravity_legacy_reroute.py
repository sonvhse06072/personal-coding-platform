from __future__ import annotations

import asyncio
from copy import deepcopy

from app.engine_antigravity import RuntimeEngine


class Storage:
    def __init__(self, row: dict) -> None:
        self.row = deepcopy(row)

    def get(self, job_id: str):
        if job_id != self.row["id"]:
            return None
        return deepcopy(self.row)

    def update(self, job_id: str, **fields) -> None:
        assert job_id == self.row["id"]
        self.row.update(deepcopy(fields))


class Router:
    def __init__(self) -> None:
        self.payloads = []

    async def route(self, payload: dict) -> dict:
        self.payloads.append(deepcopy(payload))
        return {
            "strategy": {
                "profile": "complex",
                "executor": {
                    "id": "codex_terra",
                    "provider": "openai",
                    "adapter": "codex_cli",
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "medium",
                },
                "evaluator": {
                    "id": "antigravity_claude_sonnet",
                    "provider": "google_antigravity",
                    "adapter": "antigravity_host",
                    "model": "claude-sonnet-4-6",
                    "quota_group": "antigravity_claude_gpt",
                    "reasoning_effort": "low",
                },
            }
        }


def legacy_row() -> dict:
    return {
        "id": "legacy-antigravity-job",
        "project_id": "demo",
        "status": "blocked",
        "source_commit": "a" * 40,
        "task": {"title": "bounded task"},
        "repo_analysis": {"estimated_files": 2},
        "route": {"strategy": {"profile": "complex"}},
        "progress": {
            "model_calls": 20,
            "elapsed_minutes": 90.047,
            "provider_failures": [
                {
                    "model": "antigravity_free",
                    "provider": "google_antigravity",
                    "kind": "quota_exhausted",
                }
            ],
        },
        "checkpoint": {
            "provider_state": {
                "provider:google_antigravity": {
                    "healthy": False,
                    "available": False,
                    "error_rate": 1.0,
                    "quota_pressure": 1.0,
                }
            },
            "route_history": [],
            "approved_decisions": [],
        },
        "error": None,
    }


def test_preserved_reroute_narrows_legacy_quota_marker_before_router_call():
    original = legacy_row()
    storage = Storage(original)
    engine = RuntimeEngine(storage)
    router = Router()
    engine.router = router

    updated = asyncio.run(
        engine.resume(
            original["id"],
            reset_transient_provider_failures=False,
            reroute=True,
        )
    )

    routed_state = router.payloads[0]["provider_state"]
    assert "provider:google_antigravity" not in routed_state
    assert routed_state["quota:model:antigravity_free"]["available"] is False
    assert updated["progress"] == original["progress"]
    assert updated["status"] == "queued"
    assert updated["route"]["strategy"]["evaluator"]["id"] == "antigravity_claude_sonnet"
    assert engine.queue.get_nowait() == original["id"]
