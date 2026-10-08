from __future__ import annotations

import asyncio
import os
import secrets
import shutil
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query
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
    row = storage.get(job_id)
    if not row:
        raise HTTPException(404, "Unknown job")
    if row.get("status") not in {"blocked", "interrupted"}:
        raise HTTPException(
            409,
            "Manual collaboration is allowed only for blocked/interrupted jobs; active developer collaboration uses the in-workspace bounded control artifact.",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    harden_runtime_process_secret_boundary()
    await engine.start()
    await plan_orchestrator.start()
    await progress_publisher.start()
    await job_status_publisher.start()
    yield
    await job_status_publisher.stop()
    await progress_publisher.stop()
    await plan_orchestrator.stop()
    await engine.stop()


RUNTIME_VERSION = "1.0.135"

app = FastAPI(title="Personal Coding Runtime", version=RUNTIME_VERSION, lifespan=lifespan)
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
    router_ok = await engine.router.health()
    executor_ok = await engine.ddev.health()
    return RuntimeHealth(
        status="ok" if router_ok and executor_ok else "degraded",
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


@app.post("/v1/jobs", response_model=JobView, dependencies=[Depends(auth)])
async def create_job(payload: JobCreateRequest) -> JobView:
    try:
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
        active_engineering_jobs=storage.count_active_engineering_jobs()
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
    try:
        return await engine.cleanup(
            job_id,
            remove_workspace=remove_workspace,
            release_ddev_data=release_ddev_data,
        )
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc
