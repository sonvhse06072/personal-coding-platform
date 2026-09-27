from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app.engine import RuntimeEngine


class Storage:
    def __init__(self, row: dict) -> None:
        self.rows = {row["id"]: deepcopy(row)}

    def get(self, job_id: str):
        row = self.rows.get(job_id)
        return deepcopy(row) if row else None

    def update(self, job_id: str, **fields) -> None:
        self.rows[job_id].update(deepcopy(fields))


class Router:
    def __init__(self, route: dict | None = None, error: Exception | None = None) -> None:
        self.route_value = route
        self.error = error
        self.payloads: list[dict] = []

    async def route(self, payload: dict) -> dict:
        self.payloads.append(deepcopy(payload))
        if self.error is not None:
            raise self.error
        assert self.route_value is not None
        return deepcopy(self.route_value)


WORK_ORDER = {
    "id": "WO-RESUME-1",
    "objective": "Resume bounded recovery tooling",
    "baseline_revision": "v1",
    "source_references": [{"path": "docs/recovery.md"}],
    "in_scope": ["bounded recovery tooling"],
    "out_of_scope": ["unrelated work"],
    "acceptance_criteria": [{"id": "AC-1", "description": "resume safely"}],
    "constraints": ["no scope expansion"],
    "requested_role": "developer",
    "verification": {"required_phases": ["targeted_tests"]},
    "risk": {"level": "high", "flags": ["security_sensitive"]},
    "budget": {
        "max_profile": "complex",
        "max_model_calls": 10,
        "max_repair_iterations": 2,
        "max_wall_time_minutes": 50,
        "max_changed_files": 14,
    },
    "dependencies": [],
}


def blocked_row() -> dict:
    return {
        "id": "job-resume",
        "project_id": "demo",
        "status": "blocked",
        "source_commit": "a" * 40,
        "branch": "coding/job-resume",
        "workspace": "/workspaces/job-resume",
        "task": {
            "title": "Resume bounded recovery tooling",
            "description": "old enriched task",
            "task_type": "developer",
            "flags": [],
            "semantic": {"risk": 50},
        },
        "repo_analysis": {
            "estimated_files": 4,
            "affected_components": 2,
            "dependency_depth": 1,
            "tests_available": True,
            "existing_pattern": True,
        },
        "route": {"strategy": {"profile": "complex", "executor": {"id": "old-model"}}},
        "progress": {
            "model_calls": 4,
            "input_tokens": 1234,
            "output_tokens": 432,
            "elapsed_minutes": 17.5,
            "repair_iterations": 0,
        },
        "checkpoint": {
            "work_order": deepcopy(WORK_ORDER),
            "project_baseline": {"revision": "v1"},
            "plan": "preserve this plan",
            "planner_choice": {"id": "old-planner"},
            "executor_choice": {"id": "old-executor"},
            "evaluator_choice": {"id": "old-evaluator"},
            "last_failure": "old provider failure",
            "provider_state": {
                "provider:openai": {"available": False, "healthy": False},
                "codex_terra": {"available": False, "healthy": False},
            },
            "route_history": [{"reason": "initial", "route": {"old": True}}],
            "approved_decisions": [],
        },
        "result": {"reason": "evaluator_provider_failure_without_fallback"},
        "error": None,
        "dry_run": False,
    }


def fresh_route() -> dict:
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
                "id": "antigravity_free",
                "provider": "google_antigravity",
                "adapter": "antigravity_host",
                "model": "auto",
            },
        }
    }


def test_orchestrated_failed_reroute_preserves_job_state_but_replaces_route_choices() -> None:
    original = blocked_row()
    original["status"] = "failed"
    storage = Storage(original)
    engine = RuntimeEngine(storage)
    router = Router(fresh_route())
    engine.router = router

    updated = asyncio.run(
        engine.resume(
            "job-resume",
            reset_transient_provider_failures=True,
            reroute=True,
            _allow_failed_orchestrated_resume=True,
        )
    )

    assert updated["status"] == "queued"
    assert updated["route"] == fresh_route()
    assert updated["workspace"] == original["workspace"]
    assert updated["source_commit"] == original["source_commit"]
    assert updated["progress"] == original["progress"]

    checkpoint = updated["checkpoint"]
    assert checkpoint["plan"] == "preserve this plan"
    assert checkpoint["work_order"]["id"] == "WO-RESUME-1"
    assert checkpoint["project_baseline"] == {"revision": "v1"}
    assert "planner_choice" not in checkpoint
    assert "executor_choice" not in checkpoint
    assert "evaluator_choice" not in checkpoint
    assert "last_failure" not in checkpoint
    assert "provider:openai" not in checkpoint["provider_state"]
    assert checkpoint["provider_state"]["codex_terra"]["available"] is False
    assert checkpoint["route_history"][0]["reason"] == "initial"
    assert checkpoint["route_history"][-1] == {
        "reason": "explicit_resume_reroute",
        "route": fresh_route(),
    }

    assert router.payloads[0]["provider_state"] == {
        "codex_terra": {"available": False, "healthy": False}
    }
    assert engine.queue.get_nowait() == "job-resume"


