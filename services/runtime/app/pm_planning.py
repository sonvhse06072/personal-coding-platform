from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .adapters.factory import build_adapter
from .baseline import ProjectBaseline, SourceReference, resolve_project_baseline
from .config import project_config
from .executor_client import DdevExecutorClient
from .model_capabilities import validate_model_choice
from .router_client import RouterClient
from .schemas import RepoHints, SemanticSignals
from .shell import run_command
from .storage import Storage
from .usage import estimated_cost_usd, normalize_usage
from .work_order import WorkOrder, validate_work_order_against_baseline


PlanStatus = Literal[
    "planning",
    "ready",
    "out_of_scope",
    "human_decision",
    "failed",
    "interrupted",
]
PlanExecutionMode = Literal["autonomous", "supervised"]
ScopeAssessment = Literal["in_scope", "out_of_scope", "ambiguous"]
PlanningProfile = Literal["standard", "complex"]
DecisionCategory = Literal[
    "product",
    "architecture",
    "security",
    "major_dependency",
    "data_migration",
    "production",
    "budget",
    "ambiguity",
]


class PMTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=30000)

    @field_validator("title", "description")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("PM ticket text must not be blank")
        return normalized


class PMProviderState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    healthy: bool = True
    quota_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: int = Field(default=0, ge=0)
    predicted_success: float | None = Field(default=None, ge=0.0, le=1.0)
    available: bool = True


class PMPlanCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=200)
    ticket: PMTicket
    baseline_revision: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    planning_profile: PlanningProfile = "standard"
    execution_mode: PlanExecutionMode = "autonomous"
    provider_state: dict[str, PMProviderState] = Field(default_factory=dict, max_length=50)
    decomposition_required: bool = False
    semantic: SemanticSignals | None = None
    repo_hints: RepoHints | None = None


class DecisionBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
    category: DecisionCategory
    reason: str = Field(min_length=1, max_length=5000)
    source_references: list[SourceReference] = Field(default_factory=list, max_length=20)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Decision-boundary reason must not be blank")
        return normalized


class PMPlanProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_assessment: ScopeAssessment
    summary: str = Field(min_length=1, max_length=8000)
    work_orders: list[WorkOrder] = Field(default_factory=list, max_length=30)
    decision_boundaries: list[DecisionBoundary] = Field(default_factory=list, max_length=20)

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ExecutionPlan summary must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_scope_shape(self) -> "PMPlanProposal":
        if self.scope_assessment == "out_of_scope" and self.work_orders:
            raise ValueError("Out-of-scope tickets must not produce WorkOrders")
        if self.scope_assessment == "ambiguous" and not self.decision_boundaries:
            raise ValueError("Ambiguous tickets must identify at least one human decision boundary")
        if (
            self.scope_assessment == "in_scope"
            and not self.work_orders
            and not self.decision_boundaries
        ):
            raise ValueError("In-scope tickets require WorkOrders or a human decision boundary")
        return self


class ExecutionPlanDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_assessment: ScopeAssessment
    summary: str
    work_orders: list[WorkOrder]
    decision_boundaries: list[DecisionBoundary]
    ready_work_order_ids: list[str]
    execution_mode: PlanExecutionMode = "autonomous"


class ExecutionPlanView(BaseModel):
    id: str
    project_id: str
    status: PlanStatus
    baseline_revision: str
    baseline_source_commit: str
    ticket: PMTicket
    staffing: dict[str, Any] | None = None
    plan: ExecutionPlanDocument | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    updated_at: str


def execution_plan_view(row: dict[str, Any]) -> ExecutionPlanView:
    plan = row.get("plan")
    return ExecutionPlanView(
        id=row["id"],
        project_id=row["project_id"],
        status=row["status"],
        baseline_revision=row["baseline_revision"],
        baseline_source_commit=row["baseline_source_commit"],
        ticket=PMTicket.model_validate(row["ticket"]),
        staffing=row.get("staffing"),
        plan=ExecutionPlanDocument.model_validate(plan) if plan else None,
        usage=row.get("usage"),
        error=row.get("error"),
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat(),
    )


def _baseline_reference_paths(baseline: ProjectBaseline) -> set[str]:
    result: set[str] = set()
    for references in baseline.references.model_dump(mode="json").values():
        for reference in references:
            result.add(str(reference["path"]))
    return result


