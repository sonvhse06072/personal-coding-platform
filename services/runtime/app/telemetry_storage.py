from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from .continuity import continuity_proposal
from .storage import Storage, now
from .telemetry import (
    aggregate_calibration,
    aggregate_telemetry_summary,
    classify_attention_event,
    task_telemetry_snapshot,
)


TELEMETRY_DDL = """
CREATE TABLE IF NOT EXISTS cp_task_telemetry (
  job_id TEXT PRIMARY KEY REFERENCES cp_jobs(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  task_type TEXT NOT NULL,
  role TEXT NOT NULL,
  provider TEXT NOT NULL,
  model_id TEXT NOT NULL,
  terminal BOOLEAN NOT NULL DEFAULT FALSE,
  calibration_eligible BOOLEAN NOT NULL DEFAULT FALSE,
  outcome TEXT NOT NULL,
  snapshot JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE cp_task_telemetry
  ADD COLUMN IF NOT EXISTS calibration_eligible BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS cp_task_telemetry_lookup_idx
  ON cp_task_telemetry(project_id, task_type, role, calibration_eligible, updated_at DESC);
CREATE INDEX IF NOT EXISTS cp_task_telemetry_model_idx
  ON cp_task_telemetry(project_id, provider, model_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS cp_attention_events (
  id BIGSERIAL PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES cp_jobs(id) ON DELETE CASCADE,
  event_key TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL,
  kind TEXT NOT NULL,
  avoidable BOOLEAN NOT NULL DEFAULT FALSE,
  opened_at TIMESTAMPTZ NOT NULL,
  resolved_at TIMESTAMPTZ,
  wait_seconds DOUBLE PRECISION,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS cp_attention_events_job_idx
  ON cp_attention_events(job_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS cp_continuity_proposals (
  id BIGSERIAL PRIMARY KEY,
  dedupe_key TEXT NOT NULL UNIQUE,
  project_id TEXT NOT NULL,
  job_id TEXT,
  event_type TEXT NOT NULL,
  proposal JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS cp_continuity_proposals_project_idx
  ON cp_continuity_proposals(project_id, id DESC);
"""

_STABLE_SNAPSHOT_STATES = {"completed", "failed", "cancelled", "blocked", "waiting_human"}
_CONTINUITY_TRANSITIONS = {
    "completed": "job_terminal",
    "failed": "job_terminal",
    "cancelled": "job_terminal",
    "blocked": "job_blocked",
    "waiting_human": "governance_waiting",
}
_EXTERNAL_CONTINUITY_EVENTS = {"pr_merged", "rollout", "governance_decision"}


