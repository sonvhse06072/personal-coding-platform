from __future__ import annotations

from app.baseline import resolve_project_baseline
from app.config import clear_config_cache


EXPECTED_COMMIT = "ba3207af0ce28b607b1d3dd9eb00bc69072ac234"
EXPECTED_REVISION = "validation-v1-2026-09-16"
EXPECTED_SOURCE = "PROJECT-BASELINE.md"


def test_pcp_validation_fixture_active_baseline_is_approved_and_pinned() -> None:
    clear_config_cache()
    baseline = resolve_project_baseline("pcp-validation-fixture")

    assert baseline is not None
    assert baseline.project_id == "pcp-validation-fixture"
    assert baseline.revision == EXPECTED_REVISION
    assert baseline.status == "approved"
    assert baseline.source_commit == EXPECTED_COMMIT

    references = baseline.references.model_dump(mode="json")
    assert references == {
        "goals": [{"path": EXPECTED_SOURCE, "section": "Goals"}],
        "non_goals": [{"path": EXPECTED_SOURCE, "section": "Non-goals"}],
        "requirements": [{"path": EXPECTED_SOURCE, "section": "Requirements"}],
        "architecture_constraints": [
            {"path": EXPECTED_SOURCE, "section": "Architecture constraints"}
        ],
        "quality_policy": [{"path": EXPECTED_SOURCE, "section": "Quality policy"}],
        "security_policy": [{"path": EXPECTED_SOURCE, "section": "Security policy"}],
        "budget_policy": [{"path": EXPECTED_SOURCE, "section": "Budget policy"}],
        "roadmap_frame": [{"path": EXPECTED_SOURCE, "section": "Roadmap frame"}],
    }

    clear_config_cache()
