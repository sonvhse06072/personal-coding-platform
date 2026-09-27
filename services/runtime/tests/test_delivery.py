import asyncio

import pytest

import app.engine_delivery as engine_delivery_module
from app.delivery import DeliveryError, deliver_verified_work, pull_request_body
from app.engine_delivery import DeliveryAwareStorage, RuntimeEngine


class FakeDdev:
    def __init__(self, ci_states=None, pr_result=None, reconcile_result=None):
        self.calls = []
        self.ci_states = list(ci_states or [])
        self.pr_result = pr_result or {
            "created": True,
            "number": 42,
            "url": "https://example.test/pr/42",
        }
        self.reconcile_result = (
            {"reconciled": False, "delivery": None}
            if reconcile_result is None
            else reconcile_result
        )

    async def github_reconcile_delivery(self, **kwargs):
        self.calls.append(("reconcile", kwargs))
        return dict(self.reconcile_result)

    async def publish_branch(self, **kwargs):
        self.calls.append(("publish", kwargs))
        return {"published": True, "branch": kwargs["branch"], "commit": kwargs["expected_commit"]}

    async def upsert_pull_request(self, **kwargs):
        self.calls.append(("pr", kwargs))
        return dict(self.pr_result)

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


def legacy_misclassified_delivery_row():
    commit = "b" * 40
    source_commit = "a" * 40
    branch = "ai/job12345"
    repository = "acme/demo"
    route = {
        "strategy": {
            "evaluator": {"id": "reviewer-model", "provider": "review-provider"},
            "permissions": {
                "commit": True,
                "push_ai_branch": True,
                "create_pr": True,
            },
            "review_policy": {
                "required": True,
                "independent": True,
                "independence_satisfied": True,
            },
            "budget": {"max_wall_time_minutes": 10},
        }
    }
    progress = {
        "elapsed_minutes": 0.0,
        "model_calls": 9,
        "repair_iterations": 3,
        "ci_failures": 1,
        "test_runs": 4,
        "tool_calls": 8,
        "tests_passed": True,
        "required_checks_passed": True,
        "unexpected_scope": False,
        "important_decision_flags": [],
        "failure_fingerprints": ["legacy-engineering-fingerprint"],
        "review_history": [{
            "level": "standard",
            "verdict": "pass",
            "finding_count": 0,
            "protocol_valid": True,
            "model": "reviewer-model",
            "provider": "review-provider",
        }],
    }
    delivery = {
        "enabled": True,
        "state": "ci_failure",
        "branch": branch,
        "commit": commit,
        "publish": {
            "published": True,
            "branch": branch,
            "commit": commit,
            "source_commit": source_commit,
            "repository": repository,
        },
        "pull_request": {
            "job_id": "job12345",
            "number": 18,
            "url": "https://github.com/acme/demo/pull/18",
            "state": "open",
            "head": commit,
            "head_ref": branch,
            "base_ref": "main",
            "repository": repository,
        },
        # This is legacy evidence. It proves a failed observation on the exact
        # commit, but deliberately does not pretend to know failure_class.
        "ci": {"state": "failure", "commit": commit, "failure_text": "quality failed"},
    }
    return {
        "id": "job12345",
        "project_id": "demo",
        "status": "queued",
        "workspace": "/workspaces/job12345",
        "branch": branch,
        "source_commit": source_commit,
        "task": {"title": "test"},
        "route": route,
        "progress": progress,
        "checkpoint": {
            "work_order": {"id": "WO-288"},
            "route_history": [{"reason": "initial", "route": route}],
            "last_review_report": {
                "verdict": "pass",
                "summary": "Independent review passed.",
                "finding_count": 0,
                "findings": [],
                "protocol_valid": True,
            },
            "delivery": delivery,
        },
        # ExecutionRuntimeEngine._block() replaced the previously accepted
        # result after the obsolete engineering-repair turn made no new diff.
        "result": {
            "reason": "material_change_missing_without_model_fallback",
            "last_failure": "Coding agent completed without material repository changes",
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


def test_delivery_retry_reconciles_already_merged_pr_before_publish():
    async def scenario():
        ddev = FakeDdev(
            reconcile_result={
                "reconciled": True,
                "delivery": {
                    "repository": "acme/demo",
                    "number": 27,
                    "url": "https://github.com/acme/demo/pull/27",
                    "state": "closed",
                    "merged": True,
                    "merged_at": "2026-09-27T17:03:22Z",
                    "merge_commit_sha": "c" * 40,
                    "head": "d" * 40,
                    "head_ref": "ai/job12345",
                    "base_ref": "main",
                    "ci": {"state": "success", "commit": "d" * 40},
                },
            }
        )
        kwargs = common_kwargs(ddev, {"push_ai_branch": True, "create_pr": True})
        kwargs["reconcile_existing"] = True
        result = await deliver_verified_work(**kwargs)

        assert result["state"] == "ci_success"
        assert result["reconciled_external_merge"] is True
        assert result["pull_request"]["number"] == 27
        assert result["pull_request"]["head"] == "d" * 40
        assert [kind for kind, _ in ddev.calls] == ["reconcile"]

    asyncio.run(scenario())


def test_delivery_retry_without_merged_candidate_falls_through_to_existing_publish():
    async def scenario():
        ddev = FakeDdev(["success"])
        kwargs = common_kwargs(ddev, {"push_ai_branch": True, "create_pr": True})
        kwargs["reconcile_existing"] = True
        result = await deliver_verified_work(**kwargs)

        assert result["state"] == "ci_success"
        assert [kind for kind, _ in ddev.calls] == ["reconcile", "publish", "pr", "ci"]

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


def test_delivery_retry_external_merge_completes_same_job_without_model_or_publish(monkeypatch):
    async def scenario():
        verified = accepted_result()
        verified["delivery"] = {"state": "publishing"}
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
                "model_calls": 17,
                "tool_calls": 78,
                "test_runs": 66,
                "repair_iterations": 5,
                "delivery_attempts": 1,
            },
            "checkpoint": {},
            "result": verified,
        }
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev(
            reconcile_result={
                "reconciled": True,
                "delivery": {
                    "repository": "acme/demo",
                    "number": 27,
                    "url": "https://github.com/acme/demo/pull/27",
                    "state": "closed",
                    "merged": True,
                    "merged_at": "2026-09-27T17:03:22Z",
                    "merge_commit_sha": "c" * 40,
                    "head": "d" * 40,
                    "head_ref": "ai/job12345",
                    "base_ref": "main",
                    "ci": {"state": "success", "commit": "d" * 40},
                },
            }
        )

        async def unexpected_engineering_run(_self, _job_id):
            raise AssertionError("external merge reconciliation must not run implementation")

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            unexpected_engineering_run,
        )

        await engine.run_job("job12345")

        assert backend.row["status"] == "completed"
        assert backend.row["workspace"] == row["workspace"]
        assert backend.row["result"]["commit"] == "b" * 40
        assert backend.row["result"]["delivery"]["reconciled_external_merge"] is True
        assert backend.row["result"]["delivery_finalized"] is True
        for key in ("model_calls", "tool_calls", "test_runs", "repair_iterations"):
            assert backend.row["progress"][key] == row["progress"][key]
        assert backend.row["progress"]["delivery_attempts"] == 2
        assert backend.row["progress"]["delivery_retry_attempts"] == 1
        assert [kind for kind, _ in engine.ddev.calls] == ["reconcile"]

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


