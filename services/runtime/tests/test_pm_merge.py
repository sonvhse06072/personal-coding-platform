from __future__ import annotations

from copy import deepcopy

from app.pm_merge import evaluate_pm_merge


HEAD = "b" * 40
SOURCE = "a" * 40


def context() -> tuple[dict, dict, dict, dict, dict]:
    project = {
        "base_branch": "main",
        "autonomy": {"allow_auto_merge_low_risk": True, "allow_production_deploy": False},
    }
    plan = {"plan_id": "plan-1", "project_id": "default", "plan": {"decision_boundaries": []}}
    tracked = {
        "plan_id": "plan-1",
        "work_order_id": "WO-1",
        "state": "awaiting_merge",
        "job_id": "job-12345678",
        "pr_number": 7,
    }
    route = {
        "strategy": {
            "human_decision": {"required": False, "triggers": []},
            "review_policy": {
                "required": True,
                "independent": True,
                "independence_satisfied": True,
                "conditional_on_strong_evidence": False,
            },
        }
    }
    job = {
        "id": "job-12345678",
        "project_id": "default",
        "status": "completed",
        "dry_run": False,
        "source_commit": SOURCE,
        "branch": "ai/job-123456",
        "task": {"title": "Bounded fix", "task_type": "bugfix", "flags": []},
        "repo_analysis": {
            "security_sensitive": False,
            "authentication_change": False,
            "authorization_change": False,
            "destructive_migration": False,
            "production_write": False,
        },
        "checkpoint": {
            "project_baseline": {
                "revision": "v1",
                "authority": [],
                "references": {},
            },
            "work_order": {
                "id": "WO-1",
                "risk": {"level": "standard", "flags": []},
            },
            "approved_decisions": [],
        },
        "route": route,
        "progress": {"required_checks_passed": True, "unexpected_scope": False},
        "result": {
            "status": "accepted",
            "commit": HEAD,
            "verification": {"passed": True},
            "review": {"verdict": "pass", "findings": []},
            "diff": {"diff_hash": "diff-1", "changed_files": []},
            "pm_evidence": {
                "outcome": "accepted",
                "unresolved_risks": [],
                "protected_decision_flags": [],
            },
            "route": route,
            "progress": {"required_checks_passed": True, "unexpected_scope": False},
            "delivery": {
                "state": "ci_success",
                "ci": {"state": "success", "commit": HEAD},
                "pull_request": {
                    "number": 7,
                    "head": HEAD,
                    "head_ref": "ai/job-123456",
                    "base_ref": "main",
                },
            },
            "delivery_finalized": True,
        },
    }
    pr = {
        "project_id": "default",
        "repository": "acme/demo",
        "number": 7,
        "state": "open",
        "merged": False,
        "head": HEAD,
        "head_ref": "ai/job-123456",
        "base_ref": "main",
    }
    return project, plan, tracked, job, pr


def evaluate(values):
    project, plan, tracked, job, pr = values
    return evaluate_pm_merge(project=project, plan=plan, tracked=tracked, job=job, pr=pr)


def test_low_risk_exact_green_evidence_is_pm_merge_eligible() -> None:
    result = evaluate(context())
    assert result.eligible is True
    assert result.manual_only is False
    assert result.requires_human is False
    assert result.blockers == ()
    assert result.expected_head == HEAD
    assert result.source_commit == SOURCE


def test_project_opt_out_preserves_manual_merge_gate() -> None:
    values = list(context())
    values[0] = deepcopy(values[0])
    values[0]["autonomy"]["allow_auto_merge_low_risk"] = False
    result = evaluate(tuple(values))
    assert result.eligible is False
    assert result.manual_only is True
    assert result.requires_human is False


def test_stale_pr_ci_or_required_review_fails_closed() -> None:
    values = list(context())
    values[4] = {**values[4], "head": "c" * 40}
    result = evaluate(tuple(values))
    assert "pull_request_head_mismatch" in result.blockers

    values = list(context())
    values[3] = deepcopy(values[3])
    values[3]["result"]["delivery"]["state"] = "ci_none"
    values[3]["result"]["delivery"]["ci"]["state"] = "none"
    result = evaluate(tuple(values))
    assert "ci_not_successful" in result.blockers

    values = list(context())
    values[3] = deepcopy(values[3])
    values[3]["result"]["review"]["verdict"] = "fail"
    result = evaluate(tuple(values))
    assert "required_independent_review_not_passed" in result.blockers


