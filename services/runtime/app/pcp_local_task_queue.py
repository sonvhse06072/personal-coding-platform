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
    return _verify_issue(source, issue_number=issue_number, body_sha256=body_sha256,
        base_sha=base_sha, baseline_revision=baseline_revision,
        baseline_source_commit=baseline_source_commit, expected_main=base_sha)


def _verify_issue(source, *, issue_number, body_sha256, base_sha,
                  baseline_revision, baseline_source_commit, expected_main):
    """Shared parser. Public fresh admission always pins expected_main to base."""
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
            and source.get("main_sha") == expected_main,
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

    def read_claimed(self, task: LocalSourceTask, *, job_id: str) -> dict[str, Any]:
        """Re-read the *same* claimed job after CAS; no write/repair/retry.

        A successful first claim is not enough to launch a future worker:
        state, generation, job binding and every immutable task fingerprint
        must still match on a new database connection.
        """
        require(isinstance(task, LocalSourceTask)
                and task.repository == REPOSITORY
                and task.project_id == PROJECT_ID
                and isinstance(job_id, str)
                and re.fullmatch(r"[a-f0-9]{32}", job_id) is not None,
                "pcp_local_claim_lookup_invalid")
        with self.storage.connect() as conn:
            row = conn.execute(
                """SELECT repository, issue_number, project_id, task_key,
                          body_sha256, base_sha, baseline_revision,
                          baseline_source_commit, goal_sha256, allowed_paths,
                          state, generation, job_id
                   FROM cp_pcp_local_source_receipts
                   WHERE repository=%s AND project_id=%s AND issue_number=%s
                   LIMIT 1""",
                (REPOSITORY, PROJECT_ID, task.issue_number),
            ).fetchone()
        expected = {
            "repository": task.repository,
            "issue_number": task.issue_number,
            "project_id": task.project_id,
            "task_key": task.task_key,
            "body_sha256": task.body_sha256,
            "base_sha": task.base_sha,
            "baseline_revision": task.baseline_revision,
            "baseline_source_commit": task.baseline_source_commit,
            "goal_sha256": task.goal_sha256,
            "allowed_paths": list(task.allowed_paths),
            "state": "claimed",
            "generation": 1,
            "job_id": job_id,
        }
        require(type(row) is dict
                and set(row) == set(expected)
                and all(type(row[key]) is type(value) and row[key] == value
                        for key, value in expected.items()),
                "pcp_local_claim_receipt_identity_changed")
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
            from .pcp_local_recovery import project_lock
            project_lock(conn)
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


# Private claimed-only recovery; original activation remains immutable evidence.
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time


PERMIT = Path('/config/pcp-local-claim-recovery.json')
ORIGINAL = Path('/config/pcp-local-original-activation.json')
KEY = 'pcp_local_claim_recovery'
FLAG = 'PCP_LOCAL_CLAIM_RECOVERY_ENABLED'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def enabled():
    return os.getenv(FLAG, '') == 'owner-approved'


def private_bytes(path):
    require(path.is_file() and not path.is_symlink(), 'claim_recovery_private_file_missing')
    info = path.stat()
    require(info.st_uid in (0, os.getuid()) and info.st_mode & 0o077 == 0,
            'claim_recovery_private_file_permissions')
    data = path.read_bytes()
    require(len(data) <= 128000, 'claim_recovery_private_file_size')
    return data