def test_legacy_misclassified_delivery_recovers_exact_commit_without_coding(monkeypatch):
    async def scenario():
        row = legacy_misclassified_delivery_row()
        original_progress = dict(row["progress"])
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev([
            {
                "state": "failure",
                "failure_class": "infrastructure",
                "failure_text": "quality: runner_id=0, steps=[]",
            },
            {"state": "success"},
        ])

        async def unexpected_engineering_run(_self, _job_id):
            raise AssertionError("legacy delivery recovery must not run implementation")

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            unexpected_engineering_run,
        )

        assert RuntimeEngine._accepted_result_for_delivery(row) is None
        await engine.run_job("job12345")

        assert backend.row["status"] == "blocked"
        assert backend.row["result"]["reason"] == "github_ci_infrastructure_failure"
        assert backend.row["result"]["accepted_result"]["commit"] == "b" * 40
        assert backend.row["progress"]["model_calls"] == original_progress["model_calls"]
        assert backend.row["progress"]["repair_iterations"] == original_progress["repair_iterations"]

        # The existing retry_delivery/recheck_ci action queues this same row.
        backend.update("job12345", status="queued", error=None)
        await engine.run_job("job12345")

        assert backend.row["status"] == "completed"
        assert backend.row["result"]["status"] == "accepted"
        assert backend.row["result"]["commit"] == "b" * 40
        assert backend.row["result"]["delivery"]["state"] == "ci_success"
        assert backend.row["result"]["delivery_finalized"] is True
        assert backend.row["result"]["legacy_delivery_recovery"]["authorized"] is True
        assert (
            backend.row["result"]["legacy_delivery_recovery"]["prior_block"]["reason"]
            == "material_change_missing_without_model_fallback"
        )
        assert backend.row["result"]["verification"]["verification_mode"] == "legacy_durable_recovery"
        assert backend.row["result"]["review"]["verdict"] == "pass"
        assert backend.row["progress"]["model_calls"] == original_progress["model_calls"]
        assert backend.row["progress"]["repair_iterations"] == original_progress["repair_iterations"]
        assert backend.row["progress"]["failure_fingerprints"] == original_progress["failure_fingerprints"]
        publish_calls = [kwargs for kind, kwargs in engine.ddev.calls if kind == "publish"]
        assert [call["expected_commit"] for call in publish_calls] == ["b" * 40, "b" * 40]
        assert {call["branch"] for call in publish_calls} == {"ai/job12345"}

    asyncio.run(scenario())


