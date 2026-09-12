from __future__ import annotations

import asyncio
import os
import secrets
import shutil
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from .engine import RuntimeEngine
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


storage = Storage()
engine = RuntimeEngine(storage)


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
    executor = checkpoint.get("executor_choice") or strategy.get("executor") or {}
    return JobView(
        id=row["id"], project_id=row["project_id"], status=row["status"], source_commit=row.get("source_commit"),
        baseline_revision=baseline.get("revision"),
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
    await engine.start()
    yield
    await engine.stop()


app = FastAPI(title="Personal Coding Runtime", version="1.0.18", lifespan=lifespan)


@app.get("/health", response_model=RuntimeHealth)
async def health() -> RuntimeHealth:
    router_ok = await engine.router.health()
    executor_ok = await engine.ddev.health()
    return RuntimeHealth(
        status="ok" if router_ok and executor_ok else "degraded",
        service="coding-runtime",
        version="1.0.18",
        router="ok" if router_ok else "down",
        executor="ok" if executor_ok else "down",
        adapters={
            "antigravity_host": bool(os.getenv("ANTIGRAVITY_BRIDGE_URL")),
            "codex_cli": shutil.which("codex") is not None,
            "opencode": shutil.which("opencode") is not None,
        },
    )


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
        raise HTTPException(404, "Job not found")
    return view(row)


@app.post("/v1/jobs/{job_id}/run", response_model=JobView, dependencies=[Depends(auth)])
async def run_job(job_id: str, payload: JobRunRequest | None = None) -> JobView:
    request = payload or JobRunRequest()
    try:
        row = await engine.resume(
            job_id,
            reset_transient_provider_failures=request.reset_transient_provider_failures,
        )
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
    return view(row)


@app.post("/v1/jobs/{job_id}/cleanup", dependencies=[Depends(auth)])
async def cleanup_job(job_id: str, remove_workspace: bool = False) -> dict[str, Any]:
    try:
        return await engine.cleanup(job_id, remove_workspace=remove_workspace)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc
