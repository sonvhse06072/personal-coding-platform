from __future__ import annotations

from typing import Any

from .engine_budget import RouterEngine as BudgetRouterEngine
from .schemas import (
    DimensionScores,
    RoutingRequest,
    StaffingRequest,
    StaffingResponse,
)


class RouterEngine(BudgetRouterEngine):
    """Router extension for staffing logical team roles without product reasoning."""

    def _capability_match(
        self,
        model: dict[str, Any],
        role: str,
        dimensions: DimensionScores,
        profile: str,
    ) -> float:
        if role != "product_manager":
            return super()._capability_match(model, role, dimensions, profile)

        cap = model.get("capabilities", {})
        required = {
            "planning": 0.30,
            "reasoning": 0.30,
            "structured_output": 0.22,
            "review": 0.10,
            "repo_exploration": 0.08,
        }
        score = sum((float(cap.get(name, 0)) / 10.0) * weight for name, weight in required.items())
        difficulty = (
            dimensions.reasoning_requirement
            + dimensions.context_requirement
            + dimensions.ambiguity
            + dimensions.architecture_impact
        ) / 400.0
        if profile in {"complex", "critical"}:
            score *= 0.90 + 0.10 * min(1.0, score / max(0.45, difficulty))
        return max(0.0, min(1.0, score))

    @staticmethod
    def _staffing_dimensions(request: StaffingRequest) -> DimensionScores:
        semantic = request.semantic
        return DimensionScores(
            scope=10,
            dependency_depth=10,
            ambiguity=semantic.ambiguity,
            architecture_impact=semantic.architecture_impact,
            verification_difficulty=semantic.verification_difficulty,
            risk=semantic.risk,
            context_requirement=semantic.context_requirement,
            novelty=semantic.novelty,
            reasoning_requirement=semantic.reasoning_requirement,
        )

    def staff(self, request: StaffingRequest) -> StaffingResponse:
        role_cfg = (self.policy.get("staffing_roles", {}) or {}).get(request.role)
        if not isinstance(role_cfg, dict):
            raise RuntimeError(f"Unknown or unconfigured logical role: {request.role}")

        allowed_profiles = list(role_cfg.get("allowed_profiles", []))
        if allowed_profiles and request.profile not in allowed_profiles:
            raise RuntimeError(
                f"Profile {request.profile!r} is not allowed for logical role {request.role!r}"
            )

        dimensions = self._staffing_dimensions(request)
        pseudo = RoutingRequest(
            job_id=request.request_id,
            project_id=request.project_id,
            repository="logical-role-staffing",
            source_commit="staffing",
            task={
                "title": f"Staff logical role {request.role}",
                "task_type": request.role,
                "semantic": request.semantic.model_dump(mode="json"),
            },
            repo={
                "estimated_files": 1,
                "affected_components": 1,
                "dependency_depth": 1,
                "tests_available": True,
                "existing_pattern": True,
            },
            provider_state=request.provider_state,
        )
        choice, rejected = self.select_model(
            role=request.role,
            role_names=list(role_cfg.get("model_roles", [request.role])),
            preferred_ids=list(role_cfg.get("preferred_ids", [])),
            request=pseudo,
            dimensions=dimensions,
            profile=request.profile,
        )
        return StaffingResponse(
            request_id=request.request_id,
            project_id=request.project_id,
            role=request.role,
            profile=request.profile,
            choice=choice,
            rejected_candidates=rejected,
            policy_version=int(self.policy.get("version", 1)),
            registry_version=int(self.models_doc.get("version", 1)),
        )
