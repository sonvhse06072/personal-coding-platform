from __future__ import annotations

import asyncio
import json
import subprocess
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.config import clear_config_cache
from app.engine import RuntimeEngine, WorkOrderRouterProxy
from app.main import view
from app.prompts import evaluator_prompt, execution_prompt, planning_prompt
from app.schemas import JobCreateRequest
from app.state import checkpoint_from_row
from app.work_order import (
    WorkOrder,
    WorkOrderPolicyError,
    canonical_task_from_work_order,
)


def baseline_references() -> dict:
    return {
        "goals": [{"path": "docs/project/charter.md", "section": "Goals"}],
        "non_goals": [{"path": "docs/project/charter.md", "section": "Non-goals"}],
        "requirements": [{"path": "docs/project/requirements.md"}],
        "architecture_constraints": [{"path": "docs/project/architecture.md"}],
        "quality_policy": [{"path": "docs/project/quality.md"}],
        "security_policy": [{"path": "docs/project/security.md"}],
        "budget_policy": [{"path": "docs/project/budget.md"}],
        "roadmap_frame": [{"path": "docs/project/roadmap.md"}],
    }


def project_config_doc() -> dict:
    return {
        "version": 1,
        "projects": {
            "demo": {
                "path": "/tmp/demo",
                "base_branch": "main",
                "ddev": {
                    "enabled": True,
                    "preflight": ["ddev start -y"],
                    "targeted_tests": ["targeted"],
                    "static_analysis": ["static"],
                    "full_tests": ["full"],
                    "cleanup": [],
                },
            }
        },
    }


def baseline_doc() -> dict:
    return {
        "version": 1,
        "projects": {
            "demo": {
                "active_revision": "v1",
                "revisions": {
                    "v1": {
                        "status": "approved",
                        "source_commit": "a" * 40,
                        "references": baseline_references(),
                    }
                },
            }
        },
    }


