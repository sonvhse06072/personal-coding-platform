import asyncio
import time
from copy import deepcopy

import pytest

from app.adapters.codex import CodexAdapter
from app.capability_context import agent_verification_capability_context
from app.engine import RuntimeEngine
from app.engine_execution import (
    deterministic_verification_failure_signature,
    record_deterministic_verification_failure_streak,
)
from app.review_repair_churn import EPOCH_KEY, new_epoch


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


def row(*, layered=True, legacy=False):
    return {
        "id": "job148",
        "project_id": "demo",
        "status": "verifying",
        "workspace": "/workspaces/job148",
        "checkpoint": {"work_order": None if legacy else work_order(layered=layered)},
        "progress": {},
    }


def strategy(*, mode="adaptive"):
    return {
        "profile": "standard",
        "budget_mode": mode,
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
        by_phase = {item["phase"]: item for item in result["phases"]}
        assert by_phase["static_analysis"]["required_for_final"] is True
        assert by_phase["full_tests"]["required_for_final"] is True
        assert "required_for_final" not in by_phase["targeted_tests"]

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

def test_adaptive_verification_crosses_tool_and_test_high_water_marks():
    async def scenario():
        storage = FakeStorage(row())
        engine = RuntimeEngine(storage)
        ddev = FakeDdev()
        engine.ddev = ddev
        state = progress()
        state["tool_calls"] = 100
        state["test_runs"] = 100

        result = await engine._verify(
            "job148",
            "demo",
            "/workspaces/job148",
            project(),
            strategy(mode="adaptive"),
            time.monotonic(),
            state,
        )

        assert result["passed"] is True
        assert ddev.calls == ["targeted_tests", "static_analysis", "full_tests"]

    asyncio.run(scenario())


def test_legacy_hard_verification_keeps_tool_test_ceiling():
    async def scenario():
        storage = FakeStorage(row())
        engine = RuntimeEngine(storage)
        ddev = FakeDdev()
        engine.ddev = ddev
        state = progress()
        state["tool_calls"] = 100
        state["test_runs"] = 100

        result = await engine._verify(
            "job148",
            "demo",
            "/workspaces/job148",
            project(),
            strategy(mode="legacy_hard"),
            time.monotonic(),
            state,
        )

        assert result["passed"] is False
        assert ddev.calls == []
        assert "verification budget would be exceeded" in result["failure_text"]

    asyncio.run(scenario())

@pytest.mark.parametrize("legacy", [False, True])
def test_chonhac_frontend_diff_gets_project_owned_final_quality_phase(monkeypatch, legacy):
    async def scenario():
        storage = FakeStorage(row(legacy=legacy))
        engine = RuntimeEngine(storage)
        ddev = FakeDdev()
        engine.ddev = ddev
        state = progress()
        cfg = project()
        cfg["runtime"] = {"max_diff_bytes": 750000}
        cfg["ddev"]["frontend_quality"] = ["frontend-quality"]
        cfg["ddev"]["auto_required_phases"] = [
            {
                "phase": "frontend_quality",
                "path_prefixes": ["frontend/"],
            }
        ]
        cfg["ddev"]["verification_phase_capabilities"] = {
            "frontend_quality": {"requires": ["local_listener"]},
        }
        monkeypatch.setattr(
            "app.engine.diff_state",
            lambda workspace, max_bytes: {
                "changed_files": ["frontend/tests/browser/profile.spec.ts"],
            },
        )

        route = strategy()
        route["profile"] = "complex"
        result = await engine._verify(
            "job148",
            "demo",
            "/workspaces/job148",
            cfg,
            route,
            time.monotonic(),
            state,
        )

        assert result["passed"] is True
        assert ddev.calls == [
            "targeted_tests",
            "static_analysis",
            "full_tests",
            "frontend_quality",
        ]
        frontend = result["phases"][-1]
        assert frontend["phase"] == "frontend_quality"
        assert frontend["verification_layer"] == "final"
        assert frontend["required_for_final"] is True
        assert result["tool_calls"] == result["test_runs"] == 4
        assert state["verification_attempts"] == 1
        context = agent_verification_capability_context(
            CodexAdapter("gpt-5.6-sol"),
            mode="evaluate",
            project=cfg,
            verification=result,
        )
        assert context is not None
        assert context["runtime_owned_verification_phases"] == ["frontend_quality"]

    asyncio.run(scenario())


@pytest.mark.parametrize("legacy", [False, True])
def test_chonhac_backend_diff_does_not_require_frontend_quality(monkeypatch, legacy):
    async def scenario():
        storage = FakeStorage(row(legacy=legacy))
        engine = RuntimeEngine(storage)
        ddev = FakeDdev()
        engine.ddev = ddev
        state = progress()
        cfg = project()
        cfg["runtime"] = {"max_diff_bytes": 750000}
        cfg["ddev"]["frontend_quality"] = ["frontend-quality"]
        cfg["ddev"]["auto_required_phases"] = [
            {
                "phase": "frontend_quality",
                "path_prefixes": ["frontend/"],
            }
        ]
        monkeypatch.setattr(
            "app.engine.diff_state",
            lambda workspace, max_bytes: {
                "changed_files": ["web/modules/custom/demo/demo.module"],
            },
        )

        route = strategy()
        route["profile"] = "complex"
        result = await engine._verify(
            "job148",
            "demo",
            "/workspaces/job148",
            cfg,
            route,
            time.monotonic(),
            state,
        )

        assert result["passed"] is True
        assert ddev.calls == [
            "targeted_tests",
            "static_analysis",
            "full_tests",
        ]
        assert all(
            item.get("phase") != "frontend_quality"
            for item in result["phases"]
        )
        assert agent_verification_capability_context(
            CodexAdapter("gpt-5.6-sol"),
            mode="evaluate",
            project=cfg,
            verification=result,
        ) is None

    asyncio.run(scenario())


def test_work_order_required_listener_phase_is_authoritative_for_evaluator():
    job = row()
    contract = work_order()
    contract["verification"] = {
        "intermediate_phases": ["targeted_tests"],
        "required_phases": ["frontend_quality"],
    }
    job["checkpoint"]["work_order"] = contract
    storage = FakeStorage(job)
    engine = RuntimeEngine(storage)
    ddev = FakeDdev()
    engine.ddev = ddev
    cfg = project()
    cfg["ddev"]["frontend_quality"] = ["frontend-quality"]
    cfg["ddev"]["verification_phase_capabilities"] = {
        "frontend_quality": {"requires": ["local_listener"]},
    }

    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", cfg,
        strategy(), time.monotonic(), progress(),
    ))

    assert result["passed"] is True
    assert ddev.calls == ["targeted_tests", "frontend_quality"]
    frontend = result["phases"][-1]
    assert frontend["phase"] == "frontend_quality"
    assert frontend["required_for_final"] is True
    context = agent_verification_capability_context(
        CodexAdapter("gpt-5.6-sol"),
        mode="evaluate",
        project=cfg,
        verification=result,
    )
    assert context is not None
    assert context["runtime_owned_verification_phases"] == ["frontend_quality"]


