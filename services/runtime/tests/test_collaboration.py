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
                "adapter": "fake",
                "model": "fake-model",
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