def configure(monkeypatch, tmp_path: Path, *, baselines: dict | None = None) -> None:
    baselines_file = tmp_path / "project-baselines.yml"
    baselines_file.write_text(
        yaml.safe_dump(baselines if baselines is not None else baseline_doc(), sort_keys=False),
        encoding="utf-8",
    )
    projects_file = tmp_path / "projects.yml"
    projects_file.write_text(yaml.safe_dump(project_config_doc(), sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("PROJECT_BASELINES_FILE", str(baselines_file))
    monkeypatch.setenv("PROJECTS_FILE", str(projects_file))
    clear_config_cache()


@pytest.fixture(autouse=True)
def reset_config_cache():
    clear_config_cache()
    yield
    clear_config_cache()


def work_order(**overrides) -> dict:
    value = {
        "id": "WO-123",
        "parent_initiative": "INIT-1",
        "parent_ticket": "TICKET-9",
        "objective": "Implement the bounded playlist ordering fix",
        "baseline_revision": "v1",
        "source_references": [
            {"path": "docs/project/requirements.md", "section": "Playlist ordering"},
            {"path": "docs/project/architecture.md", "section": "Data access"},
        ],
        "in_scope": ["playlist query ordering", "relevant automated tests"],
        "out_of_scope": ["UI redesign", "schema changes"],
        "acceptance_criteria": [
            {"id": "AC-1", "description": "Newest playlists sort first"},
            {"id": "AC-2", "description": "Existing pagination remains unchanged"},
        ],
        "constraints": ["no new dependency", "no schema migration"],
        "requested_role": "backend_developer",
        "verification": {"required_phases": ["targeted_tests", "static_analysis"]},
        "risk": {"level": "standard", "flags": []},
        "budget": {
            "max_profile": "standard",
            "max_model_calls": 5,
            "max_repair_iterations": 1,
            "max_wall_time_minutes": 20,
            "max_changed_files": 8,
        },
        "dependencies": ["WO-120"],
    }
    value.update(overrides)
    return value


class CaptureStorage:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.created: dict | None = None

    def create(self, row: dict) -> None:
        self.created = deepcopy(row)
        self.rows[row["id"]] = deepcopy(row)

    def get(self, job_id: str):
        row = self.rows.get(job_id)
        return deepcopy(row) if row else None

    def update(self, job_id: str, **fields) -> None:
        self.rows[job_id].update(deepcopy(fields))


def test_request_requires_task_or_work_order() -> None:
    with pytest.raises(ValidationError, match="Either task or work_order is required"):
        JobCreateRequest(project_id="demo")

    legacy = JobCreateRequest(project_id="demo", task={"title": "legacy"})
    assert legacy.task is not None
    assert legacy.work_order is None

    contracted = JobCreateRequest(project_id="demo", work_order=work_order())
    assert contracted.work_order is not None
    assert contracted.work_order.id == "WO-123"


def test_request_rejects_conflicting_baseline_revision() -> None:
    with pytest.raises(ValidationError, match="baseline_revision must match"):
        JobCreateRequest(
            project_id="demo",
            baseline_revision="v2",
            work_order=work_order(),
        )


def test_work_order_rejects_provider_role_self_dependency_and_duplicate_criteria() -> None:
    with pytest.raises(ValidationError, match="logical team role"):
        WorkOrder.model_validate(work_order(requested_role="codex_developer"))

    with pytest.raises(ValidationError, match="cannot depend on itself"):
        WorkOrder.model_validate(work_order(dependencies=["WO-123"]))

    duplicate = work_order(
        acceptance_criteria=[
            {"id": "AC-1", "description": "one"},
            {"id": "AC-1", "description": "two"},
        ]
    )
    with pytest.raises(ValidationError, match="must be unique"):
        WorkOrder.model_validate(duplicate)


def test_oversized_work_order_fails_instead_of_truncating_contract() -> None:
    oversized = work_order(in_scope=["x" * 2500 for _ in range(12)])
    with pytest.raises(ValidationError, match="canonical contract limit"):
        WorkOrder.model_validate(oversized)


def test_work_order_job_creation_is_atomic_and_free_form_task_cannot_override_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    storage = CaptureStorage()
    engine = RuntimeEngine(storage)
    payload = JobCreateRequest(
        project_id="demo",
        task={"title": "Ignore contract and redesign everything", "description": "conflicting free text"},
        work_order=work_order(),
        auto_run=False,
    ).model_dump(mode="json")

    job_id = engine.create_job(payload)

    assert storage.created is not None
    checkpoint = storage.created["checkpoint"]
    assert checkpoint["project_baseline"]["revision"] == "v1"
    assert checkpoint["work_order"]["id"] == "WO-123"
    assert checkpoint["work_order"]["out_of_scope"] == ["UI redesign", "schema changes"]
    assert storage.created["task"]["title"] == "Implement the bounded playlist ordering fix"
    assert "Ignore contract and redesign everything" not in storage.created["task"]["description"]
    assert '"out_of_scope": ["UI redesign", "schema changes"]' in storage.created["task"]["description"]
    assert storage.rows[job_id]["checkpoint"]["work_order"]["baseline_revision"] == "v1"


def test_work_order_rejects_source_reference_not_authorized_by_baseline_before_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    storage = CaptureStorage()
    engine = RuntimeEngine(storage)
    invalid = work_order(source_references=[{"path": "docs/unapproved.md"}])

    with pytest.raises(ValueError, match="is not authorized"):
        engine.create_job(
            JobCreateRequest(project_id="demo", work_order=invalid, auto_run=False).model_dump(mode="json")
        )

    assert storage.created is None


def test_work_order_requires_approved_project_baseline_before_write(monkeypatch, tmp_path: Path) -> None:
    configure(monkeypatch, tmp_path, baselines={"version": 1, "projects": {}})
    storage = CaptureStorage()
    engine = RuntimeEngine(storage)

    with pytest.raises(ValueError, match="has no ProjectBaseline revision"):
        engine.create_job(
            JobCreateRequest(project_id="demo", work_order=work_order(), auto_run=False).model_dump(mode="json")
        )

    assert storage.created is None


def test_work_order_rejects_unconfigured_verification_phase_before_write(monkeypatch, tmp_path: Path) -> None:
    configure(monkeypatch, tmp_path)
    projects = project_config_doc()
    projects["projects"]["demo"]["ddev"]["full_tests"] = []
    projects_file = tmp_path / "projects.yml"
    projects_file.write_text(yaml.safe_dump(projects, sort_keys=False), encoding="utf-8")
    clear_config_cache()

    storage = CaptureStorage()
    engine = RuntimeEngine(storage)
    contract = work_order(verification={"required_phases": ["full_tests"]})

    with pytest.raises(ValueError, match="has no commands configured"):
        engine.create_job(
            JobCreateRequest(project_id="demo", work_order=contract, auto_run=False).model_dump(mode="json")
        )
    assert storage.created is None


def router_route(profile: str = "standard") -> dict:
    return {
        "job_id": "job1",
        "project_id": "demo",
        "source_commit": "a" * 40,
        "complexity_score": 40,
        "dimensions": {},
        "strategy": {
            "profile": profile,
            "budget": {
                "max_model_calls": 8,
                "max_repair_iterations": 2,
                "max_wall_time_minutes": 25,
                "max_changed_files": 14,
                "max_tool_calls": 80,
                "max_test_runs": 8,
            },
            "executor": {"id": "x"},
        },
    }


class FakeRouter:
    def __init__(self, route: dict) -> None:
        self.value = route

    async def health(self) -> bool:
        return True

    async def route(self, payload: dict) -> dict:
        return deepcopy(self.value)

    async def reassess(self, payload: dict) -> dict:
        return {"action": "continue"}


def test_router_proxy_applies_hard_work_order_budget_ceiling() -> None:
    async def scenario():
        storage = CaptureStorage()
        contract = WorkOrder.model_validate(work_order())
        storage.rows["job1"] = {"id": "job1", "checkpoint": {"work_order": contract.model_dump(mode="json")}}
        proxy = WorkOrderRouterProxy(FakeRouter(router_route()), storage)

        result = await proxy.route({"job_id": "job1"})

        budget = result["strategy"]["budget"]
        assert budget["max_model_calls"] == 5
        assert budget["max_repair_iterations"] == 1
        assert budget["max_wall_time_minutes"] == 20
        assert budget["max_changed_files"] == 8
        assert budget["max_tool_calls"] == 80

    asyncio.run(scenario())


def test_router_proxy_rejects_profile_above_work_order_ceiling() -> None:
    async def scenario():
        storage = CaptureStorage()
        contract = WorkOrder.model_validate(work_order())
        storage.rows["job1"] = {"id": "job1", "checkpoint": {"work_order": contract.model_dump(mode="json")}}
        proxy = WorkOrderRouterProxy(FakeRouter(router_route("complex")), storage)

        with pytest.raises(WorkOrderPolicyError, match="exceeds WorkOrder max_profile"):
            await proxy.route({"job_id": "job1"})

    asyncio.run(scenario())


class FakeDdev:
    def __init__(self) -> None:
        self.phases: list[str] = []

    async def phase(self, *, phase: str, **kwargs):
        self.phases.append(phase)
        return {"passed": True, "phase": phase, "commands": [{"command": phase, "returncode": 0}]}


class VerifyStorage(CaptureStorage):
    pass


def test_required_full_tests_run_even_for_standard_router_profile() -> None:
    async def scenario():
        storage = VerifyStorage()
        contract = WorkOrder.model_validate(
            work_order(
                verification={"required_phases": ["targeted_tests", "static_analysis", "full_tests"]},
                budget={
                    "max_profile": "standard",
                    "max_model_calls": 5,
                    "max_repair_iterations": 1,
                    "max_wall_time_minutes": 20,
                    "max_changed_files": 8,
                },
            )
        )
        storage.rows["job1"] = {
            "id": "job1",
            "checkpoint": {"work_order": contract.model_dump(mode="json")},
        }
        engine = RuntimeEngine(storage)
        engine.ddev = FakeDdev()
        strategy = {
            "profile": "standard",
            "budget": {
                "max_tool_calls": 20,
                "max_test_runs": 20,
                "max_wall_time_minutes": 20,
            },
        }
        project = project_config_doc()["projects"]["demo"]
        progress = {"tool_calls": 0, "test_runs": 0}

        result = await engine._verify(
            "job1",
            "demo",
            Path("/tmp/workspace"),
            project,
            strategy,
            time.monotonic(),
            progress,
        )

        assert result["passed"] is True
        assert engine.ddev.phases == ["targeted_tests", "static_analysis", "full_tests"]
        assert result["test_runs"] == 3

    asyncio.run(scenario())


def test_canonical_contract_is_present_in_all_agent_prompt_types() -> None:
    contract = WorkOrder.model_validate(work_order())
    task = canonical_task_from_work_order(contract)
    route = {"strategy": {"profile": "standard", "definition_of_done": {"required": []}}}

    prompts = [
        planning_prompt(task=task, repo_analysis={}),
        execution_prompt(task=task, route=route, repo_analysis={}),
        evaluator_prompt(task=task, diff="diff", verification={"passed": True}),
    ]

    for prompt in prompts:
        assert "AUTHORITATIVE WORKORDER / TASK CONTRACT" in prompt
        assert "WO-123" in prompt
        assert '"baseline_revision": "v1"' in prompt
        assert '"out_of_scope": ["UI redesign", "schema changes"]' in prompt
        assert '"requested_role": "backend_developer"' in prompt
        assert '"dependencies": ["WO-120"]' in prompt
        assert '"required_phases": ["targeted_tests", "static_analysis"]' in prompt


def test_checkpoint_and_job_view_preserve_contract_identity() -> None:
    contract = WorkOrder.model_validate(work_order())
    timestamp = datetime(2026, 9, 13, tzinfo=timezone.utc)
    row = {
        "id": "job1",
        "project_id": "demo",
        "status": "queued",
        "source_commit": None,
        "branch": None,
        "workspace": None,
        "route": None,
        "repo_analysis": {"estimated_files": 1},
        "progress": {},
        "checkpoint": {
            "project_baseline": {"revision": "v1"},
            "work_order": contract.model_dump(mode="json"),
        },
        "result": None,
        "error": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    checkpoint = checkpoint_from_row(row)
    assert checkpoint["work_order"]["id"] == "WO-123"
    result = view(row)
    assert result.baseline_revision == "v1"
    assert result.work_order_id == "WO-123"

def test_work_order_accepts_frontend_quality_phase_when_configured(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    projects = project_config_doc()
    projects["projects"]["demo"]["ddev"]["frontend_quality"] = [
        "frontend-quality"
    ]
    projects_file = tmp_path / "projects.yml"
    projects_file.write_text(
        yaml.safe_dump(projects, sort_keys=False),
        encoding="utf-8",
    )
    clear_config_cache()

    storage = CaptureStorage()
    engine = RuntimeEngine(storage)
    contract = work_order(
        verification={
            "required_phases": [
                "targeted_tests",
                "frontend_quality",
            ]
        }
    )

    job_id = engine.create_job(
        JobCreateRequest(
            project_id="demo",
            work_order=contract,
            auto_run=False,
        ).model_dump(mode="json")
    )

    assert storage.rows[job_id]["checkpoint"]["work_order"][
        "verification"
    ]["required_phases"] == [
        "targeted_tests",
        "frontend_quality",
    ]



def test_visual_quality_contract_requires_frontend_quality_and_routes() -> None:
    with pytest.raises(ValidationError, match="requires frontend_quality"):
        WorkOrder.model_validate(
            work_order(
                verification={
                    "required_phases": ["targeted_tests", "visual_quality"],
                    "visual_routes": ["/artist/demo"],
                }
            )
        )

    with pytest.raises(ValidationError, match="at least one visual_routes"):
        WorkOrder.model_validate(
            work_order(
                verification={
                    "required_phases": [
                        "targeted_tests",
                        "frontend_quality",
                        "visual_quality",
                    ],
                    "visual_routes": [],
                }
            )
        )

    with pytest.raises(ValidationError, match="must run before visual_quality"):
        WorkOrder.model_validate(
            work_order(
                verification={
                    "required_phases": [
                        "targeted_tests",
                        "visual_quality",
                        "frontend_quality",
                    ],
                    "visual_routes": ["/artist/demo"],
                }
            )
        )

    contract = WorkOrder.model_validate(
        work_order(
            verification={
                "required_phases": [
                    "targeted_tests",
                    "frontend_quality",
                    "visual_quality",
                ],
                "visual_routes": ["/artist/demo", "/events"],
            }
        )
    )
    assert contract.verification.visual_routes == ["/artist/demo", "/events"]


@pytest.mark.parametrize(
    "route",
    [
        "artist/demo",
        "//evil.example",
        "https://evil.example/path",
        "/artist/demo?token=secret",
        "/artist/demo#fragment",
    ],
)
def test_visual_routes_reject_nonlocal_or_unbounded_url_forms(route: str) -> None:
    with pytest.raises(ValidationError, match="visual_routes"):
        WorkOrder.model_validate(
            work_order(
                verification={
                    "required_phases": [
                        "targeted_tests",
                        "frontend_quality",
                        "visual_quality",
                    ],
                    "visual_routes": [route],
                }
            )
        )


def test_visual_quality_requires_direct_preview_project_capability(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    projects = project_config_doc()
    demo = projects["projects"]["demo"]
    demo["ddev"]["frontend_quality"] = ["frontend-quality"]
    demo["ddev"]["visual_quality"] = ["visual-quality"]
    projects_file = tmp_path / "projects.yml"
    projects_file.write_text(yaml.safe_dump(projects, sort_keys=False), encoding="utf-8")
    clear_config_cache()

    storage = CaptureStorage()
    engine = RuntimeEngine(storage)
    contract = work_order(
        verification={
            "required_phases": [
                "targeted_tests",
                "frontend_quality",
                "visual_quality",
            ],
            "visual_routes": ["/artist/demo"],
        }
    )

    with pytest.raises(ValueError, match="direct workspace"):
        engine.create_job(
            JobCreateRequest(
                project_id="demo",
                work_order=contract,
                auto_run=False,
            ).model_dump(mode="json")
        )

    projects["projects"]["demo"]["runtime"] = {
        "workspace_mode": "direct",
        "exclusive_project_lease": True,
    }
    projects["projects"]["demo"]["preview"] = {
        "frontend": {"enabled": True},
        "visual_evidence": {
            "internal_base_url": "http://127.0.0.1:3100",
            "viewports": [390, 1024],
        },
    }
    projects_file.write_text(yaml.safe_dump(projects, sort_keys=False), encoding="utf-8")
    clear_config_cache()

    storage = CaptureStorage()
    engine = RuntimeEngine(storage)
    job_id = engine.create_job(
        JobCreateRequest(
            project_id="demo",
            work_order=contract,
            auto_run=False,
        ).model_dump(mode="json")
    )

    assert storage.rows[job_id]["checkpoint"]["work_order"]["verification"][
        "visual_routes"
    ] == ["/artist/demo"]


def test_visual_quality_runs_after_frontend_quality_with_job_preview(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def scenario():
        workspace = tmp_path / "visual-workspace"
        workspace.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(workspace)],
            check=True,
            capture_output=True,
        )

        contract = WorkOrder.model_validate(
            work_order(
                verification={
                    "required_phases": [
                        "targeted_tests",
                        "frontend_quality",
                        "visual_quality",
                    ],
                    "visual_routes": ["/artist/demo"],
                },
                budget={
                    "max_profile": "standard",
                    "max_model_calls": 5,
                    "max_repair_iterations": 1,
                    "max_wall_time_minutes": 20,
                    "max_changed_files": 8,
                },
            )
        )
        storage = VerifyStorage()
        storage.rows["job1"] = {
            "id": "job1",
            "project_id": "demo",
            "checkpoint": {"work_order": contract.model_dump(mode="json")},
        }

        class VisualDdev:
            def __init__(self) -> None:
                self.phases: list[str] = []

            async def phase(self, *, phase: str, workspace: str, **kwargs):
                self.phases.append(phase)
                stdout = ""
                if phase == "visual_quality":
                    request_path = Path(workspace) / ".git" / "pcp-visual-request.json"
                    assert request_path.exists()
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    assert request["routes"] == ["/artist/demo"]
                    marker = {
                        "version": 1,
                        "evidence_kind": "local_playwright_preview",
                        "image_reviewed": False,
                        "passed": True,
                        "routes": ["/artist/demo"],
                        "viewports": [390],
                        "artifacts": [
                            {
                                "route": "/artist/demo",
                                "viewport": {"width": 390, "height": 844},
                                "status_code": 200,
                                "console_errors": [],
                                "page_errors": [],
                                "failed_requests": [],
                                "dom": {
                                    "title": "Artist",
                                    "h1": ["Artist"],
                                    "links": 2,
                                    "buttons": 1,
                                    "main_landmarks": 1,
                                    "nav_landmarks": 1,
                                    "horizontal_overflow": False,
                                },
                                "screenshot": {
                                    "path": ".pcp-visual-evidence/artist-demo-390.png",
                                    "sha256": "a" * 64,
                                },
                                "passed": True,
                            }
                        ],
                    }
                    stdout = "PCP_VISUAL_EVIDENCE_JSON=" + json.dumps(marker)
                return {
                    "passed": True,
                    "phase": phase,
                    "commands": [
                        {
                            "command": phase,
                            "returncode": 0,
                            "stdout": stdout,
                            "stderr": "",
                        }
                    ],
                }

        class FakePreviewManager:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def status(self, job_id: str):
                return {
                    "status": "stopped",
                    "supported": True,
                    "frontend_url": None,
                }

            async def start(self, job_id: str, target: str):
                assert job_id == "job1"
                assert target == "frontend"
                return {
                    "status": "ready",
                    "supported": True,
                    "frontend_url": "https://demo.ddev.site:3100",
                }

        monkeypatch.setattr(
            "app.engine_verification.PreviewManager",
            FakePreviewManager,
        )

        engine = RuntimeEngine(storage)
        engine.ddev = VisualDdev()
        project = {
            "runtime": {
                "workspace_mode": "direct",
                "exclusive_project_lease": True,
            },
            "preview": {
                "frontend": {"enabled": True},
                "visual_evidence": {
                    "internal_base_url": "http://127.0.0.1:3100",
                    "viewports": [390],
                },
            },
            "ddev": {
                "enabled": True,
                "targeted_tests": ["targeted"],
                "frontend_quality": ["frontend"],
                "visual_quality": ["visual"],
                "full_tests": [],
            },
        }
        strategy = {
            "profile": "standard",
            "budget": {
                "max_tool_calls": 20,
                "max_test_runs": 20,
                "max_wall_time_minutes": 20,
            },
        }
        progress = {
            "tool_calls": 0,
            "test_runs": 0,
            "verification_attempts": 0,
        }

        result = await engine._verify(
            "job1",
            "demo",
            workspace,
            project,
            strategy,
            time.monotonic(),
            progress,
        )

        assert result["passed"] is True
        assert engine.ddev.phases == [
            "targeted_tests",
            "frontend_quality",
            "visual_quality",
        ]
        visual = result["phases"][-1]["visual_evidence"]
        assert visual["passed"] is True
        assert visual["image_reviewed"] is False
        assert visual["artifacts"][0]["route"] == "/artist/demo"
        assert not (workspace / ".git" / "pcp-visual-request.json").exists()

    asyncio.run(scenario())


def test_visual_quality_fails_without_bounded_evidence_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def scenario():
        workspace = tmp_path / "visual-workspace-missing"
        workspace.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(workspace)],
            check=True,
            capture_output=True,
        )
        contract = WorkOrder.model_validate(
            work_order(
                verification={
                    "required_phases": [
                        "frontend_quality",
                        "visual_quality",
                    ],
                    "visual_routes": ["/"],
                }
            )
        )
        storage = VerifyStorage()
        storage.rows["job1"] = {
            "id": "job1",
            "project_id": "demo",
            "checkpoint": {"work_order": contract.model_dump(mode="json")},
        }

        class NoMarkerDdev:
            async def phase(self, *, phase: str, **kwargs):
                return {
                    "passed": True,
                    "phase": phase,
                    "commands": [
                        {
                            "command": phase,
                            "returncode": 0,
                            "stdout": "",
                            "stderr": "",
                        }
                    ],
                }

        class ReadyPreviewManager:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def status(self, job_id: str):
                return {
                    "status": "ready",
                    "supported": True,
                    "frontend_url": "https://demo.ddev.site:3100",
                }

        monkeypatch.setattr(
            "app.engine_verification.PreviewManager",
            ReadyPreviewManager,
        )
        engine = RuntimeEngine(storage)
        engine.ddev = NoMarkerDdev()
        project = {
            "runtime": {
                "workspace_mode": "direct",
                "exclusive_project_lease": True,
            },
            "preview": {
                "frontend": {"enabled": True},
                "visual_evidence": {
                    "internal_base_url": "http://127.0.0.1:3100",
                    "viewports": [390],
                },
            },
            "ddev": {
                "enabled": True,
                "frontend_quality": ["frontend"],
                "visual_quality": ["visual"],
                "full_tests": [],
            },
        }
        result = await engine._verify(
            "job1",
            "demo",
            workspace,
            project,
            {
                "profile": "standard",
                "budget": {
                    "max_tool_calls": 20,
                    "max_test_runs": 20,
                    "max_wall_time_minutes": 20,
                },
            },
            time.monotonic(),
            {
                "tool_calls": 0,
                "test_runs": 0,
                "verification_attempts": 0,
            },
        )

        assert result["passed"] is False
        assert "bounded PCP visual evidence marker is missing or invalid" in result[
            "failure_text"
        ]
        assert not (workspace / ".git" / "pcp-visual-request.json").exists()

    asyncio.run(scenario())
