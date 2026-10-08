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
from app.pm_late_review import LateReviewService, LateReviewStore, accepted_diff, writer_providers
from app.plan_orchestrator import PlanOrchestrator as CorePlanOrchestrator
from app.pm_merge import LateReviewProof, evaluate_pm_merge
from test_pm_merge import context


@pytest.fixture(autouse=True)
def registered_test_models(monkeypatch):
    """Use authoritative provider mappings, not mutable Router declarations."""
    monkeypatch.setattr(
        pm_late_review, "models_doc",
        lambda: {"models": {
            "openai-model": {
                "provider": "openai", "adapter": "codex_cli",
                "tier": "strong", "kind": "agent", "roles": ["executor"],
                "capabilities": {"review": 8},
            },
            "google-model": {
                "provider": "google", "adapter": "codex_cli",
                "tier": "balanced", "kind": "agent", "roles": ["executor"],
                "capabilities": {"review": 7},
            },
            "cross": {
                "provider": "google", "adapter": "fake",
                "tier": "strong", "kind": "agent", "roles": ["reviewer"],
                "capabilities": {"review": 8},
            },
            "upgraded": {
                "provider": "openai", "adapter": "fake",
                "tier": "premium", "kind": "agent", "roles": ["reviewer"],
                "capabilities": {"review": 9},
            },
            "weaker": {
                "provider": "openai", "adapter": "fake",
                "tier": "strong", "kind": "agent", "roles": ["reviewer"],
                "capabilities": {"review": 10},
            },
            "equal_review": {
                "provider": "openai", "adapter": "fake",
                "tier": "premium", "kind": "agent", "roles": ["reviewer"],
                "capabilities": {"review": 8},
            },
        }},
    )
    monkeypatch.setattr(
        pm_late_review, "routing_policy_doc",
        lambda: {"review_policy": {"late_review_recovery": {
            "same_provider_higher_tier_fallback_enabled": True,
        }}},
    )


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
    with pytest.raises(RuntimeError, match="provider_registry_mismatch"):
        writer_providers({"progress": {"iteration": 1, "agent_attempts": [
            {**_attempt(1), "provider": "google"},
        ]}})

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
        checkpoint_id=182, checkpoint_key="wo:blocked:exact",
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


def test_same_provider_proof_requires_strictly_higher_tier_and_review_strength():
    values = list(context())
    cross = _proof(values)
    upgraded = LateReviewProof(**{
        **cross.__dict__,
        "review_mode": "same_provider_higher_tier",
        "reviewer_provider": "openai",
        "reviewer_model": "upgraded",
        "writer_model_ids": ("openai-model",),
        "reviewer_tier_index": 3,
        "writer_max_tier_index": 2,
        "reviewer_review_score": 9,
        "writer_max_review_score": 8,
    })
    assert _eligibility(values, upgraded).eligible
    for field, value in (
        ("reviewer_tier_index", 2),
        ("reviewer_review_score", 8),
        ("reviewer_model", "openai-model"),
        ("reviewer_provider", "google"),
        ("writer_model_ids", ()),
        ("review_mode", "unverified"),
    ):
        fake = LateReviewProof(**{**upgraded.__dict__, field: value})
        assert "required_review_independence_not_satisfied" in _eligibility(
            values, fake,
        ).blockers


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
        "pr_number": 7, "checkpoint_id": 182, "checkpoint_key": "wo:blocked:exact",
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
    # repo.diff_state() stores the digest of repo._git()'s .strip()'d text,
    # not the digest of Git's raw stdout (which ends in a newline).
    canonical = binary.decode("utf-8").strip().encode("utf-8")
    assert binary.endswith(b"\n") and binary != canonical
    return repo, source, head, hashlib.sha256(canonical).hexdigest()


def test_exact_commit_diff_matches_persisted_hash_or_fails_closed(tmp_path):
    repo, source, head, digest = _repo(tmp_path)
    job = {
        "workspace": str(repo), "source_commit": source,
        "result": {"commit": head, "diff": {"diff_hash": digest}},
    }
    recovered = accepted_diff(job, tmp_path)
    assert "review this exact diff" in recovered
    assert not recovered.endswith("\n")
    raw = subprocess.check_output(
        ["git", "-C", str(repo), "diff", "--binary", source, head],
    )
    # Regression: raw stdout SHA-256 is not the accepted Runtime hash.
    assert hashlib.sha256(raw).hexdigest() != digest
    assert hashlib.sha256(raw.decode("utf-8").strip().encode()).hexdigest() == digest
    job["result"]["diff"]["diff_hash"] = "0" * 64
    with pytest.raises(RuntimeError, match="accepted_diff_mismatch"):
        accepted_diff(job, tmp_path)
    job["result"]["diff"]["diff_hash"] = digest
    job["workspace"] = str(tmp_path.parent)
    with pytest.raises(RuntimeError, match="exact_diff_unavailable"):
        accepted_diff(job, tmp_path)



