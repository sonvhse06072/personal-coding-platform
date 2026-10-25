"""B2.2b: deterministic local queue handoff, no real model/network/Docker."""
from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from app import pcp_local_task_queue as q
from app import pcp_local_worker_loop as worker

BASE = "a" * 40
REVISION = "pcp-local-approved"


def fixture():
    task = {
        "version": 1, "key": "pcp-next-approved",
        "base_sha": BASE,
        "goal": "Implement one bounded PCP-only Python change and one regression test.",
        "allowed_paths": [
            "scripts/pcp-light-next.py", "tests/test_pcp_light_next.py",
        ],
        "mode": "github_source_pr_only",
    }
    body = q.MARKER + "\n" + json.dumps(task)
    source = {
        "project_id": q.PROJECT_ID, "repository": q.REPOSITORY,
        "number": 999, "author": q.OWNER, "state": "open",
        "is_pull_request": False,
        "html_url": f"https://github.com/{q.REPOSITORY}/issues/999",
        "main_sha": BASE, "body": body,
    }
    t = q.verify_issue(
        source, issue_number=999,
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        base_sha=BASE, baseline_revision=REVISION,
        baseline_source_commit="b" * 40,
    )
    row = {
        "repository": t.repository, "issue_number": t.issue_number,
        "project_id": t.project_id, "task_key": t.task_key,
        "body_sha256": t.body_sha256, "base_sha": t.base_sha,
        "baseline_revision": t.baseline_revision,
        "baseline_source_commit": t.baseline_source_commit,
        "goal_sha256": t.goal_sha256, "allowed_paths": list(t.allowed_paths),
        "state": "pending", "generation": 0, "job_id": None,
    }
    observed = {
        "project": {
            "project_id": q.PROJECT_ID, "repository": q.REPOSITORY,
            "base_branch": "main", "registered": True,
            "allow_create_pr": True, "allow_production_deploy": False,
        },
        "baseline": {
            "project_id": q.PROJECT_ID, "revision": REVISION,
            "source_commit": "b" * 40, "active_revision": REVISION,
            "status": "approved",
        },
        "isolation": {
            "current_main_sha": BASE, "source_repo_clean": True,
            "workspace_mode": "isolated_clone",
            "workspace_lease_state": "free", "active_writers": 0,
            "other_repo_mounts": False, "agent_docker_socket": False,
            "isolated_ddev_network": True,
        },
        "provider": {
            "adapter": "codex_cli", "model": "gpt-6-luna",
            "effort": "medium", "installed_cli_version": "0.160.0",
            "approved_cli_version": "0.160.0", "credential_scoped": True,
            "github_token_in_agent": False,
            "host_keyring_mounted": False, "provider_network_reviewed": True,
        },
        "budget": {
            "owner_approved": True, "provider_quota_verified": True,
            "model_calls": 1, "max_wall_seconds": 600,
            "max_changed_files": 2, "cash_ceiling_usd": 0.0,
        },
    }
    return t, source, row, observed


class Receipts:
    def __init__(self, row):
        self.row = row
        self.scans = 0
        self.claims = 0
        self.rechecks = 0
        self.on_claim = None

    def next_pending(self):
        self.scans += 1
        return self.row if self.row is not None and self.row["state"] == "pending" else None

    def advance(self, task, **args):
        self.claims += 1
        if self.row is None or self.row["state"] != args["expected_state"]:
            raise q.TaskStop("task_generation_or_identity_stale")
        if self.row["generation"] != args["expected_generation"]:
            raise q.TaskStop("task_generation_or_identity_stale")
        if args["target_state"] != "claimed" or not args["worker_authorized"]:
            raise AssertionError("unsafe transition")
        self.row.update(state="claimed", job_id=args["job_id"], generation=1)
        if self.on_claim is not None:
            self.on_claim()
        return {"state": "claimed", "generation": 1, "job_id": args["job_id"]}

    def read_claimed(self, task, *, job_id):
        self.rechecks += 1
        if (self.row is None
                or self.row["issue_number"] != task.issue_number
                or self.row["body_sha256"] != task.body_sha256
                or self.row["state"] != "claimed"
                or self.row["generation"] != 1
                or self.row["job_id"] != job_id):
            raise q.TaskStop("pcp_local_claim_receipt_identity_changed")
        return dict(self.row)


class GitHub:
    def __init__(self, source):
        self.source = source
        self.calls = 0

    async def local_source_issue(self, *, issue_number):
        self.calls += 1
        assert issue_number == 999
        return self.source


class Attestor:
    def __init__(self, evidence):
        self.evidence = evidence
        self.calls = 0

    def observe(self, task):
        self.calls += 1
        assert task.issue_number == 999
        return self.evidence


class Launcher:
    def __init__(self, mode="ok"):
        self.calls = 0
        self.mode = mode

    async def launch(self, *, task, goal, job_id, evidence):
        self.calls += 1
        assert task.issue_number == 999
        assert goal == "Implement one bounded PCP-only Python change and one regression test."
        assert job_id == worker.stable_job_id(task)
        assert evidence["status"] == "ADMISSION_EVIDENCE_CHECKED_NOT_DISPATCHED"
        if self.mode == "raise":
            raise RuntimeError("simulated transport uncertainty")
        if self.mode == "wrong_id":
            job_id = "f" * 32
        return {
            "job_id": job_id, "state": "queued",
            "source_commit": task.base_sha,
            "baseline_revision": task.baseline_revision,
        }


def make_loop(source_changes=None, evidence_changes=None, *, launcher=None):
    t, source, row, evidence = fixture()
    if source_changes:
        source.update(source_changes)
    if evidence_changes:
        for key, mods in evidence_changes.items():
            evidence[key].update(mods)
    receipts = Receipts(row)
    github = GitHub(source)
    attestor = Attestor(evidence)
    return worker.LocalWorkerLoop(
        receipts=receipts, github=github, trusted_attestor=attestor,
        launcher=launcher,
    ), t, receipts, github, attestor


def flags(monkeypatch, live=False):
    monkeypatch.setenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_LOCAL_TASK_WORKER_ENABLED", "owner-approved")
    if live:
        monkeypatch.setenv("PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION",
                           "owner-approved")
    else:
        monkeypatch.delenv("PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION",
                           raising=False)


def test_unset_switches_prevent_db_and_github(monkeypatch):
    monkeypatch.delenv("PCP_LOCAL_TASK_SOURCE_ENABLED", raising=False)
    monkeypatch.delenv("PCP_LOCAL_TASK_WORKER_ENABLED", raising=False)
    loop, _, receipts, github, _ = make_loop()
    with pytest.raises(q.TaskStop, match="pcp_local_worker_disabled"):
        asyncio.run(loop.preview_once())
    assert receipts.scans == github.calls == 0


def test_no_trusted_attestor_stops_before_db_even_if_two_flags_set(monkeypatch):
    flags(monkeypatch)
    loop, t, receipts, github, _ = make_loop()
    loop.trusted_attestor = None
    with pytest.raises(q.TaskStop, match="pcp_local_trusted_attestor_not_installed"):
        asyncio.run(loop.preview_once())
    assert receipts.scans == github.calls == 0


def test_validated_preview_has_no_claim_or_execution(monkeypatch):
    flags(monkeypatch)
    loop, t, receipts, github, attestor = make_loop()
    report = asyncio.run(loop.preview_once())
    assert report["status"] == "PCP_LOCAL_SOURCE_VALIDATED_NOT_DISPATCHED"
    assert report["body_sha256"] == t.body_sha256
    assert report["job_id_if_authorized"] == worker.stable_job_id(t)
    assert report["can_start_agent"] is False
    assert report["can_claim_lease"] is False
    assert report["model_calls"] == 0
    assert "goal" not in report
    assert receipts.claims == 0 and github.calls == 1 and attestor.calls == 1


def test_empty_queue_does_not_access_github_or_evidence(monkeypatch):
    flags(monkeypatch)
    loop, _, receipts, github, attestor = make_loop()
    receipts.row = None
    assert asyncio.run(loop.preview_once()) == {
        "status": "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED", "model_calls": 0,
    }
    assert github.calls == attestor.calls == 0
    assert receipts.claims == 0