def _validate_decision_references(
    boundaries: list[DecisionBoundary],
    baseline: ProjectBaseline,
) -> None:
    allowed = _baseline_reference_paths(baseline)
    for boundary in boundaries:
        for reference in boundary.source_references:
            if reference.path not in allowed:
                raise ValueError(
                    f"Decision boundary {boundary.id!r} references {reference.path!r}, "
                    f"which is outside ProjectBaseline {baseline.revision!r}"
                )


def _validate_dependency_graph(work_orders: list[WorkOrder]) -> list[str]:
    by_id = {work_order.id: work_order for work_order in work_orders}
    if len(by_id) != len(work_orders):
        raise ValueError("ExecutionPlan WorkOrder ids must be unique")

    for work_order in work_orders:
        unknown = sorted(set(work_order.dependencies) - set(by_id))
        if unknown:
            raise ValueError(
                f"WorkOrder {work_order.id!r} depends on unknown WorkOrders: {unknown}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(work_order_id: str) -> None:
        if work_order_id in visiting:
            raise ValueError("ExecutionPlan WorkOrder dependency graph contains a cycle")
        if work_order_id in visited:
            return
        visiting.add(work_order_id)
        for dependency in by_id[work_order_id].dependencies:
            visit(dependency)
        visiting.remove(work_order_id)
        visited.add(work_order_id)

    for work_order_id in by_id:
        visit(work_order_id)

    return [work_order.id for work_order in work_orders if not work_order.dependencies]


def validate_plan_proposal(
    proposal: PMPlanProposal,
    *,
    ticket: PMTicket,
    baseline: ProjectBaseline,
    project: dict[str, Any],
    decomposition_required: bool = False,
    execution_mode: PlanExecutionMode = "autonomous",
) -> ExecutionPlanDocument:
    if (
        decomposition_required
        and proposal.scope_assessment == "in_scope"
        and not proposal.decision_boundaries
        and len(proposal.work_orders) < 2
    ):
        raise ValueError("Decomposition-required in-scope tickets require at least two WorkOrders")
    _validate_decision_references(proposal.decision_boundaries, baseline)

    for work_order in proposal.work_orders:
        if work_order.parent_ticket != ticket.id:
            raise ValueError(
                f"WorkOrder {work_order.id!r} must set parent_ticket to {ticket.id!r}"
            )
        validate_work_order_against_baseline(work_order, baseline, project)

    ready_ids = _validate_dependency_graph(proposal.work_orders)
    if proposal.scope_assessment != "in_scope" or proposal.decision_boundaries:
        ready_ids = []

    return ExecutionPlanDocument(
        scope_assessment=proposal.scope_assessment,
        summary=proposal.summary,
        work_orders=proposal.work_orders,
        decision_boundaries=proposal.decision_boundaries,
        ready_work_order_ids=ready_ids,
        execution_mode=execution_mode,
    )


def execution_plan_status(plan: ExecutionPlanDocument) -> PlanStatus:
    if plan.scope_assessment == "out_of_scope":
        return "out_of_scope"
    if plan.scope_assessment == "ambiguous" or plan.decision_boundaries:
        return "human_decision"
    return "ready"


def _available_verification_phases(project: dict[str, Any]) -> list[str]:
    ddev = project.get("ddev", {}) or {}
    if not ddev.get("enabled", False):
        return []
    return [
        phase
        for phase in (
            "targeted_tests",
            "static_analysis",
            "frontend_quality",
            "visual_quality",
            "full_tests",
        )
        if ddev.get(phase)
    ]


def _planning_prompt(
    *,
    ticket: PMTicket,
    baseline: ProjectBaseline,
    project: dict[str, Any],
    decomposition_required: bool = False,
    semantic: SemanticSignals | None = None,
    repo_hints: RepoHints | None = None,
) -> str:
    verification = _available_verification_phases(project)
    schema = PMPlanProposal.model_json_schema()
    return "\n".join(
        [
            "You are the Product Manager for a bounded personal software-development project.",
            "This is planning/triage only. Do not edit files, do not run write operations, do not commit, push, merge, deploy, or amend project documentation.",
            "The checked-in ProjectBaseline is authoritative. Read the referenced source-of-truth files in this workspace before deciding scope or decomposing work.",
            "You may inspect relevant repository code/tests read-only when needed to make WorkOrders concrete, but repository implementation cannot override higher-authority Source of Truth.",
            "If the ticket conflicts with scope, architecture, security policy, a major dependency rule, destructive-data policy, production policy, or material budget policy, identify a human decision boundary instead of silently changing the project frame.",
            "Use logical team roles only. Never name a model/provider as requested_role.",
            "Every WorkOrder must set parent_ticket exactly to the input ticket id and baseline_revision exactly to the governing revision.",
            "Every WorkOrder source_references path must come from the governing baseline. Use only deterministic verification phases listed as available.",
            "When visual_quality is available and a WorkOrder materially changes a user-facing frontend/UI surface, require frontend_quality before visual_quality and provide bounded visual_routes for concrete local routes that the WorkOrder can actually render. visual_quality supplements rather than replaces deterministic frontend/browser functional checks. Do not invent fixture-dependent routes that the current WorkOrder cannot make available.",
            "Keep WorkOrders small, dependency-aware, and independently verifiable. Optimize for a personal, budget-conscious team; do not create unnecessary tasks or parallelism.",
            (
                "DECOMPOSITION_REQUIRED: This materially non-trivial ticket must produce at least two coherent, independently verifiable WorkOrders when in scope with no decision boundaries. Split by semantic/dependency boundaries, never arbitrary file counts. Out-of-scope, ambiguous or human-decision results need no artificial WorkOrders."
                if decomposition_required else "A single bounded WorkOrder is valid when sufficient."
            ),
            "Return EXACTLY one JSON object and no Markdown/prose outside the object. It must validate against the supplied JSON Schema.",
            "",
            f"TICKET: {json.dumps(ticket.model_dump(mode='json'), ensure_ascii=False, sort_keys=True)}",
            f"SEMANTIC_SIGNALS: {json.dumps(semantic.model_dump(exclude_unset=True) if semantic is not None else None, sort_keys=True)}",
            f"REPO_HINTS: {json.dumps(repo_hints.model_dump(exclude_none=True) if repo_hints is not None else None, sort_keys=True)}",
            f"PROJECT_BASELINE: {json.dumps(baseline.model_dump(mode='json'), ensure_ascii=False, sort_keys=True)}",
            f"AVAILABLE_VERIFICATION_PHASES: {json.dumps(verification)}",
            "OUTPUT_JSON_SCHEMA:",
            json.dumps(schema, ensure_ascii=False, sort_keys=True),
        ]
    )


def _parse_pm_output(output: str) -> PMPlanProposal:
    text = (output or "").strip()
    if not text:
        raise ValueError("Product Manager returned empty output")
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise ValueError("Product Manager returned an unterminated fenced response")
        text = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Product Manager output must be one JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("Product Manager output must be a JSON object")
    return PMPlanProposal.model_validate(payload)


async def _workspace_state(workspace: Path) -> str:
    result = await run_command(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=workspace,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "Unable to inspect PM workspace")
    return result.stdout


def _validate_baseline_files(workspace: Path, baseline: ProjectBaseline) -> None:
    root = workspace.resolve()
    missing: list[str] = []
    for relative in sorted(_baseline_reference_paths(baseline)):
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"ProjectBaseline path escapes PM workspace: {relative}") from exc
        if not candidate.is_file():
            missing.append(relative)
    if missing:
        raise ValueError(
            f"ProjectBaseline references missing files at source commit {baseline.source_commit}: {missing}"
        )


