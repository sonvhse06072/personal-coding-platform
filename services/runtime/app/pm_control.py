from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .schemas import RepoHints, SemanticSignals
from .storage import Storage, now


PLAN_MARKER = "<!-- coding-platform:pm-plan:v1 -->"
CONTROL_MARKER = "<!-- coding-platform:pm-control:v1 -->"

CONTROL_DDL = """
CREATE TABLE IF NOT EXISTS cp_pm_control_events (
  project_id TEXT NOT NULL,
  comment_id BIGINT NOT NULL,
  repository TEXT NOT NULL,
  issue_number INTEGER NOT NULL,
  author TEXT NOT NULL,
  comment_url TEXT,
  body_sha256 TEXT NOT NULL,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  target_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
  result JSONB,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (project_id, comment_id)
);
CREATE INDEX IF NOT EXISTS cp_pm_control_events_project_idx
  ON cp_pm_control_events(project_id, created_at DESC);
ALTER TABLE cp_pm_control_events
  ADD COLUMN IF NOT EXISTS result JSONB;
ALTER TABLE cp_pm_control_events
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
UPDATE cp_pm_control_events
  SET updated_at=created_at
  WHERE updated_at IS NULL;
ALTER TABLE cp_pm_control_events
  ALTER COLUMN updated_at SET NOT NULL;
"""


