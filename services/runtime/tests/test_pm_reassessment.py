from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.adapters.base import AgentRun
from app.pm_reassessment import (
    PMReassessmentDecision,
    changed_file_reassessment_state,
    has_pm_changed_file_authorization,
    run_pm_reassessment,
)


class FakeRouter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def staff(self, payload: dict) -> dict:
        self.calls.append(payload)
        assert payload["role"] == "product_manager"
        assert payload["exclude_model_ids"] == ["developer-model"]
        return {
            "request_id": payload["request_id"],
            "project_id": payload["project_id"],
            "role": "product_manager",
            "profile": payload["profile"],
            "choice": {
                "id": "pm-model",
                "provider": "other-provider",
                "adapter": "fake",
                "model": "pm-model-name",
                "reasoning_effort": "low",
                "score": 0.9,
                "predicted_success": 0.9,
                "reasons": ["test"],
            },
            "rejected_candidates": {
                "developer-model": ["model excluded for role separation"],
            },
            "policy_version": 17,
            "registry_version": 8,
        }


class FakeDdev:
    def __init__(self, origin: Path, root: Path) -> None:
        self.origin = origin
        self.root = root
        self.created: list[dict] = []
        self.removed: list[dict] = []

    async def create_workspace(self, **payload) -> dict:
        self.created.append(payload)
        destination = self.root / "pm-review"
        if destination.exists():
            shutil.rmtree(destination)
        subprocess.run(
            ["git", "clone", "-q", str(self.origin), str(destination)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(destination), "checkout", "-q", payload["ref"]],
            check=True,
        )
        return {
            "workspace": str(destination),
            "source_commit": payload["ref"],
            "workspace_mode": "isolated_clone",
        }

    async def remove_workspace(self, **payload) -> dict:
        self.removed.append(payload)
        shutil.rmtree(Path(payload["workspace"]), ignore_errors=True)
        return {"removed": True}


class FakeAdapter:
    def __init__(self, output: dict, *, mutate: bool = False) -> None:
        self.output = output
        self.mutate = mutate
        self.calls: list[dict] = []

    async def run(self, **payload) -> AgentRun:
        self.calls.append(payload)
        if self.mutate:
            Path(payload["workspace"], "pm-mutation.txt").write_text(
                "forbidden",
                encoding="utf-8",
            )
        return AgentRun(
            adapter="fake",
            model="pm-model-name",
            returncode=0,
            output=json.dumps(self.output),
            usage={"input_tokens": 120, "output_tokens": 40},
        )


