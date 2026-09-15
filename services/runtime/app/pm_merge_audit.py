from __future__ import annotations

import json
from typing import Any

from .storage import now


PM_MERGE_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS cp_pm_merge_audit (
  id BIGSERIAL PRIMARY KEY,
  plan_id TEXT NOT NULL,
  work_order_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  expected_head TEXT NOT NULL,
  source_commit TEXT NOT NULL,
  status TEXT NOT NULL,
  decision JSONB NOT NULL,
  result JSONB,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(plan_id, work_order_id, expected_head)
);
CREATE INDEX IF NOT EXISTS cp_pm_merge_audit_lookup_idx
  ON cp_pm_merge_audit(plan_id, work_order_id, id DESC);
"""


class PMMergeAuditStore:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def ensure(self) -> None:
        with self.storage.connect() as conn:
            conn.execute(PM_MERGE_AUDIT_DDL)
            conn.commit()

    def get(self, *, plan_id: str, work_order_id: str, expected_head: str) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            return conn.execute(
                """SELECT * FROM cp_pm_merge_audit
                WHERE plan_id=%s AND work_order_id=%s AND expected_head=%s""",
                (plan_id, work_order_id, expected_head),
            ).fetchone()

    def approve(
        self,
        *,
        plan_id: str,
        work_order_id: str,
        job_id: str,
        project_id: str,
        pr_number: int,
        expected_head: str,
        source_commit: str,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        self.ensure()
        timestamp = now()
        with self.storage.connect() as conn:
            row = conn.execute(
                """INSERT INTO cp_pm_merge_audit
                (plan_id, work_order_id, job_id, project_id, pr_number, expected_head,
                 source_commit, status, decision, result, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'approved',%s::jsonb,NULL,%s,%s)
                ON CONFLICT (plan_id, work_order_id, expected_head) DO NOTHING
                RETURNING *""",
                (
                    plan_id,
                    work_order_id,
                    job_id,
                    project_id,
                    pr_number,
                    expected_head,
                    source_commit,
                    json.dumps(decision),
                    timestamp,
                    timestamp,
                ),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """SELECT * FROM cp_pm_merge_audit
                    WHERE plan_id=%s AND work_order_id=%s AND expected_head=%s""",
                    (plan_id, work_order_id, expected_head),
                ).fetchone()
            conn.commit()
        assert row is not None
        return dict(row)

    def finish(
        self,
        *,
        plan_id: str,
        work_order_id: str,
        expected_head: str,
        status: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        if status not in {"merged", "failed", "observed_merged", "uncertain"}:
            raise ValueError("Unsupported PM merge audit status")
        with self.storage.connect() as conn:
            row = conn.execute(
                """UPDATE cp_pm_merge_audit
                SET status=%s, result=%s::jsonb, updated_at=%s
                WHERE plan_id=%s AND work_order_id=%s AND expected_head=%s
                RETURNING *""",
                (
                    status,
                    json.dumps(result),
                    now(),
                    plan_id,
                    work_order_id,
                    expected_head,
                ),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("PM merge audit record disappeared")
        return dict(row)


__all__ = ["PM_MERGE_AUDIT_DDL", "PMMergeAuditStore"]
