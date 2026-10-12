"""CI-first fullpath fixture: provisional developer vs hosted CI vs PM review.

All tests are synthetic; no live DB, Docker, GitHub, Codex or owner workspace.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path

import pytest

from app import engine_delivery as delivery_module
from app.engine_execution import RuntimeEngine as ExecutionRuntimeEngine
from app.engine_delivery import DeliveryAwareStorage, RuntimeEngine
from app.fullpath_ci_deferred import (
    DEFERRED_MODE,
    WAITING_PM,
    ci_passed_awaiting_review,
    fixture_deferred_verification,
    stage_delivery_update,
)
from app.fullpath_fixture_safety import PROJECT_ID
from app.required_ci import FULLPATH_FIXTURE_REPO

from test_delivery import FakeDdev, MemoryStorage
from test_g0_fullpath_required_ci import ci_evidence


COMMIT = "b" * 40


def original_result():
    return {
        "status": "accepted",
        "branch": "ai/synthetic-fixture",
        "commit": COMMIT,
        "verification": fixture_deferred_verification(PROJECT_ID, ddev_enabled=False),
        "route": {"strategy": {
            "permissions": {
                "commit": True, "push_ai_branch": True, "create_pr": True,
            },
            "budget": {"max_wall_time_minutes": 20},
        }},
        "review": {"verdict": "pass", "protocol_valid": True},
    }


def staged():
    row = {"id": "job12345", "project_id": PROJECT_ID}
    changes = {
        "status": "completed",
        "result": original_result(),
        "progress": {
            "elapsed_minutes": 0.0,
            "tests_passed": False,
            "required_checks_passed": True,
            "test_runs": 0,
        },
        "checkpoint": {},
        "error": None,
    }
    result = stage_delivery_update(row, changes)
    return row, result


def full_pr():
    return {
        "number": 99,
        "head": COMMIT,
        "repository": FULLPATH_FIXTURE_REPO,
        "url": "https://github.com/" + FULLPATH_FIXTURE_REPO + "/pull/99",
        "state": "open",
        "merged": False,
    }


def test_deferred_verification_truthfully_declares_no_local_tests():
    actual = fixture_deferred_verification(PROJECT_ID, ddev_enabled=False)
    assert actual["passed"] is True  # PROVISIONAL, never final acceptance
    assert actual["tests_passed"] is False
    assert actual["test_runs"] == 0 and actual["phases"] == []
    assert actual["local_tests_executed"] is False
    assert actual["hosted_ci_pending"] is True
    assert fixture_deferred_verification("other-project", ddev_enabled=False) is None
    ddev = fixture_deferred_verification(PROJECT_ID, ddev_enabled=True)
    assert ddev["passed"] is False
    assert ddev["tests_passed"] is False


def test_existing_engine_verify_uses_no_ddev_phase_for_deferred_fixture():
    class Storage:
        pass
    class ForbiddenDdev:
        async def phase(self, **kwargs):
            raise AssertionError("unapproved DDEV phase was run")
    engine = ExecutionRuntimeEngine(Storage())
    engine.ddev = ForbiddenDdev()
    result = asyncio.run(engine._verify(
        "job12345", PROJECT_ID, Path("/nonexistent"),
        {"ddev": {"enabled": False}},
        {"profile": "fast", "budget": {"max_tool_calls": 0}},
        0.0, {},
    ))
    assert result["tests_passed"] is False
    assert result["verification_mode"] == DEFERRED_MODE
    assert result["local_tests_executed"] is False


def test_original_normal_engine_provisional_result_downgraded_before_durable_storage():
    row, fields = staged()
    assert fields["status"] == "delivering"
    assert fields["result"]["status"] == "accepted"  # internal transport shape
    assert fields["result"]["acceptance_phase"] == "pending_hosted_ci"
    assert fields["result"]["verification"]["passed"] is False
    assert fields["result"]["verification"]["tests_passed"] is False
    assert fields["result"]["verification"]["local_tests_executed"] is False
    assert fields["result"]["delivery_finalized"] is False
    assert fields["progress"]["required_checks_passed"] is False
    assert fields["progress"]["tests_passed"] is False
    assert fields["progress"]["hosted_ci_pending"] is True
    assert fields["checkpoint"]["acceptance_phase"] == "pending_hosted_ci"
    assert row["project_id"] == PROJECT_ID


@pytest.mark.parametrize("mutate", [
    lambda x: x["result"].update({"commit": ""}),
    lambda x: x["result"].update({"commit": "bad"}),
    lambda x: x["result"].update({"branch": "main"}),
    lambda x: x["result"].update({"status": "completed"}),
    lambda x: x["result"].update({"delivery_finalized": True}),
    lambda x: x["result"]["verification"].update({"verification_mode": "legacy"}),
    lambda x: x["result"]["verification"].update({"tests_passed": True}),
    lambda x: x["result"]["verification"].update({"passed": False}),
    lambda x: x["result"]["verification"].update({"local_tests_executed": True}),
    lambda x: x["result"]["route"]["strategy"]["permissions"].update(
        {"commit": False}),
    lambda x: x["result"]["route"]["strategy"]["permissions"].update(
        {"push_ai_branch": False}),
    lambda x: x["result"]["route"]["strategy"]["permissions"].update(
        {"create_pr": False}),
])
def test_invalid_provisional_result_never_becomes_completed_or_delivering(mutate):
    row = {"id": "job12345", "project_id": PROJECT_ID}
    raw = {"status": "completed", "result": original_result()}
    mutate(raw)
    got = stage_delivery_update(row, raw)
    assert got["status"] == "blocked"
    assert got["result"]["reason"] == "fullpath_ci_first_admission_failed"
    assert got["result"]["accepted_result"] == raw["result"]


def test_delivery_aware_storage_preserves_original_legacy_behavior():
    for old_id in ("demo", "pcp-g0-drupal-fixture", "chonhac"):
        backend = MemoryStorage({"id": "job12345", "project_id": old_id})
        proxy = DeliveryAwareStorage(backend)
        proxy.update(
            "job12345", status="completed", result={
                "status": "accepted",
                "route": {"strategy": {
                    "permissions": {"push_ai_branch": False},
                }},
            },
        )
        assert backend.row["status"] == "completed"


def test_delivery_storage_requires_ci_for_only_new_fixture():
    backend = MemoryStorage({"id": "job12345", "project_id": PROJECT_ID})
    proxy = DeliveryAwareStorage(backend)
    _, submitted = staged()
    # Submit the original pre-proxy payload, not an already staged one.
    proxy.update("job12345", status="completed", result=original_result(),
                 progress={"required_checks_passed": True}, checkpoint={})
    assert backend.row["status"] == "delivering"
    assert backend.row["result"]["acceptance_phase"] == "pending_hosted_ci"
    assert backend.row["progress"]["required_checks_passed"] is False
    assert submitted["status"] == "delivering"


def test_hosted_ci_keeps_original_local_test_absence_and_requires_pm():
    row, stage = staged()
    original = deepcopy(stage)
    delivery = {
        "state": "ci_success",
        "pull_request": full_pr(),
        "ci": ci_evidence(),
    }
    output = ci_passed_awaiting_review(
        row=row,
        result=stage["result"],
        progress=stage["progress"],
        checkpoint=stage["checkpoint"],
        delivery=delivery,
    )
    assert output is not None
    result, progress, checkpoint = output
    assert result["acceptance_phase"] == WAITING_PM
    assert result["verification"]["hosted_ci_passed"] is True
    assert result["verification"]["hosted_ci_commit"] == COMMIT
    assert result["verification"]["local_tests_executed"] is False
    assert result["verification"]["tests_passed"] is True  # Hosted, not local
    assert result["delivery_finalized"] is False
    assert progress["required_checks_passed"] is True
    assert progress["hosted_ci_pending"] is False
    assert checkpoint["acceptance_phase"] == WAITING_PM
    assert stage == original


@pytest.mark.parametrize("alter", [
    lambda d: d.update({"state": "ci_none"}),
    lambda d: d.update({"state": "ci_failure"}),
    lambda d: d["pull_request"].update({"number": 0}),
    lambda d: d["pull_request"].update({"number": True}),
    lambda d: d["pull_request"].update({"head": "a"*40}),
    lambda d: d["pull_request"].update({"repository": "other/repo"}),
    lambda d: d["pull_request"].update({"merged": True}),
    lambda d: d["ci"].update({"state": "pending"}),
    lambda d: d["ci"].update({"commit": "a"*40}),
    lambda d: d["ci"]["actions_runs"][0].update({"name": "not-validation"}),
])
def test_invalid_hosted_ci_or_pr_never_qualifies_for_review(alter):
    row, stage = staged()
    delivery = {"state": "ci_success", "ci": ci_evidence(),
                "pull_request": full_pr()}
    alter(delivery)
    assert ci_passed_awaiting_review(
        row=row, result=stage["result"], progress=stage["progress"],
        checkpoint=stage["checkpoint"], delivery=delivery,
    ) is None


def test_real_delivery_engine_stops_at_waiting_human_not_completed():
    async def scenario():
        row, stage = staged()
        backend = MemoryStorage({
            "id": "job12345",
            "project_id": PROJECT_ID,
            "status": "delivering",
            "workspace": "/fullpath/workspaces/job12345",
            "branch": "ai/synthetic-fixture",
            "source_commit": "a"*40,
            "task": {"title": "Synthetic future fixture"},
            "progress": stage["progress"],
            "checkpoint": stage["checkpoint"],
            "result": stage["result"],
        })
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev([ci_evidence()], pr_result=full_pr())
        await engine.run_job("job12345")
        assert backend.row["status"] == "waiting_human"
        assert backend.row["result"]["acceptance_phase"] == WAITING_PM
        assert backend.row["result"]["delivery_finalized"] is False
        assert backend.row["result"]["verification"]["local_tests_executed"] is False
        assert backend.row["result"]["verification"]["hosted_ci_passed"] is True
        assert backend.row["progress"]["required_checks_passed"] is True
        assert [x[0] for x in engine.ddev.calls] == ["publish", "pr", "ci"]
        calls = len(engine.ddev.calls)
        # Second invocation cannot replay Code/PR or bypass Owner/PM review.
        await engine.run_job("job12345")
        assert backend.row["status"] == "waiting_human"
        assert len(engine.ddev.calls) == calls
    asyncio.run(scenario())


def test_real_delivery_engine_generic_ci_success_is_not_final():
    async def scenario():
        row, stage = staged()
        backend = MemoryStorage({
            "id": "job12345", "project_id": PROJECT_ID,
            "status": "delivering", "workspace": "/fullpath/workspaces/job12345",
            "branch": "ai/synthetic-fixture", "source_commit": "a"*40,
            "task": {"title": "Synthetic"}, "progress": stage["progress"],
            "checkpoint": stage["checkpoint"], "result": stage["result"],
        })
        engine = RuntimeEngine(backend)
        engine.ddev = FakeDdev(["success"], pr_result=full_pr())
        await engine.run_job("job12345")
        assert backend.row["status"] == "blocked"
        assert backend.row["result"]["reason"] == "required_exact_ci_unproven"
        assert backend.row["result"]["accepted_result"]["commit"] == COMMIT
        assert backend.row["progress"]["required_checks_passed"] is False
    asyncio.run(scenario())
