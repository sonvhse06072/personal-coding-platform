"""Bounded canonical API types; execution uses the existing job/plan APIs."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .intake_policy import IntakeDecision
from .pm_planning import PMProviderState, PMTicket, PlanningProfile, PlanStatus
from .schemas import JobStatus, RepoHints, SemanticSignals


class IntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=200)
    ticket: PMTicket
    baseline_revision: str | None = Field(
        default=None, min_length=1, max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    bounded_direct: bool = False
    semantic: SemanticSignals | None = None
    repo_hints: RepoHints = Field(default_factory=RepoHints)
    planning_profile: PlanningProfile = "standard"
    provider_state: dict[Annotated[str, Field(min_length=1, max_length=200)], PMProviderState] = Field(
        default_factory=dict, max_length=50,
    )
    auto_run: bool = Field(default=True, description="Enqueue a direct job; plans use existing automatic orchestration.")

    @field_validator("semantic", "repo_hints", mode="before")
    @classmethod
    def reject_unknown_signal_fields(cls, value, info):
        # Legacy models ignore extras. Tighten only this new boundary without
        # changing existing job/recovery clients or duplicating their models.
        schema = SemanticSignals if info.field_name == "semantic" else RepoHints
        if isinstance(value, dict) and set(value) - set(schema.model_fields):
            raise ValueError("Unknown structured signal fields")
        return value

    @field_validator("repo_hints")
    @classmethod
    def bound_scope_labels(cls, value: RepoHints) -> RepoHints:
        for labels in (value.likely_change_types, value.candidate_modules):
            if labels is not None and (len(labels) > 30 or any(len(label) > 100 for label in labels)):
                raise ValueError("Scope hints allow at most 30 labels of 100 characters each")
        return value


class IntakeJobIdentity(BaseModel):
    id: str = Field(max_length=200)
    status: JobStatus


class IntakePlanIdentity(BaseModel):
    id: str = Field(max_length=200)
    status: PlanStatus


class DirectIntakeResponse(IntakeDecision):
    mode: Literal["direct"] = "direct"
    baseline_revision: str
    job: IntakeJobIdentity


class PlanningIntakeResponse(IntakeDecision):
    mode: Literal["planning"] = "planning"
    baseline_revision: str
    plan: IntakePlanIdentity


IntakeResponse = Annotated[DirectIntakeResponse | PlanningIntakeResponse, Field(discriminator="mode")]
