from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .activity import job_registered_event, route_selected_event, status_transition_event
from .developer_stream import bind_developer_sink, runtime_activity_event


DDL = """
CREATE TABLE IF NOT EXISTS cp_jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  source_commit TEXT,
  branch TEXT,
  workspace TEXT,
  task JSONB NOT NULL,
  repo_analysis JSONB,
  route JSONB,
  progress JSONB,
  checkpoint JSONB,
  result JSONB,
  error TEXT,
  dry_run BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE cp_jobs ADD COLUMN IF NOT EXISTS checkpoint JSONB;
CREATE INDEX IF NOT EXISTS cp_jobs_status_idx ON cp_jobs(status);

CREATE TABLE IF NOT EXISTS cp_job_events (
  id BIGSERIAL PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES cp_jobs(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  phase TEXT NOT NULL,
  level TEXT NOT NULL,
  message TEXT NOT NULL,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_job_events_job_id_idx
  ON cp_job_events(job_id, id DESC);

CREATE TABLE IF NOT EXISTS cp_execution_plans (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL,
  baseline_revision TEXT NOT NULL,
  baseline_source_commit TEXT NOT NULL,
  ticket JSONB NOT NULL,
  staffing JSONB,
  plan JSONB,
  usage JSONB,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_execution_plans_project_idx
  ON cp_execution_plans(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS cp_execution_plans_status_idx
  ON cp_execution_plans(status);
"""

_ACTIVITY_STATUSES = {"routing", "planning", "executing", "verifying", "evaluating", "delivering"}
_INACTIVE_ENGINEERING_STATUSES = ("blocked", "cancelled", "completed", "failed")


def now() -> datetime:
    return datetime.now(timezone.utc)


