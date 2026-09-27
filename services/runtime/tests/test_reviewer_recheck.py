from __future__ import annotations

import asyncio
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import app.engine_execution as execution_module
from app.adapters.base import AgentRun
from app.engine_execution import RuntimeEngine


class FakeStorage:
    def __init__(self, row: dict) -> None:
        self.row = deepcopy(row)

    def get(self, job_id: str):
        return deepcopy(self.row) if job_id == self.row["id"] else None

    def update(self, job_id: str, **fields) -> None:
        assert job_id == self.row["id"]
        self.row.update(deepcopy(fields))


class AntiLoopRouter:
    def __init__(self) -> None:
        self.reassessments: list[dict] = []

    async def reassess(self, payload: dict) -> dict:
        self.reassessments.append(deepcopy(payload))
        progress = payload["progress"]
        fingerprints = progress.get("failure_fingerprints") or []
        if len(fingerprints) >= 2 and fingerprints[-1] == fingerprints[-2]:
            signal = f"repeated_failure:{fingerprints[-1]}"
            return {
                "action": "stop",
                "reason": "Circuit breaker: repeated unresolved reviewer finding",
                "signals": [signal],
            }
        if progress.get("required_checks_passed"):
            return {"action": "complete", "reason": "All required checks passed", "signals": []}
        return {"action": "continue", "reason": "Bounded repair remains available", "signals": []}


class ReviewLoopAdapter:
    def __init__(self, workspace: Path, *, resolve_on_recheck: bool) -> None:
        self.workspace = workspace
        self.resolve_on_recheck = resolve_on_recheck
        self.execution_prompts: list[str] = []
        self.evaluator_prompts: list[str] = []

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        del timeout
        assert Path(workspace) == self.workspace
        if mode == "execute":
            self.execution_prompts.append(prompt)
            if len(self.execution_prompts) == 1:
                (self.workspace / "implementation.txt").write_text("bounded change\n", encoding="utf-8")
                output = "FIRST_DEVELOPER_REPORT"
                stderr = "RAW_PRIOR_STDERR_MUST_NOT_REACH_REVIEW"
            else:
                output = "DEVELOPER_REBUTTAL\n" + ("R" * 3500) + "\nUNBOUNDED_REPORT_TAIL"
                stderr = ""
            return AgentRun(
                adapter="fake",
                model="fake-model",
                returncode=0,
                output=output,
                stderr=stderr,
                usage={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.000001},
            )

        assert mode == "evaluate"
        self.evaluator_prompts.append(prompt)
        if len(self.evaluator_prompts) == 2 and self.resolve_on_recheck:
            output = (
                'PASS\nREVIEW_JSON: {"verdict":"pass","summary":"Developer rebuttal is supported '
                'by repository evidence","findings":[],"jit_context_used":true}'
            )
        else:
            output = (
                'FAIL\nREVIEW_JSON: {"verdict":"fail","summary":"Stored rate evidence remains '
                'unresolved","findings":[{"id":"CONTACT-RATE-FIXTURE","severity":"medium",'
                '"category":"tests","message":"Prove the stored rate is redacted",'
                '"evidence_refs":["frontend/tests/browser/musician-profile.spec.ts"]}],'
                '"jit_context_used":true}'
            )
        return AgentRun(
            adapter="fake",
            model="fake-model",
            returncode=0,
            output=output,
            usage={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.000001},
        )


def _workspace(tmp_path: Path, job_id: str) -> tuple[Path, Path]:
    root = tmp_path / "workspaces"
    workspace = root / job_id
    workspace.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    (workspace / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=workspace, check=True)
    return root, workspace


def _route() -> dict:
    choice = {
        "id": "codex_terra",
        "provider": "openai",
        "adapter": "fake",
        "model": "fake-model",
    }
    return {
        "strategy": {
            "profile": "standard",
            "budget_mode": "adaptive",
            "budget": {
                "max_model_calls": 20,
                "max_input_tokens": 100000,
                "max_output_tokens": 20000,
                "max_tool_calls": 100,
                "max_test_runs": 100,
                "max_repair_iterations": 12,
                "max_iterations": 20,
                "max_changed_files": 8,
                "max_wall_time_minutes": 60,
                "hard_cost_usd": 10.0,
            },
            "definition_of_done": {"required": ["material_change"]},
            "permissions": {"commit": False},
            "executor": choice,
            "evaluator": {**choice, "id": "reviewer_model"},
            "review_policy": {"level": "standard", "required": True},
        }
    }


