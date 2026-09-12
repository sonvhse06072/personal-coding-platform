from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.baseline import ProjectRevisionDefinition


def refs() -> dict:
    ref = [{"path": "docs/project/source.md"}]
    return {
        "goals": ref,
        "non_goals": ref,
        "requirements": ref,
        "architecture_constraints": ref,
        "quality_policy": ref,
        "security_policy": ref,
        "budget_policy": ref,
        "roadmap_frame": ref,
    }


def test_project_baseline_requires_full_git_commit_id() -> None:
    # Length validation may reject a short SHA before the custom format validator.
    with pytest.raises(ValidationError):
        ProjectRevisionDefinition(
            status="approved",
            source_commit="abc1234",
            references=refs(),
        )

    # A full-length non-hex value exercises the custom exact-commit validator.
    with pytest.raises(ValidationError, match="full Git commit id"):
        ProjectRevisionDefinition(
            status="approved",
            source_commit="z" * 40,
            references=refs(),
        )

    revision = ProjectRevisionDefinition(
        status="approved",
        source_commit="A" * 40,
        references=refs(),
    )
    assert revision.source_commit == "a" * 40
