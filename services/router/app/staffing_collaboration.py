from __future__ import annotations

from typing import Any

from .schemas import RoutingRequest, StaffingRequest, StaffingResponse
from .staffing import RouterEngine as BaseRouterEngine


_COLLABORATION_ROLE_POLICY: dict[str, dict[str, Any]] = {
    "consultant": {
        "model_roles": ["planner", "reviewer", "explore"],
        "preferred_ids": [
            "antigravity_free",
            "codex_terra",
            "openrouter_qwen3_coder_free",
            "antigravity_flash_high",
            "antigravity_gemini_pro",
        ],
    },
    "test_engineer": {
        "model_roles": ["test_writer", "reviewer"],
        "preferred_ids": [
            "antigravity_free",
            "codex_luna",
            "codex_terra",
            "openrouter_qwen3_coder_free",
            "antigravity_flash_high",
        ],
    },
    "debugger": {
        "model_roles": ["debugger"],
        "preferred_ids": [
            "codex_terra",
            "antigravity_flash_high",
            "antigravity_gemini_pro",
            "antigravity_claude_sonnet",
            "codex_sol",
        ],
    },
    "security_specialist": {
        "model_roles": ["architecture"],
        "preferred_ids": [
            "antigravity_gemini_pro",
            "codex_sol",
        ],
    },
    "reviewer": {
        "model_roles": ["reviewer"],
        "preferred_ids": [
            "openrouter_qwen3_coder_free",
            "antigravity_claude_sonnet",
            "codex_terra",
            "antigravity_gemini_pro",
            "antigravity_flash_high",
            "antigravity_free",
        ],
    },
}
_REASONING_BY_PROFILE = {
    "fast": "low",
    "standard": "low",
    "complex": "medium",
    "critical": "high",
}


class RouterEngine(BaseRouterEngine):
    """Add provider-independent staffing for bounded collaboration roles."""

    def _capability_match(self, model, role, dimensions, profile):
        cap = model.get("capabilities", {})
        weights: dict[str, float] | None = None
        if role == "consultant":
            weights = {
                "reasoning": 0.30,
                "planning": 0.24,
                "repo_exploration": 0.22,
                "review": 0.16,
                "structured_output": 0.08,
            }
        elif role == "test_engineer":
            weights = {
                "review": 0.28,
                "debugging": 0.24,
                "structured_output": 0.18,
                "repo_exploration": 0.16,
                "coding": 0.14,
            }
        elif role == "debugger":
            weights = {
                "debugging": 0.36,
                "reasoning": 0.28,
                "repo_exploration": 0.20,
                "review": 0.16,
            }
        elif role == "security_specialist":
            weights = {
                "reasoning": 0.32,
                "review": 0.28,
                "planning": 0.18,
                "debugging": 0.14,
                "structured_output": 0.08,
            }
        elif role == "reviewer":
            weights = {
                "review": 0.38,
                "reasoning": 0.28,
                "debugging": 0.16,
                "repo_exploration": 0.10,
                "structured_output": 0.08,
            }
        if weights is None:
            return super()._capability_match(model, role, dimensions, profile)
        score = sum((float(cap.get(name, 0)) / 10.0) * weight for name, weight in weights.items())
        difficulty = (
            dimensions.reasoning_requirement
            + dimensions.context_requirement
            + dimensions.verification_difficulty
            + dimensions.risk
        ) / 400.0
        if profile in {"complex", "critical"}:
            score *= 0.90 + 0.10 * min(1.0, score / max(0.45, difficulty))
        return max(0.0, min(1.0, score))

    def staff(self, request: StaffingRequest) -> StaffingResponse:
        role_cfg = _COLLABORATION_ROLE_POLICY.get(request.role)
        if role_cfg is None:
            return super().staff(request)

        dimensions = self._staffing_dimensions(request)
        pseudo = RoutingRequest(
            job_id=request.request_id,
            project_id=request.project_id,
            repository="bounded-collaboration-staffing",
            source_commit="staffing",
            task={
                "title": f"Staff bounded collaboration role {request.role}",
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
            role_names=list(role_cfg["model_roles"]),
            preferred_ids=list(role_cfg["preferred_ids"]),
            request=pseudo,
            dimensions=dimensions,
            profile=request.profile,
        )
        self._apply_reasoning(choice, _REASONING_BY_PROFILE.get(request.profile))
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


__all__ = ["RouterEngine"]
