from __future__ import annotations

import re
from typing import Any

from .adapters.base import AgentAdapter, InvocationCapabilities


_PHASE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REASON_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_CONTEXT_PHASES = 32


def agent_verification_capability_context(
    adapter: AgentAdapter,
    *,
    mode: str,
    project: dict[str, Any],
    verification: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build bounded prompt context from adapter, project and final evidence."""
    capability_method = getattr(adapter, "invocation_capabilities", None)
    capabilities = (
        capability_method(mode)
        if callable(capability_method)
        else InvocationCapabilities()
    )
    if capabilities.local_listener:
        return None

    ddev = project.get("ddev") or {}
    if not isinstance(ddev, dict) or not ddev.get("enabled", False):
        return None
    phase_metadata = ddev.get("verification_phase_capabilities") or {}
    if not isinstance(phase_metadata, dict):
        return None

    required_phases: set[str] | None = None
    if mode == "evaluate":
        required_phases = {
            str(item.get("phase") or "").strip()
            for item in ((verification or {}).get("phases") or [])
            if isinstance(item, dict) and item.get("required_for_final") is True
        }

    phases: list[str] = []
    for raw_phase, raw_metadata in phase_metadata.items():
        phase = str(raw_phase).strip()
        if not _PHASE_NAME.fullmatch(phase) or not isinstance(raw_metadata, dict):
            continue
        requirements = raw_metadata.get("requires") or []
        if (
            isinstance(requirements, list)
            and "local_listener" in requirements
            and isinstance(ddev.get(phase), list)
            and bool(ddev.get(phase))
            and (required_phases is None or phase in required_phases)
        ):
            phases.append(phase)

    phases = sorted(set(phases))[:_MAX_CONTEXT_PHASES]
    if not phases:
        return None
    reason = str(capabilities.reason or "").strip()
    if not _REASON_NAME.fullmatch(reason):
        reason = "adapter_local_listener_unavailable"
    return {
        "unavailable_capabilities": ["local_listener"],
        "runtime_owned_verification_phases": phases,
        "reason": reason,
    }
