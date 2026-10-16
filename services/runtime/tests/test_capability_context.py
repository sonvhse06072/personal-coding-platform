from __future__ import annotations

import asyncio
import subprocess
from copy import deepcopy
from pathlib import Path

import app.engine_execution as execution_module
import pytest
from app.adapters.base import AgentAdapter, AgentRun, InvocationCapabilities
from app.adapters.codex import CodexAdapter
from app.adapters.opencode import OpenCodeAdapter
from app.capability_context import agent_verification_capability_context
from app.engine import RuntimeEngine
from app.prompts import evaluator_prompt, execution_prompt


def _project(*, capability_metadata: bool = True) -> dict:
    ddev = {
        "enabled": True,
        "opaque_listener_gate": ["opaque-runtime-command"],
    }
    if capability_metadata:
        ddev["verification_phase_capabilities"] = {
            "opaque_listener_gate": {"requires": ["local_listener"]},
        }
    return {"ddev": ddev}


def _context(
    adapter: AgentAdapter,
    *,
    mode: str = "execute",
    project: dict | None = None,
    verification: dict | None = None,
):
    return agent_verification_capability_context(
        adapter,
        mode=mode,
        project=project or _project(),
        verification=verification,
    )


def _execution_prompt(context: dict | None) -> str:
    return execution_prompt(
        task={"title": "Bounded change", "description": "Keep verification authoritative"},
        route={"strategy": {"profile": "standard", "definition_of_done": {}}},
        repo_analysis={},
        capability_context=context,
    )


def _evaluator_prompt(
    context: dict | None,
    *,
    verification: dict | None = None,
) -> str:
    return evaluator_prompt(
        task={"title": "Bounded change", "description": "Keep verification authoritative"},
        diff="diff --git a/example b/example",
        verification=verification or {"passed": True, "phases": []},
        capability_context=context,
    )


def test_context_is_bounded_and_uses_metadata_instead_of_command_strings():
    adapter = CodexAdapter("gpt-5.6-sol")

    context = _context(adapter)

    assert context == {
        "unavailable_capabilities": ["local_listener"],
        "runtime_owned_verification_phases": ["opaque_listener_gate"],
        "reason": "codex_workspace_network_disabled",
    }
    assert "opaque-runtime-command" not in str(context)

    framework_named_project = {
        "ddev": {
            "enabled": True,
            "frontend_quality": [
                "playwright localhost next npm run test:browser 3100"
            ],
        }
    }
    assert _context(adapter, project=framework_named_project) is None


def test_execution_prompt_includes_capability_boundary_only_when_both_sides_require_it():
    context = _context(CodexAdapter("gpt-5.6-sol"))
    constrained = _execution_prompt(context)

    assert "AGENT CAPABILITY BOUNDARY" in constrained
    assert "cannot run checks that require opening a local network listener" in constrained
    assert "Do not attempt or repeatedly retry" in constrained
    assert "listener-dependent verification phases when they are applicable" in constrained
    assert "  - opaque_listener_gate" in constrained
    assert "applicable project-owned final verification" in constrained
    assert "not evidence that it passed" in constrained
    assert "Final Runtime/DDEV verification remains authoritative" in constrained
    assert "opaque-runtime-command" not in constrained

    repair = execution_prompt(
        task={"title": "Bounded repair", "description": "Preserve failure evidence"},
        route={"strategy": {"profile": "standard", "definition_of_done": {}}},
        repo_analysis={},
        failure="listen EPERM remains ordinary failure evidence",
        capability_context=context,
    )
    assert "AGENT CAPABILITY BOUNDARY" in repair
    assert "PREVIOUS VERIFICATION FAILURE" in repair
    assert "listen EPERM remains ordinary failure evidence" in repair

    capable = _execution_prompt(_context(AgentAdapter("listener-capable")))
    no_runtime_phase = _execution_prompt(
        _context(CodexAdapter("gpt-5.6-sol"), project=_project(capability_metadata=False))
    )

    assert "AGENT CAPABILITY BOUNDARY" not in capable
    assert "AGENT CAPABILITY BOUNDARY" not in no_runtime_phase


