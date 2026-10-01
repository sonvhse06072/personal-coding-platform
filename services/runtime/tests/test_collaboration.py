from __future__ import annotations

import asyncio
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters.base import AgentRun
from app.collaboration import (
    CollaborationCreateRequest,
    CollaborationEvidence,
    CollaborationManager,
    CollaborationRecheckRequest,
)
from app.engine_verification import RuntimeEngine as VerificationRuntimeEngine


class FakeStorage:
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


class FakeRouter:
    def __init__(self):
        self.calls = []

    async def staff(self, payload):
        self.calls.append(deepcopy(payload))
        return {
            "request_id": payload["request_id"],
            "project_id": payload["project_id"],
            "role": payload["role"],
            "profile": payload["profile"],
            "choice": {
                "id": "codex_terra",
                "provider": "openai",
                "adapter": "codex_cli",
                "model": "gpt-5.6-terra",
                "reasoning_effort": "low",
            },
            "policy_version": 10,
            "registry_version": 8,
        }


class FakeDdev:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.created = []
        self.removed = []

    async def create_workspace(self, *, job_id, project_id, ref):
        self.created.append((job_id, project_id, ref))
        return {"workspace": str(self.workspace), "source_commit": ref}

    async def remove_workspace(self, *, job_id, project_id, workspace):
        self.removed.append((job_id, project_id, workspace))
        return {"removed": True}


class SequenceAdapter:
    def __init__(self, outputs, workspace_mutation: str | None = None):
        self.outputs = outputs
        self.workspace_mutation = workspace_mutation

    async def run(self, *, workspace, prompt, mode, timeout):
        if self.workspace_mutation:
            (workspace / self.workspace_mutation).write_text("mutated", encoding="utf-8")
        value = self.outputs.pop(0)
        if isinstance(value, AgentRun):
            return value
        return AgentRun(
            adapter="fake",
            model="fake-model",
            returncode=0,
            output=json.dumps(value),
            usage={"input_tokens": 10, "output_tokens": 5},
        )


def git_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    (workspace / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=workspace, check=True)
    return workspace


def work_order():
    return {
        "id": "WO-149",
        "parent_ticket": "GH-149",
        "objective": "Implement bounded collaboration",
        "baseline_revision": "mvp-v1",
        "source_references": [{"path": "docs/project/efficiency-model.md"}],
        "in_scope": ["bounded collaboration"],
        "out_of_scope": ["unrestricted agent chat"],
        "acceptance_criteria": [{"id": "AC-1", "description": "Collaboration is bounded"}],
        "constraints": ["single writer"],
        "requested_role": "developer",
        "verification": {
            "intermediate_phases": ["targeted_tests"],
            "required_phases": ["static_analysis"],
        },
        "risk": {"level": "standard", "flags": []},
        "budget": {"mode": "adaptive", "max_profile": "standard"},
        "dependencies": [],
    }


def row(workspace: Path):
    return {
        "id": "job1490000000000",
        "project_id": "demo",
        "status": "executing",
        "source_commit": "a" * 40,
        "workspace": str(workspace),
        "checkpoint": {"work_order": work_order(), "provider_state": {}},
        "route": {
            "dimensions": {
                "ambiguity": 45,
                "architecture_impact": 30,
                "verification_difficulty": 60,
                "risk": 45,
                "context_requirement": 60,
                "novelty": 40,
                "reasoning_requirement": 70,
            },
            "strategy": {
                "profile": "standard",
                "budget": {
                    "max_model_calls": 20,
                    "max_input_tokens": 100000,
                    "max_output_tokens": 20000,
                    "max_wall_time_minutes": 60,
                    "hard_cost_usd": 10.0,
                },
            },
        },
        "progress": {
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "elapsed_minutes": 0.0,
            "cost_usd": 0.0,
            "repair_iterations": 0,
            "diff_hashes": [],
        },
    }


def evidence():
    return [CollaborationEvidence(ref="tests/example.py", summary="Existing test pattern relevant to the question")]