class RecoveryPermit:
    """Concrete trusted configuration; no constructor from a request dictionary."""
    def __init__(self):
        require(enabled(), 'claim_recovery_disabled')
        raw, original = private_bytes(PERMIT), private_bytes(ORIGINAL)
        self.value = json.loads(raw, object_pairs_hook=_unique)
        self.original = json.loads(original, object_pairs_hook=_unique)
        p, a = self.value, self.original
        require(set(p) == {'version', 'decision_id', 'execution_record', 'not_before', 'expires_at',
            'receipt_before', 'original_activation_sha256', 'original_activation_digest',
            'repair_source', 'repair_commits', 'repair_paths', 'roles'}, 'claim_recovery_permit_shape')
        require(type(p['version']) is int and p['version'] == 1
            and re.fullmatch(r'[A-Za-z0-9._-]{8,100}', p['decision_id']) is not None
            and p['execution_record'].startswith('https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-')
            and p['original_activation_sha256'] == hashlib.sha256(original).hexdigest()
            and p['original_activation_digest'] == digest(a), 'claim_recovery_original_activation_changed')
        before = p['receipt_before']
        fields = set(LocalSourceTask.__dataclass_fields__)
        require(type(before) is dict and set(before) == fields | {
            'state', 'generation', 'job_id', 'created_at', 'updated_at'}, 'claim_recovery_receipt_shape')
        self.task = LocalSourceTask(**{k: tuple(before[k]) if k == 'allowed_paths' else before[k] for k in fields})
        from .pcp_local_worker_loop import claimed_source_receipt
        require({k: v for k, v in before.items() if k not in ('created_at', 'updated_at')}
            == claimed_source_receipt(self.task) and type(before['generation']) is int
            and self.task.project_id == 'pcp-local'
            and self.task.repository == 'sonvhse06072/personal-coding-platform'
            and self.task.base_sha == self.task.baseline_source_commit
            and all(a.get(k) == before[k] for k in ('issue_number', 'body_sha256', 'base_sha',
                'baseline_revision', 'baseline_source_commit')),
            'claim_recovery_original_identity_changed')
        require(re.fullmatch('[0-9a-f]{40}', p['repair_source']) is not None
            and p['repair_source'] != self.task.base_sha
            and type(p['repair_commits']) is list and p['repair_commits']
            and p['repair_commits'][-1] == p['repair_source']
            and all(re.fullmatch('[0-9a-f]{40}', x) for x in p['repair_commits'])
            and len(set(p['repair_commits'])) == len(p['repair_commits'])
            and type(p['repair_paths']) is list and p['repair_paths']
            and p['repair_paths'] == sorted(set(p['repair_paths']))
            and not set(p['repair_paths']).intersection(self.task.allowed_paths),
            'claim_recovery_repair_range_invalid')
        require(type(p['roles']) is dict and set(p['roles']) == {'runtime', 'executor', 'router', 'verifier'},
            'claim_recovery_roles_invalid')
        for role, binding in p['roles'].items():
            expected = {'image_id', 'source_commit'} | (set() if role == 'verifier' else {'configuration_sha256'})
            require(type(binding) is dict and set(binding) == expected
                and re.fullmatch('sha256:[0-9a-f]{64}', binding['image_id']) is not None
                and binding['source_commit'] == (p['repair_source'] if role in ('runtime', 'executor') else self.task.base_sha)
                and (role == 'verifier' or re.fullmatch('[0-9a-f]{64}', binding['configuration_sha256']) is not None),
                'claim_recovery_roles_invalid')
        require(p['roles']['verifier']['image_id'] == a['verification_image'] == a['runtime_image_id'],
                'claim_recovery_original_verifier_changed')
        self.sha256 = digest(p)
        self.activation = {**a, 'claim_recovery': deepcopy(p)}
        self.require_fresh()

    def require_fresh(self):
        p = self.value
        require(enabled() and all(type(p[k]) in (int, float) for k in ('not_before', 'expires_at'))
            and p['not_before'] <= time.time() < p['expires_at']
            and 0 < p['expires_at'] - p['not_before'] <= 86400,
            'claim_recovery_permit_expired')
        require(digest(self.value) == self.sha256
            and digest(json.loads(private_bytes(PERMIT), object_pairs_hook=_unique)) == self.sha256
            and hashlib.sha256(private_bytes(ORIGINAL)).hexdigest() == p['original_activation_sha256'],
            'claim_recovery_permit_revoked')

    def require_task(self, task, main):
        self.require_fresh()
        require(task == self.task and main == self.value['repair_source'], 'claim_recovery_source_changed')

    def verify_issue(self, source):
        from .pcp_local_task_queue import _verify_issue
        self.require_fresh()
        # Explicit expected CURRENT main R; immutable task/base still S.
        task = _verify_issue(source, expected_main=self.value['repair_source'], **{
            k: getattr(self.task, k) for k in ('issue_number', 'body_sha256', 'base_sha',
                'baseline_revision', 'baseline_source_commit')})
        self.require_task(task, source['main_sha'])
        return task

    def audit(self):
        return {'permit_sha256': self.sha256, 'decision': deepcopy(self.value)}


