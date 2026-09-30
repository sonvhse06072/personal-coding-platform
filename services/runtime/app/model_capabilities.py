from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REASONING_EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")
_REASONING_EFFORT_SET = frozenset(REASONING_EFFORT_ORDER)


class ModelCapabilityError(RuntimeError):
    """A durable model choice is incompatible with the mounted registry."""


@dataclass(frozen=True)
class ReasoningCapability:
    supports_explicit_effort: bool
    allowed_efforts: tuple[str, ...]


def reasoning_capability(
    model_id: str,
    model: Mapping[str, Any],
) -> ReasoningCapability:
    supports_raw = model.get("supports_reasoning_effort")
    efforts_raw = model.get("reasoning_efforts")

    if supports_raw is not None and not isinstance(supports_raw, bool):
        raise ValueError(
            f"Model {model_id!r} supports_reasoning_effort must be a boolean"
        )
    if efforts_raw is not None and not isinstance(efforts_raw, list):
        raise ValueError(f"Model {model_id!r} reasoning_efforts must be a list")
    if supports_raw is False:
        if efforts_raw is not None:
            raise ValueError(
                f"Model {model_id!r} disables reasoning effort but also declares reasoning_efforts"
            )
        return ReasoningCapability(False, ())
    if efforts_raw is None:
        if supports_raw is True:
            raise ValueError(
                f"Model {model_id!r} enables reasoning effort without reasoning_efforts"
            )
        return ReasoningCapability(False, ())
    if not efforts_raw:
        raise ValueError(f"Model {model_id!r} reasoning_efforts must not be empty")
    if any(not isinstance(item, str) or item not in _REASONING_EFFORT_SET for item in efforts_raw):
        raise ValueError(
            f"Model {model_id!r} reasoning_efforts contains an unknown value"
        )
    if len(set(efforts_raw)) != len(efforts_raw):
        raise ValueError(f"Model {model_id!r} reasoning_efforts contains duplicates")
    ordered = tuple(item for item in REASONING_EFFORT_ORDER if item in efforts_raw)
    if tuple(efforts_raw) != ordered:
        raise ValueError(
            f"Model {model_id!r} reasoning_efforts must follow canonical order"
        )
    return ReasoningCapability(True, ordered)


def validate_model_registry(document: Mapping[str, Any]) -> None:
    models = document.get("models")
    if not isinstance(models, dict):
        raise ValueError("Model registry models must be an object")
    for model_id, model in models.items():
        if not isinstance(model_id, str) or not model_id or not isinstance(model, dict):
            raise ValueError("Model registry entries must be named objects")
        reasoning_capability(model_id, model)


def validate_model_choice(
    choice: Mapping[str, Any],
    document: Mapping[str, Any] | None = None,
) -> ReasoningCapability:
    """Validate the durable PCP id/adapter/upstream-model/effort tuple."""
    if document is None:
        from .config import models_doc

        document = models_doc()

    model_id = str(choice.get("id") or "").strip()
    adapter = str(choice.get("adapter") or "").strip()
    upstream_model = str(choice.get("model") or "").strip()
    effort_raw = choice.get("reasoning_effort")
    effort = None if effort_raw is None else str(effort_raw).strip()
    models = document.get("models") or {}
    registered = models.get(model_id)
    if not model_id or not isinstance(registered, dict):
        raise ModelCapabilityError(f"Unknown PCP model id: {model_id!r}")
    if adapter != str(registered.get("adapter") or ""):
        raise ModelCapabilityError(
            f"Adapter mismatch for PCP model {model_id!r}"
        )
    if upstream_model != str(registered.get("model") or ""):
        raise ModelCapabilityError(
            f"Upstream model mismatch for PCP model {model_id!r}"
        )

    capability = reasoning_capability(model_id, registered)
    if effort is not None and effort not in capability.allowed_efforts:
        raise ModelCapabilityError(
            f"Reasoning effort {effort!r} is unsupported for PCP model {model_id!r}"
        )
    return capability


def next_supported_effort(
    choice: Mapping[str, Any],
    ceiling: str | None,
) -> str | None:
    capability = validate_model_choice(choice)
    if not capability.supports_explicit_effort:
        return None
    current = choice.get("reasoning_effort")
    if current is None:
        return None
    current = str(current)
    if ceiling not in _REASONING_EFFORT_SET:
        if ceiling is None:
            return None
        raise ModelCapabilityError(f"Unknown reasoning ceiling: {ceiling!r}")
    current_index = REASONING_EFFORT_ORDER.index(current)
    ceiling_index = REASONING_EFFORT_ORDER.index(str(ceiling))
    return next(
        (
            effort
            for effort in capability.allowed_efforts
            if current_index < REASONING_EFFORT_ORDER.index(effort) <= ceiling_index
        ),
        None,
    )
