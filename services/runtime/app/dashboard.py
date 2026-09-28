from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .activity import public_event
from .dashboard_ui import DASHBOARD_HTML


_ACTIVE_PLAN_STATES = {"active", "executing", "waiting_merge", "waiting_human"}
_ACTIVE_JOB_STATES = {"queued", "routing", "planning", "executing", "verifying", "evaluating", "delivering"}
_STANDALONE_VISIBLE_JOB_STATES = _ACTIVE_JOB_STATES | {"waiting_human", "blocked", "interrupted"}
_PLACEHOLDERS = {"", "CHANGE_ME", "change-me"}
_COOKIE = "pcp_dashboard_session"
_CONTROL_COOKIE = "pcp_dashboard_control_session"


class DashboardLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=512)


class DashboardPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["frontend", "backend", "both"]


def _dashboard_secret() -> str:
    return os.getenv("DASHBOARD_READ_TOKEN", "").strip()


def _dashboard_control_secret() -> str:
    return os.getenv("DASHBOARD_CONTROL_TOKEN", "").strip()


def _session_value(secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), b"pcp-dashboard-session-v1", hashlib.sha256).hexdigest()


def _control_session_value(secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        b"pcp-dashboard-control-session-v1",
        hashlib.sha256,
    ).hexdigest()


def _require_session(session: str | None) -> None:
    secret = _dashboard_secret()
    if secret in _PLACEHOLDERS:
        raise HTTPException(503, "Dashboard read token is not configured")
    if not session or not hmac.compare_digest(session, _session_value(secret)):
        raise HTTPException(401, "Dashboard authentication required")


def _require_control_session(session: str | None) -> None:
    secret = _dashboard_control_secret()
    if secret in _PLACEHOLDERS:
        raise HTTPException(503, "Dashboard control token is not configured")
    if not session or not hmac.compare_digest(
        session,
        _control_session_value(secret),
    ):
        raise HTTPException(401, "Dashboard preview controls are locked")


def _preview_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    return HTTPException(404 if message == "Unknown job" else 409, message)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _choice(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value:
        return None
    return {
        "id": value.get("id"),
        "provider": value.get("provider"),
        "adapter": value.get("adapter"),
        "model": value.get("model"),
        "reasoning_effort": value.get("reasoning_effort"),
        "score": value.get("score"),
        "predicted_success": value.get("predicted_success"),
    }


def _remaining(used: Any, maximum: Any, *, integer: bool = True) -> int | float | None:
    if maximum is None:
        return None
    value = max(0.0, float(maximum or 0) - float(used or 0))
    return int(value) if integer else round(value, 3)


def _job_snapshot(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    route = dict(job.get("route") or {})
    strategy = dict(route.get("strategy") or {})
    checkpoint = dict(job.get("checkpoint") or {})
    progress = dict(job.get("progress") or {})
    result = dict(job.get("result") or {})
    budget = dict(strategy.get("budget") or {})

    planner = _choice(checkpoint.get("planner_choice") or strategy.get("planner"))
    executor = _choice(checkpoint.get("executor_choice") or strategy.get("executor"))
    evaluator = _choice(checkpoint.get("evaluator_choice") or strategy.get("evaluator"))
    status = str(job.get("status") or "")
    current_model = planner if status == "planning" else evaluator if status == "evaluating" else executor

    attempts = list(progress.get("agent_attempts") or [])
    attempt_usage = dict((attempts[-1] if attempts else {}).get("usage") or {})
    remaining = {
        "input_tokens": _remaining(progress.get("input_tokens"), budget.get("max_input_tokens")),
        "output_tokens": _remaining(progress.get("output_tokens"), budget.get("max_output_tokens")),
        "model_calls": _remaining(progress.get("model_calls"), budget.get("max_model_calls")),
        "tool_calls": _remaining(progress.get("tool_calls"), budget.get("max_tool_calls")),
        "test_runs": _remaining(progress.get("test_runs"), budget.get("max_test_runs")),
        "wall_time_minutes": _remaining(
            progress.get("elapsed_minutes"), budget.get("max_wall_time_minutes"), integer=False
        ),
        "changed_files": _remaining(progress.get("changed_files"), budget.get("max_changed_files")),
        "iterations": _remaining(progress.get("iteration"), budget.get("max_iterations")),
        "repair_iterations": _remaining(
            progress.get("repair_iterations"), budget.get("max_repair_iterations")
        ),
    }
    return {
        "id": job.get("id"),
        "project_id": job.get("project_id"),
        "status": status,
        "result_reason": result.get("reason"),
        "branch": job.get("branch"),
        "source_commit": job.get("source_commit"),
        "workspace_mode": str(checkpoint.get("workspace_mode") or "isolated_clone"),
        "created_at": _iso(job.get("created_at")),
        "updated_at": _iso(job.get("updated_at")),
        "complexity_score": route.get("complexity_score"),
        "profile": strategy.get("profile"),
        "analysis_depth": strategy.get("analysis_depth"),
        "models": {
            "planner": planner,
            "executor": executor,
            "evaluator": evaluator,
            "current": current_model,
        },
        "tokens": {
            "input_budget_tokens": int(progress.get("input_tokens", 0) or 0),
            "output_tokens": int(progress.get("output_tokens", 0) or 0),
            "max_input_tokens": int(budget.get("max_input_tokens", 0) or 0),
            "max_output_tokens": int(budget.get("max_output_tokens", 0) or 0),
            "last_attempt_gross_input_tokens": int(attempt_usage.get("gross_input_tokens", attempt_usage.get("input_tokens", 0)) or 0),
            "last_attempt_cached_input_tokens": int(attempt_usage.get("cached_input_tokens", 0) or 0),
        },
        "progress": {
            "iteration": int(progress.get("iteration", 0) or 0),
            "repair_iterations": int(progress.get("repair_iterations", 0) or 0),
            "escalations": int(progress.get("escalations", 0) or 0),
            "provider_failovers": int(progress.get("provider_failovers", 0) or 0),
            "model_failovers": int(progress.get("model_failovers", 0) or 0),
            "model_calls": int(progress.get("model_calls", 0) or 0),
            "tool_calls": int(progress.get("tool_calls", 0) or 0),
            "test_runs": int(progress.get("test_runs", 0) or 0),
            "elapsed_minutes": float(progress.get("elapsed_minutes", 0.0) or 0.0),
            "cost_usd": float(progress.get("cost_usd", 0.0) or 0.0),
            "changed_files": int(progress.get("changed_files", 0) or 0),
            "tests_passed": bool(progress.get("tests_passed", False)),
            "required_checks_passed": bool(progress.get("required_checks_passed", False)),
            "agent_succeeded": bool(progress.get("agent_succeeded", False)),
        },
        "budget": {
            "max_model_calls": budget.get("max_model_calls"),
            "max_tool_calls": budget.get("max_tool_calls"),
            "max_test_runs": budget.get("max_test_runs"),
            "max_wall_time_minutes": budget.get("max_wall_time_minutes"),
            "max_changed_files": budget.get("max_changed_files"),
            "max_iterations": budget.get("max_iterations"),
            "max_repair_iterations": budget.get("max_repair_iterations"),
            "hard_cost_usd": budget.get("hard_cost_usd"),
        },
        "remaining": remaining,
        "recent_events": [],
    }


def _public_job_events(storage: Any, job_id: str, *, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in storage.events_after(job_id, after_id=after, limit=limit):
        event = public_event(dict(row))
        if event:
            events.append(event)
    return events


def build_dashboard_snapshot(storage: Any, orchestrator_store: Any) -> dict[str, Any]:
    orchestrator_store.ensure()
    with storage.connect() as conn:
        plan_rows = list(
            conn.execute(
                """SELECT o.*, p.baseline_revision, p.baseline_source_commit, p.ticket, p.plan, p.staffing
                FROM cp_plan_orchestrations o
                JOIN cp_execution_plans p ON p.id=o.plan_id
                ORDER BY o.created_at DESC, o.plan_id DESC
                LIMIT 20"""
            ).fetchall()
        )
        alert_rows = list(
            conn.execute(
                """SELECT id, event_type, severity, project_id, ticket_id, plan_id,
                          work_order_id, summary, github_url, status, attempts, created_at, sent_at
                FROM cp_notification_outbox
                ORDER BY id DESC LIMIT 3"""
            ).fetchall()
        )
        pending_notifications = conn.execute(
            "SELECT COUNT(*) AS count FROM cp_notification_outbox WHERE status IN ('pending','delivering')"
        ).fetchone()

    plans: list[dict[str, Any]] = []
    active_job_ids: set[str] = set()
    referenced_job_ids: set[str] = set()
    waiting_merge = 0
    waiting_human = 0
    blocked_plans = 0
    superseded_plans = 0
    job_views_by_id: dict[str, list[dict[str, Any]]] = {}

    for plan_row in plan_rows:
        plan_id = str(plan_row["plan_id"])
        work_orders: list[dict[str, Any]] = []
        totals = {"input_budget_tokens": 0, "output_tokens": 0}
        for wo in orchestrator_store.work_orders(plan_id):
            lifecycle = str(wo.get("lifecycle") or "active")
            job_id = str(wo.get("job_id") or "")
            if job_id:
                referenced_job_ids.add(job_id)
            job = storage.get(job_id) if job_id else None
            job_view = _job_snapshot(job)
            if job_view:
                job_views_by_id.setdefault(str(job_view["id"]), []).append(job_view)
            if lifecycle == "active" and job_view and job_view["status"] in _ACTIVE_JOB_STATES:
                active_job_ids.add(str(job_view["id"]))
            if job_view:
                totals["input_budget_tokens"] += int(job_view["tokens"].get("input_budget_tokens", 0) or 0)
                totals["output_tokens"] += int(job_view["tokens"].get("output_tokens", 0) or 0)
            if lifecycle == "active" and wo.get("state") == "awaiting_merge":
                waiting_merge += 1
            if lifecycle == "active" and wo.get("state") == "waiting_human":
                waiting_human += 1
            work_orders.append({
                "id": wo.get("work_order_id"),
                "sequence_no": wo.get("sequence_no"),
                "execution_mode": wo.get("execution_mode"),
                "state": wo.get("state"),
                "lifecycle": lifecycle,
                "superseded_by_plan_id": wo.get("superseded_by_plan_id"),
                "superseded_by_work_order_id": wo.get("superseded_by_work_order_id"),
                "superseded_at": _iso(wo.get("superseded_at")),
                "supersession_reason": wo.get("supersession_reason"),
                "pr_number": wo.get("pr_number"),
                "pr_url": wo.get("pr_url"),
                "updated_at": _iso(wo.get("updated_at")),
                "job": job_view,
            })
        status = str(plan_row.get("status") or "")
        lifecycle = str(plan_row.get("lifecycle") or "active")
        if lifecycle == "active" and status == "blocked":
            blocked_plans += 1
        if lifecycle == "superseded":
            superseded_plans += 1
        current_wo = next(
            (
                wo for wo in work_orders
                if wo["lifecycle"] == "active"
                and wo["state"] in {"running", "awaiting_merge", "waiting_human"}
            ),
            None,
        )
        plans.append({
            "id": plan_id,
            "project_id": plan_row.get("project_id"),
            "status": status,
            "lifecycle": lifecycle,
            "superseded_at": _iso(plan_row.get("superseded_at")),
            "ticket_id": plan_row.get("ticket_id"),
            "ticket_title": plan_row.get("ticket_title"),
            "github_url": plan_row.get("github_url"),
            "baseline_revision": plan_row.get("baseline_revision"),
            "baseline_source_commit": plan_row.get("baseline_source_commit"),
            "created_at": _iso(plan_row.get("created_at")),
            "updated_at": _iso(plan_row.get("updated_at")),
            "current_work_order_id": current_wo["id"] if current_wo else None,
            "token_totals": totals,
            "work_orders": work_orders,
        })

    standalone_jobs: list[dict[str, Any]] = []
    for job in storage.list(limit=500):
        job_id = str(job.get("id") or "")
        job_status = str(job.get("status") or "")
        if (
            not job_id
            or job_id in referenced_job_ids
            or job_status not in _STANDALONE_VISIBLE_JOB_STATES
        ):
            continue
        job_view = _job_snapshot(job)
        if not job_view:
            continue
        standalone_jobs.append(job_view)
        job_views_by_id.setdefault(job_id, []).append(job_view)
        if job_status in _ACTIVE_JOB_STATES:
            active_job_ids.add(job_id)
        if job_status == "waiting_human":
            waiting_human += 1

    standalone_jobs.sort(
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )

    events_by_job: dict[str, list[dict[str, Any]]] = {job_id: [] for job_id in job_views_by_id}
    for row in storage.recent_events(list(job_views_by_id), per_job_limit=40):
        event = public_event(dict(row))
        if event and event["job_id"] in events_by_job:
            events_by_job[event["job_id"]].append(event)
    for job_id, views in job_views_by_id.items():
        recent_events = sorted(
            events_by_job[job_id],
            key=lambda item: int(item.get("seq") or 0),
            reverse=True,
        )
        for job_view in views:
            job_view["recent_events"] = recent_events

    current_plan = next(
        (
            p for p in plans
            if p["lifecycle"] == "active" and p["status"] in _ACTIVE_PLAN_STATES
        ),
        next((p for p in plans if p["lifecycle"] == "active"), plans[0] if plans else None),
    )
    active_plans = sum(
        1 for p in plans
        if p["lifecycle"] == "active" and p["status"] in _ACTIVE_PLAN_STATES
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "active_plans": active_plans,
            "active_jobs": len(active_job_ids),
            "standalone_jobs": len(standalone_jobs),
            "waiting_merge": waiting_merge,
            "waiting_human": waiting_human,
            "blocked_plans": blocked_plans,
            "superseded_plans": superseded_plans,
            "pending_notifications": int((pending_notifications or {}).get("count", 0) or 0),
        },
        "current_plan_id": current_plan["id"] if current_plan else None,
        "plans": plans,
        "standalone_jobs": standalone_jobs,
        "alerts": [
            {
                "id": row.get("id"),
                "event_type": row.get("event_type"),
                "severity": row.get("severity"),
                "project_id": row.get("project_id"),
                "ticket_id": row.get("ticket_id"),
                "plan_id": row.get("plan_id"),
                "work_order_id": row.get("work_order_id"),
                "summary": row.get("summary"),
                "github_url": row.get("github_url"),
                "status": row.get("status"),
                "attempts": row.get("attempts"),
                "created_at": _iso(row.get("created_at")),
                "sent_at": _iso(row.get("sent_at")),
            }
            for row in alert_rows
        ],
    }


def create_dashboard_router(
    storage: Any,
    orchestrator_store: Any,
    preview_manager: Any | None = None,
    project_preview_manager: Any | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    def dashboard_page() -> str:
        return DASHBOARD_HTML

    @router.post("/v1/dashboard/session", include_in_schema=False)
    def dashboard_login(payload: DashboardLogin, response: Response) -> dict[str, str]:
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
            max_age=12 * 60 * 60,
            path="/",
        )
        return {"status": "ok"}

    @router.delete("/v1/dashboard/session", include_in_schema=False)
    def dashboard_logout(response: Response) -> dict[str, str]:
        response.delete_cookie(_COOKIE, path="/")
        response.delete_cookie(_CONTROL_COOKIE, path="/")
        return {"status": "ok"}

    @router.post("/v1/dashboard/control-session", include_in_schema=False)
    def dashboard_control_login(
        payload: DashboardLogin,
        response: Response,
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> dict[str, str]:
        _require_session(pcp_dashboard_session)
        secret = _dashboard_control_secret()
        if secret in _PLACEHOLDERS:
            raise HTTPException(503, "Dashboard control token is not configured")
        if not hmac.compare_digest(payload.token, secret):
            raise HTTPException(401, "Invalid dashboard control token")
        response.set_cookie(
            _CONTROL_COOKIE,
            _control_session_value(secret),
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=60 * 60,
            path="/",
        )
        return {"status": "ok"}

    @router.delete("/v1/dashboard/control-session", include_in_schema=False)
    def dashboard_control_logout(
        response: Response,
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> dict[str, str]:
        _require_session(pcp_dashboard_session)
        response.delete_cookie(_CONTROL_COOKIE, path="/")
        return {"status": "ok"}

    @router.get("/v1/dashboard/project-previews", include_in_schema=False)
    def dashboard_project_previews(
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        if project_preview_manager is None:
            raise HTTPException(503, "Project preview manager is unavailable")
        return {"projects": project_preview_manager.projects()}

    @router.get(
        "/v1/dashboard/projects/{project_id}/preview",
        include_in_schema=False,
    )
    async def dashboard_project_preview_status(
        project_id: str,
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        if project_preview_manager is None:
            raise HTTPException(503, "Project preview manager is unavailable")
        try:
            return await project_preview_manager.status(project_id)
        except RuntimeError as exc:
            raise _preview_error(exc) from exc

    @router.post(
        "/v1/dashboard/projects/{project_id}/preview",
        include_in_schema=False,
    )
    async def dashboard_project_preview_start(
        project_id: str,
        payload: DashboardPreviewRequest,
        pcp_dashboard_session: str | None = Cookie(default=None),
        pcp_dashboard_control_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        _require_control_session(pcp_dashboard_control_session)
        if project_preview_manager is None:
            raise HTTPException(503, "Project preview manager is unavailable")
        try:
            return await project_preview_manager.start(project_id, payload.target)
        except RuntimeError as exc:
            raise _preview_error(exc) from exc

    @router.delete(
        "/v1/dashboard/projects/{project_id}/preview",
        include_in_schema=False,
    )
    async def dashboard_project_preview_stop(
        project_id: str,
        pcp_dashboard_session: str | None = Cookie(default=None),
        pcp_dashboard_control_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        _require_control_session(pcp_dashboard_control_session)
        if project_preview_manager is None:
            raise HTTPException(503, "Project preview manager is unavailable")
        try:
            return await project_preview_manager.stop(project_id)
        except RuntimeError as exc:
            raise _preview_error(exc) from exc

    @router.get("/v1/dashboard/jobs/{job_id}/preview", include_in_schema=False)
    async def dashboard_preview_status(
        job_id: str,
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        if preview_manager is None:
            raise HTTPException(503, "Preview manager is unavailable")
        try:
            return await preview_manager.status(job_id)
        except RuntimeError as exc:
            raise _preview_error(exc) from exc

    @router.post("/v1/dashboard/jobs/{job_id}/preview", include_in_schema=False)
    async def dashboard_preview_start(
        job_id: str,
        payload: DashboardPreviewRequest,
        pcp_dashboard_session: str | None = Cookie(default=None),
        pcp_dashboard_control_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        _require_control_session(pcp_dashboard_control_session)
        if preview_manager is None:
            raise HTTPException(503, "Preview manager is unavailable")
        try:
            return await preview_manager.start(job_id, payload.target)
        except RuntimeError as exc:
            raise _preview_error(exc) from exc

    @router.delete("/v1/dashboard/jobs/{job_id}/preview", include_in_schema=False)
    async def dashboard_preview_stop(
        job_id: str,
        pcp_dashboard_session: str | None = Cookie(default=None),
        pcp_dashboard_control_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        _require_control_session(pcp_dashboard_control_session)
        if preview_manager is None:
            raise HTTPException(503, "Preview manager is unavailable")
        try:
            return await preview_manager.stop(job_id)
        except RuntimeError as exc:
            raise _preview_error(exc) from exc

    @router.get("/v1/dashboard/snapshot", include_in_schema=False)
    def dashboard_snapshot(pcp_dashboard_session: str | None = Cookie(default=None)) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        return build_dashboard_snapshot(storage, orchestrator_store)

    @router.get("/v1/dashboard/jobs/{job_id}/events", include_in_schema=False)
    def dashboard_job_events(
        job_id: str,
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=200),
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        if storage.get(job_id) is None:
            raise HTTPException(404, "Unknown job")
        events = _public_job_events(storage, job_id, after=after, limit=limit)
        return {"events": events, "last_seq": max([after, *[int(event["seq"]) for event in events]])}

    @router.get("/v1/dashboard/jobs/{job_id}/stream", include_in_schema=False)
    async def dashboard_job_stream(
        request: Request,
        job_id: str,
        after: int = Query(0, ge=0),
        pcp_dashboard_session: str | None = Cookie(default=None),
    ) -> StreamingResponse:
        _require_session(pcp_dashboard_session)
        if storage.get(job_id) is None:
            raise HTTPException(404, "Unknown job")

        async def stream():
            cursor = int(after)
            keepalive = 0
            while not await request.is_disconnected():
                rows = storage.events_after(job_id, after_id=cursor, limit=100)
                if rows:
                    for row in rows:
                        cursor = max(cursor, int(row.get("id") or 0))
                        event = public_event(dict(row))
                        if not event:
                            continue
                        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                        yield f"id: {event['seq']}\nevent: activity\ndata: {payload}\n\n"
                    keepalive = 0
                else:
                    keepalive += 1
                    if keepalive >= 20:
                        yield ": keepalive\n\n"
                        keepalive = 0
                await asyncio.sleep(0.75)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
