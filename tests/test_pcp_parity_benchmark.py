"""Synthetic-only regression tests; these are not performance measurements."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pcp-parity-benchmark.py"
MODULE = runpy.run_path(str(SCRIPT))
summarize = MODULE["summarize"]


def record(trial, arm, category="drupal", seconds=100, **overrides):
    start = datetime(2026, 10, 10, tzinfo=timezone.utc)
    item = {
        "trial_id": trial,
        "arm": arm,
        "task_id": "task-" + trial,
        "task_type": category,
        "source_sha": "a" * 40,
        "acceptance_sha256": "b" * 64,
        "environment_id": "isolated-validation-fixture-v1",
        "environment_class": "isolated_fixture",
        "model_id": "same-registered-model",
        "reasoning_effort": "medium",
        "verification_policy": "required-final-v1",
        "review_policy": "pm-final-v1",
        # These are SYNTHETIC per-arm assertions, never real environment proof.
        "codex_cli_version": "0.160.0",
        "toolchain_id": "ddev1.25.4-php8.3-node24-browser-pinned",
        "workspace_id": f"{trial}-{arm}-isolated",
        "started_at": start.isoformat(),
        "ended_at": (start + timedelta(seconds=seconds)).isoformat(),
        "outcome": "accepted",
        "evidence_url": "https://github.com/example/fixture/issues/1",
        "quality": {
            "deterministic": True,
            "review": True,
            "ci": True,
            "visual": True if category == "frontend" else None,
        },
        "owner_interventions": 0,
    }
    item.update(overrides)
    return item


def paired(n, *, ratio=1.2):
    categories = ("drupal", "frontend", "repair")
    records = []
    for i in range(n):
        category = categories[i % len(categories)]
        records += [
            record(f"trial-{i}", "direct", category, seconds=100),
            record(f"trial-{i}", "pcp", category, seconds=int(100 * ratio)),
        ]
    return {"schema_version": 1, "records": records}


def test_full_synthetic_cohort_yields_metrics_but_no_automatic_go():
    result = summarize(paired(12))
    assert result["status"] == "metrics_available_human_g0_gate_required"
    assert result["accepted_comparable_pairs"] == 12
    assert result["task_type_coverage"] == {"drupal": 4, "frontend": 4, "repair": 4}
    assert result["latency"]["p50"]["pcp_to_direct_ratio"] == 1.2
    assert result["latency"]["p90"]["pcp_to_direct_ratio"] == 1.2
    assert result["all_attempt_outcomes"]["pcp"]["accepted"] == 12
    assert result["telemetry_records_with_value"]["pcp"]["input_tokens"] == 0


def test_no_p90_claim_for_small_samples():
    result = summarize(paired(3))
    assert result["status"] == "insufficient_evidence"
    assert result["latency"]["p50"] is not None
    assert result["latency"]["p90"] is None
    result = summarize(paired(2))
    assert result["latency"] == {"p50": None, "p90": None}


def test_failed_or_aborted_arm_is_not_cherry_picked_as_accepted():
    payload = paired(4)
    payload["records"][1]["outcome"] = "failed"
    payload["records"][1]["quality"]["ci"] = False
    result = summarize(payload)
    assert result["accepted_comparable_pairs"] == 3
    assert result["excluded_trials"] == [
        {"trial_id": "trial-0", "reason": "at_least_one_arm_not_accepted"}
    ]
    assert result["all_attempt_outcomes"]["pcp"]["failed"] == 1
    assert result["latency"]["p90"] is None


def test_missing_arm_and_different_model_are_noncomparable():
    payload = paired(2)
    payload["records"] = payload["records"][:-1]
    payload["records"][1]["model_id"] = "different-model"
    result = summarize(payload)
    assert result["accepted_comparable_pairs"] == 0
    assert result["excluded_trials"] == [
        {"trial_id": "trial-0", "reason": "noncomparable_pinned_conditions"},
        {"trial_id": "trial-1", "reason": "missing_arm"},
    ]


def test_duplicate_trial_arm_is_rejected():
    payload = paired(1)
    payload["records"].append(dict(payload["records"][0]))
    with pytest.raises(ValueError, match="duplicate trial_id"):
        summarize(payload)


@pytest.mark.parametrize("mutate,reason", [
    (lambda r: r.update(raw_prompt="secret"), "unknown/missing fields"),
    (lambda r: r.update(source_sha="not-a-sha"), "source_sha"),
    (lambda r: r.update(environment_class="shared_live"), "environment_class"),
    (lambda r: r.update(input_tokens=True), "input_tokens"),
    (lambda r: r.update(started_at="2026-10-10T00:00:00"), "explicit UTC offset"),
    (lambda r: r.update(ended_at=r["started_at"]), "positive bounded wall"),
    (lambda r: r.update(evidence_url="https://example.com/secret"), "GitHub evidence"),
])
def test_invalid_or_unverifiable_record_rejected(mutate, reason):
    payload = paired(1)
    mutate(payload["records"][0])
    with pytest.raises(ValueError, match=reason):
        summarize(payload)


def test_frontend_cannot_claim_acceptance_without_visual_proof():
    payload = paired(1)
    for r in payload["records"]:
        r["task_type"] = "frontend"
        r["quality"]["visual"] = None
    with pytest.raises(ValueError, match="visual pass"):
        summarize(payload)


def test_accepted_record_requires_all_final_gates():
    payload = paired(1)
    payload["records"][0]["quality"]["review"] = False
    with pytest.raises(ValueError, match="failed/missing final checks"):
        summarize(payload)


def test_cli_is_read_only_and_reports_insufficient_evidence(tmp_path):
    input_path = tmp_path / "synthetic.json"
    output_path = tmp_path / "report.json"
    input_path.write_text(json.dumps(paired(2)), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(input_path),
         "--output", str(output_path)],
        capture_output=True, text=True, check=False,
    )
    assert run.returncode == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "insufficient_evidence"
    assert json.loads(input_path.read_text(encoding="utf-8"))["records"][0]["arm"] == "direct"


def test_cli_refuses_unexpected_raw_prompt_field(tmp_path):
    payload = paired(1)
    payload["records"][0]["raw_prompt"] = "should never appear in output"
    path = tmp_path / "untrusted.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(path)],
        capture_output=True, text=True, check=False,
    )
    assert run.returncode == 2
    assert "should never appear in output" not in run.stdout + run.stderr
    assert "unknown/missing fields" in run.stderr


def test_historical_outcomes_never_unlock_controlled_g0_metrics():
    payload = paired(12)
    for record in payload["records"]:
        record["environment_class"] = "historical_record"
    result = summarize(payload)
    assert result["paired_trial_ids"] == 12
    assert result["accepted_comparable_pairs"] == 0
    assert result["historical_accepted_pairs_excluded"] == 12
    assert result["status"] == "insufficient_evidence"
    assert result["latency"] == {"p50": None, "p90": None}
    assert all(
        item["reason"] == "historical_not_controlled"
        for item in result["excluded_trials"]
    )


def test_generic_php_smoke_cases_do_not_masquerade_as_drupal_cohort():
    payload = paired(12)
    for record in payload["records"]:
        if record["task_type"] == "drupal":
            record["task_type"] = "php"
    result = summarize(payload)
    assert result["php_smoke_pairs_excluded"] == 4
    assert result["accepted_comparable_pairs"] == 8
    assert result["task_type_coverage"] == {
        "drupal": 0, "frontend": 4, "repair": 4,
    }
    assert result["status"] == "insufficient_evidence"
    assert result["latency"]["p90"] is None
    assert {
        item["reason"] for item in result["excluded_trials"]
    } == {"php_smoke_not_drupal"}


def test_failed_historical_attempts_are_still_visible():
    payload = paired(1)
    for record in payload["records"]:
        record["environment_class"] = "historical_record"
    payload["records"][1]["outcome"] = "failed"
    payload["records"][1]["quality"]["ci"] = False
    result = summarize(payload)
    assert result["all_attempt_outcomes"]["pcp"]["failed"] == 1
    assert result["historical_accepted_pairs_excluded"] == 0
    assert result["excluded_trials"][0]["reason"] == "at_least_one_arm_not_accepted"



def test_host_runtime_cli_mismatch_cannot_enter_controlled_latency_cohort():
    payload = paired(12)
    for record in payload["records"]:
        if record["arm"] == "direct":
            record["codex_cli_version"] = "0.162.0"
        else:
            record["codex_cli_version"] = "0.160.0"
    result = summarize(payload)
    assert result["accepted_comparable_pairs"] == 0
    assert result["latency"] == {"p50": None, "p90": None}
    assert result["status"] == "insufficient_evidence"
    assert {e["reason"] for e in result["excluded_trials"]} == {
        "cli_version_mismatch",
    }


def test_legacy_records_without_cli_version_still_parse_but_never_go():
    payload = paired(12)
    for record in payload["records"]:
        del record["codex_cli_version"]
    result = summarize(payload)
    assert result["accepted_comparable_pairs"] == 0
    assert result["status"] == "insufficient_evidence"
    assert {e["reason"] for e in result["excluded_trials"]} == {"cli_version_missing"}


def test_shared_workspace_identity_is_not_independent_pair():
    payload = paired(12)
    for record in payload["records"]:
        record["workspace_id"] = "same-shared-checkout"
    result = summarize(payload)
    assert result["accepted_comparable_pairs"] == 0
    assert result["status"] == "insufficient_evidence"
    assert {e["reason"] for e in result["excluded_trials"]} == {
        "workspace_not_isolated",
    }


def test_missing_workspace_and_toolchain_evidence_are_nonqualifying():
    payload = paired(2)
    for record in payload["records"]:
        record.pop("workspace_id")
    result = summarize(payload)
    assert result["excluded_trials"][0]["reason"] == "workspace_identity_missing"

    payload = paired(2)
    for record in payload["records"]:
        record.pop("toolchain_id")
    result = summarize(payload)
    assert result["excluded_trials"][0]["reason"] == "toolchain_evidence_missing"


def test_different_toolchains_are_not_parity_even_with_same_model_and_cli():
    payload = paired(12)
    for record in payload["records"]:
        if record["arm"] == "pcp":
            record["toolchain_id"] = "ddev1.25.4-php8.3-node22-browser-pinned"
    result = summarize(payload)
    assert result["accepted_comparable_pairs"] == 0
    assert {e["reason"] for e in result["excluded_trials"]} == {
        "toolchain_mismatch",
    }


@pytest.mark.parametrize("name,value", [
    ("codex_cli_version", "codex-cli 0.160.0"),
    ("workspace_id", "/home/sonvh/my-secret-project"),
    ("toolchain_id", "line\nline"),
])
def test_invalid_opaque_evidence_fields_fail_validation(name, value):
    payload = paired(1)
    payload["records"][0][name] = value
    with pytest.raises(ValueError, match=name):
        summarize(payload)
