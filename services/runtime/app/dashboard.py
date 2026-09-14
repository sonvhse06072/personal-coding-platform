from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .activity import public_event
from .dashboard_ui_activity import DASHBOARD_HTML


_ACTIVE_PLAN_STATES = {"active", "executing", "waiting_merge", "waiting_human"}
_ACTIVE_JOB_STATES = {"queued", "routing", "planning", "executing", "verifying", "evaluating", "delivering"}
_PLACEHOLDERS = {"", "CHANGE_ME", "change-me"}
_COOKIE = "pcp_dashboard_session"


class DashboardLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=512)


def _dashboard_secret() -> str:
    return os.getenv("DASHBOARD_READ_TOKEN", "").strip()


def _session_value(secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), b"pcp-dashboard-session-v1", hashlib.sha256).hexdigest()


def _require_session(session: str | None) -> None:
    secret = _dashboard_secret()
    if secret in _PLACEHOLDERS:
        raise HTTPException(503, "Dashboard read token is not configured")
    if not session or not hmac.compare_digest(session, _session_value(secret)):
        raise HTTPException(401, "Dashboard session required")


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _recent_events(storage: Any, job_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    rows = storage.recent_events(job_ids, per_job_limit=40)
    grouped: dict[str, list[dict[str, Any]]] = {job_id: [] for job_id in job_ids}
    for row in rows:
        event = public_event(row)
        if event is not None:
            grouped.setdefault(str(row.get("job_id")), []).append(event)
    return grouped


def _budget_view(job: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    strategy = ((job.get("route") or {}).get("strategy") or {})
    budget = dict(strategy.get("budget") or {})
    progress = dict(job.get("progress") or {})
    pairs = {
        "model_calls": "max_model_calls",
        "tool_calls": "max_tool_calls",
        "test_runs": "max_test_runs",
        "repair_iterations": "max_repair_iterations",
        "iteration": "max_iterations",
    }
    remaining: dict[str, Any] = {}
    for used_key, budget_key in pairs.items():
        if budget_key in budget:
            try:
                remaining[used_key] = max(0, int(budget[budget_key]) - int(progress.get(used_key, 0)))
            except (TypeError, ValueError):
                pass
    if "max_wall_time_minutes" in budget:
        try:
            remaining["wall_time_minutes"] = round(
                max(0.0, float(budget["max_wall_time_minutes"]) - float(progress.get("elapsed_minutes", 0.0))),
                3,
            )
        except (TypeError, ValueError):
            pass
    return budget, remaining


def _model_view(job: dict[str, Any]) -> dict[str, Any]:
    route = job.get("route") or {}
    strategy = route.get("strategy") or {}
    models = {
        role: dict(strategy.get(role) or {}) if strategy.get(role) else None
        for role in ("planner", "executor", "evaluator")
    }
    checkpoint = job.get("checkpoint") or {}
    current = None
    for key in ("evaluator_choice", "executor_choice", "planner_choice"):
        if checkpoint.get(key):
            current = dict(checkpoint[key])
            break
    models["current"] = current
    return models


def _token_view(job: dict[str, Any]) -> dict[str, Any]:
    progress = job.get("progress") or {}
    return {
        key: progress.get(key, 0)
        for key in (
            "input_tokens",
            "cached_input_tokens",
            "input_budget_tokens",
            "output_tokens",
            "thinking_tokens",
        )
    }


def _job_snapshot(job: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    budget, remaining = _budget_view(job)
    progress = dict(job.get("progress") or {})
    return {
        "id": job["id"],
        "project_id": job["project_id"],
        "status": job["status"],
        "source_commit": job.get("source_commit"),
        "branch": job.get("branch"),
        "workspace": job.get("workspace"),
        "updated_at": _json_value(job.get("updated_at")),
        "progress": progress,
        "budget": budget,
        "remaining": remaining,
        "tokens": _token_view(job),
        "models": _model_view(job),
        "recent_events": events,
        "result": job.get("result"),
        "error": job.get("error"),
    }


def _plan_snapshot(plan: dict[str, Any], rows: list[dict[str, Any]], jobs: dict[str, dict[str, Any]], events: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    work_orders: list[dict[str, Any]] = []
    current_work_order_id = None
    for row in rows:
        job_id = row.get("job_id")
        job = jobs.get(str(job_id)) if job_id else None
        state = str(row.get("state") or "")
        if current_work_order_id is None and state in {"running", "blocked", "waiting_human", "awaiting_merge"}:
            current_work_order_id = row["work_order_id"]
        work_orders.append({
            "id": row["work_order_id"],
            "sequence_no": row.get("sequence_no"),
            "execution_mode": row.get("execution_mode"),
            "state": state,
            "job_id": job_id,
            "pr_number": row.get("pr_number"),
            "pr_url": row.get("pr_url"),
            "detail": row.get("detail") or {},
            "job": _job_snapshot(job, events.get(str(job_id), [])) if job else None,
        })
    return {
        "id": plan["plan_id"],
        "project_id": plan["project_id"],
        "status": plan["status"],
        "ticket_id": plan.get("ticket_id"),
        "ticket_title": plan.get("ticket_title"),
        "github_url": plan.get("github_url"),
        "baseline_revision": plan.get("baseline_revision"),
        "current_work_order_id": current_work_order_id,
        "updated_at": _json_value(plan.get("updated_at")),
        "work_orders": work_orders,
    }


def build_snapshot(storage: Any, orchestrator_store: Any) -> dict[str, Any]:
    plan_rows = orchestrator_store.list_orchestrations(limit=25)
    work_order_rows: dict[str, list[dict[str, Any]]] = {}
    job_ids: list[str] = []
    for plan in plan_rows:
        rows = orchestrator_store.work_orders(plan["plan_id"])
        work_order_rows[plan["plan_id"]] = rows
        job_ids.extend(str(row["job_id"]) for row in rows if row.get("job_id"))
    events = _recent_events(storage, job_ids)
    jobs = {
        job_id: job
        for job_id in job_ids
        if (job := storage.get(job_id)) is not None
    }
    plans = [
        _plan_snapshot(plan, work_order_rows.get(plan["plan_id"], []), jobs, events)
        for plan in plan_rows
    ]
    active_plans = [plan for plan in plans if plan["status"] in _ACTIVE_PLAN_STATES]
    all_jobs = [wo["job"] for plan in plans for wo in plan["work_orders"] if wo.get("job")]
    alerts = orchestrator_store.notifications(limit=10)
    current_plan = next((plan for plan in active_plans if plan["status"] == "executing"), None)
    if current_plan is None:
        current_plan = next(iter(active_plans), None)
    if current_plan is None:
        current_plan = next(iter(plans), None)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_plan_id": current_plan["id"] if current_plan else None,
        "summary": {
            "active_plans": len(active_plans),
            "active_jobs": sum(1 for job in all_jobs if job["status"] in _ACTIVE_JOB_STATES),
            "waiting_merge": sum(1 for plan in plans for wo in plan["work_orders"] if wo["state"] == "awaiting_merge"),
            "waiting_human": sum(1 for plan in plans for wo in plan["work_orders"] if wo["state"] == "waiting_human"),
            "blocked_plans": sum(1 for plan in plans if plan["status"] == "blocked"),
            "pending_notifications": sum(1 for item in alerts if item.get("status") == "pending"),
        },
        "plans": plans,
        "alerts": [
            {
                "event_type": item.get("event_type"),
                "status": item.get("status"),
                "summary": item.get("summary"),
                "created_at": _json_value(item.get("created_at")),
            }
            for item in alerts
        ],
    }


def create_dashboard_router(storage: Any, orchestrator_store: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/dashboard", response_class=HTMLResponse)
    def dashboard() -> str:
        return DASHBOARD_HTML

    @router.post("/v1/dashboard/session", status_code=204)
    def dashboard_session(payload: DashboardLogin, response: Response) -> None:
        secret = _dashboard_secret()
        if secret in _PLACEHOLDERS:
            raise HTTPException(503, "Dashboard read token is not configured")
        if not hmac.compare_digest(payload.token, secret):
            raise HTTPException(401, "Invalid dashboard token")
        response.set_cookie(
            _COOKIE,
            _session_value(secret),
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
        )

    @router.get("/v1/dashboard/snapshot")
    def dashboard_snapshot(pcp_dashboard_session: str | None = Cookie(default=None)) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        return build_snapshot(storage, orchestrator_store)

    @router.get("/v1/dashboard/jobs/{job_id}/stream")
    async def dashboard_stream(
        job_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> StreamingResponse:
        _require_session(pcp_dashboard_session)
        if storage.get(job_id) is None:
            raise HTTPException(404, "Unknown job")

        async def events():
            cursor = int(after)
            while True:
                if await request.is_disconnected():
                    return
                rows = await asyncio.to_thread(storage.events_after, job_id, cursor, 100)
                if rows:
                    for row in rows:
                        cursor = max(cursor, int(row.get("id") or 0))
                        event = public_event(row)
                        if event is None:
                            continue
                        payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
                        yield f"id: {cursor}\nevent: activity\ndata: {payload}\n\n"
                else:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.75)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return router
