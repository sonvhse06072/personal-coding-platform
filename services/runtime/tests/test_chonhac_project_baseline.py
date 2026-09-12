from __future__ import annotations

from app.baseline import resolve_project_baseline
from app.config import clear_config_cache


EXPECTED_COMMIT = "80a6974e62d5a5708c8ce4116a24e03557753e38"
EXPECTED_REVISION = "mvp-v1-2026-09-13"


def test_chonhac_active_baseline_resolves_to_approved_source_of_truth() -> None:
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
        ],
        "architecture_constraints": [
            {"path": "docs/06-architecture.md", "section": None},
            {"path": "docs/11-decisions.md", "section": None},
        ],
        "quality_policy": [
            {"path": "AGENTS.md", "section": None},
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
            {"path": "infra/staging/DEC-025-PRE-BETA-HARDENING.md", "section": None},
        ],
    }

    clear_config_cache()
