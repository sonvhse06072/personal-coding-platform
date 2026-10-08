from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import pm_late_review
from app.adapters.base import AgentRun
from app.pm_control import PMControlEnvelope
from app.pm_late_review import LateReviewService, accepted_diff, writer_providers
from app.pm_merge import LateReviewProof, evaluate_pm_merge
from test_pm_merge import context


def _attempt(iteration: int, provider: str = "openai") -> dict:
    return {
        "iteration": iteration, "provider": provider,
        "model": f"{provider}-model", "adapter": "codex_cli",
        "returncode": 0,
    }


def test_writer_provider_provenance_must_cover_every_coding_turn():
    job = {"progress": {"iteration": 2, "agent_attempts": [
        _attempt(1, "openai"), _attempt(2, "google"),
    ]}}
    assert writer_providers(job) == ("google", "openai")

    for attempts in (
        [_attempt(2)],  # truncated history
        [_attempt(1), _attempt(1)],  # missing iteration
        [_attempt(1), {**_attempt(2), "provider": ""}],
        [_attempt(1), {**_attempt(2), "model": ""}],
        [_attempt(1), {**_attempt(2), "returncode": None}],
    ):
        with pytest.raises(RuntimeError, match="history_incomplete"):
            writer_providers({"progress": {"iteration": 2, "agent_attempts": attempts}})


def _proof(values):
    _, plan, tracked, job, _ = values
    job["result"]["diff"]["diff_hash"] = "d" * 64
    job["route"]["strategy"]["review_policy"]["independence_satisfied"] = False
    job["result"]["route"]["strategy"]["review_policy"]["independence_satisfied"] = False
    return LateReviewProof(
        attestation_id=77, plan_id=plan["plan_id"],
        work_order_id=tracked["work_order_id"], job_id=job["id"],
        source_commit=job["source_commit"], branch=job["branch"],
        expected_head=job["result"]["commit"], pr_number=tracked["pr_number"],
        diff_hash=job["result"]["diff"]["diff_hash"],
        checkpoint_id=182, checkpoint_key="blocked:exact",
        writer_providers=("openai",), reviewer_provider="google",
        reviewer_model="model-review", verdict="pass",
    )


def _eligibility(values, proof=None):
    project, plan, tracked, job, pr = values
    return evaluate_pm_merge(
        project=project, plan=plan, tracked=tracked, job=job, pr=pr,
        late_review_proof=proof,
    )


def test_late_review_requires_exact_trusted_different_provider_pass():
    values = list(context())
    proof = _proof(values)
    denied = _eligibility(values)
    assert denied.eligible is False
    assert "required_review_independence_not_satisfied" in denied.blockers
    assert _eligibility(values, proof).eligible is True

    for field, value in (
        ("reviewer_provider", "openai"),
        ("verdict", "fail"),
        ("expected_head", "c" * 40),
        ("source_commit", "c" * 40),
        ("diff_hash", "a" * 64),
        ("checkpoint_id", 0),
        ("job_id", "wrong-job"),
        ("pr_number", 123),
        ("writer_providers", ()),
    ):
        bad = LateReviewProof(**{**proof.__dict__, field: value})
        assert "required_review_independence_not_satisfied" in _eligibility(values, bad).blockers
    changed = deepcopy(values)
    changed[3]["result"]["commit"] = "c" * 40
    assert _eligibility(changed, proof).eligible is False


def test_late_review_does_not_waive_protected_human_decisions():
    values = list(context())
    proof = _proof(values)
    values[3]["checkpoint"]["pending_decision"] = {"key": "owner-needed"}
    status = _eligibility(values, proof)
    assert not status.eligible
    assert status.requires_human
    assert "unresolved_job_human_decision" in status.blockers


