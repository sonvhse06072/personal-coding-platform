"""Default-OFF PCP-local source queue contract: no live GitHub/model/Docker."""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from app import pcp_local_task_queue as q

BASE = "a" * 40
BASELINE = "b" * 40
NUMBER = 888


def contract(**changes):
    x = {
        "version": 1, "key": "pcp-local-source-task",
        "base_sha": BASE,
        "goal": "Implement one isolated PCP source-only change and regression test.",
        "allowed_paths": [
            "scripts/pcp-light-sample.py", "tests/test_pcp_light_sample.py",
        ],
        "mode": "github_source_pr_only",
    }
    x.update(changes)
    return x


def source(body=None, **changes):
    if body is None:
        body = q.MARKER + "\n" + json.dumps(contract())
    row = {
        "project_id": "pcp-local", "repository": q.REPOSITORY,
        "number": NUMBER, "author": q.OWNER, "state": "open",
        "is_pull_request": False,
        "html_url": f"https://github.com/{q.REPOSITORY}/issues/{NUMBER}",
        "main_sha": BASE, "body": body,
    }
    row.update(changes)
    return row


def check(payload=None, *, digest=None, **overrides):
    payload = source() if payload is None else payload
    digest = digest if digest is not None else hashlib.sha256(
        payload["body"].encode()).hexdigest()
    return q.verify_issue(
        payload, issue_number=NUMBER, body_sha256=digest,
        base_sha=overrides.pop("base_sha", BASE),
        baseline_revision=overrides.pop("baseline_revision", "pcp-v1"),
        baseline_source_commit=overrides.pop("baseline_source_commit", BASELINE),
        **overrides,
    )


def test_positive_contract_is_not_dispatch_authority():
    task = check()
    assert task.repository == q.REPOSITORY
    assert task.project_id == "pcp-local"
    assert task.issue_number == NUMBER
    assert task.baseline_revision == "pcp-v1"
    assert task.baseline_source_commit == BASELINE
    out = task.status(created=True)
    assert out["status"] == "SOURCE_RECORDED_NOT_DISPATCHED"
    assert out["queue_state"] == "pending"
    assert out["worker_enabled"] is False
    assert out["model_calls"] == 0
    assert out["can_publish_or_merge"] is False
    assert "goal" not in out
    assert out["body_sha256"] == hashlib.sha256(source()["body"].encode()).hexdigest()


@pytest.mark.parametrize("changes", [
    {"author": "intruder"}, {"repository": "another/repo"},
    {"project_id": "chonhac"}, {"number": True},
    {"number": 889}, {"state": "closed"}, {"is_pull_request": True},
    {"html_url": "https://github.com/other/repo/issues/888"},
    {"main_sha": "c" * 40},
])
def test_foreign_issue_or_stale_main_denied(changes):
    with pytest.raises(q.TaskStop, match="github_identity_or_main_changed"):
        check(source(**changes))


@pytest.mark.parametrize("bad", [
    {"mode": "codex_run"}, {"version": True}, {"version": 2},
    {"key": "g1-old"}, {"key": "Bad Key"},
    {"base_sha": "c" * 40}, {"goal": "too short"},
    {"allowed_paths": ["scripts/pcp-light-hello.py"]},
    {"allowed_paths": ["scripts/pcp-light-ok.py", "config/models.yml"]},
    {"allowed_paths": ["scripts/pcp-light-ok.py",
                       "tests/test_pcp_light_sample.md"]},
    {"allowed_paths": ["scripts/pcp-light-ok.py",
                       "tests/test_pcp_light_sample.py",
                       "tests/test_pcp_light_sample.py"]},
    {"allowed_paths": ["scripts/pcp-light-ok.py",
                       "tests/test_pcp_light_sample.py",
                       "docs/pcp-light/../project/constitution.md"]},
    {"allowed_paths": ["scripts/pcp-light-remote-intake.py",
                       "tests/test_pcp_light_sample.py"]},
    {"allowed_paths": ["scripts/pcp-light-safe.py",
                       "tests/test_pcp_light_sample.py", "/etc/shadow"]},
])
def test_denied_task_fields_or_paths(bad):
    payload = source(body=q.MARKER + "\n" + json.dumps(contract(**bad)))
    with pytest.raises(q.TaskStop):
        check(payload)


