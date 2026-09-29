"""Separate durable publication state; never mutates plans, jobs or checkpoints."""
from __future__ import annotations

from typing import Any

from .plan_progress_handoff import handoff_key, issue_binding, render_progress, sha256


DDL = """
CREATE TABLE IF NOT EXISTS cp_plan_progress_meta (
  singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
  installed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO cp_plan_progress_meta(singleton) VALUES (TRUE) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS cp_plan_progress_handoffs (
  handoff_key TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  ticket_id TEXT,
  issue_number BIGINT NOT NULL CHECK (issue_number > 0),
  plan_id TEXT NOT NULL,
  plan_created_at TIMESTAMPTZ NOT NULL,
  desired_generation BIGINT NOT NULL DEFAULT 1,
  desired_transition_key TEXT NOT NULL,
  desired_body TEXT NOT NULL CHECK (octet_length(desired_body) <= 12160),
  desired_sha256 TEXT NOT NULL,
  comment_id BIGINT,
  published_generation BIGINT NOT NULL DEFAULT 0,
  published_sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','delivering','sent')),
  attempts BIGINT NOT NULL DEFAULT 0,
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_until TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, issue_number)
);
CREATE INDEX IF NOT EXISTS cp_plan_progress_delivery_idx
  ON cp_plan_progress_handoffs(status, available_at);
"""


class PlanProgressStore:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def ensure(self) -> None:
        with self.storage.connect() as conn:
            conn.execute(DDL)

    def candidates(self) -> list[str]:
        # Include terminal plans: a crash/staging failure after their last
        # engineering commit must be recoverable even though active_plans omits them.
        with self.storage.connect() as conn:
            return [row["plan_id"] for row in conn.execute("""
                SELECT o.plan_id FROM cp_plan_orchestrations o
                JOIN cp_execution_plans p ON p.id=o.plan_id
                CROSS JOIN cp_plan_progress_meta m
                WHERE o.lifecycle='active' AND (p.created_at >= m.installed_at OR EXISTS (
                  SELECT 1 FROM cp_plan_progress_handoffs h WHERE h.plan_id=o.plan_id))
                ORDER BY p.created_at, p.id
            """).fetchall()]

    def stage_plan(self, plan_id: str) -> bool:
        with self.storage.connect() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            plan = conn.execute("""
                SELECT o.plan_id,o.project_id,o.ticket_id,o.status,o.lifecycle,
                       p.plan,p.staffing,p.created_at AS plan_created_at,m.installed_at
                FROM cp_plan_orchestrations o JOIN cp_execution_plans p ON p.id=o.plan_id
                CROSS JOIN cp_plan_progress_meta m WHERE o.plan_id=%s AND o.lifecycle='active'
            """, (plan_id,)).fetchone()
            if plan is None:
                return False
            issue = issue_binding(plan["ticket_id"], plan.get("staffing") or {})
            if issue is None:
                return False
            key = handoff_key(plan["project_id"], issue)
            existing = conn.execute("SELECT * FROM cp_plan_progress_handoffs WHERE handoff_key=%s", (key,)).fetchone()
            if plan["plan_created_at"] < plan["installed_at"] and not (existing and existing["plan_id"] == plan_id):
                return False
            rows = list(conn.execute("""SELECT work_order_id,state,job_id FROM cp_plan_work_orders
                WHERE plan_id=%s AND lifecycle='active' ORDER BY sequence_no,work_order_id""", (plan_id,)).fetchall())
            checkpoint = conn.execute("""SELECT * FROM cp_plan_work_order_checkpoints
                WHERE plan_id=%s ORDER BY id DESC LIMIT 1""", (plan_id,)).fetchone()
            transition, body = render_progress({"orchestration": plan, "work_orders": rows, "last_checkpoint": checkpoint}, issue)
            result = conn.execute("""
                INSERT INTO cp_plan_progress_handoffs AS h
                  (handoff_key,project_id,ticket_id,issue_number,plan_id,plan_created_at,
                   desired_transition_key,desired_body,desired_sha256)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (handoff_key) DO UPDATE SET
                  ticket_id=EXCLUDED.ticket_id,plan_id=EXCLUDED.plan_id,plan_created_at=EXCLUDED.plan_created_at,
                  desired_generation=h.desired_generation+1,
                  desired_transition_key=EXCLUDED.desired_transition_key,
                  desired_body=EXCLUDED.desired_body,desired_sha256=EXCLUDED.desired_sha256,
                  status=CASE WHEN h.status='delivering' THEN 'delivering' ELSE 'pending' END,
                  available_at=now(),updated_at=now()
                WHERE (EXCLUDED.plan_created_at,EXCLUDED.plan_id) >= (h.plan_created_at,h.plan_id)
                  AND (h.desired_transition_key,h.desired_sha256)
                    IS DISTINCT FROM (EXCLUDED.desired_transition_key,EXCLUDED.desired_sha256)
            """, (key, plan["project_id"], plan["ticket_id"], issue, plan_id, plan["plan_created_at"], transition, body, sha256(body)))
            return bool(result.rowcount)

    def claim(self) -> dict[str, Any] | None:
        with self.storage.connect() as conn:
            # Recovery and claim are one transaction, with per-attempt fencing.
            conn.execute("""UPDATE cp_plan_progress_handoffs SET status='pending',lease_until=NULL
                WHERE status='delivering' AND lease_until <= now()""")
            return conn.execute("""
                WITH candidate AS (
                  SELECT handoff_key FROM cp_plan_progress_handoffs
                  WHERE status='pending' AND available_at <= now()
                  ORDER BY available_at,handoff_key FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE cp_plan_progress_handoffs h SET status='delivering',
                  lease_until=now()+interval '180 seconds',attempts=attempts+1,updated_at=now()
                FROM candidate c WHERE h.handoff_key=c.handoff_key RETURNING h.*
            """).fetchone()

    def ack(self, claim: dict[str, Any], comment_id: int) -> bool:
        if type(comment_id) is not int or comment_id <= 0:
            raise ValueError("Invalid progress comment identity")
        with self.storage.connect() as conn:
            result = conn.execute("""
                UPDATE cp_plan_progress_handoffs SET comment_id=%s,
                  published_generation=%s,published_sha256=%s,
                  status=CASE WHEN desired_generation=%s AND desired_sha256=%s
                    AND desired_body=%s THEN 'sent' ELSE 'pending' END,
                  lease_until=NULL,last_error=NULL,available_at=now(),updated_at=now()
                WHERE handoff_key=%s AND status='delivering' AND attempts=%s
            """, (comment_id, claim["desired_generation"], claim["desired_sha256"],
                  claim["desired_generation"], claim["desired_sha256"], claim["desired_body"],
                  claim["handoff_key"], claim["attempts"]))
            return bool(result.rowcount)

    def release(self, claim: dict[str, Any], error: Exception) -> bool:
        # Do not persist HTTP bodies, provider errors or secrets from exception messages.
        code = type(error).__name__[:100]
        delay = min(300, 5 * 2 ** min(claim["attempts"], 6))
        with self.storage.connect() as conn:
            result = conn.execute("""
                UPDATE cp_plan_progress_handoffs SET status='pending',lease_until=NULL,
                  last_error=%s,available_at=now()+(%s * interval '1 second'),updated_at=now()
                WHERE handoff_key=%s AND status='delivering' AND attempts=%s
            """, (code, delay, claim["handoff_key"], claim["attempts"]))
            return bool(result.rowcount)