def test_evaluator_omits_configured_but_not_required_listener_phase():
    verification = {"passed": True, "phases": []}
    context = _context(
        CodexAdapter("gpt-5.6-sol"),
        mode="evaluate",
        verification=verification,
    )

    assert context is None
    prompt = _evaluator_prompt(context, verification=verification)
    assert "AGENT CAPABILITY BOUNDARY" not in prompt
    assert "opaque_listener_gate" not in prompt
    assert "Missing or failing required Runtime/DDEV evidence" not in prompt


def test_evaluator_prompt_uses_actual_required_evidence_and_preserves_schema():
    verification = {
        "passed": True,
        "phases": [
            {
                "phase": "opaque_listener_gate",
                "passed": True,
                "commands": [{"command": "opaque", "returncode": 0}],
                "required_for_final": True,
            }
        ],
    }
    context = _context(
        CodexAdapter("gpt-5.6-sol"),
        mode="evaluate",
        verification=verification,
    )
    constrained = _evaluator_prompt(context, verification=verification)

    assert context is not None
    assert "AGENT CAPABILITY BOUNDARY" in constrained
    assert "Do not attempt or repeatedly retry recreating" in constrained
    assert "Judge the authoritative Runtime/DDEV verification evidence" in constrained
    assert "  - opaque_listener_gate" in constrained
    assert "not evidence that it passed" in constrained
    assert "Missing or failing required Runtime/DDEV evidence" in constrained
    assert "must not receive PASS" in constrained
    assert "do not automatically trust developer prose" in constrained
    assert "Return exactly two lines: first PASS or FAIL" in constrained
    assert '"verdict":"pass|fail"' in constrained

    capable = _evaluator_prompt(
        _context(
            AgentAdapter("listener-capable"),
            mode="evaluate",
            verification=verification,
        ),
        verification=verification,
    )
    assert "AGENT CAPABILITY BOUNDARY" not in capable


def _php_project() -> dict:
    return {
        "ddev": {
            "enabled": True,
            "targeted_tests": ["runtime-phpunit"],
            "static_analysis": ["runtime-phpcs"],
            "verification_phase_capabilities": {
                "targeted_tests": {"requires": ["php_runtime"]},
                "static_analysis": {"requires": ["php_runtime"]},
            },
        }
    }


def test_opencode_php_runtime_boundary_is_bounded_and_prompted():
    context = _context(
        OpenCodeAdapter("openrouter/cohere/north-mini-code:free"),
        project=_php_project(),
    )

    assert context == {
        "unavailable_capabilities": ["php_runtime"],
        "runtime_owned_verification_phases": ["static_analysis", "targeted_tests"],
        "reason": "runtime_container_php_unavailable",
    }

    prompt = _execution_prompt(context)
    assert "AGENT CAPABILITY BOUNDARY" in prompt
    assert "has no PHP runtime" in prompt
    assert "direct PHP, PHPCS, PHPUnit, PHPStan" in prompt
    assert "Do not attempt or repeatedly retry PHP" in prompt
    assert "  - static_analysis" in prompt
    assert "  - targeted_tests" in prompt
    assert "Final Runtime/DDEV verification remains authoritative" in prompt


def test_evaluator_php_boundary_uses_only_required_runtime_evidence():
    verification = {
        "passed": True,
        "phases": [
            {
                "phase": "targeted_tests",
                "passed": True,
                "required_for_final": True,
            },
            {
                "phase": "static_analysis",
                "passed": True,
                "required_for_final": False,
            },
        ],
    }
    context = _context(
        OpenCodeAdapter("openrouter/cohere/north-mini-code:free"),
        mode="evaluate",
        project=_php_project(),
        verification=verification,
    )

    assert context == {
        "unavailable_capabilities": ["php_runtime"],
        "runtime_owned_verification_phases": ["targeted_tests"],
        "reason": "runtime_container_php_unavailable",
    }

    prompt = _evaluator_prompt(context, verification=verification)
    assert "has no PHP runtime" in prompt
    assert "required PHP-dependent phases" in prompt
    assert "  - targeted_tests" in prompt
    assert "  - static_analysis" not in prompt
    assert "Missing or failing required Runtime/DDEV evidence" in prompt
    assert "must not receive PASS" in prompt


