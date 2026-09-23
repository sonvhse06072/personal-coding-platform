from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import timedelta
from typing import Any

from .storage import Storage, now


ORCHESTRATOR_DDL = """
CREATE TABLE IF NOT EXISTS cp_plan_orchestrator_meta (
  singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
  installed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS cp_plan_orchestrations (
  plan_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  ticket_id TEXT,
  ticket_title TEXT,
  github_url TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_plan_orchestrations_status_idx
  ON cp_plan_orchestrations(status, created_at);

CREATE TABLE IF NOT EXISTS cp_plan_work_orders (
  plan_id TEXT NOT NULL,
  work_order_id TEXT NOT NULL,
  sequence_no INTEGER NOT NULL,
  execution_mode TEXT NOT NULL,
  state TEXT NOT NULL,
  job_id TEXT,
  pr_number INTEGER,
  pr_url TEXT,
  detail JSONB,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (plan_id, work_order_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS cp_plan_work_orders_job_idx
  ON cp_plan_work_orders(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cp_plan_work_orders_state_idx
  ON cp_plan_work_orders(state, updated_at);

CREATE TABLE IF NOT EXISTS cp_notification_outbox (
  id BIGSERIAL PRIMARY KEY,
  dedupe_key TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  project_id TEXT NOT NULL,
  ticket_id TEXT,
  plan_id TEXT,
  work_order_id TEXT,
  summary TEXT NOT NULL,
  github_url TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  available_at TIMESTAMPTZ NOT NULL,
  lease_until TIMESTAMPTZ,
  sent_at TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_notification_outbox_delivery_idx
  ON cp_notification_outbox(status, available_at, id);
"""

_ACTIVE_JOB_STATUSES = {
    "queued",
    "routing",
    "planning",
    "executing",
    "verifying",
    "evaluating",
    "delivering",
}
_TERMINAL_JOB_STATUSES = {"blocked", "failed", "interrupted", "cancelled"}
_BUSY_WORK_ORDER_STATES = {"running", "awaiting_merge", "waiting_human"}