def receipt(conn, permit, *, lock=False):
    return conn.execute('SELECT to_jsonb(r) AS value FROM cp_pcp_local_source_receipts r '
        'WHERE repository=%s AND project_id=%s AND issue_number=%s' + (' FOR UPDATE' if lock else ''),
        (permit.task.repository, permit.task.project_id, permit.task.issue_number)).fetchone()


def classify(conn, permit):
    """Full preimage for retryable queued state. Advanced states are observe-only."""
    from .pcp_local_worker_loop import exact_value, stable_job_id
    r = receipt(conn, permit)
    row = conn.execute('SELECT to_jsonb(j) AS value FROM cp_jobs j WHERE id=%s',
                       (stable_job_id(permit.task),)).fetchone()
    before = permit.value['receipt_before']
    if row is None:
        require(r is not None and exact_value(r['value'], before), 'claim_recovery_receipt_preimage_drift')
        return 'unregistered', None
    job = row['value']
    cp = job.get('checkpoint') or {}
    audit = cp.get(KEY)
    require(type(audit) is dict and audit.get('authorization') == permit.audit(),
            'claim_recovery_conflicting_job_or_decision')
    initial = audit['registered_preimage']
    current = deepcopy(job)
    del current['checkpoint'][KEY]
    require(initial['id'] == stable_job_id(permit.task)
        and initial['source_commit'] == permit.task.base_sha
        and all(current[k] == initial[k] for k in ('id','project_id','source_commit','dry_run','created_at','task'))
        and current['checkpoint']['pcp_local_source'] == initial['checkpoint']['pcp_local_source']
        and current['checkpoint']['project_baseline'] == initial['checkpoint']['project_baseline'],
        'claim_recovery_job_identity_drift')
    if r is not None and exact_value(r['value'], before):
        require(exact_value(current, initial), 'claim_recovery_registered_preimage_drift')
        return 'registered_not_started', job
    require(r is not None and all(exact_value(r['value'].get(k), v)
        for k, v in before.items() if k not in ('state', 'generation', 'updated_at')),
        'claim_recovery_receipt_identity_drift')
    require((r['value']['state'], r['value']['generation']) in {
        ('running', 2), ('delivered', 3), ('blocked', 3)}, 'claim_recovery_receipt_transition_drift')
    execution = cp.get('pcp_local_execution') or {}
    state = ('terminal_observe_only' if job['status'] in ('completed', 'failed', 'cancelled')
        else 'verified_delivery_only' if execution.get('state') in ('verified', 'verified_uncommitted', 'commit_uncertain')
        else 'execution_fenced_no_replay')
    return state, job


def require_quiescent(conn, permit, *, lock=False):
    from .pcp_local_recovery import blocking_receipts
    suffix = ' FOR UPDATE' if lock else ''
    writers = conn.execute("SELECT id FROM cp_jobs WHERE project_id='pcp-local' AND id<>%s "
        "AND (status IS NULL OR status NOT IN ('completed','failed','cancelled'))"+suffix,
        (permit.value['receipt_before']['job_id'],)).fetchall()
    claims = conn.execute("SELECT * FROM cp_pcp_local_source_receipts WHERE project_id='pcp-local' "
        "AND issue_number<>%s AND (state IS NULL OR state NOT IN ('pending','delivered') "
        "OR (state='pending' AND (generation<>0 OR job_id IS NOT NULL)) "
        "OR (state='delivered' AND job_id IS NULL))"+suffix,
        (permit.task.issue_number,)).fetchall()
    lease = conn.execute("SELECT * FROM cp_project_leases WHERE project_id='pcp-local'"+suffix).fetchone()
    require(not writers and not blocking_receipts(conn, claims, lock=lock) and lease is None,
            'claim_recovery_ownership_changed')


def plan(storage, permit):
    require(type(permit) is RecoveryPermit, 'claim_recovery_private_permit_required')
    permit.require_fresh()
    with storage.connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        state, job = classify(conn, permit)
        if state in ('unregistered', 'registered_not_started'):
            require_quiescent(conn, permit)
    return {'state': state, 'job_id': permit.value['receipt_before']['job_id'],
        'permit_sha256': permit.sha256, 'task_source': permit.task.base_sha,
        'repair_source': permit.value['repair_source'], 'model_invocations': 0,
        'can_register': state == 'unregistered', 'can_execute': state == 'registered_not_started'}


