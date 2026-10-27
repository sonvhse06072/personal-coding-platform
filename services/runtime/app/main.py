from __future__ import annotations

import asyncio
import os
import secrets
import shutil
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .collaboration import (
    CollaborationCreateRequest,
    CollaborationRecheckRequest,
    CollaborationView,
)
from .baseline import resolve_project_baseline
from .intake import IntakeRequest, IntakeResponse, DirectIntakeResponse, PlanningIntakeResponse
from .intake_policy import classify_intake
from .job_status_publisher import JobStatusPublisher
from .dashboard import _require_session, create_dashboard_router
from .engine_telemetry import RuntimeEngine
from .engine_core import require_legacy_job, SourceJobNotExecutable
from .g0_fixture_execution import G0FixtureExecution, G0GateError
from .fullpath_pm_review import FullpathPMReviewRequest, FullpathPMReviewService
from .fullpath_worker_only import (
    F2_WORKER_MODE, F2_V2_REVISION, F2_V2_SEED, F2WorkerNotReady,
    F2_REENTRY_JOB_ID, require_f2_exact_blocked_job,
    require_f2_worker_environment, attest_f2_worker_database,
    f2_direct_intake_route_allowed,
)
from .config import projects_doc, project_baselines_doc
from .fullpath_fixture_safety import MODE as FULLPATH_CANDIDATE_MODE, parked_fullpath_environment, reject_parked_fullpath_side_effects, refuse_source_only_startup
from .storage import Storage
from .executor_client import DdevExecutorClient
from .orchestrator_notifications import PlanOrchestrator
from .plan_progress_store import PlanProgressStore
from .plan_progress_publisher import PlanProgressPublisher
from .plan_orchestrator import PlanContinuationConflict
from .orchestrator_resume import prepare_orchestrated_job_resume, reopen_orchestrated_job
from .pm_bridge import configure_control_dispatcher, router as pm_bridge_router
from .pm_control_dispatch import PMControlDispatcher
from .preview import PreviewManager, ProjectPreviewManager
from .pm_planning import (
    ExecutionPlanView,
    PMPlanCreateRequest,
    PMPlanner,
    execution_plan_view,
)
from .quota_runtime import quota_coordinator
from .schemas import (
    ActiveEngineeringWorkCount,
    HumanDecisionRequest,
    JobCreateRequest,
    JobList,
    ReviewRepairRequest,
    JobRunRequest,
    JobSourceAdvanceRequest,
    JobView,
    RuntimeHealth,
    TaskInput,
)
from .security import harden_runtime_process_secret_boundary
from .telemetry_storage import TelemetryStorage


class OperatorResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["complete", "block"]
    note: str = Field(default="", max_length=2000)


class PlanContinuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generation: int = Field(ge=1)
    continuation_key: str = Field(
        min_length=78,
        max_length=78,
        pattern=r"^plan:continue:[0-9a-f]{64}$",
    )
    checkpoint_id: int = Field(ge=1)
    checkpoint_key: str = Field(min_length=1, max_length=500)
    ready_work_order_ids: list[str] = Field(min_length=1, max_length=30)

    @field_validator("ready_work_order_ids")
    @classmethod
    def exact_sorted_ready_set(cls, value: list[str]) -> list[str]:
        if any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or len(item) > 200
            for item in value
        ):
            raise ValueError("Ready WorkOrder ids must be exact non-empty strings of at most 200 characters")
        if value != sorted(set(value)):
            raise ValueError("Ready WorkOrder ids must be unique and sorted")
        return value


class WorkOrderSupersessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)
    superseded_by_plan_id: str | None = Field(default=None, min_length=1, max_length=200)
    superseded_by_work_order_id: str | None = Field(default=None, min_length=1, max_length=200)


class NotificationReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1, max_length=1000)
    retry_seconds: int = Field(default=60, ge=5, le=3600)


class ControlActionExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_user_id: str = Field(min_length=1, max_length=100)
    telegram_chat_id: str = Field(min_length=1, max_length=100)


class ContinuityEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["pr_merged", "rollout", "governance_decision"]
    project_id: str = Field(min_length=1, max_length=200)
    job_id: str | None = Field(default=None, max_length=200)
    detail: dict[str, Any] = Field(default_factory=dict)


storage = TelemetryStorage()
engine = RuntimeEngine(storage)
_f2_single_job_intake_lock = asyncio.Lock()
g0_fixture_runner = G0FixtureExecution(Storage(), DdevExecutorClient())
fullpath_pm_review = FullpathPMReviewService(storage, engine.ddev)
pm_planner = PMPlanner(storage)
collaboration_manager = engine.collaboration
progress_handoffs = PlanProgressStore(storage)
plan_orchestrator = PlanOrchestrator(storage, engine, progress_handoffs=progress_handoffs)
pm_control_dispatcher = PMControlDispatcher(storage, engine, plan_orchestrator)
configure_control_dispatcher(pm_control_dispatcher.dispatch)
progress_publisher = PlanProgressPublisher(progress_handoffs, engine.ddev)
job_status_publisher = JobStatusPublisher(
    storage,
    engine.ddev,
    plan_orchestrator.controls,
    notification_store=plan_orchestrator.store,
)
preview_manager = PreviewManager(storage, engine.ddev)
project_preview_manager = ProjectPreviewManager(storage, engine.ddev)


def auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("RUNTIME_API_TOKEN", "").strip()
    if not expected or expected in {"CHANGE_ME", "change-me"}:
        raise HTTPException(503, "RUNTIME_API_TOKEN is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    if not secrets.compare_digest(authorization.removeprefix("Bearer ").strip(), expected):
        raise HTTPException(401, "Invalid bearer token")


def view(row: dict[str, Any]) -> JobView:
    route = row.get("route") or {}
    strategy = route.get("strategy") or {}
    checkpoint = row.get("checkpoint") or {}
    baseline = checkpoint.get("project_baseline") or {}
    work_order = checkpoint.get("work_order") or {}
    executor = checkpoint.get("executor_choice") or strategy.get("executor") or {}
    return JobView(
        id=row["id"], project_id=row["project_id"], status=row["status"], source_commit=row.get("source_commit"),
        baseline_revision=baseline.get("revision"), work_order_id=work_order.get("id"),
        branch=row.get("branch"), workspace=row.get("workspace"), complexity_score=route.get("complexity_score"),
        profile=strategy.get("profile"), executor=executor.get("id"),
        created_at=row["created_at"].isoformat(), updated_at=row["updated_at"].isoformat(),
        result=row.get("result"), error=row.get("error"),
    )


def runtime_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    return HTTPException(404 if message == "Unknown job" else 409, message)


def _require_legacy_job_mutation(job_id: str) -> None:
    """Narrow per-job HTTP gate, before any direct Executor/control action."""
    row = storage.get(job_id)
    if row is None:
        raise HTTPException(404, "Unknown job")
    try:
        require_legacy_job(row)
    except SourceJobNotExecutable as exc:
        raise HTTPException(409, str(exc)) from exc


async def _create_local_job_guarded(
    request: JobCreateRequest,
    *,
    intake_decision=None,
) -> str:
    """Create/enqueue one local job without racing exclusive direct-project sync."""
    project_id = request.project_id
    if engine.is_exclusive_direct_project(project_id):
        async with engine.project_operation_lock(project_id):
            lease = storage.project_lease(project_id)
            if lease and str(lease.get("state") or "") == "active":
                raise RuntimeError(
                    f"Project {project_id} is already leased by job "
                    f"{lease.get('owner_job_id')}"
                )
            job_id = engine.create_job(
                request.model_dump(mode="json"),
                _intake_decision=intake_decision,
            )
            if request.auto_run:
                reserved = engine.reserve_direct_project_lease(job_id)
                if (
                    reserved is None
                    or str(reserved.get("state") or "") != "active"
                    or str(reserved.get("owner_job_id") or "") != job_id
                ):
                    raise RuntimeError(
                        "Direct job could not reserve its exact project lease"
                    )
                await engine.enqueue(job_id)
            return job_id

    job_id = engine.create_job(
        request.model_dump(mode="json"),
        _intake_decision=intake_decision,
    )
    if request.auto_run:
        await engine.enqueue(job_id)
    return job_id


def _require_manual_collaboration_state(job_id: str) -> None:
    _require_legacy_job_mutation(job_id)
    row = storage.get(job_id)
    if not row:
        raise HTTPException(404, "Unknown job")
    if row.get("status") not in {"blocked", "interrupted"}:
        raise HTTPException(
            409,
            "Manual collaboration is allowed only for blocked/interrupted jobs; active developer collaboration uses the in-workspace bounded control artifact.",
        )



# This mode is SOURCE ONLY; it does not prove Docker/WSL isolation or
# create a project registration, lease, database, credentials, or worker.
PCP_LOCAL_INSPECT_MODE = "pcp_local_inspect"
PCP_LOCAL_WORKER_MODE = "pcp_local_worker"
_PCP_PROJECT_DRAFT = "projects.pcp-local.yml"
_PCP_BASELINE_DRAFT = "project-baselines.pcp-local.yml"
_PCP_LOCAL_FLAGS = (
    "PCP_LOCAL_TASK_SOURCE_ENABLED",
    "PCP_LOCAL_TASK_WORKER_ENABLED",
    "PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION",
)


def _pcp_local_scope_requested() -> bool:
    return (
        any(os.getenv(flag, "") != "" for flag in _PCP_LOCAL_FLAGS)
        or Path(os.getenv("PROJECTS_FILE", "")).name == _PCP_PROJECT_DRAFT
        or Path(os.getenv("PROJECT_BASELINES_FILE", "")).name == _PCP_BASELINE_DRAFT
    )


def _reject_pcp_local_legacy_startup() -> None:
    # Reject before normal engine/startup, historical jobs and publishers.
    if runtime_startup_mode() == PCP_LOCAL_INSPECT_MODE or _pcp_local_scope_requested():
        raise RuntimeError("PCP-local SOURCE ONLY: legacy Runtime is forbidden")


def _validate_pcp_local_inspection() -> None:
    """Check two separate parked singleton registries without touching state."""
    from .baseline import ProjectBaselineRegistry
    import yaml

    paths = []
    for key, name in (
        ("PROJECTS_FILE", _PCP_PROJECT_DRAFT),
        ("PROJECT_BASELINES_FILE", _PCP_BASELINE_DRAFT),
    ):
        raw = os.getenv(key, "")
        path = Path(raw)
        if (not raw or not path.is_absolute() or path.name != name
                or path.is_symlink() or not path.is_file()):
            raise RuntimeError("PCP-local requires explicit real draft registry files")
        paths.append(path)
    if paths[0].parent.resolve() != paths[1].parent.resolve():
        raise RuntimeError("PCP-local draft registry directories differ")
    if any(os.getenv(flag, "") != "" for flag in _PCP_LOCAL_FLAGS):
        raise RuntimeError("PCP-local activation flags must be absent")
    if parked_fullpath_environment(os.environ):
        raise RuntimeError("PCP-local cannot reuse frozen fullpath scope")
    try:
        with paths[0].open(encoding="utf-8") as stream:
            project_registry = yaml.safe_load(stream)
        with paths[1].open(encoding="utf-8") as stream:
            baseline_registry = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError("PCP-local draft YAML invalid") from exc

    draft = {
        "registration_status": "draft",
        "repository": "sonvhse06072/personal-coding-platform",
        "path": None,
        "base_branch": "main",
        "privacy": {
            "private_code": True,
            "allow_training_provider": False,
            "require_zero_retention": True,
        },
        "autonomy": {
            "allow_commit": False, "allow_push_ai_branch": False,
            "allow_create_pr": False, "allow_auto_merge_low_risk": False,
            "allow_production_deploy": False,
        },
        "runtime": {
            "branch_prefix": "ai", "workspace_mode": "isolated_clone",
            "developer_permission_mode": "bounded",
            "exclusive_project_lease": False,
        },
        "ddev": {
            "enabled": False, "preflight": [], "targeted_tests": [],
            "static_analysis": [], "full_tests": [], "cleanup": [],
        },
    }
    if (type(project_registry) is not dict
            or type(project_registry.get("version")) is not int
            or project_registry != {
                "version": 1, "projects": {"pcp-local": draft},
            }):
        raise RuntimeError("PCP-local project is not a parked singleton")
    if (type(baseline_registry) is not dict
            or type(baseline_registry.get("version")) is not int
            or baseline_registry != {
                "version": 1,
                "projects": {"pcp-local": {
                    "active_revision": None, "revisions": {},
                }},
            }):
        raise RuntimeError("PCP-local baseline is not inactive draft")
    ProjectBaselineRegistry.model_validate(baseline_registry)


def runtime_startup_mode() -> str:
    """Explicit, opt-in inspection startup without any durable/runtime transitions."""
    mode = os.getenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    if mode not in {"normal", "inspect", "g0_fixture_run", FULLPATH_CANDIDATE_MODE, F2_WORKER_MODE, PCP_LOCAL_INSPECT_MODE, PCP_LOCAL_WORKER_MODE}:
        raise RuntimeError(
            "Invalid PCP_RUNTIME_STARTUP_MODE; expected normal, inspect, pcp_local_inspect, g0_fixture_run, g0_fullpath_candidate or g0_fullpath_worker"
        )
    return mode


async def _start_legacy_control_plane() -> None:
    """Preserve normal PlanOrchestrator tick and publisher startup.

    No scheduler, plan replay or publisher belongs to a future direct-intake
    fresh F2 worker startup. Parked F2 also blocks direct helper invocation.
    """
    _reject_pcp_local_legacy_startup()
    reject_parked_fullpath_side_effects()
    await plan_orchestrator.start()
    await progress_publisher.start()
    await job_status_publisher.start()


async def _stop_legacy_control_plane() -> None:
    """Unchanged normal teardown order; never a parked F2 operation."""
    _reject_pcp_local_legacy_startup()
    reject_parked_fullpath_side_effects()
    await job_status_publisher.stop()
    await progress_publisher.stop()
    await plan_orchestrator.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # PCP-local scope is rejected before all legacy secret, DB and job actions.
    # Historical invalid-mode startup still hardens before validating the mode.
    if os.getenv("PCP_RUNTIME_STARTUP_MODE", "normal") == PCP_LOCAL_INSPECT_MODE:
        _validate_pcp_local_inspection()
        app.state.pcp_local_inspection_ready = True
        try:
            yield
        finally:
            app.state.pcp_local_inspection_ready = False
        return
    if os.getenv("PCP_RUNTIME_STARTUP_MODE") == PCP_LOCAL_WORKER_MODE:
        from .pcp_local_worker_loop import TrustedReaders
        from .pm_bridge import PMBridgeGitHubClient
        harden_runtime_process_secret_boundary()
        # A mode flag cannot grant operational authority. No DB initialization,
        # scheduler, replay, publisher or model call runs at process startup.
        TrustedReaders(engine, PMBridgeGitHubClient()).authority()
        app.state.pcp_local_worker_ready = True
        try:
            yield
        finally:
            app.state.pcp_local_worker_ready = False
        return
    if _pcp_local_scope_requested():
        raise RuntimeError("PCP-local SOURCE ONLY: legacy Runtime is forbidden")
    harden_runtime_process_secret_boundary()
    mode = runtime_startup_mode()
    if mode == "inspect":
        # In particular: no Storage.init DDL/planning updates, Antigravity
        # cancel-all, queued-job replay, lease cleanup, PlanOrchestrator ticks,
        # or asynchronous notification publishers.
        yield
        return
    if runtime_startup_mode() == "g0_fixture_run":
        # Dedicated G0-only DB and fixture scope. Never run engine.start(),
        # Antigravity global cancellation, project lease repair, PM scheduling
        # or notification publisher loops in this single-job research mode.
        g0_fixture_runner.prepare_startup()
        yield
        return
    if runtime_startup_mode() == F2_WORKER_MODE:
        # F2 direct-intake only. Attest the *already installed* fresh schema
        # under the unprivileged DB role; do not call Storage.init/engine.start
        # or PlanOrchestrator, host Antigravity cancellation or publishers.
        proof = attest_f2_worker_database(
            storage=storage, env=os.environ,
            projects=projects_doc(), baselines=project_baselines_doc(),
        )
        await engine.start_fullpath_worker_only(proof)
        try:
            yield
        finally:
            await engine.stop_fullpath_worker_only()
        return
    if (
        runtime_startup_mode() == FULLPATH_CANDIDATE_MODE
        or parked_fullpath_environment(os.environ)
    ):
        # Even startup_mode=normal cannot promote an F2-rooted candidate into
        # real DB/host cancel/replay/plan actions by changing one variable.
        refuse_source_only_startup()
    await engine.start()
    await _start_legacy_control_plane()
    yield
    await _stop_legacy_control_plane()
    await engine.stop()


RUNTIME_VERSION = "1.0.141"

app = FastAPI(title="Personal Coding Runtime", version=RUNTIME_VERSION, lifespan=lifespan)


@app.middleware("http")
async def inspection_mode_http_guard(request: Request, call_next):
    # A mode flip cannot bypass a parked process latch.
    worker = getattr(app.state, "pcp_local_worker_ready", False)
    if worker or os.getenv("PCP_RUNTIME_STARTUP_MODE") == PCP_LOCAL_WORKER_MODE:
        if (not worker or runtime_startup_mode() != PCP_LOCAL_WORKER_MODE
                or (request.method, request.url.path) not in {
                    ("GET", "/health"), ("POST", "/v1/pcp-local/run-once"),
                    ("POST", "/v1/pcp-local/pm-review")}):
            return JSONResponse(status_code=403, content={"detail": "PCP-local dedicated admission only"})
        return await call_next(request)
    parked = getattr(app.state, "pcp_local_inspection_ready", False)
    if parked or os.getenv("PCP_RUNTIME_STARTUP_MODE") == PCP_LOCAL_INSPECT_MODE:
        if (not parked or runtime_startup_mode() != PCP_LOCAL_INSPECT_MODE
                or request.method != "GET" or request.url.path != "/health"):
            return JSONResponse(status_code=503, content={
                "detail": "PCP-local SOURCE ONLY: inspection APIs parked",
            })
        return await call_next(request)
    if _pcp_local_scope_requested():
        return JSONResponse(status_code=503, content={
            "detail": "PCP-local draft cannot serve legacy Runtime endpoints",
        })
    mode = runtime_startup_mode()
    if mode == F2_WORKER_MODE:
        # Middleware is required even when callers skip FastAPI lifespan.
        try:
            require_f2_worker_environment(os.environ)
        except F2WorkerNotReady:
            return JSONResponse(status_code=503, content={
                "detail": "F2 worker-only environment not authorized"
            })
        if not getattr(engine, "_f2_worker_only", False):
            return JSONResponse(status_code=503, content={
                "detail": "F2 worker-only database and startup not attested"
            })
        if not f2_direct_intake_route_allowed(request.method, request.url.path):
            return JSONResponse(status_code=403, content={
                "detail": "F2 direct-intake only: forbidden endpoint"
            })
    elif mode == FULLPATH_CANDIDATE_MODE or parked_fullpath_environment(os.environ):
        # Even a caller that bypasses lifespan or flips mode=normal cannot
        # reach generic job, PM review or legacy administrative endpoints.
        return JSONResponse(status_code=503, content={
            "detail": "G0 full-path candidate is source-only, not activated"
        })
    # GET handlers may also lazy-initialize mutable stores. Never expose the
    # normal dashboard, PM Bridge, planner, generic job or control endpoints.
    if mode == "inspect" and (
        request.method != "GET" or request.url.path != "/health"
    ):
        return JSONResponse(
            status_code=503,
            content={"detail": "Runtime inspection mode: mutation and dashboard APIs disabled"},
        )
    if mode == "g0_fixture_run" and not g0_fixture_allowed_route(
        request.method, request.url.path
    ):
        return JSONResponse(
            status_code=503,
            content={"detail": "G0 fixture mode: only exact fixture job endpoints enabled"},
        )
    return await call_next(request)


def g0_fixture_allowed_route(method: str, path: str) -> bool:
    if method == "GET" and path == "/health":
        return True
    if method == "POST" and path == "/v1/g0-fixture/prepare":
        return True
    match = __import__("re").fullmatch(
        r"/v1/g0-fixture/jobs/([0-9a-f]{32})(?:/(execute|deliver))?", path
    )
    if match is None:
        return False
    return method == ("GET" if match.group(2) is None else "POST")


def _require_g0_runtime_mode() -> None:
    # The G0 endpoints exist in source for testability, but must never become
    # callable through the existing multi-project normal Runtime.
    if runtime_startup_mode() != "g0_fixture_run":
        raise HTTPException(403, "G0 fixture endpoints require their isolated Runtime mode")


def g0_view(row: dict[str, Any]) -> dict[str, Any]:
    """Keep the G0 response bounded; no prompts, secrets or provider raw logs."""
    result = row.get("result") or {}
    return {
        "job_id": row["id"],
        "project_id": row["project_id"],
        "status": row["status"],
        "source_commit": row.get("source_commit"),
        "branch": row.get("branch"),
        "result": {
            key: result.get(key) for key in (
                "stage", "commit", "changed_files", "verification_policy",
                "workflow_blob", "codex_cli_version", "deterministic_ci",
                "pull_request",
            ) if key in result
        },
    }


@app.post("/v1/g0-fixture/prepare", dependencies=[Depends(auth)])
async def g0_prepare() -> dict[str, Any]:
    _require_g0_runtime_mode()
    try:
        return g0_view(await g0_fixture_runner.prepare())
    except G0GateError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/v1/g0-fixture/jobs/{job_id}/execute", dependencies=[Depends(auth)])
async def g0_execute(job_id: str) -> dict[str, Any]:
    _require_g0_runtime_mode()
    try:
        return g0_view(await g0_fixture_runner.execute(job_id))
    except G0GateError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/v1/g0-fixture/jobs/{job_id}/deliver", dependencies=[Depends(auth)])
async def g0_deliver(job_id: str) -> dict[str, Any]:
    _require_g0_runtime_mode()
    try:
        return g0_view(await g0_fixture_runner.deliver(job_id))
    except G0GateError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/v1/g0-fixture/jobs/{job_id}", dependencies=[Depends(auth)])
def g0_status(job_id: str) -> dict[str, Any]:
    _require_g0_runtime_mode()
    try:
        return g0_view(g0_fixture_runner.current(job_id))
    except G0GateError as exc:
        raise HTTPException(404, str(exc)) from exc


app.include_router(pm_bridge_router)
app.include_router(
    create_dashboard_router(
        storage,
        plan_orchestrator.store,
        preview_manager=preview_manager,
        project_preview_manager=project_preview_manager,
    )
)


@app.get("/health", response_model=RuntimeHealth)
async def health() -> RuntimeHealth:
    if getattr(app.state, "pcp_local_inspection_ready", False):
        return RuntimeHealth(
            status="degraded", service="coding-runtime",
            version=RUNTIME_VERSION, router="not_checked", executor="not_checked",
            adapters={"antigravity_host": False, "codex_cli": False, "opencode": False},
        )
    router_ok = await engine.router.health()
    executor_ok = await engine.ddev.health()
    return RuntimeHealth(
        status="ok" if router_ok and executor_ok and runtime_startup_mode() == "normal" else "degraded",
        service="coding-runtime",
        version=RUNTIME_VERSION,
        router="ok" if router_ok else "down",
        executor="ok" if executor_ok else "down",
        adapters={
            "antigravity_host": bool(os.getenv("ANTIGRAVITY_BRIDGE_URL")),
            "codex_cli": shutil.which("codex") is not None,
            "opencode": shutil.which("opencode") is not None,
        },
    )


@app.get("/v1/quota", dependencies=[Depends(auth)])
def quota_view() -> dict[str, Any]:
    return quota_coordinator.view()


@app.get("/v1/telemetry/calibration", dependencies=[Depends(auth)])
def telemetry_calibration(
    project_id: str = Query(..., min_length=1, max_length=200),
    task_type: str = Query(..., min_length=1, max_length=100),
    role: str | None = Query(default=None, max_length=80),
) -> dict[str, Any]:
    return storage.calibration_hint(project_id=project_id, task_type=task_type, role=role)


@app.get("/v1/telemetry/attention/{job_id}", dependencies=[Depends(auth)])
def telemetry_attention(job_id: str) -> dict[str, Any]:
    if not storage.get(job_id):
        raise HTTPException(404, "Unknown job")
    return storage.attention_summary(job_id)


@app.get("/v1/continuity/proposal", dependencies=[Depends(auth)])
def latest_continuity_proposal(
    project_id: str = Query(..., min_length=1, max_length=200),
) -> dict[str, Any]:
    proposal = storage.latest_continuity_proposal(project_id)
    if proposal is None:
        raise HTTPException(404, "No continuity proposal for project")
    return proposal


@app.post("/v1/continuity/events", dependencies=[Depends(auth)])
def record_continuity_event(payload: ContinuityEventRequest) -> dict[str, Any]:
    if payload.job_id:
        _require_legacy_job_mutation(payload.job_id)
    if payload.job_id and not storage.get(payload.job_id):
        raise HTTPException(404, "Unknown job")
    try:
        return storage.record_external_continuity(
            project_id=payload.project_id,
            event_type=payload.event_type,
            job_id=payload.job_id,
            payload=payload.detail,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/v1/dashboard/quota", include_in_schema=False)
def dashboard_quota_view(
    pcp_dashboard_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    _require_session(pcp_dashboard_session)
    return quota_coordinator.view()


@app.post("/v1/plans", response_model=ExecutionPlanView, dependencies=[Depends(auth)])
async def create_execution_plan(payload: PMPlanCreateRequest) -> ExecutionPlanView:
    try:
        row = await pm_planner.create_plan(payload)
    except (RuntimeError, KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    await plan_orchestrator.tick()
    return execution_plan_view(row)


@app.post("/v1/intake", response_model=IntakeResponse, dependencies=[Depends(auth)])
async def intake_ticket(payload: IntakeRequest) -> IntakeResponse:
    try:
        baseline = resolve_project_baseline(payload.project_id, payload.baseline_revision)
        if baseline is None:
            raise ValueError("Canonical intake requires an approved ProjectBaseline")
        decision = classify_intake(
            bounded_direct=payload.bounded_direct,
            semantic=payload.semantic, repo_hints=payload.repo_hints,
        )
        if payload.execution_mode == "supervised" and decision.mode != "planning":
            raise ValueError(
                "Supervised execution mode requires planning intake; direct intake classification cannot be overridden"
            )
        result = {**decision.model_dump(), "baseline_revision": baseline.revision}
        if decision.mode == "planning":
            plan = await create_execution_plan(PMPlanCreateRequest(
                project_id=payload.project_id, ticket=payload.ticket,
                baseline_revision=baseline.revision,
                planning_profile=payload.planning_profile,
                provider_state=payload.provider_state,
                decomposition_required=decision.decomposition_required,
                execution_mode=payload.execution_mode,
                semantic=payload.semantic, repo_hints=payload.repo_hints,
            ))
            return PlanningIntakeResponse(**result, plan={"id": plan.id, "status": plan.status})
        request = JobCreateRequest(
            project_id=payload.project_id,
            task=TaskInput(
                title=payload.ticket.title, description=payload.ticket.description,
                semantic=payload.semantic,
            ),
            baseline_revision=baseline.revision, repo_hints=payload.repo_hints,
            provider_state={key: state.model_dump(mode="json") for key, state in payload.provider_state.items()},
            auto_run=payload.auto_run,
        )
        job_id = await _create_local_job_guarded(
            request,
            intake_decision=decision,
        )
    except (RuntimeError, KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    row = storage.get(job_id)
    assert row is not None
    return DirectIntakeResponse(**result, job={"id": job_id, "status": row["status"]})


@app.get("/v1/plans/{plan_id}", response_model=ExecutionPlanView, dependencies=[Depends(auth)])
def get_execution_plan(plan_id: str) -> ExecutionPlanView:
    row = storage.get_execution_plan(plan_id)
    if not row:
        raise HTTPException(404, "ExecutionPlan not found")
    return execution_plan_view(row)


@app.get("/v1/plans/{plan_id}/orchestration", dependencies=[Depends(auth)])
def get_plan_orchestration(plan_id: str) -> dict[str, Any]:
    result = plan_orchestrator.view(plan_id)
    if result is None:
        raise HTTPException(404, "Plan is not registered for orchestration")
    return result


@app.get("/v1/plans/{plan_id}/progress", dependencies=[Depends(auth)])
def get_plan_progress(plan_id: str) -> dict[str, Any]:
    result = plan_orchestrator.progress(plan_id)
    if result is None:
        raise HTTPException(404, "Plan is not registered for orchestration")
    return result


@app.post("/v1/plans/{plan_id}/continue", dependencies=[Depends(auth)])
async def continue_execution_plan(
    plan_id: str,
    payload: PlanContinuationRequest,
) -> dict[str, Any]:
    try:
        return await plan_orchestrator.continue_plan(
            plan_id=plan_id,
            generation=payload.generation,
            continuation_key=payload.continuation_key,
            checkpoint_id=payload.checkpoint_id,
            checkpoint_key=payload.checkpoint_key,
            ready_work_order_ids=payload.ready_work_order_ids,
        )
    except PlanContinuationConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/v1/plans/{plan_id}/work-orders/{work_order_id}/operator", dependencies=[Depends(auth)])
async def resolve_operator_work_order(
    plan_id: str,
    work_order_id: str,
    payload: OperatorResolutionRequest,
) -> dict[str, Any]:
    try:
        return await plan_orchestrator.resolve_operator(
            plan_id=plan_id,
            work_order_id=work_order_id,
            action=payload.action,
            note=payload.note,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/v1/plans/{plan_id}/work-orders/{work_order_id}/supersede", dependencies=[Depends(auth)])
def supersede_orchestrated_work_order(
    plan_id: str,
    work_order_id: str,
    payload: WorkOrderSupersessionRequest,
) -> dict[str, Any]:
    """Explicitly retire exact orchestration identity without touching its job."""
    try:
        return plan_orchestrator.store.supersede_work_order(
            plan_id=plan_id,
            work_order_id=work_order_id,
            reason=payload.reason,
            superseded_by_plan_id=payload.superseded_by_plan_id,
            superseded_by_work_order_id=payload.superseded_by_work_order_id,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/v1/orchestrator/tick", dependencies=[Depends(auth)])
async def orchestrator_tick() -> dict[str, Any]:
    return await plan_orchestrator.tick()


@app.post("/v1/notifications/claim", dependencies=[Depends(auth)])
def claim_notification(lease_seconds: int = Query(300, ge=30, le=1800)) -> dict[str, Any]:
    event = plan_orchestrator.store.claim_notification(lease_seconds=lease_seconds)
    return {"event": dict(event) if event else None}


@app.post("/v1/notifications/{event_id}/ack", dependencies=[Depends(auth)])
def ack_notification(event_id: int) -> dict[str, Any]:
    if event_id < 1:
        raise HTTPException(422, "event_id must be positive")
    if not plan_orchestrator.store.ack_notification(event_id):
        raise HTTPException(409, "Notification is not currently claimed")
    return {"status": "sent", "event_id": event_id}


@app.post("/v1/notifications/{event_id}/release", dependencies=[Depends(auth)])
def release_notification(event_id: int, payload: NotificationReleaseRequest) -> dict[str, Any]:
    if event_id < 1:
        raise HTTPException(422, "event_id must be positive")
    if not plan_orchestrator.store.release_notification(
        event_id,
        error=payload.error,
        retry_seconds=payload.retry_seconds,
    ):
        raise HTTPException(409, "Notification is not currently claimed")
    return {"status": "pending", "event_id": event_id}


@app.post("/v1/control-actions/{action_id}/execute", dependencies=[Depends(auth)])
async def execute_control_action(
    action_id: str,
    payload: ControlActionExecuteRequest,
) -> dict[str, Any]:
    if not action_id or len(action_id) > 100:
        raise HTTPException(422, "Invalid control action id")
    try:
        return await plan_orchestrator.controls.execute(
            action_id,
            telegram_user_id=payload.telegram_user_id,
            telegram_chat_id=payload.telegram_chat_id,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/v1/g0-fullpath/jobs/{job_id}/pm-review", dependencies=[Depends(auth)])
async def finalize_fullpath_pm_review(
    job_id: str, payload: FullpathPMReviewRequest,
) -> dict[str, Any]:
    """One exact-HEAD PM acceptance, with fresh GitHub proof and atomic state.

    The future fixture must pass a separate full runtime/source identity guard.
    This route is 503 in the non-executable fullpath candidate mode.
    """
    _require_legacy_job_mutation(job_id)
    try:
        return await fullpath_pm_review.finalize(job_id, payload)
    except (RuntimeError, ValueError) as exc:
        # Never echo GitHub review bodies, credentials, URLs or model output.
        raise HTTPException(409, str(exc)[:200]) from exc


@app.post("/v1/jobs", response_model=JobView, dependencies=[Depends(auth)])
async def create_job(payload: JobCreateRequest) -> JobView:
    try:
        if runtime_startup_mode() == F2_WORKER_MODE:
            require_f2_worker_environment(os.environ)
            if not getattr(engine, "_f2_worker_only", False):
                raise F2WorkerNotReady("F2 worker database not attested")
            if not (
                payload.project_id == "pcp-g0-fullpath-fixture"
                and payload.work_order is None
                and payload.task is not None
                and payload.source_commit == F2_V2_SEED
                and payload.baseline_revision == F2_V2_REVISION
                and payload.auto_run is True
                and payload.dry_run is False
                and not payload.provider_state
            ):
                raise F2WorkerNotReady("F2 permits one exact v2 direct-intake task")
            # Require genuine canonical direct evidence, not a caller-declared
            # label. Unknown or protected scope fails BEFORE any durable job
            # insertion, provider call or workspace creation.
            decision = classify_intake(
                bounded_direct=True,
                semantic=payload.task.semantic,
                repo_hints=payload.repo_hints,
            )
            if decision.mode != "direct" or decision.decomposition_required:
                raise F2WorkerNotReady(
                    "F2 single-job trial requires canonical bounded direct intake"
                )
            async with _f2_single_job_intake_lock:
                if storage.list(limit=1):
                    raise F2WorkerNotReady("F2 already has a job: preserve current evidence")
                job_id = await _create_local_job_guarded(
                    payload, intake_decision=decision,
                )
        else:
            job_id = await _create_local_job_guarded(payload)
    except (RuntimeError, KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    row = storage.get(job_id)
    assert row is not None
    return view(row)


@app.get("/v1/jobs", response_model=JobList, dependencies=[Depends(auth)])
def list_jobs(limit: int = Query(50, ge=1, le=500)) -> JobList:
    return JobList(jobs=[view(row) for row in storage.list(limit)])


@app.get(
    "/v1/jobs/active-count",
    response_model=ActiveEngineeringWorkCount,
    dependencies=[Depends(auth)],
)
def active_engineering_work_count() -> ActiveEngineeringWorkCount:
    return ActiveEngineeringWorkCount(
        active_engineering_jobs=(
            storage.count_active_engineering_jobs()
            + plan_orchestrator.late_reviews.store.active_count()
        )
    )


@app.get("/v1/jobs/{job_id}", response_model=JobView, dependencies=[Depends(auth)])
def get_job(job_id: str) -> JobView:
    row = storage.get(job_id)
    if not row:
        raise HTTPException(404, "Unknown job")
    return view(row)


@app.post(
    "/v1/jobs/{job_id}/collaborations",
    response_model=CollaborationView,
    dependencies=[Depends(auth)],
)
async def create_collaboration(job_id: str, payload: CollaborationCreateRequest) -> CollaborationView:
    _require_manual_collaboration_state(job_id)
    try:
        return await collaboration_manager.create(job_id, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise runtime_error(exc) from exc


@app.get(
    "/v1/jobs/{job_id}/collaborations",
    response_model=list[CollaborationView],
    dependencies=[Depends(auth)],
)
def list_collaborations(job_id: str) -> list[CollaborationView]:
    try:
        return collaboration_manager.list(job_id)
    except RuntimeError as exc:
        raise runtime_error(exc) from exc


@app.get(
    "/v1/jobs/{job_id}/collaborations/{thread_id}",
    response_model=CollaborationView,
    dependencies=[Depends(auth)],
)
def get_collaboration(job_id: str, thread_id: str) -> CollaborationView:
    try:
        return collaboration_manager.get(job_id, thread_id)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post(
    "/v1/jobs/{job_id}/collaborations/{thread_id}/recheck",
    response_model=CollaborationView,
    dependencies=[Depends(auth)],
)
async def recheck_collaboration(
    job_id: str,
    thread_id: str,
    payload: CollaborationRecheckRequest,
) -> CollaborationView:
    _require_manual_collaboration_state(job_id)
    try:
        return await collaboration_manager.recheck(job_id, thread_id, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise runtime_error(exc) from exc


@app.post(
    "/v1/jobs/{job_id}/collaborations/{thread_id}/cancel",
    response_model=CollaborationView,
    dependencies=[Depends(auth)],
)
async def cancel_collaboration(job_id: str, thread_id: str) -> CollaborationView:
    _require_legacy_job_mutation(job_id)
    try:
        return await collaboration_manager.cancel(job_id, thread_id)
    except RuntimeError as exc:
        raise runtime_error(exc) from exc


@app.post(
    "/v1/jobs/{job_id}/advance-source",
    response_model=JobView,
    dependencies=[Depends(auth)],
)
async def advance_job_source(
    job_id: str,
    payload: JobSourceAdvanceRequest,
) -> JobView:
    _require_legacy_job_mutation(job_id)
    try:
        orchestration_resume = prepare_orchestrated_job_resume(
            plan_orchestrator.store,
            job_id,
        )
        row = await engine.advance_direct_job_source(
            job_id,
            expected_old_source=payload.expected_old_source,
            expected_new_source=payload.expected_new_source,
            _allow_failed_orchestrated_recovery=bool(
                orchestration_resume and orchestration_resume.get("reopen")
            ),
        )
    except RuntimeError as exc:
        raise runtime_error(exc) from exc
    return view(row)


@app.post("/v1/jobs/{job_id}/run", response_model=JobView, dependencies=[Depends(auth)])
async def run_job(job_id: str, payload: JobRunRequest | None = None) -> JobView:
    request = payload or JobRunRequest()
    try:
        if runtime_startup_mode() == F2_WORKER_MODE:
            require_f2_worker_environment(os.environ)
            if (
                job_id != F2_REENTRY_JOB_ID
                or not getattr(engine, "_f2_worker_only", False)
                or request.reset_transient_provider_failures
                or request.reroute
                or request.verification_only_after_pm_handoff
            ):
                raise F2WorkerNotReady("F2 one-job resume is not authorized")
            async with _f2_single_job_intake_lock:
                _require_legacy_job_mutation(job_id)
                # No planner/PM orchestration, provider-state reset, reroute,
                # budget increase, replay or new job. A second request sees
                # status=queued and fails the same exact blocked-row gate.
                require_f2_exact_blocked_job(storage.get(job_id))
                if engine.active_jobs or not engine.queue.empty():
                    raise F2WorkerNotReady("F2 one-job worker is already active")
                row = await engine.resume(job_id)
        else:
            _require_legacy_job_mutation(job_id)
            orchestration_resume = prepare_orchestrated_job_resume(plan_orchestrator.store, job_id)
            row = await engine.resume(
                job_id,
                reset_transient_provider_failures=request.reset_transient_provider_failures,
                reroute=request.reroute,
                verification_only_after_pm_handoff=request.verification_only_after_pm_handoff,
                _allow_failed_orchestrated_resume=bool(
                    orchestration_resume and orchestration_resume.get("reopen")
                ),
            )
            reopen_orchestrated_job(plan_orchestrator.store, orchestration_resume, job_id)
    except RuntimeError as exc:
        raise runtime_error(exc) from exc
    return view(row)


@app.post(
    "/v1/jobs/{job_id}/review-repair",
    response_model=JobView,
    dependencies=[Depends(auth)],
)
async def request_review_repair(job_id: str, payload: ReviewRepairRequest) -> JobView:
    _require_legacy_job_mutation(job_id)
    try:
        row = await engine.request_review_repair(
            job_id,
            expected_commit=payload.expected_commit,
            finding=payload.finding,
            evidence=payload.evidence,
            references=payload.references,
        )
    except RuntimeError as exc:
        raise runtime_error(exc) from exc
    return view(row)


@app.post("/v1/jobs/{job_id}/cancel", response_model=JobView, dependencies=[Depends(auth)])
async def cancel_job(job_id: str) -> JobView:
    _require_legacy_job_mutation(job_id)
    try:
        await engine.ddev.cancel(job_id=job_id)
        active = engine.active_jobs.get(job_id)
        if active and not active.done():
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
        row = await engine.cancel(job_id)
    except RuntimeError as exc:
        raise runtime_error(exc) from exc
    return view(row)


@app.post("/v1/jobs/{job_id}/decision", response_model=JobView, dependencies=[Depends(auth)])
async def resolve_decision(job_id: str, payload: HumanDecisionRequest) -> JobView:
    _require_legacy_job_mutation(job_id)
    try:
        row = await engine.resolve_human_decision(
            job_id,
            action=payload.action,
            note=payload.note,
            expected_decision_key=payload.decision_key,
        )
    except RuntimeError as exc:
        raise runtime_error(exc) from exc
    await plan_orchestrator.tick()
    return view(row)


@app.post("/v1/jobs/{job_id}/cleanup", dependencies=[Depends(auth)])
async def cleanup_job(
    job_id: str,
    remove_workspace: bool = False,
    release_ddev_data: bool = False,
) -> dict[str, Any]:
    _require_legacy_job_mutation(job_id)
    try:
        return await engine.cleanup(
            job_id,
            remove_workspace=remove_workspace,
            release_ddev_data=release_ddev_data,
        )
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/v1/pcp-local/run-once", dependencies=[Depends(auth)])
async def pcp_local_run_once():
    if (not getattr(app.state, "pcp_local_worker_ready", False)
            or runtime_startup_mode() != PCP_LOCAL_WORKER_MODE):
        raise HTTPException(403, "PCP-local dedicated startup required")
    from .pcp_local_task_queue import TaskStop
    try:
        row = await engine.run_pcp_local_once()
    except TaskStop as exc:
        raise HTTPException(409, exc.code) from None
    return {"job_id": row["id"], "status": row["status"], "can_merge": False}


@app.post("/v1/pcp-local/pm-review", dependencies=[Depends(auth)])
async def pcp_local_pm_review(payload: FullpathPMReviewRequest):
    if (not getattr(app.state, "pcp_local_worker_ready", False)
            or runtime_startup_mode() != PCP_LOCAL_WORKER_MODE):
        raise HTTPException(403, "PCP-local dedicated startup required")
    from .pcp_local_task_queue import TaskStop
    try:
        return await engine.finalize_pcp_local_review(payload)
    except TaskStop as exc:
        raise HTTPException(409, exc.code) from None
