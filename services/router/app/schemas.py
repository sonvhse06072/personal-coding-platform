from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ProfileName = Literal["fast", "standard", "complex", "critical"]
RouteAction = Literal["continue", "escalate", "stop", "complete", "human_decision"]
ReasoningEffort = Literal["low", "medium", "high"]


class SemanticSignals(BaseModel):
    ambiguity: int = Field(default=25, ge=0, le=100)
    architecture_impact: int = Field(default=10, ge=0, le=100)
    verification_difficulty: int = Field(default=25, ge=0, le=100)
    risk: int = Field(default=20, ge=0, le=100)
    context_requirement: int = Field(default=30, ge=0, le=100)
    novelty: int = Field(default=25, ge=0, le=100)
    reasoning_requirement: int = Field(default=40, ge=0, le=100)


class TaskDescriptor(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20000)
    task_type: str = Field(default="unknown", max_length=100)
    semantic: SemanticSignals = Field(default_factory=SemanticSignals)
    flags: list[str] = Field(default_factory=list)


class RepoAnalysis(BaseModel):
    estimated_files: int = Field(default=1, ge=0, le=500)
    affected_components: int = Field(default=1, ge=0, le=100)
    dependency_depth: int = Field(default=1, ge=0, le=10)
    tests_available: bool = True
    existing_pattern: bool = False
    historical_churn: int = Field(default=20, ge=0, le=100)
    schema_change: bool = False
    security_sensitive: bool = False
    authentication_change: bool = False
    authorization_change: bool = False
    external_api: bool = False
    production_write: bool = False
    destructive_migration: bool = False
    likely_change_types: list[str] = Field(default_factory=list)
    candidate_modules: list[str] = Field(default_factory=list)
    related_commits_found: int = Field(default=0, ge=0, le=100)


class PrivacyPolicy(BaseModel):
    private_code: bool = True
    allow_training_provider: bool = False
    require_zero_retention: bool = False


class ProviderState(BaseModel):
    healthy: bool = True
    quota_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: int = Field(default=0, ge=0)
    predicted_success: float | None = Field(default=None, ge=0.0, le=1.0)
    available: bool = True


class RoutingRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(default="default", max_length=200)
    repository: str = Field(default="unknown", max_length=500)
    source_commit: str = Field(min_length=4, max_length=100)
    task: TaskDescriptor
    repo: RepoAnalysis = Field(default_factory=RepoAnalysis)
    provider_state: dict[str, ProviderState] = Field(default_factory=dict)
    privacy: PrivacyPolicy | None = None


class StaffingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(default="default", min_length=1, max_length=200)
    role: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]{1,79}$")
    profile: ProfileName = "standard"
    semantic: SemanticSignals = Field(default_factory=SemanticSignals)
    provider_state: dict[str, ProviderState] = Field(default_factory=dict)


class DimensionScores(BaseModel):
    scope: int
    dependency_depth: int
    ambiguity: int
    architecture_impact: int
    verification_difficulty: int
    risk: int
    context_requirement: int
    novelty: int
    reasoning_requirement: int


class ModelChoice(BaseModel):
    id: str
    provider: str
    adapter: str
    model: str
    reasoning_effort: ReasoningEffort | None = None
    score: float
    predicted_success: float
    reasons: list[str]


class StaffingResponse(BaseModel):
    request_id: str
    project_id: str
    role: str
    profile: ProfileName
    choice: ModelChoice
    rejected_candidates: dict[str, list[str]] = Field(default_factory=dict)
    policy_version: int
    registry_version: int


class HumanDecision(BaseModel):
    required: bool
    triggers: list[str] = Field(default_factory=list)
    reason: str | None = None


class Budget(BaseModel):
    max_model_calls: int
    max_input_tokens: int
    max_output_tokens: int
    max_tool_calls: int
    max_iterations: int
    max_repair_iterations: int
    max_escalations: int
    max_provider_failovers: int = 2
    max_model_failovers: int = 2
    max_test_runs: int
    max_wall_time_minutes: int
    soft_cost_usd: float
    hard_cost_usd: float
    max_changed_files: int


class ExecutionStrategy(BaseModel):
    profile: ProfileName
    analysis_depth: int
    planner: ModelChoice | None = None
    executor: ModelChoice
    evaluator: ModelChoice | None = None
    reasoning_ceiling: dict[str, ReasoningEffort] = Field(default_factory=dict)
    human_decision: HumanDecision
    budget: Budget
    anti_loop: dict[str, Any]
    permissions: dict[str, bool]
    definition_of_done: dict[str, list[str]]
    reasons: list[str]


class RoutingResponse(BaseModel):
    job_id: str
    project_id: str
    source_commit: str
    complexity_score: int
    dimensions: DimensionScores
    strategy: ExecutionStrategy
    rejected_candidates: dict[str, list[str]] = Field(default_factory=dict)
    policy_version: int
    registry_version: int


class ExecutionProgress(BaseModel):
    iteration: int = Field(default=0, ge=0)
    repair_iterations: int = Field(default=0, ge=0)
    escalations: int = Field(default=0, ge=0)
    provider_failovers: int = Field(default=0, ge=0)
    model_failovers: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    test_runs: int = Field(default=0, ge=0)
    elapsed_minutes: float = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)
    changed_files: int = Field(default=0, ge=0)
    failure_fingerprints: list[str] = Field(default_factory=list)
    diff_hashes: list[str] = Field(default_factory=list)
    progress_markers: list[str] = Field(default_factory=list)
    tests_passed: bool = False
    required_checks_passed: bool = False
    material_change_present: bool = False
    agent_succeeded: bool = False
    last_agent_failure_kind: str | None = None
    unexpected_scope: bool = False
    important_decision_flags: list[str] = Field(default_factory=list)


class ReassessRequest(BaseModel):
    route: RoutingResponse
    progress: ExecutionProgress
    provider_state: dict[str, ProviderState] = Field(default_factory=dict)


class ReassessResponse(BaseModel):
    action: RouteAction
    reason: str
    current_profile: ProfileName
    next_executor: ModelChoice | None = None
    human_decision: HumanDecision | None = None
    remaining: dict[str, float | int]
    signals: list[str] = Field(default_factory=list)