async def prepare(engine):
    from .pcp_local_worker_loop import TrustedReaders, RuntimeTaskAttestor, RuntimeTaskLauncher
    from .pcp_local_task_queue import LocalSourceQueueStore, MARKER
    from .pm_bridge import PMBridgeGitHubClient
    permit = RecoveryPermit()
    readers = TrustedReaders(engine, PMBridgeGitHubClient())
    from .pcp_local_readiness import collect_readiness
    readiness = await collect_readiness(engine, readers)
    require(readiness['ready'], 'claim_recovery_readiness_blocked')
    task, issue = await readers.source()
    require(readers.recovery.sha256 == permit.sha256, 'claim_recovery_permit_revoked')
    attestor = RuntimeTaskAttestor(issue_number=task.issue_number, readers=readers.readers())
    launcher = RuntimeTaskLauncher(engine=engine, attestor=attestor, github=readers.github,
                                  receipts=LocalSourceQueueStore(engine.storage))
    launcher.recovery = permit
    launcher.task, launcher.attempted = task, True
    await launcher._recheck(task)
    launcher.source_binding = attestor.binding(task)
    goal = json.loads(issue['body'].strip()[len(MARKER):].strip())['goal']
    return permit, readers, launcher, goal


async def register(engine):
    """Commit once, return durable reconciliation. Never enqueue, lease or model."""
    permit = RecoveryPermit()
    before = plan(engine.storage, permit)
    if before['state'] != 'unregistered':
        return before
    permit, readers, launcher, goal = await prepare(engine)
    require(not list(engine.workspace_root.iterdir()), 'claim_recovery_workspace_exists')
    remote = await readers.executor('/v1/pcp-local/claim-recovery-preflight', {})
    require(remote == {'permit_sha256': permit.sha256, 'side_effects': 'absent'},
            'claim_recovery_remote_side_effects')
    engine.create_job({'_job_id': permit.value['receipt_before']['job_id'], 'project_id': 'pcp-local',
        'source_commit': permit.task.base_sha, 'baseline_revision': permit.task.baseline_revision,
        'task': {'title': f'PCP-local issue #{permit.task.issue_number}', 'description': goal,
                 'task_type': 'implementation'}}, _pcp_local_registration=launcher)
    return plan(engine.storage, permit)


async def execute(engine):
    # Share publication/PM-operation serialization with the normal worker path.
    async with engine.project_operation_lock('pcp-local'):
        return await _execute_locked(engine)


async def _execute_locked(engine):
    """One queue hydration under a cross-process lock; receipt CAS fences models.

    On an uncertain running transition, return observe-only; NEVER reset/replay.
    A lost registration/queue acknowledgement can safely retry this explicit step.
    """
    from .pcp_local_worker_loop import run_admitted_job, TrustedReaders
    from .pm_bridge import PMBridgeGitHubClient
    permit = RecoveryPermit()
    with engine.storage.connect() as conn:
        held = conn.execute('SELECT pg_try_advisory_lock(%s,%s) AS held', (5260112, 831)).fetchone()['held']
        require(held, 'claim_recovery_execution_busy')
        try:
            result = plan(engine.storage, permit)
            if result['state'] != 'registered_not_started':
                return result
            readers = TrustedReaders(engine, PMBridgeGitHubClient())
            from .pcp_local_readiness import collect_readiness
            readiness = await collect_readiness(engine, readers)
            require(readiness['ready'], 'claim_recovery_readiness_blocked')
            task, _ = await readers.source()
            await readers.refresh(task)
            require(not list(engine.workspace_root.iterdir()), 'claim_recovery_workspace_exists')
            remote = await readers.executor('/v1/pcp-local/claim-recovery-preflight', {})
            require(remote == {'permit_sha256': permit.sha256, 'side_effects': 'absent'},
                    'claim_recovery_remote_side_effects')
            require(plan(engine.storage, permit)['state'] == 'registered_not_started', 'claim_recovery_state_changed')
            if engine.queue.empty():
                await engine.enqueue(result['job_id'])
            row = await run_admitted_job(engine, readers, task)
            return {'state': row['status'], 'job_id': row['id'], 'can_merge': False}
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s,%s)', (5260112, 831))