def _envelope(action="request_late_independent_review", **overrides):
    fields = {
        "schema_version": 1, "project_id": "default", "action": action,
        "plan_id": "plan-1", "work_order_id": "WO-1",
        "job_id": "job-12345678", "source_commit": "a" * 40,
        "expected_head": "b" * 40, "branch": "ai/job-123456",
        "pr_number": 7, "checkpoint_id": 182, "checkpoint_key": "blocked:exact",
    }
    fields.update(overrides)
    return PMControlEnvelope.model_validate(fields)


def test_late_review_controls_reject_missing_or_untrusted_identity():
    _envelope()
    _envelope("release_late_independent_review", attestation_id=77)
    with pytest.raises(ValidationError):
        _envelope("release_late_independent_review")
    with pytest.raises(ValidationError):
        _envelope("request_late_independent_review", attestation_id=77)
    with pytest.raises(ValidationError):
        _envelope("request_late_independent_review", checkpoint_key=None)
    with pytest.raises(ValidationError):
        _envelope("request_diagnostics", attestation_id=77,
                  diagnostic_collectors=["job"])


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL,
    ).decode().strip()


def _repo(tmp_path: Path):
    repo = tmp_path / "preserved"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "tests@example.test")
    _git(repo, "config", "user.name", "Tests")
    (repo / "example.txt").write_text("original\n")
    _git(repo, "add", "example.txt")
    _git(repo, "commit", "-qm", "base")
    source = _git(repo, "rev-parse", "HEAD")
    (repo / "example.txt").write_text("review this exact diff\n")
    _git(repo, "add", "example.txt")
    _git(repo, "commit", "-qm", "delivered")
    head = _git(repo, "rev-parse", "HEAD")
    binary = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "--binary", source, head],
    )
    return repo, source, head, hashlib.sha256(binary).hexdigest()


def test_exact_commit_diff_matches_persisted_hash_or_fails_closed(tmp_path):
    repo, source, head, digest = _repo(tmp_path)
    job = {
        "workspace": str(repo), "source_commit": source,
        "result": {"commit": head, "diff": {"diff_hash": digest}},
    }
    assert "review this exact diff" in accepted_diff(job, tmp_path)
    job["result"]["diff"]["diff_hash"] = "0" * 64
    with pytest.raises(RuntimeError, match="accepted_diff_mismatch"):
        accepted_diff(job, tmp_path)
    job["result"]["diff"]["diff_hash"] = digest
    job["workspace"] = str(tmp_path.parent)
    with pytest.raises(RuntimeError, match="exact_diff_unavailable"):
        accepted_diff(job, tmp_path)


class _FakeLedger:
    def __init__(self, *, created=True):
        self.created = created
        self.calls = []
        self.saved = None

    def find(self, identity):
        self.calls.append(("find", dict(identity)))
        return {"id": 99, "status": "claimed"} if not self.created else None

    def claim(self, identity):
        self.calls.append(("claim", dict(identity)))
        return {"id": 99, "status": "claimed"}, self.created

    def finish(self, attempt_id, **kwargs):
        self.calls.append(("finish", kwargs["status"]))
        self.saved = kwargs
        return 120 if kwargs["attestation"] is not None else None


class _FakeAdapter:
    def __init__(self, output):
        self.output = output
        self.calls = []

    async def run(self, *, workspace, prompt, mode, timeout):
        self.calls.append({"workspace": workspace, "mode": mode, "timeout": timeout})
        assert mode == "evaluate"
        assert _git(workspace, "status", "--porcelain") == ""
        return AgentRun(
            adapter="fake", model="cross", returncode=0, output=self.output,
        )


class _FakeRouter:
    def __init__(self, choice):
        self.choice = choice
        self.calls = []

    async def staff(self, data):
        self.calls.append(data)
        return {
            "role": "reviewer",
            "request_id": data["request_id"],
            "choice": self.choice,
        }