@pytest.mark.parametrize("changes", [
    {"author": "other"}, {"repository": "sonvhse06072/chonhac"},
    {"state": "closed"}, {"main_sha": "d" * 40},
    {"is_pull_request": True},
])
def test_foreign_or_stale_issue_never_claims(monkeypatch, changes):
    flags(monkeypatch)
    loop, _, receipts, github, attestor = make_loop(source_changes=changes)
    with pytest.raises(q.TaskStop):
        asyncio.run(loop.preview_once())
    assert receipts.claims == 0 and attestor.calls == 0


@pytest.mark.parametrize("changes", [
    {"isolation": {"agent_docker_socket": True}},
    {"isolation": {"workspace_lease_state": "busy"}},
    {"isolation": {"active_writers": 1}},
    {"project": {"repository": "sonvhse06072/chonhac"}},
    {"provider": {"github_token_in_agent": True}},
    {"provider": {"credential_scoped": False}},
    {"budget": {"owner_approved": False}},
    {"baseline": {"status": "draft"}},
])
def test_untrusted_evidence_never_claims(monkeypatch, changes):
    flags(monkeypatch)
    loop, _, receipts, _, _ = make_loop(evidence_changes=changes)
    with pytest.raises(q.TaskStop):
        asyncio.run(loop.preview_once())
    assert receipts.claims == 0


def test_preparation_rechecks_immutable_digest(monkeypatch):
    flags(monkeypatch)
    loop, t, receipts, github, attestor = make_loop()
    github.source["body"] += " edited"
    with pytest.raises(q.TaskStop, match="issue_body_digest_changed"):
        asyncio.run(loop.preview_once())
    assert receipts.claims == 0 and attestor.calls == 0


def test_execute_not_authorized_even_with_launcher(monkeypatch):
    flags(monkeypatch, live=False)
    launcher = Launcher()
    loop, _, receipts, github, _ = make_loop(launcher=launcher)
    with pytest.raises(q.TaskStop, match="pcp_local_live_activation_not_approved"):
        asyncio.run(loop.execute_once())
    assert receipts.scans == github.calls == launcher.calls == 0


def test_execute_no_launcher_denied_before_reads(monkeypatch):
    flags(monkeypatch, live=True)
    loop, _, receipts, github, _ = make_loop()
    with pytest.raises(q.TaskStop, match="pcp_local_durable_launcher_not_installed"):
        asyncio.run(loop.execute_once())
    assert receipts.scans == github.calls == 0


def test_claim_then_immutable_queued_ack_is_not_delivery(monkeypatch):
    flags(monkeypatch, live=True)
    launcher = Launcher()
    loop, t, receipts, github, _ = make_loop(launcher=launcher)
    result = asyncio.run(loop.execute_once())
    assert result == {
        "status": "PCP_LOCAL_CLAIMED_AWAITING_JOB_RECONCILIATION",
        "issue_number": 999, "job_id": worker.stable_job_id(t),
        "receipt_generation": 1, "source_commit": BASE,
        "model_execution_proof": "NOT_ATTESTED", "can_merge": False,
    }
    assert receipts.row["state"] == "claimed"
    assert receipts.claims == 1 and launcher.calls == 1
    assert asyncio.run(loop.execute_once()) == {
        "status": "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED", "model_calls": 0,
    }
    assert receipts.claims == 1 and launcher.calls == 1


def test_claim_race_denies_duplicate_launcher(monkeypatch):
    flags(monkeypatch, live=True)
    launcher = Launcher()
    loop, _, receipts, github, _ = make_loop(launcher=launcher)
    def race(*args, **kwargs):
        raise q.TaskStop("task_generation_or_identity_stale")
    receipts.advance = race
    with pytest.raises(q.TaskStop, match="task_generation_or_identity_stale"):
        asyncio.run(loop.execute_once())
    assert launcher.calls == 0


@pytest.mark.parametrize("mode,error", [
    ("raise", "pcp_local_launch_uncertain_do_not_retry"),
    ("wrong_id", "pcp_local_launch_ack_ambiguous_do_not_retry"),
])
def test_after_claim_uncertainty_is_not_retried(monkeypatch, mode, error):
    flags(monkeypatch, live=True)
    launcher = Launcher(mode=mode)
    loop, _, receipts, _, _ = make_loop(launcher=launcher)
    with pytest.raises(q.TaskStop, match=error):
        asyncio.run(loop.execute_once())
    assert receipts.row["state"] == "claimed"
    assert receipts.claims == 1 and launcher.calls == 1
    assert asyncio.run(loop.execute_once())["status"] == (
        "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED")
    assert launcher.calls == 1