def fence(storage, permit):
    """Full-row CAS before the existing execution path may acquire its lease."""
    from .pcp_local_recovery import blocking_receipts
    permit.require_fresh()
    with storage.connect() as conn:
        conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute('SELECT pg_advisory_xact_lock(%s,%s)', (5260112, 808))
        receipt(conn, permit, lock=True)
        conn.execute('SELECT id FROM cp_jobs WHERE id=%s FOR UPDATE',
                     (permit.value['receipt_before']['job_id'],)).fetchone()
        state, _ = classify(conn, permit)
        require(state == 'registered_not_started', 'claim_recovery_execution_already_fenced')
        require_quiescent(conn, permit, lock=True)
        permit.require_fresh()
        conn.execute("UPDATE cp_pcp_local_source_receipts SET state='running',generation=2,updated_at=NOW() "
            'WHERE repository=%s AND issue_number=%s', (permit.task.repository, permit.task.issue_number))
        conn.commit()


def session_request(path, payload=None):
    import urllib.request
    token = os.environ.get('RUNTIME_API_TOKEN')
    if not token:
        raise ValueError('authentication_unavailable')
    req = urllib.request.Request('http://127.0.0.1:8787/v1/pcp-local/' + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=300) as response:
        value = json.load(response)
        if not isinstance(value, dict):
            raise ValueError("invalid_response")
        return value