def _service(tmp_path, monkeypatch, *, verdict="PASS", provider="google", created=True):
    repo, source, head, digest = _repo(tmp_path)
    job = {
        "workspace": str(repo), "project_id": "default",
        "source_commit": source, "branch": "ai/job-123456",
        "task": {"title": "Review bounded changes", "semantic": {}},
        "checkpoint": {"provider_state": {}, "work_order": {"id": "WO-1"}},
        "result": {
            "commit": head, "diff": {"diff_hash": digest},
            "verification": {"passed": True},
        },
    }
    choice = {
        "id": "cross", "model": "cross", "provider": provider,
        "adapter": "fake",
    }
    router = _FakeRouter(choice)
    engine = SimpleNamespace(router=router, workspace_root=tmp_path)
    service = LateReviewService(SimpleNamespace(), engine, SimpleNamespace())
    ledger = _FakeLedger(created=created)
    service.store = ledger

    envelope = _envelope(source_commit=source, expected_head=head)
    async def preflight(_envelope):
        return {}, {}, job, {"writers": ("openai",), "pr": {}, "ci": {}}, "diff"

    monkeypatch.setattr(service, "_preflight", preflight)
    monkeypatch.setattr(pm_late_review, "validate_model_choice", lambda x: None)
    output = (
        verdict + "\nREVIEW_JSON: " + json.dumps({
            "verdict": verdict.lower(), "summary": "Checked exact head",
            "findings": [], "jit_context_used": False,
        })
    )
    adapter = _FakeAdapter(output)
    monkeypatch.setattr(pm_late_review, "build_adapter", lambda *args: adapter)
    return service, ledger, router, adapter, envelope


async def _execute(service, envelope):
    received = await service.request(envelope)
    active = tuple(service._tasks)
    if active:
        completed = await asyncio.gather(*active)
        return received, completed[0]
    return received, received


def test_late_review_one_real_distinct_provider_pass_is_attested(tmp_path, monkeypatch):
    service, ledger, router, adapter, envelope = _service(tmp_path, monkeypatch)
    request, result = asyncio.run(_execute(service, envelope))
    assert request["status"] == "claimed"
    assert result["status"] == "passed"
    assert result["attestation_id"] == 120
    assert ledger.saved["attestation"]["expected_head"] == envelope.expected_head
    assert ledger.saved["attestation"]["reviewer_provider"] == "google"
    assert router.calls[0]["provider_state"]["provider:openai"]["available"] is False
    assert len(adapter.calls) == 1


def test_duplicate_late_review_claim_does_not_spend_model_call(tmp_path, monkeypatch):
    service, ledger, router, adapter, envelope = _service(tmp_path, monkeypatch, created=False)
    request, result = asyncio.run(_execute(service, envelope))
    assert result["replayed"] is True
    assert result["status"] == "claimed"
    assert router.calls == []
    assert adapter.calls == []


def test_same_provider_reviewer_never_invoked(tmp_path, monkeypatch):
    service, ledger, router, adapter, envelope = _service(
        tmp_path, monkeypatch, provider="openai",
    )
    request, result = asyncio.run(_execute(service, envelope))
    assert result["status"] == "no_capacity"
    assert ledger.saved is None
    assert not any(item[0] == "claim" for item in ledger.calls)
    assert adapter.calls == []


def test_late_review_structured_fail_and_contradictory_pass_are_not_attested(tmp_path, monkeypatch):
    service, ledger, router, adapter, envelope = _service(tmp_path, monkeypatch, verdict="FAIL")
    request, result = asyncio.run(_execute(service, envelope))
    assert result["status"] == "failed"
    assert ledger.saved["attestation"]["verdict"] == "fail"
    # A contradictory reviewer output cannot smuggle PASS through REVIEW_JSON.
    service2, ledger2, _, adapter2, envelope2 = _service(
        tmp_path / "next", monkeypatch, verdict="PASS",
    )
    adapter2.output = adapter2.output.replace("PASS\n", "FAIL\n", 1)
    request2, result2 = asyncio.run(_execute(service2, envelope2))
    assert result2["status"] == "uncertain"
    assert ledger2.saved["attestation"] is None