def test_extra_secret_or_execution_switch_cannot_authorize():
    payload = source(body=q.MARKER + "\n" + json.dumps({
        **contract(), "model": "gpt-6-luna",
        "allow_merge": True, "github_token": "fake-secret",
    }))
    with pytest.raises(q.TaskStop, match="task_schema_invalid"):
        check(payload)


def test_duplicate_json_key_and_marker_denied():
    text = q.MARKER + '\n{"version":1,"version":1}'
    with pytest.raises(q.TaskStop, match="task_duplicate_json_key"):
        check(source(body=text))
    text = q.MARKER + "\n" + json.dumps(contract()) + "\n" + q.MARKER
    with pytest.raises(q.TaskStop, match="issue_body_or_marker_invalid"):
        check(source(body=text))


def test_digest_and_baseline_are_independent():
    s = source()
    with pytest.raises(q.TaskStop, match="issue_body_digest_changed"):
        check(s, digest="0" * 64)
    with pytest.raises(q.TaskStop, match="baseline_identity_invalid"):
        check(s, baseline_source_commit="bad")
    with pytest.raises(q.TaskStop, match="baseline_identity_invalid"):
        check(s, baseline_revision="../etc")
    with pytest.raises(q.TaskStop, match="base_sha_invalid"):
        check(s, base_sha="short")


def test_stale_body_digest_refuses_even_valid_edited_body():
    before = source()
    digest = hashlib.sha256(before["body"].encode()).hexdigest()
    updated = source(body=q.MARKER + "\n" + json.dumps(
        contract(goal="Another valid text which is not the previously accepted task.")))
    with pytest.raises(q.TaskStop, match="issue_body_digest_changed"):
        check(updated, digest=digest)


class Cursor:
    def __init__(self, record):
        self.record = record
    def fetchone(self):
        return self.record


class FakeDatabase:
    def __init__(self):
        self.receipts = {}
        self.task_keys = set()
        self.execute_count = 0
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        self.commits += 1

    def execute(self, sql, params=None):
        self.execute_count += 1
        s = sql.strip()
        if s.startswith("CREATE TABLE"):
            return Cursor(None)
        if s.startswith("INSERT INTO cp_pcp_local_source_receipts"):
            repository, num, project_id, key = params[:4]
            pk = (repository, num)
            if pk not in self.receipts and (project_id, key) not in self.task_keys:
                self.task_keys.add((project_id, key))
                self.receipts[pk] = {
                    "project_id": project_id, "task_key": key,
                    "body_sha256": params[4], "base_sha": params[5],
                    "baseline_revision": params[6],
                    "baseline_source_commit": params[7],
                    "goal_sha256": params[8],
                    "allowed_paths": json.loads(params[9]),
                    "state": "pending", "generation": 0, "job_id": None,
                }
                return Cursor({"issue_number": num})
            return Cursor(None)
        if s.startswith("SELECT project_id"):
            return Cursor(self.receipts.get(tuple(params)))
        if s.startswith("UPDATE cp_pcp_local_source_receipts"):
            target, job_id, repo, num = params[:4]
            row = self.receipts.get((repo, num))
            if (row is None or row["state"] != params[-3]
                    or row["generation"] != params[-2]
                    or row["job_id"] not in (None, params[-1])):
                return Cursor(None)
            row.update(state=target, generation=row["generation"] + 1)
            row["job_id"] = row["job_id"] or job_id
            return Cursor({k: row[k] for k in ("state", "generation", "job_id")})
        raise AssertionError("Unexpected SQL")


class FakeStorage:
    def __init__(self):
        self.db = FakeDatabase()
    def connect(self):
        return self.db


