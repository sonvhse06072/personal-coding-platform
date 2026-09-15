import asyncio
import time
from copy import deepcopy

from app.engine import RuntimeEngine


class FakeStorage:
    def __init__(self, row):
        self.row = deepcopy(row)
        self.events = []

    def get(self, job_id):
        if job_id != self.row["id"]:
            return None
        return deepcopy(self.row)

    def update(self, job_id, **fields):
        assert job_id == self.row["id"]
        self.row.update(deepcopy(fields))

    def append_event(self, job_id, event):
        assert job_id == self.row["id"]
        self.events.append(deepcopy(event))


class FakeDdev:
    def __init__(self, outcomes=None):
        self.outcomes = dict(outcomes or {})
        self.calls = []

    async def phase(self, *, job_id, project_id, workspace, phase, timeout_seconds):
        self.calls.append(phase)
        passed = self.outcomes.get(phase, True)
        return {
            "phase": phase,
            "passed": passed,
            "commands": [f"run-{phase}"],
        }


class FakeRouter:
    async def route(self, payload):
        return {
            "strategy": {
                "executor": {
                    "id": "fallback",
                    "provider": "openai",
                    "adapter": "codex_cli",
                    "model": "gpt-fallback",
                }
            }
        }


def work_order(*, layered=True):
    verification = {
        "required_phases": ["static_analysis", "full_tests"],
    }
    if layered:
        verification["intermediate_phases"] = ["targeted_tests"]
    return {
        "id": "WO-148",
        "parent_ticket": "GH-148",
        "objective": "Implement layered verification",
        "baseline_revision": "mvp-v1",
        "source_references": [{"path": "docs/project/constitution.md"}],
        "in_scope": ["runtime verification"],
        "out_of_scope": ["production deployment"],
        "acceptance_criteria": [{"id": "AC-1", "description": "Verification is layered"}],
        "requested_role": "developer",
        "verification": verification,
        "risk": {"level": "standard", "flags": []},
        "budget": {"mode": "adaptive", "max_profile": "standard"},
        "dependencies": [],
    }


def row(*, layered=True):
    return {
        "id": "job148",
        "project_id": "demo",
        "status": "verifying",
        "workspace": "/workspaces/job148",
        "checkpoint": {"work_order": work_order(layered=layered)},
        "progress": {},
    }


def strategy():
    return {
        "profile": "standard",
        "budget": {
            "max_tool_calls": 100,
            "max_test_runs": 100,
            "max_wall_time_minutes": 60,
            "max_provider_failovers": 2,
        },
    }


def project():
    return {
        "ddev": {
            "enabled": True,
            "targeted_tests": ["targeted"],
            "static_analysis": ["static"],
            "full_tests": ["full"],
        }
    }


def progress():
    return {
        "tool_calls": 0,
        "test_runs": 0,
        "repair_iterations": 0,
        "provider_failovers": 0,
    }


def test_failed_intermediate_phase_skips_expensive_final_checks():
    async def scenario():
        storage = FakeStorage(row())
        engine = RuntimeEngine(storage)
        ddev = FakeDdev({"targeted_tests": False})
        engine.ddev = ddev
        state = progress()

        result = await engine._verify(
            "job148",
            "demo",
            "/workspaces/job148",
            project(),
            strategy(),
            time.monotonic(),
            state,
        )

        assert result["passed"] is False
        assert result["verification_mode"] == "layered"
        assert ddev.calls == ["targeted_tests"]
        assert state["verification_attempts"] == 1
        assert state.get("verification_retry_attempts", 0) == 0
        assert state["repair_iterations"] == 0
        assert any(
            event.get("data", {}).get("kind") == "verification_layer"
            for event in storage.events
        )

    asyncio.run(scenario())


def test_layered_candidate_must_pass_all_required_final_phases():
    async def scenario():
        storage = FakeStorage(row())
        engine = RuntimeEngine(storage)
        ddev = FakeDdev()
        engine.ddev = ddev
        state = progress()

        result = await engine._verify(
            "job148",
            "demo",
            "/workspaces/job148",
            project(),
            strategy(),
            time.monotonic(),
            state,
        )

        assert result["passed"] is True
        assert ddev.calls == ["targeted_tests", "static_analysis", "full_tests"]
        assert result["phases"][0]["verification_layer"] == "intermediate"
        assert result["phases"][1]["verification_layer"] == "final"
        assert result["phases"][-1]["phase"] == "full_tests"
        assert state["repair_iterations"] == 0

    asyncio.run(scenario())


def test_second_verification_cycle_counts_retry_without_engineering_repair():
    async def scenario():
        storage = FakeStorage(row())
        engine = RuntimeEngine(storage)
        engine.ddev = FakeDdev()
        state = progress()

        for _ in range(2):
            result = await engine._verify(
                "job148",
                "demo",
                "/workspaces/job148",
                project(),
                strategy(),
                time.monotonic(),
                state,
            )
            assert result["passed"] is True

        assert state["verification_attempts"] == 2
        assert state["verification_retry_attempts"] == 1
        assert state["repair_iterations"] == 0

    asyncio.run(scenario())


def test_legacy_work_order_keeps_historical_verification_path():
    async def scenario():
        storage = FakeStorage(row(layered=False))
        engine = RuntimeEngine(storage)
        engine.ddev = FakeDdev()
        state = progress()

        result = await engine._verify(
            "job148",
            "demo",
            "/workspaces/job148",
            project(),
            strategy(),
            time.monotonic(),
            state,
        )

        assert result["passed"] is True
        assert result["verification_mode"] == "legacy"
        # Historical standard behavior runs targeted + static; the governance
        # facade then appends WorkOrder-required full_tests.
        assert engine.ddev.calls == ["targeted_tests", "static_analysis", "full_tests"]

    asyncio.run(scenario())


def test_provider_recovery_has_its_own_counter_and_does_not_spend_repair_budget():
    async def scenario():
        storage = FakeStorage(row())
        engine = RuntimeEngine(storage)
        engine.router = FakeRouter()
        state = progress()
        provider_state = {}

        next_choice, _ = await engine._provider_failover(
            route_payload={"job_id": "job148"},
            provider_state=provider_state,
            current_choice={
                "id": "broken",
                "provider": "openrouter",
                "adapter": "opencode",
                "model": "broken-model",
            },
            failure_kind="quota_exhausted",
            progress=state,
            strategy=strategy(),
        )

        assert next_choice is not None
        assert next_choice["id"] == "fallback"
        assert state["provider_recovery_attempts"] == 1
        assert state["provider_failovers"] == 1
        assert state["repair_iterations"] == 0
        assert any(
            event.get("data", {}).get("kind") == "provider_recovery"
            for event in storage.events
        )

    asyncio.run(scenario())
