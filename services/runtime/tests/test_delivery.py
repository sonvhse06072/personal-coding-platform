import asyncio

import pytest

import app.engine_delivery as engine_delivery_module
from app.delivery import DeliveryError, deliver_verified_work, pull_request_body
from app.engine_delivery import DeliveryAwareStorage, RuntimeEngine


class FakeDdev:
    def __init__(self, ci_states=None):
        self.calls = []
        self.ci_states = list(ci_states or [])

    async def publish_branch(self, **kwargs):
        self.calls.append(("publish", kwargs))
        return {"published": True, "branch": kwargs["branch"], "commit": kwargs["expected_commit"]}

    async def upsert_pull_request(self, **kwargs):
        self.calls.append(("pr", kwargs))
        return {"created": True, "number": 42, "url": "https://example.test/pr/42"}

    async def github_ci(self, **kwargs):
        self.calls.append(("ci", kwargs))
        evidence = self.ci_states.pop(0) if self.ci_states else "none"
        if isinstance(evidence, dict):
            state = evidence.get("state", "none")
            extra = evidence
        else:
            state = evidence
            extra = {}
        result = {
            **extra,
            "state": state,
            "commit": kwargs["commit"],
        }
        result.setdefault("failure_text", "unit test failed" if state == "failure" else "")
        return result


class MemoryStorage:
    def __init__(self, row=None):
        self.row = dict(row or {"id": "job12345"})
        self.events = []

    def update(self, _job_id, **fields):
        self.row.update(fields)

    def get(self, _job_id):
        return dict(self.row)

    def append_event(self, _job_id, event):
        self.events.append(event)


async def no_sleep(_seconds):
    return None


def common_kwargs(ddev, permissions):
    return {
        "ddev": ddev,
        "job_id": "job12345",
        "project_id": "demo",
        "workspace": "/workspaces/job12345",
        "branch": "ai/job12345",
        "source_commit": "a" * 40,
        "commit": "b" * 40,
        "title": "AI: test",
        "body": "body",
        "permissions": permissions,
        "max_wait_seconds": 5,
        "sleeper": no_sleep,
        "poll_seconds": 0.001,
        "discovery_seconds": 0,
    }


def accepted_result():
    return {
        "status": "accepted",
        "branch": "ai/job12345",
        "commit": "b" * 40,
        "route": {
            "strategy": {
                "permissions": {"push_ai_branch": True, "create_pr": True},
                "budget": {"max_wall_time_minutes": 10},
            }
        },
        "verification": {"passed": True, "phases": []},
        "evaluator": None,
        "delivery": {
            "state": "ci_waiting",
            "publish": {"published": True},
            "pull_request": {"number": 42},
        },
    }


def test_delivery_is_skipped_when_push_gate_is_off():
    async def scenario():
        ddev = FakeDdev()
        result = await deliver_verified_work(**common_kwargs(ddev, {"push_ai_branch": False}))
        assert result["state"] == "skipped"
        assert ddev.calls == []

    asyncio.run(scenario())


def test_publish_without_pr_gate_stops_after_branch_publish():
    async def scenario():
        ddev = FakeDdev()
        result = await deliver_verified_work(
            **common_kwargs(ddev, {"push_ai_branch": True, "create_pr": False})
        )
        assert result["state"] == "published"
        assert [kind for kind, _ in ddev.calls] == ["publish"]

    asyncio.run(scenario())


def test_pr_delivery_waits_for_pending_ci_then_succeeds():
    async def scenario():
        ddev = FakeDdev(["pending", "success"])
        result = await deliver_verified_work(
            **common_kwargs(ddev, {"push_ai_branch": True, "create_pr": True})
        )
        assert result["state"] == "ci_success"
        assert result["pull_request"]["number"] == 42
        assert [kind for kind, _ in ddev.calls] == ["publish", "pr", "ci", "ci"]

    asyncio.run(scenario())


def test_ci_failure_is_returned_for_repair_instead_of_becoming_delivery_error():
    async def scenario():
        ddev = FakeDdev(["failure"])
        result = await deliver_verified_work(
            **common_kwargs(ddev, {"push_ai_branch": True, "create_pr": True})
        )
        assert result["state"] == "ci_failure"
        assert result["ci"]["failure_text"] == "unit test failed"

    asyncio.run(scenario())


def test_repository_without_ci_is_accepted_after_discovery_grace():
    async def scenario():
        ddev = FakeDdev(["none"])
        result = await deliver_verified_work(
            **common_kwargs(ddev, {"push_ai_branch": True, "create_pr": True})
        )
        assert result["state"] == "ci_none"

    asyncio.run(scenario())


def test_delivery_storage_holds_verified_result_in_delivering_state():
    backend = MemoryStorage()
    storage = DeliveryAwareStorage(backend)
    storage.update(
        "job12345",
        status="completed",
        result={
            "status": "accepted",
            "route": {"strategy": {"permissions": {"push_ai_branch": True}}},
        },
    )
    assert backend.row["status"] == "delivering"

    storage.update(
        "job12345",
        status="completed",
        result={
            "status": "accepted",
            "delivery_finalized": True,
            "route": {"strategy": {"permissions": {"push_ai_branch": True}}},
        },
    )
    assert backend.row["status"] == "completed"


