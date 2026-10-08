"""Fail-closed tests for the Owner-delegated PM-chat review trust boundary."""
from __future__ import annotations

import asyncio
import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import pm_chat_review
from app.pm_chat_review import (
    PMChatReviewService,
    PMChatReviewProof,
    PM_CHAT_REVIEW_MARKER,
    parse_pm_chat_review,
)
from app.pm_merge import evaluate_pm_merge
from test_pm_merge import context


SOURCE = "a" * 40
HEAD = "b" * 40
DIFF = "d" * 64


def report(**changes):
    data = {
        "schema_version": 1,
        "project_id": "default",
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "job_id": "job-12345678",
        "source_commit": SOURCE,
        "expected_head": HEAD,
        "diff_hash": DIFF,
        "branch": "ai/job-123456",
        "pr_number": 7,
        "checkpoint_id": 182,
        "checkpoint_key": "wo:blocked:key",
        "verdict": "pass",
        "summary": (
            "Examined the exact committed diff, accepted WorkOrder scope, "
            "authorization boundary, aggregate persistence, regression tests, "
            "and current CI evidence. No blocking findings were identified."
        ),
        "findings": [],
    }
    data.update(changes)
    return data


def review_body(**changes) -> str:
    return PM_CHAT_REVIEW_MARKER + "\n" + json.dumps(
        report(**changes), sort_keys=True, ensure_ascii=False,
    )


def proof(**changes) -> PMChatReviewProof:
    data = {
        "attestation_id": 91,
        "project_id": "default",
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "job_id": "job-12345678",
        "source_commit": SOURCE,
        "branch": "ai/job-123456",
        "expected_head": HEAD,
        "pr_number": 7,
        "checkpoint_id": 182,
        "checkpoint_key": "wo:blocked:key",
        "review_id": 45,
        "review_author": "owner",
        "review_body_sha256": hashlib.sha256(review_body().encode()).hexdigest(),
        "control_comment_id": 9001,
        "verdict": "pass",
    }
    data.update(changes)
    return PMChatReviewProof(**data)


def manual_context():
    project, plan, tracked, job, pr = deepcopy(context())
    job["result"]["route"]["strategy"]["review_policy"]["independence_satisfied"] = False
    job["result"]["diff"]["diff_hash"] = DIFF
    return project, plan, tracked, job, pr


def test_pm_chat_report_requires_structured_exact_bounded_protocol():
    assert parse_pm_chat_review(review_body()).verdict == "pass"
    for bad in (
        "",
        PM_CHAT_REVIEW_MARKER + "\nPASS",
        review_body() + "\n" + PM_CHAT_REVIEW_MARKER,
        review_body(verdict="pass", findings=["high: broken gate"]),
        review_body(verdict="fail", findings=[]),
        review_body(summary="not a substantive independent assessment"),
        review_body(diff_hash="e" * 63),
        review_body(extra_key="no"),
    ):
        with pytest.raises((ValueError, ValidationError)):
            parse_pm_chat_review(bad)
    assert parse_pm_chat_review(review_body(verdict="fail", findings=["high: issue"])).verdict == "fail"


def test_pm_merge_accepts_only_exact_manual_proof_and_preserves_protected_gates():
    project, plan, tracked, job, pr = manual_context()
    assert "required_review_independence_not_satisfied" in evaluate_pm_merge(
        project=project, plan=plan, tracked=tracked, job=job, pr=pr,
    ).blockers
    ok = evaluate_pm_merge(
        project=project, plan=plan, tracked=tracked, job=job, pr=pr,
        pm_chat_review_proof=proof(),
    )
    assert ok.eligible
    assert ok.evidence["pm_chat_review_mode"] == "pm_chat_manual_review"
    assert ok.evidence["pm_chat_review_attestation_id"] == 91
    assert ok.evidence["late_review_attestation_id"] is None
    for altered in (
        {"review_mode": "cross_provider"}, {"expected_head": "c" * 40},
        {"diff_hash": "e" * 64}, {"control_comment_id": 0},
        {"verdict": "fail"}, {"checkpoint_id": 0},
    ):
        denied = evaluate_pm_merge(
            project=project, plan=plan, tracked=tracked, job=job, pr=pr,
            pm_chat_review_proof=proof(**altered),
        )
        assert "required_review_independence_not_satisfied" in denied.blockers

    job = deepcopy(job)
    job["checkpoint"]["pending_decision"] = {"key": "owner-protected"}
    denied = evaluate_pm_merge(
        project=project, plan=plan, tracked=tracked, job=job, pr=pr,
        pm_chat_review_proof=proof(),
    )
    assert denied.requires_human
    assert "unresolved_job_human_decision" in denied.blockers

    job = deepcopy(manual_context()[3])
    job["repo_analysis"]["security_sensitive"] = True
    denied = evaluate_pm_merge(
        project=project, plan=plan, tracked=tracked, job=job, pr=pr,
        pm_chat_review_proof=proof(),
    )
    assert denied.requires_human
    assert "protected_change_without_matching_owner_approval" in denied.blockers

    project = deepcopy(project)
    project["autonomy"]["allow_pm_merge"] = False
    denied = evaluate_pm_merge(
        project=project, plan=plan, tracked=tracked,
        job=manual_context()[3], pr=pr, pm_chat_review_proof=proof(),
    )
    assert denied.manual_only and not denied.eligible