def test_two_round_dialogue_hands_unresolved_disagreement_to_pm(tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        storage = FakeStorage(row(workspace))
        adapter = SequenceAdapter(
            [
                {"recommendation": "Add a focused recovery assertion", "risks": [], "suggested_tests": ["focused recovery test"], "unresolved": True},
                {"recommendation": "The remaining disagreement needs PM disposition", "risks": ["contract interpretation"], "suggested_tests": [], "unresolved": True},
            ]
        )
        manager = CollaborationManager(
            storage,
            router=FakeRouter(),
            ddev=FakeDdev(workspace),
            adapter_builder=lambda *args: adapter,
        )

        first = await manager.create(
            storage.row["id"],
            CollaborationCreateRequest(
                role="test_engineer",
                topic="verification",
                objective="challenge the focused verification design",
                question="Which focused assertion is missing?",
                evidence=evidence(),
            ),
        )
        assert first.status == "open"
        assert first.rounds == 1
        assert [item["type"] for item in first.trace] == ["consult_request", "structured_response"]
        assert all(len(item["hash"]) == 64 for item in first.trace)

        second = await manager.recheck(
            storage.row["id"],
            first.id,
            CollaborationRecheckRequest(
                developer_response="Added the recovery assertion and kept the scope unchanged.",
                evidence=[CollaborationEvidence(ref="runtime:current_diff", summary="Focused assertion added")],
            ),
        )
        assert second.status == "pm_handoff"
        assert second.rounds == 2
        assert second.pm_handoff["reason"] == "collaboration_round_limit_with_unresolved_disagreement"
        assert len(second.trace) == 4
        assert storage.row["progress"]["repair_iterations"] == 0
        assert storage.row["progress"]["collaboration_model_calls"] == 2

        with pytest.raises(RuntimeError, match="cannot be re-checked"):
            await manager.recheck(
                storage.row["id"],
                first.id,
                CollaborationRecheckRequest(developer_response="third round", evidence=[]),
            )

    asyncio.run(scenario())


def test_collaborator_cannot_become_second_writer(tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        storage = FakeStorage(row(workspace))
        adapter = SequenceAdapter(
            [{"recommendation": "irrelevant", "unresolved": False}],
            workspace_mutation="second-writer.txt",
        )
        manager = CollaborationManager(
            storage,
            router=FakeRouter(),
            ddev=FakeDdev(workspace),
            adapter_builder=lambda *args: adapter,
        )

        with pytest.raises(RuntimeError, match="modified its disposable workspace"):
            await manager.create(
                storage.row["id"],
                CollaborationCreateRequest(
                    role="reviewer",
                    topic="review",
                    objective="review without writing",
                    question="Is the evidence sufficient?",
                    evidence=evidence(),
                ),
            )
        thread = manager.list(storage.row["id"])[0]
        assert thread.status == "open"
        assert thread.rounds == 0
        assert storage.row["progress"]["repair_iterations"] == 0

    asyncio.run(scenario())


def test_invalid_collaboration_staffing_does_not_precharge_or_invoke(tmp_path):
    class InvalidStaffingRouter:
        async def staff(self, payload: dict) -> dict:
            return {
                "request_id": payload["request_id"],
                "project_id": payload["project_id"],
                "role": payload["role"],
                "profile": payload["profile"],
                "choice": {
                    "id": "antigravity_free",
                    "provider": "google_antigravity",
                    "adapter": "antigravity_host",
                    "model": "gemini-3.8-flash-medium",
                    "reasoning_effort": "max",
                },
                "policy_version": 19,
                "registry_version": 10,
            }

    async def scenario():
        workspace = git_workspace(tmp_path)
        storage = FakeStorage(row(workspace))
        adapter = SequenceAdapter(
            [{"recommendation": "must not run", "unresolved": False}]
        )
        manager = CollaborationManager(
            storage,
            router=InvalidStaffingRouter(),
            ddev=FakeDdev(workspace),
            adapter_builder=lambda *args: adapter,
        )

        with pytest.raises(RuntimeError, match="unsupported"):
            await manager.create(
                storage.row["id"],
                CollaborationCreateRequest(
                    role="reviewer",
                    topic="capability",
                    objective="reject an invalid local choice",
                    question="Should this call run?",
                    evidence=evidence(),
                ),
            )

        assert storage.row["progress"]["model_calls"] == 0
        assert "collaboration_model_calls" not in storage.row["progress"]
        assert len(adapter.outputs) == 1

    asyncio.run(scenario())


def test_adaptive_create_runs_above_static_model_call_limit(tmp_path) -> None:
    async def scenario():
        workspace = git_workspace(tmp_path)
        current = row(workspace)
        current["route"]["strategy"]["budget_mode"] = "adaptive"
        current["progress"].update(
            {
                "model_calls": 73,
                "input_tokens": 500000,
                "output_tokens": 50000,
                "elapsed_minutes": 190.0,
                "cost_usd": 1.0,
            }
        )
        storage = FakeStorage(current)
        adapter = SequenceAdapter(
            [
                {
                    "recommendation": "Security consultation completed.",
                    "risks": [],
                    "suggested_tests": ["Run the focused access-control test."],
                    "unresolved": False,
                }
            ]
        )
        manager = CollaborationManager(
            storage,
            router=FakeRouter(),
            ddev=FakeDdev(workspace),
            adapter_builder=lambda *args: adapter,
        )

        result = await manager.create(
            current["id"],
            CollaborationCreateRequest(
                role="security_specialist",
                topic="trust boundary",
                objective="review the bounded security-sensitive change",
                question="Does the implementation preserve the approved trust boundary?",
                evidence=evidence(),
                deadline_seconds=360,
            ),
        )

        assert result.status == "resolved"
        assert result.participant_role == "security_specialist"
        assert storage.row["progress"]["model_calls"] == 74
        assert storage.row["progress"]["collaboration_model_calls"] == 1
        assert len(adapter.outputs) == 0

    asyncio.run(scenario())


def test_adaptive_collaboration_ignores_static_cumulative_counters() -> None:
    current = row(Path("/tmp/unused"))
    current["route"]["strategy"]["budget_mode"] = "adaptive"
    current["progress"].update(
        {
            "model_calls": 73,
            "input_tokens": 500000,
            "output_tokens": 50000,
            "elapsed_minutes": 190.0,
            "cost_usd": 1.0,
        }
    )

    CollaborationManager._ensure_budget(current)
    assert CollaborationManager._timeout_seconds(current, 360) == 360


def test_adaptive_collaboration_still_enforces_hard_cost() -> None:
    current = row(Path("/tmp/unused"))
    current["route"]["strategy"]["budget_mode"] = "adaptive"
    current["progress"]["model_calls"] = 73
    current["progress"]["elapsed_minutes"] = 190.0
    current["progress"]["cost_usd"] = 10.0

    with pytest.raises(RuntimeError, match="hard-cost emergency ceiling"):
        CollaborationManager._ensure_budget(current)


def test_legacy_collaboration_preserves_fixed_counter_and_wall_limits() -> None:
    current = row(Path("/tmp/unused"))
    current["route"]["strategy"]["budget_mode"] = "legacy_hard"
    current["progress"]["model_calls"] = 20

    with pytest.raises(RuntimeError, match="model-call emergency ceiling"):
        CollaborationManager._ensure_budget(current)

    current["progress"]["model_calls"] = 0
    current["progress"]["elapsed_minutes"] = 59.95
    with pytest.raises(RuntimeError, match="Insufficient job wall-time"):
        CollaborationManager._timeout_seconds(current, 360)


def test_adaptive_collaboration_timeout_remains_per_round_bounded() -> None:
    current = row(Path("/tmp/unused"))
    current["route"]["strategy"]["budget_mode"] = "adaptive"
    current["progress"]["elapsed_minutes"] = 999.0

    assert CollaborationManager._timeout_seconds(current, 30) == 30
    assert CollaborationManager._timeout_seconds(current, 360) == 360
    assert CollaborationManager._timeout_seconds(current, 5000) == 900


def test_recursive_collaborator_fanout_is_rejected():
    with pytest.raises(ValidationError, match="consultant-to-consultant fanout"):
        CollaborationCreateRequest(
            role="debugger",
            topic="failure",
            objective="debug",
            question="why?",
            evidence=evidence(),
            initiator_role="reviewer",
        )


def test_control_artifact_is_removed_before_real_diff_is_verified(tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        storage = FakeStorage(row(workspace))
        engine = object.__new__(VerificationRuntimeEngine)
        engine.storage = storage

        (workspace / "README.md").write_text("baseline\nreal change\n", encoding="utf-8")
        request_path = workspace / ".pcp-collaboration-request.json"
        request_path.write_text(
            json.dumps(
                {
                    "action": "consult",
                    "role": "consultant",
                    "topic": "pattern",
                    "objective": "check the repository pattern",
                    "question": "Does this follow the existing pattern?",
                    "evidence": [{"ref": "README.md", "summary": "Changed file"}],
                }
            ),
            encoding="utf-8",
        )
        progress = storage.row["progress"]
        progress["diff_hashes"] = ["dirty-control-artifact-hash"]

        consumed = await engine._consume_collaboration_request(
            job_id=storage.row["id"],
            workspace=workspace,
            project={"runtime": {"max_diff_bytes": 100000}},
            progress=progress,
        )

        assert consumed is not None
        assert consumed.request.role == "consultant"
        assert not request_path.exists()
        assert consumed.clean_diff["changed_file_count"] == 1
        assert ".pcp-collaboration-request.json" not in consumed.clean_diff["diff"]
        assert progress["material_change_present"] is True
        assert progress["diff_hashes"][-1] == consumed.clean_diff["diff_hash"]

    asyncio.run(scenario())


def test_malformed_control_artifact_fails_closed(tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        storage = FakeStorage(row(workspace))
        engine = object.__new__(VerificationRuntimeEngine)
        engine.storage = storage
        (workspace / ".pcp-collaboration-request.json").write_text("not-json", encoding="utf-8")

        with pytest.raises(RuntimeError, match="valid JSON object"):
            await engine._consume_collaboration_request(
                job_id=storage.row["id"],
                workspace=workspace,
                project={"runtime": {"max_diff_bytes": 100000}},
                progress=storage.row["progress"],
            )

    asyncio.run(scenario())



def test_direct_collaborator_reuses_owning_workspace_without_branch_clone(tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        job = row(workspace)
        job["checkpoint"]["workspace_mode"] = "direct"
        storage = FakeStorage(job)
        ddev = FakeDdev(tmp_path / "should-not-be-used")
        adapter = SequenceAdapter(
            [{"recommendation": "Direct workspace is safe to review", "unresolved": False}]
        )
        manager = CollaborationManager(
            storage,
            router=FakeRouter(),
            ddev=ddev,
            adapter_builder=lambda *args: adapter,
        )

        result = await manager.create(
            storage.row["id"],
            CollaborationCreateRequest(
                role="reviewer",
                topic="review",
                objective="review current direct workspace without writing",
                question="Is the current direct diff consistent?",
                evidence=evidence(),
            ),
        )

        assert result.status == "resolved"
        assert ddev.created == []
        assert ddev.removed == []
        assert workspace.exists()
        assert subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip() == ""

    asyncio.run(scenario())