def test_verified_delivery_resume_requires_commit_and_only_resumes_infrastructure_ci_failure():
    base = {
        "status": "queued",
        "route": {"strategy": {"permissions": {"push_ai_branch": True}}},
        "result": {"status": "accepted", "commit": "b" * 40},
    }
    assert RuntimeEngine._verified_result_needs_delivery(base) is True

    engineering = dict(base)
    engineering["result"] = {
        **base["result"],
        "delivery": {"state": "ci_failure", "ci": {"failure_class": "engineering"}},
    }
    assert RuntimeEngine._verified_result_needs_delivery(engineering) is False

    infrastructure = dict(base)
    infrastructure["result"] = {
        **base["result"],
        "delivery": {"state": "ci_failure", "ci": {"failure_class": "infrastructure"}},
    }
    assert RuntimeEngine._verified_result_needs_delivery(infrastructure) is True


def test_blocked_delivery_exposes_nested_verified_result_for_resume():
    verified = accepted_result()
    row = {
        "status": "queued",
        "result": {
            "reason": "github_delivery_failed",
            "last_failure": "GitHub API unavailable",
            "accepted_result": verified,
        },
    }
    assert RuntimeEngine._accepted_result_for_delivery(row) == verified
    assert RuntimeEngine._verified_result_needs_delivery(row) is True


def test_blocked_delivery_resume_reuses_verified_commit_without_execution_loop():
    async def scenario():
        verified = accepted_result()
        row = {
            "id": "job12345",
            "project_id": "demo",
            "status": "queued",
            "workspace": "/workspaces/job12345",
            "branch": "ai/job12345",
            "source_commit": "a" * 40,
            "task": {"title": "test"},
            "progress": {"elapsed_minutes": 0.0},
            "checkpoint": {},
            "result": {
                "reason": "github_delivery_failed",
                "last_failure": "GitHub API unavailable",
                "accepted_result": verified,
            },
        }
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev(["none"])

        await engine.run_job("job12345")

        assert backend.row["status"] == "completed"
        assert backend.row["result"]["commit"] == "b" * 40
        assert backend.row["result"]["delivery_finalized"] is True
        assert backend.row["progress"].get("model_calls", 0) == 0

    asyncio.run(scenario())


def test_infrastructure_ci_failure_blocks_without_engineering_repair(monkeypatch):
    async def scenario():
        verified = accepted_result()
        row = {
            "id": "job12345",
            "project_id": "demo",
            "status": "queued",
            "workspace": "/workspaces/job12345",
            "branch": "ai/job12345",
            "source_commit": "a" * 40,
            "task": {"title": "test"},
            "progress": {
                "elapsed_minutes": 0.0,
                "repair_iterations": 4,
                "ci_failures": 2,
                "failure_fingerprints": ["existing"],
                "model_calls": 7,
            },
            "provider_state": {"model-a": {"healthy": True}},
            "checkpoint": {},
            "result": verified,
        }
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev(
            [
                {
                    "state": "failure",
                    "failure_class": "infrastructure",
                    "failure_text": "quality: runner_id=0, steps=[]",
                }
            ]
        )

        async def unexpected_engineering_run(_self, _job_id):
            raise AssertionError("implementation engine must not run")

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            unexpected_engineering_run,
        )

        await engine.run_job("job12345")

        assert backend.row["status"] == "blocked"
        assert backend.row["result"]["reason"] == "github_ci_infrastructure_failure"
        accepted = backend.row["result"]["accepted_result"]
        assert accepted["status"] == "accepted"
        assert accepted["commit"] == "b" * 40
        assert accepted["delivery"]["ci"]["failure_class"] == "infrastructure"
        assert backend.row["progress"]["repair_iterations"] == 4
        assert backend.row["progress"]["ci_failures"] == 2
        assert backend.row["progress"]["failure_fingerprints"] == ["existing"]
        assert backend.row["progress"]["model_calls"] == 7
        assert backend.row["provider_state"] == {"model-a": {"healthy": True}}

    asyncio.run(scenario())


