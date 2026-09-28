import asyncio
from copy import deepcopy

import pytest

import app.engine_delivery as engine_delivery_module
from app.engine import RuntimeEngine as GovernedRuntimeEngine
from app.engine_delivery import RuntimeEngine


OLD_COMMIT = "b" * 40
NEW_COMMIT = "c" * 40
SOURCE_COMMIT = "a" * 40


def delivered_result(*, finalized=True):
    return {
        "status": "accepted",
        "branch": "ai/job12345",
        "commit": OLD_COMMIT,
        "diff": {"diff_hash": "delivered-diff", "changed_files": ["src/app.py"]},
        "verification": {"passed": True, "phases": []},
        "evaluator": "pass",
        "delivery_finalized": finalized,
        "delivery": {
            "state": "ci_success" if finalized else "ci_waiting",
            "pull_request": {
                "number": 42,
                "state": "open",
                "head": OLD_COMMIT,
                "head_ref": "ai/job12345",
                "base_ref": "main",
                "repository": "acme/demo",
            },
        },
        "route": {
            "strategy": {
                "permissions": {
                    "commit": True,
                    "push_ai_branch": True,
                    "create_pr": True,
                },
                "budget": {"max_wall_time_minutes": 10},
            }
        },
    }


def job_row(*, status="completed", blocked_reason="github_ci_timeout"):
    accepted = delivered_result(finalized=status == "completed")
    result = accepted
    if status == "blocked":
        result = {
            "reason": blocked_reason,
            "last_failure": blocked_reason,
            "accepted_result": accepted,
        }
    return {
        "id": "job12345",
        "project_id": "demo",
        "status": status,
        "workspace": "/workspaces/job12345",
        "branch": "ai/job12345",
        "source_commit": SOURCE_COMMIT,
        "task": {"title": "test", "description": "original"},
        "route": deepcopy(accepted["route"]),
        "repo_analysis": {"estimated_files": 1},
        "progress": {
            "elapsed_minutes": 3.5,
            "model_calls": 7,
            "tool_calls": 9,
            "test_runs": 4,
            "repair_iterations": 2,
            "delivery_attempts": 1,
        },
        "checkpoint": {
            "workspace_mode": "isolated_clone",
            "work_order": {"id": "WO-354", "objective": "original"},
            "project_baseline": {"revision": "baseline-1"},
            "route_history": [{"reason": "initial", "route": deepcopy(accepted["route"])}],
            "delivery": deepcopy(accepted["delivery"]),
        },
        "result": result,
        "error": None,
    }


class MemoryStorage:
    def __init__(self, row):
        self.row = deepcopy(row)
        self.events = []

    def get(self, _job_id):
        return deepcopy(self.row)

    def update(self, _job_id, **fields):
        self.row.update(deepcopy(fields))

    def append_event(self, _job_id, event):
        self.events.append(deepcopy(event))


class RepairDdev:
    def __init__(self, *, ci_state="success", workspace_mode="isolated_clone"):
        self.calls = []
        self.ci_state = ci_state
        self.workspace_mode = workspace_mode

    async def prepare_review_repair(self, **kwargs):
        self.calls.append(("prepare", kwargs))
        return {
            **kwargs,
            "workspace_mode": self.workspace_mode,
            "pull_request": {
                "number": kwargs["pr_number"],
                "state": "open",
                "merged": False,
                "head": kwargs["expected_commit"],
                "head_ref": kwargs["branch"],
                "base_ref": "main",
                "repository": "acme/demo",
            },
        }

    async def github_reconcile_delivery(self, **kwargs):
        self.calls.append(("reconcile", kwargs))
        return {"reconciled": False, "delivery": None}

    async def publish_branch(self, **kwargs):
        self.calls.append(("publish", kwargs))
        return {"published": True, "commit": kwargs["expected_commit"]}

    async def upsert_pull_request(self, **kwargs):
        self.calls.append(("pr", kwargs))
        assert kwargs["expected_pr_number"] == 42
        return {
            "created": False,
            "number": 42,
            "state": "open",
            "head": kwargs["expected_commit"],
            "head_ref": kwargs["branch"],
            "base_ref": "main",
        }

    async def github_ci(self, **kwargs):
        self.calls.append(("ci", kwargs))
        return {"state": self.ci_state, "commit": kwargs["commit"], "failure_text": ""}


def pending_record():
    return {
        "request_id": "repair-1",
        "state": "pending",
        "expected_commit": OLD_COMMIT,
        "delivered_diff_hash": "delivered-diff",
        "pr_number": 42,
        "finding": "Repair the bounded PM finding.",
        "message": "PCP_PM_REVIEW_REPAIR: repair the bounded PM finding",
    }


