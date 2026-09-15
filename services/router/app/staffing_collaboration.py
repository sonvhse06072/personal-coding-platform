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
    """Add provider-independent eligibility policy for collaboration roles.

    Capability scoring stays in the base staffing layer so there is one scoring
    definition per logical role. This extension only supplies which existing
    model capabilities/roles are eligible and their cost-aware preference order.
    """

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