@pytest.fixture
def auto_required_project(monkeypatch):
    cfg = project()
    cfg["ddev"]["frontend_quality"] = ["frontend-quality"]
    cfg["ddev"]["auto_required_phases"] = [
        {"phase": "frontend_quality", "path_prefixes": ["frontend/"]},
    ]
    cfg["ddev"]["verification_phase_capabilities"] = {
        "frontend_quality": {"requires": ["local_listener"]},
    }
    monkeypatch.setattr(
        "app.engine.diff_state",
        lambda workspace, max_bytes: {"changed_files": ["frontend/app/page.tsx"]},
    )
    return cfg


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("missing", [False, True])
def test_auto_required_phase_without_commands_fails_closed(auto_required_project, legacy, missing):
    cfg = auto_required_project
    if missing:
        del cfg["ddev"]["frontend_quality"]
    else:
        cfg["ddev"]["frontend_quality"] = []
    engine = RuntimeEngine(FakeStorage(row(legacy=legacy)))
    engine.ddev = FakeDdev()

    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", cfg, strategy(), time.monotonic(), progress(),
    ))

    assert result["passed"] is result["tests_passed"] is False
    assert "frontend_quality: required verification has no configured commands" in result["failure_text"]
    assert "frontend_quality" not in engine.ddev.calls


@pytest.mark.parametrize("legacy", [False, True])
def test_failing_auto_required_phase_fails_verification(auto_required_project, legacy):
    engine = RuntimeEngine(FakeStorage(row(legacy=legacy)))
    engine.ddev = FakeDdev({"frontend_quality": False})

    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", auto_required_project,
        strategy(), time.monotonic(), progress(),
    ))

    assert result["passed"] is result["tests_passed"] is False
    assert "frontend_quality" in result["failure_text"]
    assert result["phases"][-1] == {
        "phase": "frontend_quality", "passed": False,
        "commands": ["run-frontend_quality"],
        "verification_layer": "final", "required_for_final": True,
    }
    assert result["tool_calls"] == result["test_runs"] == len(engine.ddev.calls)