def test_codex_context_keeps_capabilities_separate_when_both_are_unavailable():
    project = {
        "ddev": {
            "enabled": True,
            "frontend_quality": ["runtime-browser"],
            "targeted_tests": ["runtime-phpunit"],
            "verification_phase_capabilities": {
                "frontend_quality": {"requires": ["local_listener"]},
                "targeted_tests": {"requires": ["php_runtime"]},
            },
        }
    }

    context = _context(CodexAdapter("gpt-5.6-sol"), project=project)

    assert context == {
        "unavailable_capabilities": ["local_listener", "php_runtime"],
        "runtime_owned_verification_phases": ["frontend_quality", "targeted_tests"],
        "reason": "multiple_capabilities_unavailable",
        "capability_phases": {
            "local_listener": ["frontend_quality"],
            "php_runtime": ["targeted_tests"],
        },
        "reasons": {
            "local_listener": "codex_workspace_network_disabled",
            "php_runtime": "runtime_container_php_unavailable",
        },
    }

    prompt = _execution_prompt(context)
    assert "opening a local network listener" in prompt
    assert "has no PHP runtime" in prompt
    assert "  - frontend_quality" in prompt
    assert "  - targeted_tests" in prompt


def test_scoped_codex_broker_hint_only_after_independent_execute_admission():
    project = {
        "ddev": {
            "enabled": True,
            "frontend_quality": ["opaque project-owned frontend check"],
            "targeted_tests": ["opaque project-owned PHP test"],
            "verification_phase_capabilities": {
                "frontend_quality": {"requires": ["local_listener"]},
                "targeted_tests": {"requires": ["php_runtime"]},
            },
        },
    }
    adapter = CodexAdapter("gpt-6-luna", "medium")

    admitted = agent_verification_capability_context(
        adapter, mode="execute", project=project,
        scoped_developer_broker=True,
    )
    assert admitted is not None
    assert admitted["unavailable_capabilities"] == [
        "local_listener", "php_runtime",
    ]
    assert admitted["scoped_developer_tool"] == "pcp_dev.pcp_run_project_checks"
    prompt = _execution_prompt(admitted)
    assert "pcp_dev.pcp_run_project_checks" in prompt
    assert "already admitted, job-scoped Executor broker" in prompt
    assert "No direct PHP" in prompt
    assert "Do not attempt direct local listeners" in prompt
    assert "Final Runtime/DDEV verification remains authoritative" in prompt
    assert "Do not attempt or repeatedly retry PHP, PHPCS" not in prompt
    assert "opaque project-owned PHP test" not in prompt
    assert "opaque project-owned frontend check" not in prompt
    assert "PCP_DEV_BROKER_TOKEN" not in prompt

    denied = agent_verification_capability_context(
        adapter, mode="execute", project=project,
    )
    assert denied is not None
    assert "scoped_developer_tool" not in denied
    assert "pcp_dev.pcp_run_project_checks" not in _execution_prompt(denied)
    assert "Do not attempt or repeatedly retry PHP, PHPCS" in _execution_prompt(denied)


@pytest.mark.parametrize("mode", ["plan", "evaluate"])
def test_scoped_broker_cannot_be_advertised_to_non_developer_modes(mode):
    adapter = CodexAdapter("gpt-6-luna")
    context = agent_verification_capability_context(
        adapter, mode=mode, project=_php_project(),
        scoped_developer_broker=True,
        verification={"phases": [{
            "phase": "targeted_tests", "required_for_final": True,
        }]},
    )
    if context is not None:
        assert "scoped_developer_tool" not in context
        assert "pcp_dev.pcp_run_project_checks" not in (
            _evaluator_prompt(context) if mode == "evaluate"
            else _execution_prompt(context)
        )


def test_scoped_broker_flag_does_not_advertise_tool_to_foreign_adapter():
    context = agent_verification_capability_context(
        OpenCodeAdapter("openrouter/cohere/north-mini-code:free"),
        mode="execute",
        project=_php_project(),
        scoped_developer_broker=True,
    )
    assert context is not None
    assert "scoped_developer_tool" not in context
    assert "pcp_dev.pcp_run_project_checks" not in _execution_prompt(context)


