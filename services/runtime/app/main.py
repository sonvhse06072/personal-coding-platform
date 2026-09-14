from __future__ import annotations

import asyncio
import os
import secrets
import shutil
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .dashboard import create_dashboard_router
from .engine import RuntimeEngine
from .orchestrator_notifications import PlanOrchestrator
from .orchestrator_resume import prepare_orchestrated_job_resume, reopen_orchestrated_job
from .pm_bridge import router as pm_bridge_router
from .pm_planning import (
    ExecutionPlanView,
    PMPlanCreateRequest,
    PMPlanner,
    execution_plan_view,
)
from .schemas import (
    HumanDecisionRequest,
    JobCreateRequest,
    JobList,
    JobRunRequest,
    JobView,
    RuntimeHealth,
)
from .security import harden_runtime_process_secret_boundary
from .storage import Storage


class OperatorResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["complete", "block"]
    note: str = Field(default="", max_length=2000)


class NotificationReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1, max_length=1000)
    retry_seconds: int = Field(default=60, ge=5, le=3600)


class ControlActionExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_user_id: str = Field(min_length=1, max_length=100)
    telegram_chat_id: str = Field(min_length=1, max_length=100)


storage = Storage()
engine = RuntimeEngine(storage)
pm_planner = PMPlanner(storage)
plan_orchestrator = PlanOrchestrator(storage, engine)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Coding agents run as child processes of Runtime. Harden the long-running
    # parent before any job can launch so a same-UID child cannot recover Runtime
    # credentials from procfs even though both processes share one container.
    harden_runtime_process_secret_boundary()
    # Storage initialization inside engine.start() also marks any in-flight PM
    # planning turn interrupted. Neither coding jobs nor PM model calls are
    # silently replayed after an uncertain process restart.
    await engine.start()
    await plan_orchestrator.start()
    yield
    await plan_orchestrator.stop()
    await engine.stop()


app = FastAPI(title="Personal Coding Runtime", version="1.0.34", lifespan=lifespan)
app.include_router(pm_bridge_router)
app.include_router(create_dashboard_router(storage, plan_orchestrator.store))


@app.get("/health", response_model=RuntimeHealth)
async def health() -> RuntimeHealth:
    router_ok = await engine.router.health()
    executor_ok = await engine.ddev.health()
    return RuntimeHealth(
        status="ok" if router_ok and executor_ok else "degraded",
        service="coding-runtime",
        version="1.0.34",
        router="ok" if router_ok else "down",
        executor="ok" if executor_ok else "down",
        adapters={
            "antigravity_host": bool(os.getenv("ANTIGRAVITY_BRIDGE_URL")),
            "codex_cli": shutil.which("codex") is not None,
            "opencode": shutil.which("opencode") is not None,
        },
    )


@app.post("/v1/plans", response_model=ExecutionPlanView, dependencies=[Depends(auth)])
async def create_execution_plan(payload: PMPlanCreateRequest) -> ExecutionPlanView:
    try:
        row = await pm_planner.create_plan(payload)
    except (RuntimeError, KeyError, ValueError) as exc:
        # Pre-flight governance/configuration errors occur before a durable plan
        # row is created. Model/runtime failures after persistence are returned as
        # a durable `failed` ExecutionPlan instead of being lost in an HTTP error.
        raise HTTPException(422, str(exc)) from exc
    # The background orchestrator discovers eligible newly-created plans from the
    # durable creation timestamp. This explicit tick removes normal polling delay
    # without changing that registration boundary.
    await plan_orchestrator.tick()
    return execution_plan_view(row)


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
        job_id = engine.create_job(payload.model_dump(mode="json"))
    except (RuntimeError, KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if payload.auto_run:
        await engine.enqueue(job_id)
    row = storage.get(job_id)
    assert row is not None
    return view(row)


@app.get("/v1/jobs", response_model=JobList, dependencies=[Depends(auth)])
def list_jobs(limit: int = Query(50, ge=1, le=500)) -> JobList:
    return JobList(jobs=[view(row) for row in storage.list(limit)])


@app.get("/v1/jobs/{job_id}", response_model=JobView, dependencies=[Depends(auth)])
def get_job(job_id: str) -> JobView:
    row = storage.get(job_id)
    if not row:
        raise HTTPException(404, "Unknown job")
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
            _allow_failed_orchestrated_resume=bool(
                orchestration_resume and orchestration_resume.get("reopen")
            ),
        )
        reopen_orchestrated_job(plan_orchestrator.store, orchestration_resume, job_id)
    except RuntimeError as exc:
        raise runtime_error(exc) from exc
    return view(row)


@app.post("/v1/jobs/{job_id}/cancel", response_model=JobView, dependencies=[Depends(auth)])
async def cancel_job(job_id: str) -> JobView:
    try:
        # Drain every external side effect before the engine persists the terminal
        # `cancelled` state. DDEV owns Composer/Drush/PHPUnit processes; cancelling
        # the active asyncio task propagates into Codex/OpenCode and the Antigravity
        # adapter, whose CancelledError handler terminates the host-side `agy` run.
        # If Runtime crashes during this drain, the DB remains non-terminal and
        # startup recovery will treat the job as interrupted and clean it again.
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
        )
    except RuntimeError as exc:
        raise runtime_error(exc) from exc
    await plan_orchestrator.tick()
    return view(row)


@app.post("/v1/jobs/{job_id}/cleanup", dependencies=[Depends(auth)])
async def cleanup_job(job_id: str, remove_workspace: bool = False) -> dict[str, Any]:
    try:
        return await engine.cleanup(job_id, remove_workspace=remove_workspace)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc
