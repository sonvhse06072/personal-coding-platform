from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .dashboard_ui import DASHBOARD_HTML


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
        raise HTTPException(401, "Dashboard authentication required")


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
        "score": value.get("score"),
        "predicted_success": value.get("predicted_success"),
    }


def _job_snapshot(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    route = dict(job.get("route") or {})
    strategy = dict(route.get("strategy") or {})
    checkpoint = dict(job.get("checkpoint") or {})
    progress = dict(job.get("progress") or {})
    budget = dict(strategy.get("budget") or {})

    planner = _choice(checkpoint.get("planner_choice") or strategy.get("planner"))
    executor = _choice(checkpoint.get("executor_choice") or strategy.get("executor"))
    evaluator = _choice(checkpoint.get("evaluator_choice") or strategy.get("evaluator"))
    status = str(job.get("status") or "")
    current_model = planner if status == "planning" else evaluator if status == "evaluating" else executor

    attempts = list(progress.get("agent_attempts") or [])
    attempt_usage = dict((attempts[-1] if attempts else {}).get("usage") or {})
    return {
        "id": job.get("id"),
        "status": status,
        "branch": job.get("branch"),
        "source_commit": job.get("source_commit"),
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
    }


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
                ORDER BY id DESC LIMIT 12"""
            ).fetchall()
        )
        pending_notifications = conn.execute(
            "SELECT COUNT(*) AS count FROM cp_notification_outbox WHERE status IN ('pending','delivering')"
        ).fetchone()

    plans: list[dict[str, Any]] = []
    active_jobs = 0
    waiting_merge = 0
    waiting_human = 0
    blocked_plans = 0

    for plan_row in plan_rows:
        plan_id = str(plan_row["plan_id"])
        work_orders: list[dict[str, Any]] = []
        totals = {"input_budget_tokens": 0, "output_tokens": 0}
        for wo in orchestrator_store.work_orders(plan_id):
            job = storage.get(str(wo["job_id"])) if wo.get("job_id") else None
            job_view = _job_snapshot(job)
            if job_view and job_view["status"] in _ACTIVE_JOB_STATES:
                active_jobs += 1
            if job_view:
                totals["input_budget_tokens"] += int(job_view["tokens"].get("input_budget_tokens", 0) or 0)
                totals["output_tokens"] += int(job_view["tokens"].get("output_tokens", 0) or 0)
            if wo.get("state") == "awaiting_merge":
                waiting_merge += 1
            if wo.get("state") == "waiting_human":
                waiting_human += 1
            work_orders.append({
                "id": wo.get("work_order_id"),
                "sequence_no": wo.get("sequence_no"),
                "execution_mode": wo.get("execution_mode"),
                "state": wo.get("state"),
                "pr_number": wo.get("pr_number"),
                "pr_url": wo.get("pr_url"),
                "updated_at": _iso(wo.get("updated_at")),
                "job": job_view,
            })
        status = str(plan_row.get("status") or "")
        if status == "blocked":
            blocked_plans += 1
        current_wo = next((wo for wo in work_orders if wo["state"] in {"running", "awaiting_merge", "waiting_human"}), None)
        plans.append({
            "id": plan_id,
            "project_id": plan_row.get("project_id"),
            "status": status,
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

    current_plan = next((p for p in plans if p["status"] in _ACTIVE_PLAN_STATES), plans[0] if plans else None)
    active_plans = sum(1 for p in plans if p["status"] in _ACTIVE_PLAN_STATES)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "active_plans": active_plans,
            "active_jobs": active_jobs,
            "waiting_merge": waiting_merge,
            "waiting_human": waiting_human,
            "blocked_plans": blocked_plans,
            "pending_notifications": int((pending_notifications or {}).get("count", 0) or 0),
        },
        "current_plan_id": current_plan["id"] if current_plan else None,
        "plans": plans,
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


def create_dashboard_router(storage: Any, orchestrator_store: Any) -> APIRouter:
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
        return {"status": "ok"}

    @router.get("/v1/dashboard/snapshot", include_in_schema=False)
    def dashboard_snapshot(pcp_dashboard_session: str | None = Cookie(default=None)) -> dict[str, Any]:
        _require_session(pcp_dashboard_session)
        return build_dashboard_snapshot(storage, orchestrator_store)

    return router
