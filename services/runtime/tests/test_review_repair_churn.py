from __future__ import annotations

import asyncio
import subprocess
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.engine_execution as execution_module
from app.engine import RuntimeEngine
from app.engine_core import RuntimeEngineCore
from app.review_repair_churn import (
    EPOCH_KEY,
    GATE_KEY,
    HISTORY_KEY,
    INITIALIZED_KEY,
    ReviewRepairChurnPaused,
    decision_identity,
    new_epoch,
    record_observation,
)


class MemoryStorage:
    def __init__(self, row):
        self.row = deepcopy(row)
        self.events = []

    def get(self, job_id):
        return deepcopy(self.row) if job_id == self.row["id"] else None

    def update(self, job_id, **fields):
        assert job_id == self.row["id"]
        self.row.update(deepcopy(fields))

    def append_event(self, job_id, event):
        assert job_id == self.row["id"]
        self.events.append(deepcopy(event))


def _pending(request_id="repair-churn-1"):
    return {
        "request_id": request_id,
        "state": "pending",
        "expected_commit": "b" * 40,
        "delivered_diff_hash": "delivered-diff",
        "pr_number": 38,
        "message": "PCP_PM_REVIEW_REPAIR: bounded finding",
    }


def _progress(*, repairs=42, verifications=45):
    return {
        "repair_iterations": repairs,
        "verification_attempts": verifications,
        "model_calls": 119,
        "tool_calls": 90,
        "test_runs": 88,
        "iteration": 50,
        "elapsed_minutes": 235.5,
        "cost_usd": 0.1,
        "failure_fingerprints": [],
        "progress_markers": [],
        "diff_hashes": [],
    }


def _row(*, status="blocked", repairs=42, verifications=45):
    request_id = "repair-churn-1"
    progress = _progress(repairs=repairs, verifications=verifications)
    return {
        "id": "job-churn-1",
        "project_id": "demo",
        "status": status,
        "source_commit": "a" * 40,
        "workspace": "/workspaces/job-churn-1",
        "branch": "ai/job-churn-1",
        "task": {"title": "Bound repair churn", "description": "test"},
        "repo_analysis": {"estimated_files": 1},
        "route": {
            "strategy": {
                "profile": "standard",
                "budget_mode": "adaptive",
                "budget": {
                    "max_model_calls": 8,
                    "max_input_tokens": 100,
                    "max_output_tokens": 100,
                    "max_tool_calls": 8,
                    "max_iterations": 5,
                    "max_repair_iterations": 2,
                    "max_test_runs": 8,
                    "max_wall_time_minutes": 25,
                    "hard_cost_usd": 10.0,
                    "max_changed_files": 14,
                },
                "human_decision": {"required": False},
                "definition_of_done": {"required": ["material_change"]},
                "permissions": {"commit": False},
                "executor": {
                    "id": "developer",
                    "provider": "test",
                    "adapter": "fake",
                    "model": "fake",
                },
            }
        },
        "progress": progress,
        "checkpoint": {
            "workspace_mode": "isolated_clone",
            "provider_state": {},
            "route_history": [],
            "approved_decisions": [],
            "pending_review_repair": _pending(request_id),
            EPOCH_KEY: new_epoch(
                request_id,
                _progress(repairs=42, verifications=45),
                legacy_baseline_migrated=False,
            ),
        },
        "result": {"reason": "test"},
        "error": None,
    }


def _engine(storage):
    engine = object.__new__(RuntimeEngine)
    engine.storage = storage
    engine.active_jobs = {}
    engine.queue = asyncio.Queue()
    return engine


def test_adaptive_planning_counters_remain_nonblocking_without_review_repair_epoch():
    strategy = deepcopy(_row()["route"]["strategy"])
    progress = _progress(repairs=500, verifications=500)
    progress.update(
        {
            "model_calls": 500,
            "tool_calls": 500,
            "test_runs": 500,
            "iteration": 500,
            "input_tokens": 5_000_000,
            "output_tokens": 1_000_000,
            "elapsed_minutes": 500,
        }
    )

    assert (
        RuntimeEngineCore._pre_model_budget_reason(
            progress,
            strategy,
            include_iteration=True,
        )
        is None
    )


