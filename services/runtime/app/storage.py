from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row


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
  result JSONB,
  error TEXT,
  dry_run BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_jobs_status_idx ON cp_jobs(status);
"""


def now() -> datetime:
    return datetime.now(timezone.utc)


class Storage:
    def __init__(self) -> None:
        self.dsn = os.getenv("DATABASE_URL", "postgresql://db:db@db:5432/db")

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(DDL)
            conn.commit()

    def create(self, row: dict[str, Any]) -> None:
        timestamp = now()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_jobs
                (id, project_id, status, source_commit, branch, workspace, task, repo_analysis, route, progress, result, error, dry_run, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s)""",
                (
                    row["id"], row["project_id"], row.get("status", "queued"), row.get("source_commit"),
                    row.get("branch"), row.get("workspace"), json.dumps(row.get("task", {})),
                    json.dumps(row.get("repo_analysis")), json.dumps(row.get("route")), json.dumps(row.get("progress")),
                    json.dumps(row.get("result")), row.get("error"), bool(row.get("dry_run", False)), timestamp, timestamp,
                ),
            )
            conn.commit()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM cp_jobs WHERE id=%s", (job_id,)).fetchone()

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM cp_jobs ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall())

    def update(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        json_fields = {"task", "repo_analysis", "route", "progress", "result"}
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
            conn.execute(f"UPDATE cp_jobs SET {', '.join(sets)} WHERE id=%s", values)
            conn.commit()
