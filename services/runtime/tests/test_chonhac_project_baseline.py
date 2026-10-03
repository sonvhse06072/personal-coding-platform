from __future__ import annotations

from app.baseline import resolve_project_baseline
from app.config import clear_config_cache


EXPECTED_COMMIT = "7003c1f72c02a3daea3312449fca6fd57bbc76bc"
EXPECTED_REVISION = "pilot-v1-2026-10-03-dec033"
PREVIOUS_COMPLETION_COMMIT = "6038857e33d3717321a54e35743fa8b9dbeba8d2"
PREVIOUS_COMPLETION_REVISION = "mvp-v1-2026-10-01-completion"
PREVIOUS_GOVERNED_COMMIT = "8383b0004ee649cb3ac0fef1e68f9ca40718005b"
PREVIOUS_GOVERNED_REVISION = "mvp-v1-2026-09-27-governed"
PREVIOUS_DESIGN_COMMIT = "afc0901a6c073f763c440df4d492778c12fec11a"
PREVIOUS_DESIGN_REVISION = "mvp-v1-2026-09-22-design"
LEGACY_COMMIT = "b143fbb001c2006ec82570619802b607085fbeb0"
LEGACY_REVISION = "mvp-v1-2026-09-13"


def test_chonhac_active_baseline_resolves_to_dec033_controlled_pilot() -> None:
    clear_config_cache()
    baseline = resolve_project_baseline("chonhac")

    assert baseline is not None
    assert baseline.project_id == "chonhac"
    assert baseline.revision == EXPECTED_REVISION
    assert baseline.status == "approved"
    assert baseline.source_commit == EXPECTED_COMMIT

    references = baseline.references.model_dump(mode="json")
    assert references == {
        "goals": [
            {"path": "docs/00-project-overview.md", "section": None},
            {"path": "docs/01-product-brief.md", "section": None},
        ],
        "non_goals": [
            {"path": "docs/02-mvp-scope.md", "section": None},
        ],
        "requirements": [
            {"path": "docs/02-mvp-scope.md", "section": None},
            {"path": "docs/04-business-rules.md", "section": None},
            {"path": "docs/05-data-model.md", "section": None},
            {"path": "docs/07-api-contracts.md", "section": None},
            {"path": "docs/08-ux-notes.md", "section": None},
            {"path": "docs/17-design-language.md", "section": None},
            {"path": "docs/18-design-execution-plan.md", "section": None},
            {"path": "docs/19-information-architecture-sitemap.md", "section": None},
            {"path": "docs/20-core-wireframe-system.md", "section": None},
            {"path": "docs/21-responsive-mobile-review.md", "section": None},
            {"path": "docs/22-shared-component-contract.md", "section": None},
            {"path": "docs/27-event-network-successor-reconciliation.md", "section": None},
        ],
        "architecture_constraints": [
            {"path": "docs/06-architecture.md", "section": None},
            {"path": "docs/11-decisions.md", "section": None},
            {"path": "docs/27-event-network-successor-reconciliation.md", "section": None},
        ],
        "quality_policy": [
            {"path": "AGENTS.md", "section": None},
            {"path": ".governance/document-authority.json", "section": None},
            {"path": "docs/context-memory-architecture.md", "section": None},
            {"path": "docs/17-design-language.md", "section": None},
            {"path": "docs/18-design-execution-plan.md", "section": None},
            {"path": "docs/20-core-wireframe-system.md", "section": None},
            {"path": "docs/21-responsive-mobile-review.md", "section": None},
            {"path": "docs/22-shared-component-contract.md", "section": None},
            {"path": "docs/27-event-network-successor-reconciliation.md", "section": None},
        ],
        "security_policy": [
            {"path": "docs/13-permissions-access-matrix.md", "section": None},
            {"path": "docs/27-event-network-successor-reconciliation.md", "section": None},
        ],
        "budget_policy": [
            {"path": "AGENTS.md", "section": None},
        ],
        "roadmap_frame": [
            {"path": "PROJECT-CONTEXT.md", "section": None},
            {"path": "docs/09-roadmap.md", "section": None},
            {"path": "docs/10-backlog.md", "section": None},
            {"path": "docs/27-event-network-successor-reconciliation.md", "section": None},
            {"path": "infra/staging/DEC-025-PRE-BETA-HARDENING.md", "section": None},
        ],
    }

    authority = {rule.path: rule.authority for rule in baseline.authority}
    assert authority["docs/11-decisions.md"] == "human_owner_protected"
    assert authority["docs/27-event-network-successor-reconciliation.md"] == "human_owner_protected"
    assert authority["docs/19-information-architecture-sitemap.md"] == "delegated_design_owner"
    assert authority["PROJECT-CONTEXT.md"] == "mutable_execution"
    assert authority["docs/history/episodes.md"] == "evidence_history"
    assert len(authority) == 38

    clear_config_cache()


def test_previous_completion_baseline_remains_explicitly_resolvable() -> None:
    clear_config_cache()
    baseline = resolve_project_baseline("chonhac", PREVIOUS_COMPLETION_REVISION)

    assert baseline is not None
    assert baseline.project_id == "chonhac"
    assert baseline.revision == PREVIOUS_COMPLETION_REVISION
    assert baseline.status == "approved"
    assert baseline.source_commit == PREVIOUS_COMPLETION_COMMIT
    assert any(
        reference.path == "docs/24-mvp-completion-contract.md"
        for reference in baseline.references.requirements
    )

    clear_config_cache()


def test_previous_governed_baseline_remains_explicitly_resolvable() -> None:
    clear_config_cache()
    baseline = resolve_project_baseline("chonhac", PREVIOUS_GOVERNED_REVISION)

    assert baseline is not None
    assert baseline.project_id == "chonhac"
    assert baseline.revision == PREVIOUS_GOVERNED_REVISION
    assert baseline.status == "approved"
    assert baseline.source_commit == PREVIOUS_GOVERNED_COMMIT
    assert len(baseline.authority) == 34

    clear_config_cache()


def test_previous_design_baseline_remains_explicitly_resolvable() -> None:
    clear_config_cache()
    baseline = resolve_project_baseline("chonhac", PREVIOUS_DESIGN_REVISION)

    assert baseline is not None
    assert baseline.project_id == "chonhac"
    assert baseline.revision == PREVIOUS_DESIGN_REVISION
    assert baseline.status == "approved"
    assert baseline.source_commit == PREVIOUS_DESIGN_COMMIT
    assert baseline.authority == []

    clear_config_cache()


def test_chonhac_legacy_baseline_remains_explicitly_resolvable() -> None:
    clear_config_cache()
    baseline = resolve_project_baseline("chonhac", LEGACY_REVISION)

    assert baseline is not None
    assert baseline.project_id == "chonhac"
    assert baseline.revision == LEGACY_REVISION
    assert baseline.status == "approved"
    assert baseline.source_commit == LEGACY_COMMIT

    clear_config_cache()
