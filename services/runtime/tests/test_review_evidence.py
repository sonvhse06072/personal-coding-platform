from __future__ import annotations

import json

from app.evidence_packs import (
    consultant_evidence_pack,
    developer_repair_evidence_pack,
    pm_evidence_pack,
    reviewer_evidence_pack,
)
from app.prompts import evaluator_prompt
from app.review import (
    mark_actioned_review_findings,
    parse_review_output,
    record_review_telemetry,
    should_run_review,
)


def verification(*, full: bool = True):
    phases = [
        {
            "phase": "targeted_tests",
            "passed": True,
            "verification_layer": "intermediate",
            "required_for_final": False,
            "commands": [
                {
                    "command": "pytest tests/test_small.py",
                    "returncode": 0,
                    "stdout": "x" * 50000,
                    "stderr": "",
                }
            ],
        },
        {
            "phase": "static_analysis",
            "passed": True,
            "verification_layer": "final",
            "required_for_final": True,
            "commands": [{"command": "phpstan", "returncode": 0}],
        },
    ]
    if full:
        phases.append(
            {
                "phase": "full_tests",
                "passed": True,
                "required_for_final": True,
                "commands": [{"command": "pytest", "returncode": 0}],
            }
        )
    return {
        "passed": True,
        "tests_passed": True,
        "verification_mode": "layered",
        "phases": phases,
        "failure_text": "",
    }


def test_reviewer_pack_is_compact_and_omits_command_output():
    huge_diff = "diff --git a/a.py b/a.py\n" + ("+changed line\n" * 3000) + "TAIL_SECRET_SENTINEL"
    pack = reviewer_evidence_pack(
        task={"title": "Small change", "description": "contract"},
        diff=huge_diff,
        verification=verification(),
        work_order={"id": "WO-150", "objective": "Small change"},
    )

    encoded = json.dumps(pack)
    assert pack["task_contract"]["id"] == "WO-150"
    assert pack["diff"]["truncated"] is True
    assert len(pack["diff"]["excerpt"]) < len(huge_diff)
    assert "TAIL_SECRET_SENTINEL" not in encoded
    assert "x" * 100 not in encoded
    assert pack["verification"]["phases"][0]["commands"][0] == {
        "command": "pytest tests/test_small.py",
        "returncode": 0,
        "timed_out": False,
    }
    assert pack["jit_retrieval"]["mode"] == "repository_read_only"


def test_evaluator_prompt_uses_pack_and_explicit_jit_contract():
    huge_diff = "diff --git a/a.py b/a.py\n" + ("+line\n" * 4000) + "DO_NOT_PROPAGATE"
    prompt = evaluator_prompt(
        task={"title": "Review me", "description": "legacy description"},
        diff=huge_diff,
        verification=verification(),
        work_order={"id": "WO-150", "objective": "Review me"},
        baseline={"revision": "mvp-v1", "source_commit": "abc123"},
    )

    assert "REVIEW_EVIDENCE_PACK" in prompt
    assert "repository access just in time" in prompt
    assert "REVIEW_JSON" in prompt
    assert "DO_NOT_PROPAGATE" not in prompt


def test_structured_review_report_and_resource_telemetry(monkeypatch):
    report = parse_review_output(
        'FAIL\nREVIEW_JSON: {"verdict":"fail","summary":"Missing regression assertion","findings":[{"id":"F-1","severity":"high","category":"tests","message":"Add the regression assertion","evidence_refs":["tests/test_x.py"]}],"jit_context_used":true}'
    )
    assert report.verdict == "fail"
    assert report.findings[0].id == "F-1"

    monkeypatch.setattr("app.review.estimated_cost_usd", lambda model_id, raw: 0.02)
    progress = {}
    record_review_telemetry(
        progress,
        report,
        review_level="standard",
        model_id="codex_terra",
        provider="openai",
        raw_usage={"input_tokens": 120, "output_tokens": 30},
    )

    assert progress["review_runs"] == 1
    assert progress["review_findings"] == 1
    assert progress["review_jit_context_runs"] == 1
    assert progress["review_input_tokens"] == 120
    assert progress["review_output_tokens"] == 30
    assert progress["review_cost_usd"] == 0.02


def test_fast_review_can_skip_only_with_strong_deterministic_evidence():
    policy = {
        "level": "lightweight",
        "required": False,
        "conditional_on_strong_evidence": True,
    }
    assert should_run_review(
        policy,
        verification(full=True),
        changed_files=2,
        unexpected_scope=False,
    ) is False
    assert should_run_review(
        policy,
        verification(full=False),
        changed_files=6,
        unexpected_scope=False,
    ) is True


def test_actioned_findings_are_counted_only_after_diff_changes():
    checkpoint = {
        "pending_review_findings": {
            "diff_hash": "old",
            "findings": [{"id": "F-1"}, {"id": "F-2"}],
        }
    }
    progress = {"review_findings_actioned": 0}

    mark_actioned_review_findings(checkpoint, progress, current_diff_hash="old")
    assert progress["review_findings_actioned"] == 0
    assert "pending_review_findings" in checkpoint

    mark_actioned_review_findings(checkpoint, progress, current_diff_hash="new")
    assert progress["review_findings_actioned"] == 2
    assert "pending_review_findings" not in checkpoint


