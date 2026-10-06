from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import timedelta
from typing import Any

from .config import project_config
from .storage import Storage, now
from .work_order_checkpoints import (
    blocked_evidence_checkpoint_rows,
    blocked_plan_evidence,
    checkpoint_evidence,
    checkpoint_read_model,
    launch_identity,
    orchestrator_launch,
    ready_work_order_ids as dependency_ready_work_order_ids,
    transition_key,
)


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
  lifecycle TEXT NOT NULL DEFAULT 'active',
  superseded_at TIMESTAMPTZ,
  supervision_generation BIGINT NOT NULL DEFAULT 0 CHECK (supervision_generation >= 0),
  supervision_state TEXT CHECK (supervision_state IS NULL OR supervision_state IN ('held','released')),
  supervision_checkpoint_id BIGINT,
  supervision_checkpoint_key TEXT,
  supervision_checkpoint_work_order_id TEXT,
  supervision_ready_work_order_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  supervision_continuation_key TEXT,
  supervision_released_at TIMESTAMPTZ,
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
  lifecycle TEXT NOT NULL DEFAULT 'active',
  superseded_by_plan_id TEXT,
  superseded_by_work_order_id TEXT,
  superseded_at TIMESTAMPTZ,
  supersession_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (plan_id, work_order_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS cp_plan_work_orders_job_idx
  ON cp_plan_work_orders(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cp_plan_work_orders_state_idx
  ON cp_plan_work_orders(state, updated_at);

CREATE TABLE IF NOT EXISTS cp_plan_work_order_checkpoints (
  id BIGSERIAL PRIMARY KEY,
  checkpoint_key TEXT NOT NULL UNIQUE,
  plan_id TEXT NOT NULL,
  work_order_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  state TEXT NOT NULL,
  job_id TEXT,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL,
  FOREIGN KEY (plan_id, work_order_id)
    REFERENCES cp_plan_work_orders(plan_id, work_order_id)
);
CREATE INDEX IF NOT EXISTS cp_plan_work_order_checkpoints_plan_idx
  ON cp_plan_work_order_checkpoints(plan_id, id);
CREATE INDEX IF NOT EXISTS cp_plan_work_order_checkpoints_work_order_idx
  ON cp_plan_work_order_checkpoints(plan_id, work_order_id, id);

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

ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS lifecycle TEXT NOT NULL DEFAULT 'active';
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ;
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS supervision_generation BIGINT NOT NULL DEFAULT 0;
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS supervision_state TEXT;
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS supervision_checkpoint_id BIGINT;
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS supervision_checkpoint_key TEXT;
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS supervision_checkpoint_work_order_id TEXT;
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS supervision_ready_work_order_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS supervision_continuation_key TEXT;
ALTER TABLE cp_plan_orchestrations
  ADD COLUMN IF NOT EXISTS supervision_released_at TIMESTAMPTZ;
ALTER TABLE cp_plan_work_orders
  ADD COLUMN IF NOT EXISTS lifecycle TEXT NOT NULL DEFAULT 'active';
ALTER TABLE cp_plan_work_orders
  ADD COLUMN IF NOT EXISTS superseded_by_plan_id TEXT;
ALTER TABLE cp_plan_work_orders
  ADD COLUMN IF NOT EXISTS superseded_by_work_order_id TEXT;
ALTER TABLE cp_plan_work_orders
  ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ;
ALTER TABLE cp_plan_work_orders
  ADD COLUMN IF NOT EXISTS supersession_reason TEXT;
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
_ATTENTION_WORK_ORDER_STATES = {"awaiting_merge", "blocked", "waiting_human"}
_SUPERSEDEABLE_WORK_ORDER_STATES = {"awaiting_merge", "blocked", "pending", "waiting_human"}
_CHECKPOINT_TRANSITIONS = {
    "started": ({"pending"}, "running"),
    "waiting_human": ({"pending", "running"}, "waiting_human"),
    "accepted": ({"running", "waiting_human"}, "awaiting_merge"),
    "completed": ({"running", "waiting_human"}, "completed"),
    "merged": ({"awaiting_merge"}, "completed"),
    "blocked": ({"pending", "running", "waiting_human", "awaiting_merge"}, "blocked"),
    "recovered_accepted": ({"blocked"}, "awaiting_merge"),
    "repair_reopened": ({"awaiting_merge"}, "running"),
}
_OWNER_ATTENTION_EVENT_TYPES = {
    "ci_failed_after_repairs",
    "human_decision_required",
    "operator_action_required",
    "provider_quota_exhausted",
    "work_order_blocked",
}
CHECKPOINT_EVIDENCE_MAX_BYTES = 16 * 1024


class PlanContinuationConflict(RuntimeError):
    """The supplied continuation does not match the current durable plan gate."""


def plan_execution_mode(plan: dict[str, Any]) -> str:
    mode = plan.get("execution_mode", "autonomous")
    if mode not in {"autonomous", "supervised"}:
        raise RuntimeError("ExecutionPlan has an invalid execution mode")
    return str(mode)


def build_continuation_key(
    *,
    plan_id: str,
    generation: int,
    checkpoint_id: int,
    checkpoint_key: str,
    ready_work_order_ids: list[str],
) -> str:
    identity = {
        "checkpoint_id": checkpoint_id,
        "checkpoint_key": checkpoint_key,
        "generation": generation,
        "plan_id": plan_id,
        "ready_work_order_ids": sorted(ready_work_order_ids),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "plan:continue:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def supervision_read_model(
    plan: dict[str, Any], orchestration: dict[str, Any],
) -> dict[str, Any]:
    mode = plan_execution_mode(plan)
    result: dict[str, Any] = {"mode": mode, "state": None}
    if mode != "supervised" or int(orchestration.get("supervision_generation") or 0) < 1:
        return result
    ready = orchestration.get("supervision_ready_work_order_ids") or []
    result.update(
        state=orchestration.get("supervision_state"),
        generation=int(orchestration["supervision_generation"]),
        checkpoint={
            "id": orchestration.get("supervision_checkpoint_id"),
            "checkpoint_key": orchestration.get("supervision_checkpoint_key"),
            "work_order_id": orchestration.get("supervision_checkpoint_work_order_id"),
        },
        ready_work_order_ids=list(ready),
        continuation_key=orchestration.get("supervision_continuation_key"),
    )
    return result


def _checkpoint_evidence_json(evidence: dict[str, Any]) -> str:
    if not isinstance(evidence, dict):
        raise ValueError("Checkpoint evidence must be a JSON object")
    try:
        serialized = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        size = len(serialized.encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Checkpoint evidence must be serializable JSON") from exc
    if size > CHECKPOINT_EVIDENCE_MAX_BYTES:
        raise ValueError(f"Checkpoint evidence exceeds {CHECKPOINT_EVIDENCE_MAX_BYTES} bytes")
    return serialized


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

                # New supervised plans are held before generation-zero launch so
                # their decomposition can be reviewed before any executor job,
                # workspace mutation or project lease is created. Historical
                # generation-zero plans retain their existing semantics because
                # only newly registered plans receive this checkpoint.
                if (
                    plan_execution_mode(plan) == "supervised"
                    and not plan.get("decision_boundaries")
                    and work_orders
                ):
                    states = {
                        str(work_order["id"]): "pending"
                        for work_order in work_orders
                    }
                    ready = sorted(dependency_ready_work_order_ids(plan, states))
                    if ready:
                        checkpoint = self._append_checkpoint(
                            conn,
                            checkpoint_key=f"plan:supervision-initial:{row['id']}",
                            plan_id=str(row["id"]),
                            work_order_id=ready[0],
                            kind="supervision_initial",
                            state="pending",
                            evidence={"ready_work_order_ids": ready},
                        )
                        generation = 1
                        continuation_key = build_continuation_key(
                            plan_id=str(row["id"]),
                            generation=generation,
                            checkpoint_id=int(checkpoint["id"]),
                            checkpoint_key=str(checkpoint["checkpoint_key"]),
                            ready_work_order_ids=ready,
                        )
                        conn.execute(
                            """UPDATE cp_plan_orchestrations
                            SET status='supervised_hold',
                                supervision_generation=%s,
                                supervision_state='held',
                                supervision_checkpoint_id=%s,
                                supervision_checkpoint_key=%s,
                                supervision_checkpoint_work_order_id=%s,
                                supervision_ready_work_order_ids=%s::jsonb,
                                supervision_continuation_key=%s,
                                supervision_released_at=NULL,
                                updated_at=%s
                            WHERE plan_id=%s""",
                            (
                                generation,
                                checkpoint["id"],
                                checkpoint["checkpoint_key"],
                                checkpoint["work_order_id"],
                                json.dumps(ready),
                                continuation_key,
                                timestamp,
                                row["id"],
                            ),
                        )
                registered.append(str(row["id"]))
            conn.commit()
        return registered

    def active_plans(self) -> list[dict[str, Any]]:
        """Return non-completed plans that still require reconciliation.

        Blocked plans remain non-launchable, but must stay observable here so a
        same-child state transition that already completed outside the parent
        loop can be reconciled from exact durable delivery evidence.
        """
        self.ensure()
        with self.storage.connect() as conn:
            return list(
                conn.execute(
                    """SELECT o.*, p.baseline_revision, p.baseline_source_commit,
                              p.ticket, p.plan, p.staffing
                    FROM cp_plan_orchestrations o
                    JOIN cp_execution_plans p ON p.id=o.plan_id
                    WHERE o.lifecycle='active'
                      AND o.status <> 'completed'
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

    def append_checkpoint(
        self,
        *,
        checkpoint_key: str,
        plan_id: str,
        work_order_id: str,
        kind: str,
        state: str,
        job_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append compact execution evidence, or return an identical retry.

        Callers supply a stable transition key and summaries only: never raw
        transcripts, logs, prompts, Runtime results or filesystem contents.
        The store owns the timestamp; retries cannot refresh historical evidence.
        Schema installation belongs to ensure() at orchestrator startup.
        """
        with self.storage.connect() as conn:
            row = self._append_checkpoint(
                conn, checkpoint_key=checkpoint_key, plan_id=plan_id,
                work_order_id=work_order_id, kind=kind, state=state,
                job_id=job_id, evidence=evidence,
            )
            conn.commit()
            return row

    def _append_checkpoint(
        self, conn: Any, *, checkpoint_key: str, plan_id: str,
        work_order_id: str, kind: str, state: str,
        job_id: str | None = None, evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Shared append validation/insert; the caller owns the transaction."""
        identity = {
            "checkpoint_key": checkpoint_key,
            "plan_id": plan_id,
            "work_order_id": work_order_id,
            "kind": kind,
            "state": state,
            "job_id": job_id,
        }
        for field, value in identity.items():
            if field == "job_id" and value is None:
                continue
            limit = 500 if field == "checkpoint_key" else 200
            if (
                not isinstance(value, str) or not value or value != value.strip()
                or len(value) > limit or "\x00" in value
            ):
                raise ValueError(f"Checkpoint {field} must be an exact non-empty string of at most {limit} characters")
        serialized = _checkpoint_evidence_json({} if evidence is None else evidence)
        tracked = conn.execute(
            """SELECT 1 FROM cp_plan_work_orders
            WHERE plan_id=%s AND work_order_id=%s FOR KEY SHARE""",
            (plan_id, work_order_id),
        ).fetchone()
        if tracked is None:
            raise RuntimeError("Unknown checkpoint plan/WorkOrder identity")
        row = conn.execute(
            """INSERT INTO cp_plan_work_order_checkpoints
            (checkpoint_key, plan_id, work_order_id, kind, state, job_id, evidence, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (checkpoint_key) DO NOTHING RETURNING *""",
            (checkpoint_key, plan_id, work_order_id, kind, state, job_id, serialized, now()),
        ).fetchone()
        if row is None:
            # A separate statement sees the committed winner of a concurrent
            # insert under PostgreSQL's default READ COMMITTED isolation.
            # JSONB equality ignores object-key ordering and numeric spelling,
            # while retaining JSON types (true is not the number 1).
            row = conn.execute(
                """SELECT * FROM cp_plan_work_order_checkpoints
                WHERE checkpoint_key=%s AND plan_id=%s AND work_order_id=%s
                  AND kind=%s AND state=%s AND job_id IS NOT DISTINCT FROM %s
                  AND evidence=%s::jsonb""",
                (checkpoint_key, plan_id, work_order_id, kind, state, job_id, serialized),
            ).fetchone()
            if row is None:
                raise RuntimeError("Checkpoint key already has different identity/content")
        return dict(row)

    def checkpoints(self, plan_id: str, *, work_order_id: str | None = None) -> list[dict[str, Any]]:
        """Read all durable history, including superseded WorkOrders, by row ID."""
        where = "plan_id=%s"
        params = [plan_id]
        if work_order_id is not None:
            where += " AND work_order_id=%s"
            params.append(work_order_id)
        with self.storage.connect() as conn:
            return list(conn.execute(
                f"SELECT * FROM cp_plan_work_order_checkpoints WHERE {where} ORDER BY id",
                params,
            ).fetchall())

    def progress_snapshot(self, plan_id: str) -> dict[str, Any] | None:
        """Read one consistent snapshot without DDL, reconciliation or scheduling."""
        with self.storage.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            plan = conn.execute(
                """SELECT o.plan_id,o.project_id,o.ticket_id,o.status,o.lifecycle,
                          o.supervision_generation,o.supervision_state,
                          o.supervision_checkpoint_id,o.supervision_checkpoint_key,
                          o.supervision_checkpoint_work_order_id,
                          o.supervision_ready_work_order_ids,o.supervision_continuation_key,
                          p.plan
                FROM cp_plan_orchestrations o
                LEFT JOIN cp_execution_plans p ON p.id=o.plan_id
                WHERE o.plan_id=%s""",
                (plan_id,),
            ).fetchone()
            if plan is None:
                return None
            rows = list(conn.execute(
                """SELECT work_order_id, state, job_id FROM cp_plan_work_orders
                WHERE plan_id=%s AND lifecycle='active' ORDER BY sequence_no, work_order_id""",
                (plan_id,),
            ).fetchall())
            latest = conn.execute(
                """SELECT * FROM cp_plan_work_order_checkpoints
                WHERE plan_id=%s ORDER BY id DESC LIMIT 1""",
                (plan_id,),
            ).fetchone()
            blocked_inputs = blocked_evidence_checkpoint_rows(conn, plan_id, rows)
            return {
                "orchestration": dict(plan),
                "work_orders": rows,
                "last_checkpoint": latest,
                **blocked_inputs,
            }

    @staticmethod
    def _terminal_checkpoint(conn: Any, plan_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """SELECT c.* FROM cp_plan_work_order_checkpoints c
            JOIN cp_plan_work_orders w
              ON w.plan_id=c.plan_id AND w.work_order_id=c.work_order_id
            WHERE c.plan_id=%s AND w.lifecycle='active' AND w.state='completed'
              AND c.kind IN ('completed','merged')
              AND c.job_id IS NOT DISTINCT FROM w.job_id
            ORDER BY c.id DESC LIMIT 1""",
            (plan_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _supervision_identity_matches(
        orchestration: dict[str, Any], checkpoint: dict[str, Any], ready: list[str],
    ) -> bool:
        return (
            orchestration.get("supervision_checkpoint_id") == checkpoint.get("id")
            and orchestration.get("supervision_checkpoint_key") == checkpoint.get("checkpoint_key")
            and list(orchestration.get("supervision_ready_work_order_ids") or []) == ready
        )

    def reconcile_supervision(self, plan_id: str) -> dict[str, Any] | None:
        """Create or preserve the exact between-WorkOrder supervised gate."""
        with self.storage.connect() as conn:
            orchestration = conn.execute(
                """SELECT o.*, p.plan FROM cp_plan_orchestrations o
                JOIN cp_execution_plans p ON p.id=o.plan_id
                WHERE o.plan_id=%s FOR UPDATE OF o""",
                (plan_id,),
            ).fetchone()
            if orchestration is None:
                return None
            current = dict(orchestration)
            plan = dict(current.get("plan") or {})
            if plan_execution_mode(plan) != "supervised":
                conn.commit()
                return supervision_read_model(plan, current)
            if current.get("lifecycle") != "active" or plan.get("decision_boundaries"):
                conn.commit()
                return supervision_read_model(plan, current)

            rows = list(conn.execute(
                """SELECT work_order_id,state FROM cp_plan_work_orders
                WHERE plan_id=%s AND lifecycle='active'
                ORDER BY sequence_no,work_order_id""",
                (plan_id,),
            ).fetchall())
            states = {str(row["work_order_id"]): str(row["state"]) for row in rows}
            if (
                not rows
                or any(state in _BUSY_WORK_ORDER_STATES | {"blocked"} for state in states.values())
                or all(state == "completed" for state in states.values())
            ):
                conn.commit()
                return supervision_read_model(plan, current)

            ready = sorted(dependency_ready_work_order_ids(plan, states))
            checkpoint = self._terminal_checkpoint(conn, plan_id)
            if not ready or checkpoint is None:
                conn.commit()
                return supervision_read_model(plan, current)

            if self._supervision_identity_matches(current, checkpoint, ready):
                if current.get("supervision_state") == "held" and current.get("status") != "supervised_hold":
                    conn.execute(
                        """UPDATE cp_plan_orchestrations
                        SET status='supervised_hold',updated_at=%s WHERE plan_id=%s""",
                        (now(), plan_id),
                    )
                    current["status"] = "supervised_hold"
                conn.commit()
                return supervision_read_model(plan, current)

            generation = int(current.get("supervision_generation") or 0) + 1
            key = build_continuation_key(
                plan_id=plan_id,
                generation=generation,
                checkpoint_id=int(checkpoint["id"]),
                checkpoint_key=str(checkpoint["checkpoint_key"]),
                ready_work_order_ids=ready,
            )
            timestamp = now()
            conn.execute(
                """UPDATE cp_plan_orchestrations
                SET status='supervised_hold',supervision_generation=%s,
                    supervision_state='held',supervision_checkpoint_id=%s,
                    supervision_checkpoint_key=%s,
                    supervision_checkpoint_work_order_id=%s,
                    supervision_ready_work_order_ids=%s::jsonb,
                    supervision_continuation_key=%s,supervision_released_at=NULL,
                    updated_at=%s
                WHERE plan_id=%s""",
                (
                    generation,
                    checkpoint["id"],
                    checkpoint["checkpoint_key"],
                    checkpoint["work_order_id"],
                    json.dumps(ready),
                    key,
                    timestamp,
                    plan_id,
                ),
            )
            current.update(
                status="supervised_hold",
                supervision_generation=generation,
                supervision_state="held",
                supervision_checkpoint_id=checkpoint["id"],
                supervision_checkpoint_key=checkpoint["checkpoint_key"],
                supervision_checkpoint_work_order_id=checkpoint["work_order_id"],
                supervision_ready_work_order_ids=ready,
                supervision_continuation_key=key,
                supervision_released_at=None,
            )
            conn.commit()
            return supervision_read_model(plan, current)

    def supervision_allows_launch(self, plan_id: str) -> bool:
        """Read the plan gate immediately before the existing launch path mutates."""
        with self.storage.connect() as conn:
            row = conn.execute(
                """SELECT o.status,o.supervision_generation,o.supervision_state,p.plan
                FROM cp_plan_orchestrations o JOIN cp_execution_plans p ON p.id=o.plan_id
                WHERE o.plan_id=%s""",
                (plan_id,),
            ).fetchone()
            if row is None:
                return False
            if plan_execution_mode(dict(row.get("plan") or {})) == "autonomous":
                return True
            if row.get("status") == "supervised_hold" or row.get("supervision_state") == "held":
                return False
            if row.get("supervision_state") == "released":
                return True
            if int(row.get("supervision_generation") or 0) != 0:
                return False
            # Generation zero is launchable only before the first durable
            # terminal boundary. This keeps a direct _launch_one() invocation
            # from skipping reconciliation and creating WO-2 before its hold.
            return self._terminal_checkpoint(conn, plan_id) is None

    def _mark_supervision_released(
        self, conn: Any, *, plan_id: str, generation: int,
    ) -> None:
        result = conn.execute(
            """UPDATE cp_plan_orchestrations
            SET supervision_state='released',supervision_released_at=%s,
                status='active',updated_at=%s
            WHERE plan_id=%s AND supervision_generation=%s
              AND supervision_state='held' AND status='supervised_hold'""",
            (now(), now(), plan_id, generation),
        )
        if result.rowcount != 1:
            raise PlanContinuationConflict("Supervised continuation changed before release")

    def release_supervision(
        self,
        *,
        plan_id: str,
        generation: int,
        continuation_key: str,
        checkpoint_id: int,
        checkpoint_key: str,
        ready_work_order_ids: list[str],
    ) -> dict[str, Any]:
        """Atomically release one exact held generation or return its exact retry."""
        ready = list(ready_work_order_ids)
        if ready != sorted(set(ready)):
            raise PlanContinuationConflict("Continuation ready WorkOrder set must be unique and sorted")
        with self.storage.connect() as conn:
            orchestration = conn.execute(
                """SELECT o.*,p.plan FROM cp_plan_orchestrations o
                JOIN cp_execution_plans p ON p.id=o.plan_id
                WHERE o.plan_id=%s FOR UPDATE OF o""",
                (plan_id,),
            ).fetchone()
            if orchestration is None:
                raise PlanContinuationConflict("Unknown orchestration plan")
            current = dict(orchestration)
            plan = dict(current.get("plan") or {})
            if plan_execution_mode(plan) != "supervised":
                raise PlanContinuationConflict("ExecutionPlan is not supervised")
            if current.get("lifecycle") != "active":
                raise PlanContinuationConflict("ExecutionPlan is not active")
            if plan.get("decision_boundaries"):
                raise PlanContinuationConflict("ExecutionPlan has an unresolved Human Owner decision boundary")

            expected_key = build_continuation_key(
                plan_id=plan_id,
                generation=generation,
                checkpoint_id=checkpoint_id,
                checkpoint_key=checkpoint_key,
                ready_work_order_ids=ready,
            )
            exact = (
                current.get("supervision_generation") == generation
                and current.get("supervision_checkpoint_id") == checkpoint_id
                and current.get("supervision_checkpoint_key") == checkpoint_key
                and list(current.get("supervision_ready_work_order_ids") or []) == ready
                and current.get("supervision_continuation_key") == continuation_key
                and continuation_key == expected_key
            )
            if not exact:
                raise PlanContinuationConflict("Continuation identity does not match the current supervised generation")
            if current.get("supervision_state") == "released":
                conn.commit()
                return {"changed": False, "supervision": supervision_read_model(plan, current)}
            if current.get("status") in {"blocked", "waiting_human", "waiting_merge"}:
                raise PlanContinuationConflict("ExecutionPlan is at a separate protected or child gate")
            if current.get("supervision_state") != "held" or current.get("status") != "supervised_hold":
                raise PlanContinuationConflict("ExecutionPlan is not at the current supervised hold")

            rows = list(conn.execute(
                """SELECT work_order_id,state,job_id FROM cp_plan_work_orders
                WHERE plan_id=%s AND lifecycle='active'
                ORDER BY sequence_no,work_order_id""",
                (plan_id,),
            ).fetchall())
            states = {str(row["work_order_id"]): str(row["state"]) for row in rows}
            terminal = self._terminal_checkpoint(conn, plan_id)

            held_checkpoint = terminal
            if terminal is None and generation == 1:
                initial = conn.execute(
                    """SELECT * FROM cp_plan_work_order_checkpoints
                    WHERE plan_id=%s AND id=%s AND checkpoint_key=%s
                      AND kind='supervision_initial' AND state='pending'
                    LIMIT 1""",
                    (plan_id, checkpoint_id, checkpoint_key),
                ).fetchone()
                if (
                    initial is not None
                    and all(str(row["state"]) == "pending" for row in rows)
                    and all(row.get("job_id") is None for row in rows)
                ):
                    held_checkpoint = dict(initial)

            if (
                any(state in _BUSY_WORK_ORDER_STATES | {"blocked"} for state in states.values())
                or sorted(dependency_ready_work_order_ids(plan, states)) != ready
                or held_checkpoint is None
                or held_checkpoint.get("id") != checkpoint_id
                or held_checkpoint.get("checkpoint_key") != checkpoint_key
            ):
                raise PlanContinuationConflict("Durable plan state no longer matches the held continuation")
            self._mark_supervision_released(conn, plan_id=plan_id, generation=generation)
            current.update(
                status="active",
                supervision_state="released",
                supervision_released_at=now(),
            )
            conn.commit()
            return {"changed": True, "supervision": supervision_read_model(plan, current)}

    def update_plan(self, plan_id: str, *, status: str) -> bool:
        with self.storage.connect() as conn:
            result = conn.execute(
                """UPDATE cp_plan_orchestrations SET status=%s, updated_at=%s
                WHERE plan_id=%s AND status IS DISTINCT FROM %s""",
                (status, now(), plan_id, status),
            )
            conn.commit()
            return bool(result.rowcount)

    def update_work_order(self, plan_id: str, work_order_id: str, **fields: Any) -> bool:
        with self.storage.connect() as conn:
            changed = self._update_work_order(conn, plan_id, work_order_id, **fields)
            conn.commit()
            return changed

    def _update_work_order(self, conn: Any, plan_id: str, work_order_id: str, **fields: Any) -> bool:
        """Existing mutable update and attention retirement in the caller's transaction."""
        allowed = {"state", "job_id", "pr_number", "pr_url", "detail"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported plan work-order fields: {sorted(unknown)}")
        if not fields:
            return False

        normalized = {
            key: (dict(value or {}) if key == "detail" else value)
            for key, value in fields.items()
        }
        current = conn.execute(
            """SELECT * FROM cp_plan_work_orders
            WHERE plan_id=%s AND work_order_id=%s FOR UPDATE""",
            (plan_id, work_order_id),
        ).fetchone()
        if current is None or all(current.get(key) == value for key, value in normalized.items()):
            return False

        previous_state = str(current.get("state") or "")
        sets: list[str] = []
        values: list[Any] = []
        for key, value in normalized.items():
            if key == "detail":
                sets.append("detail=%s::jsonb")
                values.append(json.dumps(value))
            else:
                sets.append(f"{key}=%s")
                values.append(value)
        sets.append("updated_at=%s")
        values.append(now())
        values.extend([plan_id, work_order_id])
        conn.execute(
            f"UPDATE cp_plan_work_orders SET {', '.join(sets)} WHERE plan_id=%s AND work_order_id=%s",
            values,
        )
        if previous_state in _ATTENTION_WORK_ORDER_STATES:
            self._supersede_notification_rows(
                conn, plan_id=plan_id, work_order_id=work_order_id,
                attention_state=previous_state,
            )
            conn.execute(
                """UPDATE cp_control_actions SET status='cancelled', updated_at=%s
                WHERE status='pending' AND plan_id=%s AND work_order_id=%s""",
                (now(), plan_id, work_order_id),
            )
        return True

    def transition_work_order(
        self, *, expected: dict[str, Any], checkpoint_key: str, kind: str,
        evidence: dict[str, Any], **fields: Any,
    ) -> dict[str, Any]:
        """Commit one exact lifecycle mutation and its evidence, or neither.

        Exact retries validate the original checkpoint and never reapply an old
        mutation. Dependency evidence is a store-owned post-transition snapshot.
        """
        plan_id, work_order_id = expected["plan_id"], expected["work_order_id"]
        state = fields["state"]
        job_id = fields.get("job_id", expected.get("job_id"))
        sources, target = _CHECKPOINT_TRANSITIONS.get(kind, (set(), None))
        if expected.get("state") not in sources or state != target:
            raise RuntimeError("Invalid checkpoint transition kind/state")
        if job_id != expected.get("job_id") and kind != "started":
            raise RuntimeError("Checkpoint transition cannot replace the Runtime job")
        if {"transition", "dependencies", "next"} & evidence.keys():
            raise ValueError("Transition and dependency evidence is store-owned")
        with self.storage.connect() as conn:
            # Match supersession's plan-before-WorkOrder lock order. Serialize
            # checkpoint transitions within one plan, including dependency reads.
            plan = conn.execute(
                "SELECT * FROM cp_plan_orchestrations WHERE plan_id=%s FOR UPDATE", (plan_id,),
            ).fetchone()
            current = conn.execute(
                """SELECT * FROM cp_plan_work_orders
                WHERE plan_id=%s AND work_order_id=%s FOR UPDATE""", (plan_id, work_order_id),
            ).fetchone()
            if plan is None or current is None:
                raise RuntimeError("Unknown checkpoint plan/WorkOrder identity")
            existing = conn.execute(
                "SELECT * FROM cp_plan_work_order_checkpoints WHERE checkpoint_key=%s", (checkpoint_key,),
            ).fetchone()
            materialized = dict(evidence)
            materialized["transition"] = {
                "from_state": expected["state"],
                "source_updated_at": str(expected.get("updated_at") or ""),
                "source_job_id": expected.get("job_id"),
                "source_pr_number": expected.get("pr_number"),
            }
            if existing is not None:
                # Retry observes its original dependency snapshot, even after a
                # later child has advanced. All caller-owned content is rechecked.
                for key in ("dependencies", "next"):
                    materialized[key] = existing["evidence"].get(key)
            else:
                if plan["lifecycle"] != "active" or current["lifecycle"] != "active":
                    raise RuntimeError("Superseded orchestration cannot transition")
                if any(current.get(key) != expected.get(key) for key in (
                    "state", "job_id", "pr_number", "updated_at",
                )):
                    raise RuntimeError("Stale WorkOrder transition identity/state")
                definition = conn.execute(
                    "SELECT plan FROM cp_execution_plans WHERE id=%s", (plan_id,),
                ).fetchone()
                plan_doc = (definition or {}).get("plan") or {}
                rows = list(conn.execute(
                    """SELECT work_order_id, state FROM cp_plan_work_orders
                    WHERE plan_id=%s AND lifecycle='active' ORDER BY sequence_no, work_order_id""", (plan_id,),
                ).fetchall())
                states = {row["work_order_id"]: row["state"] for row in rows}
                states[work_order_id] = state
                definitions = {item["id"]: item for item in plan_doc.get("work_orders") or []}
                dependencies = definitions.get(work_order_id, {}).get("dependencies") or []
                materialized["dependencies"] = {dep: states.get(dep) for dep in dependencies}
                materialized["next"] = dependency_ready_work_order_ids(plan_doc, states)
                self._update_work_order(conn, plan_id, work_order_id, **fields)
            checkpoint = self._append_checkpoint(
                conn, checkpoint_key=checkpoint_key, plan_id=plan_id, work_order_id=work_order_id,
                kind=kind, state=state, job_id=job_id, evidence=materialized,
            )
            conn.commit()
            return checkpoint

    def release_launch(self, plan_id: str, work_order_id: str, job_id: str) -> bool:
        """Release only a never-executed reservation with durable started proof."""
        identity = launch_identity(plan_id, work_order_id)
        if job_id != identity["job_id"]:
            raise RuntimeError("Mismatched orchestrator launch job")
        with self.storage.connect() as conn:
            plan = conn.execute(
                "SELECT * FROM cp_plan_orchestrations WHERE plan_id=%s FOR UPDATE", (plan_id,),
            ).fetchone()
            tracked = conn.execute(
                "SELECT * FROM cp_plan_work_orders WHERE plan_id=%s AND work_order_id=%s FOR UPDATE",
                (plan_id, work_order_id),
            ).fetchone()
            if (not plan or not tracked or plan["lifecycle"] != "active" or tracked["lifecycle"] != "active"
                    or tracked["execution_mode"] != "agent" or tracked["state"] != "running" or tracked["job_id"] != job_id):
                raise RuntimeError("Orchestrator launch requires exact active running WorkOrder")
            key = transition_key(tracked, "started", job_id, {})
            proof = conn.execute(
                """SELECT 1 FROM cp_plan_work_order_checkpoints
                WHERE checkpoint_key=%s AND plan_id=%s AND work_order_id=%s AND job_id=%s
                  AND kind='started' AND state='running'""", (key, plan_id, work_order_id, job_id),
            ).fetchone()
            if proof is None:
                raise RuntimeError("Orchestrator launch lacks exact durable started checkpoint")
            job = conn.execute("SELECT * FROM cp_jobs WHERE id=%s FOR UPDATE", (job_id,)).fetchone()
            marker = orchestrator_launch(job or {})
            if (not marker or job["project_id"] != plan["project_id"]
                    or any(marker.get(key) != value for key, value in identity.items())):
                raise RuntimeError("Orchestrator launch lacks exact reservation")
            if job["status"] != "queued" or marker["state"] == "launched":
                return False
            if marker["state"] == "held":
                conn.execute(
                    """UPDATE cp_jobs SET checkpoint=jsonb_set(checkpoint, '{orchestrator_launch,state}', '"ready"'),
                    updated_at=%s WHERE id=%s""", (now(), job_id),
                )
            conn.commit()
            return True

    def supersede_work_order(
        self,
        *,
        plan_id: str,
        work_order_id: str,
        reason: str,
        superseded_by_plan_id: str | None = None,
        superseded_by_work_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Retire one exact tracked WorkOrder without changing execution truth.

        The operation changes orchestration eligibility only. It never updates the
        tracked state, Runtime job, result, progress, workspace, or counters.
        """
        self.ensure()
        reason = reason.strip()[:2000]
        replacement_plan_id = superseded_by_plan_id or None
        replacement_work_order_id = superseded_by_work_order_id or None
        identities = [plan_id, work_order_id]
        identities.extend(
            value
            for value in (replacement_plan_id, replacement_work_order_id)
            if value is not None
        )
        if any(not value or value != value.strip() for value in identities) or not reason:
            raise RuntimeError("Supersession requires exact plan, WorkOrder, and reason")
        if bool(replacement_plan_id) != bool(replacement_work_order_id):
            raise RuntimeError("Replacement plan and WorkOrder identities must be supplied together")
        if (replacement_plan_id, replacement_work_order_id) == (plan_id, work_order_id):
            raise RuntimeError("A WorkOrder cannot supersede itself")

        timestamp = now()
        with self.storage.connect() as conn:
            plan = conn.execute(
                "SELECT * FROM cp_plan_orchestrations WHERE plan_id=%s FOR UPDATE",
                (plan_id,),
            ).fetchone()
            if plan is None:
                raise RuntimeError("Unknown orchestration plan")
            tracked = conn.execute(
                """SELECT * FROM cp_plan_work_orders
                WHERE plan_id=%s AND work_order_id=%s FOR UPDATE""",
                (plan_id, work_order_id),
            ).fetchone()
            if tracked is None:
                raise RuntimeError("Unknown orchestrated WorkOrder")

            current = dict(tracked)
            if str(current.get("lifecycle") or "active") == "superseded":
                existing = (
                    current.get("superseded_by_plan_id"),
                    current.get("superseded_by_work_order_id"),
                    current.get("supersession_reason"),
                )
                requested = (replacement_plan_id, replacement_work_order_id, reason)
                if existing != requested:
                    raise RuntimeError("WorkOrder is already superseded with different metadata")
                conn.commit()
                return {"changed": False, "plan": dict(plan), "work_order": current}
            if str(plan.get("lifecycle") or "active") != "active":
                raise RuntimeError("Orchestration plan is not active")
            source_state = str(current.get("state") or "")
            if source_state not in _SUPERSEDEABLE_WORK_ORDER_STATES:
                raise RuntimeError(
                    f"WorkOrder cannot be superseded from state={source_state}"
                )
            source_job_id = str(current.get("job_id") or "")
            if source_job_id:
                source_job = conn.execute(
                    "SELECT status FROM cp_jobs WHERE id=%s",
                    (source_job_id,),
                ).fetchone()
                if source_job is None:
                    raise RuntimeError("Supersession target is missing its Runtime job")
                if str(source_job.get("status") or "") in _ACTIVE_JOB_STATUSES:
                    raise RuntimeError("An in-flight Runtime job cannot be superseded")

            if replacement_plan_id and replacement_work_order_id:
                replacement_plan = conn.execute(
                    "SELECT * FROM cp_plan_orchestrations WHERE plan_id=%s",
                    (replacement_plan_id,),
                ).fetchone()
                if replacement_plan is None:
                    raise RuntimeError("Unknown replacement orchestration plan")
                if replacement_plan.get("project_id") != plan.get("project_id"):
                    raise RuntimeError("Replacement orchestration project does not match")
                replacement = conn.execute(
                    """SELECT * FROM cp_plan_work_orders
                    WHERE plan_id=%s AND work_order_id=%s""",
                    (replacement_plan_id, replacement_work_order_id),
                ).fetchone()
                if replacement is None:
                    raise RuntimeError("Unknown replacement orchestrated WorkOrder")
                if str(replacement.get("lifecycle") or "active") != "active":
                    raise RuntimeError("Replacement WorkOrder is not active orchestration history")

            conn.execute(
                """UPDATE cp_plan_work_orders
                SET lifecycle='superseded', superseded_by_plan_id=%s,
                    superseded_by_work_order_id=%s, superseded_at=%s,
                    supersession_reason=%s, updated_at=%s
                WHERE plan_id=%s AND work_order_id=%s AND lifecycle='active'""",
                (
                    replacement_plan_id,
                    replacement_work_order_id,
                    timestamp,
                    reason,
                    timestamp,
                    plan_id,
                    work_order_id,
                ),
            )
            self._supersede_all_attention_rows(
                conn,
                plan_id=plan_id,
                work_order_id=work_order_id,
            )
            conn.execute(
                """UPDATE cp_control_actions SET status='cancelled', updated_at=%s
                WHERE status='pending' AND plan_id=%s AND work_order_id=%s""",
                (timestamp, plan_id, work_order_id),
            )
            remaining = list(conn.execute(
                """SELECT state FROM cp_plan_work_orders
                WHERE plan_id=%s AND lifecycle='active'
                ORDER BY sequence_no, work_order_id""",
                (plan_id,),
            ).fetchall())
            if not remaining:
                conn.execute(
                    """UPDATE cp_plan_orchestrations
                    SET lifecycle='superseded', superseded_at=%s, updated_at=%s
                    WHERE plan_id=%s AND lifecycle='active'""",
                    (timestamp, timestamp, plan_id),
                )
                self._supersede_plan_attention_rows(conn, plan_id=plan_id)
            else:
                states = [str(row.get("state") or "") for row in remaining]
                if any(state == "blocked" for state in states):
                    plan_status = "blocked"
                elif any(state == "waiting_human" for state in states):
                    plan_status = "waiting_human"
                elif any(state == "awaiting_merge" for state in states):
                    plan_status = "waiting_merge"
                elif any(state == "running" for state in states):
                    plan_status = "executing"
                elif states and all(state == "completed" for state in states):
                    plan_status = "completed"
                else:
                    plan_status = "active"
                conn.execute(
                    """UPDATE cp_plan_orchestrations SET status=%s, updated_at=%s
                    WHERE plan_id=%s AND status IS DISTINCT FROM %s""",
                    (plan_status, timestamp, plan_id, plan_status),
                )
            work_order = conn.execute(
                """SELECT * FROM cp_plan_work_orders
                WHERE plan_id=%s AND work_order_id=%s""",
                (plan_id, work_order_id),
            ).fetchone()
            updated_plan = conn.execute(
                "SELECT * FROM cp_plan_orchestrations WHERE plan_id=%s",
                (plan_id,),
            ).fetchone()
            conn.commit()
            return {
                "changed": True,
                "plan": dict(updated_plan or plan),
                "work_order": dict(work_order or current),
            }

    @staticmethod
    def _legacy_attention_state_sql() -> str:
        return """CASE
          WHEN payload->>'attention_state' <> '' THEN payload->>'attention_state'
          WHEN payload#>>'{advisory,reason}' = 'awaiting_merge' THEN 'awaiting_merge'
          WHEN payload#>>'{advisory,reason}' IN ('human_decision_required','operator_waiting_human')
            THEN 'waiting_human'
          WHEN event_type = 'work_order_blocked' THEN 'blocked'
          ELSE NULL
        END"""

    @staticmethod
    def _is_owner_attention(*, event_type: str, payload: dict[str, Any] | None) -> bool:
        materialized_payload = dict(payload or {})
        raw_attention_state = materialized_payload.get("attention_state")
        attention_state = "" if raw_attention_state is None else str(raw_attention_state)
        raw_advisory = materialized_payload.get("advisory")
        advisory = raw_advisory if isinstance(raw_advisory, dict) else {}
        raw_advisory_reason = advisory.get("reason")
        advisory_reason = "" if raw_advisory_reason is None else str(raw_advisory_reason)
        return bool(
            event_type in _OWNER_ATTENTION_EVENT_TYPES
            or attention_state
            or advisory_reason
            in {"awaiting_merge", "human_decision_required", "operator_waiting_human"}
        )

    @classmethod
    def _owner_attention_sql(cls) -> str:
        return f"""(({cls._legacy_attention_state_sql()}) IS NOT NULL
          OR event_type = ANY(%s))"""

    def _supersede_notification_rows(
        self,
        conn: Any,
        *,
        plan_id: str,
        work_order_id: str,
        attention_state: str,
        except_generation: str | None = None,
    ) -> int:
        generation_filter = ""
        values: list[Any] = [now(), plan_id, work_order_id, attention_state]
        if except_generation is not None:
            generation_filter = " AND COALESCE(payload->>'attention_generation','') <> %s"
            values.append(except_generation)
        result = conn.execute(
            f"""UPDATE cp_notification_outbox
            SET status='superseded', lease_until=NULL, updated_at=%s
            WHERE status IN ('pending','delivering')
              AND plan_id=%s AND work_order_id=%s
              AND ({self._legacy_attention_state_sql()})=%s
              {generation_filter}""",
            values,
        )
        return int(result.rowcount or 0)

    def _supersede_all_attention_rows(
        self,
        conn: Any,
        *,
        plan_id: str,
        work_order_id: str,
    ) -> int:
        result = conn.execute(
            f"""UPDATE cp_notification_outbox
            SET status='superseded', lease_until=NULL, updated_at=%s
            WHERE status IN ('pending','delivering')
              AND plan_id=%s AND work_order_id=%s
              AND {self._owner_attention_sql()}""",
            (now(), plan_id, work_order_id, list(_OWNER_ATTENTION_EVENT_TYPES)),
        )
        return int(result.rowcount or 0)

    def _supersede_plan_attention_rows(self, conn: Any, *, plan_id: str) -> int:
        result = conn.execute(
            f"""UPDATE cp_notification_outbox
            SET status='superseded', lease_until=NULL, updated_at=%s
            WHERE status IN ('pending','delivering')
              AND plan_id=%s
              AND {self._owner_attention_sql()}""",
            (now(), plan_id, list(_OWNER_ATTENTION_EVENT_TYPES)),
        )
        return int(result.rowcount or 0)

    def supersede_obsolete_notifications(self) -> int:
        """Retire current or legacy attention rows that no longer match durable state."""
        self.ensure()
        attention_state = self._legacy_attention_state_sql()
        with self.storage.connect() as conn:
            result = conn.execute(
                f"""UPDATE cp_notification_outbox notification
                SET status='superseded', lease_until=NULL, updated_at=%s
                FROM cp_plan_work_orders work_order
                WHERE notification.status IN ('pending','delivering')
                  AND notification.plan_id=work_order.plan_id
                  AND notification.work_order_id=work_order.work_order_id
                  AND ({attention_state}) IS NOT NULL
                  AND (work_order.lifecycle <> 'active'
                    OR ({attention_state}) IS DISTINCT FROM work_order.state)""",
                (now(),),
            )
            conn.commit()
            return int(result.rowcount or 0)

    def any_busy_work_order(self) -> bool:
        with self.storage.connect() as conn:
            row = conn.execute(
                """SELECT 1 FROM cp_plan_work_orders work_order
                JOIN cp_plan_orchestrations plan ON plan.plan_id=work_order.plan_id
                WHERE work_order.lifecycle='active' AND plan.lifecycle='active'
                  AND work_order.state = ANY(%s) LIMIT 1""",
                (list(_BUSY_WORK_ORDER_STATES),),
            ).fetchone()
            return row is not None

    def claim_notification(self, *, lease_seconds: int = 300) -> dict[str, Any] | None:
        self.ensure()
        timestamp = now()
        lease_until = timestamp + timedelta(seconds=max(30, min(1800, lease_seconds)))
        owner_attention_sql = self._owner_attention_sql()
        with self.storage.connect() as conn:
            conn.execute(
                """UPDATE cp_notification_outbox
                SET status='pending', lease_until=NULL, updated_at=%s
                WHERE status='delivering' AND lease_until IS NOT NULL AND lease_until <= %s""",
                (timestamp, timestamp),
            )
            row = conn.execute(
                f"""SELECT * FROM cp_notification_outbox
                WHERE status='pending' AND available_at <= %s
                  AND (
                    NOT {owner_attention_sql}
                    OR (
                      (plan_id IS NULL OR EXISTS (
                        SELECT 1 FROM cp_plan_orchestrations plan
                        WHERE plan.plan_id=cp_notification_outbox.plan_id
                          AND plan.lifecycle='active'
                      ))
                      AND (work_order_id IS NULL OR NOT EXISTS (
                        SELECT 1 FROM cp_plan_work_orders work_order
                        WHERE work_order.plan_id=cp_notification_outbox.plan_id
                          AND work_order.work_order_id=cp_notification_outbox.work_order_id
                          AND work_order.lifecycle <> 'active'
                      ))
                    )
                  )
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1""",
                (timestamp, list(_OWNER_ATTENTION_EVENT_TYPES)),
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
        attention_state: str | None = None,
        attention_generation: str | None = None,
    ) -> bool:
        timestamp = now()
        materialized_payload = dict(payload or {})
        if attention_state and attention_generation:
            materialized_payload["attention_state"] = attention_state
            materialized_payload["attention_generation"] = attention_generation
        owner_attention = self._is_owner_attention(
            event_type=event_type,
            payload=materialized_payload,
        )
        with self.storage.connect() as conn:
            if owner_attention and plan_id:
                eligible_plan = conn.execute(
                    """SELECT 1 FROM cp_plan_orchestrations
                    WHERE plan_id=%s AND lifecycle='active' FOR SHARE""",
                    (plan_id,),
                ).fetchone()
                if eligible_plan is None:
                    conn.commit()
                    return False
            if owner_attention and work_order_id and not plan_id:
                conn.commit()
                return False
            if owner_attention and plan_id and work_order_id:
                eligible = conn.execute(
                    """SELECT 1 FROM cp_plan_work_orders work_order
                    JOIN cp_plan_orchestrations plan ON plan.plan_id=work_order.plan_id
                    WHERE work_order.plan_id=%s AND work_order.work_order_id=%s
                      AND work_order.lifecycle='active' AND plan.lifecycle='active'
                    FOR SHARE OF work_order, plan""",
                    (plan_id, work_order_id),
                ).fetchone()
                if eligible is None:
                    conn.commit()
                    return False
            if attention_state and attention_generation and plan_id and work_order_id:
                self._supersede_notification_rows(
                    conn,
                    plan_id=plan_id,
                    work_order_id=work_order_id,
                    attention_state=attention_state,
                    except_generation=attention_generation,
                )
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
                    json.dumps(materialized_payload),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            return bool(result.rowcount)


class PlanOrchestrator:
    def __init__(self, storage: Storage, engine: Any, *, store: PlanOrchestratorStore | None = None, progress_handoffs: Any = None) -> None:
        self.storage = storage
        self.engine = engine
        self.store = store or PlanOrchestratorStore(storage)
        self.progress_handoffs = progress_handoffs
        self._progress_installed = False
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
            self._ensure_progress_handoffs()
            registered = self.store.register_new_plans()
            self._stage_progress_handoffs(registered)
            try:
                plans = self.store.active_plans()
                for plan in plans:
                    await self._reconcile_plan(plan)
                    reconcile_supervision = getattr(self.store, "reconcile_supervision", None)
                    if callable(reconcile_supervision):
                        reconcile_supervision(str(plan["plan_id"]))
                launched = None
                if not self.store.any_busy_work_order():
                    launched = await self._launch_one()
                return {"registered": registered, "launched": launched}
            finally:
                # All engineering transactions have ended, including terminal
                # transitions. Failed staging is retried from durable snapshots.
                self._stage_progress_handoffs()

    def _ensure_progress_handoffs(self) -> None:
        if self.progress_handoffs is not None and not self._progress_installed:
            try:
                self.progress_handoffs.ensure()
                self._progress_installed = True
            except Exception as exc:
                logging.getLogger(__name__).warning("Progress installation unavailable (%s)", type(exc).__name__)

    def _stage_progress_handoffs(self, plan_ids: list[str] | None = None) -> None:
        if not self._progress_installed:
            return
        try:
            candidates = plan_ids if plan_ids is not None else self.progress_handoffs.candidates()
            for plan_id in candidates:
                try:
                    self.progress_handoffs.stage_plan(plan_id)
                except Exception as exc:
                    logging.getLogger(__name__).warning("Progress staging unavailable (%s)", type(exc).__name__)
        except Exception as exc:
            logging.getLogger(__name__).warning("Progress candidates unavailable (%s)", type(exc).__name__)

    def view(self, plan_id: str) -> dict[str, Any] | None:
        orchestration = self.store.orchestration(plan_id)
        if orchestration is None:
            return None
        return {
            **dict(orchestration),
            "work_orders": [dict(row) for row in self.store.work_orders(plan_id)],
        }

    def progress(self, plan_id: str) -> dict[str, Any] | None:
        snapshot = self.store.progress_snapshot(plan_id)
        if snapshot is None:
            return None
        plan = snapshot["orchestration"]
        rows = snapshot["work_orders"]
        states = {row["work_order_id"]: row["state"] for row in rows}
        current = next((row["work_order_id"] for row in rows if row["state"] in _BUSY_WORK_ORDER_STATES), None)
        blocked = next((row for row in rows if row["state"] == "blocked"), None)
        ready = dependency_ready_work_order_ids(plan.get("plan") or {}, states)
        return {
            "plan_id": plan["plan_id"],
            "project_id": plan["project_id"],
            "ticket_id": plan["ticket_id"],
            "state": plan["status"],
            "lifecycle": plan["lifecycle"],
            "completed": sum(row["state"] == "completed" for row in rows),
            "total": len(rows),
            "current_work_order": current,
            "blocked": {"work_order_id": blocked["work_order_id"], "job_id": blocked["job_id"]} if blocked else None,
            "blocked_evidence": blocked_plan_evidence(snapshot),
            "next": ready,
            "supervision": supervision_read_model(plan.get("plan") or {}, plan),
            "last_checkpoint": (
                checkpoint_read_model(snapshot["last_checkpoint"])
                if blocked else snapshot["last_checkpoint"]
            ),
        }

    def _checkpoint_transition(
        self, tracked: dict[str, Any], *, kind: str, state: str,
        job: dict[str, Any] | None = None, pr: dict[str, Any] | None = None,
        reason: str | None = None, **fields: Any,
    ) -> dict[str, Any]:
        if job is None and tracked.get("job_id"):
            job = self.storage.get(str(tracked["job_id"]))
        evidence = checkpoint_evidence(tracked, job, pr=pr, reason=reason)
        job_id = fields.get("job_id", tracked.get("job_id"))
        return self.store.transition_work_order(
            expected=tracked, kind=kind, state=state, evidence=evidence,
            checkpoint_key=transition_key(tracked, kind, job_id, evidence, job), **fields,
        )

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
        if str(row.get("lifecycle") or "active") != "active":
            raise RuntimeError("Superseded WorkOrders do not require operator recovery")
        if row["execution_mode"] != "operator" or row["state"] != "waiting_human":
            raise RuntimeError("WorkOrder is not waiting for an operator")
        detail = dict(row.get("detail") or {})
        detail["operator_note"] = note.strip()[:2000]
        if action == "complete":
            self._checkpoint_transition(row, kind="completed", state="completed", detail=detail)
            self.store.update_plan(plan_id, status="active")
        elif action == "block":
            # Detail serves operator attention; the immutable checkpoint owns
            # the bounded block reason used by progress and parent handoff.
            detail["reason"] = "operator_blocked"
            self._checkpoint_transition(
                row, kind="blocked", state="blocked", reason=note.strip() or "operator_blocked", detail=detail,
            )
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

    async def continue_plan(
        self,
        *,
        plan_id: str,
        generation: int,
        continuation_key: str,
        checkpoint_id: int,
        checkpoint_key: str,
        ready_work_order_ids: list[str],
    ) -> dict[str, Any]:
        release = self.store.release_supervision(
            plan_id=plan_id,
            generation=generation,
            continuation_key=continuation_key,
            checkpoint_id=checkpoint_id,
            checkpoint_key=checkpoint_key,
            ready_work_order_ids=ready_work_order_ids,
        )
        if not release["changed"]:
            return {
                "plan_id": plan_id,
                "status": "released",
                "idempotent": True,
                "supervision": release["supervision"],
                "launched": None,
            }
        tick = await self.tick()
        return {
            "plan_id": plan_id,
            "status": "released",
            "idempotent": False,
            "supervision": release["supervision"],
            "launched": tick.get("launched"),
        }

    async def _reconcile_plan(self, plan: dict[str, Any]) -> None:
        plan_id = str(plan["plan_id"])
        plan_doc = dict(plan.get("plan") or {})
        definitions = {item["id"]: item for item in plan_doc.get("work_orders") or []}
        rows = [
            row for row in self.store.work_orders(plan_id)
            if str(row.get("lifecycle") or "active") == "active"
        ]

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

            if state == "blocked" and job_id:
                job = self.storage.get(str(job_id))
                if job is not None and str(job.get("status") or "") == "completed":
                    result = dict(job.get("result") or {})
                    delivery = dict(result.get("delivery") or {})
                    ci = dict(delivery.get("ci") or {})
                    pr = dict(delivery.get("pull_request") or {})
                    verified_commit = str(result.get("commit") or "").strip()
                    branch = str(job.get("branch") or "").strip()
                    pr_number = pr.get("number")
                    try:
                        normalized_pr_number = int(pr_number) if pr_number else None
                    except (TypeError, ValueError):
                        normalized_pr_number = None
                    ci_commit = str(ci.get("commit") or "").strip()
                    exact_delivery_binding = bool(
                        result.get("status") == "accepted"
                        and result.get("delivery_finalized") is True
                        and verified_commit
                        and branch
                        and normalized_pr_number
                        and str(pr.get("head") or "") == verified_commit
                        and str(pr.get("head_ref") or "") == branch
                        and (not ci_commit or ci_commit == verified_commit)
                    )
                    persisted_ci_success = bool(
                        delivery.get("state") == "ci_success"
                        and ci.get("state") == "success"
                    )
                    fresh_ci_success = False
                    if (
                        exact_delivery_binding
                        and not persisted_ci_success
                        and delivery.get("state") == "ci_none"
                        and ci.get("state") == "none"
                    ):
                        try:
                            project = project_config(str(plan["project_id"]))
                            expected_base = str(project.get("base_branch") or "main")
                            current_pr = await self.engine.ddev.github_pull_request(
                                project_id=str(plan["project_id"]),
                                pr_number=int(normalized_pr_number),
                            )
                            current_ci = await self.engine.ddev.github_ci(
                                project_id=str(plan["project_id"]),
                                commit=verified_commit,
                            )
                        except Exception:
                            current_pr = {}
                            current_ci = {}
                        fresh_ci_success = bool(
                            int(current_pr.get("number") or 0) == normalized_pr_number
                            and str(current_pr.get("state") or "") == "open"
                            and not bool(current_pr.get("merged"))
                            and str(current_pr.get("head") or "") == verified_commit
                            and str(current_pr.get("head_ref") or "") == branch
                            and str(current_pr.get("base_ref") or "") == expected_base
                            and str(current_ci.get("state") or "") == "success"
                            and str(current_ci.get("commit") or "") == verified_commit
                        )
                    exact_completed_delivery = bool(
                        exact_delivery_binding
                        and (persisted_ci_success or fresh_ci_success)
                    )
                    if exact_completed_delivery:
                        detail = dict(tracked.get("detail") or {})
                        detail.update({
                            "job_id": job_id,
                            "recovered_from_blocked": True,
                            "recovery_reason": "same_child_completed_finalized_delivery",
                            "recovery_ci_source": (
                                "persisted_delivery"
                                if persisted_ci_success
                                else "fresh_github_exact_head"
                            ),
                        })
                        self._checkpoint_transition(
                            tracked,
                            kind="recovered_accepted",
                            job=job,
                            state="awaiting_merge",
                            pr_number=int(normalized_pr_number),
                            pr_url=pr.get("url"),
                            detail=detail,
                        )
                        continue

            if state in {"running", "waiting_human"} and job_id:
                job = self.storage.get(str(job_id))
                if job is None:
                    self._block_tracked(plan, tracked, "orchestrated_job_missing")
                    continue
                job_status = str(job.get("status") or "")
                marker = orchestrator_launch(job)
                if state == "running" and job_status == "queued" and marker and marker["state"] in {"held", "ready"}:
                    if self.store.release_launch(plan_id, work_order_id, str(job_id)):
                        await self.engine.enqueue(str(job_id))
                    continue
                if job_status in _ACTIVE_JOB_STATUSES:
                    if state != "running":
                        self.store.update_work_order(plan_id, work_order_id, state="running")
                    continue
                if job_status == "waiting_human":
                    if state != "waiting_human":
                        self._checkpoint_transition(tracked, kind="waiting_human", state="waiting_human", job=job)
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
                        remove_data=True,
                    )
                    result = dict(job.get("result") or {})
                    delivery = dict(result.get("delivery") or {})
                    pr = dict(delivery.get("pull_request") or {})
                    if pr.get("number"):
                        self._checkpoint_transition(
                            tracked, kind="accepted", job=job,
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
                        self._checkpoint_transition(
                            tracked, kind="completed", job=job,
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
                        remove_data=job_status == "cancelled",
                    )
                    self._block_job(
                        plan,
                        tracked,
                        job,
                        resource_quiesce=resource_quiesce,
                    )
                    continue

            if state == "awaiting_merge":
                # A governed PM review repair may reopen the same completed job
                # after this WorkOrder entered its merge gate. Follow that
                # durable job transition instead of evaluating or merging the
                # stale delivered result. The normal running-state reconciliation
                # will handle later repair completion/failure on the next tick.
                if job_id:
                    job = self.storage.get(str(job_id))
                    if job is not None and str(job.get("status") or "") in _ACTIVE_JOB_STATUSES:
                        detail = dict(tracked.get("detail") or {})
                        detail["review_repair_reopened"] = True
                        self._checkpoint_transition(
                            tracked, kind="repair_reopened", job=job,
                            state="running",
                            detail=detail,
                        )
                        continue
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
                    self._checkpoint_transition(
                        tracked, kind="merged", pr=pr,
                        state="completed",
                        detail=detail,
                    )
                elif str(pr.get("state") or "") == "closed":
                    self._block_tracked(plan, tracked, "pull_request_closed_without_merge")

        rows = [
            row for row in self.store.work_orders(plan_id)
            if str(row.get("lifecycle") or "active") == "active"
        ]
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
        elif str(plan.get("status") or "") == "supervised_hold":
            self.store.update_plan(plan_id, status="supervised_hold")
        else:
            self.store.update_plan(plan_id, status="active")

    def _direct_project_lease_busy(self, project_id: str, candidate_job_id: str) -> bool:
        try:
            project = project_config(project_id)
        except (KeyError, ValueError):
            return False
        runtime = project.get("runtime", {}) or {}
        if str(runtime.get("workspace_mode") or "isolated_clone") != "direct":
            return False
        lookup = getattr(self.storage, "project_lease", None)
        if not callable(lookup):
            return False
        lease = lookup(project_id)
        if not lease or str(lease.get("state") or "") != "active":
            return False
        return str(lease.get("owner_job_id") or "") != candidate_job_id

    async def _launch_one(self) -> dict[str, str] | None:
        for plan in self.store.active_plans():
            if str(plan.get("status")) in {
                "blocked", "completed", "waiting_human", "supervised_hold",
            }:
                continue
            plan_doc = dict(plan.get("plan") or {})
            definitions = {item["id"]: item for item in plan_doc.get("work_orders") or []}
            tracked = [
                row for row in self.store.work_orders(str(plan["plan_id"]))
                if str(row.get("lifecycle") or "active") == "active"
            ]
            states = {row["work_order_id"]: row["state"] for row in tracked}
            ready = set(dependency_ready_work_order_ids(plan_doc, states))
            for row in tracked:
                if row["state"] != "pending":
                    continue
                definition = definitions.get(row["work_order_id"])
                if not definition:
                    self._block_tracked(plan, row, "work_order_definition_missing")
                    return None
                if row["work_order_id"] not in ready:
                    continue
                supervision_allows_launch = getattr(self.store, "supervision_allows_launch", None)
                if callable(supervision_allows_launch) and not supervision_allows_launch(
                    str(plan["plan_id"])
                ):
                    continue
                if row["execution_mode"] == "operator":
                    self._checkpoint_transition(
                        row, kind="waiting_human", reason="operator_execution_required",
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
                if self._direct_project_lease_busy(str(plan["project_id"]), job_id):
                    continue
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
                created_job_id = self.engine.create_job(
                    payload, _orchestration=(str(plan["plan_id"]), str(row["work_order_id"])),
                )
                self._checkpoint_transition(
                    row, kind="started", job=self.storage.get(created_job_id),
                    state="running",
                    job_id=created_job_id,
                    detail={"job_id": created_job_id},
                )
                self.store.update_plan(str(plan["plan_id"]), status="executing")
                if self.store.release_launch(str(plan["plan_id"]), str(row["work_order_id"]), created_job_id):
                    await self.engine.enqueue(created_job_id)
                return {"plan_id": str(plan["plan_id"]), "work_order_id": str(row["work_order_id"]), "job_id": created_job_id}
        return None

    async def _quiesce_job_workspace(
        self,
        plan: dict[str, Any],
        tracked: dict[str, Any],
        job: dict[str, Any],
        *,
        remove_data: bool = False,
    ) -> dict[str, Any]:
        workspace = str(job.get("workspace") or "").strip()
        if not workspace:
            return {"quiesced": False, "reason": "no_workspace"}
        try:
            result = await self.engine.ddev.quiesce_workspace(
                job_id=str(job["id"]),
                project_id=str(job["project_id"]),
                workspace=workspace,
                remove_data=remove_data,
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
        explicit_reason = str(result.get("reason") or "").strip()
        status = str(job.get("status") or "").strip()
        if explicit_reason:
            reason = explicit_reason
        elif status == "failed":
            # Generic worker exceptions retain their raw bounded job.error for
            # diagnostics, but orchestration/public evidence uses one stable
            # reason instead of leaking a free-form exception string into the
            # reason classifier.
            reason = "runtime_failed"
        else:
            reason = str(job.get("error") or status or "job_blocked")
        progress = dict(job.get("progress") or {})
        failures = list(progress.get("provider_failures") or [])
        quota_failure = any(
            str(item.get("kind") or "") in {"quota_exhausted", "rate_limited"}
            for item in failures
            if isinstance(item, dict)
        )
        ci_failures = int(progress.get("ci_failures", 0) or 0)
        self._checkpoint_transition(
            tracked, kind="blocked", job=job, reason=reason,
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
        self._checkpoint_transition(
            tracked, kind="blocked", reason=reason,
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
