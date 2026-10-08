from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from context_memory import (  # noqa: E402
    _exact_reference_strings,
    compose_context,
    read_all_docs_chars,
    render_context_text,
)


def identities(pack):
    return {
        item["identity"]
        for item in [*pack["pinned"], *pack["retrieved"]]
    }



def test_reference_parser_does_not_treat_normal_pr_prefix_words_as_ids():
    assert _exact_reference_strings(
        {"task": {"title": "Review provider recovery policy and job-owned preview"}}
    ) == set()

    refs = _exact_reference_strings(
        {"task": {"title": "Re-check PR #311 and issue #309"}}
    )
    assert "#311" in refs
    assert "#309" in refs


def test_context_composer_pins_governance_and_current_state():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "developer",
            "task": {
                "title": "Implement bounded cleanup safely",
                "task_type": "implementation",
            },
            "budget_chars": 24000,
        },
    )

    selected = identities(pack)

    assert "AGENTS.md#Core invariants" in selected
    assert (
        "docs/project/current-state.md#Current Project State and Handoff"
        in selected
    )
    assert pack["selected_chars"] <= pack["budget_chars"]
    assert pack["provenance"]["sources_are_repository_relative"] is True
    assert pack["provenance"]["generated_from_head"]


def test_current_state_query_does_not_pull_historical_t3_without_exact_ref():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "product_manager",
            "task": {
                "title": "What is the current Runtime version and active work now?",
                "task_type": "status",
            },
            "budget_chars": 24000,
        },
    )

    assert pack["retrieval"]["current_intent"] is True
    assert not [
        item for item in pack["retrieved"] if item["tier"] == "T3"
    ]


def test_exact_issue_ref_retrieves_historical_episode():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "debugger",
            "task": {
                "title": "Explain the accepted direct preview health lesson",
                "task_type": "incident_research",
            },
            "references": {"issue": "297"},
            "budget_chars": 24000,
        },
    )

    assert any(
        item["tier"] == "T3"
        and "Chợ Nhạc direct workspace + job-owned live preview"
        in item["identity"]
        and any(
            reason.startswith("exact_ref:")
            for reason in item["reasons"]
        )
        for item in pack["retrieved"]
    )


def test_unsupported_query_abstains_from_t2_t3_retrieval():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "specialist",
            "task": {
                "title": "quantum banana orbital jurisprudence",
                "task_type": "unknown",
            },
            "budget_chars": 24000,
        },
    )

    assert pack["retrieved"] == []
    assert pack["retrieval"]["supported_memory_found"] is False
    assert "no supported T2/T3 memory selected" in render_context_text(pack)


def test_small_budget_still_contains_t0_and_t1_and_never_exceeds_budget():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "reviewer",
            "task": {
                "title": "Review direct workspace lease and preview safety",
                "task_type": "code_review",
            },
            "references": {"issue": "309"},
            "budget_chars": 5000,
        },
    )

    tiers = {item["tier"] for item in pack["pinned"]}
    assert "T0" in tiers
    assert "T1" in tiers
    assert pack["selected_chars"] <= 5000
    assert any(item["truncated"] for item in pack["pinned"])


def test_role_specific_pinned_context_differs():
    base = {
        "project_id": "personal-coding-platform",
        "task": {
            "title": "Assess a scope and architecture change",
            "task_type": "decision",
        },
        "budget_chars": 24000,
    }
    pm = compose_context(ROOT, {**base, "role": "product_manager"})
    developer = compose_context(ROOT, {**base, "role": "developer"})

    pm_ids = identities(pm)
    developer_ids = identities(developer)

    assert (
        "docs/project/constitution.md#6. Product Manager authority"
        in pm_ids
    )
    assert (
        "docs/project/constitution.md#6. Product Manager authority"
        not in developer_ids
    )
    assert "AGENTS.md#Baseline authority preservation" in pm_ids
    assert "AGENTS.md#Baseline authority preservation" in developer_ids
    assert pm_ids != developer_ids


def test_context_pack_contains_no_absolute_repository_path():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "reviewer",
            "task": {
                "title": "Review provider recovery policy",
                "task_type": "policy_review",
                "description": (
                    "Do not echo /home/private/worktree or "
                    "RUNTIME_API_TOKEN=super-secret-value"
                ),
            },
            "references": {
                "issue": "228",
                "file": "/home/private/worktree/secret.txt",
            },
            "budget_chars": 24000,
        },
    )

    serialized = json.dumps(pack, ensure_ascii=False)
    assert str(ROOT) not in serialized
    assert "/home/" not in serialized
    assert "super-secret-value" not in serialized
    assert "/home/private/worktree" not in serialized
    assert "RUNTIME_API_TOKEN=[secret-redacted]" in serialized
    assert "DASHBOARD_CONTROL_TOKEN" not in serialized


def test_read_all_baseline_is_materially_larger_than_composed_pack():
    baseline = read_all_docs_chars(ROOT)
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "debugger",
            "task": {
                "title": "Investigate BuildKit cache isolation history",
                "task_type": "incident_research",
            },
            "references": {"issue": "281"},
            "budget_chars": 24000,
        },
    )

    assert baseline > 100000
    assert pack["selected_chars"] < baseline * 0.50


def test_evaluation_fixture_passes():
    fixture = json.loads(
        (ROOT / "config" / "context-memory-eval.json").read_text(
            encoding="utf-8"
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pcp-context-eval.py"),
            "--repo-root",
            str(ROOT),
        ],
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        pytest.fail(
            "context-memory evaluation failed:\n"
            + result.stdout
            + "\n"
            + result.stderr
        )

    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["metrics"]["required_target_recall"] == 1.0
    assert payload["metrics"]["stale_historical_false_positive_rate"] == 0.0
    assert payload["metrics"]["authority_conflict_failure_rate"] == 0.0
    assert payload["metrics"]["abstention_accuracy"] == 1.0
    assert payload["metrics"]["mean_context_ratio_vs_read_all"] < 0.50


def test_t1_stays_compact_and_does_not_accumulate_completed_chronology():
    """Tier-1 is an active replace-in-place index, not a historical rollout log."""
    content = (ROOT / "docs/project/current-state.md").read_text(encoding="utf-8")
    assert len(content.encode("utf-8")) < 15000
    assert len(content.splitlines()) <= 250
    assert "## Active PCP issues and owner attention" in content
    assert "## Immediate next safe actions" in content
    assert "## Historical accepted platform / local state snapshot" not in content
    assert "## Generation-1 execution — active" not in content
    assert "GitHub/Runtime" in content