class ExplicitlyConstrainedAdapter(AgentAdapter):
    def invocation_capabilities(self, mode: str) -> InvocationCapabilities:
        return InvocationCapabilities(
            local_listener=False,
            reason=f"fixture_{mode}_listener_unavailable",
        )


def test_context_uses_declared_adapter_capability_not_adapter_name():
    context = _context(ExplicitlyConstrainedAdapter("not-codex"))

    assert context is not None
    assert context["reason"] == "fixture_execute_listener_unavailable"


class UnboundedReasonAdapter(ExplicitlyConstrainedAdapter):
    def invocation_capabilities(self, mode: str) -> InvocationCapabilities:
        del mode
        return InvocationCapabilities(local_listener=False, reason="not bounded!" * 100)


def test_context_replaces_unbounded_adapter_reason():
    context = _context(UnboundedReasonAdapter("not-codex"))

    assert context is not None
    assert context["reason"] == "adapter_local_listener_unavailable"


class EngineStorage:
    def __init__(self, row: dict) -> None:
        self.row = deepcopy(row)
        self.events: list[dict] = []

    def get(self, job_id: str):
        return deepcopy(self.row) if job_id == self.row["id"] else None

    def update(self, job_id: str, **fields) -> None:
        assert job_id == self.row["id"]
        self.row.update(deepcopy(fields))

    def append_event(self, job_id: str, event: dict) -> None:
        assert job_id == self.row["id"]
        self.events.append(deepcopy(event))


class EngineRouter:
    async def reassess(self, payload: dict) -> dict:
        if payload["progress"].get("required_checks_passed"):
            return {"action": "complete", "reason": "Required checks passed", "signals": []}
        return {"action": "continue", "reason": "Repair", "signals": []}


class EngineDdev:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def phase(self, *, phase: str, **kwargs) -> dict:
        del kwargs
        self.calls.append(phase)
        return {
            "phase": phase,
            "passed": True,
            "commands": [{"command": phase, "returncode": 0}],
        }


class EngineAdapter(AgentAdapter):
    def __init__(
        self,
        adapter_name: str,
        model: str,
        prompts: dict[str, list[str]],
        changed_path: str,
    ) -> None:
        super().__init__(model)
        self.adapter_name = adapter_name
        self.prompts = prompts
        self.changed_path = changed_path

    def invocation_capabilities(self, mode: str) -> InvocationCapabilities:
        if self.adapter_name == "codex_cli":
            return CodexAdapter(self.model).invocation_capabilities(mode)
        return super().invocation_capabilities(mode)

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        del timeout
        self.prompts.setdefault(mode, []).append(prompt)
        if mode == "execute":
            target = workspace / self.changed_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("bounded change\n", encoding="utf-8")
            output = "Implemented bounded change"
        else:
            output = (
                'PASS\nREVIEW_JSON: {"verdict":"pass","summary":"Evidence is sufficient",'
                '"findings":[],"jit_context_used":false}'
            )
        return AgentRun(
            adapter=self.adapter_name,
            model=self.model,
            returncode=0,
            output=output,
            usage={"input_tokens": 10, "output_tokens": 5},
        )


def _engine_route(executor_adapter: str, evaluator_adapter: str) -> dict:
    def choice(adapter: str, role: str) -> dict:
        registry = {
            "codex_cli": ("codex_terra", "openai", "gpt-5.6-terra", "low"),
            "opencode": (
                "openrouter_qwen3_coder_free",
                "openrouter",
                "openrouter/cohere/north-mini-code:free",
                None,
            ),
        }
        model_id, provider, model, effort = registry[adapter]
        return {
            "id": model_id,
            "provider": provider,
            "adapter": adapter,
            "model": model,
            "reasoning_effort": effort,
        }

    return {
        "strategy": {
            "profile": "standard",
            "budget_mode": "adaptive",
            "budget": {
                "max_model_calls": 8,
                "max_input_tokens": 10000,
                "max_output_tokens": 10000,
                "max_tool_calls": 30,
                "max_test_runs": 30,
                "max_repair_iterations": 4,
                "max_iterations": 6,
                "max_changed_files": 8,
                "max_wall_time_minutes": 10,
                "hard_cost_usd": 1.0,
            },
            "definition_of_done": {"required": ["material_change"]},
            "permissions": {"commit": False},
            "executor": choice(executor_adapter, "executor"),
            "evaluator": choice(evaluator_adapter, "evaluator"),
            "review_policy": {"level": "standard", "required": True},
        }
    }


