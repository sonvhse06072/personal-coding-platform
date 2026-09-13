from __future__ import annotations

from copy import deepcopy
from typing import Any


_ALLOWED_TRACKED_STATES = {"blocked", "running"}


def prepare_orchestrated_job_resume(store: Any, job_id: str) -> dict[str, Any] | None:
    """Validate whether a Runtime job may be resumed under orchestration.

    Non-orchestrated jobs return ``None``. A tracked agent WorkOrder may resume
    while already running (for example after a Runtime interruption) or while
    blocked. Operator-only WorkOrders are never converted into agent execution.
    """
    store.ensure()
    with store.storage.connect() as conn:
        tracked = conn.execute(
            "SELECT * FROM cp_plan_work_orders WHERE job_id=%s",
            (job_id,),
        ).fetchone()
    if tracked is None:
        return None

    tracked = dict(tracked)
    if str(tracked.get("execution_mode") or "") != "agent":
        raise RuntimeError("Operator-only WorkOrders cannot be resumed as coding jobs")

    state = str(tracked.get("state") or "")
    if state not in _ALLOWED_TRACKED_STATES:
        raise RuntimeError(f"Orchestrated WorkOrder cannot resume from state={state}")

    plan_id = str(tracked.get("plan_id") or "")
    plan = store.orchestration(plan_id)
    if plan is None:
        raise RuntimeError("Orchestrated resume is missing its plan")
    plan_status = str(plan.get("status") or "")

    reopen = state == "blocked"
    if reopen and plan_status != "blocked":
        raise RuntimeError(
            f"Blocked WorkOrder cannot be reopened while plan status={plan_status}"
        )

    return {
        "plan_id": plan_id,
        "work_order_id": str(tracked.get("work_order_id") or ""),
        "reopen": reopen,
        "detail": deepcopy(tracked.get("detail") or {}),
    }


def reopen_orchestrated_job(store: Any, context: dict[str, Any] | None, job_id: str) -> None:
    """Return the exact blocked agent WorkOrder to the orchestrator's active path."""
    if not context or not bool(context.get("reopen")):
        return

    detail = deepcopy(context.get("detail") or {})
    detail.update({
        "job_id": job_id,
        "resume_state": "explicit_job_resume",
    })
    store.update_work_order(
        str(context["plan_id"]),
        str(context["work_order_id"]),
        state="running",
        detail=detail,
    )
    store.update_plan(str(context["plan_id"]), status="executing")
