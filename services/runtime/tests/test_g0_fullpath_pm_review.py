"""Synthetic-only proof of F1d standalone PM review finalization.

No PostgreSQL, Docker, provider, GitHub network or other project touched.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import fullpath_pm_review as pm
from app import main
from app.fullpath_ci_deferred import WAITING_PM
from app.required_ci import FULLPATH_FIXTURE_REPO
from test_g0_fullpath_required_ci import ci_evidence


JOB = "1" * 32
SOURCE = "a" * 40
HEAD = "b" * 40
DIFF = "d" * 64
REVIEWER = "approved-owner"
CI_AT = "2026-10-10T10:00:00Z"
REVIEW_AT = "2026-10-10T10:01:00Z"


def request(**changes):
    values = {
        "source_commit": SOURCE,
        "expected_head": HEAD,
        "branch": "ai/fullpath-0123",
        "baseline_revision": "fullpath-v1",
        "pr_number": 42,
        "review_id": 7,
    }
    values.update(changes)
    return pm.FullpathPMReviewRequest(**values)


def report(**changes):
    values = {
        "schema_version": 1, "project_id": pm.PROJECT_ID,
        "job_id": JOB, "source_commit": SOURCE,
        "expected_head": HEAD, "branch": "ai/fullpath-0123",
        "baseline_revision": "fullpath-v1",
        "pr_number": 42, "ci_run_id": 101, "diff_hash": DIFF,
        "verdict": "pass",
        "summary": (
            "Checked the exact project baseline and delivered diff, reviewed "
            "the hosted Drupal tests and security boundary, inspected the "
            "source and confirmed no unresolved findings or protected changes."
        ),
        "findings": [],
    }
    values.update(changes)
    return values


def review_body(**changes):
    return pm.MARKER + "\n" + json.dumps(report(**changes), sort_keys=True)


def ci():
    d = ci_evidence()
    d["actions_runs"][0]["updated_at"] = CI_AT
    return d


def pr():
    return {
        "project_id": pm.PROJECT_ID, "repository": FULLPATH_FIXTURE_REPO,
        "number": 42, "state": "open", "merged": False,
        "head": HEAD, "head_ref": "ai/fullpath-0123",
        "base_ref": "benchmark/fullpath",
        "html_url": "https://github.com/" + FULLPATH_FIXTURE_REPO + "/pull/42",
    }


def gh_review(body=None):
    return {
        "project_id": pm.PROJECT_ID, "repository": FULLPATH_FIXTURE_REPO,
        "pr_number": 42, "id": 7,
        "state": "COMMENTED", "commit_id": HEAD,
        "author": REVIEWER, "submitted_at": REVIEW_AT,
        "body": review_body() if body is None else body,
        "html_url": "https://github.com/" + FULLPATH_FIXTURE_REPO
        + "/pull/42#pullrequestreview-7",
    }


def job():
    return {
        "id": JOB, "project_id": pm.PROJECT_ID,
        "status": "waiting_human", "source_commit": SOURCE,
        "branch": "ai/fullpath-0123", "workspace": "/fullpath/workspaces/" + JOB,
        "checkpoint": {
            "acceptance_phase": WAITING_PM,
            "project_baseline": {"revision": "fullpath-v1", "source_commit": SOURCE},
            "canonical_intake": {
                "mode": "direct", "bounded_direct": True,
                "decomposition_required": False,
            },
        },
        "progress": {
            "required_checks_passed": True, "tests_passed": True,
            "unexpected_scope": False, "test_runs": 0,
            "important_decision_flags": [],
        },
        "result": {
            "status": "accepted",
            "acceptance_phase": WAITING_PM,
            "delivery_finalized": False,
            "branch": "ai/fullpath-0123", "commit": HEAD,
            "verification": {
                "verification_mode": "hosted_ci",
                "passed": True, "tests_passed": True,
                "hosted_ci_passed": True, "hosted_ci_pending": False,
                "hosted_ci_commit": HEAD,
                "local_tests_executed": False, "test_runs": 0,
            },
            "review": {"verdict": "pass", "protocol_valid": True,
                       "findings": []},
            "diff": {"diff_hash": DIFF, "changed_files": [
                "web/modules/custom/pcp_g0_fixture/src/EventLabelNormalizer.php",
            ]},
            "route": {"strategy": {
                "permissions": {
                    "commit": True, "push_ai_branch": True, "create_pr": True,
                },
                "human_decision": {"required": False},
            }},
            "pm_evidence": {"unresolved_risks": [],
                            "protected_decision_flags": []},
            "delivery": {
                "state": "ci_success", "ci": ci(),
                "pull_request": {
                    "number": 42, "repository": FULLPATH_FIXTURE_REPO,
                    "head": HEAD, "head_ref": "ai/fullpath-0123",
                    "base_ref": "benchmark/fullpath", "merged": False,
                },
            },
        },
    }


def fake_project():
    return {
        "base_branch": "benchmark/fullpath",
        "runtime": {"workspace_mode": "isolated_clone"},
        "ddev": {"enabled": False},
        "autonomy": {"allow_production_deploy": False},
        "pm_standalone_review": {
            "enabled": True, "reviewer_login": REVIEWER,
        },
    }


def approved_baseline():
    return SimpleNamespace(revision="fullpath-v1", source_commit=SOURCE)


def safe_env():
    return {
        **{k: v for k, v in pm.FIXED_ENV.items()
           if k != "PCP_RUNTIME_STARTUP_MODE"},
        "PCP_RUNTIME_STARTUP_MODE": "normal",
        "PCP_FULLPATH_PM_FINALIZATION_ENABLED": "owner-approved",
        "DATABASE_URL": "postgresql://fullpath:secret@fullpath-db:5432/fullpath",
    }


class Cursor:
    def __init__(self, row):
        self.row = deepcopy(row) if row is not None else None

    def fetchone(self):
        return deepcopy(self.row)


class Transaction:
    def __init__(self, storage):
        self.storage = storage
        self.commits = 0
        self.writes = []

    def __enter__(self):
        self.storage.lock_entries += 1
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.storage.queries.append(query)
        if "SELECT * FROM cp_jobs WHERE id=%s FOR UPDATE" in query:
            return Cursor(self.storage.row)
        if "UPDATE cp_jobs SET status='completed'" in query:
            if self.storage.row["status"] != "waiting_human":
                return Cursor(None)
            vals = params
            self.storage.row.update({
                "status": "completed",
                "result": json.loads(vals[0]),
                "checkpoint": json.loads(vals[1]),
                "progress": json.loads(vals[2]),
            })
            self.writes.append("completion")
            self.storage.writes.append("completion")
            return Cursor({"id": vals[-1]})
        if "INSERT INTO cp_job_events" in query:
            self.storage.writes.append("event")
            return Cursor(None)
        raise AssertionError("Unexpected SQL: " + query[:140])

    def commit(self):
        self.commits += 1
        self.storage.commits += 1


class MemoryDB:
    def __init__(self, row=None):
        self.row = deepcopy(row or job())
        self.queries = []
        self.writes = []
        self.commits = 0
        self.lock_entries = 0

    def get(self, job_id):
        assert job_id == JOB
        return deepcopy(self.row)

    def connect(self):
        return Transaction(self)


class FakeExecutor:
    def __init__(self, *, p=None, c=None, r=None):
        self.pr = deepcopy(pr() if p is None else p)
        self.ci = deepcopy(ci() if c is None else c)
        self.review = deepcopy(gh_review() if r is None else r)
        self.calls = []

    async def github_pull_request(self, **kwargs):
        self.calls.append("pr")
        return deepcopy(self.pr)

    async def github_ci(self, **kwargs):
        self.calls.append("ci")
        return deepcopy(self.ci)

    async def github_pull_request_review(self, **kwargs):
        self.calls.append("review")
        return deepcopy(self.review)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(pm.os.path, "exists", lambda path: False)
    monkeypatch.setattr(pm, "project_config", lambda project_id: fake_project())
    monkeypatch.setattr(pm, "resolve_project_baseline",
                        lambda project_id, revision: approved_baseline())
    return safe_env()


def test_pass_report_has_one_bounded_strict_marker():
    parsed = pm.parse_review_body(review_body())
    assert parsed.verdict == "pass"
    assert parsed.diff_hash == DIFF
    for value in (
        "", review_body() + pm.MARKER,
        "untrusted preface" + review_body(),
        pm.MARKER + "not JSON",
        review_body(extra="untrusted"),
        review_body(verdict="pass", findings=["critical"]),
        review_body(verdict="fail", findings=[]),
        review_body(expected_head="a"*40),
        review_body(summary="tiny"),
    ):
        if "expected_head" in value and '"expected_head": "a' in value:
            # A syntactically valid wrong SHA is rejected by binding, not parse.
            continue
        with pytest.raises((ValueError, ValidationError)):
            pm.parse_review_body(value)


@pytest.mark.parametrize("change", [
    lambda d: d.update({"PCP_RUNTIME_STARTUP_MODE": "g0_fullpath_candidate"}),
    lambda d: d.update({"DATABASE_URL": "postgresql://db:pw@db:5432/db"}),
    lambda d: d.update({"PCP_FULLPATH_PM_FINALIZATION_ENABLED": ""}),
    lambda d: d.update({"PROJECTS_FILE": "/config/projects.yml"}),
    lambda d: d.update({"CODEX_HOME": "/home/coder/.codex"}),
    lambda d: d.update({"ANTIGRAVITY_BRIDGE_URL": "http://localhost"}),
    lambda d: d.update({"PCP_G0_EXECUTION_ENABLED": "owner-approved"}),
])
def test_legacy_global_or_parked_runtime_rejected_without_db_touch(env, change):
    changed = deepcopy(env)
    change(changed)
    with pytest.raises(RuntimeError, match="not_authorized"):
        pm.require_isolated_review_environment(changed)


def test_only_owner_approved_new_fixture_can_finalize(env, monkeypatch):
    monkeypatch.setattr(
        pm, "project_config",
        lambda _: {**fake_project(),
                   "pm_standalone_review": {"enabled": True,
                                             "reviewer_login": "another-author"}},
    )
    service = pm.FullpathPMReviewService(MemoryDB(), FakeExecutor())
    with pytest.raises(RuntimeError, match="github_identity"):
        asyncio.run(service.finalize(JOB, request(), env=env))


@pytest.mark.parametrize("mutate", [
    lambda x: x.update({"status": "blocked"}),
    lambda x: x.update({"project_id": "chonhac"}),
    lambda x: x.update({"source_commit": "c"*40}),
    lambda x: x["checkpoint"].update({"pending_decision": {"key": "protected"}}),
    lambda x: x["checkpoint"].update({"orchestrator_launch": {"state": "held"}}),
    lambda x: x["checkpoint"].update({"work_order": {"id": "WO-1"}}),
    lambda x: x["checkpoint"]["canonical_intake"].update({"mode": "planning"}),
    lambda x: x["checkpoint"]["project_baseline"].update({"source_commit": "c"*40}),
    lambda x: x["progress"].update({"required_checks_passed": False}),
    lambda x: x["progress"].update({"unexpected_scope": True}),
    lambda x: x["progress"].update({"important_decision_flags": ["destructive_migration"]}),
    lambda x: x["result"].update({"acceptance_phase": "pending_hosted_ci"}),
    lambda x: x["result"].update({"delivery_finalized": True}),
    lambda x: x["result"]["verification"].update({"local_tests_executed": True}),
    lambda x: x["result"]["verification"].update({"hosted_ci_passed": False}),
    lambda x: x["result"]["review"].update({"verdict": "fail"}),
    lambda x: x["result"]["pm_evidence"].update({"unresolved_risks": ["material"]}),
    lambda x: x["result"]["route"]["strategy"].update(
        {"human_decision": {"required": True}}),
    lambda x: x["result"]["delivery"]["pull_request"].update({"head": "c"*40}),
])
def test_unverified_or_protected_job_never_reads_github_or_writes(env, mutate):
    db = MemoryDB()
    mutate(db.row)
    gh = FakeExecutor()
    service = pm.FullpathPMReviewService(db, gh)
    with pytest.raises(RuntimeError):
        asyncio.run(service.finalize(JOB, request(), env=env))
    assert db.writes == []
    assert gh.calls == []


@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"state": "closed"}),
    lambda d: d.update({"merged": True}),
    lambda d: d.update({"head": "a"*40}),
    lambda d: d.update({"head_ref": "ai/other"}),
    lambda d: d.update({"base_ref": "main"}),
    lambda d: d.update({"repository": "other/repo"}),
    lambda d: d.update({"html_url": "https://evil.invalid/pr"}),
])
def test_changed_pr_identity_prevents_completion(env, mutate):
    gh = FakeExecutor()
    mutate(gh.pr)
    db = MemoryDB()
    with pytest.raises(RuntimeError):
        asyncio.run(pm.FullpathPMReviewService(db, gh).finalize(
            JOB, request(), env=env))
    assert db.row["status"] == "waiting_human"
    assert db.writes == []


@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"state": "pending"}),
    lambda d: d.update({"commit": "a"*40}),
    lambda d: d["actions_runs"][0].update({"conclusion": "failure"}),
    lambda d: d["actions_runs"][0].update({"updated_at": None}),
])
def test_wrong_current_actions_ci_cannot_complete(env, mutate):
    gh = FakeExecutor()
    mutate(gh.ci)
    db = MemoryDB()
    with pytest.raises(RuntimeError):
        asyncio.run(pm.FullpathPMReviewService(db, gh).finalize(
            JOB, request(), env=env))
    assert db.writes == []


@pytest.mark.parametrize("mutate", [
    lambda d: d.update({"state": "DISMISSED"}),
    lambda d: d.update({"author": "unknown"}),
    lambda d: d.update({"commit_id": "a"*40}),
    lambda d: d.update({"id": 8}),
    lambda d: d.update({"submitted_at": CI_AT}),
    lambda d: d.update({"html_url": "https://evil.example/review"}),
    lambda d: d.update({"body": review_body(verdict="fail", findings=["critical"])}),
    lambda d: d.update({"body": review_body(expected_head="c"*40)}),
    lambda d: d.update({"body": review_body(ci_run_id=909)}),
    lambda d: d.update({"body": review_body(diff_hash="e"*64)}),
])
def test_invalid_live_pm_review_never_commits(env, mutate):
    gh = FakeExecutor()
    mutate(gh.review)
    db = MemoryDB()
    with pytest.raises((RuntimeError, ValidationError)):
        asyncio.run(pm.FullpathPMReviewService(db, gh).finalize(
            JOB, request(), env=env))
    assert db.writes == []


def test_exact_standalone_review_atomically_completes_after_ci(env):
    db = MemoryDB()
    gh = FakeExecutor()
    result = asyncio.run(pm.FullpathPMReviewService(db, gh).finalize(
        JOB, request(), env=env))
    assert result["status"] == "completed"
    assert result["idempotent_replay"] is False
    assert result["github_pr_merged"] is False
    assert db.row["status"] == "completed"
    assert db.row["result"]["acceptance_phase"] == pm.FINISHED
    assert db.row["result"]["delivery_finalized"] is True
    assert db.row["result"]["fullpath_pm_review"]["review_id"] == 7
    assert db.row["result"]["fullpath_pm_review"]["ci_run_id"] == 101
    assert db.row["result"]["verification"]["local_tests_executed"] is False
    assert db.row["result"]["verification"]["hosted_ci_passed"] is True
    assert db.row["checkpoint"]["fullpath_pm_review"]["receipt_sha256"] == result[
        "receipt_sha256"
    ]
    assert db.row["progress"]["pm_review_finalized"] is True
    assert db.writes == ["completion", "event"]
    assert db.commits == 1
    assert "FOR UPDATE" in db.queries[0]
    assert gh.calls == ["pr", "ci", "review"]


def test_duplicate_review_is_idempotent_without_new_writes(env):
    db = MemoryDB()
    gh = FakeExecutor()
    service = pm.FullpathPMReviewService(db, gh)
    first = asyncio.run(service.finalize(JOB, request(), env=env))
    second = asyncio.run(service.finalize(JOB, request(), env=env))
    assert second["idempotent_replay"] is True
    assert second["receipt_sha256"] == first["receipt_sha256"]
    assert db.writes == ["completion", "event"]
    assert db.commits == 1
    assert gh.calls == ["pr", "ci", "review", "pr", "ci", "review"]


def test_changed_review_after_completion_is_not_idempotent(env):
    db = MemoryDB()
    gh = FakeExecutor()
    service = pm.FullpathPMReviewService(db, gh)
    asyncio.run(service.finalize(JOB, request(), env=env))
    gh.review["body"] = review_body(summary="B" * 100)
    with pytest.raises(RuntimeError, match="receipt_conflict"):
        asyncio.run(service.finalize(JOB, request(), env=env))
    assert db.writes == ["completion", "event"]


def test_competing_review_cannot_complete_on_stale_job_snapshot(env):
    db = MemoryDB()
    gh = FakeExecutor()
    original_fetch = gh.github_pull_request_review
    async def tamper(**kwargs):
        db.row["progress"]["model_calls"] = 99
        return await original_fetch(**kwargs)
    gh.github_pull_request_review = tamper
    with pytest.raises(RuntimeError, match="job_changed_during_review"):
        asyncio.run(pm.FullpathPMReviewService(db, gh).finalize(
            JOB, request(), env=env))
    assert db.writes == []


def test_new_route_exposed_only_behind_existing_auth_and_parked_mode(monkeypatch):
    monkeypatch.setenv("PCP_RUNTIME_STARTUP_MODE", "g0_fullpath_candidate")
    monkeypatch.setenv("RUNTIME_API_TOKEN", "review-test-token")
    client = TestClient(main.app)
    try:
        assert client.post(
            f"/v1/g0-fullpath/jobs/{JOB}/pm-review",
            json=request().model_dump(),
            headers={"Authorization": "Bearer review-test-token"},
        ).status_code == 503
    finally:
        client.close()