def _engine_project() -> dict:
    return {
        "runtime": {"max_diff_bytes": 500000},
        "ddev": {
            "enabled": True,
            "preflight": ["preflight"],
            "targeted_tests": ["targeted"],
            "static_analysis": ["static"],
            "opaque_listener_gate": ["opaque-runtime-command"],
            "auto_required_phases": [
                {
                    "phase": "opaque_listener_gate",
                    "path_prefixes": ["listener/"],
                }
            ],
            "verification_phase_capabilities": {
                "opaque_listener_gate": {"requires": ["local_listener"]},
            },
        },
    }


def _run_engine(
    monkeypatch,
    tmp_path: Path,
    *,
    executor_adapter: str,
    evaluator_adapter: str,
    changed_path: str = "listener/implementation.txt",
) -> dict:
    job_id = f"job-{executor_adapter}-{evaluator_adapter}"
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / job_id
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    (workspace / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=workspace, check=True)
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        text=True,
    ).strip()

    storage = EngineStorage(
        {
            "id": job_id,
            "project_id": "demo",
            "status": "queued",
            "source_commit": source_commit,
            "workspace": str(workspace),
            "branch": f"ai/{job_id}",
            "task": {"title": "Capability integration", "description": "Bounded change"},
            "repo_analysis": {"estimated_files": 1},
            "route": _engine_route(executor_adapter, evaluator_adapter),
            "checkpoint": {"provider_state": {}, "workspace_mode": "isolated_clone"},
            "progress": {},
        }
    )
    prompts: dict[str, list[str]] = {}
    engine = object.__new__(RuntimeEngine)
    engine.storage = storage
    engine.router = EngineRouter()
    ddev = EngineDdev()
    engine.ddev = ddev
    engine.workspace_root = workspace_root

    monkeypatch.setattr(execution_module, "project_config", lambda project_id: _engine_project())
    monkeypatch.setattr(
        execution_module,
        "build_adapter",
        lambda adapter, model, reasoning_effort=None: EngineAdapter(
            adapter,
            model,
            prompts,
            changed_path,
        ),
    )

    asyncio.run(engine.run_job(job_id))

    assert storage.row["status"] == "completed"
    assert len(prompts["execute"]) == 1
    assert len(prompts["evaluate"]) == 1
    return {"prompts": prompts, "ddev_calls": ddev.calls, "row": storage.row}


def test_engine_selected_route_controls_execution_and_evaluator_context(monkeypatch, tmp_path):
    codex_executor = _run_engine(
        monkeypatch,
        tmp_path / "codex-executor",
        executor_adapter="codex_cli",
        evaluator_adapter="opencode",
    )
    assert "opaque_listener_gate" in codex_executor["ddev_calls"]
    assert "AGENT CAPABILITY BOUNDARY" in codex_executor["prompts"]["execute"][0]
    assert "AGENT CAPABILITY BOUNDARY" not in codex_executor["prompts"]["evaluate"][0]

    codex_evaluator = _run_engine(
        monkeypatch,
        tmp_path / "codex-evaluator",
        executor_adapter="opencode",
        evaluator_adapter="codex_cli",
    )
    assert "opaque_listener_gate" in codex_evaluator["ddev_calls"]
    assert "AGENT CAPABILITY BOUNDARY" not in codex_evaluator["prompts"]["execute"][0]
    assert "AGENT CAPABILITY BOUNDARY" in codex_evaluator["prompts"]["evaluate"][0]
    assert '"required_for_final": true' in codex_evaluator["prompts"]["evaluate"][0]

    capable = _run_engine(
        monkeypatch,
        tmp_path / "capable",
        executor_adapter="opencode",
        evaluator_adapter="opencode",
    )
    assert "opaque_listener_gate" in capable["ddev_calls"]
    assert "AGENT CAPABILITY BOUNDARY" not in capable["prompts"]["execute"][0]
    assert "AGENT CAPABILITY BOUNDARY" not in capable["prompts"]["evaluate"][0]