def test_github_review_provenance_rejects_wrong_account_head_state_or_repository():
    valid = {
        "project_id": "default", "repository": "acme/demo",
        "pr_number": 7, "id": 45, "state": "COMMENTED",
        "author": "owner", "commit_id": HEAD,
        "body": review_body(),
        "submitted_at": "2026-10-08T08:00:00Z",
        "html_url": "https://github.com/acme/demo/pull/7#pullrequestreview-45",
    }
    kwargs = {
        "project_id": "default", "repo": "acme/demo",
        "owner": "owner", "pr_number": 7,
        "review_id": 45, "expected_head": HEAD,
    }
    assert PMChatReviewService._review_identity(valid, **kwargs).verdict == "pass"
    for changes in (
        {"author": "bot"}, {"commit_id": SOURCE},
        {"state": "APPROVED"}, {"state": "DISMISSED"},
        {"repository": "attacker/other"}, {"pr_number": 8},
        {"id": 46}, {"id": "45"},
        {"submitted_at": None}, {"html_url": "https://attacker.invalid"},
    ):
        with pytest.raises(RuntimeError, match="provenance"):
            PMChatReviewService._review_identity({**valid, **changes}, **kwargs)


def test_capacity_requires_confirmed_router_no_eligible_and_no_higher_tier(monkeypatch):
    monkeypatch.setattr(pm_chat_review, "registered_review_capacity", lambda job: {
        "status": "registry_evaluated",
        "writer_providers": ["openai"],
        "strict_higher_tier_registry_model_ids": [],
    })
    status = {"value": "no_eligible_cross_provider_now"}

    async def inspect(**kwargs):
        return {"status": status["value"]}

    monkeypatch.setattr(pm_chat_review, "probe_reviewer_capacity", inspect)
    service = PMChatReviewService(
        SimpleNamespace(), SimpleNamespace(router=object()), SimpleNamespace(),
    )
    assert asyncio.run(service._capacity({})) == "no_eligible_cross_provider_now"
    for bad in ("eligible_cross_provider_at_probe", "staffing_unverifiable", "not_checked"):
        status["value"] = bad
        with pytest.raises(RuntimeError, match="not_verified"):
            asyncio.run(service._capacity({}))

    monkeypatch.setattr(pm_chat_review, "registered_review_capacity", lambda job: {
        "status": "registry_evaluated", "writer_providers": ["openai"],
        "strict_higher_tier_registry_model_ids": ["stronger-openai-model"],
    })
    with pytest.raises(RuntimeError, match="not_exhausted"):
        asyncio.run(service._capacity({}))


