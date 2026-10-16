from __future__ import annotations

import re
from typing import Any

from .adapters.base import AgentAdapter, InvocationCapabilities


_PHASE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REASON_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_CONTEXT_PHASES = 32


def _bounded_reason(value: str | None, fallback: str) -> str:
    reason = str(value or "").strip()
    return reason if _REASON_NAME.fullmatch(reason) else fallback


def agent_verification_capability_context(
    adapter: AgentAdapter,
    *,
    mode: str,
    project: dict[str, Any],
    verification: dict[str, Any] | None = None,
    scoped_developer_broker: bool = False,
) -> dict[str, Any] | None:
    """Build bounded prompt context from adapter, project and final evidence."""
    capability_method = getattr(adapter, "invocation_capabilities", None)
    capabilities = (
        capability_method(mode)
        if callable(capability_method)
        else InvocationCapabilities()
    )

    declared_unavailable = {
        "local_listener": (
            not capabilities.local_listener,
            _bounded_reason(
                capabilities.reason,
                "adapter_local_listener_unavailable",
            ),
        ),
        "php_runtime": (
            not capabilities.php_runtime,
            _bounded_reason(
                capabilities.php_runtime_reason,
                "adapter_php_runtime_unavailable",
            ),
        ),
    }
    if not any(unavailable for unavailable, _reason in declared_unavailable.values()):
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

    capability_phases: dict[str, list[str]] = {}
    capability_reasons: dict[str, str] = {}
    for capability, (unavailable, reason) in declared_unavailable.items():
        if not unavailable:
            continue
        phases: list[str] = []
        for raw_phase, raw_metadata in phase_metadata.items():
            phase = str(raw_phase).strip()
            if not _PHASE_NAME.fullmatch(phase) or not isinstance(raw_metadata, dict):
                continue
            requirements = raw_metadata.get("requires") or []
            if (
                isinstance(requirements, list)
                and capability in requirements
                and isinstance(ddev.get(phase), list)
                and bool(ddev.get(phase))
                and (required_phases is None or phase in required_phases)
            ):
                phases.append(phase)
        phases = sorted(set(phases))[:_MAX_CONTEXT_PHASES]
        if phases:
            capability_phases[capability] = phases
            capability_reasons[capability] = reason

    if not capability_phases:
        return None

    unavailable_capabilities = sorted(capability_phases)
    all_phases = sorted(
        {
            phase
            for phases in capability_phases.values()
            for phase in phases
        }
    )[:_MAX_CONTEXT_PHASES]
    result: dict[str, Any] = {
        "unavailable_capabilities": unavailable_capabilities,
        "runtime_owned_verification_phases": all_phases,
        "reason": (
            capability_reasons[unavailable_capabilities[0]]
            if len(unavailable_capabilities) == 1
            else "multiple_capabilities_unavailable"
        ),
    }
    if len(unavailable_capabilities) > 1:
        result["capability_phases"] = capability_phases
        result["reasons"] = capability_reasons
    # This is a *prompt hint* about an independently admitted, scoped tool,
    # never an assertion that the local sandbox gained PHP/network or that
    # any Executor check passed. Never derive this flag from project prose.
    if (scoped_developer_broker is True
            and mode in {"execute", "repair"}
            and getattr(adapter, "name", None) == "codex_cli"):
        result["scoped_developer_tool"] = "pcp_dev.pcp_run_project_checks"
    return result