def test_infrastructure_recheck_reuses_commit_and_can_complete(monkeypatch):
    async def scenario():
        row = {
            "id": "job12345",
            "project_id": "demo",
            "status": "queued",
            "workspace": "/workspaces/job12345",
            "branch": "ai/job12345",
            "source_commit": "a" * 40,
            "task": {"title": "test"},
            "progress": {"elapsed_minutes": 0.0, "repair_iterations": 0},
            "checkpoint": {},
            "result": accepted_result(),
        }
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev(
            [
                {"state": "failure", "failure_class": "infrastructure"},
                {"state": "success"},
            ]
        )

        async def unexpected_engineering_run(_self, _job_id):
            raise AssertionError("implementation engine must not run")

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            unexpected_engineering_run,
        )

        await engine.run_job("job12345")
        assert backend.row["status"] == "blocked"
        preserved = backend.row["result"]["accepted_result"]
        assert preserved["commit"] == "b" * 40

        # retry_delivery/recheck_ci queues the same durable job without changing
        # its accepted payload, commit, branch, PR, workspace, or counters.
        backend.update("job12345", status="queued", error=None)
        await engine.run_job("job12345")

        assert backend.row["status"] == "completed"
        assert backend.row["result"]["commit"] == "b" * 40
        assert backend.row["result"]["delivery"]["state"] == "ci_success"
        assert backend.row["result"]["delivery_finalized"] is True
        assert backend.row["progress"]["repair_iterations"] == 0
        assert backend.row["progress"].get("model_calls", 0) == 0
        assert backend.row["progress"]["delivery_attempts"] == 2
        assert backend.row["progress"]["delivery_retry_attempts"] == 1
        assert backend.row["progress"]["infrastructure_retry_attempts"] == 1
        publish_calls = [kwargs for kind, kwargs in engine.ddev.calls if kind == "publish"]
        assert [call["expected_commit"] for call in publish_calls] == ["b" * 40, "b" * 40]

    asyncio.run(scenario())


def test_infrastructure_recheck_exhaustion_blocks_fail_closed(monkeypatch):
    async def scenario():
        row = {
            "id": "job12345",
            "project_id": "demo",
            "status": "queued",
            "workspace": "/workspaces/job12345",
            "branch": "ai/job12345",
            "source_commit": "a" * 40,
            "task": {"title": "test"},
            "progress": {"elapsed_minutes": 0.0, "repair_iterations": 0},
            "checkpoint": {},
            "result": accepted_result(),
        }
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev(
            [
                {"state": "failure", "failure_class": "infrastructure"},
                {"state": "failure", "failure_class": "infrastructure"},
            ]
        )

        async def unexpected_engineering_run(_self, _job_id):
            raise AssertionError("implementation engine must not run")

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            unexpected_engineering_run,
        )

        await engine.run_job("job12345")
        backend.update("job12345", status="queued", error=None)
        await engine.run_job("job12345")

        assert backend.row["status"] == "blocked"
        assert backend.row["result"]["reason"] == "github_ci_infrastructure_failure"
        assert backend.row["result"]["accepted_result"]["commit"] == "b" * 40
        assert backend.row["progress"]["delivery_attempts"] == 2
        assert backend.row["progress"]["infrastructure_retry_attempts"] == 1
        assert backend.row["progress"]["repair_iterations"] == 0
        assert backend.row["progress"].get("failure_fingerprints", []) == []

    asyncio.run(scenario())


def test_engineering_ci_failure_still_enters_repair_flow(monkeypatch):
    async def scenario():
        row = {
            "id": "job12345",
            "project_id": "demo",
            "status": "queued",
            "workspace": "/workspaces/job12345",
            "branch": "ai/job12345",
            "source_commit": "a" * 40,
            "task": {"title": "test"},
            "progress": {"elapsed_minutes": 0.0, "repair_iterations": 0},
            "checkpoint": {},
            "result": accepted_result(),
        }
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev(
            [
                {
                    "state": "failure",
                    "failure_class": "engineering",
                    "failure_text": "Run PHPUnit: assertion failed",
                }
            ]
        )
        parent_calls = []

        async def record_engineering_run(_self, job_id):
            parent_calls.append(job_id)

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            record_engineering_run,
        )

        await engine.run_job("job12345")

        assert parent_calls == ["job12345"]
        assert backend.row["status"] == "queued"
        assert backend.row["progress"]["ci_failures"] == 1
        assert backend.row["progress"]["repair_iterations"] == 1
        assert len(backend.row["progress"]["failure_fingerprints"]) == 1

    asyncio.run(scenario())


def test_pull_request_body_never_claims_auto_merge():
    body = pull_request_body(
        job_id="job12345",
        branch="ai/job12345",
        commit="b" * 40,
        verification={"phases": [{"phase": "targeted_tests"}]},
        evaluator="PASS",
    )
    assert "not auto-merged" in body
    assert "targeted_tests" in body

def test_adaptive_delivery_uses_bounded_attempt_cap_after_total_wall_threshold():
    strategy = {
        "budget_mode": "adaptive",
        "budget": {"max_wall_time_minutes": 10},
    }

    assert RuntimeEngine._delivery_wait_seconds(
        strategy,
        {"elapsed_minutes": 12.5},
    ) == 900


def test_legacy_delivery_still_blocks_after_total_wall_threshold():
    strategy = {
        "budget_mode": "legacy_hard",
        "budget": {"max_wall_time_minutes": 10},
    }

    with pytest.raises(DeliveryError, match="wall-time budget"):
        RuntimeEngine._delivery_wait_seconds(
            strategy,
            {"elapsed_minutes": 10.1},
        )
