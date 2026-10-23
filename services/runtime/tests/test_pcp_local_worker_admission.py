"""B2.2a local worker admission — pure negative gates, NO model/Docker/GitHub."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess

import pytest

from app import pcp_local_worker_admission as admission
from app import pcp_local_task_queue as queue


def sample_task():
    contract = {
        "version": 1,
        "key": "pcp-admission-sample",
        "base_sha": "a" * 40,
        "goal": "Implement one narrowly permitted PCP source-only change and test.",
        "allowed_paths": [
            "scripts/pcp-light-sample.py",
            "tests/test_pcp_light_sample.py",
        ],
        "mode": "github_source_pr_only",
    }
    body = queue.MARKER + "\n" + json.dumps(contract)
    issue = {
        "project_id": queue.PROJECT_ID,
        "repository": queue.REPOSITORY,
        "number": 111,
        "author": queue.OWNER,
        "state": "open",
        "is_pull_request": False,
        "html_url": "https://github.com/sonvhse06072/personal-coding-platform/issues/111",
        "main_sha": "a" * 40,
        "body": body,
    }
    return queue.verify_issue(
        issue,
        issue_number=111,
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        base_sha="a" * 40,
        baseline_revision="approved-pcp-v1",
        baseline_source_commit="b" * 40,
    )


def evidence():
    task = sample_task()
    receipt = {
        "repository": task.repository,
        "project_id": task.project_id,
        "issue_number": task.issue_number,
        "task_key": task.task_key,
        "body_sha256": task.body_sha256,
        "base_sha": task.base_sha,
        "baseline_revision": task.baseline_revision,
        "baseline_source_commit": task.baseline_source_commit,
        "goal_sha256": task.goal_sha256,
        "allowed_paths": list(task.allowed_paths),
        "state": "pending",
        "generation": 0,
        "job_id": None,
    }
    return {
        "task": task,
        "receipt": receipt,
        "project": {
            "project_id": "pcp-local",
            "repository": queue.REPOSITORY,
            "base_branch": "main",
            "registered": True,
            "allow_create_pr": True,
            "allow_production_deploy": False,
        },
        "baseline": {
            "project_id": "pcp-local",
            "revision": "approved-pcp-v1",
            "source_commit": "b" * 40,
            "active_revision": "approved-pcp-v1",
            "status": "approved",
        },
        "isolation": {
            "current_main_sha": "a" * 40,
            "source_repo_clean": True,
            "workspace_mode": "isolated_clone",
            "workspace_lease_state": "free",
            "active_writers": 0,
            "other_repo_mounts": False,
            "agent_docker_socket": False,
            "isolated_ddev_network": True,
        },
        "provider": {
            "adapter": "codex_cli",
            "model": "gpt-6-luna",
            "effort": "medium",
            "installed_cli_version": "0.160.0",
            "approved_cli_version": "0.160.0",
            "credential_scoped": True,
            "github_token_in_agent": False,
            "host_keyring_mounted": False,
            "provider_network_reviewed": True,
        },
        "budget": {
            "owner_approved": True,
            "provider_quota_verified": True,
            "model_calls": 1,
            "max_wall_seconds": 900,
            "max_changed_files": 2,
            "cash_ceiling_usd": 0.0,
        },
    }


def authorize(monkeypatch):
    monkeypatch.setenv("PCP_LOCAL_TASK_SOURCE_ENABLED", "owner-approved")
    monkeypatch.setenv("PCP_LOCAL_TASK_WORKER_ENABLED", "owner-approved")


def test_feature_flags_missing_deny_before_any_evidence(monkeypatch):
    monkeypatch.delenv("PCP_LOCAL_TASK_SOURCE_ENABLED", raising=False)
    monkeypatch.delenv("PCP_LOCAL_TASK_WORKER_ENABLED", raising=False)
    with pytest.raises(queue.TaskStop, match="worker_flags_not_authorized"):
        admission.check_worker_admission(None, receipt=None, project=None,
                                         baseline=None, isolation=None,
                                         provider=None, budget=None)


@pytest.mark.parametrize("source_flag,worker_flag", [
    ("", ""), ("owner-approved", ""),
    ("", "owner-approved"), ("true", "owner-approved"),
    ("owner-approved", "true"), ("ON", "ON"),
])
def test_partial_or_malformed_flags_deny(monkeypatch, source_flag, worker_flag):
    monkeypatch.setenv("PCP_LOCAL_TASK_SOURCE_ENABLED", source_flag)
    monkeypatch.setenv("PCP_LOCAL_TASK_WORKER_ENABLED", worker_flag)
    with pytest.raises(queue.TaskStop, match="worker_flags_not_authorized"):
        admission.check_worker_admission(**evidence())


def test_positive_is_evidence_only_never_agent_claim_or_merge(monkeypatch):
    authorize(monkeypatch)
    out = admission.check_worker_admission(**evidence())
    assert out["status"] == "ADMISSION_EVIDENCE_CHECKED_NOT_DISPATCHED"
    assert out["project_id"] == "pcp-local"
    assert out["repository"] == queue.REPOSITORY
    assert out["receipt_generation"] == 0
    assert out["requires_fresh_live_recheck"] is True
    assert out["can_start_agent"] is False
    assert out["can_claim_lease"] is False
    assert out["can_publish_or_merge"] is False
    assert out["model_calls_executed"] == 0
    assert out["model_calls_cap"] == 1
    assert "goal" not in out
    assert "credential" not in json.dumps(out).lower()
    assert "github_token" not in json.dumps(out).lower()


@pytest.mark.parametrize("field,value", [
    ("body_sha256", "f" * 64), ("issue_number", 112),
    ("repository", "sonvhse06072/chonhac"),
    ("project_id", "chonhac"), ("task_key", "reused"),
    ("base_sha", "f" * 40), ("baseline_revision", "other"),
    ("baseline_source_commit", "f" * 40),
    ("goal_sha256", "f" * 64),
    ("allowed_paths", ["scripts/pcp-light-sample.py", "tests/test_pcp_light_other.py"]),
    ("state", "claimed"), ("state", "delivered"),
    ("generation", 1), ("generation", True), ("job_id", "f" * 32),
])
def test_stale_or_forged_receipt_never_admitted(monkeypatch, field, value):
    authorize(monkeypatch)
    args = evidence()
    args["receipt"][field] = value
    with pytest.raises(queue.TaskStop, match="receipt_identity_or_generation_stale"):
        admission.check_worker_admission(**args)


@pytest.mark.parametrize("section", [
    "receipt", "project", "baseline", "isolation", "provider", "budget",
])
def test_extra_permission_or_secret_field_denied(monkeypatch, section):
    authorize(monkeypatch)
    args = evidence()
    args[section]["github_token"] = "fake-secret"
    with pytest.raises(queue.TaskStop, match="_shape_invalid"):
        admission.check_worker_admission(**args)


@pytest.mark.parametrize("field,value", [
    ("project_id", "chonhac"),
    ("repository", "sonvhse06072/other"),
    ("base_branch", "develop"),
    ("registered", False),
    ("registered", 1),
    ("allow_create_pr", False),
    ("allow_production_deploy", True),
])
def test_wrong_project_or_permission(monkeypatch, field, value):
    authorize(monkeypatch)
    args = evidence()
    args["project"][field] = value
    with pytest.raises(queue.TaskStop, match="project_authority_denied"):
        admission.check_worker_admission(**args)


@pytest.mark.parametrize("field,value", [
    ("project_id", "chonhac"), ("revision", "other"),
    ("source_commit", "d" * 40), ("active_revision", "other"),
    ("status", "draft"), ("status", None),
])
def test_baseline_mismatch_or_not_approved(monkeypatch, field, value):
    authorize(monkeypatch)
    args = evidence()
    args["baseline"][field] = value
    with pytest.raises(queue.TaskStop, match="baseline_not_active_or_drifted"):
        admission.check_worker_admission(**args)


@pytest.mark.parametrize("field,value", [
    ("current_main_sha", "d" * 40), ("source_repo_clean", False),
    ("workspace_mode", "direct"), ("workspace_lease_state", "busy"),
    ("active_writers", 1), ("active_writers", True),
    ("other_repo_mounts", True), ("agent_docker_socket", True),
    ("isolated_ddev_network", False),
])
def test_workspace_cross_project_or_stale_lease_denied(monkeypatch, field, value):
    authorize(monkeypatch)
    args = evidence()
    args["isolation"][field] = value
    with pytest.raises(queue.TaskStop, match="workspace_or_lease_not_attested"):
        admission.check_worker_admission(**args)


@pytest.mark.parametrize("field,value", [
    ("adapter", "antigravity_host"), ("model", "paid/unknown"),
    ("effort", "none"), ("effort", ["medium"]),
    ("installed_cli_version", "latest"),
    ("approved_cli_version", "0.169.0"),
    ("credential_scoped", False), ("github_token_in_agent", True),
    ("host_keyring_mounted", True), ("provider_network_reviewed", False),
])
def test_unapproved_model_or_privilege_denied(monkeypatch, field, value):
    authorize(monkeypatch)
    args = evidence()
    args["provider"][field] = value
    with pytest.raises(queue.TaskStop, match="provider_or_credential_not_attested"):
        admission.check_worker_admission(**args)


@pytest.mark.parametrize("field,value", [
    ("owner_approved", False), ("provider_quota_verified", False),
    ("model_calls", 0), ("model_calls", 3), ("model_calls", True),
    ("max_wall_seconds", 30), ("max_wall_seconds", 1800),
    ("max_changed_files", 99), ("cash_ceiling_usd", -0.1),
    ("cash_ceiling_usd", 6.0), ("cash_ceiling_usd", "free"),
])
def test_budget_without_owner_proof_or_out_of_bounds_denied(monkeypatch, field, value):
    authorize(monkeypatch)
    args = evidence()
    args["budget"][field] = value
    with pytest.raises(queue.TaskStop, match="budget_not_independently_approved"):
        admission.check_worker_admission(**args)


def test_preflight_does_not_call_subprocess_or_network(monkeypatch):
    authorize(monkeypatch)

    def nope(*a, **k):
        raise AssertionError("B2.2a must not invoke outside tools")

    monkeypatch.setattr(subprocess, "run", nope)
    assert admission.check_worker_admission(**evidence())["can_start_agent"] is False


def test_wrong_task_object_fails_closed(monkeypatch):
    authorize(monkeypatch)
    args = evidence()
    args["task"] = {"body_sha256": "a" * 64}
    with pytest.raises(queue.TaskStop, match="task_type_invalid"):
        admission.check_worker_admission(**args)
