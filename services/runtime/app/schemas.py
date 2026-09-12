from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal[
    "queued", "routing", "planning", "executing", "verifying", "evaluating",
    "waiting_human", "completed", "blocked", "failed", "cancelled", "interrupted"
]


class SemanticSignals(BaseModel):
    ambiguity: int = Field(default=25, ge=0, le=100)
    architecture_impact: int = Field(default=10, ge=0, le=100)
    verification_difficulty: int = Field(default=25, ge=0, le=100)
    risk: int = Field(default=20, ge=0, le=100)
    context_requirement: int = Field(default=30, ge=0, le=100)
    novelty: int = Field(default=25, ge=0, le=100)
    reasoning_requirement: int = Field(default=40, ge=0, le=100)


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=30000)
    task_type: str = Field(default="unknown", max_length=100)
    flags: list[str] = Field(default_factory=list)
    semantic: SemanticSignals | None = None


class RepoHints(BaseModel):
    estimated_files: int | None = Field(default=None, ge=0, le=500)
    affected_components: int | None = Field(default=None, ge=0, le=100)
    dependency_depth: int | None = Field(default=None, ge=0, le=10)
    tests_available: bool | None = None
    existing_pattern: bool | None = None
    historical_churn: int | None = Field(default=None, ge=0, le=100)
    schema_change: bool | None = None
    security_sensitive: bool | None = None
    authentication_change: bool | None = None
    authorization_change: bool | None = None
    external_api: bool | None = None
    production_write: bool | None = None
    destructive_migration: bool | None = None
    likely_change_types: list[str] | None = None
    candidate_modules: list[str] | None = None
    related_commits_found: int | None = Field(default=None, ge=0, le=100)


class JobCreateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    task: TaskInput
    source_commit: str | None = Field(default=None, max_length=100)
    baseline_revision: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    repo_hints: RepoHints = Field(default_factory=RepoHints)
    provider_state: dict[str, dict[str, Any]] = Field(default_factory=dict)
    auto_run: bool = True
    dry_run: bool = False


class JobRunRequest(BaseModel):
    reset_transient_provider_failures: bool = False


class HumanDecisionRequest(BaseModel):
    action: Literal["approve", "reject"]
    note: str = Field(default="", max_length=5000)


class JobView(BaseModel):
    id: str
    project_id: str
    status: JobStatus | str
    source_commit: str | None = None
    baseline_revision: str | None = None
    branch: str | None = None
    workspace: str | None = None
    complexity_score: int | None = None
    profile: str | None = None
    executor: str | None = None
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


class JobList(BaseModel):
    jobs: list[JobView]


class RuntimeHealth(BaseModel):
    status: str
    service: str
    version: str
    router: str
    executor: str
    adapters: dict[str, bool]