def test_protected_change_requires_matching_durable_owner_decision() -> None:
    values = list(context())
    values[3] = deepcopy(values[3])
    values[3]["repo_analysis"]["security_sensitive"] = True
    decision = {
        "required": True,
        "triggers": ["security_boundary_change"],
        "reason": "Security boundary",
    }
    values[3]["route"]["strategy"]["human_decision"] = decision
    values[3]["result"]["route"] = deepcopy(values[3]["route"])
    result = evaluate(tuple(values))
    assert result.eligible is False
    assert result.requires_human is True
    assert "protected_change_without_matching_owner_approval" in result.blockers

    values[3]["checkpoint"]["approved_decisions"] = ["security_boundary_change"]
    result = evaluate(tuple(values))
    assert result.eligible is True
    assert result.approved_protected_signals == ("security_boundary_change",)


def test_baseline_covered_security_authorization_can_satisfy_merge_gate() -> None:
    values = list(context())
    values[3] = deepcopy(values[3])
    values[3]["repo_analysis"]["security_sensitive"] = True
    values[3]["checkpoint"]["pm_baseline_covered_protected_authorizations"] = [
        {
            "diff_hash": "diff-1",
            "protected_signals": ["security_boundary_change"],
            "approved_by": "pm-model",
            "baseline_authority_refs": ["docs/24-mvp-completion-contract.md"],
            "review_verdict": "pass",
            "baseline_revision": "v1",
        }
    ]

    result = evaluate(tuple(values))
    assert result.eligible is True
    assert result.requires_human is False
    assert result.approved_protected_signals == ("security_boundary_change",)
    assert result.evidence[
        "baseline_covered_pm_authorized_protected_signals"
    ] == ["security_boundary_change"]


def test_baseline_covered_security_authorization_is_invalidated_by_diff_change() -> None:
    values = list(context())
    values[3] = deepcopy(values[3])
    values[3]["repo_analysis"]["security_sensitive"] = True
    values[3]["checkpoint"]["pm_baseline_covered_protected_authorizations"] = [
        {
            "diff_hash": "diff-old",
            "protected_signals": ["security_boundary_change"],
            "approved_by": "pm-model",
            "baseline_authority_refs": ["docs/24-mvp-completion-contract.md"],
            "review_verdict": "pass",
            "baseline_revision": "v1",
        }
    ]

    result = evaluate(tuple(values))
    assert result.eligible is False
    assert result.requires_human is True
    assert "protected_change_without_matching_owner_approval" in result.blockers


def test_high_risk_and_pending_decision_never_use_low_risk_auto_merge() -> None:
    values = list(context())
    values[3] = deepcopy(values[3])
    values[3]["checkpoint"]["work_order"]["risk"]["level"] = "high"
    result = evaluate(tuple(values))
    assert result.requires_human is True
    assert "work_order_risk_not_low" in result.blockers

    values = list(context())
    values[3] = deepcopy(values[3])
    values[3]["checkpoint"]["pending_decision"] = {"key": "x"}
    result = evaluate(tuple(values))
    assert result.requires_human is True
    assert "unresolved_job_human_decision" in result.blockers


def test_fast_review_may_skip_only_with_durable_strong_evidence_marker() -> None:
    values = list(context())
    values[3] = deepcopy(values[3])
    policy = values[3]["route"]["strategy"]["review_policy"]
    policy.update({"required": False, "conditional_on_strong_evidence": True})
    values[3]["result"]["route"] = deepcopy(values[3]["route"])
    values[3]["result"]["review"] = {"verdict": "skipped"}
    values[3]["result"]["progress"]["review_skipped_strong_evidence"] = 1
    result = evaluate(tuple(values))
    assert result.eligible is True

    values[3]["result"]["progress"]["review_skipped_strong_evidence"] = 0
    result = evaluate(tuple(values))
    assert "conditional_review_has_no_pass_or_strong_evidence_skip" in result.blockers
