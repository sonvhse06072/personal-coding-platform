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

CREATE TABLE IF NOT EXISTS cp_project_leases (
  project_id TEXT PRIMARY KEY,
  owner_job_id TEXT NOT NULL REFERENCES cp_jobs(id),
  generation BIGINT NOT NULL DEFAULT 1,
  state TEXT NOT NULL DEFAULT 'active',
  acquired_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_project_leases_owner_idx
  ON cp_project_leases(owner_job_id, state);

CREATE TABLE IF NOT EXISTS cp_job_previews (
  job_id TEXT PRIMARY KEY REFERENCES cp_jobs(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT NOT NULL,
  generation INTEGER NOT NULL DEFAULT 1,
  frontend_url TEXT,
  backend_url TEXT,
  integration_note TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  stopped_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS cp_job_previews_status_idx
  ON cp_job_previews(status, updated_at);

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
_PROJECT_LEASE_TERMINAL_STATUSES = ("cancelled", "completed", "failed")


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

    def project_lease(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM cp_project_leases WHERE project_id=%s",
                (project_id,),
            ).fetchone()

    def acquire_project_lease(self, project_id: str, job_id: str) -> dict[str, Any]:
        """Atomically acquire one direct-workspace lease for an exact project/job.

        A live lease is never stolen from a non-terminal job. Exact reacquisition
        by the same job is idempotent so Runtime retries/restarts cannot create a
        second ownership generation.
        """
        timestamp = now()
        with self.connect() as conn:
            job = conn.execute(
                "SELECT id, project_id, status FROM cp_jobs WHERE id=%s FOR UPDATE",
                (job_id,),
            ).fetchone()
            if job is None:
                raise RuntimeError("Cannot acquire project lease for unknown job")
            if str(job.get("project_id") or "") != project_id:
                raise RuntimeError("Project lease job/project identity mismatch")

            lease = conn.execute(
                "SELECT * FROM cp_project_leases WHERE project_id=%s FOR UPDATE",
                (project_id,),
            ).fetchone()
            if lease is None:
                conn.execute(
                    """INSERT INTO cp_project_leases
                    (project_id, owner_job_id, generation, state, acquired_at, updated_at)
                    VALUES (%s,%s,1,'active',%s,%s)""",
                    (project_id, job_id, timestamp, timestamp),
                )
            else:
                owner_job_id = str(lease.get("owner_job_id") or "")
                state = str(lease.get("state") or "")
                if state == "active" and owner_job_id == job_id:
                    conn.commit()
                    current = dict(lease)
                    current["reused"] = True
                    return current
                if state == "active":
                    owner = conn.execute(
                        "SELECT status FROM cp_jobs WHERE id=%s",
                        (owner_job_id,),
                    ).fetchone()
                    if owner is None or str(owner.get("status") or "") not in _PROJECT_LEASE_TERMINAL_STATUSES:
                        raise RuntimeError(
                            f"Project {project_id} is leased by active job {owner_job_id}"
                        )
                generation = int(lease.get("generation") or 0) + 1
                conn.execute(
                    """UPDATE cp_project_leases
                    SET owner_job_id=%s, generation=%s, state='active',
                        acquired_at=%s, updated_at=%s
                    WHERE project_id=%s""",
                    (job_id, generation, timestamp, timestamp, project_id),
                )
            current = conn.execute(
                "SELECT * FROM cp_project_leases WHERE project_id=%s",
                (project_id,),
            ).fetchone()
            conn.commit()
            assert current is not None
            result = dict(current)
            result["reused"] = False
            return result

    def release_project_lease(self, project_id: str, job_id: str) -> bool:
        """Release only the exact job-owned lease; exact repeats are harmless."""
        timestamp = now()
        with self.connect() as conn:
            lease = conn.execute(
                "SELECT * FROM cp_project_leases WHERE project_id=%s FOR UPDATE",
                (project_id,),
            ).fetchone()
            if lease is None:
                conn.commit()
                return False
            owner_job_id = str(lease.get("owner_job_id") or "")
            state = str(lease.get("state") or "")
            if owner_job_id != job_id:
                if state == "active":
                    raise RuntimeError("Project lease is owned by a different job")
                conn.commit()
                return False
            if state != "active":
                conn.commit()
                return False
            conn.execute(
                """UPDATE cp_project_leases
                SET state='released', updated_at=%s
                WHERE project_id=%s AND owner_job_id=%s""",
                (timestamp, project_id, job_id),
            )
            conn.commit()
            return True

    def reconcile_terminal_project_leases(self) -> int:
        """Release leases only when durable owner-job state proves terminal."""
        timestamp = now()
        with self.connect() as conn:
            result = conn.execute(
                """UPDATE cp_project_leases lease
                SET state='released', updated_at=%s
                FROM cp_jobs job
                WHERE lease.owner_job_id=job.id
                  AND lease.state='active'
                  AND job.status = ANY(%s)""",
                (timestamp, list(_PROJECT_LEASE_TERMINAL_STATUSES)),
            )
            conn.commit()
            return int(result.rowcount or 0)

    def preview_state(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM cp_job_previews WHERE job_id=%s",
                (job_id,),
            ).fetchone()

    def upsert_preview_state(
        self,
        *,
        job_id: str,
        project_id: str,
        target: str,
        status: str,
        generation: int,
        frontend_url: str | None = None,
        backend_url: str | None = None,
        integration_note: str | None = None,
        error: str | None = None,
        stopped: bool = False,
    ) -> dict[str, Any]:
        timestamp = now()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_job_previews
                (job_id, project_id, target, status, generation,
                 frontend_url, backend_url, integration_note, error,
                 created_at, updated_at, stopped_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (job_id) DO UPDATE SET
                  project_id=EXCLUDED.project_id,
                  target=EXCLUDED.target,
                  status=EXCLUDED.status,
                  generation=EXCLUDED.generation,
                  frontend_url=EXCLUDED.frontend_url,
                  backend_url=EXCLUDED.backend_url,
                  integration_note=EXCLUDED.integration_note,
                  error=EXCLUDED.error,
                  updated_at=EXCLUDED.updated_at,
                  stopped_at=EXCLUDED.stopped_at""",
                (
                    job_id,
                    project_id,
                    target,
                    status,
                    max(1, int(generation)),
                    frontend_url,
                    backend_url,
                    integration_note,
                    error[-2000:] if error else None,
                    timestamp,
                    timestamp,
                    timestamp if stopped else None,
                ),
            )
            row = conn.execute(
                "SELECT * FROM cp_job_previews WHERE job_id=%s",
                (job_id,),
            ).fetchone()
            conn.commit()
            assert row is not None
            return row

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
