from __future__ import annotations

from typing import Any


MANAGED_START = "<!-- PCP:CONTINUITY:START -->"
MANAGED_END = "<!-- PCP:CONTINUITY:END -->"
_ALLOWED_MUTABLE_PATH = "docs/project/current-state.md"


def continuity_proposal(
    row: dict[str, Any],
    *,
    event_type: str,
    attention_summary: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checkpoint = row.get("checkpoint") or {}
    work_order = checkpoint.get("work_order") or {}
    result = row.get("result") or {}
    return {
        "event_type": str(event_type),
        "project_id": str(row.get("project_id") or ""),
        "job_id": str(row.get("id") or "") or None,
        "status": str(row.get("status") or "unknown"),
        "work_order_id": str(work_order.get("id") or "") or None,
        "branch": str(row.get("branch") or "") or None,
        "outcome": (telemetry or {}).get("task_outcome") or result.get("status") or result.get("reason"),
        "attention": dict(attention_summary or {}),
        "telemetry": {
            "first_pass_success": (telemetry or {}).get("first_pass_success"),
            "repair_count": (telemetry or {}).get("repair_count"),
            "provider_failures": (telemetry or {}).get("provider_failures"),
            "quota_failures": (telemetry or {}).get("quota_failures"),
        },
        "detail": dict(payload or {}),
        "authority": {
            "mutable_target": _ALLOWED_MUTABLE_PATH,
            "direct_durable_policy_write_allowed": False,
            "application_path": "normal_git_branch_pr_authority",
        },
    }


def render_managed_section(proposal: dict[str, Any]) -> str:
    """Render only the bounded mutable section allowed for continuity automation."""
    attention = proposal.get("attention") or {}
    telemetry = proposal.get("telemetry") or {}
    lines = [
        MANAGED_START,
        "## Automated continuity snapshot",
        "",
        f"- Event: `{proposal.get('event_type') or 'unknown'}`.",
        f"- Project/job: `{proposal.get('project_id') or 'unknown'}` / `{proposal.get('job_id') or 'n/a'}`.",
        f"- Runtime state: `{proposal.get('status') or 'unknown'}`; outcome: `{proposal.get('outcome') or 'unknown'}`.",
        f"- WorkOrder: `{proposal.get('work_order_id') or 'n/a'}`; branch: `{proposal.get('branch') or 'n/a'}`.",
        (
            "- Human attention: "
            f"interventions `{attention.get('human_interventions', 0)}`, "
            f"avoidable `{attention.get('avoidable_blocks', 0)}`, "
            f"owner wait `{round(float(attention.get('time_waiting_for_owner_seconds', 0.0) or 0.0), 1)}` seconds."
        ),
        (
            "- Execution evidence: "
            f"first-pass `{telemetry.get('first_pass_success')}`, "
            f"repairs `{telemetry.get('repair_count')}`, "
            f"provider failures `{telemetry.get('provider_failures')}`, "
            f"quota failures `{telemetry.get('quota_failures')}`."
        ),
        "- This section is mutable execution state only. Durable architecture/policy changes still require their normal reviewed Git path.",
        MANAGED_END,
    ]
    return "\n".join(lines)


def render_managed_current_state(existing: str, proposal: dict[str, Any]) -> str:
    """Replace one bounded mutable section; never append a chronological log."""
    if MANAGED_START not in existing or MANAGED_END not in existing:
        raise ValueError("current-state.md is missing the managed continuity markers")
    start = existing.index(MANAGED_START)
    end = existing.index(MANAGED_END, start) + len(MANAGED_END)
    replacement = render_managed_section(proposal)
    return existing[:start] + replacement + existing[end:]


def assert_mutable_continuity_target(path: str) -> None:
    if str(path).strip("/") != _ALLOWED_MUTABLE_PATH:
        raise ValueError("Continuity automation may only target docs/project/current-state.md")


__all__ = [
    "MANAGED_END",
    "MANAGED_START",
    "assert_mutable_continuity_target",
    "continuity_proposal",
    "render_managed_current_state",
    "render_managed_section",
]