def test_role_specific_packs_remain_small_structured_artifacts():
    repair = developer_repair_evidence_pack(
        work_order_ref="WO-150",
        current_diff_ref="sha256:abc",
        failing_check="one failing test",
        reviewer_findings=[{"id": "F-1", "severity": "high", "message": "fix me"}],
        relevant_files=["a.py", "a.py", "b.py"],
        prior_attempt_summary="prior attempt",
    )
    consultant = consultant_evidence_pack(
        work_order_ref="WO-150",
        objective="challenge design",
        question="Is this safe?",
        evidence=[{"ref": "a.py", "summary": "relevant path"}],
    )
    pm = pm_evidence_pack(
        work_order_ref="WO-150",
        outcome="accepted",
        verification_summary=verification(),
        review_summary={"verdict": "pass", "finding_count": 0},
        unresolved_risks=[],
        protected_decision_flags=[],
        baseline_covered_protected_authorizations=[
            {
                "diff_hash": "diff-1",
                "protected_signals": ["security_boundary_change"],
                "approved_by": "pm-model",
                "provider": "openai",
                "summary": "Covered by the pinned baseline.",
                "review_verdict": "pass",
                "baseline_revision": "v1",
            }
        ],
    )

    assert repair["role"] == "developer_repair"
    assert repair["relevant_files"] == ["a.py", "b.py"]
    assert consultant["role"] == "consultant"
    assert pm["role"] == "product_manager"
    assert pm["baseline_covered_protected_authorizations"][0]["diff_hash"] == "diff-1"
    assert pm["baseline_covered_protected_authorizations"][0]["protected_signals"] == ["security_boundary_change"]
    assert all(pack["jit_retrieval"]["mode"] == "repository_read_only" for pack in [repair, consultant, pm])



def test_legacy_fail_review_finding_is_bounded():
    report = parse_review_output("FAIL\n" + ("x" * 5000))

    assert report.verdict == "fail"
    assert len(report.summary) == 4000
    assert len(report.findings) == 1
    assert len(report.findings[0].message) == 2000


def test_streaming_or_unstructured_review_output_fails_closed():
    raw_event = json.dumps(
        {
            "type": "step_start",
            "title": "Independent review",
            "detail": "x" * 5000,
        }
    )

    report = parse_review_output(raw_event)

    assert report.verdict == "fail"
    assert report.protocol_valid is False
    assert len(report.findings) == 1
    assert report.findings[0].message == (
        "Reviewer returned malformed or unstructured output; "
        "no valid REVIEW_JSON failure report was available."
    )
    assert "step_start" not in report.findings[0].message


def test_invalid_structured_review_fails_closed_without_validation_error():
    report = parse_review_output(
        "FAIL\nREVIEW_JSON: "
        + json.dumps(
            {
                "verdict": "fail",
                "summary": "Malformed oversized finding",
                "findings": [
                    {
                        "id": "F-oversized",
                        "severity": "medium",
                        "category": "review",
                        "message": "x" * 2501,
                        "evidence_refs": [],
                    }
                ],
                "jit_context_used": False,
            }
        )
    )

    assert report.verdict == "fail"
    assert report.protocol_valid is False
    assert len(report.findings) == 1
    assert "malformed or unstructured" in report.findings[0].message
    assert len(report.findings[0].message) < 2000



def test_malformed_structured_pass_fails_closed():
    report = parse_review_output(
        'PASS\nREVIEW_JSON: {"verdict":"pass","summary":'
    )

    assert report.verdict == "fail"
    assert report.protocol_valid is False
    assert len(report.findings) == 1
    assert "malformed or unstructured" in report.findings[0].message

def test_legacy_fail_review_remains_protocol_valid():
    report = parse_review_output("FAIL\nOne bounded correctness concern.")

    assert report.verdict == "fail"
    assert report.protocol_valid is True
    assert len(report.findings) == 1


def test_protocol_invalid_review_is_telemetry_not_actionable_finding(monkeypatch):
    report = parse_review_output('{"type":"step_start","detail":"not a review verdict"}')
    assert report.protocol_valid is False

    monkeypatch.setattr("app.review.estimated_cost_usd", lambda model_id, raw: 0.0)
    progress = {}
    record_review_telemetry(
        progress,
        report,
        review_level="standard",
        model_id="reviewer",
        provider="provider",
        raw_usage={"input_tokens": 10, "output_tokens": 5},
    )

    assert progress["review_runs"] == 1
    assert progress["review_protocol_failures"] == 1
    assert progress["review_findings"] == 0
    assert progress["review_history"][-1]["protocol_valid"] is False
    assert progress["review_history"][-1]["finding_count"] == 0

