import asyncio
from copy import deepcopy

from app.engine import RuntimeEngine


class FakeStorage:
    def __init__(self, row):
        self.rows = {row["id"]: deepcopy(row)}

    def get(self, job_id):
        value = self.rows.get(job_id)
        return deepcopy(value) if value else None

    def update(self, job_id, **fields):
        self.rows[job_id].update(deepcopy(fields))


class FakeDdev:
    def __init__(self):
        self.cancelled = []

    async def cancel(self, *, job_id):
        self.cancelled.append(job_id)
        return True


def base_row(status="blocked"):
    return {
        "id": "job12345",
        "project_id": "demo",
        "status": status,
        "repo_analysis": {"estimated_files": 2},
        "progress": {"model_calls": 5, "iteration": 3, "cost_usd": 0.25},
        "checkpoint": {
            "provider_state": {
                "provider:openai": {"available": False},
                "codex_plus": {"available": False},
            },
            "route_history": [],
            "approved_decisions": [],
        },
    }


def test_resume_preserves_budget_and_can_reset_only_provider_health():
    async def scenario():
        storage = FakeStorage(base_row())
        engine = RuntimeEngine(storage)
        queued = []

        async def enqueue(job_id):
            queued.append(job_id)

        engine.enqueue = enqueue
        row = await engine.resume("job12345", reset_transient_provider_failures=True)
        assert row["status"] == "queued"
        assert row["progress"] == {"model_calls": 5, "iteration": 3, "cost_usd": 0.25}
        assert "provider:openai" not in row["checkpoint"]["provider_state"]
        assert row["checkpoint"]["provider_state"]["codex_plus"]["available"] is False
        assert queued == ["job12345"]

    asyncio.run(scenario())


def test_approved_human_decision_resumes_same_job_without_resetting_progress():
    async def scenario():
        row = base_row("waiting_human")
        row["checkpoint"]["pending_decision"] = {
            "key": "architecture_choice",
            "decision": {
                "required": True,
                "triggers": ["architecture_choice"],
                "reason": "Choose architecture",
            },
            "source": "reassessment",
        }
        storage = FakeStorage(row)
        engine = RuntimeEngine(storage)
        queued = []

        async def enqueue(job_id):
            queued.append(job_id)

        engine.enqueue = enqueue
        result = await engine.resolve_human_decision(
            "job12345", action="approve", note="Use the existing pattern"
        )
        assert result["status"] == "queued"
        assert result["progress"]["model_calls"] == 5
        assert "architecture_choice" in result["checkpoint"]["approved_decisions"]
        assert result["checkpoint"]["decision_history"][-1]["note"] == "Use the existing pattern"
        assert queued == ["job12345"]

    asyncio.run(scenario())


def test_cancel_marks_job_and_cancels_active_runtime_task_and_ddev_process():
    async def scenario():
        storage = FakeStorage(base_row("executing"))
        engine = RuntimeEngine(storage)
        engine.ddev = FakeDdev()
        active = asyncio.create_task(asyncio.sleep(60))
        engine.active_jobs["job12345"] = active

        result = await engine.cancel("job12345")
        assert result["status"] == "cancelled"
        assert active.cancelled()
        assert engine.ddev.cancelled == ["job12345"]

    asyncio.run(scenario())


def test_human_pm_decision_returns_to_pm_without_authorizing_diff():
    async def scenario():
        row = base_row("waiting_human")
        row["checkpoint"]["pending_decision"] = {
            "key": "scope_change",
            "decision": {
                "required": True,
                "triggers": ["scope_change"],
                "reason": "PM cannot approve this scope boundary.",
            },
            "source": "pm_reassessment",
        }
        row["checkpoint"]["pending_pm_reassessment"] = {
            "signal": "changed_file_working_target_exceeded",
            "diff_hash": "diff-abc",
            "used": 11,
            "working_target": 8,
            "emergency_limit": 16,
            "pm_model_id": "pm-model",
            "summary": "Human-owned scope decision is required.",
        }
        storage = FakeStorage(row)
        engine = RuntimeEngine(storage)
        queued = []

        async def enqueue(job_id):
            queued.append(job_id)

        engine.enqueue = enqueue
        result = await engine.resolve_human_decision(
            "job12345",
            action="approve",
            note="Decision supplied; baseline remains authoritative.",
        )

        assert result["status"] == "queued"
        assert result["checkpoint"]["pending_pm_reassessment"]["diff_hash"] == "diff-abc"
        assert not result["checkpoint"].get("pm_reassessment_authorizations")
        assert "scope_change" in result["checkpoint"]["approved_decisions"]
        assert queued == ["job12345"]

    asyncio.run(scenario())


def test_rejected_pm_human_decision_queues_same_job_for_bounded_repair():
    async def scenario():
        row = base_row("waiting_human")
        original_progress = dict(row["progress"])
        row["checkpoint"]["pending_decision"] = {
            "key": "major_dependency_addition",
            "decision": {
                "required": True,
                "triggers": ["major_dependency_addition"],
                "reason": "PM requested approval for an out-of-scope test dependency.",
            },
            "source": "pm_reassessment",
        }
        row["checkpoint"]["pending_pm_reassessment"] = {
            "signal": "changed_file_working_target_exceeded",
            "diff_hash": "diff-test-deps",
            "used": 9,
            "working_target": 8,
            "emergency_limit": 16,
            "pm_model_id": "pm-model",
            "summary": "Third-party test dependency is outside the WorkOrder.",
        }
        storage = FakeStorage(row)
        engine = RuntimeEngine(storage)
        queued = []

        async def enqueue(job_id):
            queued.append(job_id)

        engine.enqueue = enqueue
        result = await engine.resolve_human_decision(
            "job12345",
            action="reject",
            note="Do not expand scope. Remove third-party frontend test libraries and use the existing test stack.",
        )

        assert result["status"] == "queued"
        assert result["progress"] == original_progress
        assert not result["checkpoint"].get("approved_decisions")
        assert result["checkpoint"]["pending_pm_reassessment"]["diff_hash"] == "diff-test-deps"
        assert "PCP_HUMAN_DECISION_REJECTED:" in result["checkpoint"]["last_failure"]
        assert "Remove third-party frontend test libraries" in result["checkpoint"]["last_failure"]
        assert result["checkpoint"]["failure_context"] == {
            "version": 1,
            "kind": "semantic_repair",
            "source": "human_rejection",
            "message": result["checkpoint"]["last_failure"],
            "diff_hash": "diff-test-deps",
            "decision_key": "major_dependency_addition",
        }
        assert result["checkpoint"]["decision_history"][-1]["action"] == "reject"
        assert result["result"]["reason"] == "human_decision_rejected_repair"
        assert queued == ["job12345"]

    asyncio.run(scenario())
