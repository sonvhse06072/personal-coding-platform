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
    _budgeted_t1_content,
    _exact_reference_strings,
    _markdown_sections,
    _query_text,
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



def test_unknown_task_type_is_not_topical_retrieval_evidence():
    # A classifier placeholder must not match unrelated T2/T3 content.
    request = {
        "task": {
            "title": "quantum banana orbital jurisprudence",
            "task_type": "unknown",
        },
    }
    assert _query_text(request).strip() == "quantum banana orbital jurisprudence"
    assert _query_text({
        "task": {"title": "Review provider update", "task_type": "model_update"},
    }).strip() == "Review provider update model_update"



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
    assert payload["metrics"]["required_content_recall"] == 1.0
    assert payload["metrics"]["case_count"] >= 12
    assert payload["metrics"]["composed_case_count"] >= 11
    assert payload["metrics"]["mean_compose_ms"] >= 0
    assert payload["metrics"]["stale_historical_false_positive_rate"] == 0.0
    assert payload["metrics"]["authority_conflict_failure_rate"] == 0.0
    assert payload["metrics"]["abstention_accuracy"] == 1.0
    assert payload["metrics"]["mean_context_ratio_vs_read_all"] < 0.50


def test_heading_blocks_are_non_overlapping():
    """Parent headings must not claim matches present only under child headings."""
    sections = _markdown_sections(
        "sample.md",
        "T2",
        "# Guide\nIntro\n## First\nFirst-only.\n### Detail\nChild-only.\n## Second\nSecond-only.",
    )
    by_heading = {item.heading: item.content for item in sections}
    assert "Second-only" not in by_heading["Guide"]
    assert "Child-only" not in by_heading["First"]
    assert "Child-only" in by_heading["Detail"]
    assert "Second-only" in by_heading["Second"]


def test_oversized_t1_prioritizes_active_actions_over_historical_prefix():
    text = (
        "# Current Project State and Handoff\nSource is checked at read time.\n"
        "## Historical accepted status\n" + ("old rollout log " * 200) + "\n"
        "## Resume order\nFetch live GitHub and Runtime before changes.\n"
        "## Active PCP issues\nThe exact blocking gate is actionable.\n"
        "## Immediate next safe actions\nDo not bypass independent review.\n"
    )
    selected, omitted = _budgeted_t1_content(text, 650)
    assert len(selected) <= 650
    assert "Do not bypass independent review." in selected
    assert "exact blocking gate" in selected
    assert "Resume order" in selected
    assert "Historical accepted status" in omitted
    assert "old rollout log" not in selected


def test_cross_project_retrieval_fails_closed():
    with pytest.raises(ValueError, match="project_id"):
        compose_context(
            ROOT,
            {
                "project_id": "chonhac",
                "role": "product_manager",
                "task": {"title": "Find artist profile requirements"},
            },
        )


def test_vietnamese_current_intent_is_recognized():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "product_manager",
            "task": {
                "title": "Trạng thái hiện tại của Runtime và job đang hoạt động?",
                "task_type": "status",
            },
        },
    )
    assert pack["retrieval"]["current_intent"] is True
    assert "docs/project/current-state.md#Current Project State and Handoff" in identities(pack)


def test_business_strategy_available_as_topical_t2():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "product_manager",
            "task": {
                "title": "PCP primary customer and internal business value proposition",
                "task_type": "business_strategy",
            },
            "references": {"topic": "business strategy"},
            "budget_chars": 24000,
        },
    )
    assert any(
        item["source"] == "docs/project/business-strategy.md"
        for item in pack["retrieved"]
    )
    assert pack["provenance"]["source_project_id"] == "personal-coding-platform"


def test_t1_stays_compact_and_does_not_accumulate_completed_chronology():
    """Tier-1 is an active replace-in-place index, not a historical rollout log."""
    content = (ROOT / "docs/project/current-state.md").read_text(encoding="utf-8")
    assert len(content.encode("utf-8")) < 15000
    assert len(content.splitlines()) <= 250
    assert "## Active PCP issues and owner attention" in content
    assert "## Immediate next safe actions" in content
    # Runtime continuity publication relies on this stable T1 safety heading.
    assert "## Standing safety boundary" in content
    assert "## Historical accepted platform / local state snapshot" not in content
    assert "## Generation-1 execution — active" not in content
    assert "GitHub/Runtime" in content


def test_exact_file_reference_matches_source_path_not_only_body():
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": "specialist",
            "task": {"title": "Consult the exact business policy file"},
            "references": {"file": "docs/project/business-strategy.md"},
            "budget_chars": 24000,
        },
    )
    assert any(
        item["source"] == "docs/project/business-strategy.md"
        and any(reason.startswith("exact_ref:") for reason in item["reasons"])
        for item in pack["retrieved"]
    )


@pytest.mark.parametrize("role", ["product_manager", "developer", "reviewer"])
def test_role_critical_governance_is_not_clipped_by_default(role):
    pack = compose_context(
        ROOT,
        {
            "project_id": "personal-coding-platform",
            "role": role,
            "task": {"title": "Check merge and authorization boundaries"},
            "budget_chars": 24000,
        },
    )
    pinned = {item["heading"]: item for item in pack["pinned"] if item["tier"] == "T0"}
    assert pack["retrieval"]["core_governance_complete"] is True
    assert not pinned["Core invariants"]["truncated"]
    assert "Developer agents must never merge." in pinned["Core invariants"]["content"]
    assert not pinned["9. Trust and security invariants"]["truncated"]
    assert not pinned["10. Verification and delivery invariants"]["truncated"]


def test_memory_evaluation_includes_content_and_project_scope_cases():
    fixture = json.loads(
        (ROOT / "config" / "context-memory-eval.json").read_text(encoding="utf-8")
    )
    cases = fixture["cases"]
    assert any(case.get("required_content_contains") for case in cases)
    assert any(case.get("expected_error_contains") == "project_id" for case in cases)
    assert any(
        case.get("kind") == "current"
        and "hiện tại" in case["request"]["task"]["title"]
        for case in cases
    )