def test_one_issue_receipt_is_durable_and_repeat_is_idempotent():
    db = FakeStorage()
    store1 = q.LocalSourceQueueStore(db)
    store2 = q.LocalSourceQueueStore(db)
    t = check()
    assert store1.record(t) is True
    assert store2.record(t) is False
    assert len(db.db.receipts) == 1
    assert db.db.commits == 2
    assert db.db.receipts[(q.REPOSITORY, NUMBER)]["state"] == "pending"
    assert db.db.receipts[(q.REPOSITORY, NUMBER)]["job_id"] is None


def test_same_issue_changed_identity_is_not_reissued():
    from dataclasses import replace
    db = FakeStorage()
    store = q.LocalSourceQueueStore(db)
    task = check()
    assert store.record(task) is True
    changed = replace(task, body_sha256="b" * 64)
    with pytest.raises(q.TaskStop, match="existing_issue_receipt_mismatch"):
        store.record(changed)
    assert len(db.db.receipts) == 1


def test_reused_task_key_in_another_issue_is_not_a_new_job():
    from dataclasses import replace
    db = FakeStorage()
    store = q.LocalSourceQueueStore(db)
    task = check()
    assert store.record(task) is True
    other = replace(task, issue_number=NUMBER + 1)
    with pytest.raises(q.TaskStop, match="task_key_reused_or_missing"):
        store.record(other)
    assert len(db.db.receipts) == 1


def test_worker_flag_missing_denies_transitions(monkeypatch):
    monkeypatch.delenv("PCP_LOCAL_TASK_WORKER_ENABLED", raising=False)
    with pytest.raises(q.TaskStop, match="worker_activation_not_authorized"):
        q.validate_transition("pending", "claimed")
    with pytest.raises(q.TaskStop, match="worker_activation_not_authorized"):
        q.validate_transition("pending", "claimed", worker_authorized=True)
    monkeypatch.setenv("PCP_LOCAL_TASK_WORKER_ENABLED", "malformed")
    with pytest.raises(q.TaskStop, match="worker_activation_not_authorized"):
        q.validate_transition("pending", "claimed", worker_authorized=True)


@pytest.mark.parametrize("current,target", [
    ("pending", "running"), ("claimed", "delivered"),
    ("delivered", "pending"), ("blocked", "claimed"),
    ("running", "pending"), ("invalid", "claimed"),
])
def test_invalid_future_worker_transitions_still_denied(monkeypatch, current, target):
    monkeypatch.setenv("PCP_LOCAL_TASK_WORKER_ENABLED", "owner-approved")
    with pytest.raises(q.TaskStop, match="task_transition_denied"):
        q.validate_transition(current, target, worker_authorized=True)


def test_generation_cas_only_in_independently_admitted_worker(monkeypatch):
    monkeypatch.setenv("PCP_LOCAL_TASK_WORKER_ENABLED", "owner-approved")
    store = q.LocalSourceQueueStore(FakeStorage())
    task = check()
    store.record(task)
    job_id = "c" * 32
    assert store.advance(
        task, expected_state="pending", expected_generation=0,
        target_state="claimed", job_id=job_id, worker_authorized=True,
    ) == {"state": "claimed", "generation": 1, "job_id": job_id}
    with pytest.raises(q.TaskStop, match="task_generation_or_identity_stale"):
        store.advance(
            task, expected_state="pending", expected_generation=0,
            target_state="claimed", job_id=job_id, worker_authorized=True,
        )


def test_job_identity_cannot_swap_after_claim(monkeypatch):
    monkeypatch.setenv("PCP_LOCAL_TASK_WORKER_ENABLED", "owner-approved")
    store = q.LocalSourceQueueStore(FakeStorage())
    task = check()
    store.record(task)
    first = "c" * 32
    store.advance(task, expected_state="pending", expected_generation=0,
                  target_state="claimed", job_id=first, worker_authorized=True)
    with pytest.raises(q.TaskStop, match="task_generation_or_identity_stale"):
        store.advance(task, expected_state="claimed", expected_generation=1,
                      target_state="running", job_id="d" * 32,
                      worker_authorized=True)
    assert store.advance(task, expected_state="claimed", expected_generation=1,
                         target_state="running", job_id=first,
                         worker_authorized=True) == {
        "state": "running", "generation": 2, "job_id": first,
    }