def test_control_must_be_from_configured_owner_and_canonical_issue(monkeypatch):
    monkeypatch.setattr(pm_chat_review, "bridge_project_config", lambda project_id: {
        "allowed_authors": ["owner", "pm-agent"],
        "pm_chat_review": {"enabled": True, "owner_author": "owner"},
    })
    service = PMChatReviewService(SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
    service.control_events = SimpleNamespace(get=lambda project_id, comment_id: {
        "author": "owner", "comment_id": 15, "issue_number": 63,
        "repository": "acme/demo", "body_sha256": "a" * 64,
    })
    assert service._owner_author("default") == "owner"
    assert service._control(
        project_id="default", comment_id=15, issue_number=63, owner="owner",
    )["author"] == "owner"
    with pytest.raises(RuntimeError, match="not_authorized"):
        service._control(
            project_id="default", comment_id=15, issue_number=5, owner="owner",
        )
    with pytest.raises(RuntimeError, match="not_authorized"):
        service._control(
            project_id="default", comment_id=16, issue_number=63, owner="owner",
        )
    monkeypatch.setattr(pm_chat_review, "bridge_project_config", lambda project_id: {
        "allowed_authors": ["owner"],
        "pm_chat_review": {"enabled": False, "owner_author": "owner"},
    })
    with pytest.raises(RuntimeError, match="not_owner_authorized"):
        service._owner_author("default")


def test_existing_live_review_body_change_invalidates_proof():
    async def altered(**kwargs):
        review = {"body": review_body(summary="This substantial, updated review is changed and cannot reuse the original signed attestation."), }
        return review, parse_pm_chat_review(review["body"])
    service = PMChatReviewService(SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
    service._github_review = altered
    with pytest.raises(RuntimeError, match="changed"):
        asyncio.run(service.verify_live(proof(), "acme/demo"))


def test_manual_proof_storage_rejects_tampering_without_any_model_execution(monkeypatch):
    payload = {
        **proof().__dict__,
        "review_submitted_at": "2026-10-08T08:00:00Z",
        "review_url": "https://github.com/acme/demo/pull/7#pullrequestreview-45",
        "control_body_sha256": "f" * 64,
        "capacity_status": "no_eligible_cross_provider_now",
        "finding_count": 0,
        "report_sha256": "e" * 64,
    }
    row = {
        "id": payload["attestation_id"],
        "project_id": payload["project_id"], "plan_id": payload["plan_id"],
        "work_order_id": payload["work_order_id"], "job_id": payload["job_id"],
        "expected_head": payload["expected_head"],
        "checkpoint_id": payload["checkpoint_id"],
        "pr_number": payload["pr_number"],
        "review_id": payload["review_id"],
        "control_comment_id": payload["control_comment_id"],
        "payload": payload,
    }
    service = PMChatReviewService(SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
    service.store = SimpleNamespace(get=lambda attestation_id: row)
    monkeypatch.setattr(service, "_owner_author", lambda project_id: "owner")
    _, plan, tracked, job, _ = manual_context()
    accepted = service.trusted_proof(
        plan=plan, tracked=tracked, job=job,
        attestation_id=91, checkpoint_id=182, checkpoint_key="wo:blocked:key",
    )
    assert accepted is not None and accepted.review_mode == "pm_chat_manual_review"
    row["payload"] = {**payload, "verdict": "fail"}
    with pytest.raises(RuntimeError, match="identity_invalid"):
        service.trusted_proof(
            plan=plan, tracked=tracked, job=job,
            attestation_id=91, checkpoint_id=182, checkpoint_key="wo:blocked:key",
        )


def test_pm_control_contract_rejects_spoofed_attestation_and_wrong_action_fields():
    from app.pm_control import PMControlEnvelope

    identity = {
        "schema_version": 1, "project_id": "default", "plan_id": "plan-1",
        "work_order_id": "WO-1", "job_id": "job-12345678",
        "source_commit": SOURCE, "expected_head": HEAD,
        "branch": "ai/job-123456", "pr_number": 7,
        "checkpoint_id": 182, "checkpoint_key": "wo:blocked:key",
    }
    recorded = PMControlEnvelope.model_validate({
        **identity, "action": "record_pm_chat_review", "review_id": 45,
    })
    assert recorded.review_id == 45 and recorded.attestation_id is None
    released = PMControlEnvelope.model_validate({
        **identity, "action": "release_pm_chat_review", "attestation_id": 91,
    })
    assert released.attestation_id == 91 and released.review_id is None
    for bad in (
        {**identity, "action": "record_pm_chat_review"},
        {**identity, "action": "record_pm_chat_review", "review_id": 45, "attestation_id": 91},
        {**identity, "action": "release_pm_chat_review", "review_id": 45, "attestation_id": 91},
        {**identity, "action": "release_pm_chat_review"},
        {**identity, "action": "request_diagnostics", "review_id": 45, "diagnostic_collectors": ["job"]},
    ):
        with pytest.raises(ValidationError):
            PMControlEnvelope.model_validate(bad)


def _manual_service_fixture(monkeypatch):
    project, plan, tracked, job, pr = manual_context()
    plan["ticket_id"] = "GH-63"
    job["result"]["review"]["protocol_valid"] = True
    envelope = SimpleNamespace(**{
        "project_id": "default", "plan_id": "plan-1",
        "work_order_id": "WO-1", "job_id": "job-12345678",
        "source_commit": SOURCE, "expected_head": HEAD,
        "branch": "ai/job-123456", "pr_number": 7,
        "checkpoint_id": 182, "checkpoint_key": "wo:blocked:key",
        "review_id": 45, "attestation_id": 91,
    })
    repo = "acme/demo"
    review = {
        "project_id": "default", "repository": repo,
        "pr_number": 7, "id": 45, "state": "COMMENTED",
        "commit_id": HEAD, "author": "owner", "body": review_body(),
        "submitted_at": "2026-10-08T10:00:00Z",
        "html_url": "https://github.com/acme/demo/pull/7#pullrequestreview-45",
    }

    async def preflight(_envelope):
        return plan, tracked, job, {"pr": pr, "ci": {"state": "success", "commit": HEAD}}, "exact-diff"

    fake_orchestrator = SimpleNamespace(
        late_reviews=SimpleNamespace(_preflight=preflight),
        merge_audit=SimpleNamespace(get=lambda **kwargs: None),
    )
    service = PMChatReviewService(SimpleNamespace(), SimpleNamespace(), fake_orchestrator)
    monkeypatch.setattr(service, "_owner_author", lambda project_id: "owner")
    monkeypatch.setattr(service, "_control", lambda **kwargs: {
        "author": "owner", "repository": repo, "body_sha256": "a" * 64,
    })
    async def capacity(_job):
        return "no_eligible_cross_provider_now"
    monkeypatch.setattr(service, "_capacity", capacity)
    pr["repository"] = repo
    return service, envelope, project, plan, tracked, job, pr, review, fake_orchestrator


def test_record_fetches_real_github_review_and_keeps_same_checkpoint(monkeypatch):
    service, envelope, project, plan, tracked, job, pr, review, orch = _manual_service_fixture(monkeypatch)
    appended = []
    service.store = SimpleNamespace(append=lambda data: (appended.append(data), {"id": 91})[1])
    calls = []

    async def github_review(**kwargs):
        calls.append(kwargs)
        return review, parse_pm_chat_review(review["body"])
    service._github_review = github_review
    result = asyncio.run(service.record(envelope, comment_id=901, issue_number=63))
    assert result["status"] == "attested"
    assert result["attestation_id"] == 91
    assert len(calls) == 1 and calls[0]["expected_head"] == HEAD
    assert appended[0]["diff_hash"] == DIFF
    review["body"] = review_body(diff_hash="e" * 64)
    appended.clear()
    with pytest.raises(RuntimeError, match="report_identity_mismatch"):
        asyncio.run(service.record(envelope, comment_id=905, issue_number=63))
    assert appended == []
    review["body"] = review_body()
    assert appended[0]["review_mode"] == "pm_chat_manual_review"
    assert appended[0]["review_body_sha256"] == hashlib.sha256(review["body"].encode()).hexdigest()
    assert appended[0]["control_comment_id"] == 901
    assert tracked["state"] == "awaiting_merge"  # no transition or mutation at record

    # An unrelated issue cannot confer review authority.
    appended.clear()
    with pytest.raises(RuntimeError, match="canonical_ticket"):
        asyncio.run(service.record(envelope, comment_id=902, issue_number=99))
    assert appended == []


def test_release_rechecks_all_original_protected_gates_before_checkpoint(monkeypatch):
    service, envelope, project, plan, tracked, job, pr, review, orch = _manual_service_fixture(monkeypatch)
    monkeypatch.setattr(service, "trusted_proof", lambda **kwargs: proof())
    calls = {"transitions": [], "plans": []}
    async def live(_proof, _repo):
        return None
    monkeypatch.setattr(service, "verify_live", live)
    orch._checkpoint_transition = lambda tracked, **kwargs: (
        calls["transitions"].append(kwargs), {"id": 183},
    )[1]
    orch.store = SimpleNamespace(update_plan=lambda plan_id, **kwargs: calls["plans"].append((plan_id, kwargs)))
    monkeypatch.setattr(pm_chat_review, "project_config", lambda project_id: project)
    result = asyncio.run(service.release(envelope, comment_id=903, issue_number=63))
    assert result["review_mode"] == "pm_chat_manual_review"
    assert calls["transitions"][0]["kind"] == "pm_chat_review_released"
    assert calls["transitions"][0]["state"] == "awaiting_merge"
    assert calls["plans"] == [("plan-1", {"status": "waiting_merge"})]

    # Even a genuine PM-chat attestation may not override Human Owner signals.
    calls["transitions"].clear()
    job["checkpoint"]["pending_decision"] = {"key": "owner-protected"}
    with pytest.raises(RuntimeError, match="other_merge_gates"):
        asyncio.run(service.release(envelope, comment_id=904, issue_number=63))
    assert calls["transitions"] == []