def test_legacy_pending_request_snapshots_historical_counters_exactly_once():
    row = _row()
    row["checkpoint"].pop(EPOCH_KEY)
    storage = MemoryStorage(row)
    engine = _engine(storage)
    checkpoint = deepcopy(row["checkpoint"])
    progress = deepcopy(row["progress"])

    assert engine._ensure_review_repair_churn_epoch(
        job_id=row["id"], checkpoint=checkpoint, progress=progress
    )
    migrated = deepcopy(storage.row["checkpoint"][EPOCH_KEY])
    assert migrated["baseline"] == {
        "repair_iterations": 42,
        "verification_attempts": 45,
    }
    assert migrated["legacy_baseline_migrated"] is True
    assert migrated["baseline_origin"] == "legacy_first_resume"
    assert storage.row["checkpoint"][INITIALIZED_KEY] == {"request_id": "repair-churn-1"}
    assert not engine._review_repair_churn_guard(
        job_id=row["id"], checkpoint=checkpoint, progress=progress
    )

    progress["repair_iterations"] = 47
    progress["verification_attempts"] = 51
    checkpoint = deepcopy(storage.row["checkpoint"])
    assert not engine._ensure_review_repair_churn_epoch(
        job_id=row["id"], checkpoint=checkpoint, progress=progress
    )
    assert storage.row["checkpoint"][EPOCH_KEY] == migrated


def test_varied_diff_and_fingerprint_churn_trips_total_epoch_guard():
    row = _row(repairs=48, verifications=53)
    row["progress"]["failure_fingerprints"] = [f"finding-{i}" for i in range(12)]
    row["progress"]["progress_markers"] = [f"progress-{i}" for i in range(12)]
    row["progress"]["diff_hashes"] = [f"diff-{i}" for i in range(12)]
    record_observation(
        row["checkpoint"],
        diff_hash="latest-material-diff",
        verification={
            "passed": False,
            "tests_passed": False,
            "verification_attempt": 53,
            "failure_text": "latest deterministic failure",
            "phases": [{"phase": "full_tests", "passed": False}],
        },
        review={
            "verdict": "fail",
            "summary": "latest reviewer summary",
            "finding_count": 1,
            "findings": [{"id": "finding-latest", "message": "repair it"}],
        },
    )
    storage = MemoryStorage(row)
    engine = _engine(storage)

    assert engine._review_repair_churn_guard(
        job_id=row["id"],
        checkpoint=deepcopy(row["checkpoint"]),
        progress=deepcopy(row["progress"]),
    )

    assert storage.row["status"] == "waiting_human"
    assert storage.row["result"]["reason"] == "repair_churn_circuit_breaker"
    evidence = storage.row["result"]["evidence"]
    assert evidence["delta"] == {
        "repair_iterations": 6,
        "verification_attempts": 8,
    }
    assert evidence["reached"]["repair_cycles"] is True
    assert evidence["reached"]["verification_cycles"] is True
    assert evidence["latest_diff_hash"] == "latest-material-diff"
    assert evidence["latest_review_summary"]["summary"] == "latest reviewer summary"
    assert evidence["latest_verification_summary"]["failure_text"] == (
        "latest deterministic failure"
    )
    assert evidence["failure_fingerprint_tail"] == [
        f"finding-{i}" for i in range(4, 12)
    ]
    assert evidence["progress_marker_tail"] == [
        f"progress-{i}" for i in range(4, 12)
    ]