def test_completed_direct_workspace_exact_diff_at_returned_main(tmp_path, monkeypatch):
    # The original coding job has finished, so direct checkout is back on the
    # source/main commit; the delivered head still exists in this Git database.
    repo, source, head, digest = _repo(tmp_path)
    isolated_root = tmp_path / "isolated"
    isolated_root.mkdir()
    job = {
        "project_id": "chonhac",
        "workspace": str(repo),
        "source_commit": source,
        "checkpoint": {"workspace_mode": "direct"},
        "result": {"commit": head, "diff": {"diff_hash": digest}},
    }
    monkeypatch.setattr(
        pm_late_review, "project_config",
        lambda project_id: {
            "path": str(repo),
            "runtime": {"workspace_mode": "direct"},
        },
    )
    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", str(repo))
    _git(repo, "checkout", "--detach", source)
    assert _git(repo, "rev-parse", "HEAD") == source
    assert "review this exact diff" in accepted_diff(job, isolated_root)
    assert _git(repo, "rev-parse", "HEAD") == source

    job["result"]["diff"]["diff_hash"] = "0" * 64
    with pytest.raises(RuntimeError, match="accepted_diff_mismatch"):
        accepted_diff(job, isolated_root)


def test_direct_workspace_requires_exact_mount_project_and_immutable_mode(tmp_path, monkeypatch):
    repo, source, head, digest = _repo(tmp_path)
    root = tmp_path / "isolated"
    root.mkdir()
    configured = {
        "path": str(repo),
        "runtime": {"workspace_mode": "direct"},
    }
    monkeypatch.setattr(pm_late_review, "project_config", lambda _id: configured)
    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", str(repo))
    job = {
        "project_id": "chonhac",
        "workspace": str(repo),
        "source_commit": source,
        "checkpoint": {"workspace_mode": "direct"},
        "result": {"commit": head, "diff": {"diff_hash": digest}},
    }
    assert "review this exact diff" in accepted_diff(job, root)

    # No generic exception for arbitrary absolute paths or a stale mount.
    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match="exact_diff_unavailable"):
        accepted_diff(job, root)
    monkeypatch.setenv("CODING_DIRECT_PROJECT_ROOT", str(repo))

    configured["path"] = str(tmp_path)
    with pytest.raises(RuntimeError, match="exact_diff_unavailable"):
        accepted_diff(job, root)
    configured["path"] = str(repo)

    configured["runtime"]["workspace_mode"] = "isolated_clone"
    with pytest.raises(RuntimeError, match="exact_diff_unavailable"):
        accepted_diff(job, root)
    configured["runtime"]["workspace_mode"] = "direct"

    job["checkpoint"]["workspace_mode"] = "isolated_clone"
    with pytest.raises(RuntimeError, match="exact_diff_unavailable"):
        accepted_diff(job, root)
    job["checkpoint"]["workspace_mode"] = "direct"

    job["result"]["diff"]["diff_truncated"] = True
    with pytest.raises(RuntimeError, match="exact_diff_unavailable"):
        accepted_diff(job, root)


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
        return 120 if kwargs.get("attestation") is not None else None


class _FakeAdapter:
    def __init__(self, output, model="cross"):
        self.output = output
        self.model = model
        self.calls = []

    async def run(self, *, workspace, prompt, mode, timeout):
        self.calls.append({"workspace": workspace, "mode": mode, "timeout": timeout})
        assert mode == "evaluate"
        assert _git(workspace, "status", "--porcelain") == ""
        return AgentRun(
            adapter="fake", model=self.model, returncode=0, output=self.output,
        )


