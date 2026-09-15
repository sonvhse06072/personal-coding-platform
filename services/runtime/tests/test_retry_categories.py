import asyncio
import time
from copy import deepcopy

import app.engine_delivery as delivery_module
import app.engine_execution as execution_module
from app.engine_delivery import RuntimeEngine as DeliveryRuntimeEngine
from app.engine_verification import RuntimeEngine as VerificationRuntimeEngine


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
    def __init__(self):
        self.calls = []

    async def phase(self, *, job_id, project_id, workspace, phase, timeout_seconds):
        self.calls.append(phase)
        return {
            "phase": phase,
            "passed": True,
            "commands": [f"run-{phase}"],
        }


def _event_kinds(storage):
    return [event.get("data", {}).get("kind") for event in storage.events]


def _work_order():
    return {
        "id": "WO-148-retry",
        "parent_ticket": "GH-148",
        "objective": "Verify retry attribution",
        "baseline_revision": "mvp-v1",
        "source_references": [{"path": "docs/project/constitution.md"}],
        "in_scope": ["runtime retry accounting"],
        "out_of_scope": ["production deployment"],
        "acceptance_criteria": [{"id": "AC-1", "description": "Retries are attributed separately"}],
        "requested_role": "developer",
        "verification": {
            "intermediate_phases": ["targeted_tests"],
            "required_phases": ["static_analysis", "full_tests"],
        },
        "risk": {"level": "standard", "flags": []},
        "budget": {"mode": "adaptive", "max_profile": "standard"},
        "dependencies": [],
    }


def _strategy():
    return {
        "profile": "standard",
        "budget": {
            "max_tool_calls": 100,
            "max_test_runs": 100,
            "max_wall_time_minutes": 60,
        },
    }


def _project():
    return {
        "ddev": {
            "enabled": True,
            "targeted_tests": ["targeted"],
            "static_analysis": ["static"],
            "full_tests": ["full"],
        }
    }


def test_verification_retry_has_distinct_activity_without_repair_charge():
    async def scenario():
        storage = FakeStorage(
            {
                "id": "job148",
                "status": "verifying",
                "workspace": "/workspaces/job148",
                "checkpoint": {"work_order": _work_order()},
                "progress": {},
            }
        )
        engine = object.__new__(VerificationRuntimeEngine)
        engine.storage = storage
        engine.ddev = FakeDdev()
        progress = {
            "tool_calls": 0,
            "test_runs": 0,
            "repair_iterations": 0,
        }

        for _ in range(2):
            result = await engine._verify(
                "job148",
                "demo",
                "/workspaces/job148",
                _project(),
                _strategy(),
                time.monotonic(),
                progress,
            )
            assert result["passed"] is True

        assert progress["verification_attempts"] == 2
        assert progress["verification_retry_attempts"] == 1
        assert progress["repair_iterations"] == 0
        assert "verification_retry" in _event_kinds(storage)
        assert any(
            event.get("data", {}).get("status") == "pending:final:full_tests"
            for event in storage.events
        )

    asyncio.run(scenario())


def test_preflight_resume_is_infrastructure_retry_not_engineering_repair():
    async def scenario():
        storage = FakeStorage(
            {
                "id": "job148",
                "status": "queued",
                "workspace": "/workspaces/job148",
                "result": {"reason": "preflight_failed"},
                "progress": {"repair_iterations": 0},
            }
        )
        engine = object.__new__(VerificationRuntimeEngine)
        engine.storage = storage

        original = execution_module.RuntimeEngine.run_job

        async def no_op_parent_run(self, job_id):
            return None

        execution_module.RuntimeEngine.run_job = no_op_parent_run
        try:
            await engine.run_job("job148")
        finally:
            execution_module.RuntimeEngine.run_job = original

        assert storage.row["progress"]["infrastructure_retry_attempts"] == 1
        assert storage.row["progress"]["repair_iterations"] == 0
        assert "infrastructure_retry" in _event_kinds(storage)

    asyncio.run(scenario())


def test_delivery_resume_is_delivery_retry_not_engineering_repair():
    async def scenario():
        storage = FakeStorage(
            {
                "id": "job148",
                "project_id": "demo",
                "status": "queued",
                "workspace": "/workspaces/job148",
                "branch": "ai/job148",
                "source_commit": "a" * 40,
                "task": {"title": "Retry delivery"},
                "checkpoint": {},
                "progress": {
                    "elapsed_minutes": 0.0,
                    "delivery_attempts": 1,
                    "repair_iterations": 0,
                },
                "result": {
                    "status": "accepted",
                    "commit": "b" * 40,
                    "verification": {"passed": True, "phases": []},
                    "route": {
                        "strategy": {
                            "budget": {"max_wall_time_minutes": 60},
                            "permissions": {
                                "push_ai_branch": True,
                                "create_pr": True,
                            },
                        }
                    },
                },
            }
        )
        engine = object.__new__(DeliveryRuntimeEngine)
        engine.storage = storage
        engine.ddev = object()

        original = delivery_module.deliver_verified_work

        async def successful_delivery(**kwargs):
            return {
                "enabled": True,
                "state": "ci_success",
                "branch": kwargs["branch"],
                "commit": kwargs["commit"],
            }

        delivery_module.deliver_verified_work = successful_delivery
        try:
            await engine.run_job("job148")
        finally:
            delivery_module.deliver_verified_work = original

        assert storage.row["status"] == "completed"
        assert storage.row["progress"]["delivery_retry_attempts"] == 1
        assert storage.row["progress"]["repair_iterations"] == 0
        assert "delivery_retry" in _event_kinds(storage)

    asyncio.run(scenario())