class TelemetryStorage(Storage):
    """Add evidence collection without changing Runtime's authoritative job state."""

    def init(self) -> None:
        super().init()
        with self.connect() as conn:
            conn.execute(TELEMETRY_DDL)
            conn.commit()

    @staticmethod
    def _minimum_sample_size() -> int:
        try:
            return max(3, min(50, int(os.getenv("TELEMETRY_MIN_SAMPLES", "5"))))
        except ValueError:
            return 5

    def update(self, job_id: str, **fields: Any) -> None:
        previous = self.get(job_id)
        super().update(job_id, **fields)
        current = self.get(job_id)
        if not previous or not current:
            return

        self._record_attention_transition(previous, current)
        self._record_budget_attention(previous, current)

        status = str(current.get("status") or "")
        if status in _STABLE_SNAPSHOT_STATES:
            snapshot = task_telemetry_snapshot(current)
            self._upsert_task_telemetry(snapshot)
        else:
            snapshot = None

        previous_status = str(previous.get("status") or "")
        if previous_status != status:
            if status in _CONTINUITY_TRANSITIONS:
                self._persist_continuity(
                    current,
                    event_type=_CONTINUITY_TRANSITIONS[status],
                    telemetry=snapshot,
                )
            elif previous_status == "waiting_human":
                self._persist_continuity(
                    current,
                    event_type="governance_resolved",
                    telemetry=snapshot or task_telemetry_snapshot(current),
                )

    def _upsert_task_telemetry(self, snapshot: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_task_telemetry
                (job_id, project_id, task_type, role, provider, model_id, terminal,
                 calibration_eligible, outcome, snapshot, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT (job_id) DO UPDATE SET
                  project_id=EXCLUDED.project_id,
                  task_type=EXCLUDED.task_type,
                  role=EXCLUDED.role,
                  provider=EXCLUDED.provider,
                  model_id=EXCLUDED.model_id,
                  terminal=EXCLUDED.terminal,
                  calibration_eligible=EXCLUDED.calibration_eligible,
                  outcome=EXCLUDED.outcome,
                  snapshot=EXCLUDED.snapshot,
                  updated_at=EXCLUDED.updated_at""",
                (
                    snapshot["job_id"],
                    snapshot["project_id"],
                    snapshot["task_type"],
                    snapshot["role"],
                    snapshot["provider"],
                    snapshot["model_id"],
                    bool(snapshot["terminal"]),
                    bool(snapshot["calibration_eligible"]),
                    snapshot["task_outcome"],
                    json.dumps(snapshot),
                    now(),
                ),
            )
            conn.commit()

    @staticmethod
    def _decision_event_key(row: dict[str, Any]) -> str:
        checkpoint = row.get("checkpoint") or {}
        pending = checkpoint.get("pending_decision") or {}
        key = str(pending.get("key") or "unknown")
        return f"decision:{row.get('id')}:{key}"

    def _record_attention_transition(self, previous: dict[str, Any], current: dict[str, Any]) -> None:
        before = str(previous.get("status") or "")
        after = str(current.get("status") or "")
        timestamp = now()
        with self.connect() as conn:
            if before != "waiting_human" and after == "waiting_human":
                event_key = self._decision_event_key(current)
                checkpoint = current.get("checkpoint") or {}
                pending = checkpoint.get("pending_decision") or {}
                classification = classify_attention_event("human_decision", current)
                conn.execute(
                    """INSERT INTO cp_attention_events
                    (job_id, event_key, category, kind, avoidable, opened_at, metadata)
                    VALUES (%s,%s,%s,'human_decision',%s,%s,%s::jsonb)
                    ON CONFLICT (event_key) DO NOTHING""",
                    (
                        current["id"],
                        event_key,
                        classification["category"],
                        bool(classification["avoidable"]),
                        timestamp,
                        json.dumps({"source": pending.get("source"), "decision": pending.get("decision") or {}}),
                    ),
                )
            elif before == "waiting_human" and after != "waiting_human":
                conn.execute(
                    """UPDATE cp_attention_events
                    SET resolved_at=%s,
                        wait_seconds=GREATEST(0, EXTRACT(EPOCH FROM (%s - opened_at)))
                    WHERE id=(
                      SELECT id FROM cp_attention_events
                      WHERE job_id=%s AND kind='human_decision' AND resolved_at IS NULL
                      ORDER BY opened_at DESC LIMIT 1
                    )""",
                    (timestamp, timestamp, current["id"]),
                )
            conn.commit()

    def _record_budget_attention(self, previous: dict[str, Any], current: dict[str, Any]) -> None:
        old_checkpoint = previous.get("checkpoint") or {}
        new_checkpoint = current.get("checkpoint") or {}
        old_items = [item for item in (old_checkpoint.get("budget_authorizations") or []) if isinstance(item, dict)]
        new_items = [item for item in (new_checkpoint.get("budget_authorizations") or []) if isinstance(item, dict)]
        known = {str(item.get("action_id") or "") for item in old_items}
        additions = [item for item in new_items if str(item.get("action_id") or "") not in known]
        if not additions:
            return

        classification = classify_attention_event("budget_extension", current)
        timestamp = now()
        opened_at = previous.get("updated_at") or timestamp
        with self.connect() as conn:
            for item in additions:
                action_id = str(item.get("action_id") or "unknown")
                event_key = f"budget:{current['id']}:{action_id}"
                conn.execute(
                    """INSERT INTO cp_attention_events
                    (job_id, event_key, category, kind, avoidable, opened_at, resolved_at, wait_seconds, metadata)
                    VALUES (%s,%s,%s,'budget_extension',%s,%s,%s,
                      GREATEST(0, EXTRACT(EPOCH FROM (%s - %s))),%s::jsonb)
                    ON CONFLICT (event_key) DO NOTHING""",
                    (
                        current["id"],
                        event_key,
                        classification["category"],
                        bool(classification["avoidable"]),
                        opened_at,
                        timestamp,
                        timestamp,
                        opened_at,
                        json.dumps(item),
                    ),
                )
            conn.commit()

    def attention_summary(self, job_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT
                  COUNT(*)::int AS human_interventions,
                  COUNT(*) FILTER (WHERE avoidable)::int AS avoidable_blocks,
                  COUNT(*) FILTER (WHERE category='decision_boundary')::int AS decision_boundary_interventions,
                  COUNT(*) FILTER (WHERE category='routine_operational')::int AS routine_operational_interventions,
                  COALESCE(SUM(wait_seconds),0)::double precision AS time_waiting_for_owner_seconds
                FROM cp_attention_events WHERE job_id=%s""",
                (job_id,),
            ).fetchone()
        return dict(row or {})

    @staticmethod
    def _telemetry_filters(
        project_id: str,
        task_type: str | None,
        role: str | None,
    ) -> tuple[str, list[Any]]:
        clauses = ["project_id=%s"]
        params: list[Any] = [project_id]
        if task_type:
            clauses.append("task_type=%s")
            params.append(task_type)
        if role:
            clauses.append("role=%s")
            params.append(role)
        return " AND ".join(clauses), params

    def aggregate_attention_summary(
        self,
        *,
        project_id: str,
        task_type: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        where, params = self._telemetry_filters(project_id, task_type, role)
        with self.connect() as conn:
            row = conn.execute(
                f"""SELECT
                  COUNT(a.id)::int AS human_interventions,
                  COUNT(a.id) FILTER (WHERE a.avoidable)::int AS avoidable_blocks,
                  COUNT(a.id) FILTER (WHERE a.category='decision_boundary')::int AS decision_boundary_interventions,
                  COUNT(a.id) FILTER (WHERE a.category='routine_operational')::int AS routine_operational_interventions,
                  COALESCE(SUM(a.wait_seconds),0)::double precision AS time_waiting_for_owner_seconds
                FROM cp_task_telemetry t
                LEFT JOIN cp_attention_events a ON a.job_id=t.job_id
                WHERE {where.replace('project_id', 't.project_id').replace('task_type', 't.task_type').replace('role', 't.role')}""",
                tuple(params),
            ).fetchone()
        value = dict(row or {})
        with self.connect() as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*)::int AS task_count FROM cp_task_telemetry WHERE {where}",
                tuple(params),
            ).fetchone()
        task_count = int((count_row or {}).get("task_count", 0) or 0)
        interventions = int(value.get("human_interventions", 0) or 0)
        avoidable = int(value.get("avoidable_blocks", 0) or 0)
        value["human_interventions_per_task"] = round(interventions / task_count, 4) if task_count else 0.0
        value["avoidable_blocks_per_task"] = round(avoidable / task_count, 4) if task_count else 0.0
        return value

    def telemetry_summary(
        self,
        *,
        project_id: str,
        task_type: str | None = None,
        role: str | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        where, params = self._telemetry_filters(project_id, task_type, role)
        params.append(max(1, min(int(limit), 2000)))
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT snapshot FROM cp_task_telemetry
                WHERE {where}
                ORDER BY updated_at DESC LIMIT %s""",
                tuple(params),
            ).fetchall()
        snapshots = [dict(row["snapshot"]) for row in rows if isinstance(row.get("snapshot"), dict)]
        result = aggregate_telemetry_summary(
            snapshots,
            attention=self.aggregate_attention_summary(
                project_id=project_id,
                task_type=task_type,
                role=role,
            ),
        )
        result.update({"project_id": project_id, "task_type": task_type, "role": role})
        return result

    def _persist_continuity(
        self,
        row: dict[str, Any],
        *,
        event_type: str,
        telemetry: dict[str, Any] | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attention = self.attention_summary(str(row["id"]))
        proposal = continuity_proposal(
            row,
            event_type=event_type,
            attention_summary=attention,
            telemetry=telemetry,
            payload=payload,
        )
        encoded = json.dumps(proposal, sort_keys=True, separators=(",", ":"), default=str)
        dedupe_key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_continuity_proposals
                (dedupe_key, project_id, job_id, event_type, proposal, created_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT (dedupe_key) DO NOTHING""",
                (dedupe_key, row["project_id"], row.get("id"), event_type, json.dumps(proposal), now()),
            )
            conn.commit()
        return proposal

    def record_external_continuity(
        self,
        *,
        project_id: str,
        event_type: str,
        payload: dict[str, Any],
        job_id: str | None = None,
    ) -> dict[str, Any]:
        if event_type not in _EXTERNAL_CONTINUITY_EVENTS:
            raise ValueError("Unsupported external continuity event")
        row = self.get(job_id) if job_id else None
        if row:
            if str(row.get("project_id") or "") != str(project_id):
                raise ValueError("Continuity event project_id does not match job project")
            return self._persist_continuity(
                row,
                event_type=event_type,
                telemetry=task_telemetry_snapshot(row),
                payload=payload,
            )
        proposal = {
            "event_type": event_type,
            "project_id": project_id,
            "job_id": job_id,
            "status": "external_event",
            "detail": dict(payload),
            "authority": {
                "mutable_target": "docs/project/current-state.md",
                "direct_durable_policy_write_allowed": False,
                "application_path": "normal_git_branch_pr_authority",
            },
        }
        encoded = json.dumps(proposal, sort_keys=True, separators=(",", ":"), default=str)
        dedupe_key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO cp_continuity_proposals
                (dedupe_key, project_id, job_id, event_type, proposal, created_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT (dedupe_key) DO NOTHING""",
                (dedupe_key, project_id, job_id, event_type, json.dumps(proposal), now()),
            )
            conn.commit()
        return proposal

    def latest_continuity_proposal(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT proposal FROM cp_continuity_proposals
                WHERE project_id=%s ORDER BY id DESC LIMIT 1""",
                (project_id,),
            ).fetchone()
        return dict(row["proposal"]) if row and isinstance(row.get("proposal"), dict) else None

    def calibration_hint(
        self,
        *,
        project_id: str,
        task_type: str,
        role: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: list[Any] = [project_id, task_type]
        role_sql = ""
        if role:
            role_sql = " AND role=%s"
            params.append(role)
        params.append(max(5, min(int(limit), 500)))
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT snapshot FROM cp_task_telemetry
                WHERE project_id=%s AND task_type=%s AND calibration_eligible=TRUE{role_sql}
                ORDER BY updated_at DESC LIMIT %s""",
                tuple(params),
            ).fetchall()
        snapshots = [dict(row["snapshot"]) for row in rows if isinstance(row.get("snapshot"), dict)]
        result = aggregate_calibration(
            snapshots,
            minimum_sample_size=self._minimum_sample_size(),
        )
        result.update({"project_id": project_id, "task_type": task_type, "role": role})
        return result


__all__ = ["TELEMETRY_DDL", "TelemetryStorage"]