def test_guard_stops_before_another_developer_model_turn(monkeypatch, tmp_path):
    row = _row(status="queued", repairs=48, verifications=45)
    root = tmp_path / "workspaces"
    workspace = root / row["id"]
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    row["workspace"] = str(workspace)
    storage = MemoryStorage(row)
    engine = object.__new__(execution_module.RuntimeEngine)
    engine.storage = storage
    engine.workspace_root = root
    engine.ddev = object()

    monkeypatch.setattr(
        execution_module,
        "project_config",
        lambda _project_id: {
            "path": str(tmp_path / "source"),
            "runtime": {"max_diff_bytes": 10000},
            "ddev": {"enabled": False},
        },
    )
    monkeypatch.setattr(
        execution_module,
        "build_adapter",
        lambda *_args, **_kwargs: pytest.fail("developer model must not be built"),
    )

    asyncio.run(engine.run_job(row["id"]))

    assert storage.row["status"] == "waiting_human"
    assert storage.row["progress"]["model_calls"] == 119


def test_guard_stops_before_another_ddev_verification_cycle(monkeypatch):
    row = _row(status="verifying", repairs=42, verifications=53)
    storage = MemoryStorage(row)
    engine = _engine(storage)
    original_epoch = deepcopy(row["checkpoint"][EPOCH_KEY])
    current_diff = Mock(side_effect=AssertionError("Auto phases must not be resolved after churn stop"))
    monkeypatch.setattr("app.engine.diff_state", current_diff)

    class NoDdev:
        async def phase(self, **_kwargs):
            raise AssertionError("DDEV verification must not run")

    engine.ddev = NoDdev()
    with pytest.raises(ReviewRepairChurnPaused):
        asyncio.run(
            engine._verify(
                row["id"],
                "demo",
                "/workspaces/job-churn-1",
                {"ddev": {
                    "enabled": True,
                    "auto_required_phases": [
                        {"phase": "frontend_quality", "path_prefixes": ["frontend/"]},
                    ],
                    "frontend_quality": ["browser"],
                }},
                row["route"]["strategy"],
                time.monotonic(),
                deepcopy(row["progress"]),
            )
        )
    assert storage.row["status"] == "waiting_human"
    assert storage.row["progress"]["verification_attempts"] == 53
    assert storage.row["checkpoint"][EPOCH_KEY] == original_epoch
    current_diff.assert_not_called()


def test_interrupted_ddev_attempt_is_durable_and_blocks_replay_after_restart():
    row = _row(status="verifying", repairs=42, verifications=52)
    storage = MemoryStorage(row)
    engine = _engine(storage)

    class InterruptedDdev:
        async def phase(self, **_kwargs):
            raise RuntimeError("simulated DDEV interruption")

    engine.ddev = InterruptedDdev()
    with pytest.raises(RuntimeError, match="simulated DDEV interruption"):
        asyncio.run(
            engine._verify(
                row["id"],
                "demo",
                "/workspaces/job-churn-1",
                {
                    "ddev": {
                        "enabled": True,
                        "targeted_tests": ["targeted"],
                        "static_analysis": ["static"],
                    }
                },
                row["route"]["strategy"],
                time.monotonic(),
                deepcopy(row["progress"]),
            )
        )

    assert storage.row["progress"]["verification_attempts"] == 53
    restarted = _engine(storage)
    assert restarted._review_repair_churn_guard(
        job_id=row["id"],
        checkpoint=deepcopy(storage.row["checkpoint"]),
        progress=deepcopy(storage.row["progress"]),
    )
    assert storage.row["status"] == "waiting_human"


def test_restart_provider_reset_and_reroute_preserve_epoch_baseline():
    async def scenario():
        row = _row()
        row["checkpoint"]["provider_state"] = {
            "provider:test": {"available": False}
        }
        storage = MemoryStorage(row)
        # A fresh engine over the same durable row models a Runtime restart.
        engine = _engine(storage)

        class Router:
            async def route(self, _payload):
                return deepcopy(row["route"])

        engine.router = Router()
        engine.enqueue = lambda _job_id: asyncio.sleep(0)
        baseline = deepcopy(row["checkpoint"][EPOCH_KEY])

        updated = await engine.resume(
            row["id"],
            reset_transient_provider_failures=True,
            reroute=True,
        )

        assert updated["status"] == "queued"
        assert updated["checkpoint"][EPOCH_KEY] == baseline
        assert "provider:test" not in updated["checkpoint"]["provider_state"]

    asyncio.run(scenario())