def test_completed_open_pr_can_be_reopened_without_resetting_job_contract_or_history():
    async def scenario():
        original = job_row(status="completed")
        storage = MemoryStorage(original)
        engine = GovernedRuntimeEngine(storage)
        engine.ddev = RepairDdev()
        enqueued = []

        async def enqueue(job_id):
            enqueued.append(job_id)

        engine.enqueue = enqueue
        updated = await engine.request_review_repair(
            "job12345",
            expected_commit=OLD_COMMIT,
            finding="Synchronize the desktop filter draft and query state.",
            evidence={"review": "PM-38"},
            references=["PR #38 review"],
        )

        assert updated["status"] == "queued"
        assert enqueued == ["job12345"]
        assert updated["id"] == original["id"]
        assert updated["workspace"] == original["workspace"]
        assert updated["branch"] == original["branch"]
        assert updated["task"] == original["task"]
        assert updated["progress"] == original["progress"]
        checkpoint = updated["checkpoint"]
        assert checkpoint["work_order"] == original["checkpoint"]["work_order"]
        assert checkpoint["project_baseline"] == original["checkpoint"]["project_baseline"]
        assert checkpoint["route_history"] == original["checkpoint"]["route_history"]
        assert checkpoint["pending_review_repair"]["expected_commit"] == OLD_COMMIT
        assert checkpoint["accepted_result_history"][-1]["result"] == original["result"]
        assert checkpoint["delivery_history"][-1]["delivery"] == original["result"]["delivery"]
        assert checkpoint["failure_context"]["source"] == "pm_review_repair"

    asyncio.run(scenario())


def test_stale_caller_commit_is_rejected_before_executor_validation():
    async def scenario():
        storage = MemoryStorage(job_row(status="completed"))
        engine = GovernedRuntimeEngine(storage)
        ddev = RepairDdev()
        engine.ddev = ddev

        with pytest.raises(RuntimeError, match="Expected commit"):
            await engine.request_review_repair(
                "job12345",
                expected_commit="d" * 40,
                finding="stale finding",
            )

        assert ddev.calls == []
        assert storage.row["status"] == "completed"

    asyncio.run(scenario())


def test_registered_done_worker_still_blocks_review_repair_until_finalizer_exits():
    async def scenario():
        storage = MemoryStorage(job_row(status="completed"))
        engine = GovernedRuntimeEngine(storage)
        ddev = RepairDdev()
        engine.ddev = ddev
        registered = asyncio.create_task(asyncio.sleep(0))
        await registered
        assert registered.done()
        engine.active_jobs["job12345"] = registered

        with pytest.raises(RuntimeError, match="while the job is active"):
            await engine.request_review_repair(
                "job12345",
                expected_commit=OLD_COMMIT,
                finding="Do not race the worker finalizer.",
            )

        assert ddev.calls == []
        assert storage.row["status"] == "completed"

    asyncio.run(scenario())


def test_completed_direct_job_reacquires_same_job_lease_before_branch_restore(monkeypatch):
    class DirectStorage(MemoryStorage):
        def __init__(self, row):
            super().__init__(row)
            self.lease_calls = []

        def acquire_project_lease(self, project_id, job_id):
            self.lease_calls.append((project_id, job_id))
            return {
                "project_id": project_id,
                "owner_job_id": job_id,
                "state": "active",
                "generation": 3,
                "reused": False,
            }

    async def handoff(_self, project_id, job_id):
        assert (project_id, job_id) == ("demo", "job12345")

    async def scenario():
        row = job_row(status="completed")
        row["checkpoint"]["workspace_mode"] = "direct"
        row["workspace"] = "/projects/demo"
        storage = DirectStorage(row)
        engine = GovernedRuntimeEngine(storage)
        engine.ddev = RepairDdev(workspace_mode="direct")
        engine.enqueue = lambda _job_id: asyncio.sleep(0)
        monkeypatch.setattr(
            "app.engine.ProjectPreviewManager.handoff_to_job",
            handoff,
        )

        updated = await engine.request_review_repair(
            "job12345",
            expected_commit=OLD_COMMIT,
            finding="Repair direct-workspace implementation.",
        )

        assert storage.lease_calls == [("demo", "job12345")]
        assert updated["workspace"] == "/projects/demo"
        assert updated["branch"] == "ai/job12345"
        assert updated["checkpoint"]["project_lease_generation"] == 3
        assert updated["checkpoint"]["pending_review_repair"]["executor_verification"][
            "workspace_mode"
        ] == "direct"

    asyncio.run(scenario())


