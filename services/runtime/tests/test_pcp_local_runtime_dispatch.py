"""#808: actual registrar/queue code, synthetic observers and transactional DB only.

No PostgreSQL, provider, Docker, Host startup, filesystem workspace or HTTP call.
The connection double stages INSERT/events until commit and models ambiguous
commit, rollback, row/advisory locks and receipt CAS independently of the engine.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import threading
from types import SimpleNamespace

import pytest

from app import engine as engine_module
from app import config
from app import pcp_local_task_queue as source
from app import pcp_local_worker_loop as worker
from app.engine import RuntimeEngine
from app.storage import Storage
from test_pcp_local_worker_loop import fixture, GitHub, flags


class Result:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Database(Storage):
    def __init__(self, receipt):
        self.receipts = {receipt["issue_number"]: deepcopy(receipt)}
        self.jobs = {}
        self.events = []
        self.lease = None
        self.lock = threading.RLock()
        self.trace = []
        self.connections = 0
        self.commit_failure = None
        self.before_registration = None
        self.before_insert = None
        self.after_registration = None

    def connect(self):
        self.connections += 1
        return Connection(self, self.connections)


class Connection:
    def __init__(self, db, number):
        self.db, self.number = db, number
        self.jobs, self.receipts, self.events = {}, {}, []
        self.locked = False

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        # Uncommitted INSERT/events/receipt writes are discarded on close/error.
        self.jobs.clear()
        self.receipts.clear()
        if self.locked:
            self.db.lock.release()
        return False

    def acquire(self):
        if not self.locked:
            self.db.lock.acquire()
            self.locked = True

    def execute(self, statement, params=None):
        sql = " ".join(statement.split())
        self.db.trace.append((self.number, sql, params))
        assert not any(token in sql for token in ("CREATE TABLE", "ALTER TABLE", "DELETE FROM"))
        if sql.startswith("SET LOCAL"):
            return Result()
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            self.acquire()
            if self.db.before_registration:
                callback, self.db.before_registration = self.db.before_registration, None
                callback()
            return Result()
        if sql.startswith("UPDATE cp_pcp_local_source_receipts"):
            self.acquire()
            target, job_id, repository, number, project, body, base, revision, baseline, state, generation, same_job = params
            row = self.db.receipts.get(number)
            expected = (repository, project, body, base, revision, baseline, state, generation)
            if row is None or tuple(row[k] for k in (
                "repository", "project_id", "body_sha256", "base_sha", "baseline_revision",
                "baseline_source_commit", "state", "generation")) != expected:
                return Result()
            if row["job_id"] is not None and row["job_id"] != same_job:
                return Result()
            row = {**row, "state": target, "generation": generation + 1,
                   "job_id": row["job_id"] or job_id}
            self.receipts[number] = deepcopy(row)
            return Result([{k: row[k] for k in ("state", "generation", "job_id")}])
        if "FROM cp_pcp_local_source_receipts" in sql:
            assert params[0:2] == (source.REPOSITORY, source.PROJECT_ID)
            rows = list(self.db.receipts.values())
            if "ORDER BY created_at" in sql:
                return Result(sorted((r for r in rows if r["state"] == "pending"),
                                     key=lambda r: r["issue_number"])[:1])
            if "issue_number<>" in sql:
                return Result([{"issue_number": r["issue_number"]} for r in rows
                    if r["issue_number"] != params[2] and (
                        r["state"] not in {"pending", "delivered"}
                        or (r["state"] == "pending" and (r["job_id"] is not None or r["generation"] != 0))
                        or (r["state"] == "delivered" and r["job_id"] is None))])
            if "FOR UPDATE" in sql:
                self.acquire()
            row = self.db.receipts.get(params[2])
            return Result([row] if row else [])
        if "FROM cp_project_leases" in sql:
            assert params == (source.PROJECT_ID,)
            self.acquire()
            return Result([self.db.lease] if self.db.lease is not None else [])
        if "FROM cp_jobs" in sql:
            if "WHERE project_id=" in sql:
                assert params == (source.PROJECT_ID,)
                return Result([r for r in self.db.jobs.values()
                    if r["project_id"] == source.PROJECT_ID and r.get("status") not in {"completed", "failed", "cancelled"}])
            row = self.db.jobs.get(params[0])
            return Result([row] if row else [])
        if sql.startswith("INSERT INTO cp_jobs"):
            assert self.locked
            if self.db.before_insert:
                self.db.before_insert()
            keys = ("id", "project_id", "status", "source_commit", "branch", "workspace", "task",
                    "repo_analysis", "route", "progress", "checkpoint", "result", "error", "dry_run", "created_at", "updated_at")
            row = dict(zip(keys, params))
            assert row["id"] not in self.db.jobs
            for key in ("task", "repo_analysis", "route", "progress", "checkpoint", "result"):
                row[key] = json.loads(row[key])
            self.jobs[row["id"]] = row
            return Result()
        if sql.startswith("INSERT INTO cp_job_events"):
            self.events.append(params)
            return Result()
        raise AssertionError("Unexpected fake DB operation: " + sql)

    def commit(self):
        self.db.trace.append((self.number, "COMMIT", None))
        registration = bool(self.jobs)
        if registration and self.db.commit_failure == "before":
            raise RuntimeError("synthetic commit failed before persistence")
        self.db.jobs.update(deepcopy(self.jobs))
        self.db.receipts.update(deepcopy(self.receipts))
        self.db.events.extend(deepcopy(self.events))
        self.jobs.clear()
        self.receipts.clear()
        self.events.clear()
        if registration and self.db.commit_failure == "after":
            raise RuntimeError("synthetic lost commit acknowledgement")
        if registration and self.db.after_registration:
            self.db.after_registration()


class Queue(asyncio.Queue):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.submissions = []
        self.failure = None

    async def put(self, job_id):
        # This assertion would fail if registration used a different transaction
        # or queued an uncommitted job, even when the test result claims success.
        assert job_id in self.db.jobs
        assert self.db.jobs[job_id]["status"] == "queued"
        self.submissions.append(job_id)
        self.db.trace.append((0, "ENQUEUE", job_id))
        if self.failure == "before":
            raise RuntimeError("synthetic queue acknowledgement lost")
        await super().put(job_id)
        if self.failure == "after":
            raise RuntimeError("synthetic queued but response lost")


@pytest.fixture
def setup(monkeypatch):
    flags(monkeypatch, live=True)  # Process-only synthetic flags, never config.
    task, issue, receipt, facts = fixture()
    db = Database(receipt)
    engine = RuntimeEngine(db)
    engine.queue = Queue(db)
    github = GitHub(issue)
    clock = [100.0]
    values = deepcopy(facts)
    values.update(
        writer={"project_id": source.PROJECT_ID, "workspace_mode": "isolated_clone",
                "lease": None, "other_job_ids": []},
        publisher={"project_id": source.PROJECT_ID, "repository": source.REPOSITORY,
                   "executor_only": True, "allow_create_pr": True, "allow_merge": False,
                   "credential_in_agent": False},
        model_choice={"id": "codex_gpt6_luna", "adapter": "codex_cli",
                      "model": "gpt-6-luna", "reasoning_effort": "medium"},
    )
    revisions = {k: str(i + 1) * 64 for i, k in enumerate(sorted(worker.OBSERVER_PARTS))}
    reads = []
    def reader(key):
        def observe(actual):
            assert actual == task
            reads.append(key)
            return worker.RuntimeObservation(deepcopy(values[key]), revisions[key], 100.0, 150.0)
        return observe
    readers = {k: reader(k) for k in worker.OBSERVER_PARTS}
    baseline = SimpleNamespace(project_id=source.PROJECT_ID, revision=task.baseline_revision,
        source_commit=task.baseline_source_commit,
        model_dump=lambda **_: {"project_id": source.PROJECT_ID, "revision": task.baseline_revision,
                               "source_commit": task.baseline_source_commit, "status": "approved"})
    project = {"repository": source.REPOSITORY, "base_branch": "main", "registration_status": "approved",
               "runtime": {"workspace_mode": "isolated_clone", "developer_permission_mode": "bounded",
                           "exclusive_project_lease": False},
               "autonomy": {"allow_commit": True, "allow_push_ai_branch": True,
                            "allow_create_pr": True, "allow_production_deploy": False}}
    registry = {"projects": {source.PROJECT_ID: {"active_revision": task.baseline_revision}}}
    monkeypatch.setattr(config, "project_config", lambda _: deepcopy(project))
    monkeypatch.setattr(engine_module, "project_config", lambda _: deepcopy(project))
    monkeypatch.setattr(config, "project_baselines_doc", lambda: deepcopy(registry))
    monkeypatch.setattr(engine_module, "resolve_project_baseline", lambda *_: baseline)
    monkeypatch.setattr("app.baseline.resolve_project_baseline", lambda *_: baseline)
    # The model tuple is checked against the real, checked-in model registry.
    def forbidden(*_, **__):
        raise AssertionError("No Host, worker, model or alternate job insertion")
    monkeypatch.setattr(db, "create", forbidden)
    monkeypatch.setattr(db, "init", forbidden)
    monkeypatch.setattr(db, "acquire_project_lease", forbidden)
    monkeypatch.setattr(engine, "start", forbidden)
    monkeypatch.setattr("app.engine_execution.build_adapter", forbidden)
    async def dispatch():
        return await engine.dispatch_pcp_local_once(issue_number=task.issue_number,
            readers=readers, github=github, clock=lambda: clock[0])
    return SimpleNamespace(task=task, issue=issue, db=db, engine=engine, github=github,
        readers=readers, facts=values, revisions=revisions, clock=clock, reads=reads,
        dispatch=dispatch, project=project, registry=registry, baseline=baseline)


def claimed(s):
    return s.db.receipts[s.task.issue_number]


def test_one_normal_queued_job_and_existing_queue_after_atomic_commit(setup):
    s = setup
    result = asyncio.run(s.dispatch())
    job_id = worker.stable_job_id(s.task)
    assert result["runtime_job_state"] == "queued"
    assert result["model_calls"] == 0 and result["model_execution_proof"] == "NOT_ATTESTED"
    assert s.engine.queue.submissions == [job_id]
    assert list(s.db.jobs) == [job_id]
    row = s.db.jobs[job_id]
    assert row["status"] == "queued" and row["source_commit"] == s.task.base_sha
    assert row["task"]["description"] == "Implement one bounded PCP-only Python change and one regression test."
    binding = row["checkpoint"]["pcp_local_source"]
    assert binding["receipt"] == worker.claimed_source_receipt(s.task) == claimed(s)
    assert binding["reservation"] == "pcp_local_isolated_queued_job"
    assert set(binding["observations"]) == worker.OBSERVER_PARTS
    assert row["checkpoint"]["project_baseline"]["source_commit"] == s.task.baseline_source_commit
    assert row["progress"]["model_calls"] == 0
    assert s.db.lease is None and len(s.db.events) == 1
    insertion = next(i for i, (_, sql, _) in enumerate(s.db.trace) if sql.startswith("INSERT INTO cp_jobs"))
    tx = s.db.trace[insertion][0]
    assert any(n == tx and "FROM cp_pcp_local_source_receipts" in sql and "FOR UPDATE" in sql
               for n, sql, _ in s.db.trace[:insertion])
    commit = next(i for i, (n, sql, _) in enumerate(s.db.trace[insertion:], insertion) if n == tx and sql == "COMMIT")
    enqueue = next(i for i, (_, sql, _) in enumerate(s.db.trace) if sql == "ENQUEUE")
    assert insertion < commit < enqueue
    assert claimed(s)["state"] == "claimed" and claimed(s)["generation"] == 1


@pytest.mark.parametrize("field,value", [
    ("repository", "sonvhse06072/chonhac"), ("project_id", "chonhac"),
    ("issue_number", 1000), ("task_key", "another-approved-key"),
    ("body_sha256", "f" * 64), ("goal_sha256", "f" * 64),
    ("base_sha", "f" * 40), ("baseline_revision", "different"),
    ("baseline_source_commit", "e" * 40), ("allowed_paths", ["tests/test_pcp_light_other.py"]),
    ("generation", 2), ("generation", True), ("state", "pending"), ("job_id", "e" * 32),
])
def test_full_receipt_rechecked_in_insert_transaction(setup, field, value):
    s = setup
    s.db.before_registration = lambda: claimed(s).__setitem__(field, value)
    with pytest.raises(source.TaskStop, match="launch_uncertain"):
        asyncio.run(s.dispatch())
    assert not s.db.jobs and not s.db.events and not s.engine.queue.submissions
    assert claimed(s)[field] == value  # Never resets the consumed/corrupt claim.


@pytest.mark.parametrize("status", [None, "queued", "routing", "blocked", "interrupted", "waiting_human", "unknown"])
def test_any_nonterminal_or_unknown_pcp_writer_blocks(setup, status):
    s = setup
    prior = {"id": "d" * 32, "project_id": source.PROJECT_ID, "status": status,
             "progress": {"model_calls": 7}}
    s.db.jobs[prior["id"]] = deepcopy(prior)
    with pytest.raises(source.TaskStop, match="launch_uncertain"):
        asyncio.run(s.dispatch())
    assert s.db.jobs == {prior["id"]: prior}
    assert not s.engine.queue.submissions and claimed(s)["state"] == "claimed"


@pytest.mark.parametrize("project,status", [("chonhac", "completed"), (source.PROJECT_ID, "completed"), (source.PROJECT_ID, "queued")])
def test_existing_same_job_id_is_never_reused_even_if_partial_metadata_matches(setup, project, status):
    s = setup
    job_id = worker.stable_job_id(s.task)
    prior = {"id": job_id, "project_id": project, "status": status,
             "checkpoint": {"work_order": {"id": s.task.task_key,
                                           "baseline_revision": s.task.baseline_revision}},
             "progress": {"model_calls": 9}}
    s.db.jobs[job_id] = deepcopy(prior)
    with pytest.raises(source.TaskStop, match="launch_uncertain"):
        asyncio.run(s.dispatch())
    assert s.db.jobs == {job_id: prior} and not s.engine.queue.submissions


@pytest.mark.parametrize("state,job_id", [("claimed", None), ("claimed", "e" * 32), ("running", "e" * 32), ("blocked", None), (None, None), ("unknown", None), ("pending", "e" * 32), ("delivered", None)])
def test_other_claim_with_unknown_or_known_owner_is_not_adopted(setup, state, job_id):
    s = setup
    other = {**deepcopy(claimed(s)), "issue_number": 1000, "state": state, "job_id": job_id}
    s.db.receipts[1000] = deepcopy(other)
    with pytest.raises(source.TaskStop, match="launch_uncertain"):
        asyncio.run(s.dispatch())
    assert s.db.receipts[1000] == other and not s.db.jobs


@pytest.mark.parametrize("mutation", ["added", "generation", "owner", "active"])
def test_lease_drift_after_observation_is_rejected_in_transaction(setup, mutation):
    s = setup
    lease = {"project_id": source.PROJECT_ID, "owner_job_id": "d" * 32,
             "generation": 1, "state": "released"}
    if mutation != "added":
        s.facts["writer"]["lease"] = deepcopy(lease)
        s.db.lease = deepcopy(lease)
    def drift():
        s.db.lease = deepcopy(lease)
        if mutation == "generation":
            s.db.lease["generation"] = 2
        elif mutation == "owner":
            s.db.lease["owner_job_id"] = "e" * 32
        elif mutation == "active":
            s.db.lease["state"] = "active"
    s.db.before_registration = drift
    with pytest.raises(source.TaskStop, match="launch_uncertain"):
        asyncio.run(s.dispatch())
    assert not s.db.jobs and not s.engine.queue.submissions


@pytest.mark.parametrize("stage", ["insert", "commit_before", "commit_after", "enqueue_before", "enqueue_after"])
def test_crash_preserves_claim_and_durable_outcome_without_retry(setup, stage):
    s = setup
    def crash():
        raise RuntimeError("synthetic interruption")
    if stage == "insert":
        s.db.before_insert = crash
    elif stage.startswith("commit"):
        s.db.commit_failure = stage.split("_")[1]
    else:
        s.engine.queue.failure = stage.split("_")[1]
    with pytest.raises(source.TaskStop, match="launch_uncertain"):
        asyncio.run(s.dispatch())
    assert claimed(s)["state"] == "claimed" and claimed(s)["generation"] == 1
    assert len(s.db.jobs) == (stage in {"commit_after", "enqueue_before", "enqueue_after"})
    before = deepcopy(s.db.jobs)
    submissions = list(s.engine.queue.submissions)
    try:
        result = asyncio.run(s.dispatch())
        assert result["status"] == "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED"
    except source.TaskStop:
        assert stage == "enqueue_after"
    assert s.db.jobs == before and s.engine.queue.submissions == submissions


@pytest.mark.parametrize("part,field,value", [
    ("project", "repository", "sonvhse06072/chonhac"),
    ("baseline", "source_commit", "d" * 40), ("baseline", "active_revision", "wrong"),
    ("isolation", "agent_docker_socket", True), ("isolation", "other_repo_mounts", True),
    ("isolation", "active_writers", 1), ("isolation", "source_repo_clean", False),
    ("provider", "credential_scoped", False), ("provider", "github_token_in_agent", True),
    ("provider", "host_keyring_mounted", True), ("provider", "provider_network_reviewed", False),
    ("provider", "installed_cli_version", "0.0.0"), ("provider", "model", "gpt-fake"),
    ("budget", "provider_quota_verified", False), ("budget", "owner_approved", False),
    ("publisher", "credential_in_agent", True), ("publisher", "executor_only", False),
    ("publisher", "allow_merge", True), ("model_choice", "id", "fake_model"),
    ("model_choice", "reasoning_effort", "ultra"), ("writer", "other_job_ids", ["d" * 32]),
])
def test_untrusted_or_incomplete_facts_never_claim(setup, part, field, value):
    s = setup
    s.facts[part][field] = value
    with pytest.raises((source.TaskStop, ValueError)):
        asyncio.run(s.dispatch())
    assert claimed(s)["state"] == "pending" and not s.db.jobs
    assert not s.engine.queue.submissions


@pytest.mark.parametrize("mutation", ["missing", "boolean", "dictionary", "expired", "future", "revision", "changed_revision"])
def test_missing_fake_expired_or_revised_reader_is_never_authority(setup, mutation):
    s = setup
    if mutation == "missing":
        del s.readers["writer"]
    elif mutation in {"boolean", "dictionary"}:
        s.readers["provider"] = lambda _: True if mutation == "boolean" else s.facts["provider"]
    elif mutation == "expired":
        s.clock[0] = 150.0
    elif mutation == "future":
        s.clock[0] = 99.0
    elif mutation == "revision":
        s.revisions["writer"] = "owner says yes"
    else:
        s.db.before_registration = lambda: s.revisions.__setitem__("writer", "f" * 64)
        # This mutation is discovered by the final observer pass after commit.
    with pytest.raises((source.TaskStop, ValueError)):
        asyncio.run(s.dispatch())
    assert not s.engine.queue.submissions
    if mutation == "changed_revision":
        assert len(s.db.jobs) == 1 and claimed(s)["state"] == "claimed"
    else:
        assert not s.db.jobs and claimed(s)["state"] == "pending"


@pytest.mark.parametrize("mutation", ["flag", "baseline", "project", "provider", "issue", "ttl"])
def test_postcommit_revocation_preserves_queued_row_but_never_enqueues(setup, monkeypatch, mutation):
    s = setup
    def revoke():
        if mutation == "flag":
            monkeypatch.delenv("PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION")
        elif mutation == "baseline":
            s.registry["projects"][source.PROJECT_ID]["active_revision"] = "wrong"
        elif mutation == "project":
            s.project["autonomy"]["allow_create_pr"] = False
        elif mutation == "provider":
            s.facts["provider"]["credential_scoped"] = False
        elif mutation == "issue":
            s.issue["body"] += " changed"
        else:
            s.clock[0] = 151.0
    s.db.after_registration = revoke
    with pytest.raises(source.TaskStop, match="launch_uncertain"):
        asyncio.run(s.dispatch())
    assert len(s.db.jobs) == 1 and not s.engine.queue.submissions
    assert claimed(s)["state"] == "claimed" and claimed(s)["generation"] == 1


def test_parallel_dispatches_have_one_durable_insert_and_one_enqueue(setup):
    s = setup
    async def run():
        return await asyncio.gather(s.dispatch(), s.dispatch(), return_exceptions=True)
    result = asyncio.run(run())
    assert sum(isinstance(v, dict) and v.get("runtime_job_state") == "queued" for v in result) == 1
    assert len(s.db.jobs) == len(s.db.events) == len(s.engine.queue.submissions) == 1


def test_two_runtime_instances_racing_the_same_pending_snapshot_cannot_launch_twice(setup):
    s = setup
    async def run():
        gate = asyncio.Event()
        calls = 0
        class RacingGitHub:
            async def local_source_issue(self, *, issue_number):
                nonlocal calls
                calls += 1
                if calls <= 2:
                    if calls == 2:
                        gate.set()
                    await gate.wait()  # Both have read the original pending row.
                assert issue_number == s.task.issue_number
                return deepcopy(s.issue)
        other = RuntimeEngine(s.db)
        other.queue = Queue(s.db)
        github = RacingGitHub()
        results = await asyncio.gather(*(
            instance.dispatch_pcp_local_once(issue_number=s.task.issue_number,
                readers=s.readers, github=github, clock=lambda: s.clock[0])
            for instance in (s.engine, other)), return_exceptions=True)
        assert sum(isinstance(v, dict) and v.get("runtime_job_state") == "queued" for v in results) == 1
        assert sum(isinstance(v, source.TaskStop) for v in results) == 1
        assert len(s.engine.queue.submissions) + len(other.queue.submissions) == 1
    asyncio.run(run())
    assert len(s.db.jobs) == len(s.db.events) == 1
    assert claimed(s)["generation"] == 1


def test_source_job_cannot_execute_or_reenter_general_registration(setup):
    s = setup
    asyncio.run(s.dispatch())
    job_id = worker.stable_job_id(s.task)
    with pytest.raises(RuntimeError, match="separate execution admission"):
        asyncio.run(s.engine.run_job(job_id))
    with pytest.raises(source.TaskStop, match="trusted_registration"):
        s.engine.create_job({"project_id": source.PROJECT_ID, "_job_id": job_id})
    assert s.db.jobs[job_id]["status"] == "queued"


def test_fixed_issue_is_checked_before_github_or_claim(setup):
    s = setup
    with pytest.raises(source.TaskStop, match="approved_issue_mismatch"):
        asyncio.run(s.engine.dispatch_pcp_local_once(issue_number=1000,
            readers=s.readers, github=s.github, clock=lambda: s.clock[0]))
    assert s.github.calls == 0 and claimed(s)["state"] == "pending"


def test_no_flags_no_readers_no_db_and_no_existing_worker(setup, monkeypatch):
    s = setup
    monkeypatch.delenv("PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION")
    with pytest.raises(source.TaskStop, match="live_activation_not_approved"):
        asyncio.run(s.dispatch())
    assert s.db.connections == s.github.calls == 0
    flags(monkeypatch, live=True)
    s.engine.worker_task = object()
    with pytest.raises(source.TaskStop, match="existing_worker"):
        asyncio.run(s.dispatch())
    assert s.db.connections == s.github.calls == 0


def protected_job(s, identity="source", status="queued"):
    asyncio.run(s.dispatch())
    job_id = worker.stable_job_id(s.task)
    row = s.db.jobs[job_id]
    row["status"] = status
    if identity == "missing-marker":
        row["checkpoint"].pop("pcp_local_source")
    elif identity == "null-marker":
        row["checkpoint"]["pcp_local_source"] = None
    elif identity == "false-marker":
        row["checkpoint"]["pcp_local_source"] = False
    elif identity == "corrupt-marker":
        row["checkpoint"]["pcp_local_source"] = "untrusted-allow"
    elif identity == "foreign-marker":
        row["project_id"] = "synthetic-foreign"
    elif identity == "missing-project":
        row.pop("project_id")
    elif identity == "corrupt-checkpoint":
        row["checkpoint"] = ["not-a-checkpoint"]
    return job_id


class NoLegacyEffects:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def forbidden(*args, **kwargs):
            self.calls.append(name)
            raise AssertionError("Forbidden legacy side effect: " + name)
        return forbidden


@pytest.mark.parametrize("identity", ["source", "missing-marker", "null-marker", "false-marker", "corrupt-marker", "foreign-marker", "missing-project", "corrupt-checkpoint"])
@pytest.mark.parametrize("operation", ["run_job", "resume", "cancel", "cleanup", "request_review_repair", "advance_direct_job_source", "resolve_human_decision"])
def test_b2f2_facade_mutators_deny_before_any_derived_effect(setup, monkeypatch, identity, operation):
    from app.engine_core import SourceJobNotExecutable
    s = setup
    job_id = protected_job(s, identity, "blocked")
    before = deepcopy((s.db.jobs, s.db.receipts, s.db.events, s.db.lease))
    effects = NoLegacyEffects()
    s.engine.ddev = s.engine.router = effects
    def no_write(*args, **kwargs):
        effects.calls.append("write")
        raise AssertionError("SOURCE modified durable state")
    monkeypatch.setattr(s.db, "update", no_write)
    arguments = {
        "resume": {"reroute": True, "reset_transient_provider_failures": True},
        "cleanup": {"remove_workspace": True, "release_ddev_data": True},
        "request_review_repair": {"expected_commit": "f" * 40, "finding": "synthetic"},
        "advance_direct_job_source": {"expected_old_source": "a" * 40, "expected_new_source": "b" * 40},
        "resolve_human_decision": {"action": "approve"},
    }
    with pytest.raises(SourceJobNotExecutable):
        asyncio.run(getattr(s.engine, operation)(job_id, **arguments.get(operation, {})))
    assert effects.calls == []
    assert (s.db.jobs, s.db.receipts, s.db.events, s.db.lease) == before
    assert s.engine.queue.submissions == [job_id]


def test_b2f2_delivery_entry_denies_even_when_called_unbound(setup, monkeypatch):
    from app import engine_delivery
    from app.engine_core import SourceJobNotExecutable
    s = setup
    job_id = protected_job(s)
    before = deepcopy((s.db.jobs, s.db.receipts, s.db.events))
    def forbidden(*args, **kwargs):
        raise AssertionError("Legacy recovery inspected a SOURCE job")
    monkeypatch.setattr(engine_delivery, "recover_legacy_accepted_result", forbidden)
    monkeypatch.setattr(s.engine, "_ensure_review_repair_churn_epoch", forbidden)
    with pytest.raises(SourceJobNotExecutable):
        asyncio.run(engine_delivery.RuntimeEngine.run_job(s.engine, job_id))
    assert (s.db.jobs, s.db.receipts, s.db.events) == before


@pytest.mark.parametrize("identity", ["source", "null-marker", "foreign-marker", "missing-project", "corrupt-checkpoint"])
def test_b2f2_stray_queue_item_cannot_run_fail_or_cleanup(setup, monkeypatch, caplog, identity):
    from app.engine_core import RuntimeEngineCore
    s = setup
    job_id = protected_job(s, identity)
    before = deepcopy((s.db.jobs, s.db.receipts, s.db.events, s.db.lease))
    effects = NoLegacyEffects()
    s.engine.ddev = effects
    # Bypass constructor's entry wrapper to independently test dequeue rejection.
    s.engine.run_job = effects.run_job
    s.engine._quiesce_stable_manual_job = effects.cleanup
    async def run():
        task = asyncio.create_task(RuntimeEngineCore._worker_loop(s.engine))
        try:
            await asyncio.wait_for(s.engine.queue.join(), timeout=1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(run())
    assert effects.calls == [] and not s.engine.active_jobs
    assert "withheld SOURCE/ambiguous queue item; durable claim unchanged" in caplog.text
    assert (s.db.jobs, s.db.receipts, s.db.events, s.db.lease) == before


def test_b2f2_cleanup_helpers_preserve_terminal_source_lease(setup):
    s = setup
    job_id = protected_job(s, status="completed")
    s.db.jobs[job_id]["checkpoint"]["workspace_mode"] = "direct"
    before = deepcopy((s.db.jobs, s.db.receipts, s.db.events, s.db.lease))
    effects = NoLegacyEffects()
    s.engine.ddev = effects
    async def run():
        assert await s.engine._retire_terminal_direct_preview(job_id) is False
        assert await s.engine._restore_terminal_direct_workspace(job_id) is False
        await s.engine._quiesce_stable_manual_job(job_id)
        assert s.engine._release_terminal_direct_lease(job_id) is False
    asyncio.run(run())
    assert effects.calls == []
    assert (s.db.jobs, s.db.receipts, s.db.events, s.db.lease) == before


HTTP_SOURCE_MUTATIONS = [
    ("run", {"reroute": True}), ("cancel", None),
    ("cleanup?remove_workspace=true&release_ddev_data=true", None),
    ("advance-source", {"expected_old_source": "a" * 40, "expected_new_source": "b" * 40}),
    ("review-repair", {"expected_commit": "f" * 40, "finding": "synthetic"}),
    ("decision", {"action": "approve"}),
    ("collaborations", {"role": "debugger", "topic": "synthetic", "objective": "synthetic",
                        "question": "synthetic", "evidence": [{"ref": "synthetic", "summary": "synthetic"}]}),
    ("collaborations/fake/recheck", {"developer_response": "synthetic"}),
    ("collaborations/fake/cancel", None),
]


@pytest.mark.parametrize("identity", ["source", "foreign-marker", "missing-project", "null-marker", "corrupt-checkpoint"])
@pytest.mark.parametrize("suffix,body", HTTP_SOURCE_MUTATIONS)
def test_b2f2_authenticated_http_mutators_stop_before_executor_or_orchestrator(setup, monkeypatch, identity, suffix, body):
    import httpx
    from app import main
    s = setup
    job_id = protected_job(s, identity)
    for flag in main._PCP_LOCAL_FLAGS:
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "normal")
    monkeypatch.setenv("RUNTIME_API_TOKEN", "synthetic-control-token")
    monkeypatch.setattr(main, "storage", s.db)
    effects = NoLegacyEffects()
    # Any handler reaching the engine/control plane instead of its durable-row
    # guard fails the test. ASGI requests make no real network/listener call.
    s.engine.ddev = effects
    monkeypatch.setattr(main, "engine", s.engine)
    monkeypatch.setattr(main, "collaboration_manager", effects)
    monkeypatch.setattr(main, "plan_orchestrator", effects)
    monkeypatch.setattr(main, "prepare_orchestrated_job_resume", lambda *a: (_ for _ in ()).throw(AssertionError("plan touched")))
    before = deepcopy((s.db.jobs, s.db.receipts, s.db.events, s.db.lease))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://synthetic") as client:
            result = await client.post(f"/v1/jobs/{job_id}/{suffix}", json=body,
                                      headers={"Authorization": "Bearer synthetic-control-token"})
            assert result.status_code == 409, result.text
            assert "separate execution admission" in result.json()["detail"]
    asyncio.run(run())
    assert effects.calls == []
    assert (s.db.jobs, s.db.receipts, s.db.events, s.db.lease) == before


@pytest.mark.parametrize('enabled,commands,passed,stdout,expected', [
    (False, ['tests/test_pcp_light_example.py'], True, '2 passed', 'disabled'),
    (True, [], True, '2 passed', 'missing'),
    (True, ['tests/test_pcp_light_example.py'], True, '', False),
    (True, ['tests/test_pcp_light_example.py'], True, '2 skipped', False),
    (True, ['tests/test_pcp_light_example.py'], False, '1 passed, 1 failed', False),
    (True, ['tests/test_pcp_light_example.py'], True, '2 passed, 1 skipped', True),
])
def test_pcp_verification_never_accepts_disabled_empty_or_skipped(enabled, commands, passed, stdout, expected):
    engine = object.__new__(RuntimeEngine)
    calls = []
    async def phase(**kwargs):
        calls.append(kwargs['phase'])
        return {'phase': kwargs['phase'], 'passed': passed, 'commands': [
            {'returncode': 0, 'stdout': stdout, 'timed_out': False}]}
    engine.ddev = SimpleNamespace(phase=phase)
    project = {'ddev': {'enabled': enabled, 'targeted_tests': commands, 'full_tests': commands}}
    if isinstance(expected, str):
        with pytest.raises(source.TaskStop, match=expected):
            asyncio.run(engine.verify_pcp_local('a' * 32, '/fake', project))
        assert calls == []
    else:
        result = asyncio.run(engine.verify_pcp_local('a' * 32, '/fake', project))
        assert result['passed'] is expected
        if expected:
            assert result['test_runs'] == 4 and result['skipped_tests'] == 2
            assert calls == ['targeted_tests', 'full_tests']


def test_admitted_worker_rejects_caller_dictionaries_without_claim(setup):
    s = setup
    with pytest.raises(source.TaskStop, match='concrete_readers'):
        asyncio.run(worker.run_admitted_job(s.engine, s.readers, s.task))
    assert claimed(s)['state'] == 'pending' and s.db.jobs == {}


def test_dedicated_delivery_requires_concrete_reader_before_mutation(setup):
    s = setup
    with pytest.raises(source.TaskStop, match='delivery_admission'):
        asyncio.run(s.engine.deliver_pcp_local('a' * 32, s.readers, s.task))
    assert s.db.jobs == {}


@pytest.mark.parametrize('outcome', ['success', 'timeout', 'repair'])
def test_dedicated_worker_keeps_durable_identity_and_never_replays(setup, monkeypatch, tmp_path, outcome):
    from pathlib import Path
    from app import pcp_local_worker_loop as trusted
    from app.adapters.base import AgentRun
    from app.adapters.codex import CodexAdapter
    s = setup
    asyncio.run(s.dispatch())
    job_id = worker.stable_job_id(s.task)
    engine = s.engine
    engine.workspace_root = tmp_path
    workspace = tmp_path/job_id
    workspace.mkdir()
    reader = object.__new__(trusted.TrustedReaders)
    reader.engine = engine
    reader.lease_generation = None
    reader.task = s.task
    reader.activation = {'budget': {'model_calls':2,'max_wall_seconds':300,'cash_ceiling_usd':5}}
    reader.snapshot = {'model_choice':s.facts['model_choice']}
    reader.route = {'strategy':{'executor':s.facts['model_choice']}}
    reader.authority = lambda: (s.project, s.baseline)
    refreshes = []
    async def refresh(task):
        assert task == s.task
        refreshes.append(s.db.receipts[s.task.issue_number]['state'])
        return reader.snapshot
    reader.refresh = refresh
    monkeypatch.setattr(s.db, 'get', lambda key: deepcopy(s.db.jobs.get(key)))
    def update(key, **fields):
        s.db.jobs[key].update(deepcopy(fields))
    monkeypatch.setattr(s.db, 'update', update)
    def lease(project, key):
        assert project == source.PROJECT_ID and key == job_id
        s.db.lease = dict(project_id=project,owner_job_id=key,generation=1,state='active')
        return deepcopy(s.db.lease)
    monkeypatch.setattr(s.db,'acquire_project_lease',lease)
    monkeypatch.setattr('app.security.harden_runtime_process_secret_boundary',lambda: None)
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    async def create_workspace(**kwargs):
        assert kwargs == dict(job_id=job_id,project_id=source.PROJECT_ID,ref=s.task.base_sha,workspace_mode='isolated_clone')
        return dict(workspace=str(workspace),branch='ai/'+job_id[:12],source_commit=s.task.base_sha)
    monkeypatch.setattr(engine.ddev,'create_workspace',create_workspace)
    attempts = []
    async def fake_run(self, **kwargs):
        # Each invocation is preceded by a persisted increment and running CAS.
        assert s.db.receipts[s.task.issue_number]['state'] == 'running'
        assert s.db.jobs[job_id]['progress']['model_calls'] == len(attempts)+1
        attempts.append(kwargs['mode'])
        if outcome == 'timeout':
            (workspace/'retained-diff.txt').write_text('uncertain edit')
            raise TimeoutError('unknown provider result')
        return AgentRun(adapter='codex_cli',model=self.model,returncode=0,output='done')
    monkeypatch.setattr(CodexAdapter,'run',fake_run)
    diff = {'changed_files':list(s.task.allowed_paths),'diff_hash':'c'*64}
    monkeypatch.setattr('app.repo.diff_state',lambda *a,**kw:deepcopy(diff))
    commits=[]
    monkeypatch.setattr('app.repo.commit_changes',lambda *args:commits.append(args) or 'd'*40)
    checks=[]
    async def verify(*args,**kwargs):
        checks.append(1)
        return {'passed': outcome!='repair' or len(checks)>1, 'test_runs':1}
    monkeypatch.setattr(engine,'verify_pcp_local',verify)
    deliveries=[]
    async def deliver(key, actual_reader, task):
        assert s.db.jobs[key]['checkpoint']['pcp_local_execution']['state']=='verified'
        assert actual_reader is reader and task == s.task
        deliveries.append(key)
    monkeypatch.setattr(engine,'deliver_pcp_local',deliver)
    if outcome == 'timeout':
        with pytest.raises(TimeoutError):
            asyncio.run(worker.run_admitted_job(engine,reader,s.task))
        assert attempts == ['execute'] and not checks and not commits and not deliveries
        assert (workspace/'retained-diff.txt').read_text()=='uncertain edit'
        assert s.db.jobs[job_id]['status']=='blocked'
    else:
        asyncio.run(worker.run_admitted_job(engine,reader,s.task))
        assert attempts == (['execute','repair'] if outcome=='repair' else ['execute'])
        assert deliveries==[job_id] and len(commits)==1
    assert s.db.receipts[s.task.issue_number]['job_id']==job_id
    assert s.db.receipts[s.task.issue_number]['state']=='running'
    assert s.db.lease['owner_job_id']==job_id and s.db.lease['generation']==1
    count=len(attempts)
    with pytest.raises(source.TaskStop):
        asyncio.run(worker.run_admitted_job(engine,reader,s.task))
    assert len(attempts)==count
