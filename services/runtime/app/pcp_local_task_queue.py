"""PARKED PCP-local GitHub source-task contract and durable idempotent receipts.

Source-only B2.1: no autonomous poll, model call, issue dispatch, project
registration, credential provision, branch creation, or merge permission.
An approved baseline, exact current GitHub main, and explicit source switch
are separate preconditions enforced by the Runtime caller.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
from typing import Any

REPOSITORY = "sonvhse06072/personal-coding-platform"
PROJECT_ID = "pcp-local"
OWNER = "sonvhse06072"
MARKER = "<!-- coding-platform:pcp-remote-source:v1 -->"
MODE = "github_source_pr_only"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
KEY_RE = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
FIELDS = {"version", "key", "base_sha", "goal", "allowed_paths", "mode"}
# A source issue cannot modify the task gate it is evaluated against.
FORBIDDEN = frozenset({
    "scripts/pcp-light-remote-intake.py",
    "tests/test_pcp_light_remote_intake.py",
})


class TaskStop(ValueError):
    """Machine-safe denial code; never serialize untrusted task content."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(ok: bool, code: str) -> None:
    if not ok:
        raise TaskStop(code)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "task_duplicate_json_key")
        result[key] = value
    return result


def _allowed_path(value: Any) -> bool:
    if (not isinstance(value, str) or not 1 <= len(value) <= 240
            or "\\" in value or "\x00" in value or value in FORBIDDEN):
        return False
    p = PurePosixPath(value)
    if p.is_absolute() or p.as_posix() != value or any(
            part in {"", ".", ".."} for part in value.split("/")):
        return False
    parts = p.parts
    if len(parts) == 2 and parts[0] == "scripts":
        return (parts[1].startswith("pcp-light-")
                and parts[1].endswith(".py")
                and len(parts[1]) > len("pcp-light-.py"))
    if len(parts) == 2 and parts[0] == "tests":
        return (parts[1].startswith("test_pcp_light_")
                and parts[1].endswith(".py")
                and len(parts[1]) > len("test_pcp_light_.py"))
    return (len(parts) >= 3 and parts[:2] == ("docs", "pcp-light")
            and parts[-1].endswith(".md") and len(parts[-1]) > 3)


@dataclass(frozen=True)
class LocalSourceTask:
    repository: str
    project_id: str
    issue_number: int
    task_key: str
    body_sha256: str
    base_sha: str
    baseline_revision: str
    baseline_source_commit: str
    goal_sha256: str
    allowed_paths: tuple[str, ...]

    def status(self, *, created: bool) -> dict[str, Any]:
        return {
            "status": "SOURCE_RECORDED_NOT_DISPATCHED",
            "repository": self.repository,
            "project_id": self.project_id,
            "issue_number": self.issue_number,
            "task_key": self.task_key,
            "body_sha256": self.body_sha256,
            "base_sha": self.base_sha,
            "baseline_revision": self.baseline_revision,
            "allowed_paths": list(self.allowed_paths),
            "new_receipt": created,
            "queue_state": "pending",
            "worker_enabled": False,
            "model_calls": 0,
            "can_publish_or_merge": False,
        }