def _row(workspace: Path, job_id: str) -> dict:
    work_order = {
        "id": "WO-284",
        "objective": "Carry developer repair evidence into reviewer re-check",
        "in_scope": ["Runtime reviewer dialogue"],
        "out_of_scope": ["Changing anti-loop policy"],
        "acceptance_criteria": [{"id": "AC-1", "description": "Reviewer sees bounded response"}],
    }
    return {
        "id": job_id,
        "project_id": "demo",
        "status": "queued",
        "source_commit": "a" * 40,
        "workspace": str(workspace),
        "branch": f"ai/{job_id[:12]}",
        "task": {"title": "Reviewer re-check", "description": "Bounded Runtime regression"},
        "repo_analysis": {"estimated_files": 1},
        "route": _route(),
        "checkpoint": {
            "work_order": work_order,
            "project_baseline": {"revision": "v1", "source_commit": "a" * 40},
            "provider_state": {},
            "workspace_mode": "isolated_clone",
        },
        "progress": {},
    }


def _review_pack(prompt: str) -> dict:
    marker = "REVIEW_EVIDENCE_PACK: "
    line = next(item for item in prompt.splitlines() if item.startswith(marker))
    return json.loads(line[len(marker) :])


def _run_review_loop(monkeypatch, tmp_path: Path, *, resolve_on_recheck: bool):
    job_id = "job284reviewloop"
    root, workspace = _workspace(tmp_path, job_id)
    storage = FakeStorage(_row(workspace, job_id))
    router = AntiLoopRouter()
    adapter = ReviewLoopAdapter(workspace, resolve_on_recheck=resolve_on_recheck)
    engine = object.__new__(RuntimeEngine)
    engine.storage = storage
    engine.router = router
    engine.ddev = object()
    engine.workspace_root = root

    monkeypatch.setattr(
        execution_module,
        "project_config",
        lambda project_id: {"runtime": {"max_diff_bytes": 500000}, "ddev": {"enabled": False}},
    )
    monkeypatch.setattr(execution_module, "build_adapter", lambda *args: adapter)

    asyncio.run(engine.run_job(job_id))
    return storage, router, adapter


def test_developer_rebuttal_reaches_reviewer_recheck_as_bounded_advisory_evidence(
    monkeypatch, tmp_path
):
    storage, router, adapter = _run_review_loop(
        monkeypatch, tmp_path, resolve_on_recheck=True
    )

    assert storage.row["status"] == "completed"
    assert len(router.reassessments) == 2
    assert len(adapter.execution_prompts) == 2
    assert "INDEPENDENT REVIEW FINDINGS" in adapter.execution_prompts[1]
    assert "CONTACT-RATE-FIXTURE" in adapter.execution_prompts[1]

    first_pack = _review_pack(adapter.evaluator_prompts[0])
    second_prompt = adapter.evaluator_prompts[1]
    second_pack = _review_pack(second_prompt)
    assert first_pack["developer_report"] == "FIRST_DEVELOPER_REPORT"
    assert second_pack["developer_report"].startswith("DEVELOPER_REBUTTAL")
    assert second_pack["developer_report"].endswith("...[truncated]")
    assert "UNBOUNDED_REPORT_TAIL" not in second_prompt
    assert "FIRST_DEVELOPER_REPORT" not in second_prompt
    assert "RAW_PRIOR_STDERR_MUST_NOT_REACH_REVIEW" not in second_prompt
    assert "advisory repair/rebuttal evidence" in second_prompt
    assert "do not accept a developer claim automatically" in second_prompt


def test_unresolved_reviewer_finding_still_triggers_repeated_failure_circuit_breaker(
    monkeypatch, tmp_path
):
    storage, router, adapter = _run_review_loop(
        monkeypatch, tmp_path, resolve_on_recheck=False
    )

    assert len(adapter.execution_prompts) == 2
    assert len(adapter.evaluator_prompts) == 2
    assert storage.row["status"] == "blocked"
    assert storage.row["result"]["reason"] == "reassessment_stopped"
    assert storage.row["result"]["reassess"]["signals"][0].startswith("repeated_failure:")
    fingerprints = storage.row["progress"]["failure_fingerprints"]
    assert len(fingerprints) == 2
    assert fingerprints[0] == fingerprints[1]
    assert len(router.reassessments) == 2


class ProtectedBoundaryRouter(AntiLoopRouter):
    async def reassess(self, payload: dict) -> dict:
        self.reassessments.append(deepcopy(payload))
        progress = payload["progress"]
        if "major_dependency_addition" in (progress.get("important_decision_flags") or []):
            return {
                "action": "human_decision",
                "reason": "Protected dependency signal",
                "signals": ["major_dependency_addition"],
                "human_decision": {
                    "required": True,
                    "triggers": ["major_dependency_addition"],
                    "reason": "Execution discovered an important decision boundary.",
                },
            }
        if progress.get("required_checks_passed"):
            return {"action": "complete", "reason": "All required checks passed", "signals": []}
        return {"action": "continue", "reason": "Bounded repair remains available", "signals": []}


