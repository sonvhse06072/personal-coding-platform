from __future__ import annotations

from app.baseline import resolve_project_baseline
from app.config import clear_config_cache


EXPECTED_COMMIT = "6038857e33d3717321a54e35743fa8b9dbeba8d2"
EXPECTED_REVISION = "mvp-v1-2026-10-01-completion"
EVENT_COMMIT = "77370a25608f4163628d553fadeed9fd192d0824"
EVENT_REVISION = "event-network-v1-2026-10-03-dec032"
PREVIOUS_GOVERNED_COMMIT = "8383b0004ee649cb3ac0fef1e68f9ca40718005b"
PREVIOUS_GOVERNED_REVISION = "mvp-v1-2026-09-27-governed"
PREVIOUS_DESIGN_COMMIT = "afc0901a6c073f763c440df4d492778c12fec11a"
PREVIOUS_DESIGN_REVISION = "mvp-v1-2026-09-22-design"
LEGACY_COMMIT = "b143fbb001c2006ec82570619802b607085fbeb0"
LEGACY_REVISION = "mvp-v1-2026-09-13"


def test_chonhac_active_baseline_resolves_to_approved_completion_source_of_truth() -> None:
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
            {"path": "docs/08-ux-notes.md", "section": None},
            {"path": "docs/17-design-language.md", "section": None},
            {"path": "docs/18-design-execution-plan.md", "section": None},
            {"path": "docs/19-information-architecture-sitemap.md", "section": None},
            {"path": "docs/20-core-wireframe-system.md", "section": None},
            {"path": "docs/21-responsive-mobile-review.md", "section": None},
            {"path": "docs/22-shared-component-contract.md", "section": None},
            {"path": "docs/24-mvp-completion-contract.md", "section": None},
            {"path": "docs/25-mvp-workflow-design.md", "section": None},
        ],
        "architecture_constraints": [
            {"path": "docs/06-architecture.md", "section": None},
            {"path": "docs/11-decisions.md", "section": None},
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
            {"path": "docs/25-mvp-workflow-design.md", "section": None},
            {"path": "docs/26-local-demo-workflow.md", "section": None},
        ],
        "security_policy": [
            {"path": "docs/13-permissions-access-matrix.md", "section": None},
            {"path": "docs/24-mvp-completion-contract.md", "section": None},
        ],
        "budget_policy": [
            {"path": "AGENTS.md", "section": None},
        ],
        "roadmap_frame": [
            {"path": "PROJECT-CONTEXT.md", "section": None},
            {"path": "docs/09-roadmap.md", "section": None},
            {"path": "docs/10-backlog.md", "section": None},
            {"path": "docs/26-local-demo-workflow.md", "section": None},
            {"path": "infra/staging/DEC-025-PRE-BETA-HARDENING.md", "section": None},
        ],
    }

    authority = {rule.path: rule.authority for rule in baseline.authority}
    assert authority["docs/04-business-rules.md"] == "human_owner_protected"
    assert authority["docs/11-decisions.md"] == "human_owner_protected"
    assert authority[".governance/document-authority.json"] == "human_owner_protected"
    assert authority["docs/17-design-language.md"] == "delegated_design_owner"
    assert authority["docs/22-shared-component-contract.md"] == "delegated_design_owner"
    assert authority["docs/24-mvp-completion-contract.md"] == "human_owner_protected"
    assert authority["docs/25-mvp-workflow-design.md"] == "delegated_design_owner"
    assert authority["docs/26-local-demo-workflow.md"] == "mutable_execution"
    assert authority["PROJECT-CONTEXT.md"] == "mutable_execution"
    assert authority["docs/history/episodes.md"] == "evidence_history"
    assert len(authority) == 37

    clear_config_cache()



def test_dec032_event_baseline_is_explicitly_resolvable_without_changing_active_revision() -> None:
    clear_config_cache()

    active = resolve_project_baseline("chonhac")
    event = resolve_project_baseline("chonhac", EVENT_REVISION)

    assert active is not None
    assert active.revision == EXPECTED_REVISION
    assert active.source_commit == EXPECTED_COMMIT

    assert event is not None
    assert event.project_id == "chonhac"
    assert event.revision == EVENT_REVISION
    assert event.status == "approved"
    assert event.source_commit == EVENT_COMMIT

    references = event.references.model_dump(mode="json")
    assert references["requirements"] == [
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
    ]
    assert references["architecture_constraints"] == [
        {"path": "docs/06-architecture.md", "section": None},
        {"path": "docs/11-decisions.md", "section": None},
        {"path": "docs/27-event-network-successor-reconciliation.md", "section": None},
    ]
    assert references["security_policy"] == [
        {"path": "docs/13-permissions-access-matrix.md", "section": None},
        {"path": "docs/27-event-network-successor-reconciliation.md", "section": None},
    ]
    assert references["roadmap_frame"] == [
        {"path": "docs/09-roadmap.md", "section": None},
        {"path": "docs/10-backlog.md", "section": None},
        {"path": "docs/27-event-network-successor-reconciliation.md", "section": None},
    ]

    authority = {rule.path: rule.authority for rule in event.authority}
    assert authority["docs/27-event-network-successor-reconciliation.md"] == "human_owner_protected"
    assert authority["docs/19-information-architecture-sitemap.md"] == "delegated_design_owner"
    assert authority["PROJECT-CONTEXT.md"] == "mutable_execution"
    assert len(authority) == 38

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
