from app import engine_verification as engine_verification_module
from app.engine_verification import RuntimeEngine as VerificationRuntimeEngine, _CollaborationRequested
from __future__ import annotations

import asyncio
import json
import subprocess
from copy import deepcopy
from pathlib import Path

from app.adapters.base import AgentRun
from app.collaboration import (
    CollaborationCreateRequest,
    CollaborationEvidence,
    CollaborationManager,
    CollaborationRecheckRequest,
    DeveloperCollaborationRequest,
)


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


class FakeDdev:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    async def create_workspace(self, *, job_id, project_id, ref):
        return {"workspace": str(self.workspace), "source_commit": ref}

    async def remove_workspace(self, *, job_id, project_id, workspace):
        return {"removed": True}


class FixedRouter:
    async def staff(self, payload):
        return staffing(payload, model_id="codex_terra", provider="openai")


class FailoverRouter:
    def __init__(self):
        self.calls = []

    async def staff(self, payload):
        self.calls.append(deepcopy(payload))
        if len(self.calls) == 1:
            return staffing(payload, model_id="codex_terra", provider="openai")
        return staffing(payload, model_id="antigravity_free", provider="google_antigravity")


def staffing(payload, *, model_id: str, provider: str):
    registry = {
        "codex_terra": ("codex_cli", "gpt-5.6-terra"),
        "antigravity_free": ("antigravity_host", "gemini-3.8-flash-medium"),
    }
    adapter, model = registry[model_id]
    return {
        "request_id": payload["request_id"],
        "project_id": payload["project_id"],
        "role": payload["role"],
        "profile": payload["profile"],
        "choice": {
            "id": model_id,
            "provider": provider,
            "adapter": adapter,
            "model": model,
            "reasoning_effort": "low",
        },
        "policy_version": 10,
        "registry_version": 8,
    }


class SequenceAdapter:
    def __init__(self, outputs):
        self.outputs = outputs

    async def run(self, *, workspace, prompt, mode, timeout):
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
        "id": "WO-149-recovery",
        "parent_ticket": "GH-149",
        "objective": "Keep collaboration durable and bounded",
        "baseline_revision": "mvp-v1",
        "source_references": [{"path": "docs/project/efficiency-model.md"}],
        "in_scope": ["collaboration recovery"],
        "out_of_scope": ["recursive swarm"],
        "acceptance_criteria": [{"id": "AC-1", "description": "Thread survives manager restart"}],
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
        "id": "job149recovery01",
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
                    "max_provider_failovers": 2,
                    "max_wall_time_minutes": 60,
                    "hard_cost_usd": 10.0,
                },
            },
        },
        "progress": {
            "model_calls": 0,
            "provider_failovers": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "elapsed_minutes": 0.0,
            "cost_usd": 0.0,
            "repair_iterations": 0,
        },
    }


def evidence():
    return [CollaborationEvidence(ref="README.md", summary="Baseline evidence")]