class PlanOrchestratorStore:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def ensure(self) -> None:
        timestamp = now()
        with self.storage.connect() as conn:
            conn.execute(ORCHESTRATOR_DDL)
            conn.execute(
                """INSERT INTO cp_plan_orchestrator_meta(singleton, installed_at)
                VALUES (TRUE, %s)
                ON CONFLICT (singleton) DO NOTHING""",
                (timestamp,),
            )
            conn.commit()

    def register_new_plans(self) -> list[str]:
        """Register only plans created after the orchestrator was first installed.

        Existing plans are intentionally not adopted. This prevents a feature
        deployment from unexpectedly launching work that was created under the
        previous manual-execution contract.
        """
        self.ensure()
        registered: list[str] = []
        timestamp = now()
        with self.storage.connect() as conn:
            rows = list(
                conn.execute(
                    """SELECT p.*
                    FROM cp_execution_plans p
                    CROSS JOIN cp_plan_orchestrator_meta m
                    WHERE m.singleton=TRUE
                      AND p.created_at >= m.installed_at
                      AND p.plan IS NOT NULL
                      AND p.status IN ('ready', 'human_decision')
                      AND NOT EXISTS (
                        SELECT 1 FROM cp_plan_orchestrations o WHERE o.plan_id=p.id
                      )
                    ORDER BY p.created_at, p.id"""
                ).fetchall()
            )
            for row in rows:
                plan = dict(row.get("plan") or {})
                work_orders = list(plan.get("work_orders") or [])
                ticket = dict(row.get("ticket") or {})
                staffing = dict(row.get("staffing") or {})
                github_url = str(staffing.get("comment_url") or "") or None
                conn.execute(
                    """INSERT INTO cp_plan_orchestrations
                    (plan_id, project_id, status, ticket_id, ticket_title, github_url, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        row["id"],
                        row["project_id"],
                        "active",
                        ticket.get("id"),
                        ticket.get("title"),
                        github_url,
                        timestamp,
                        timestamp,
                    ),
                )
                for sequence_no, work_order in enumerate(work_orders):
                    requested_role = str(work_order.get("requested_role") or "developer")
                    execution_mode = "operator" if requested_role == "operator" else "agent"
                    conn.execute(
                        """INSERT INTO cp_plan_work_orders
                        (plan_id, work_order_id, sequence_no, execution_mode, state,
                         job_id, pr_number, pr_url, detail, created_at, updated_at)
                        VALUES (%s,%s,%s,%s,'pending',NULL,NULL,NULL,%s::jsonb,%s,%s)""",
                        (
                            row["id"],
                            work_order["id"],
                            sequence_no,
                            execution_mode,
                            json.dumps({}),
                            timestamp,
                            timestamp,
                        ),
                    )
                registered.append(str(row["id"]))
            conn.commit()
        return registered

    def active_plans(self) -> list[dict[str, Any]]:
        self.ensure()
        with self.storage.connect() as conn:
            return list(
                conn.execute(
                    """SELECT o.*, p.baseline_revision, p.baseline_source_commit,
                              p.ticket, p.plan, p.staffing
                    FROM cp_plan_orchestrations o
                    JOIN cp_execution_plans p ON p.id=o.plan_id
                    WHERE o.status NOT IN ('completed', 'blocked')
                    ORDER BY o.created_at, o.plan_id"""
                ).fetchall()
            )

    def orchestration(self, plan_id: str) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            return conn.execute(
                "SELECT * FROM cp_plan_orchestrations WHERE plan_id=%s",
                (plan_id,),
            ).fetchone()

    def work_orders(self, plan_id: str) -> list[dict[str, Any]]:
        self.ensure()
        with self.storage.connect() as conn:
            return list(
                conn.execute(
                    """SELECT * FROM cp_plan_work_orders
                    WHERE plan_id=%s ORDER BY sequence_no, work_order_id""",
                    (plan_id,),
                ).fetchall()
            )

    def update_plan(self, plan_id: str, *, status: str) -> None:
        with self.storage.connect() as conn:
            conn.execute(
                "UPDATE cp_plan_orchestrations SET status=%s, updated_at=%s WHERE plan_id=%s",
                (status, now(), plan_id),
            )
            conn.commit()

    def update_work_order(self, plan_id: str, work_order_id: str, **fields: Any) -> None:
        allowed = {"state", "job_id", "pr_number", "pr_url", "detail"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported plan work-order fields: {sorted(unknown)}")
        sets: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key == "detail":
                sets.append("detail=%s::jsonb")
                values.append(json.dumps(value or {}))
            else:
                sets.append(f"{key}=%s")
                values.append(value)
        sets.append("updated_at=%s")
        values.append(now())
        values.extend([plan_id, work_order_id])
        with self.storage.connect() as conn:
            conn.execute(
                f"UPDATE cp_plan_work_orders SET {', '.join(sets)} WHERE plan_id=%s AND work_order_id=%s",
                values,
            )
            conn.commit()

    def any_busy_work_order(self) -> bool:
        with self.storage.connect() as conn:
            row = conn.execute(
                """SELECT 1 FROM cp_plan_work_orders
                WHERE state = ANY(%s) LIMIT 1""",
                (list(_BUSY_WORK_ORDER_STATES),),
            ).fetchone()
            return row is not None

    def claim_notification(self, *, lease_seconds: int = 300) -> dict[str, Any] | None:
        self.ensure()
        timestamp = now()
        lease_until = timestamp + timedelta(seconds=max(30, min(1800, lease_seconds)))
        with self.storage.connect() as conn:
            conn.execute(
                """UPDATE cp_notification_outbox
                SET status='pending', lease_until=NULL, updated_at=%s
                WHERE status='delivering' AND lease_until IS NOT NULL AND lease_until <= %s""",
                (timestamp, timestamp),
            )
            row = conn.execute(
                """SELECT * FROM cp_notification_outbox
                WHERE status='pending' AND available_at <= %s
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1""",
                (timestamp,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            updated = conn.execute(
                """UPDATE cp_notification_outbox
                SET status='delivering', attempts=attempts+1, lease_until=%s, updated_at=%s
                WHERE id=%s
                RETURNING *""",
                (lease_until, timestamp, row["id"]),
            ).fetchone()
            conn.commit()
            return updated

    def ack_notification(self, event_id: int) -> bool:
        timestamp = now()
        with self.storage.connect() as conn:
            result = conn.execute(
                """UPDATE cp_notification_outbox
                SET status='sent', sent_at=%s, lease_until=NULL, last_error=NULL, updated_at=%s
                WHERE id=%s AND status='delivering'""",
                (timestamp, timestamp, event_id),
            )
            conn.commit()
            return bool(result.rowcount)

    def release_notification(self, event_id: int, *, error: str, retry_seconds: int = 60) -> bool:
        timestamp = now()
        available_at = timestamp + timedelta(seconds=max(5, min(3600, retry_seconds)))
        with self.storage.connect() as conn:
            result = conn.execute(
                """UPDATE cp_notification_outbox
                SET status='pending', available_at=%s, lease_until=NULL,
                    last_error=%s, updated_at=%s
                WHERE id=%s AND status='delivering'""",
                (available_at, error.strip()[:1000], timestamp, event_id),
            )
            conn.commit()
            return bool(result.rowcount)

    def emit_notification(
        self,
        *,
        dedupe_key: str,
        event_type: str,
        severity: str,
        project_id: str,
        ticket_id: str | None,
        plan_id: str | None,
        work_order_id: str | None,
        summary: str,
        github_url: str | None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        timestamp = now()
        with self.storage.connect() as conn:
            result = conn.execute(
                """INSERT INTO cp_notification_outbox
                (dedupe_key, event_type, severity, project_id, ticket_id, plan_id,
                 work_order_id, summary, github_url, payload, status, attempts,
                 available_at, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'pending',0,%s,%s,%s)
                ON CONFLICT (dedupe_key) DO NOTHING""",
                (
                    dedupe_key,
                    event_type,
                    severity,
                    project_id,
                    ticket_id,
                    plan_id,
                    work_order_id,
                    summary.strip()[:2000],
                    github_url,
                    json.dumps(payload or {}),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            return bool(result.rowcount)


class PlanOrchestrator:
    def __init__(self, storage: Storage, engine: Any, *, store: PlanOrchestratorStore | None = None) -> None:
        self.storage = storage
        self.engine = engine
        self.store = store or PlanOrchestratorStore(storage)
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._stopping = False
        self.poll_seconds = max(5.0, float(os.getenv("PLAN_ORCHESTRATOR_POLL_SECONDS", "15")))

    async def start(self) -> None:
        self.store.ensure()
        self._stopping = False
        await self.tick()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.poll_seconds)
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Individual plan/job failures are persisted as orchestration state;
                # an unexpected polling error must not terminate Runtime.
                continue

    async def tick(self) -> dict[str, Any]:
        async with self._lock:
            registered = self.store.register_new_plans()
            plans = self.store.active_plans()
            for plan in plans:
                await self._reconcile_plan(plan)
            launched = None
            if not self.store.any_busy_work_order():
                launched = await self._launch_one()
            return {"registered": registered, "launched": launched}

    def view(self, plan_id: str) -> dict[str, Any] | None:
        orchestration = self.store.orchestration(plan_id)
        if orchestration is None:
            return None
        return {
            **dict(orchestration),
            "work_orders": [dict(row) for row in self.store.work_orders(plan_id)],
        }

    async def resolve_operator(
        self,
        *,
        plan_id: str,
        work_order_id: str,
        action: str,
        note: str,
    ) -> dict[str, Any]:
        rows = {row["work_order_id"]: row for row in self.store.work_orders(plan_id)}
        row = rows.get(work_order_id)
        if row is None:
            raise RuntimeError("Unknown orchestrated WorkOrder")
        if row["execution_mode"] != "operator" or row["state"] != "waiting_human":
            raise RuntimeError("WorkOrder is not waiting for an operator")
        detail = dict(row.get("detail") or {})
        detail["operator_note"] = note.strip()[:2000]
        if action == "complete":
            self.store.update_work_order(plan_id, work_order_id, state="completed", detail=detail)
            self.store.update_plan(plan_id, status="active")
        elif action == "block":
            self.store.update_work_order(plan_id, work_order_id, state="blocked", detail=detail)
            self.store.update_plan(plan_id, status="blocked")
            plan = self.storage.get_execution_plan(plan_id) or {}
            self._notify(
                plan,
                work_order_id=work_order_id,
                event_type="work_order_blocked",
                severity="error",
                summary="Operator marked the WorkOrder blocked.",
                suffix="operator-blocked",
            )
        else:
            raise RuntimeError("Unsupported operator action")
        await self.tick()
        result = self.view(plan_id)
        assert result is not None
        return result

    async def _reconcile_plan(self, plan: dict[str, Any]) -> None:
        plan_id = str(plan["plan_id"])
        plan_doc = dict(plan.get("plan") or {})
        definitions = {item["id"]: item for item in plan_doc.get("work_orders") or []}
        rows = self.store.work_orders(plan_id)

        if plan_doc.get("decision_boundaries"):
            self.store.update_plan(plan_id, status="waiting_human")
            self._notify(
                plan,
                work_order_id=None,
                event_type="human_decision_required",
                severity="warning",
                summary="ExecutionPlan has unresolved PM decision boundaries.",
                suffix="plan-decision-boundary",
            )
            return

        for tracked in rows:
            work_order_id = str(tracked["work_order_id"])
            state = str(tracked["state"])
            job_id = tracked.get("job_id")

            if state in {"running", "waiting_human"} and job_id:
                job = self.storage.get(str(job_id))
                if job is None:
                    self._block_tracked(plan, tracked, "orchestrated_job_missing")
                    continue
                job_status = str(job.get("status") or "")
                if job_status in _ACTIVE_JOB_STATUSES:
                    if state != "running":
                        self.store.update_work_order(plan_id, work_order_id, state="running")
                    continue
                if job_status == "waiting_human":
                    self.store.update_work_order(plan_id, work_order_id, state="waiting_human")
                    self._notify(
                        plan,
                        work_order_id=work_order_id,
                        event_type="human_decision_required",
                        severity="warning",
                        summary="Coding job requires a human decision before it can continue.",
                        suffix=f"job-human:{job_id}",
                    )
                    continue
                if job_status == "completed":
                    resource_quiesce = await self._quiesce_job_workspace(
                        plan,
                        tracked,
                        job,
                    )
                    result = dict(job.get("result") or {})
                    delivery = dict(result.get("delivery") or {})
                    pr = dict(delivery.get("pull_request") or {})
                    if pr.get("number"):
                        self.store.update_work_order(
                            plan_id,
                            work_order_id,
                            state="awaiting_merge",
                            pr_number=int(pr["number"]),
                            pr_url=pr.get("url"),
                            detail={
                                "job_id": job_id,
                                "delivery_state": delivery.get("state"),
                                "resource_quiesce": resource_quiesce,
                            },
                        )
                    else:
                        self.store.update_work_order(
                            plan_id,
                            work_order_id,
                            state="completed",
                            detail={
                                "job_id": job_id,
                                "delivery_state": delivery.get("state"),
                                "resource_quiesce": resource_quiesce,
                            },
                        )
                    continue
                if job_status in _TERMINAL_JOB_STATUSES:
                    resource_quiesce = await self._quiesce_job_workspace(
                        plan,
                        tracked,
                        job,
                    )
                    self._block_job(
                        plan,
                        tracked,
                        job,
                        resource_quiesce=resource_quiesce,
                    )
                    continue

            if state == "awaiting_merge":
                pr_number = tracked.get("pr_number")
                if not pr_number:
                    self._block_tracked(plan, tracked, "missing_pull_request_number")
                    continue
                pr = await self.engine.ddev.github_pull_request(
                    project_id=str(plan["project_id"]),
                    pr_number=int(pr_number),
                )
                if bool(pr.get("merged")):
                    detail = dict(tracked.get("detail") or {})
                    detail.update(
                        {
                            "merged_at": pr.get("merged_at"),
                            "merge_commit_sha": pr.get("merge_commit_sha"),
                        }
                    )
                    self.store.update_work_order(
                        plan_id,
                        work_order_id,
                        state="completed",
                        detail=detail,
                    )
                elif str(pr.get("state") or "") == "closed":
                    self._block_tracked(plan, tracked, "pull_request_closed_without_merge")

        rows = self.store.work_orders(plan_id)
        states = [str(row["state"]) for row in rows]
        if rows and all(state == "completed" for state in states):
            self.store.update_plan(plan_id, status="completed")
            self._notify(
                plan,
                work_order_id=None,
                event_type="ticket_completed",
                severity="success",
                summary="ExecutionPlan completed; all WorkOrders passed their merge/operator gates.",
                suffix="plan-completed",
            )
        elif any(state == "blocked" for state in states):
            self.store.update_plan(plan_id, status="blocked")
        elif any(state == "waiting_human" for state in states):
            self.store.update_plan(plan_id, status="waiting_human")
        elif any(state == "awaiting_merge" for state in states):
            self.store.update_plan(plan_id, status="waiting_merge")
        elif any(state == "running" for state in states):
            self.store.update_plan(plan_id, status="executing")
        else:
            self.store.update_plan(plan_id, status="active")

    async def _launch_one(self) -> dict[str, str] | None:
        for plan in self.store.active_plans():
            if str(plan.get("status")) in {"blocked", "completed", "waiting_human"}:
                continue
            plan_doc = dict(plan.get("plan") or {})
            definitions = {item["id"]: item for item in plan_doc.get("work_orders") or []}
            tracked = self.store.work_orders(str(plan["plan_id"]))
            states = {row["work_order_id"]: row["state"] for row in tracked}
            for row in tracked:
                if row["state"] != "pending":
                    continue
                definition = definitions.get(row["work_order_id"])
                if not definition:
                    self._block_tracked(plan, row, "work_order_definition_missing")
                    return None
                dependencies = list(definition.get("dependencies") or [])
                if not all(states.get(dep) == "completed" for dep in dependencies):
                    continue
                if row["execution_mode"] == "operator":
                    self.store.update_work_order(
                        str(plan["plan_id"]),
                        str(row["work_order_id"]),
                        state="waiting_human",
                        detail={"reason": "operator_execution_required"},
                    )
                    self.store.update_plan(str(plan["plan_id"]), status="waiting_human")
                    self._notify(
                        plan,
                        work_order_id=str(row["work_order_id"]),
                        event_type="operator_action_required",
                        severity="warning",
                        summary="Operator-only WorkOrder is ready and requires owner action.",
                        suffix="operator-ready",
                    )
                    return None

                job_id = self._deterministic_job_id(str(plan["plan_id"]), str(row["work_order_id"]))
                payload = {
                    "_job_id": job_id,
                    "project_id": plan["project_id"],
                    "work_order": definition,
                    "baseline_revision": plan["baseline_revision"],
                    # Deliberately omit source_commit so each sequential WorkOrder
                    # starts from the project's current base branch after the
                    # previous PR was manually merged.
                    "source_commit": None,
                    "repo_hints": self._repo_hints(definition),
                    "provider_state": {},
                    "dry_run": False,
                }
                created_job_id = self.engine.create_job(payload)
                self.store.update_work_order(
                    str(plan["plan_id"]),
                    str(row["work_order_id"]),
                    state="running",
                    job_id=created_job_id,
                    detail={"job_id": created_job_id},
                )
                self.store.update_plan(str(plan["plan_id"]), status="executing")
                job = self.storage.get(created_job_id)
                if job and str(job.get("status")) == "queued":
                    await self.engine.enqueue(created_job_id)
                return {"plan_id": str(plan["plan_id"]), "work_order_id": str(row["work_order_id"]), "job_id": created_job_id}
        return None

    async def _quiesce_job_workspace(
        self,
        plan: dict[str, Any],
        tracked: dict[str, Any],
        job: dict[str, Any],
    ) -> dict[str, Any]:
        workspace = str(job.get("workspace") or "").strip()
        if not workspace:
            return {"quiesced": False, "reason": "no_workspace"}
        try:
            result = await self.engine.ddev.quiesce_workspace(
                job_id=str(job["id"]),
                project_id=str(job["project_id"]),
                workspace=workspace,
            )
        except Exception as exc:
            message = str(exc)[-2000:]
            self._notify(
                plan,
                work_order_id=str(tracked["work_order_id"]),
                event_type="workspace_quiesce_failed",
                severity="warning",
                summary=f"Workspace DDEV quiesce failed: {message}",
                suffix=f"workspace-quiesce:{job.get('id')}",
                payload={"job_id": job.get("id"), "error": message},
            )
            return {"quiesced": False, "error": message}
        return {
            "quiesced": bool(result.get("quiesced", False)),
            "data_removed": bool(result.get("data_removed", False)),
        }

    def _block_job(
        self,
        plan: dict[str, Any],
        tracked: dict[str, Any],
        job: dict[str, Any],
        *,
        resource_quiesce: dict[str, Any] | None = None,
    ) -> None:
        plan_id = str(plan["plan_id"])
        work_order_id = str(tracked["work_order_id"])
        result = dict(job.get("result") or {})
        reason = str(result.get("reason") or job.get("error") or job.get("status") or "job_blocked")
        progress = dict(job.get("progress") or {})
        failures = list(progress.get("provider_failures") or [])
        quota_failure = any(
            str(item.get("kind") or "") in {"quota_exhausted", "rate_limited"}
            for item in failures
            if isinstance(item, dict)
        )
        ci_failures = int(progress.get("ci_failures", 0) or 0)
        self.store.update_work_order(
            plan_id,
            work_order_id,
            state="blocked",
            detail={
                "reason": reason,
                "job_id": job.get("id"),
                "resource_quiesce": resource_quiesce or {},
            },
        )
        self.store.update_plan(plan_id, status="blocked")
        if quota_failure and "without_fallback" in reason:
            event_type = "provider_quota_exhausted"
            summary = "Provider/model quota was exhausted and no eligible fallback remained."
        elif ci_failures > 0:
            event_type = "ci_failed_after_repairs"
            summary = "CI remained failing after the allowed repair budget was exhausted."
        else:
            event_type = "work_order_blocked"
            summary = f"WorkOrder blocked with reason: {reason[:300]}"
        self._notify(
            plan,
            work_order_id=work_order_id,
            event_type=event_type,
            severity="error",
            summary=summary,
            suffix=f"job-blocked:{job.get('id')}:{reason}",
            payload={"reason": reason, "job_id": job.get("id")},
        )

    def _block_tracked(self, plan: dict[str, Any], tracked: dict[str, Any], reason: str) -> None:
        plan_id = str(plan["plan_id"])
        work_order_id = str(tracked["work_order_id"])
        self.store.update_work_order(
            plan_id,
            work_order_id,
            state="blocked",
            detail={"reason": reason},
        )
        self.store.update_plan(plan_id, status="blocked")
        self._notify(
            plan,
            work_order_id=work_order_id,
            event_type="work_order_blocked",
            severity="error",
            summary=f"WorkOrder blocked with reason: {reason}",
            suffix=f"tracked-blocked:{reason}",
        )

    def _notify(
        self,
        plan: dict[str, Any],
        *,
        work_order_id: str | None,
        event_type: str,
        severity: str,
        summary: str,
        suffix: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        plan_id = str(plan["plan_id"])
        ticket = dict(plan.get("ticket") or {})
        base_key = f"{plan.get('project_id')}:{plan_id}:{work_order_id or '-'}:{event_type}:{suffix}"
        dedupe_key = hashlib.sha256(base_key.encode("utf-8")).hexdigest()
        self.store.emit_notification(
            dedupe_key=dedupe_key,
            event_type=event_type,
            severity=severity,
            project_id=str(plan.get("project_id") or ""),
            ticket_id=str(ticket.get("id") or "") or None,
            plan_id=plan_id,
            work_order_id=work_order_id,
            summary=summary,
            github_url=str(plan.get("github_url") or "") or None,
            payload=payload,
        )

    @staticmethod
    def _deterministic_job_id(plan_id: str, work_order_id: str) -> str:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"coding-platform:{plan_id}:{work_order_id}").hex

    @staticmethod
    def _repo_hints(work_order: dict[str, Any]) -> dict[str, Any]:
        flags = set(work_order.get("risk", {}).get("flags") or [])

        # A plan-orchestrated WorkOrder is an authoritative contract. Its full
        # serialized text contains both in-scope work and explicit non-scope /
        # preservation constraints. Letting repo keyword analysis reinterpret
        # words such as "authentication", "security", "schema" or "API" from
        # those boundaries as intended changes can spuriously raise routing
        # risk/profile. Protected-change booleans therefore come from explicit
        # WorkOrder risk flags for orchestrated jobs. Legacy free-text jobs do
        # not use these hints and retain analyzer inference.
        protected_flags = (
            "schema_change",
            "security_sensitive",
            "authentication_change",
            "authorization_change",
            "external_api",
            "production_write",
            "destructive_migration",
        )

        hints = {
            "estimated_files": min(30, int(work_order.get("budget", {}).get("max_changed_files", 14))),
            "affected_components": min(10, max(1, len(work_order.get("source_references") or []))),
            "dependency_depth": min(10, len(work_order.get("dependencies") or [])),
            "tests_available": True,
            "existing_pattern": True,
            "likely_change_types": sorted(flags)[:20],
        }
        hints.update({name: name in flags for name in protected_flags})
        return hints