class ProtectedRepairAdapter:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.execution_prompts: list[str] = []
        self.evaluator_prompts: list[str] = []

    async def run(self, *, workspace: Path, prompt: str, mode: str, timeout: int) -> AgentRun:
        del timeout
        assert Path(workspace) == self.workspace
        if mode == "execute":
            self.execution_prompts.append(prompt)
            (self.workspace / "implementation.txt").write_text(
                f"bounded change {len(self.execution_prompts)}\n",
                encoding="utf-8",
            )
            package = self.workspace / "package.json"
            if len(self.execution_prompts) == 1:
                package.write_text(
                    '{"dependencies":{"@testing-library/react":"^16.3.3"}}\n',
                    encoding="utf-8",
                )
                output = "Added focused tests with a third-party test helper."
            else:
                package.unlink(missing_ok=True)
                output = "Removed the out-of-scope test helper and used the existing stack."
            return AgentRun(
                adapter="fake",
                model="fake-model",
                returncode=0,
                output=output,
                usage={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.000001},
            )

        assert mode == "evaluate"
        self.evaluator_prompts.append(prompt)
        if len(self.evaluator_prompts) == 1:
            output = (
                'FAIL\nREVIEW_JSON: {"verdict":"fail","summary":"Third-party test library is out of scope",'
                '"findings":[{"id":"DEP-SCOPE","severity":"medium","category":"scope",'
                '"message":"Remove the third-party frontend library",'
                '"evidence_refs":["package.json"]}],"jit_context_used":false}'
            )
        else:
            output = (
                'PASS\nREVIEW_JSON: {"verdict":"pass","summary":"Out-of-scope dependency removed",'
                '"findings":[],"jit_context_used":false}'
            )
        return AgentRun(
            adapter="fake",
            model="fake-model",
            returncode=0,
            output=output,
            usage={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.000001},
        )


def test_protected_reviewer_failure_goes_to_pm_repair_before_router_human(
    monkeypatch, tmp_path
):
    job_id = "job338protected"
    root, workspace = _workspace(tmp_path, job_id)
    row = _row(workspace, job_id)
    row["checkpoint"]["work_order"]["out_of_scope"] = ["Third-party frontend libraries"]
    storage = FakeStorage(row)
    router = ProtectedBoundaryRouter()
    adapter = ProtectedRepairAdapter(workspace)
    engine = object.__new__(RuntimeEngine)
    engine.storage = storage
    engine.router = router
    engine.ddev = object()
    engine.workspace_root = root

    pm_calls = []

    async def fake_pm_reassessment(**payload):
        pm_calls.append(deepcopy(payload))
        assert payload["trigger"]["signal"] == "protected_execution_signal"
        assert payload["trigger"]["protected_decision_flags"] == [
            "major_dependency_addition"
        ]
        assert payload["review_summary"]["verdict"] == "fail"
        return {
            "decision": {
                "action": "request_repair",
                "summary": "The dependency is removable and outside the WorkOrder.",
                "developer_message": "Remove the third-party frontend library and use the existing test stack.",
                "human_necessity": None,
                "unresolved_risks": [],
                "human_triggers": [],
            },
            "model_id": "pm-other-model",
            "provider": "other-provider",
            "usage": {"input_tokens": 5, "output_tokens": 5},
            "staffing": {"choice": {"id": "pm-other-model"}},
        }

    monkeypatch.setattr(
        execution_module,
        "project_config",
        lambda project_id: {"runtime": {"max_diff_bytes": 500000}, "ddev": {"enabled": False}},
    )
    monkeypatch.setattr(execution_module, "build_adapter", lambda *args: adapter)
    monkeypatch.setattr(execution_module, "run_pm_reassessment", fake_pm_reassessment)

    asyncio.run(engine.run_job(job_id))

    assert len(pm_calls) == 1
    assert len(adapter.execution_prompts) >= 2
    assert "PCP_PM_REASSESSMENT:" in adapter.execution_prompts[1]
    assert "Remove the third-party frontend library" in adapter.execution_prompts[1]
    assert not (workspace / "package.json").exists()
    assert storage.row["progress"]["repair_iterations"] >= 1
    assert storage.row["progress"]["important_decision_flags"] == []
    assert all(
        "major_dependency_addition"
        not in ((item.get("progress") or {}).get("important_decision_flags") or [])
        for item in router.reassessments
    )
    assert storage.row["status"] != "waiting_human"
    assert (storage.row.get("result") or {}).get("reason") != "human_decision_required"
    assert not storage.row["checkpoint"].get("pending_decision")