class PMPlanner:
    def __init__(
        self,
        storage: Storage,
        *,
        router: RouterClient | None = None,
        ddev: DdevExecutorClient | None = None,
        adapter_builder=build_adapter,
    ) -> None:
        self.storage = storage
        self.router = router or RouterClient()
        self.ddev = ddev or DdevExecutorClient()
        self.adapter_builder = adapter_builder
        self._lock = asyncio.Lock()

    async def create_plan(self, request: PMPlanCreateRequest) -> dict[str, Any]:
        async with self._lock:
            return await self._create_plan_locked(request)

    async def _create_plan_locked(self, request: PMPlanCreateRequest) -> dict[str, Any]:
        project = project_config(request.project_id)
        baseline = resolve_project_baseline(request.project_id, request.baseline_revision)
        if baseline is None:
            raise ValueError("Product Manager planning requires an approved ProjectBaseline")
        if not _available_verification_phases(project):
            raise ValueError("Product Manager planning requires at least one deterministic verification phase")

        plan_id = f"pm-{uuid.uuid4().hex}"
        self.storage.create_execution_plan(
            {
                "id": plan_id,
                "project_id": request.project_id,
                "status": "planning",
                "baseline_revision": baseline.revision,
                "baseline_source_commit": baseline.source_commit,
                "ticket": request.ticket.model_dump(mode="json"),
                "staffing": None,
                "plan": None,
                "usage": None,
                "error": None,
            }
        )

        workspace_info: dict[str, Any] | None = None
        planning_error: str | None = None
        try:
            staffing = await self.router.staff(
                {
                    "request_id": plan_id,
                    "project_id": request.project_id,
                    "role": "product_manager",
                    "profile": request.planning_profile,
                    "semantic": {
                        "ambiguity": 45,
                        "architecture_impact": 45,
                        "verification_difficulty": 30,
                        "risk": 40,
                        "context_requirement": 75,
                        "novelty": 40,
                        "reasoning_requirement": 85,
                    },
                    "provider_state": {
                        key: state.model_dump(mode="json")
                        for key, state in request.provider_state.items()
                    },
                }
            )
            self.storage.update_execution_plan(plan_id, staffing=staffing)

            choice = staffing.get("choice") or {}
            validate_model_choice(choice)

            workspace_info = await self.ddev.create_workspace(
                job_id=plan_id,
                project_id=request.project_id,
                ref=baseline.source_commit,
                workspace_mode="isolated_clone",
            )
            source_commit = str(workspace_info.get("source_commit") or "").lower()
            if source_commit != baseline.source_commit.lower():
                raise RuntimeError(
                    "PM workspace source commit does not match the approved ProjectBaseline"
                )
            workspace = Path(str(workspace_info["workspace"]))
            _validate_baseline_files(workspace, baseline)
            before = await _workspace_state(workspace)

            adapter = self.adapter_builder(
                str(choice["adapter"]),
                str(choice["model"]),
                choice.get("reasoning_effort"),
            )
            run = await adapter.run(
                workspace=workspace,
                prompt=_planning_prompt(
                    ticket=request.ticket, baseline=baseline, project=project,
                    decomposition_required=request.decomposition_required,
                    semantic=request.semantic, repo_hints=request.repo_hints,
                ),
                mode="plan",
                timeout=600 if request.planning_profile == "complex" else 360,
            )
            after = await _workspace_state(workspace)
            if after != before:
                raise RuntimeError("Product Manager modified the read-only planning workspace")
            if run.returncode != 0:
                detail = run.failure_message or run.stderr or run.output or "Product Manager call failed"
                raise RuntimeError(
                    f"Product Manager model call failed ({run.failure_kind or run.returncode}): {detail[-12000:]}"
                )

            proposal = _parse_pm_output(run.output)
            plan = validate_plan_proposal(
                proposal,
                ticket=request.ticket,
                baseline=baseline,
                project=project,
                decomposition_required=request.decomposition_required,
                execution_mode=request.execution_mode,
            )
            status = execution_plan_status(plan)
            normalized_usage = normalize_usage(run.usage)
            normalized_usage["estimated_cost_usd"] = estimated_cost_usd(
                str(choice.get("id") or ""),
                run.usage,
            )
            normalized_usage["model_calls"] = 1
            self.storage.update_execution_plan(
                plan_id,
                status=status,
                plan=plan.model_dump(mode="json"),
                usage=normalized_usage,
                error=None,
            )
        except asyncio.CancelledError:
            self.storage.update_execution_plan(
                plan_id,
                status="interrupted",
                error="Product Manager planning was cancelled; submit a new planning request.",
            )
            raise
        except Exception as exc:
            planning_error = f"{type(exc).__name__}: {exc}"
            self.storage.update_execution_plan(
                plan_id,
                status="failed",
                error=planning_error[-12000:],
            )
        finally:
            if workspace_info and workspace_info.get("workspace"):
                try:
                    await asyncio.shield(
                        self.ddev.remove_workspace(
                            job_id=plan_id,
                            project_id=request.project_id,
                            workspace=str(workspace_info["workspace"]),
                        )
                    )
                except Exception as cleanup_exc:
                    row = self.storage.get_execution_plan(plan_id)
                    existing = str((row or {}).get("error") or planning_error or "").strip()
                    detail = f"PM planning workspace cleanup failed: {cleanup_exc}"
                    error = f"{existing}\n{detail}".strip()[-12000:]
                    self.storage.update_execution_plan(
                        plan_id,
                        status="failed",
                        error=error,
                    )

        row = self.storage.get_execution_plan(plan_id)
        assert row is not None
        return row
