from __future__ import annotations

from app.config import clear_config_cache, get_config
from app.model_capabilities import reasoning_capability
from app.schemas import StaffingRequest
from app.staffing_collaboration import RouterEngine


def make_engine() -> RouterEngine:
    clear_config_cache()
    return RouterEngine(get_config())


def request(role: str, **overrides) -> StaffingRequest:
    data = {
        "request_id": f"ct-{role}-1",
        "project_id": "default",
        "role": role,
        "profile": "standard",
        "semantic": {
            "ambiguity": 45,
            "architecture_impact": 30,
            "verification_difficulty": 55,
            "risk": 45,
            "context_requirement": 60,
            "novelty": 40,
            "reasoning_requirement": 70,
        },
    }
    data.update(overrides)
    return StaffingRequest(**data)


def test_collaboration_roles_are_staffed_by_logical_capability_not_model_identity() -> None:
    engine = make_engine()

    role_to_model_roles = {
        "consultant": {"planner", "reviewer", "explore"},
        "test_engineer": {"test_writer", "reviewer"},
        "debugger": {"debugger"},
        "security_specialist": {"architecture"},
        "reviewer": {"reviewer"},
    }
    for role, allowed_model_roles in role_to_model_roles.items():
        result = engine.staff(request(role))
        assert result.role == role
        assert set(engine.models[result.choice.id]["roles"]) & allowed_model_roles
        capability = reasoning_capability(
            result.choice.id,
            engine.models[result.choice.id],
        )
        if capability.supports_explicit_effort:
            assert result.choice.reasoning_effort == "low"
        else:
            assert result.choice.reasoning_effort is None


def test_security_specialist_uses_architecture_capable_model() -> None:
    engine = make_engine()
    result = engine.staff(request("security_specialist"))

    assert "architecture" in engine.models[result.choice.id]["roles"]
    assert result.choice.id in {"antigravity_gemini_pro", "codex_sol"}


def test_collaboration_staffing_respects_provider_state_and_can_fallback() -> None:
    engine = make_engine()
    first = engine.staff(request("reviewer"))
    result = engine.staff(
        request(
            "reviewer",
            provider_state={
                first.choice.id: {"available": False, "healthy": False},
                f"provider:{first.choice.provider}": {"available": False, "healthy": False},
            },
        )
    )

    assert result.choice.id != first.choice.id
    assert result.choice.provider != first.choice.provider or first.choice.provider == "google_antigravity"


def test_product_manager_staffing_remains_backward_compatible() -> None:
    engine = make_engine()
    result = engine.staff(request("product_manager"))

    assert result.role == "product_manager"
    assert "product_manager" in engine.models[result.choice.id]["roles"]