class PMControlEnvelope(BaseModel):
    """Strict non-mutating v1 GitHub control envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    project_id: str = Field(min_length=1, max_length=200)
    action: Literal[
        "request_diagnostics",
        "resolve_job_decision",
        "review_repair",
        "recheck_blocker",
        "resume_same_job",
        "merge_standalone_job",
        "continue_supervised_plan",
        "direct_intake",
    ]

    job_id: str | None = Field(default=None, min_length=8, max_length=100)
    plan_id: str | None = Field(default=None, min_length=1, max_length=200)
    generation: int | None = Field(default=None, ge=1)
    blocker_generation: str | None = Field(default=None, min_length=1, max_length=200)
    control_action_id: str | None = Field(default=None, min_length=8, max_length=200)
    recovery_action_type: Literal[
        "pm_scope_reassess",
        "resume_same",
        "retry_delivery",
        "recheck_ci",
        "recheck_orchestration",
    ] | None = None

    decision_key: str | None = Field(default=None, min_length=1, max_length=500)
    decision: Literal["approve", "reject"] | None = None
    note: str | None = Field(default=None, max_length=5000)

    expected_commit: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{40}$")
    source_commit: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{40}$")
    expected_head: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{40}$")
    branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$",
    )
    pr_number: int | None = Field(default=None, ge=1)
    base_branch: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$",
    )
    review_reference: str | None = Field(default=None, min_length=1, max_length=500)

    finding: str | None = Field(default=None, min_length=1, max_length=8000)
    references: list[str] = Field(default_factory=list, max_length=12)

    continuation_key: str | None = Field(
        default=None,
        min_length=78,
        max_length=78,
        pattern=r"^plan:continue:[0-9a-f]{64}$",
    )
    checkpoint_id: int | None = Field(default=None, ge=1)
    checkpoint_key: str | None = Field(default=None, min_length=1, max_length=500)
    ready_work_order_ids: list[str] = Field(default_factory=list, max_length=30)

    baseline_revision: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    expected_remote_main_sha: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{40}$",
    )
    intake_semantic: SemanticSignals | None = None
    intake_repo_hints: RepoHints | None = None

    diagnostic_collectors: list[
        Literal[
            "job",
            "attention",
            "collaboration",
            "plan_progress",
            "recent_activity",
            "github_delivery",
            "worktree",
            "runtime_health",
        ]
    ] = Field(default_factory=list, max_length=8)

    @field_validator("intake_semantic", "intake_repo_hints", mode="before")
    @classmethod
    def reject_unknown_intake_signal_fields(cls, value, info):
        if value is None:
            return value
        schema = (
            SemanticSignals
            if info.field_name == "intake_semantic"
            else RepoHints
        )
        if isinstance(value, dict) and set(value) - set(schema.model_fields):
            raise ValueError("Unknown remote intake structured signal fields")
        return value

    @model_validator(mode="after")
    def validate_action_identity(self) -> "PMControlEnvelope":
        def require(*fields: str) -> None:
            missing = [
                name
                for name in fields
                if getattr(self, name) in (None, "", [])
            ]
            if missing:
                raise ValueError(
                    f"{self.action} requires exact target field(s): "
                    + ", ".join(missing)
                )

        if self.action == "request_diagnostics":
            if not self.job_id and not self.plan_id:
                raise ValueError("request_diagnostics requires job_id or plan_id")
            if not self.diagnostic_collectors:
                raise ValueError(
                    "request_diagnostics requires diagnostic_collectors"
                )
        elif self.action == "resolve_job_decision":
            require("job_id", "decision_key", "decision")
        elif self.action == "review_repair":
            require("job_id", "expected_commit", "finding")
        elif self.action in {"recheck_blocker", "resume_same_job"}:
            require("job_id", "blocker_generation")
            if bool(self.control_action_id) == bool(self.recovery_action_type):
                raise ValueError(
                    f"{self.action} requires exactly one of "
                    "control_action_id or recovery_action_type"
                )
        elif self.action == "merge_standalone_job":
            require(
                "job_id",
                "source_commit",
                "expected_commit",
                "expected_head",
                "branch",
                "pr_number",
                "base_branch",
                "review_reference",
            )
        elif self.action == "continue_supervised_plan":
            require(
                "plan_id",
                "generation",
                "continuation_key",
                "checkpoint_id",
                "checkpoint_key",
                "ready_work_order_ids",
            )
        elif self.action == "direct_intake":
            require(
                "baseline_revision",
                "expected_remote_main_sha",
                "intake_semantic",
                "intake_repo_hints",
            )

        if self.ready_work_order_ids:
            if any(
                not item
                or item != item.strip()
                or len(item) > 200
                for item in self.ready_work_order_ids
            ):
                raise ValueError(
                    "ready_work_order_ids must contain exact non-empty ids <= 200 characters"
                )
            if self.ready_work_order_ids != sorted(set(self.ready_work_order_ids)):
                raise ValueError(
                    "ready_work_order_ids must be unique and sorted"
                )

        for reference in self.references:
            if not reference.strip() or len(reference) > 500:
                raise ValueError(
                    "references must contain non-empty values <= 500 characters"
                )
        return self

    def target_identity(self) -> dict[str, Any]:
        values = {
            "job_id": self.job_id,
            "plan_id": self.plan_id,
            "generation": self.generation,
            "blocker_generation": self.blocker_generation,
            "control_action_id": self.control_action_id,
            "recovery_action_type": self.recovery_action_type,
            "expected_commit": self.expected_commit,
            "source_commit": self.source_commit,
            "expected_head": self.expected_head,
            "branch": self.branch,
            "pr_number": self.pr_number,
            "base_branch": self.base_branch,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_key": self.checkpoint_key,
            "baseline_revision": self.baseline_revision,
            "expected_remote_main_sha": self.expected_remote_main_sha,
        }
        return {
            key: value
            for key, value in values.items()
            if value not in (None, "", [])
        }


def parse_pm_control_comment(body: str) -> PMControlEnvelope:
    if len(body.encode("utf-8")) > 65536:
        raise ValueError("PM control comment exceeds 64 KiB")
    if body.count(CONTROL_MARKER) != 1:
        raise ValueError(
            "PM control comment must contain exactly one versioned control marker"
        )
    if PLAN_MARKER in body:
        raise ValueError("PM comment cannot mix plan and control markers")

    payload = body.split(CONTROL_MARKER, 1)[1].strip()
    if not payload:
        raise ValueError("PM control marker must be followed by one JSON object")

    fence = chr(96) * 3
    if payload.startswith(fence):
        lines = payload.splitlines()
        if (
            len(lines) < 3
            or lines[0].strip() not in {fence, fence + "json"}
            or lines[-1].strip() != fence
        ):
            raise ValueError(
                "PM control fenced payload must contain exactly one complete JSON block"
            )
        payload = "\n".join(lines[1:-1]).strip()

    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("PM control payload must be one JSON object") from exc

    if not isinstance(raw, dict):
        raise ValueError("PM control payload must be a JSON object")

    return PMControlEnvelope.model_validate(raw)


class PMControlEventStore:
    """Durable consume-once audit for remote PM control comments."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def ensure(self) -> None:
        with self.storage.connect() as conn:
            conn.execute(CONTROL_DDL)
            conn.commit()

    def get(self, project_id: str, comment_id: int) -> dict[str, Any] | None:
        self.ensure()
        with self.storage.connect() as conn:
            return conn.execute(
                """SELECT * FROM cp_pm_control_events
                WHERE project_id=%s AND comment_id=%s""",
                (project_id, comment_id),
            ).fetchone()

    def claim(self, project_id: str, comment_id: int) -> dict[str, Any]:
        self.ensure()
        timestamp = now()
        with self.storage.connect() as conn:
            current = conn.execute(
                """SELECT * FROM cp_pm_control_events
                WHERE project_id=%s AND comment_id=%s FOR UPDATE""",
                (project_id, comment_id),
            ).fetchone()
            if current is None:
                raise RuntimeError("PM control event does not exist")
            if str(current.get("status") or "") != "accepted_pending_dispatch":
                raise RuntimeError(
                    f"PM control event is not dispatchable (status={current.get('status')})"
                )
            claimed = conn.execute(
                """UPDATE cp_pm_control_events
                SET status='dispatching', updated_at=%s
                WHERE project_id=%s AND comment_id=%s
                  AND status='accepted_pending_dispatch'
                RETURNING *""",
                (timestamp, project_id, comment_id),
            ).fetchone()
            conn.commit()
        if claimed is None:
            raise RuntimeError("PM control event could not be claimed")
        return dict(claimed)

    def finish(
        self,
        *,
        project_id: str,
        comment_id: int,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"executed", "failed", "uncertain", "unsupported_action_dispatch"}:
            raise ValueError("Unsupported PM control terminal status")
        self.ensure()
        with self.storage.connect() as conn:
            row = conn.execute(
                """UPDATE cp_pm_control_events
                SET status=%s, result=%s::jsonb, error=%s, updated_at=%s
                WHERE project_id=%s AND comment_id=%s AND status='dispatching'
                RETURNING *""",
                (
                    status,
                    json.dumps(result or {}, ensure_ascii=False, sort_keys=True),
                    error,
                    now(),
                    project_id,
                    comment_id,
                ),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("PM control event terminal transition rejected")
        return dict(row)

    def record(
        self,
        *,
        project_id: str,
        comment_id: int,
        repository: str,
        issue_number: int,
        author: str,
        comment_url: str | None,
        body_sha256: str,
        action: str,
        status: str,
        target_identity: dict[str, Any],
        error: str | None,
    ) -> None:
        self.ensure()
        with self.storage.connect() as conn:
            conn.execute(
                """INSERT INTO cp_pm_control_events
                (project_id, comment_id, repository, issue_number, author,
                 comment_url, body_sha256, action, status, target_identity,
                 result, error, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,NULL,%s,%s,%s)
                ON CONFLICT (project_id, comment_id) DO NOTHING""",
                (
                    project_id,
                    comment_id,
                    repository,
                    issue_number,
                    author,
                    comment_url,
                    body_sha256,
                    action,
                    status,
                    json.dumps(
                        target_identity,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    error,
                    now(),
                    now(),
                ),
            )
            conn.commit()