class _FakeRouter:
    def __init__(
        self, choice, *, cross_unavailable=False, fallback_choice=None,
        cross_failure=None,
    ):
        self.choice = choice
        self.cross_unavailable = cross_unavailable
        self.fallback_choice = fallback_choice
        self.cross_failure = cross_failure
        self.calls = []

    async def staff(self, data):
        self.calls.append(data)
        if len(self.calls) == 1:
            if self.cross_failure:
                raise RuntimeError(self.cross_failure)
            if self.cross_unavailable:
                raise RuntimeError("No eligible model for role=reviewer; rejected={}")
        return {
            "role": "reviewer",
            "request_id": data["request_id"],
            "choice": (
                self.fallback_choice
                if len(self.calls) > 1 and self.fallback_choice is not None
                else self.choice
            ),
        }


def _service(
    tmp_path, monkeypatch, *, verdict="PASS", provider="google",
    created=True, cross_unavailable=False, fallback_choice=None,
    cross_failure=None,
):
    repo, source, head, digest = _repo(tmp_path)
    job = {
        "workspace": str(repo), "project_id": "default",
        "source_commit": source, "branch": "ai/job-123456",
        "task": {"title": "Review bounded changes", "semantic": {}},
        "progress": {
            "iteration": 1,
            "agent_attempts": [_attempt(1, "openai")],
        },
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
    router = _FakeRouter(
        choice, cross_unavailable=cross_unavailable,
        fallback_choice=fallback_choice, cross_failure=cross_failure,
    )
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
    adapter = _FakeAdapter(
        output, model=(
            str(fallback_choice.get("model") or "")
            if cross_unavailable and fallback_choice else "cross"
        ),
    )
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
    assert result["status"] == "staffing_error"
    assert ledger.saved is None
    assert not any(item[0] == "claim" for item in ledger.calls)
    assert adapter.calls == []


def test_same_provider_higher_tier_fallback_after_confirmed_no_cross_capacity(
    tmp_path, monkeypatch,
):
    upgraded = {
        "id": "upgraded", "provider": "openai",
        "model": "upgraded", "adapter": "fake",
    }
    service, ledger, router, adapter, envelope = _service(
        tmp_path, monkeypatch, cross_unavailable=True,
        fallback_choice=upgraded,
    )
    request, result = asyncio.run(_execute(service, envelope))
    assert request["review_mode"] == "same_provider_higher_tier"
    assert result["status"] == "passed"
    assert result["review_mode"] == "same_provider_higher_tier"
    assert result["reviewer_provider"] == "openai"
    assert ledger.saved["attestation"]["cross_provider_unavailable"] is True
    escalation = ledger.saved["attestation"]["escalation"]
    assert escalation["writer_model_ids"] == ["openai-model"]
    assert escalation["reviewer_tier_index"] > escalation["writer_max_tier_index"]
    assert escalation["reviewer_review_score"] > escalation["writer_max_review_score"]
    assert len(router.calls) == 2
    assert router.calls[0]["provider_state"]["provider:openai"]["available"] is False
    # At fallback time only models satisfying BOTH stronger constraints are eligible.
    assert router.calls[1]["provider_state"]["openai-model"]["available"] is False
    assert router.calls[1]["provider_state"]["weaker"]["available"] is False
    assert router.calls[1]["provider_state"]["equal_review"]["available"] is False
    assert len(adapter.calls) == 1
    assert len([x for x in ledger.calls if x[0] == "claim"]) == 1


@pytest.mark.parametrize("model_id", ["weaker", "equal_review", "openai-model"])
def test_fallback_rejects_non_stronger_model_without_model_call(
    tmp_path, monkeypatch, model_id,
):
    rejected = {
        "id": model_id, "provider": "openai",
        "model": model_id, "adapter": (
            "codex_cli" if model_id == "openai-model" else "fake"
        ),
    }
    service, ledger, router, adapter, envelope = _service(
        tmp_path, monkeypatch, cross_unavailable=True,
        fallback_choice=rejected,
    )
    request, result = asyncio.run(_execute(service, envelope))
    assert result["status"] == "staffing_error"
    assert ledger.saved is None
    assert adapter.calls == []
    assert len(router.calls) == 2
    assert not any(c[0] == "claim" for c in ledger.calls)


def test_network_or_untrusted_cross_staffing_never_enables_fallback(
    tmp_path, monkeypatch,
):
    service, ledger, router, adapter, envelope = _service(
        tmp_path, monkeypatch, cross_failure="Router temporarily unreachable",
    )
    request, result = asyncio.run(_execute(service, envelope))
    assert result["status"] == "staffing_error"
    assert len(router.calls) == 1
    assert ledger.saved is None
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
    assert ledger2.saved.get("attestation") is None


def test_snapshot_requires_exact_blocked_checkpoint_job_and_delivery():
    project, plan, tracked, job, pr = context()
    reason = "pm_merge_ineligible:required_review_independence_not_satisfied"
    plan.update({"status": "blocked", "lifecycle": "active"})
    plan["plan"]["work_orders"] = [{"id": "WO-1"}]
    tracked.update({"state": "blocked", "lifecycle": "active", "detail": {"reason": reason}})
    job["result"]["route"]["strategy"]["review_policy"]["independence_satisfied"] = False
    job["result"]["review"]["protocol_valid"] = True
    checkpoint = {
        "id": 182, "checkpoint_key": "wo:blocked:exact", "state": "blocked",
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
    tracked["detail"]["reason"] = reason
    plan["plan"]["work_orders"] = []
    with pytest.raises(RuntimeError, match="canonical_plan_missing"):
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



def test_release_transition_seals_attestation_in_immutable_checkpoint():
    _, _, tracked, job, pr = context()
    tracked["state"] = "blocked"
    captured = []
    class CaptureStore:
        def transition_work_order(self, **kwargs):
            captured.append(kwargs)
            return {"id": 301}
    facade = SimpleNamespace(
        storage=SimpleNamespace(get=lambda job_id: job),
        store=CaptureStore(),
    )
    release = {
        "attestation_id": 77,
        "checkpoint_id": 182,
        "checkpoint_key": "wo:blocked:exact",
        "head": job["result"]["commit"],
        "review_mode": "cross_provider",
    }
    CorePlanOrchestrator._checkpoint_transition(
        facade, tracked, kind="late_review_released",
        state="awaiting_merge", job=job, pr=pr,
        detail={"late_review_release": release},
    )
    proof = captured[0]["evidence"]["late_review_proof"]
    assert proof == {
        "review_mode": "cross_provider",
        "attestation_id": 77,
        "blocked_checkpoint_id": 182,
        "blocked_checkpoint_key": "wo:blocked:exact",
        "expected_head": job["result"]["commit"],
    }

    captured.clear()
    for invalid in (None, {}, {"attestation_id": 77}, {**release, "head": "c"}):
        with pytest.raises(RuntimeError, match="requires exact attested checkpoint"):
            CorePlanOrchestrator._checkpoint_transition(
                facade, tracked, kind="late_review_released",
                state="awaiting_merge", job=job, pr=pr,
                detail={"late_review_release": invalid},
            )
        assert not captured



def test_staffing_422_must_explicitly_prove_no_eligible_cross_provider():
    import httpx

    request = httpx.Request("POST", "http://router/v1/staff")
    no_model = httpx.Response(
        422, request=request,
        json={"detail": "No eligible model for role=reviewer; rejected={}"},
    )
    unavailable = httpx.Response(
        503, request=request, json={"detail": "Router unavailable"},
    )
    malformed = httpx.Response(
        422, request=request, json={"detail": "model registry invalid"},
    )
    assert pm_late_review._no_eligible_reviewer(
        httpx.HTTPStatusError("no reviewer", request=request, response=no_model),
    )
    assert not pm_late_review._no_eligible_reviewer(
        httpx.HTTPStatusError("backend unavailable", request=request, response=unavailable),
    )
    assert not pm_late_review._no_eligible_reviewer(
        httpx.HTTPStatusError("invalid policy", request=request, response=malformed),
    )


def test_no_stronger_reviewer_can_safely_recheck_capacity_without_claim(
    tmp_path, monkeypatch,
):
    base_registry = pm_late_review.models_doc()
    base_registry["models"].pop("upgraded")
    monkeypatch.setattr(pm_late_review, "models_doc", lambda: base_registry)
    service, ledger, router, adapter, envelope = _service(
        tmp_path, monkeypatch, cross_unavailable=True,
    )
    request, result = asyncio.run(_execute(service, envelope))
    assert result["status"] == "no_capacity"
    assert result["reason"] == "no_eligible_higher_tier_reviewer"
    assert len(router.calls) == 1
    assert adapter.calls == []
    assert ledger.saved is None
    assert not any(entry[0] == "claim" for entry in ledger.calls)


def test_immutable_fallback_attestation_is_rechecked_at_release(monkeypatch):
    project, plan, tracked, job, pr = context()
    job["progress"].update({
        "iteration": 1, "agent_attempts": [_attempt(1, "openai")],
    })
    job["checkpoint"]["executor_choice"] = {
        "id": "openai-model", "provider": "openai", "adapter": "codex_cli",
    }
    job["result"]["diff"]["diff_hash"] = "d" * 64
    job["result"]["route"]["strategy"]["review_policy"]["independence_satisfied"] = False

    reviewer = {"id": "upgraded", "provider": "openai", "adapter": "fake"}
    escalation = pm_late_review._escalated_reviewer_evidence(
        job, reviewer, ("openai",),
    )
    data = {
        "plan_id": plan["plan_id"],
        "work_order_id": tracked["work_order_id"],
        "job_id": job["id"],
        "source_commit": job["source_commit"],
        "branch": job["branch"],
        "expected_head": job["result"]["commit"],
        "pr_number": tracked["pr_number"],
        "diff_hash": job["result"]["diff"]["diff_hash"],
        "checkpoint_id": 182,
        "checkpoint_key": "wo:blocked:exact",
        "writer_providers": ["openai"],
        "reviewer_provider": "openai",
        "reviewer_model": "upgraded",
        "reviewer_adapter": "fake",
        "review_mode": "same_provider_higher_tier",
        "cross_provider_unavailable": True,
        "escalation": dict(escalation),
        "attempt_id": 90,
        "verdict": "pass",
        "protocol_valid": True,
    }
    attestation = {
        "id": 101,
        "attempt_id": 90,
        "payload": data,
        "status": "passed",
        **{
            field: data[field] for field in (
                "plan_id", "work_order_id", "job_id", "source_commit",
                "branch", "expected_head", "diff_hash", "pr_number",
                "checkpoint_id", "checkpoint_key",
                "reviewer_provider", "reviewer_model",
            )
        },
    }
    service = LateReviewService(SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
    service.store = SimpleNamespace(get_attestation=lambda attestation_id: attestation)
    kwargs = {
        "plan": plan, "tracked": tracked, "job": job,
        "attestation_id": 101,
        "checkpoint_id": 182, "checkpoint_key": "wo:blocked:exact",
    }
    proof = service.trusted_proof(**kwargs)
    assert proof is not None
    assert proof.review_mode == "same_provider_higher_tier"
    assert proof.reviewer_tier_index > proof.writer_max_tier_index
    assert _eligibility((project, plan, tracked, job, pr), proof).eligible is True

    data["escalation"]["reviewer_tier_index"] = 2
    with pytest.raises(RuntimeError, match="higher_tier_attestation_stale"):
        service.trusted_proof(**kwargs)
    data["escalation"]["reviewer_tier_index"] = escalation["reviewer_tier_index"]
    monkeypatch.setattr(
        pm_late_review, "routing_policy_doc",
        lambda: {"review_policy": {"late_review_recovery": {
            "same_provider_higher_tier_fallback_enabled": False,
        }}},
    )
    with pytest.raises(RuntimeError, match="fallback_policy_disabled"):
        service.trusted_proof(**kwargs)


def test_fallback_disabled_does_not_consume_a_model_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pm_late_review, "routing_policy_doc",
        lambda: {"review_policy": {"late_review_recovery": {
            "same_provider_higher_tier_fallback_enabled": False,
        }}},
    )
    service, ledger, router, adapter, envelope = _service(
        tmp_path, monkeypatch, cross_unavailable=True,
        fallback_choice={
            "id": "upgraded", "model": "upgraded",
            "provider": "openai", "adapter": "fake",
        },
    )
    _, result = asyncio.run(_execute(service, envelope))
    assert result["status"] == "no_capacity"
    assert len(router.calls) == 1
    assert adapter.calls == []
    assert ledger.saved is None



def test_orphan_claim_is_marked_uncertain_on_startup_without_replay(monkeypatch):
    class Connection:
        def __init__(self):
            self.statements = []
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, statement, args):
            self.statements.append((statement, args))
            return self

        def fetchall(self):
            return [{"id": 7}, {"id": 8}]

        def commit(self):
            self.committed = True

    conn = Connection()
    store = LateReviewStore(SimpleNamespace(connect=lambda: conn))
    monkeypatch.setattr(store, "ensure", lambda: None)
    assert store.reconcile_orphan_claims() == 2
    statement, _ = conn.statements[0]
    assert "status='uncertain'" in statement
    assert "WHERE status='claimed'" in statement
    assert "runtime_restarted_before_review_finalization" in statement
    assert conn.committed is True