def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / "component.tsx").write_text("export const A = 1;\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "component.tsx"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "base"], check=True)
    (root / "component.tsx").write_text("export const A = 2;\n", encoding="utf-8")
    return root


def strategy() -> dict:
    return {
        "budget_mode": "adaptive",
        "adaptive_budget": {
            "enabled": True,
            "dimensions": {
                "max_changed_files": {
                    "estimate": 6,
                    "working_target": 8,
                    "emergency_limit": 16,
                }
            },
        },
    }


def test_changed_file_working_target_requires_pm_only_inside_emergency_headroom() -> None:
    assert changed_file_reassessment_state(strategy(), changed_files=8) is None
    assert changed_file_reassessment_state(strategy(), changed_files=9) == {
        "used": 9,
        "working_target": 8,
        "emergency_limit": 16,
    }
    assert changed_file_reassessment_state(strategy(), changed_files=16) == {
        "used": 16,
        "working_target": 8,
        "emergency_limit": 16,
    }
    assert changed_file_reassessment_state(strategy(), changed_files=17) is None


def test_pm_authorization_is_exact_diff_bound() -> None:
    checkpoint = {
        "pm_reassessment_authorizations": [
            {
                "signal": "changed_file_working_target_exceeded",
                "diff_hash": "abc",
                "used": 11,
                "emergency_limit": 16,
            }
        ]
    }

    assert has_pm_changed_file_authorization(
        checkpoint,
        diff_hash="abc",
        used=11,
    )
    assert not has_pm_changed_file_authorization(
        checkpoint,
        diff_hash="different",
        used=11,
    )
    assert not has_pm_changed_file_authorization(
        checkpoint,
        diff_hash="abc",
        used=12,
    )


def test_pm_reassessment_uses_different_model_and_keeps_workspace_read_only(tmp_path) -> None:
    root = workspace(tmp_path)
    router = FakeRouter()
    ddev = FakeDdev(root, tmp_path)
    source_commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    adapter = FakeAdapter(
        {
            "action": "approve_continue",
            "summary": "All changed files remain inside the approved frontend WorkOrder.",
            "developer_message": None,
            "unresolved_risks": [],
            "human_triggers": [],
        }
    )

    result = asyncio.run(
        run_pm_reassessment(
            router=router,
            ddev=ddev,
            workspace=root,
            job_id="job-1",
            project_id="demo",
            source_commit=source_commit,
            profile="standard",
            current_executor={"id": "developer-model"},
            provider_state={},
            work_order={"id": "WO-1", "in_scope": ["frontend only"]},
            baseline={"revision": "v1"},
            trigger={
                "signal": "changed_file_working_target_exceeded",
                "used": 9,
                "working_target": 8,
                "emergency_limit": 16,
            },
            diff={
                "changed_file_count": 9,
                "changed_files": ["component.tsx"],
                "diff_stat": "1 file changed",
                "diff_hash": "abc",
            },
            verification={"passed": True},
            review_summary={"verdict": "pass"},
            developer_report="Implemented colocated component tests.",
            decision_context={},
            max_diff_bytes=500000,
            timeout_seconds=60,
            adapter_builder=lambda *_args: adapter,
        )
    )

    assert result["model_id"] == "pm-model"
    assert result["decision"]["action"] == "approve_continue"
    assert router.calls[0]["exclude_model_ids"] == ["developer-model"]
    assert len(adapter.calls) == 1
    assert "Primary Developer" in adapter.calls[0]["prompt"]
    assert Path(adapter.calls[0]["workspace"]) != root
    assert len(ddev.created) == 1
    assert len(ddev.removed) == 1


def test_pm_reassessment_fails_closed_if_pm_mutates_workspace(tmp_path) -> None:
    root = workspace(tmp_path)
    router = FakeRouter()
    ddev = FakeDdev(root, tmp_path)
    source_commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    adapter = FakeAdapter(
        {
            "action": "approve_continue",
            "summary": "Looks fine.",
            "developer_message": None,
            "unresolved_risks": [],
            "human_triggers": [],
        },
        mutate=True,
    )

    with pytest.raises(RuntimeError, match="modified its read-only review workspace"):
        asyncio.run(
            run_pm_reassessment(
                router=router,
                ddev=ddev,
                workspace=root,
                job_id="job-1",
                project_id="demo",
                source_commit=source_commit,
                profile="standard",
                current_executor={"id": "developer-model"},
                provider_state={},
                work_order={"id": "WO-1"},
                baseline={"revision": "v1"},
                trigger={
                    "signal": "changed_file_working_target_exceeded",
                    "used": 9,
                    "working_target": 8,
                    "emergency_limit": 16,
                },
                diff={
                    "changed_file_count": 9,
                    "changed_files": ["component.tsx"],
                    "diff_stat": "1 file changed",
                    "diff_hash": "abc",
                },
                verification={"passed": True},
                review_summary=None,
                developer_report=None,
                decision_context={},
                max_diff_bytes=500000,
                timeout_seconds=60,
                adapter_builder=lambda *_args: adapter,
            )
        )


def test_pm_mutation_never_changes_developer_workspace(tmp_path) -> None:
    root = workspace(tmp_path)
    developer_before = (root / "component.tsx").read_text(encoding="utf-8")
    router = FakeRouter()
    ddev = FakeDdev(root, tmp_path)
    source_commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    adapter = FakeAdapter(
        {
            "action": "approve_continue",
            "summary": "Would approve.",
            "developer_message": None,
            "unresolved_risks": [],
            "human_triggers": [],
        },
        mutate=True,
    )

    with pytest.raises(RuntimeError):
        asyncio.run(
            run_pm_reassessment(
                router=router,
                ddev=ddev,
                workspace=root,
                job_id="job-2",
                project_id="demo",
                source_commit=source_commit,
                profile="standard",
                current_executor={"id": "developer-model"},
                provider_state={},
                work_order={"id": "WO-1"},
                baseline={"revision": "v1"},
                trigger={
                    "signal": "changed_file_working_target_exceeded",
                    "used": 9,
                    "working_target": 8,
                    "emergency_limit": 16,
                },
                diff={
                    "changed_file_count": 9,
                    "changed_files": ["component.tsx"],
                    "diff_stat": "1 file changed",
                    "diff_hash": "abc",
                },
                verification={"passed": True},
                review_summary=None,
                developer_report=None,
                decision_context={},
                max_diff_bytes=500000,
                timeout_seconds=60,
                adapter_builder=lambda *_args: adapter,
            )
        )

    assert (root / "component.tsx").read_text(encoding="utf-8") == developer_before
    assert not (root / "pm-mutation.txt").exists()
    assert len(ddev.removed) == 1


def test_pm_approval_cannot_hide_unresolved_risk() -> None:
    with pytest.raises(ValueError, match="cannot retain unresolved risks"):
        PMReassessmentDecision.model_validate(
            {
                "action": "approve_continue",
                "summary": "Approve despite unresolved concern.",
                "developer_message": None,
                "unresolved_risks": ["Scope evidence is incomplete."],
                "human_triggers": [],
            }
        )


def test_pm_human_escalation_is_limited_to_known_owner_boundaries() -> None:
    with pytest.raises(ValueError, match="unsupported Human Owner triggers"):
        PMReassessmentDecision.model_validate(
            {
                "action": "human_decision",
                "summary": "Ask owner for an ordinary implementation preference.",
                "developer_message": None,
                "unresolved_risks": [],
                "human_triggers": ["ordinary_implementation_preference"],
            }
        )