@pytest.mark.parametrize("legacy", [False, True])
def test_auto_required_union_is_ordered_and_does_not_rerun_phases(auto_required_project, legacy):
    cfg = auto_required_project
    cfg["ddev"]["auto_required_phases"] = [
        {"phase": phase, "path_prefixes": ["frontend/"]}
        for phase in ["static_analysis", "frontend_quality", "frontend_quality", "full_tests"]
    ]
    engine = RuntimeEngine(FakeStorage(row(legacy=legacy)))
    engine.ddev = FakeDdev()

    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", cfg, strategy(), time.monotonic(), progress(),
    ))

    expected = ["targeted_tests", "static_analysis"]
    expected += ["frontend_quality", "full_tests"] if legacy else ["full_tests", "frontend_quality"]
    assert result["passed"] is True
    assert engine.ddev.calls == expected
    assert [item["phase"] for item in result["phases"]] == expected
    assert result["tool_calls"] == result["test_runs"] == 4


@pytest.mark.parametrize("configured_commands", [[], ["full"]])
def test_completed_legacy_phase_without_commands_cannot_satisfy_auto_requirement(
    auto_required_project, configured_commands,
):
    cfg = auto_required_project
    cfg["ddev"]["full_tests"] = configured_commands
    cfg["ddev"]["auto_required_phases"] = [
        {"phase": "full_tests", "path_prefixes": ["frontend/"]},
    ]

    class EmptyFullTestsDdev(FakeDdev):
        async def phase(self, **kwargs):
            result = await super().phase(**kwargs)
            if kwargs["phase"] == "full_tests":
                result["commands"] = []
            return result

    engine = RuntimeEngine(FakeStorage(row(legacy=True)))
    engine.ddev = EmptyFullTestsDdev()
    route = strategy()
    route["profile"] = "complex"
    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", cfg, route, time.monotonic(), progress(),
    ))

    assert result["verification_mode"] == "legacy"
    assert engine.ddev.calls == ["targeted_tests", "static_analysis", "full_tests"]
    assert result["phases"][-1]["phase"] == "full_tests"
    assert result["phases"][-1]["passed"] is True
    assert result["phases"][-1]["commands"] == []
    assert result["passed"] is result["tests_passed"] is False
    expected = (
        "required verification has no executed commands"
        if configured_commands else "required verification has no configured commands"
    )
    assert f"full_tests: {expected}" in result["failure_text"]


def test_newly_executed_required_phase_without_command_evidence_fails(auto_required_project):
    class EmptyAutoPhaseDdev(FakeDdev):
        async def phase(self, **kwargs):
            result = await super().phase(**kwargs)
            if kwargs["phase"] == "frontend_quality":
                result["commands"] = []
            return result

    engine = RuntimeEngine(FakeStorage(row(legacy=True)))
    engine.ddev = EmptyAutoPhaseDdev()
    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", auto_required_project,
        strategy(), time.monotonic(), progress(),
    ))

    assert engine.ddev.calls == ["targeted_tests", "static_analysis", "frontend_quality"]
    assert result["phases"][-1]["commands"] == []
    assert result["passed"] is result["tests_passed"] is False
    assert "frontend_quality: required verification has no executed commands" in result["failure_text"]


@pytest.mark.parametrize("legacy", [False, True])
def test_failed_base_verification_does_not_resolve_auto_phases(monkeypatch, auto_required_project, legacy):
    def unexpected_diff(*args):
        pytest.fail("Failed base verification must not resolve auto phases")

    monkeypatch.setattr("app.engine.diff_state", unexpected_diff)
    engine = RuntimeEngine(FakeStorage(row(legacy=legacy)))
    engine.ddev = FakeDdev({"targeted_tests": False})

    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", auto_required_project,
        strategy(), time.monotonic(), progress(),
    ))

    assert result["passed"] is result["tests_passed"] is False
    assert "frontend_quality" not in engine.ddev.calls
    assert "frontend_quality" not in result["failure_text"]


@pytest.mark.parametrize("mode", ["adaptive", "legacy_hard"])
def test_legacy_auto_required_phase_preserves_budget_mode(auto_required_project, mode):
    engine = RuntimeEngine(FakeStorage(row(legacy=True)))
    engine.ddev = FakeDdev()
    route = strategy(mode=mode)
    route["budget"].update(max_tool_calls=2, max_test_runs=2)

    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", auto_required_project,
        route, time.monotonic(), progress(),
    ))

    assert result["passed"] is (mode == "adaptive")
    assert ("frontend_quality" in engine.ddev.calls) is (mode == "adaptive")
    if mode == "legacy_hard":
        assert "would exceed execution budget" in result["failure_text"]