def test_different_candidate_has_distinct_stable_job_id():
    from dataclasses import replace
    t, _, _, _ = fixture()
    assert worker.stable_job_id(t) == worker.stable_job_id(t)
    assert worker.stable_job_id(t) != worker.stable_job_id(
        replace(t, issue_number=1000))
    assert len(worker.stable_job_id(t)) == 32


@pytest.mark.parametrize("actual,expected", [
    (True, 1), ({"generation": True}, {"generation": 1}),
    ([1, True], [1, 1]), ({"state": "claimed", "extra": True}, {"state": "claimed"}),
])
def test_source_fingerprint_requires_exact_types_and_keys(actual, expected):
    assert not worker.exact_value(actual, expected)


def test_concrete_attestor_has_no_default_or_boolean_readers():
    with pytest.raises(q.TaskStop, match="trusted_readers_required"):
        worker.RuntimeTaskAttestor(issue_number=999, readers={})
    with pytest.raises(q.TaskStop, match="trusted_readers_required"):
        worker.RuntimeTaskAttestor(issue_number=999,
            readers={k: True for k in worker.OBSERVER_PARTS})


class ReadOnlyQuery:
    def __init__(self, result):
        self.result = result
        self.queries = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params=None):
        self.queries.append((statement, params))
        return self

    def fetchone(self):
        return self.result

    def commit(self):
        self.committed = True
        raise AssertionError("Readonly queue scan must not commit")


class ReadOnlyStorage:
    def __init__(self, result):
        self.db = ReadOnlyQuery(result)

    def connect(self):
        return self.db


def test_db_next_pending_reads_only_pcp_local():
    _, _, row, _ = fixture()
    db = ReadOnlyStorage(row)
    store = q.LocalSourceQueueStore(db)
    assert store.next_pending() == row
    assert len(db.db.queries) == 1
    sql, params = db.db.queries[0]
    assert "SELECT repository" in sql and "state='pending'" in sql
    assert "LIMIT 1" in sql and "ORDER BY created_at" in sql
    assert params == (q.REPOSITORY, q.PROJECT_ID)
    assert not db.db.committed


def test_db_next_pending_empty_remains_empty():
    db = ReadOnlyStorage(None)
    store = q.LocalSourceQueueStore(db)
    assert store.next_pending() is None
    assert not db.db.committed


@pytest.mark.parametrize("field,value,expected", [
    ("repository", "sonvhse06072/chonhac", "pending_receipt_identity_invalid"),
    ("project_id", "chonhac", "pending_receipt_identity_invalid"),
    ("issue_number", True, "pending_receipt_identity_invalid"),
    ("generation", True, "pending_receipt_identity_invalid"),
    ("generation", 1, "pending_receipt_identity_invalid"),
    ("job_id", "a" * 32, "pending_receipt_identity_invalid"),
    ("state", "claimed", "pending_receipt_identity_invalid"),
])
def test_db_pending_identity_mismatch_fails_closed(field, value, expected):
    _, _, row, _ = fixture()
    row[field] = value
    db = ReadOnlyStorage(row)
    with pytest.raises(q.TaskStop, match=expected):
        q.LocalSourceQueueStore(db).next_pending()
    assert not db.db.committed


def test_db_pending_rejects_unknown_fields():
    _, _, row, _ = fixture()
    row["provider_token"] = "secret"
    with pytest.raises(q.TaskStop, match="pending_receipt_shape_invalid"):
        q.LocalSourceQueueStore(ReadOnlyStorage(row)).next_pending()


def test_p1_after_claim_rechecks_exact_receipt_issue_and_attestor(monkeypatch):
    flags(monkeypatch, live=True)
    launcher = Launcher()
    loop, task, receipts, github, attestor = make_loop(launcher=launcher)
    result = asyncio.run(loop.execute_once())
    assert result["job_id"] == worker.stable_job_id(task)
    assert receipts.claims == receipts.rechecks == 1
    assert github.calls == 2
    assert attestor.calls == 2
    assert launcher.calls == 1


