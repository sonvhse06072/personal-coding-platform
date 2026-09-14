from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from .schemas import (
    Budget,
    DimensionScores,
    ExecutionProgress,
    ExecutionStrategy,
    HumanDecision,
    ModelChoice,
    PrivacyPolicy,
    ProviderState,
    ReassessRequest,
    ReassessResponse,
    RepoAnalysis,
    RoutingRequest,
    RoutingResponse,
)


PROFILE_ORDER = ["fast", "standard", "complex", "critical"]


class RouterEngine:
    def __init__(self, config: dict[str, Any]):
        self.models_doc = config["models"]
        self.policy = config["policy"]
        self.projects_doc = config["projects"]
        self.models: dict[str, dict[str, Any]] = self.models_doc.get("models", {})
        self.projects: dict[str, dict[str, Any]] = self.projects_doc.get("projects", {})

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> int:
        return int(round(max(low, min(high, value))))

    def _project(self, project_id: str) -> dict[str, Any]:
        return self.projects.get(project_id) or self.projects.get("default", {})

    def _privacy(self, request: RoutingRequest) -> PrivacyPolicy:
        if request.privacy is not None:
            return request.privacy
        data = self._project(request.project_id).get("privacy", {})
        return PrivacyPolicy(**data)

    def compute_dimensions(self, request: RoutingRequest) -> DimensionScores:
        repo = request.repo
        sem = request.task.semantic

        scope = min(100, repo.estimated_files * 5 + repo.affected_components * 9)
        if repo.schema_change:
            scope += 10
        if repo.external_api:
            scope += 8

        verification = sem.verification_difficulty
        if not repo.tests_available:
            verification += 22
        if repo.external_api:
            verification += 10
        if repo.schema_change:
            verification += 10

        risk = sem.risk
        risk += 18 if repo.security_sensitive else 0
        risk += 25 if repo.authentication_change else 0
        risk += 25 if repo.authorization_change else 0
        risk += 18 if repo.schema_change else 0
        risk += 30 if repo.production_write else 0
        risk += 35 if repo.destructive_migration else 0

        novelty = sem.novelty
        if repo.existing_pattern:
            novelty -= 20
        if repo.related_commits_found > 0:
            novelty -= min(15, repo.related_commits_found * 3)

        context = sem.context_requirement
        context += min(30, repo.affected_components * 5)
        context += min(20, repo.dependency_depth * 2)

        ambiguity = sem.ambiguity
        if repo.existing_pattern:
            ambiguity -= 8

        architecture = sem.architecture_impact
        if repo.affected_components >= 4:
            architecture += 12
        if repo.authentication_change or repo.authorization_change:
            architecture += 20

        reasoning = sem.reasoning_requirement
        if repo.external_api:
            reasoning += 8
        if not repo.tests_available:
            reasoning += 8

        return DimensionScores(
            scope=self._clamp(scope),
            dependency_depth=self._clamp(repo.dependency_depth * 10),
            ambiguity=self._clamp(ambiguity),
            architecture_impact=self._clamp(architecture),
            verification_difficulty=self._clamp(verification),
            risk=self._clamp(risk),
            context_requirement=self._clamp(context),
            novelty=self._clamp(novelty),
            reasoning_requirement=self._clamp(reasoning),
        )

    def complexity_score(self, dimensions: DimensionScores) -> int:
        weights = self.policy.get("complexity_weights", {})
        total = 0.0
        values = dimensions.model_dump()
        for key, value in values.items():
            total += value * float(weights.get(key, 0.0))
        return self._clamp(total)

    def determine_profile(self, request: RoutingRequest, score: int) -> tuple[str, list[str]]:
        reasons: list[str] = []
        flags = set(request.task.flags)
        repo = request.repo

        if repo.production_write:
            flags.add("production_write")
        if repo.destructive_migration:
            flags.add("destructive_migration")

        critical_triggers = set(self.policy.get("critical_triggers", []))
        if flags & critical_triggers:
            matched = sorted(flags & critical_triggers)
            return "critical", [f"Critical trigger: {item}" for item in matched]

        if score <= int(self.policy["profiles"]["fast"].get("max_score", 29)):
            profile = "fast"
        elif score <= int(self.policy["profiles"]["standard"].get("max_score", 59)):
            profile = "standard"
        elif score <= int(self.policy["profiles"]["complex"].get("max_score", 79)):
            profile = "complex"
        else:
            profile = "critical"
        reasons.append(f"Complexity score {score} maps to {profile}")

        overrides = self.policy.get("minimum_profile_overrides", {})
        facts = {
            "security_sensitive": repo.security_sensitive,
            "schema_change": repo.schema_change,
            "authentication_change": repo.authentication_change,
            "authorization_change": repo.authorization_change,
            "production_write": repo.production_write,
            "destructive_migration": repo.destructive_migration,
        }
        for fact, enabled in facts.items():
            if enabled and fact in overrides:
                minimum = overrides[fact]
                if PROFILE_ORDER.index(profile) < PROFILE_ORDER.index(minimum):
                    reasons.append(f"{fact} raises minimum profile to {minimum}")
                    profile = minimum

        # Semantic floors prevent a deceptively small file scope from routing a
        # reasoning-heavy/debugging task to a weak execution topology.
        sem = request.task.semantic
        if sem.reasoning_requirement >= 80 and (
            sem.verification_difficulty >= 60 or sem.context_requirement >= 70
        ):
            if PROFILE_ORDER.index(profile) < PROFILE_ORDER.index("complex"):
                reasons.append("High reasoning plus verification/context demand raises minimum profile to complex")
                profile = "complex"
        if sem.architecture_impact >= 75:
            if PROFILE_ORDER.index(profile) < PROFILE_ORDER.index("complex"):
                reasons.append("High architecture impact raises minimum profile to complex")
                profile = "complex"
        if sem.risk >= 85:
            if PROFILE_ORDER.index(profile) < PROFILE_ORDER.index("critical"):
                reasons.append("Very high semantic risk raises minimum profile to critical")
                profile = "critical"
        return profile, reasons

    def _human_decision(self, request: RoutingRequest) -> HumanDecision:
        triggers = set(self.policy.get("human_decision_triggers", []))
        present = set(request.task.flags)
        repo = request.repo
        if repo.destructive_migration:
            present.add("destructive_migration")
        if repo.production_write:
            present.add("production_write")
        if repo.authentication_change or repo.authorization_change:
            present.add("security_boundary_change")
        matched = sorted(triggers & present)
        if matched:
            return HumanDecision(
                required=True,
                triggers=matched,
                reason="Important decision boundary reached; implementation review is not required, but a human decision is.",
            )
        return HumanDecision(required=False)

    def _privacy_allowed(self, model: dict[str, Any], privacy: PrivacyPolicy) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        mp = model.get("privacy", {})
        if privacy.private_code and not bool(mp.get("private_code_allowed", False)):
            reasons.append("private code is not allowed by provider policy")
        if not privacy.allow_training_provider and bool(mp.get("training_allowed", True)):
            reasons.append("provider may train on data")
        if privacy.require_zero_retention and not bool(mp.get("zero_retention_supported", False)):
            reasons.append("zero retention is required")
        return not reasons, reasons

    def _capability_match(self, model: dict[str, Any], role: str, dimensions: DimensionScores, profile: str) -> float:
        cap = model.get("capabilities", {})
        required: dict[str, float]
        if role == "planner":
            required = {
                "planning": 0.34,
                "reasoning": 0.34,
                "repo_exploration": 0.18,
                "coding": 0.14,
            }
        elif role == "evaluator":
            required = {
                "review": 0.42,
                "reasoning": 0.30,
                "debugging": 0.18,
                "coding": 0.10,
            }
        else:
            required = {
                "coding": 0.35,
                "debugging": 0.25,
                "reasoning": 0.22,
                "repo_exploration": 0.18,
            }

        score = sum((float(cap.get(name, 0)) / 10.0) * weight for name, weight in required.items())
        difficulty = (
            dimensions.reasoning_requirement
            + dimensions.context_requirement
            + dimensions.verification_difficulty
        ) / 300.0
        if profile in {"complex", "critical"}:
            score *= 0.90 + 0.10 * min(1.0, score / max(0.45, difficulty))
        return max(0.0, min(1.0, score))

    def _model_score(
        self,
        model_id: str,
        model: dict[str, Any],
        role: str,
        dimensions: DimensionScores,
        profile: str,
        state: ProviderState,
        preferred_ids: list[str],
    ) -> tuple[float, float, list[str]]:
        scoring = self.policy.get("scoring", {})
        capability = self._capability_match(model, role, dimensions, profile)
        predicted = state.predicted_success if state.predicted_success is not None else float(model.get("base_success", scoring.get("fallback_unknown_success", 0.7)))
        score = capability * float(scoring.get("capability_weight", 0.52))
        score += predicted * float(scoring.get("predicted_success_weight", 0.30))

        reasons = [f"capability={capability:.2f}", f"predicted_success={predicted:.2f}"]

        if model_id in preferred_ids:
            position = preferred_ids.index(model_id)
            profile_cfg = self.policy.get("profiles", {}).get(profile, {})
            preferred_order_bonus = profile_cfg.get(
                "preferred_order_bonus", scoring.get("preferred_order_bonus", 0.08)
            )
            bonus = float(preferred_order_bonus) * max(0.25, 1.0 - position * 0.25)
            score += bonus
            reasons.append(f"preferred-order bonus={bonus:.3f}")

        cost_class = model.get("cost_class", "premium")
        if cost_class == "free":
            score += float(scoring.get("free_cost_bonus", 0.06))
            reasons.append("free cost bonus")
        elif cost_class == "subscription":
            score += float(scoring.get("subscription_cost_bonus", 0.04))
            reasons.append("subscription pool bonus")
        elif cost_class == "ultra_low":
            score += float(scoring.get("ultra_low_cost_bonus", 0.03))
            reasons.append("ultra-low cost bonus")
        elif cost_class == "premium":
            score -= float(scoring.get("premium_cost_penalty", 0.04))
            reasons.append("premium cost penalty")
        elif cost_class == "scarce":
            score -= float(scoring.get("scarce_cost_penalty", 0.10))
            reasons.append("scarce quota penalty")

        quota_penalty = state.quota_pressure * float(scoring.get("quota_pressure_penalty", 0.12))
        error_penalty = state.error_rate * float(scoring.get("error_rate_penalty", 0.12))
        latency_scale = min(1.0, state.latency_ms / 10000.0)
        latency_penalty = latency_scale * float(scoring.get("latency_penalty", 0.03))
        score -= quota_penalty + error_penalty + latency_penalty
        if quota_penalty:
            reasons.append(f"quota penalty={quota_penalty:.3f}")
        if error_penalty:
            reasons.append(f"error-rate penalty={error_penalty:.3f}")
        if latency_penalty:
            reasons.append(f"latency penalty={latency_penalty:.3f}")
        return score, predicted, reasons

    def select_model(
        self,
        *,
        role: str,
        role_names: list[str],
        preferred_ids: list[str],
        request: RoutingRequest,
        dimensions: DimensionScores,
        profile: str,
        exclude_providers: set[str] | None = None,
        minimum_tier_index: int | None = None,
    ) -> tuple[ModelChoice, dict[str, list[str]]]:
        privacy = self._privacy(request)
        rejected: dict[str, list[str]] = {}
        candidates: list[tuple[float, str, dict[str, Any], float, list[str]]] = []
        exclude_providers = exclude_providers or set()
        tier_order = ["utility", "balanced", "strong", "premium", "frontier"]

        for model_id, model in self.models.items():
            reasons: list[str] = []
            if model.get("kind") != "agent":
                reasons.append("not an agent")
            allowed_profiles = model.get("allowed_profiles")
            if allowed_profiles is not None and profile not in set(allowed_profiles):
                reasons.append(f"profile {profile!r} is not allowed")
            if not set(role_names) & set(model.get("roles", [])):
                reasons.append(f"missing required role: {role_names}")
            if model.get("provider") in exclude_providers:
                reasons.append("provider excluded for model-family diversity")
            if minimum_tier_index is not None:
                tier = model.get("tier", "utility")
                if tier not in tier_order or tier_order.index(tier) < minimum_tier_index:
                    reasons.append("below escalation tier")

            allowed, privacy_reasons = self._privacy_allowed(model, privacy)
            if not allowed:
                reasons.extend(privacy_reasons)

            model_state = request.provider_state.get(model_id, ProviderState())
            provider_state = request.provider_state.get(f"provider:{model.get('provider')}", ProviderState())
            state = ProviderState(
                healthy=model_state.healthy and provider_state.healthy,
                quota_pressure=max(model_state.quota_pressure, provider_state.quota_pressure),
                error_rate=max(model_state.error_rate, provider_state.error_rate),
                latency_ms=max(model_state.latency_ms, provider_state.latency_ms),
                predicted_success=model_state.predicted_success if model_state.predicted_success is not None else provider_state.predicted_success,
                available=model_state.available and provider_state.available,
            )
            if not state.available:
                reasons.append("provider/model unavailable")
            if not state.healthy:
                reasons.append("provider/model unhealthy")

            if reasons:
                rejected[model_id] = reasons
                continue

            score, predicted, scoring_reasons = self._model_score(
                model_id, model, role, dimensions, profile, state, preferred_ids
            )
            candidates.append((score, model_id, model, predicted, scoring_reasons))

        if not candidates:
            raise RuntimeError(f"No eligible model for role={role}; rejected={rejected}")

        candidates.sort(key=lambda row: row[0], reverse=True)
        score, model_id, model, predicted, reasons = candidates[0]
        return ModelChoice(
            id=model_id,
            provider=model["provider"],
            adapter=model["adapter"],
            model=str(model["model"]),
            score=round(score, 4),
            predicted_success=round(predicted, 4),
            reasons=reasons,
        ), rejected

    def _budget(self, profile: str) -> Budget:
        cfg = self.policy["profiles"][profile]
        return Budget(
            max_model_calls=cfg["max_model_calls"],
            max_input_tokens=cfg["max_input_tokens"],
            max_output_tokens=cfg["max_output_tokens"],
            max_tool_calls=cfg["max_tool_calls"],
            max_iterations=cfg["max_iterations"],
            max_repair_iterations=cfg["max_repair_iterations"],
            max_escalations=cfg["max_escalations"],
            max_provider_failovers=cfg.get("max_provider_failovers", 2),
            max_model_failovers=cfg.get("max_model_failovers", 2),
            max_test_runs=cfg["max_test_runs"],
            max_wall_time_minutes=cfg["max_wall_time_minutes"],
            soft_cost_usd=float(cfg["soft_cost_usd"]),
            hard_cost_usd=float(cfg["hard_cost_usd"]),
            max_changed_files=cfg["max_changed_files"],
        )

    def route(self, request: RoutingRequest) -> RoutingResponse:
        dimensions = self.compute_dimensions(request)
        complexity = self.complexity_score(dimensions)
        profile, profile_reasons = self.determine_profile(request, complexity)
        profile_cfg = self.policy["profiles"][profile]

        rejected_all: dict[str, list[str]] = {}
        executor, rejected = self.select_model(
            role="executor",
            role_names=profile_cfg.get("executor_roles", ["executor"]),
            preferred_ids=profile_cfg.get("preferred_executor_ids", []),
            request=request,
            dimensions=dimensions,
            profile=profile,
        )
        rejected_all.update(rejected)

        planner = None
        if profile_cfg.get("planner", False):
            planner, rejected = self.select_model(
                role="planner",
                role_names=profile_cfg.get("planner_roles", ["planner"]),
                preferred_ids=profile_cfg.get("preferred_planner_ids", []),
                request=request,
                dimensions=dimensions,
                profile=profile,
            )
            rejected_all.update(rejected)

        evaluator = None
        if profile_cfg.get("evaluator", False):
            try:
                evaluator, rejected = self.select_model(
                    role="evaluator",
                    role_names=profile_cfg.get("evaluator_roles", ["reviewer"]),
                    preferred_ids=profile_cfg.get("preferred_evaluator_ids", []),
                    request=request,
                    dimensions=dimensions,
                    profile=profile,
                    exclude_providers={executor.provider},
                )
            except RuntimeError:
                evaluator, rejected = self.select_model(
                    role="evaluator",
                    role_names=profile_cfg.get("evaluator_roles", ["reviewer"]),
                    preferred_ids=profile_cfg.get("preferred_evaluator_ids", []),
                    request=request,
                    dimensions=dimensions,
                    profile=profile,
                )
            rejected_all.update(rejected)

        project = self._project(request.project_id)
        autonomy = project.get("autonomy", {})
        permissions = {
            "commit": bool(autonomy.get("allow_commit", True)),
            "push_ai_branch": bool(autonomy.get("allow_push_ai_branch", True)),
            "create_pr": bool(autonomy.get("allow_create_pr", True)),
            "auto_merge_low_risk": bool(autonomy.get("allow_auto_merge_low_risk", True)) and profile in {"fast", "standard"},
            "production_deploy": bool(autonomy.get("allow_production_deploy", False)),
        }

        dod_required = ["targeted_tests_pass", "static_analysis_pass", "no_unexpected_scope"]
        if "material_change_required" in request.task.flags:
            dod_required.append("material_change")
        if profile in {"complex", "critical"}:
            dod_required.append("evaluator_pass")
        definition_of_done = {
            "required": dod_required,
            "forbidden": ["unapproved_production_write", "budget_override", "scope_expansion_without_reassessment"],
        }

        reasons = profile_reasons + [
            f"Executor selected: {executor.id}",
            f"Analysis depth: {profile_cfg.get('analysis_depth', 1)}",
        ]
        if planner:
            reasons.append(f"Planner selected: {planner.id}")
        if evaluator:
            reasons.append(f"Independent evaluator selected: {evaluator.id}")
        if request.repo.existing_pattern:
            reasons.append("Existing implementation pattern lowers novelty/ambiguity")
        if not request.repo.tests_available:
            reasons.append("Missing tests increases verification difficulty")

        return RoutingResponse(
            job_id=request.job_id,
            project_id=request.project_id,
            source_commit=request.source_commit,
            complexity_score=complexity,
            dimensions=dimensions,
            strategy=ExecutionStrategy(
                profile=profile,
                analysis_depth=int(profile_cfg.get("analysis_depth", 1)),
                planner=planner,
                executor=executor,
                evaluator=evaluator,
                human_decision=self._human_decision(request),
                budget=self._budget(profile),
                anti_loop=deepcopy(self.policy.get("anti_loop", {})),
                permissions=permissions,
                definition_of_done=definition_of_done,
                reasons=reasons,
            ),
            rejected_candidates=rejected_all,
            policy_version=int(self.policy.get("version", 1)),
            registry_version=int(self.models_doc.get("version", 1)),
        )

    @staticmethod
    def _repeated_failure(progress: ExecutionProgress, limit: int) -> tuple[bool, str | None]:
        if not progress.failure_fingerprints:
            return False, None
        counts = Counter(progress.failure_fingerprints)
        fingerprint, count = counts.most_common(1)[0]
        return count > limit, fingerprint if count > limit else None

    @staticmethod
    def _oscillation(progress: ExecutionProgress, limit: int) -> bool:
        hashes = progress.diff_hashes
        if len(hashes) < 3:
            return False
        # Detect A -> B -> A and repeated variants of it.
        oscillations = 0
        for idx in range(2, len(hashes)):
            if hashes[idx] == hashes[idx - 2] and hashes[idx] != hashes[idx - 1]:
                oscillations += 1
        return oscillations >= limit

    def reassess(self, request: ReassessRequest) -> ReassessResponse:
        route = request.route
        progress = request.progress
        budget = route.strategy.budget
        anti = route.strategy.anti_loop
        signals: list[str] = []

        remaining = {
            "model_calls": max(0, budget.max_model_calls - progress.model_calls),
            "input_tokens": max(0, budget.max_input_tokens - progress.input_tokens),
            "output_tokens": max(0, budget.max_output_tokens - progress.output_tokens),
            "tool_calls": max(0, budget.max_tool_calls - progress.tool_calls),
            "iterations": max(0, budget.max_iterations - progress.iteration),
            "repair_iterations": max(0, budget.max_repair_iterations - progress.repair_iterations),
            "escalations": max(0, budget.max_escalations - progress.escalations),
            "provider_failovers": max(0, budget.max_provider_failovers - progress.provider_failovers),
            "model_failovers": max(0, budget.max_model_failovers - progress.model_failovers),
            "test_runs": max(0, budget.max_test_runs - progress.test_runs),
            "wall_time_minutes": max(0.0, budget.max_wall_time_minutes - progress.elapsed_minutes),
            "cost_usd": round(max(0.0, budget.hard_cost_usd - progress.cost_usd), 4),
            "changed_files": max(0, budget.max_changed_files - progress.changed_files),
        }

        hard_limits = [
            (progress.model_calls >= budget.max_model_calls, "model-call budget exhausted"),
            (progress.input_tokens >= budget.max_input_tokens, "input-token budget exhausted"),
            (progress.output_tokens >= budget.max_output_tokens, "output-token budget exhausted"),
            (progress.tool_calls >= budget.max_tool_calls, "tool-call budget exhausted"),
            (progress.iteration >= budget.max_iterations, "iteration budget exhausted"),
            (progress.repair_iterations >= budget.max_repair_iterations, "repair budget exhausted"),
            (progress.provider_failovers > budget.max_provider_failovers, "provider-failover budget exhausted"),
            (progress.model_failovers > budget.max_model_failovers, "model-failover budget exhausted"),
            (progress.test_runs >= budget.max_test_runs, "test-run budget exhausted"),
            (progress.elapsed_minutes >= budget.max_wall_time_minutes, "wall-time budget exhausted"),
            (progress.cost_usd >= budget.hard_cost_usd, "hard cost budget exhausted"),
        ]
        for hit, reason in hard_limits:
            if hit:
                return ReassessResponse(
                    action="stop",
                    reason=reason,
                    current_profile=route.strategy.profile,
                    remaining=remaining,
                    signals=["hard_budget_guard"],
                )

        material_required = "material_change" in route.strategy.definition_of_done.get("required", [])
        material_ok = (not material_required) or progress.material_change_present
        if progress.required_checks_passed and progress.tests_passed and progress.agent_succeeded and material_ok:
            return ReassessResponse(
                action="complete",
                reason="Definition-of-done checks passed",
                current_profile=route.strategy.profile,
                remaining=remaining,
                signals=["done"],
            )
        if progress.required_checks_passed and progress.tests_passed and material_required and not progress.material_change_present:
            signals.append("material_change_missing")
        if not progress.agent_succeeded and progress.last_agent_failure_kind:
            signals.append(f"agent_failure:{progress.last_agent_failure_kind}")

        if progress.important_decision_flags:
            human = HumanDecision(
                required=True,
                triggers=progress.important_decision_flags,
                reason="Execution discovered an important decision boundary.",
            )
            return ReassessResponse(
                action="human_decision",
                reason="Human decision required; routine implementation review is not requested",
                current_profile=route.strategy.profile,
                human_decision=human,
                remaining=remaining,
                signals=["decision_boundary"],
            )

        if progress.changed_files > budget.max_changed_files or progress.unexpected_scope:
            signals.append("scope_expansion")

        repeat_limit = int(anti.get("same_failure_fingerprint_limit", 2))
        repeated, fingerprint = self._repeated_failure(progress, repeat_limit)
        if repeated:
            signals.append(f"repeated_failure:{fingerprint}")

        oscillation = self._oscillation(progress, int(anti.get("diff_oscillation_limit", 2)))
        if oscillation:
            signals.append("diff_oscillation")

        no_progress_limit = int(anti.get("no_progress_iterations", 2))
        if len(progress.progress_markers) >= no_progress_limit + 1:
            tail = progress.progress_markers[-(no_progress_limit + 1):]
            if len(set(tail)) == 1:
                signals.append("no_progress")

        soft_budget_hit = progress.cost_usd >= budget.soft_cost_usd
        if soft_budget_hit:
            signals.append("soft_cost_budget")

        should_escalate = bool(signals) or progress.repair_iterations >= max(1, budget.max_repair_iterations - 1)
        if should_escalate and progress.escalations < budget.max_escalations:
            current = route.strategy.executor
            model = self.models.get(current.id, {})
            tier_order = ["utility", "balanced", "strong", "premium", "frontier"]
            current_tier = model.get("tier", "balanced")
            current_index = tier_order.index(current_tier) if current_tier in tier_order else 1
            next_min = min(len(tier_order) - 1, current_index + 1)

            # Reconstruct a routing request from route metadata is intentionally avoided in v1.
            # Escalation searches eligible executor models using the original dimensions and permissive privacy.
            pseudo = RoutingRequest(
                job_id=route.job_id,
                project_id=route.project_id,
                repository="reassessment",
                source_commit=route.source_commit,
                task={"title": "Reassessed execution", "semantic": {
                    "ambiguity": route.dimensions.ambiguity,
                    "architecture_impact": route.dimensions.architecture_impact,
                    "verification_difficulty": route.dimensions.verification_difficulty,
                    "risk": route.dimensions.risk,
                    "context_requirement": route.dimensions.context_requirement,
                    "novelty": route.dimensions.novelty,
                    "reasoning_requirement": route.dimensions.reasoning_requirement,
                }},
                repo={"estimated_files": max(1, progress.changed_files)},
                provider_state=request.provider_state,
            )
            profile_cfg = self.policy["profiles"][route.strategy.profile]
            try:
                next_executor, _ = self.select_model(
                    role="executor",
                    role_names=profile_cfg.get("executor_roles", ["executor"]),
                    preferred_ids=profile_cfg.get("preferred_executor_ids", []),
                    request=pseudo,
                    dimensions=route.dimensions,
                    profile=route.strategy.profile,
                    minimum_tier_index=next_min,
                )
                if next_executor.id != current.id:
                    return ReassessResponse(
                        action="escalate",
                        reason="Progress guard or soft budget indicates current strategy should escalate",
                        current_profile=route.strategy.profile,
                        next_executor=next_executor,
                        remaining=remaining,
                        signals=signals,
                    )
            except RuntimeError:
                pass

        if repeated or oscillation:
            return ReassessResponse(
                action="stop",
                reason="Circuit breaker: repeated failure or solution oscillation without a valid escalation path",
                current_profile=route.strategy.profile,
                remaining=remaining,
                signals=signals,
            )

        return ReassessResponse(
            action="continue",
            reason="Within budget and no circuit-break condition detected",
            current_profile=route.strategy.profile,
            remaining=remaining,
            signals=signals,
        )
