from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .baseline import ProjectBaseline, SourceReference


ProfileName = Literal["fast", "standard", "complex", "critical"]
RiskLevel = Literal["routine", "standard", "high", "critical"]
VerificationPhase = Literal["targeted_tests", "static_analysis", "full_tests"]

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$"
_ROLE_PATTERN = r"^[a-z][a-z0-9_]{1,79}$"
_PROFILE_RANK = {"fast": 0, "standard": 1, "complex": 2, "critical": 3}
_RISK_SCORE = {"routine": 20, "standard": 40, "high": 70, "critical": 90}
_PROVIDER_ROLE_WORDS = {
    "openai", "codex", "claude", "anthropic", "deepseek", "antigravity", "groq", "openrouter"
}
_MAX_SERIALIZED_BYTES = 24000


class WorkOrderPolicyError(ValueError):
    pass


class AcceptanceCriterion(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=_ID_PATTERN)
    description: str = Field(min_length=1, max_length=3000)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Acceptance criterion description must not be blank")
        return normalized


class WorkOrderRisk(BaseModel):
    level: RiskLevel = "standard"
    flags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("flags")
    @classmethod
    def normalize_flags(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                raise ValueError("Risk flags must not be blank")
            if len(normalized) > 100:
                raise ValueError("Risk flag is too long")
            if normalized not in result:
                result.append(normalized)
        return result


class WorkOrderBudget(BaseModel):
    max_profile: ProfileName = "standard"
    max_model_calls: int = Field(default=8, ge=1, le=100)
    max_repair_iterations: int = Field(default=2, ge=0, le=20)
    max_wall_time_minutes: int = Field(default=25, ge=1, le=240)
    max_changed_files: int = Field(default=14, ge=1, le=200)


class WorkOrderVerification(BaseModel):
    required_phases: list[VerificationPhase] = Field(min_length=1, max_length=3)

    @field_validator("required_phases")
    @classmethod
    def deduplicate_phases(cls, values: list[VerificationPhase]) -> list[VerificationPhase]:
        result: list[VerificationPhase] = []
        for value in values:
            if value not in result:
                result.append(value)
        return result


class WorkOrder(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=_ID_PATTERN)
    parent_initiative: str | None = Field(default=None, max_length=200)
    parent_ticket: str | None = Field(default=None, max_length=200)
    objective: str = Field(min_length=1, max_length=5000)
    baseline_revision: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    source_references: list[SourceReference] = Field(min_length=1, max_length=50)
    in_scope: list[str] = Field(min_length=1, max_length=50)
    out_of_scope: list[str] = Field(min_length=1, max_length=50)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1, max_length=50)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    requested_role: str = Field(default="developer", min_length=2, max_length=80, pattern=_ROLE_PATTERN)
    verification: WorkOrderVerification
    risk: WorkOrderRisk = Field(default_factory=WorkOrderRisk)
    budget: WorkOrderBudget = Field(default_factory=WorkOrderBudget)
    dependencies: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("objective")
    @classmethod
    def normalize_objective(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("WorkOrder objective must not be blank")
        return normalized

    @field_validator("parent_initiative", "parent_ticket")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("in_scope", "out_of_scope", "constraints", "dependencies")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                raise ValueError("WorkOrder list values must not be blank")
            if len(normalized) > 3000:
                raise ValueError("WorkOrder list value is too long")
            if normalized not in result:
                result.append(normalized)
        return result

    @field_validator("requested_role")
    @classmethod
    def role_must_be_provider_independent(cls, value: str) -> str:
        normalized = value.strip().lower()
        words = set(normalized.split("_"))
        if words & _PROVIDER_ROLE_WORDS:
            raise ValueError("requested_role must describe a logical team role, not a model/provider")
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> "WorkOrder":
        criterion_ids = [criterion.id for criterion in self.acceptance_criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError("Acceptance criterion ids must be unique")
        if self.id in set(self.dependencies):
            raise ValueError("WorkOrder cannot depend on itself")
        serialized = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        if len(serialized.encode("utf-8")) > _MAX_SERIALIZED_BYTES:
            raise ValueError(
                f"WorkOrder exceeds the {_MAX_SERIALIZED_BYTES}-byte canonical contract limit"
            )
        return self


def validate_work_order_against_baseline(
    work_order: WorkOrder,
    baseline: ProjectBaseline | None,
    project: dict[str, Any],
) -> None:
    if baseline is None:
        raise ValueError("WorkOrder requires an approved ProjectBaseline")
    if work_order.baseline_revision != baseline.revision:
        raise ValueError(
            f"WorkOrder baseline_revision {work_order.baseline_revision!r} does not match "
            f"resolved ProjectBaseline {baseline.revision!r}"
        )

    allowed_paths: set[str] = set()
    for references in baseline.references.model_dump(mode="json").values():
        for reference in references:
            allowed_paths.add(str(reference["path"]))
    for reference in work_order.source_references:
        if reference.path not in allowed_paths:
            raise ValueError(
                f"WorkOrder source reference {reference.path!r} is not authorized by "
                f"ProjectBaseline {baseline.revision!r}"
            )

    ddev = project.get("ddev", {}) or {}
    if not ddev.get("enabled", False):
        raise ValueError("WorkOrder deterministic verification requires an enabled DDEV project")
    for phase in work_order.verification.required_phases:
        commands = ddev.get(phase, []) or []
        if not commands:
            raise ValueError(
                f"WorkOrder requires verification phase {phase!r}, but the project has no commands configured"
            )


def canonical_task_from_work_order(work_order: WorkOrder) -> dict[str, Any]:
    contract = json.dumps(work_order.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    description = (
        "AUTHORITATIVE WORKORDER / TASK CONTRACT. Do not reinterpret, broaden, or override this contract.\n"
        f"{contract}\n"
        "Implement only the declared in_scope work, preserve out_of_scope boundaries, satisfy every acceptance criterion, "
        "and report rather than silently changing project scope or constraints."
    )
    return {
        "title": work_order.objective[:500],
        "description": description,
        "task_type": work_order.requested_role,
        "flags": list(work_order.risk.flags),
        "semantic": {"risk": _RISK_SCORE[work_order.risk.level]},
    }


def apply_work_order_budget(route: dict[str, Any], work_order: WorkOrder) -> dict[str, Any]:
    """Apply the WorkOrder as a hard execution ceiling without weakening Router budgets."""

    updated = deepcopy(route)
    strategy = updated.get("strategy") or {}
    selected_profile = str(strategy.get("profile") or "")
    if selected_profile not in _PROFILE_RANK:
        raise WorkOrderPolicyError(f"Router returned unknown profile {selected_profile!r}")
    if _PROFILE_RANK[selected_profile] > _PROFILE_RANK[work_order.budget.max_profile]:
        raise WorkOrderPolicyError(
            f"Router profile {selected_profile!r} exceeds WorkOrder max_profile "
            f"{work_order.budget.max_profile!r}"
        )

    budget = dict(strategy.get("budget") or {})
    ceilings = {
        "max_model_calls": work_order.budget.max_model_calls,
        "max_repair_iterations": work_order.budget.max_repair_iterations,
        "max_wall_time_minutes": work_order.budget.max_wall_time_minutes,
        "max_changed_files": work_order.budget.max_changed_files,
    }
    for key, ceiling in ceilings.items():
        current = budget.get(key)
        if current is None:
            raise WorkOrderPolicyError(f"Router strategy is missing required budget field {key!r}")
        budget[key] = min(current, ceiling)
    strategy["budget"] = budget
    updated["strategy"] = strategy
    return updated


def work_order_snapshot(value: dict[str, Any] | WorkOrder | None) -> WorkOrder | None:
    if value is None:
        return None
    if isinstance(value, WorkOrder):
        return value
    return WorkOrder.model_validate(value)