def test_failed_non_orchestrated_job_is_rejected_without_internal_authorization() -> None:
    original = blocked_row()
    original["status"] = "failed"
    storage = Storage(original)
    engine = RuntimeEngine(storage)

    with pytest.raises(RuntimeError, match="status=failed"):
        asyncio.run(engine.resume("job-resume"))

    current = storage.get("job-resume")
    assert current["status"] == "failed"
    assert current["workspace"] == original["workspace"]
    assert current["source_commit"] == original["source_commit"]
    assert current["progress"] == original["progress"]
    assert engine.queue.empty()


def test_reroute_failure_leaves_blocked_route_and_progress_unchanged() -> None:
    original = blocked_row()
    storage = Storage(original)
    engine = RuntimeEngine(storage)
    engine.router = Router(error=RuntimeError("router unavailable"))

    with pytest.raises(RuntimeError, match="router unavailable"):
        asyncio.run(
            engine.resume(
                "job-resume",
                reset_transient_provider_failures=True,
                reroute=True,
            )
        )

    current = storage.get("job-resume")
    assert current["status"] == "blocked"
    assert current["route"] == original["route"]
    assert current["progress"] == original["progress"]
    assert engine.queue.empty()


def changed_file_recovery_route(*, working: int = 8, emergency: int = 16) -> dict:
    route = fresh_route()
    route["strategy"].update({
        "budget_mode": "adaptive",
        "budget": {"max_changed_files": emergency},
        "adaptive_budget": {
            "enabled": True,
            "effort_pressure": 0.5,
            "dimensions": {
                "max_changed_files": {
                    "estimate": 6,
                    "working_target": working,
                    "emergency_limit": emergency,
                }
            },
        },
    })
    return route


def test_changed_file_scope_recovery_refreshes_route_and_preserves_same_job():
    original = blocked_row()
    original["progress"].update({
        "changed_files": 10,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    original["result"] = {
        "reason": "reassessment_stopped",
        "diff": {
            "changed_file_count": 10,
            "changed_files": [f"frontend/file-{i}.tsx" for i in range(10)],
        },
        "reassess": {
            "action": "stop",
            "reason": "Circuit breaker: abnormal execution signal without a valid escalation path",
            "signals": ["scope_expansion"],
        },
    }
    storage = Storage(original)
    engine = RuntimeEngine(storage)
    engine.router = Router(changed_file_recovery_route())

    updated = asyncio.run(
        engine.resume(
            "job-resume",
            reroute=True,
            _require_changed_file_headroom=True,
        )
    )

    assert updated["status"] == "queued"
    assert updated["progress"] == original["progress"]
    assert updated["workspace"] == original["workspace"]
    assert updated["checkpoint"]["work_order"] == original["checkpoint"]["work_order"]
    assert updated["route"]["strategy"]["budget"]["max_changed_files"] == 16
    assert updated["checkpoint"]["route_history"][-1]["reason"] == (
        "changed_file_scope_policy_refresh"
    )
    assert engine.queue.get_nowait() == "job-resume"


def test_changed_file_scope_recovery_fails_closed_above_fresh_emergency_limit():
    original = blocked_row()
    original["progress"].update({
        "changed_files": 17,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    original["result"] = {
        "reason": "reassessment_stopped",
        "diff": {
            "changed_file_count": 17,
            "changed_files": [f"frontend/file-{i}.tsx" for i in range(17)],
        },
        "reassess": {"action": "stop", "signals": ["scope_expansion"]},
    }
    storage = Storage(original)
    engine = RuntimeEngine(storage)
    engine.router = Router(changed_file_recovery_route())

    with pytest.raises(RuntimeError, match="fresh emergency ceiling"):
        asyncio.run(
            engine.resume(
                "job-resume",
                reroute=True,
                _require_changed_file_headroom=True,
            )
        )

    current = storage.get("job-resume")
    assert current["status"] == "blocked"
    assert current["route"] == original["route"]
    assert current["progress"] == original["progress"]
    assert engine.queue.empty()


def test_changed_file_scope_recovery_fails_closed_on_sensitive_changed_path():
    original = blocked_row()
    original["progress"].update({
        "changed_files": 9,
        "unexpected_scope": True,
        "important_decision_flags": [],
    })
    original["result"] = {
        "reason": "reassessment_stopped",
        "diff": {
            "changed_file_count": 9,
            "changed_files": [
                "frontend/component.tsx",
                "config/routing-policy.yml",
            ],
        },
        "reassess": {"action": "stop", "signals": ["scope_expansion"]},
    }
    storage = Storage(original)
    engine = RuntimeEngine(storage)
    engine.router = Router(changed_file_recovery_route())

    with pytest.raises(RuntimeError, match="protected changed-path boundary"):
        asyncio.run(
            engine.resume(
                "job-resume",
                reroute=True,
                _require_changed_file_headroom=True,
            )
        )

    assert storage.get("job-resume")["status"] == "blocked"
    assert engine.queue.empty()