def test_legacy_misclassified_delivery_missing_acceptance_evidence_fails_closed(monkeypatch):
    async def scenario():
        row = legacy_misclassified_delivery_row()
        row["checkpoint"].pop("last_review_report")
        original_progress = dict(row["progress"])
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev([{"state": "success"}])

        async def unexpected_engineering_run(_self, _job_id):
            raise AssertionError("incomplete legacy evidence must not run implementation")

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            unexpected_engineering_run,
        )

        await engine.run_job("job12345")

        assert backend.row["status"] == "blocked"
        assert backend.row["result"]["reason"] == "legacy_delivery_acceptance_evidence_incomplete"
        assert "review_verdict_passed" in backend.row["result"]["legacy_delivery_recovery"]["missing_evidence"]
        assert backend.row["progress"] == original_progress
        assert engine.ddev.calls == []

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


def test_trusted_exact_sha_success_finalizes_same_accepted_commit_without_implementation(monkeypatch):
    async def scenario():
        commit = "0a9f0f09660d8d61cd99fa1e341c2c4debc6a25e"
        verified = accepted_result()
        verified["commit"] = commit
        verified["branch"] = "ai/812aabd7ab0a"
        verified["delivery"] = {
            "state": "ci_failure",
            "pull_request": {
                "number": 18,
                "head": commit,
                "head_ref": "ai/812aabd7ab0a",
            },
            "ci": {"state": "failure", "failure_class": "infrastructure"},
        }
        row = {
            "id": "812aabd7ab0a5adbb18a7a5edc8d7009",
            "project_id": "demo",
            "status": "queued",
            "workspace": "/workspaces/812aabd7ab0a5adbb18a7a5edc8d7009",
            "branch": "ai/812aabd7ab0a",
            "source_commit": "a" * 40,
            "task": {"title": "test"},
            "progress": {
                "elapsed_minutes": 0.0,
                "model_calls": 11,
                "repair_iterations": 4,
                "ci_failures": 2,
                "failure_fingerprints": ["preserved-engineering-history"],
            },
            "checkpoint": {},
            "result": verified,
        }
        original_progress = dict(row["progress"])
        backend = MemoryStorage(row)
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev(
            [{
                "state": "success",
                "effective_state": "success",
                "infrastructure_failures_superseded": True,
                "failures": [
                    {
                        "source": "github_actions",
                        "run_id": 35964005524,
                        "failure_class": "infrastructure",
                        "effective": False,
                        "superseded_by_trusted_exact_sha": True,
                    }
                ],
                "effective_failures": [],
                "latest_trusted_exact_sha_evidence": {
                    "context": "pcp/exact-sha-ci",
                    "state": "success",
                    "target_sha": commit,
                    "valid": True,
                },
            }],
            pr_result={
                "created": False,
                "number": 18,
                "url": "https://github.com/acme/demo/pull/18",
                "head": commit,
                "head_ref": "ai/812aabd7ab0a",
            },
        )

        async def unexpected_engineering_run(_self, _job_id):
            raise AssertionError("trusted exact-SHA success must not run implementation")

        monkeypatch.setattr(
            engine_delivery_module.ExecutionRuntimeEngine,
            "run_job",
            unexpected_engineering_run,
        )

        await engine.run_job(row["id"])

        assert backend.row["status"] == "completed"
        assert backend.row["workspace"] == row["workspace"]
        assert backend.row["branch"] == "ai/812aabd7ab0a"
        assert backend.row["result"]["commit"] == commit
        assert backend.row["result"]["delivery"]["state"] == "ci_success"
        assert backend.row["result"]["delivery"]["pull_request"]["number"] == 18
        assert backend.row["result"]["delivery"]["ci"][
            "infrastructure_failures_superseded"
        ] is True
        for key in (
            "model_calls",
            "repair_iterations",
            "ci_failures",
            "failure_fingerprints",
        ):
            assert backend.row["progress"][key] == original_progress[key]

    asyncio.run(scenario())


def test_trusted_exact_sha_failure_enters_existing_engineering_repair_path(monkeypatch):
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
        engine.ddev = FakeDdev([{
            "state": "failure",
            "failure_class": "engineering",
            "failure_text": "Exact-SHA validation: repository tests failed",
            "latest_trusted_exact_sha_evidence": {
                "context": "pcp/exact-sha-ci",
                "state": "failure",
                "target_sha": "b" * 40,
                "valid": True,
            },
        }])
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


def test_pull_request_body_reports_recovered_independent_review():
    body = pull_request_body(
        job_id="job12345",
        branch="ai/job12345",
        commit="b" * 40,
        verification={"phases": []},
        evaluator=None,
        review={"verdict": "pass"},
    )

    assert "Independent evaluator: pass" in body

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