@pytest.mark.parametrize("mutation", [
    "main", "body", "claimed_job", "claimed_generation",
    "lease_busy", "model_effort", "provider_credentials", "revoke_flag",
])
def test_p1_drift_after_claim_never_reaches_launcher(monkeypatch, mutation):
    flags(monkeypatch, live=True)
    launcher = Launcher()
    loop, task, receipts, github, attestor = make_loop(launcher=launcher)

    def drift():
        if mutation == "main":
            github.source["main_sha"] = "d" * 40
        elif mutation == "body":
            github.source["body"] += "\nchanged post-claim"
        elif mutation == "claimed_job":
            receipts.row["job_id"] = "f" * 32
        elif mutation == "claimed_generation":
            receipts.row["generation"] = 2
        elif mutation == "lease_busy":
            attestor.evidence["isolation"]["workspace_lease_state"] = "busy"
        elif mutation == "model_effort":
            # Both efforts pass the standalone gate. The second snapshot
            # must still be IDENTICAL to the first independently observed one.
            attestor.evidence["provider"]["effort"] = "high"
        elif mutation == "provider_credentials":
            attestor.evidence["provider"]["credential_scoped"] = False
        elif mutation == "revoke_flag":
            monkeypatch.delenv("PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION", raising=False)

    receipts.on_claim = drift
    with pytest.raises(q.TaskStop, match="pcp_local_prelaunch_recheck_uncertain_do_not_retry"):
        asyncio.run(loop.execute_once())
    assert receipts.claims == 1
    assert receipts.row["state"] == "claimed"
    assert launcher.calls == 0
    if mutation == "revoke_flag":
        # Revoked operational consent must STOP before any queue read,
        # rather than acknowledge an idle queue as though still authorized.
        with pytest.raises(q.TaskStop, match="pcp_local_live_activation_not_approved"):
            asyncio.run(loop.execute_once())
    else:
        assert asyncio.run(loop.execute_once())["status"] == (
            "PCP_LOCAL_QUEUE_IDLE_NOT_DISPATCHED"
        )
    assert launcher.calls == 0


def test_p1_claimed_lookup_read_only_exact_binding():
    task, _, pending, _ = fixture()
    job_id = worker.stable_job_id(task)
    claimed = dict(pending, state="claimed", generation=1, job_id=job_id)
    db = ReadOnlyStorage(claimed)
    store = q.LocalSourceQueueStore(db)
    assert store.read_claimed(task, job_id=job_id) == claimed
    assert len(db.db.queries) == 1
    sql, args = db.db.queries[0]
    assert sql.lstrip().startswith("SELECT repository")
    assert "WHERE repository=%s AND project_id=%s AND issue_number=%s" in sql
    assert args == (q.REPOSITORY, q.PROJECT_ID, task.issue_number)
    assert db.db.committed is False


@pytest.mark.parametrize("changes", [
    {"state": "pending"},
    {"state": "delivered"},
    {"generation": 0},
    {"generation": True},
    {"job_id": "f" * 32},
    {"body_sha256": "f" * 64},
    {"baseline_revision": "not-approved"},
    {"allowed_paths": ["tests/test_pcp_light_other.py"]},
    {"project_id": "chonhac"},
])
def test_p1_claimed_lookup_wrong_identity_is_denied(changes):
    task, _, pending, _ = fixture()
    job_id = worker.stable_job_id(task)
    claimed = dict(pending, state="claimed", generation=1, job_id=job_id)
    claimed.update(changes)
    db = ReadOnlyStorage(claimed)
    with pytest.raises(q.TaskStop, match="pcp_local_claim_receipt_identity_changed"):
        q.LocalSourceQueueStore(db).read_claimed(task, job_id=job_id)
    assert db.db.committed is False


def test_p1_claimed_lookup_no_row_denied():
    task, _, _, _ = fixture()
    db = ReadOnlyStorage(None)
    with pytest.raises(q.TaskStop, match="pcp_local_claim_receipt_identity_changed"):
        q.LocalSourceQueueStore(db).read_claimed(
            task, job_id=worker.stable_job_id(task)
        )