@pytest.mark.parametrize("passed", [False, True])
def test_legacy_auto_phase_preserves_churn_epoch_and_counts_one_attempt(auto_required_project, passed):
    job = row(legacy=True)
    state = progress()
    state.update(repair_iterations=50, verification_attempts=52, verification_retry_attempts=51)
    job["checkpoint"].update({
        "pending_review_repair": {"request_id": "test-auto-phase-repair", "state": "pending"},
        EPOCH_KEY: new_epoch(
            "test-auto-phase-repair",
            {"repair_iterations": 45, "verification_attempts": 47},
            legacy_baseline_migrated=False,
        ),
    })
    storage = FakeStorage(job)
    engine = RuntimeEngine(storage)

    class MultiCommandDdev(FakeDdev):
        async def phase(self, **kwargs):
            result = await super().phase(**kwargs)
            if kwargs["phase"] == "frontend_quality":
                result["commands"] = ["typecheck", "build", "browser"]
            return result

    auto_required_project["ddev"]["frontend_quality"] = ["typecheck", "build", "browser"]
    engine.ddev = MultiCommandDdev({"frontend_quality": passed})
    result = asyncio.run(engine._verify(
        "job148", "demo", "/workspaces/job148", auto_required_project,
        strategy(), time.monotonic(), state,
    ))

    assert result["passed"] is passed
    assert result["tool_calls"] == result["test_runs"] == 5
    assert result["verification_attempt"] == state["verification_attempts"] == 53
    assert state["verification_retry_attempts"] == 52
    assert state["repair_iterations"] == 50
    assert storage.row["progress"] == state
    assert storage.row["checkpoint"] == job["checkpoint"]


def _failed_verification(*, output: str, command: str = "phpunit", attempt: int = 1):
    return {
        "passed": False,
        "tests_passed": False,
        "verification_attempt": attempt,
        "phases": [
            {
                "phase": "targeted_tests",
                "passed": False,
                "commands": [
                    {
                        "command": command,
                        "returncode": 1,
                        "timed_out": False,
                        "stdout": output,
                        "stderr": "",
                    }
                ],
            }
        ],
    }


def test_deterministic_failure_signature_ignores_volatile_output() -> None:
    first = deterministic_verification_failure_signature(
        _failed_verification(output="failure at 2.41s"),
        diff_hash="diff-a",
    )
    second = deterministic_verification_failure_signature(
        _failed_verification(output="same failure at 3.02s"),
        diff_hash="diff-a",
    )
    assert first == second


def test_deterministic_failure_streak_trips_after_configured_limit() -> None:
    checkpoint = {}
    one = record_deterministic_verification_failure_streak(
        checkpoint,
        _failed_verification(output="run one", attempt=1),
        diff_hash="diff-a",
        limit=2,
    )
    two = record_deterministic_verification_failure_streak(
        checkpoint,
        _failed_verification(output="run two changed output", attempt=2),
        diff_hash="diff-a",
        limit=2,
    )
    three = record_deterministic_verification_failure_streak(
        checkpoint,
        _failed_verification(output="run three changed output", attempt=3),
        diff_hash="diff-a",
        limit=2,
    )

    assert one["count"] == 1
    assert two["count"] == 2
    assert three["count"] == 3
    assert three["count"] > three["limit"]


def test_deterministic_failure_streak_resets_on_diff_or_command_change() -> None:
    checkpoint = {}
    record_deterministic_verification_failure_streak(
        checkpoint,
        _failed_verification(output="failure", attempt=1),
        diff_hash="diff-a",
        limit=2,
    )
    changed_diff = record_deterministic_verification_failure_streak(
        checkpoint,
        _failed_verification(output="failure", attempt=2),
        diff_hash="diff-b",
        limit=2,
    )
    changed_command = record_deterministic_verification_failure_streak(
        checkpoint,
        _failed_verification(output="failure", command="phpcs", attempt=3),
        diff_hash="diff-b",
        limit=2,
    )

    assert changed_diff["count"] == 1
    assert changed_command["count"] == 1


def test_deterministic_failure_streak_clears_on_pass() -> None:
    checkpoint = {}
    record_deterministic_verification_failure_streak(
        checkpoint,
        _failed_verification(output="failure"),
        diff_hash="diff-a",
        limit=2,
    )
    passed = {
        "passed": True,
        "tests_passed": True,
        "verification_attempt": 2,
        "phases": [
            {
                "phase": "targeted_tests",
                "passed": True,
                "commands": [{"command": "phpunit", "returncode": 0, "timed_out": False}],
            }
        ],
    }
    assert record_deterministic_verification_failure_streak(
        checkpoint,
        passed,
        diff_hash="diff-a",
        limit=2,
    ) is None
    assert "deterministic_verification_failure_streak" not in checkpoint