def _insert_job_event(conn: Any, job_id: str, event: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO cp_job_events
        (job_id, event_type, phase, level, message, data, created_at)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)""",
        (
            job_id,
            event["event_type"],
            event["phase"],
            event["level"],
            event["message"],
            json.dumps(event.get("data") or {}),
            now(),
        ),
    )


class Storage:
    def __init__(self) -> None:
        self.dsn = os.getenv("DATABASE_URL", "postgresql://db:db@db:5432/db")

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(DDL)
            conn.execute(
                """UPDATE cp_execution_plans
                SET status='interrupted',
                    error='Runtime restarted during PM planning; submit a new planning request.',
                    updated_at=%s
                WHERE status='planning'""",
                (now(),),
            )
            conn.commit()

    def create(self, row: dict[str, Any]) -> None:
        timestamp = now()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_jobs
                (id, project_id, status, source_commit, branch, workspace, task, repo_analysis, route, progress, checkpoint, result, error, dry_run, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s)""",
                (
                    row["id"], row["project_id"], row.get("status", "queued"), row.get("source_commit"),
                    row.get("branch"), row.get("workspace"), json.dumps(row.get("task", {})),
                    json.dumps(row.get("repo_analysis")), json.dumps(row.get("route")), json.dumps(row.get("progress")),
                    json.dumps(row.get("checkpoint")), json.dumps(row.get("result")), row.get("error"),
                    bool(row.get("dry_run", False)), timestamp, timestamp,
                ),
            )
            _insert_job_event(conn, row["id"], job_registered_event())
            conn.commit()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM cp_jobs WHERE id=%s", (job_id,)).fetchone()

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM cp_jobs ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall())

    def count_active_engineering_jobs(self) -> int:
        """Count all jobs that make destructive operator maintenance unsafe."""
        with self.connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS active_engineering_jobs
                FROM cp_jobs
                WHERE status IS NULL OR status NOT IN (%s, %s, %s, %s)""",
                _INACTIVE_ENGINEERING_STATUSES,
            ).fetchone()
        if row is None:
            raise RuntimeError("Active engineering job count query returned no result")
        return int(row["active_engineering_jobs"])

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        """Append one already-sanitized observability event for a durable job."""
        with self.connect() as conn:
            _insert_job_event(conn, job_id, event)
            conn.commit()

    def events_after(self, job_id: str, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 200))
        cursor = max(0, int(after_id))
        with self.connect() as conn:
            return list(
                conn.execute(
                    """SELECT id, job_id, event_type, phase, level, message, data, created_at
                    FROM cp_job_events
                    WHERE job_id=%s AND id>%s
                    ORDER BY id ASC
                    LIMIT %s""",
                    (job_id, cursor, bounded),
                ).fetchall()
            )

    def update(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        json_fields = {"task", "repo_analysis", "route", "progress", "checkpoint", "result"}
        sets: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key in json_fields:
                sets.append(f"{key}=%s::jsonb")
                values.append(json.dumps(value) if value is not None else None)
            else:
                sets.append(f"{key}=%s")
                values.append(value)
        sets.append("updated_at=%s")
        values.append(now())
        values.append(job_id)
        with self.connect() as conn:
            previous = conn.execute(
                "SELECT status, route, workspace FROM cp_jobs WHERE id=%s FOR UPDATE",
                (job_id,),
            ).fetchone()
            conn.execute(f"UPDATE cp_jobs SET {', '.join(sets)} WHERE id=%s", values)
            if previous:
                if "route" in fields and fields["route"] != previous.get("route"):
                    route_event = route_selected_event(fields["route"])
                    if route_event:
                        _insert_job_event(conn, job_id, route_event)
                if "status" in fields:
                    transition_event = status_transition_event(previous.get("status"), fields["status"])
                    if transition_event:
                        _insert_job_event(conn, job_id, transition_event)
                    if str(fields["status"]) == "blocked":
                        result = fields.get("result") if isinstance(fields.get("result"), dict) else {}
                        reason = str(result.get("reason") or "work_order_blocked")
                        workspace = Path(str(previous.get("workspace") or "."))
                        _insert_job_event(
                            conn,
                            job_id,
                            runtime_activity_event(
                                kind="block",
                                message=f"Runtime blocked: {reason}",
                                phase="blocked",
                                level="error",
                                status=reason,
                                workspace=workspace,
                            ),
                        )
            conn.commit()
        if "status" in fields:
            if str(fields["status"]) in _ACTIVITY_STATUSES:
                bind_developer_sink(lambda event, bound_job_id=job_id: self.append_event(bound_job_id, event))
            else:
                bind_developer_sink(None)

    def recent_events(self, job_ids: list[str], per_job_limit: int = 40) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(str(job_id) for job_id in job_ids if job_id))
        if not ids:
            return []
        limit = max(1, min(int(per_job_limit), 100))
        with self.connect() as conn:
            return list(
                conn.execute(
                    """SELECT id, job_id, event_type, phase, level, message, data, created_at
                    FROM (
                      SELECT id, job_id, event_type, phase, level, message, data, created_at,
                             ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY id DESC) AS event_rank
                      FROM cp_job_events
                      WHERE job_id = ANY(%s)
                    ) recent
                    WHERE event_rank <= %s
                    ORDER BY job_id, id""",
                    (ids, limit),
                ).fetchall()
            )

    def create_execution_plan(self, row: dict[str, Any]) -> None:
        timestamp = now()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_execution_plans
                (id, project_id, status, baseline_revision, baseline_source_commit,
                 ticket, staffing, plan, usage, error, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s)""",
                (
                    row["id"],
                    row["project_id"],
                    row.get("status", "planning"),
                    row["baseline_revision"],
                    row["baseline_source_commit"],
                    json.dumps(row["ticket"]),
                    json.dumps(row.get("staffing")),
                    json.dumps(row.get("plan")),
                    json.dumps(row.get("usage")),
                    row.get("error"),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()

    def get_execution_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM cp_execution_plans WHERE id=%s",
                (plan_id,),
            ).fetchone()

    def update_execution_plan(self, plan_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = {"status", "staffing", "plan", "usage", "error"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported execution-plan fields: {sorted(unknown)}")

        json_fields = {"staffing", "plan", "usage"}
        sets: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key in json_fields:
                sets.append(f"{key}=%s::jsonb")
                values.append(json.dumps(value) if value is not None else None)
            else:
                sets.append(f"{key}=%s")
                values.append(value)
        sets.append("updated_at=%s")
        values.append(now())
        values.append(plan_id)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE cp_execution_plans SET {', '.join(sets)} WHERE id=%s",
                values,
            )
            conn.commit()

    def recover_execution_plans(self) -> int:
        """Fail closed after restart instead of replaying an uncertain PM model turn."""

        timestamp = now()
        with self.connect() as conn:
            result = conn.execute(
                """UPDATE cp_execution_plans
                SET status='interrupted',
                    error='Runtime restarted during PM planning; submit a new planning request.',
                    updated_at=%s
                WHERE status='planning'""",
                (timestamp,),
            )
            conn.commit()
            return int(result.rowcount or 0)
