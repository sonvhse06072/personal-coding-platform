from __future__ import annotations

from app.baseline import resolve_project_baseline
from app.config import clear_config_cache


EXPECTED_COMMIT = "afc0901a6c073f763c440df4d492778c12fec11a"
EXPECTED_REVISION = "mvp-v1-2026-09-22-design"
LEGACY_COMMIT = "b143fbb001c2006ec82570619802b607085fbeb0"
LEGACY_REVISION = "mvp-v1-2026-09-13"


def test_chonhac_active_baseline_resolves_to_approved_design_source_of_truth() -> None:
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
        ],
        "architecture_constraints": [
            {"path": "docs/06-architecture.md", "section": None},
            {"path": "docs/11-decisions.md", "section": None},
        ],
        "quality_policy": [
            {"path": "AGENTS.md", "section": None},
            {"path": "docs/17-design-language.md", "section": None},
            {"path": "docs/18-design-execution-plan.md", "section": None},
            {"path": "docs/20-core-wireframe-system.md", "section": None},
            {"path": "docs/21-responsive-mobile-review.md", "section": None},
            {"path": "docs/22-shared-component-contract.md", "section": None},
        ],
        "security_policy": [
            {"path": "docs/13-permissions-access-matrix.md", "section": None},
        ],
        "budget_policy": [
            {"path": "AGENTS.md", "section": None},
        ],
        "roadmap_frame": [
            {"path": "PROJECT-CONTEXT.md", "section": None},
            {"path": "docs/09-roadmap.md", "section": None},
            {"path": "docs/10-backlog.md", "section": None},
            {"path": "infra/staging/DEC-025-PRE-BETA-HARDENING.md", "section": None},
        ],
    }

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
