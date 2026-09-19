from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .baseline import ProjectBaseline, SourceReference


ProfileName = Literal["fast", "standard", "complex", "critical"]
RiskLevel = Literal["routine", "standard", "high", "critical"]
VerificationPhase = Literal["targeted_tests", "static_analysis", "full_tests"]
BudgetMode = Literal["legacy_hard", "adaptive"]

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$"
_ROLE_PATTERN = r"^[a-z][a-z0-9_]{1,79}$"
_PROFILE_RANK = {"fast": 0, "standard": 1, "complex": 2, "critical": 3}
_RISK_SCORE = {"routine": 20, "standard": 40, "high": 70, "critical": 90}
_PROVIDER_ROLE_WORDS = {
    "openai", "codex", "claude", "anthropic", "deepseek", "antigravity", "groq", "openrouter"
}
_ADAPTIVE_ELASTIC_DIMENSIONS = (
    "max_model_calls",
    "max_tool_calls",
    "max_iterations",
    "max_repair_iterations",
    "max_test_runs",
    "max_wall_time_minutes",
)
# Router TaskDescriptor.description is capped at 20k. Leave headroom for the
# canonical-task wrapper so a schema-valid WorkOrder cannot fail later at Router.
_MAX_SERIALIZED_BYTES = 16000


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
    # New PM-generated contracts must choose the semantics explicitly. The
    # before-validator preserves every legacy persisted/API payload that predates
    # this field by injecting the historical hard-ceiling behavior.
    mode: BudgetMode = Field(
        ...,
        description=(
            "Use adaptive for new routine PM WorkOrders so task estimates do not become owner-interruption gates. "
            "Use legacy_hard only for compatibility or an explicitly required hard task ceiling."
        ),
    )
    max_profile: ProfileName = "standard"
    max_model_calls: int = Field(default=8, ge=1, le=100)
    max_repair_iterations: int = Field(default=2, ge=0, le=20)
    max_wall_time_minutes: int = Field(default=25, ge=1, le=240)
    max_changed_files: int = Field(default=14, ge=1, le=200)

    @model_validator(mode="before")
    @classmethod
    def legacy_mode_for_pre_adaptive_payloads(cls, value: Any) -> Any:
        if isinstance(value, dict) and "mode" not in value:
            updated = dict(value)
            updated["mode"] = "legacy_hard"
            return updated
        return value


class WorkOrderVerification(BaseModel):
    # New PM contracts explicitly identify cheap/intermediate checks separately
    # from final acceptance checks. Legacy persisted payloads predate this field;
    # the before-validator injects [] so their historical verification behavior
    # remains unchanged after a Runtime rollout.
    intermediate_phases: list[VerificationPhase] = Field(
        ...,
        max_length=3,
        description=(
            "Cheap verification phases to gate repair iterations before final checks. "
            "Use an empty list only when no safe intermediate check exists."
        ),
    )
    required_phases: list[VerificationPhase] = Field(min_length=1, max_length=3)

    @model_validator(mode="before")
    @classmethod
    def legacy_intermediate_phases(cls, value: Any) -> Any:
        if isinstance(value, dict) and "intermediate_phases" not in value:
            updated = dict(value)
            updated["intermediate_phases"] = []
            return updated
        return value

    @field_validator("intermediate_phases", "required_phases")
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
    budget: WorkOrderBudget
    dependencies: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="before")
    @classmethod
    def validate_raw_contract_size(cls, value: Any) -> Any:
        if isinstance(value, dict):
            serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if len(serialized.encode("utf-8")) > _MAX_SERIALIZED_BYTES:
                raise ValueError(
                    f"WorkOrder exceeds the {_MAX_SERIALIZED_BYTES}-byte canonical contract limit"
                )
        return value

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
        for dependency in self.dependencies:
            if not re.fullmatch(_ID_PATTERN, dependency):
                raise ValueError(f"Invalid WorkOrder dependency id: {dependency}")
        if self.id in set(self.dependencies):
            raise ValueError("WorkOrder cannot depend on itself")
        overlap = set(self.in_scope) & set(self.out_of_scope)
        if overlap:
            raise ValueError(f"WorkOrder scope is contradictory: {sorted(overlap)}")
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
    phases = list(work_order.verification.intermediate_phases) + list(
        work_order.verification.required_phases
    )
    for phase in dict.fromkeys(phases):
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