def test_pending_review_repair_precedes_green_delivery_reconciliation(monkeypatch):
    async def scenario():
        row = job_row(status="blocked")
        row["status"] = "queued"
        row["checkpoint"]["pending_review_repair"] = pending_record()
        storage = MemoryStorage(row)
        engine = RuntimeEngine(storage)
        engine.ddev = RepairDdev(ci_state="success")
        engineering_calls = []

        async def engineering_run(_self, job_id):
            engineering_calls.append(job_id)
            current = storage.get(job_id)
            storage.update(job_id, status="blocked", checkpoint=current["checkpoint"])

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            engineering_run,
        )

        await engine.run_job("job12345")

        assert engineering_calls == ["job12345"]
        assert storage.row["status"] == "blocked"
        assert storage.row["checkpoint"]["pending_review_repair"]["request_id"] == "repair-1"
        assert not any(kind in {"reconcile", "publish", "ci"} for kind, _ in engine.ddev.calls)

    asyncio.run(scenario())


def test_provider_interruption_preserves_pending_repair_for_resume(monkeypatch):
    async def scenario():
        row = job_row(status="blocked")
        row["status"] = "queued"
        row["checkpoint"]["pending_review_repair"] = pending_record()
        storage = MemoryStorage(row)
        engine = RuntimeEngine(storage)
        calls = []

        async def interrupted_run(_self, job_id):
            calls.append(job_id)
            current = storage.get(job_id)
            checkpoint = current["checkpoint"]
            checkpoint["last_failure"] = "provider unavailable"
            storage.update(job_id, status="blocked", checkpoint=checkpoint)

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            interrupted_run,
        )
        await engine.run_job("job12345")
        assert storage.row["checkpoint"]["pending_review_repair"]["request_id"] == "repair-1"

        storage.update("job12345", status="queued")
        await engine.run_job("job12345")
        assert calls == ["job12345", "job12345"]
        assert storage.row["checkpoint"]["pending_review_repair"]["request_id"] == "repair-1"

    asyncio.run(scenario())


def test_restart_after_repair_commit_resumes_new_delivery_without_second_engineering_turn(
    monkeypatch,
):
    async def scenario():
        row = job_row(status="blocked")
        row["status"] = "queued"
        row["checkpoint"]["pending_review_repair"] = pending_record()
        row["checkpoint"]["review_repair_history"] = [deepcopy(pending_record())]
        repaired = delivered_result(finalized=False)
        repaired["commit"] = NEW_COMMIT
        repaired.pop("delivery", None)
        row["result"] = repaired
        storage = MemoryStorage(row)
        engine = RuntimeEngine(storage)
        engine.ddev = RepairDdev(ci_state="success")

        async def unexpected_engineering_run(_self, _job_id):
            raise AssertionError("accepted new repair commit must resume delivery")

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            unexpected_engineering_run,
        )

        await engine.run_job("job12345")

        assert storage.row["status"] == "completed"
        assert storage.row["result"]["commit"] == NEW_COMMIT
        assert next(fields for kind, fields in engine.ddev.calls if kind == "ci")[
            "commit"
        ] == NEW_COMMIT

    asyncio.run(scenario())


def test_successful_repair_delivers_new_commit_to_same_pr_and_checks_new_head(monkeypatch):
    async def scenario():
        row = job_row(status="blocked")
        row["status"] = "queued"
        row["checkpoint"]["pending_review_repair"] = pending_record()
        row["checkpoint"]["review_repair_history"] = [deepcopy(pending_record())]
        storage = MemoryStorage(row)
        engine = RuntimeEngine(storage)
        ddev = RepairDdev(ci_state="success")
        engine.ddev = ddev

        async def repaired_run(_self, job_id):
            current = storage.get(job_id)
            result = delivered_result(finalized=False)
            result["commit"] = NEW_COMMIT
            result["diff"] = {"diff_hash": "repair-diff", "changed_files": ["src/app.py"]}
            result.pop("delivery", None)
            storage.update(
                job_id,
                status="delivering",
                result=result,
                checkpoint=current["checkpoint"],
            )

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            repaired_run,
        )
        await engine.run_job("job12345")

        assert storage.row["status"] == "completed"
        assert storage.row["result"]["commit"] == NEW_COMMIT
        assert storage.row["result"]["delivery_finalized"] is True
        assert "pending_review_repair" not in storage.row["checkpoint"]
        assert "active_review_repair" not in storage.row["checkpoint"]
        history = storage.row["checkpoint"]["review_repair_history"][-1]
        assert history["state"] == "completed"
        assert history["new_commit"] == NEW_COMMIT
        publish_call = next(fields for kind, fields in ddev.calls if kind == "publish")
        assert publish_call["review_repair_pr_number"] == 42
        assert publish_call["review_repair_previous_commit"] == OLD_COMMIT
        pr_call = next(fields for kind, fields in ddev.calls if kind == "pr")
        assert pr_call["expected_pr_number"] == 42
        assert pr_call["expected_commit"] == NEW_COMMIT
        ci_calls = [fields for kind, fields in ddev.calls if kind == "ci"]
        assert ci_calls == [{"project_id": "demo", "commit": NEW_COMMIT}]

    asyncio.run(scenario())