def test_snapshot_requires_exact_blocked_checkpoint_job_and_delivery():
    project, plan, tracked, job, pr = context()
    reason = "pm_merge_ineligible:required_review_independence_not_satisfied"
    plan.update({"status": "blocked", "lifecycle": "active"})
    tracked.update({"state": "blocked", "lifecycle": "active", "detail": {"reason": reason}})
    job["result"]["route"]["strategy"]["review_policy"]["independence_satisfied"] = False
    job["result"]["review"]["protocol_valid"] = True
    checkpoint = {
        "id": 182, "checkpoint_key": "blocked:exact", "state": "blocked",
        "kind": "blocked", "job_id": job["id"], "evidence": {"reason": reason},
    }
    class FakePlanStore:
        def orchestration(self, _id):
            return plan
        def work_orders(self, _id):
            return [tracked]
        def checkpoints(self, _id, **kwargs):
            return [checkpoint]
    class FakeJobStore:
        def get(self, _id):
            return job
        def get_execution_plan(self, _id):
            return {"plan": plan["plan"]}
    orch = SimpleNamespace(store=FakePlanStore())
    service = LateReviewService(FakeJobStore(), SimpleNamespace(), orch)
    envelope = _envelope()
    captured = service._snapshot(envelope)
    assert captured[1]["state"] == "blocked"
    assert captured[2]["id"] == job["id"]

    checkpoint["id"] = 183
    with pytest.raises(RuntimeError, match="checkpoint_stale"):
        service._snapshot(envelope)
    checkpoint["id"] = 182
    job["result"]["commit"] = "c" * 40
    with pytest.raises(RuntimeError, match="delivery_identity_changed"):
        service._snapshot(envelope)
    job["result"]["commit"] = "b" * 40
    tracked["detail"]["reason"] = "different_blocker"
    with pytest.raises(RuntimeError, match="work_order_identity_changed"):
        service._snapshot(envelope)


def test_release_checks_full_pm_gates_before_transition(monkeypatch):
    project, plan, tracked, job, pr = context()
    proof = _proof([project, plan, tracked, job, pr])
    tracked["state"] = "blocked"
    tracked["detail"] = {"reason": "pm_merge_ineligible:required_review_independence_not_satisfied"}
    decisions = []
    class FakeAudit:
        existing = None
        def get(self, **kwargs):
            return self.existing
    class FakePlanStore:
        def update_plan(self, plan_id, *, status):
            decisions.append(("plan", status))
    class FakeOrch:
        store = FakePlanStore()
        merge_audit = FakeAudit()
        def _checkpoint_transition(self, *args, **kwargs):
            decisions.append(("transition", kwargs["kind"]))
            return {"id": 301}
    orch = FakeOrch()
    service = LateReviewService(SimpleNamespace(), SimpleNamespace(), orch)
    async def preflight(envelope):
        return plan, tracked, job, {
            "writers": ("openai",), "pr": pr,
            "ci": {"state": "success", "commit": job["result"]["commit"]},
        }, "diff"
    monkeypatch.setattr(service, "_preflight", preflight)
    monkeypatch.setattr(service, "trusted_proof", lambda **kwargs: proof)
    monkeypatch.setattr(pm_late_review, "project_config", lambda project_id: project)
    envelope = _envelope("release_late_independent_review", attestation_id=77)
    response = asyncio.run(service.release(envelope))
    assert response["status"] == "released"
    assert decisions == [("transition", "late_review_released"), ("plan", "waiting_merge")]

    decisions.clear()
    orch.merge_audit.existing = {"status": "uncertain"}
    with pytest.raises(RuntimeError, match="merge_audit_replay_rejected"):
        asyncio.run(service.release(envelope))
    assert decisions == []

    orch.merge_audit.existing = None
    job["checkpoint"]["pending_decision"] = {"key": "owner-required"}
    with pytest.raises(RuntimeError, match="merge_gate_still_blocked"):
        asyncio.run(service.release(envelope))
    assert decisions == []