def rehydrate_task_from_work_order(
    current_task: dict[str, Any] | None,
    work_order: WorkOrder,
) -> dict[str, Any]:
    """Restore authoritative task meaning while retaining analyzer-derived signals."""

    canonical = canonical_task_from_work_order(work_order)
    current = current_task or {}
    semantic = current.get("semantic")
    if isinstance(semantic, dict):
        merged_semantic = dict(semantic)
        merged_semantic["risk"] = canonical["semantic"]["risk"]
        canonical["semantic"] = merged_semantic
    flags = list(canonical.get("flags") or [])
    for flag in current.get("flags") or []:
        if flag not in flags:
            flags.append(flag)
    canonical["flags"] = flags
    return canonical


def _reconcile_adaptive_emergency_budget(
    budget: dict[str, Any], adaptive: dict[str, Any]
) -> dict[str, Any]:
    """Make effective adaptive ceilings match Router-advertised emergency limits.

    Router adaptive metadata is the authority for elastic task headroom. This
    validation is deliberately strict so version skew or malformed metadata can
    never silently widen a job. A lower effective field may be promoted only to
    its advertised emergency limit; an already-higher field fails closed.
    """

    dimensions = adaptive.get("dimensions")
    if not isinstance(dimensions, dict):
        raise WorkOrderPolicyError("Adaptive Router strategy is missing a dimensions object")

    reconciled = dict(budget)
    for dimension in _ADAPTIVE_ELASTIC_DIMENSIONS:
        if dimension not in reconciled:
            raise WorkOrderPolicyError(
                f"Router strategy is missing required adaptive budget field {dimension!r}"
            )
        envelope = dimensions.get(dimension)
        if not isinstance(envelope, dict):
            raise WorkOrderPolicyError(
                f"Adaptive Router strategy is missing envelope for {dimension!r}"
            )
        try:
            estimate = float(envelope["estimate"])
            working_target = float(envelope["working_target"])
            emergency_limit = float(envelope["emergency_limit"])
            current = float(reconciled[dimension])
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkOrderPolicyError(
                f"Adaptive Router envelope for {dimension!r} is malformed"
            ) from exc

        if not (0 <= estimate <= working_target <= emergency_limit):
            raise WorkOrderPolicyError(
                f"Adaptive Router envelope for {dimension!r} is not monotonic"
            )
        if current > emergency_limit:
            raise WorkOrderPolicyError(
                f"Router effective budget {dimension!r} exceeds its advertised emergency limit"
            )

        if dimension == "max_wall_time_minutes":
            reconciled[dimension] = emergency_limit
        else:
            if not emergency_limit.is_integer():
                raise WorkOrderPolicyError(
                    f"Adaptive Router emergency limit for {dimension!r} must be integral"
                )
            reconciled[dimension] = int(emergency_limit)

    return reconciled


def apply_work_order_budget(route: dict[str, Any], work_order: WorkOrder) -> dict[str, Any]:
    """Apply WorkOrder policy without turning adaptive estimates into hard stops.

    ``legacy_hard`` preserves the historical behavior exactly for old/pinned
    WorkOrders. ``adaptive`` still hard-bounds profile and changed-file scope,
    while Router/Runtime own the task-specific estimate/working/emergency
    envelope. If adaptive metadata is absent, fail closed by falling back to the
    legacy clamps rather than silently widening an old Router contract.
    """

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
    if "max_changed_files" not in budget:
        raise WorkOrderPolicyError("Router strategy is missing required budget field 'max_changed_files'")
    budget["max_changed_files"] = min(
        int(budget["max_changed_files"]),
        work_order.budget.max_changed_files,
    )

    adaptive = strategy.get("adaptive_budget")
    adaptive_enabled = (
        work_order.budget.mode == "adaptive"
        and isinstance(adaptive, dict)
        and bool(adaptive.get("enabled", False))
    )

    if adaptive_enabled:
        budget = _reconcile_adaptive_emergency_budget(budget, adaptive)
        strategy["budget_mode"] = "adaptive"
    else:
        ceilings = {
            "max_model_calls": work_order.budget.max_model_calls,
            "max_repair_iterations": work_order.budget.max_repair_iterations,
            "max_wall_time_minutes": work_order.budget.max_wall_time_minutes,
        }
        for key, ceiling in ceilings.items():
            current = budget.get(key)
            if current is None:
                raise WorkOrderPolicyError(f"Router strategy is missing required budget field {key!r}")
            budget[key] = min(current, ceiling)
        # Missing/disabled adaptive metadata is a fail-closed route even when the
        # declared WorkOrder requested adaptive semantics.
        strategy["budget_mode"] = "legacy_hard"

    strategy["budget"] = budget
    updated["strategy"] = strategy
    return updated


def work_order_snapshot(value: dict[str, Any] | WorkOrder | None) -> WorkOrder | None:
    if value is None:
        return None
    if isinstance(value, WorkOrder):
        return value
    return WorkOrder.model_validate(value)