def verify_issue(
    source: Any, *, issue_number: int, body_sha256: str,
    base_sha: str, baseline_revision: str, baseline_source_commit: str,
) -> LocalSourceTask:
    """Verify the exact *Executor-fetched* issue and pinned current main.

    Caller separately resolves the approved ProjectBaseline and compares the
    current trusted branch SHA. Validation alone never grants dispatch.
    """
    require(type(issue_number) is int and issue_number > 0,
            "issue_number_invalid")
    require(isinstance(body_sha256, str) and DIGEST_RE.fullmatch(body_sha256) is not None,
            "body_digest_invalid")
    require(isinstance(base_sha, str) and SHA_RE.fullmatch(base_sha) is not None,
            "base_sha_invalid")
    require(isinstance(baseline_source_commit, str)
            and SHA_RE.fullmatch(baseline_source_commit) is not None
            and isinstance(baseline_revision, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", baseline_revision)
            is not None, "baseline_identity_invalid")
    require(isinstance(source, dict)
            and source.get("project_id") == PROJECT_ID
            and source.get("repository") == REPOSITORY
            and type(source.get("number")) is int
            and source["number"] == issue_number
            and source.get("author") == OWNER
            and source.get("state") == "open"
            and source.get("is_pull_request") is False
            and source.get("html_url")
            == f"https://github.com/{REPOSITORY}/issues/{issue_number}"
            and source.get("main_sha") == base_sha,
            "github_identity_or_main_changed")
    body = source.get("body")
    require(isinstance(body, str) and len(body.encode("utf-8")) <= 16000
            and body.count(MARKER) == 1
            and body.lstrip().startswith(MARKER),
            "issue_body_or_marker_invalid")
    require(hashlib.sha256(body.encode("utf-8")).hexdigest() == body_sha256,
            "issue_body_digest_changed")
    try:
        task = json.loads(body.strip()[len(MARKER):].strip(),
                          object_pairs_hook=_unique)
    except TaskStop:
        raise
    except (TypeError, ValueError) as exc:
        raise TaskStop("task_json_invalid") from exc
    require(isinstance(task, dict) and set(task) == FIELDS,
            "task_schema_invalid")
    key, goal, paths = task["key"], task["goal"], task["allowed_paths"]
    require(type(task["version"]) is int and task["version"] == 1
            and task["mode"] == MODE
            and isinstance(key, str) and KEY_RE.fullmatch(key) is not None
            and not key.startswith(("g0-", "g1-", "f2-", "chonhac-"))
            and isinstance(goal, str) and 20 <= len(goal) <= 4000
            and task["base_sha"] == base_sha,
            "task_contract_or_source_invalid")
    require(isinstance(paths, list) and 2 <= len(paths) <= 4
            and all(_allowed_path(p) for p in paths)
            and len(set(paths)) == len(paths)
            and any(p.startswith("tests/test_pcp_light_")
                    and p.endswith(".py") for p in paths),
            "task_paths_invalid")
    return LocalSourceTask(
        repository=REPOSITORY, project_id=PROJECT_ID, issue_number=issue_number,
        task_key=key, body_sha256=body_sha256, base_sha=base_sha,
        baseline_revision=baseline_revision,
        baseline_source_commit=baseline_source_commit,
        goal_sha256=hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        allowed_paths=tuple(paths),
    )


# Separate from historical PM control / job tables; never rewrite consumed jobs.
RECEIPT_DDL = """
CREATE TABLE IF NOT EXISTS cp_pcp_local_source_receipts (
  repository TEXT NOT NULL,
  issue_number BIGINT NOT NULL CHECK (issue_number > 0),
  project_id TEXT NOT NULL,
  task_key TEXT NOT NULL,
  body_sha256 TEXT NOT NULL,
  base_sha TEXT NOT NULL,
  baseline_revision TEXT NOT NULL,
  baseline_source_commit TEXT NOT NULL,
  goal_sha256 TEXT NOT NULL,
  allowed_paths JSONB NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending'
    CHECK (state IN ('pending','claimed','running','delivered','blocked')),
  generation INTEGER NOT NULL DEFAULT 0,
  job_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (repository, issue_number),
  UNIQUE (project_id, task_key)
);
"""

TRANSITIONS = {
    "pending": frozenset({"claimed", "blocked"}),
    "claimed": frozenset({"running", "blocked"}),
    "running": frozenset({"delivered", "blocked"}),
    "blocked": frozenset(),
    "delivered": frozenset(),
}


def validate_transition(current: str, target: str, *,
                        worker_authorized: bool = False) -> None:
    """Internal future-worker preflight; no B2.1 route exposes this operation."""
    require(worker_authorized
            and os.getenv("PCP_LOCAL_TASK_WORKER_ENABLED", "") == "owner-approved",
            "worker_activation_not_authorized")
    require(target in TRANSITIONS.get(current, ()), "task_transition_denied")


class LocalSourceQueueStore:
    """Transactional, durable *receipt* only. Records NEVER execute a job."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def next_pending(self) -> dict[str, Any] | None:
        """One oldest PCP-local receipt, READ ONLY; no replay or table creation.

        The caller must independently check default-off flags and the approved
        ProjectBaseline BEFORE invoking this method. It never claims a job.
        """
        with self.storage.connect() as conn:
            row = conn.execute(
                """SELECT repository, issue_number, project_id, task_key,
                          body_sha256, base_sha, baseline_revision,
                          baseline_source_commit, goal_sha256, allowed_paths,
                          state, generation, job_id
                   FROM cp_pcp_local_source_receipts
                   WHERE repository=%s AND project_id=%s AND state='pending'
                   ORDER BY created_at ASC, issue_number ASC
                   LIMIT 1""",
                (REPOSITORY, PROJECT_ID),
            ).fetchone()
        if row is None:
            return None
        require(isinstance(row, dict), "pending_receipt_shape_invalid")
        require(row.get("repository") == REPOSITORY
                and row.get("project_id") == PROJECT_ID
                and row.get("state") == "pending"
                and type(row.get("issue_number")) is int
                and row["issue_number"] > 0
                and type(row.get("generation")) is int
                and row["generation"] == 0
                and row.get("job_id") is None,
                "pending_receipt_identity_invalid")
        # Fail closed on unexpected row fields rather than carrying mutable
        # internal metadata into a model/Runtime authorization decision.
        required = {
            "repository", "issue_number", "project_id", "task_key",
            "body_sha256", "base_sha", "baseline_revision",
            "baseline_source_commit", "goal_sha256", "allowed_paths",
            "state", "generation", "job_id",
        }
        require(set(row) == required, "pending_receipt_shape_invalid")
        return dict(row)

    def record(self, task: LocalSourceTask) -> bool:
        with self.storage.connect() as conn:
            conn.execute(RECEIPT_DDL)
            inserted = conn.execute(
                """INSERT INTO cp_pcp_local_source_receipts
                   (repository, issue_number, project_id, task_key,
                    body_sha256, base_sha, baseline_revision,
                    baseline_source_commit, goal_sha256, allowed_paths)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT DO NOTHING RETURNING issue_number""",
                (task.repository, task.issue_number, task.project_id,
                 task.task_key, task.body_sha256, task.base_sha,
                 task.baseline_revision, task.baseline_source_commit,
                 task.goal_sha256, json.dumps(list(task.allowed_paths))),
            ).fetchone()
            if inserted is not None:
                conn.commit()
                return True
            prior = conn.execute(
                """SELECT project_id, task_key, body_sha256, base_sha,
                          baseline_revision, baseline_source_commit,
                          goal_sha256, allowed_paths, state
                   FROM cp_pcp_local_source_receipts
                   WHERE repository=%s AND issue_number=%s FOR UPDATE""",
                (task.repository, task.issue_number),
            ).fetchone()
            require(prior is not None, "task_key_reused_or_missing")
            expected = {
                "project_id": task.project_id,
                "task_key": task.task_key,
                "body_sha256": task.body_sha256,
                "base_sha": task.base_sha,
                "baseline_revision": task.baseline_revision,
                "baseline_source_commit": task.baseline_source_commit,
                "goal_sha256": task.goal_sha256,
                "allowed_paths": list(task.allowed_paths),
            }
            require(all(prior.get(key) == value
                        for key, value in expected.items()),
                    "existing_issue_receipt_mismatch")
            require(prior.get("state") == "pending",
                    "existing_issue_already_processed")
            conn.commit()
            return False

    def advance(self, task: LocalSourceTask, *, expected_state: str,
                expected_generation: int, target_state: str,
                job_id: str | None, worker_authorized: bool = False) -> dict:
        """Parked transition primitive; never invoked by B2.1 PM Bridge."""
        validate_transition(expected_state, target_state,
                            worker_authorized=worker_authorized)
        require(type(expected_generation) is int and expected_generation >= 0,
                "task_generation_invalid")
        # A previously claimed job can never be silently replaced by a
        # different caller/job on a later transition.
        if target_state == "blocked" and job_id is None:
            pass
        else:
            require(isinstance(job_id, str)
                    and re.fullmatch(r"[a-f0-9]{32}", job_id) is not None,
                    "task_job_identity_invalid")
        with self.storage.connect() as conn:
            row = conn.execute(
                """UPDATE cp_pcp_local_source_receipts
                   SET state=%s, generation=generation+1, job_id=COALESCE(job_id,%s),
                       updated_at=NOW()
                   WHERE repository=%s AND issue_number=%s
                     AND project_id=%s AND body_sha256=%s AND base_sha=%s
                     AND baseline_revision=%s AND
                         baseline_source_commit=%s
                     AND state=%s AND generation=%s
                     AND (job_id IS NULL OR job_id=%s)
                   RETURNING state, generation, job_id""",
                (target_state, job_id, task.repository, task.issue_number,
                 task.project_id, task.body_sha256, task.base_sha,
                 task.baseline_revision, task.baseline_source_commit,
                 expected_state, expected_generation, job_id),
            ).fetchone()
            require(row is not None, "task_generation_or_identity_stale")
            conn.commit()
            return dict(row)