def _recovery_engine(row, monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    workspace = root / row["id"]
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    row["workspace"] = str(workspace)
    storage = MemoryStorage(row)
    engine = _engine(storage)
    engine.workspace_root = root
    model = Mock(side_effect=AssertionError("model call after durable churn stop"))
    phase = AsyncMock(side_effect=AssertionError("DDEV call after durable churn stop"))
    engine.ddev = SimpleNamespace(phase=phase)
    monkeypatch.setattr(execution_module, "build_adapter", model)
    monkeypatch.setattr(
        execution_module,
        "project_config",
        lambda _project_id: {
            "path": str(tmp_path / "source"),
            "runtime": {"max_diff_bytes": 10000},
            "ddev": {"enabled": True},
        },
    )
    return storage, engine, model, phase


def _invoke_recovery(engine, row, entry):
    if entry == "run":
        engine.storage.update(row["id"], status="queued")
        asyncio.run(engine.run_job(row["id"]))
    else:
        with pytest.raises(ReviewRepairChurnPaused):
            asyncio.run(engine._verify(
                row["id"], "demo", row["workspace"],
                {"ddev": {"enabled": True}}, row["route"]["strategy"],
                time.monotonic(), deepcopy(row["progress"]),
            ))


@pytest.mark.parametrize("entry", ["run", "verify"])
@pytest.mark.parametrize("damage", [
    "null_epoch", "list_epoch", "empty_epoch", "malformed_baseline",
    "fractional_generation", "missing_started_at", "wrong_epoch_request", "missing_with_gate",
    "missing_with_pending_decision", "missing_with_initialization",
    "missing_with_history", "missing_with_decision_history",
    "null_gate", "list_gate", "missing_gate_request", "missing_gate_generation",
    "wrong_gate_request", "wrong_gate_generation", "wrong_gate_decision_key",
    "wrong_gate_baseline", "wrong_pending_generation",
])
def test_inconsistent_recovery_metadata_blocks_without_reset_or_work(
    entry, damage, monkeypatch, tmp_path,
):
    stopped, _ = _waiting_churn_row()
    row = deepcopy(stopped.row)
    checkpoint = row["checkpoint"]
    epoch = deepcopy(checkpoint[EPOCH_KEY])
    if damage == "null_epoch":
        checkpoint[EPOCH_KEY] = None
    elif damage == "list_epoch":
        checkpoint[EPOCH_KEY] = []
    elif damage == "empty_epoch":
        checkpoint[EPOCH_KEY] = {}
    elif damage == "malformed_baseline":
        checkpoint[EPOCH_KEY]["baseline"] = None
    elif damage == "fractional_generation":
        checkpoint[EPOCH_KEY]["generation"] = 0.5
    elif damage == "missing_started_at":
        checkpoint[EPOCH_KEY].pop("started_at")
    elif damage == "wrong_epoch_request":
        checkpoint[EPOCH_KEY]["request_id"] = "another-request"
    elif damage.startswith("missing_with_"):
        checkpoint.pop(EPOCH_KEY)
        if damage != "missing_with_gate":
            checkpoint.pop(GATE_KEY)
        if damage not in {"missing_with_gate", "missing_with_pending_decision"}:
            checkpoint.pop("pending_decision")
        if damage == "missing_with_initialization":
            checkpoint[INITIALIZED_KEY] = {"request_id": epoch["request_id"]}
        elif damage == "missing_with_history":
            checkpoint[HISTORY_KEY] = [epoch]
        elif damage == "missing_with_decision_history":
            checkpoint["decision_history"] = [{
                "source": "review_repair_churn", "request_id": epoch["request_id"],
                "generation": 0, "action": "reject",
            }]
    elif damage == "null_gate":
        checkpoint[GATE_KEY] = None
    elif damage == "list_gate":
        checkpoint[GATE_KEY] = []
    elif damage == "missing_gate_request":
        checkpoint[GATE_KEY].pop("request_id")
    elif damage == "missing_gate_generation":
        checkpoint[GATE_KEY].pop("generation")
    elif damage == "wrong_gate_request":
        checkpoint[GATE_KEY]["request_id"] = "another-request"
    elif damage == "wrong_gate_generation":
        checkpoint[GATE_KEY]["generation"] = 1
    elif damage == "wrong_gate_decision_key":
        checkpoint[GATE_KEY]["decision_key"] = "stale-key"
    elif damage == "wrong_gate_baseline":
        checkpoint[GATE_KEY]["baseline"]["repair_iterations"] = 43
    elif damage == "wrong_pending_generation":
        checkpoint["pending_decision"]["generation"] = 1

    storage, engine, model, phase = _recovery_engine(row, monkeypatch, tmp_path)
    original_checkpoint = deepcopy(checkpoint)
    for _ in range(2):
        _invoke_recovery(engine, row, entry)
        assert storage.row["status"] == "blocked"
        assert storage.row["result"]["reason"] == "repair_churn_circuit_breaker"
        assert storage.row["result"]["evidence"]["integrity_error"]
        assert len(str(storage.row["result"]["evidence"])) < 2500
        # Includes absent/null epochs, generation/baseline, gate, histories and
        # the original pending repair finding: recovery must not rewrite any.
        assert storage.row["checkpoint"] == original_checkpoint
        assert storage.row["progress"] == row["progress"]
    model.assert_not_called()
    phase.assert_not_called()


@pytest.mark.parametrize("invalid_epoch", [None, [], {}])
def test_explicit_invalid_epoch_is_not_legacy_without_other_feature_evidence(invalid_epoch):
    row = _row()
    row["checkpoint"][EPOCH_KEY] = invalid_epoch
    storage = MemoryStorage(row)
    engine = _engine(storage)
    asyncio.run(engine.run_job(row["id"]))
    assert storage.row["status"] == "blocked"
    assert storage.row["checkpoint"] == row["checkpoint"]
    assert storage.row["progress"] == row["progress"]


def test_unrelated_archived_request_does_not_prevent_genuine_legacy_migration():
    row = _row()
    row["checkpoint"][HISTORY_KEY] = [new_epoch(
        "previous-request", row["progress"], legacy_baseline_migrated=False,
    )]
    row["checkpoint"].pop(EPOCH_KEY)
    storage = MemoryStorage(row)
    engine = _engine(storage)
    assert engine._ensure_review_repair_churn_epoch(
        job_id=row["id"], checkpoint=row["checkpoint"], progress=row["progress"],
    )
    assert storage.row["checkpoint"][EPOCH_KEY]["baseline"] == {
        "repair_iterations": 42, "verification_attempts": 45,
    }


@pytest.mark.parametrize("entry", ["run", "verify"])
@pytest.mark.parametrize("rejected", [False, True])
def test_persisted_gate_latches_with_stale_progress_above_baseline(
    entry, rejected, monkeypatch, tmp_path,
):
    stopped, prior_engine = _waiting_churn_row()
    key = stopped.row["checkpoint"]["pending_decision"]["key"]
    if rejected:
        asyncio.run(prior_engine.resolve_human_decision(
            stopped.row["id"], action="reject", expected_decision_key=key,
        ))
    row = deepcopy(stopped.row)
    row["progress"]["repair_iterations"] = 47  # baseline=42, gate tripped at 48
    storage, engine, model, phase = _recovery_engine(row, monkeypatch, tmp_path)
    for _ in range(2):
        _invoke_recovery(engine, row, entry)
        assert storage.row["status"] == "waiting_human"
        for field in (EPOCH_KEY, GATE_KEY, "pending_review_repair"):
            assert storage.row["checkpoint"][field] == row["checkpoint"][field]
        for field, value in row["progress"].items():
            assert storage.row["progress"][field] == value
        assert storage.row["result"]["evidence"] == row["checkpoint"][GATE_KEY]
        assert storage.row["result"]["evidence"]["current"]["repair_iterations"] == 48
        assert storage.row["checkpoint"]["pending_decision"]["key"] == key
    model.assert_not_called()
    phase.assert_not_called()

    # Even with stale counters, only the exact authorization opens a window.
    engine.enqueue = AsyncMock()
    with pytest.raises(RuntimeError, match="exact decision key"):
        asyncio.run(engine.resolve_human_decision(row["id"], action="approve"))
    approved = asyncio.run(engine.resolve_human_decision(
        row["id"], action="approve", expected_decision_key=key,
    ))
    assert approved["checkpoint"][EPOCH_KEY]["generation"] == 1
    assert approved["checkpoint"][EPOCH_KEY]["baseline"]["repair_iterations"] == 47
    assert GATE_KEY not in approved["checkpoint"]
    engine.enqueue.assert_awaited_once_with(row["id"])


def _waiting_churn_row():
    row = _row(status="blocked", repairs=48, verifications=45)
    storage = MemoryStorage(row)
    engine = _engine(storage)
    checkpoint = deepcopy(row["checkpoint"])
    progress = deepcopy(row["progress"])
    assert engine._review_repair_churn_guard(
        job_id=row["id"], checkpoint=checkpoint, progress=progress
    )
    return storage, engine


def test_human_approve_creates_generation_n_plus_one_and_old_key_is_stale():
    async def scenario():
        storage, engine = _waiting_churn_row()
        engine.enqueue = lambda _job_id: asyncio.sleep(0)
        old_key = storage.row["checkpoint"]["pending_decision"]["key"]

        approved = await engine.resolve_human_decision(
            storage.row["id"],
            action="approve",
            note="Authorize one bounded window.",
            expected_decision_key=old_key,
        )

        epoch = approved["checkpoint"][EPOCH_KEY]
        assert epoch["generation"] == 1
        assert epoch["baseline"] == {
            "repair_iterations": 48,
            "verification_attempts": 45,
        }
        assert GATE_KEY not in approved["checkpoint"]

        progressed = deepcopy(approved["progress"])
        progressed["repair_iterations"] = 54
        checkpoint = deepcopy(approved["checkpoint"])
        assert engine._review_repair_churn_guard(
            job_id=approved["id"], checkpoint=checkpoint, progress=progressed
        )
        new_key = storage.row["checkpoint"]["pending_decision"]["key"]
        assert new_key == decision_identity("repair-churn-1", 1)
        assert new_key != old_key

        with pytest.raises(RuntimeError, match="stale or does not match"):
            await engine.resolve_human_decision(
                approved["id"],
                action="approve",
                expected_decision_key=old_key,
            )

    asyncio.run(scenario())


def test_human_reject_and_ordinary_run_do_not_rearm_epoch():
    async def scenario():
        storage, engine = _waiting_churn_row()
        engine.enqueue = lambda _job_id: asyncio.sleep(0)
        key = storage.row["checkpoint"]["pending_decision"]["key"]
        baseline = deepcopy(storage.row["checkpoint"][EPOCH_KEY])

        rejected = await engine.resolve_human_decision(
            storage.row["id"],
            action="reject",
            note="Stop this repair attempt.",
            expected_decision_key=key,
        )
        assert rejected["status"] == "blocked"
        assert rejected["checkpoint"][EPOCH_KEY] == baseline
        assert rejected["result"]["reason"] == "repair_churn_circuit_breaker"

        resumed = await engine.resume(storage.row["id"])
        assert resumed["checkpoint"][EPOCH_KEY] == baseline
        assert engine._review_repair_churn_guard(
            job_id=resumed["id"],
            checkpoint=deepcopy(resumed["checkpoint"]),
            progress=deepcopy(resumed["progress"]),
        )
        assert storage.row["status"] == "waiting_human"
        assert storage.row["checkpoint"][EPOCH_KEY] == baseline
        assert storage.row["checkpoint"]["pending_decision"]["key"] == key

    asyncio.run(scenario())