def test_unresolved_thread_survives_manager_recreation_and_can_recheck(tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        storage = FakeStorage(row(workspace))
        first_adapter = SequenceAdapter(
            [{"recommendation": "Check one more invariant", "unresolved": True}]
        )
        first_manager = CollaborationManager(
            storage,
            router=FixedRouter(),
            ddev=FakeDdev(workspace),
            adapter_builder=lambda *args: first_adapter,
        )
        first = await first_manager.create(
            storage.row["id"],
            CollaborationCreateRequest(
                role="consultant",
                topic="invariant",
                objective="challenge the implementation invariant",
                question="Is one invariant missing?",
                evidence=evidence(),
            ),
        )
        assert first.status == "open"
        assert first.rounds == 1

        # Simulate Runtime recreation: the new manager has no in-memory thread
        # state and must recover everything from the durable job checkpoint.
        second_adapter = SequenceAdapter(
            [{"recommendation": "The added invariant resolves the concern", "unresolved": False}]
        )
        second_manager = CollaborationManager(
            storage,
            router=FixedRouter(),
            ddev=FakeDdev(workspace),
            adapter_builder=lambda *args: second_adapter,
        )
        recovered = second_manager.get(storage.row["id"], first.id)
        assert recovered.rounds == 1
        assert recovered.response.recommendation == "Check one more invariant"

        final = await second_manager.recheck(
            storage.row["id"],
            first.id,
            CollaborationRecheckRequest(
                developer_response="Added the missing invariant.",
                evidence=[CollaborationEvidence(ref="runtime:current_diff", summary="Invariant added")],
            ),
        )
        assert final.status == "resolved"
        assert final.rounds == 2
        assert storage.row["progress"]["repair_iterations"] == 0

    asyncio.run(scenario())


def test_provider_failure_restafs_same_logical_role_without_engineering_repair(tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        storage = FakeStorage(row(workspace))
        router = FailoverRouter()
        adapter = SequenceAdapter(
            [
                AgentRun(
                    adapter="fake",
                    model="fake-model",
                    returncode=75,
                    output="quota exhausted",
                    usage={"input_tokens": 4, "output_tokens": 1},
                    failure_kind="quota_exhausted",
                    failure_message="quota exhausted",
                ),
                {"recommendation": "Fallback reviewer completed the consultation", "unresolved": False},
            ]
        )
        manager = CollaborationManager(
            storage,
            router=router,
            ddev=FakeDdev(workspace),
            adapter_builder=lambda *args: adapter,
        )

        result = await manager.create(
            storage.row["id"],
            CollaborationCreateRequest(
                role="reviewer",
                topic="review",
                objective="review with bounded provider recovery",
                question="Is the implementation evidence sufficient?",
                evidence=evidence(),
            ),
        )

        assert result.status == "resolved"
        assert [call["role"] for call in router.calls] == ["reviewer", "reviewer"]
        progress = storage.row["progress"]
        assert progress["collaboration_model_calls"] == 2
        assert progress["collaboration_provider_recoveries"] == 1
        assert progress["provider_failovers"] == 1
        assert progress["repair_iterations"] == 0
        provider_state = storage.row["checkpoint"]["provider_state"]
        assert provider_state["quota:model:codex_terra"]["available"] is False

    asyncio.run(scenario())


def test_resolved_collaboration_continues_in_same_worker_without_enqueue(monkeypatch, tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        current = row(workspace)
        current["status"] = "queued"
        storage = FakeStorage(current)
        engine = object.__new__(VerificationRuntimeEngine)
        engine.storage = storage
        engine.collaboration = None

        request = DeveloperCollaborationRequest(
            action="consult",
            role="security_specialist",
            topic="trust boundary",
            objective="review bounded security behavior",
            question="Is the repair acceptable?",
            evidence=evidence(),
        )
        requested = _CollaborationRequested(
            request,
            {
                "changed_file_count": 1,
                "changed_files": ["src/Security/Access.php"],
                "diff": "diff",
                "diff_hash": "diff-1",
            },
        )
        parent_calls = []
        enqueue_calls = []

        async def fake_parent_run(self, job_id):
            parent_calls.append(job_id)
            if len(parent_calls) == 1:
                raise requested
            storage.update(job_id, status="completed")

        async def fake_handle(job_id, received):
            assert received is requested
            storage.update(job_id, status="queued")
            return True

        async def fake_enqueue(job_id):
            enqueue_calls.append(job_id)

        monkeypatch.setattr(
            engine_verification_module.ExecutionRuntimeEngine,
            "run_job",
            fake_parent_run,
        )
        engine._handle_collaboration_request = fake_handle
        engine.enqueue = fake_enqueue
        engine._runtime_event = lambda *args, **kwargs: None

        await VerificationRuntimeEngine.run_job(engine, current["id"])

        assert parent_calls == [current["id"], current["id"]]
        assert enqueue_calls == []
        assert storage.row["status"] == "completed"

    asyncio.run(scenario())


def test_blocked_collaboration_does_not_continue_parent_worker(monkeypatch, tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        current = row(workspace)
        current["status"] = "queued"
        storage = FakeStorage(current)
        engine = object.__new__(VerificationRuntimeEngine)
        engine.storage = storage
        engine.collaboration = None

        request = DeveloperCollaborationRequest(
            action="consult",
            role="security_specialist",
            topic="trust boundary",
            objective="review bounded security behavior",
            question="Is the repair acceptable?",
            evidence=evidence(),
        )
        requested = _CollaborationRequested(
            request,
            {
                "changed_file_count": 1,
                "changed_files": ["src/Security/Access.php"],
                "diff": "diff",
                "diff_hash": "diff-1",
            },
        )
        parent_calls = []

        async def fake_parent_run(self, job_id):
            parent_calls.append(job_id)
            raise requested

        async def fake_handle(job_id, received):
            storage.update(job_id, status="blocked")
            return False

        monkeypatch.setattr(
            engine_verification_module.ExecutionRuntimeEngine,
            "run_job",
            fake_parent_run,
        )
        engine._handle_collaboration_request = fake_handle
        engine._runtime_event = lambda *args, **kwargs: None

        await VerificationRuntimeEngine.run_job(engine, current["id"])

        assert parent_calls == [current["id"]]
        assert storage.row["status"] == "blocked"

    asyncio.run(scenario())