def session_main(argv=None):
    import argparse
    from http.client import HTTPException
    import urllib.parse
    parser = argparse.ArgumentParser(description='PCP local status, readiness and PM finalization; default read-only.')
    parser.add_argument('action', nargs='?', default='status', choices=('status','readiness','finalize','verify-held','review-repair'))
    parser.add_argument('--apply', action='store_true', help='Only verify-held: one authorized non-model attempt')
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--phase', default='admission', choices=('admission','status','delivery','finalization','held-verification','review-repair'))
    parser.add_argument('--review-id', type=int)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    import re
    if not re.fullmatch('[0-9a-f]{32}', args.job_id):
        parser.error('--job-id must be an exact job identity')
    if args.apply and args.action not in ('verify-held','review-repair'):
        parser.error('--apply is only valid for verify-held or review-repair')
    if args.action in ('verify-held','review-repair'):
        endpoint='review-repair' if args.action=='review-repair' else 'held-verification'
        report=dict(action=args.action,job_id=args.job_id,mutation_requests=0,outcome='unobserved')
        try:
            observed=session_request(endpoint)
            require(observed.get('job_id')==args.job_id,'held_operator_identity')
            report.update(observation=observed,outcome='observed')
            if args.apply and observed.get('ready') is True:
                report['mutation_requests']=1
                try:
                    session_request(endpoint,{k:observed[k] for k in (('job_id','permit_sha256','expected_head','pr_number','patch_sha256') if args.action=='review-repair' else ('job_id','permit_sha256'))})
                except (OSError,ValueError,HTTPException,KeyError,TypeError):
                    pass
                report['after']=session_request(endpoint)
                require(report['after'].get('job_id')==args.job_id
                    and report['after'].get('permit_sha256')==observed['permit_sha256'],
                    'held_reconciliation_identity_changed')
                if args.action=='review-repair':
                    require(all(report['after'].get(k)==observed[k] for k in ('expected_head','pr_number','patch_sha256')),
                            'local_repair_reconciliation_identity_changed')
                report['outcome']='reconciled'
        except (OSError,ValueError,HTTPException,KeyError,TypeError):
            report['outcome']='reconcile_before_retry'
        print(json.dumps(report,sort_keys=True))
        return 0 if report['outcome'] in {'observed','reconciled'} else 2
    phase = 'status' if args.action == 'status' else 'finalization' if args.action == 'finalize' else args.phase
    query = urllib.parse.urlencode({k:v for k,v in dict(phase=phase, job_id=args.job_id, review_id=args.review_id).items() if v is not None})
    report = dict(action=args.action, job_id=args.job_id, outcome='blocked', mutation_requests=0)
    try:
        observed = session_request('readiness?' + query)
        report['observation'] = observed
        if args.action != 'finalize':
            report['outcome'] = 'observed' if observed['ready'] else 'blocked'
        elif (observed.get('existing_success') and observed.get('ready') is True
                and observed.get('job', {}).get('id') == args.job_id
                and observed['job'].get('review_id') == args.review_id):
            report['outcome'] = 'already_completed'
        elif observed['ready'] is True and observed.get('job', {}).get('id') == args.job_id:
            from .fullpath_pm_review import FullpathPMReviewRequest
            payload = FullpathPMReviewRequest(**observed['identity']).model_dump()
            if payload['review_id'] != args.review_id:
                raise ValueError('review_identity_changed')
            generation = observed['job']['lease']['generation']
            report['mutation_requests'] = 1
            try:
                response = session_request('pm-review', payload)
                report['result'] = {k: response.get(k) for k in ('job_id', 'status', 'merged')}
                report['outcome'] = 'response_received'
            except (OSError, ValueError, HTTPException):
                report['outcome'] = 'response_uncertain'
            # Always reconcile after a mutation, including success/lost acknowledgement.
            after = session_request('readiness?' + urllib.parse.urlencode(dict(phase='status',job_id=args.job_id)))
            report['after'] = after
            job = after.get('job', {})
            if (after.get('ready') is True and job.get('id') == args.job_id
                    and job.get('status') == 'completed' and job.get('finalized') is True
                    and job.get('review_id') == args.review_id
                    and job.get('receipt') == {'state':'delivered','generation':3}
                    and job.get('lease') == {'state':'released','generation':generation}):
                report['outcome'] = 'completed'
            else:
                report['outcome'] = 'reconcile_before_retry'
        report['next_action'] = 'none' if report['outcome'] in ('observed','already_completed','completed') else 'Inspect read-only state and blockers; do not replay'
        if args.action != 'finalize' and observed.get('operation'):
            report['next_action'] = observed['operation']['next_action']
    except (OSError, ValueError, HTTPException, KeyError, TypeError):
        report.update(outcome='reconcile_before_retry' if report['mutation_requests'] else 'unobserved',
                      next_action='Reconcile read-only; request was not automatically retried')
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"PCP {args.action}: {report['outcome']} | job {args.job_id} | writes {report['mutation_requests']}")
        for check in report.get('observation', {}).get('checks', report.get('observation', {}).get('blockers', [])):
            print(f"{check['component']}: {check.get('state', check.get('code', 'unknown'))} | {check['actor']} | {check['next_action']}")
        operation = report.get('observation', {}).get('operation')
        if operation:
            print(f"operation: {operation['state']} | {operation['actor']} | eligible {operation['eligible']}")
        print(report['next_action'])
    return 0 if report['outcome'] in ('observed','already_completed','completed') else 2



def main(argv=None):
    """In-container operator client. No token on argv/logs; default is read-only."""
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'session':
        return session_main(argv[1:])
    import argparse
    import urllib.error
    import urllib.request
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='plan',
                        choices=('plan', 'readiness', 'register', 'execute', 'deliver'))
    action = parser.parse_args(argv).action
    token = os.environ.get('RUNTIME_API_TOKEN', '')
    if not token:
        print('runtime_auth_unavailable')
        return 2
    paths = {'plan': '/claim-recovery', 'readiness': '/readiness',
        'register': '/claim-recovery/register', 'execute': '/claim-recovery/execute', 'deliver': '/deliver'}
    request = urllib.request.Request('http://127.0.0.1:8787/v1/pcp-local'+paths[action],
        method='GET' if action in ('plan','readiness') else 'POST',
        headers={'Authorization': 'Bearer '+token})
    try:
        with urllib.request.urlopen(request, timeout=3600) as response:
            result = json.load(response)
        print(json.dumps(result, sort_keys=True))
        return 0
    except urllib.error.HTTPError as exc:
        # Do not reflect arbitrary upstream error content or authentication.
        print(json.dumps({'status': exc.code, 'action': action, 'next': 'read_only_reconcile'}))
        return 2
    except (OSError, ValueError):
        print('request_outcome_uncertain_read_only_reconcile_before_retry')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
