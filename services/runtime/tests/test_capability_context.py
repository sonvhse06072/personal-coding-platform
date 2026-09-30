from __future__ import annotations

import asyncio
import subprocess
from copy import deepcopy
from pathlib import Path

import app.engine_execution as execution_module
from app.adapters.base import AgentAdapter, AgentRun, InvocationCapabilities
from app.adapters.codex import CodexAdapter
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
        return {
            "id": f"{role}-{adapter}",
            "provider": "fixture-provider",
            "adapter": adapter,
            "model": f"fixture-{role}",
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

    storage = EngineStorage(
        {
            "id": job_id,
            "project_id": "demo",
            "status": "queued",
            "source_commit": "a" * 40,
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
