"""Deterministic admission policy for new canonical ticket handoffs only."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import RepoHints, SemanticSignals


POLICY_VERSION = 1
HARD_BOUNDARIES = (
    "schema_change", "security_sensitive", "authentication_change",
    "authorization_change", "external_api", "production_write", "destructive_migration",
)
SEMANTIC_THRESHOLDS = {
    "ambiguity": 50,
    "architecture_impact": 50,
    "verification_difficulty": 50,
    "risk": 50,
    "context_requirement": 70,
    "novelty": 50,
    "reasoning_requirement": 70,
}
MATERIAL_COMPONENTS = 2
MULTI_UNIT_COMPONENTS = 3
MATERIAL_FILES = 10
MATERIAL_CHURN = 50
MATERIAL_SIGNAL_COUNT = 2
REQUIRED_HINTS = (
    "estimated_files", "affected_components", "dependency_depth",
    "tests_available", "existing_pattern", "historical_churn", *HARD_BOUNDARIES,
)


class IntakeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal[1] = POLICY_VERSION
    mode: Literal["direct", "planning"]
    bounded_direct: bool
    reasons: list[str] = Field(max_length=40)
    material_signals: list[str] = Field(max_length=20)
    decomposition_required: bool


def classify_intake(
    *, bounded_direct: bool, semantic: SemanticSignals | None, repo_hints: RepoHints,
) -> IntakeDecision:
    """Unknown evidence is never proof of small scope; prose has no authority."""
    reasons: list[str] = []
    material: list[str] = []
    hard = [name for name in HARD_BOUNDARIES if getattr(repo_hints, name) is True]
    if (repo_hints.dependency_depth or 0) > 0:
        hard.append("dependency_depth")
    if (repo_hints.affected_components or 0) >= MULTI_UNIT_COMPONENTS:
        hard.append("multi_unit_components")
    reasons.extend(f"hard:{name}" for name in hard)

    if not bounded_direct:
        reasons.append("bounded_direct_not_requested")
    for name, threshold in SEMANTIC_THRESHOLDS.items():
        if semantic is None or name not in semantic.model_fields_set:
            reasons.append(f"missing:semantic.{name}")
        elif getattr(semantic, name) >= threshold:
            material.append(name)
    for name in REQUIRED_HINTS:
        value = getattr(repo_hints, name)
        if value is None or (name in {"estimated_files", "affected_components"} and value == 0):
            reasons.append(f"missing:repo_hints.{name}")

    if (repo_hints.affected_components or 0) >= MATERIAL_COMPONENTS:
        material.append("affected_components")
    if (repo_hints.estimated_files or 0) >= MATERIAL_FILES:
        material.append("estimated_files")
    if (repo_hints.historical_churn or 0) >= MATERIAL_CHURN:
        material.append("historical_churn")
    # Missing tests and missing patterns describe one verification shape, not
    # two independent reasons to decompose an otherwise small ticket.
    if repo_hints.tests_available is False or repo_hints.existing_pattern is False:
        material.append("verification_shape")
    if len(material) >= MATERIAL_SIGNAL_COUNT:
        reasons.append("multiple_material_signals")
    materially_large = bool(hard) or len(material) >= MATERIAL_SIGNAL_COUNT
    return IntakeDecision(
        mode="planning" if reasons else "direct",
        bounded_direct=bounded_direct,
        reasons=reasons or ["bounded_direct_eligible"],
        material_signals=material,
        decomposition_required=materially_large,
    )