def test_engine_configured_but_unrequired_phase_is_not_required_for_evaluator(
    monkeypatch,
    tmp_path,
):
    result = _run_engine(
        monkeypatch,
        tmp_path / "backend-only",
        executor_adapter="codex_cli",
        evaluator_adapter="codex_cli",
        changed_path="backend/implementation.py",
    )

    assert "opaque_listener_gate" not in result["ddev_calls"]
    assert "AGENT CAPABILITY BOUNDARY" in result["prompts"]["execute"][0]
    assert "when they are applicable" in result["prompts"]["execute"][0]
    assert "AGENT CAPABILITY BOUNDARY" not in result["prompts"]["evaluate"][0]
    assert "opaque_listener_gate" not in result["prompts"]["evaluate"][0]


def _invalid_antigravity_choice() -> dict:
    return {
        "id": "antigravity_free",
        "provider": "google_antigravity",
        "adapter": "antigravity_host",
        "model": "gemini-3.8-flash-medium",
        "reasoning_effort": "max",
    }


def _run_invalid_engine_choice(monkeypatch, tmp_path: Path, phase: str):
    job_id = f"job-invalid-{phase}"
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / job_id
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    (workspace / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=workspace, check=True)
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        text=True,
    ).strip()

    route = _engine_route("codex_cli", "opencode")
    if phase == "planner":
        route["strategy"]["planner"] = _invalid_antigravity_choice()
    elif phase == "executor":
        route["strategy"]["executor"] = _invalid_antigravity_choice()
        route["strategy"]["evaluator"] = None
    elif phase == "evaluator":
        route["strategy"]["evaluator"] = _invalid_antigravity_choice()
    else:
        raise AssertionError(phase)

    storage = EngineStorage(
        {
            "id": job_id,
            "project_id": "demo",
            "status": "queued",
            "source_commit": source_commit,
            "workspace": str(workspace),
            "branch": f"ai/{job_id}",
            "task": {"title": "Capability rejection", "description": "Do not invoke"},
            "repo_analysis": {"estimated_files": 1},
            "route": route,
            "checkpoint": {"provider_state": {}, "workspace_mode": "isolated_clone"},
            "progress": {"model_calls": 0},
        }
    )
    prompts: dict[str, list[str]] = {}
    engine = object.__new__(RuntimeEngine)
    engine.storage = storage
    engine.router = EngineRouter()
    engine.ddev = EngineDdev()
    engine.workspace_root = workspace_root
    builder_calls: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(execution_module, "project_config", lambda project_id: _engine_project())

    def builder(adapter: str, model: str, reasoning_effort: str | None = None):
        builder_calls.append((adapter, model, reasoning_effort))
        return EngineAdapter(adapter, model, prompts, "listener/implementation.txt")

    monkeypatch.setattr(execution_module, "build_adapter", builder)
    with pytest.raises(RuntimeError, match="unsupported"):
        asyncio.run(engine.run_job(job_id))
    return storage, builder_calls


@pytest.mark.parametrize("phase", ["planner", "executor"])
def test_invalid_persisted_choice_consumes_zero_model_calls_and_builds_no_adapter(
    monkeypatch,
    tmp_path,
    phase,
):
    storage, builder_calls = _run_invalid_engine_choice(
        monkeypatch,
        tmp_path / phase,
        phase,
    )

    assert storage.row["progress"]["model_calls"] == 0
    assert builder_calls == []


def test_invalid_evaluator_choice_does_not_record_a_second_model_attempt(
    monkeypatch,
    tmp_path,
):
    storage, builder_calls = _run_invalid_engine_choice(
        monkeypatch,
        tmp_path / "evaluator",
        "evaluator",
    )

    assert storage.row["progress"]["model_calls"] == 1
    assert len(builder_calls) == 1
