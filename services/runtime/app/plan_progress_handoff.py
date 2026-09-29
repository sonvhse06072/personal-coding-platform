"""Compact, transition-driven parent progress. This channel has no engineering authority."""
from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any

from .work_order_checkpoints import blocked_plan_evidence, ready_work_order_ids


BODY_MAX_BYTES = 12 * 1024
# Reserve room for the executor-owned marker and separator.
CONTENT_MAX_BYTES = BODY_MAX_BYTES - 128


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def handoff_key(project_id: str, issue_number: int) -> str:
    return sha256(f"{project_id}:{issue_number}")


def issue_binding(ticket_id: Any, staffing: dict[str, Any]) -> int | None:
    # An explicitly supplied but malformed structured identity fails closed.
    if "issue_number" in staffing:
        number = staffing["issue_number"]
        return number if type(number) is int and 0 < number <= 2**63 - 1 else None
    match = re.fullmatch(r"GH-([1-9][0-9]{0,18})", ticket_id or "")
    return int(match[1]) if match and int(match[1]) <= 2**63 - 1 else None


def _text(value: Any, limit: int = 200) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return "-"
    value = " ".join(str(value).split()).replace("\x00", "")
    # Render identities as text, preventing injected HTML/markers and mentions.
    value = html.escape(value, quote=False).replace("@", "&#64;")
    return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore") or "-"


def _checkpoint_line(checkpoint: dict[str, Any] | None) -> str:
    if not checkpoint:
        return "checkpoint unavailable"
    evidence = checkpoint.get("evidence") or {}
    parts = [
        f"{_text(checkpoint.get('kind'), 40)} checkpoint {_text(checkpoint.get('id'), 30)}",
        f"key {_text(checkpoint.get('checkpoint_key'), 120)}",
    ]
    if checkpoint.get("job_id"):
        parts.append(f"job {_text(checkpoint['job_id'])}")
    for key, label in (
        ("produced_commit", "commit"), ("pr_number", "PR"),
        ("merge_commit", "merge"),
    ):
        if evidence.get(key) is not None:
            prefix = "#" if key == "pr_number" else ""
            parts.append(f"{label} {prefix}{_text(evidence[key])}")
    return "; ".join(parts)


def render_progress(snapshot: dict[str, Any], issue_number: int) -> tuple[str, str]:
    plan, rows = snapshot["orchestration"], snapshot["work_orders"]
    states = {row["work_order_id"]: row["state"] for row in rows}
    current = next((row["work_order_id"] for row in rows
                    if row["state"] in {"running", "awaiting_merge", "waiting_human"}), None)
    ready = ready_work_order_ids(plan.get("plan") or {}, states)
    checkpoint = snapshot.get("last_checkpoint") or {}
    blocked_evidence = blocked_plan_evidence(snapshot)
    # No mutable polling timestamps, details, results or provider data enter this identity.
    identity = {
        "plan_id": plan["plan_id"], "state": plan["status"], "lifecycle": plan["lifecycle"],
        "checkpoint": [checkpoint.get("id"), checkpoint.get("checkpoint_key")],
        "work_orders": [[row["work_order_id"], row["state"], row.get("job_id")] for row in rows],
        "next": ready,
    }
    transition = sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")))
    lines = ["## PCP execution progress", "", f"Ticket: GH-{issue_number}",
             f"Plan: {_text(plan['plan_id'])}", f"State: {_text(plan['status'])}",
             f"Progress: {sum(state == 'completed' for state in states.values())} / {len(rows)} completed",
             f"Current: {_text(current)}", "", "WorkOrders:"]
    for row in rows[:30]:
        lines.append(f"- {_text(row['work_order_id'], 100)} — {_text(row['state'], 40)}")
    if blocked_evidence:
        current_blocked = blocked_evidence["current"]
        lines += ["", "Blocked evidence:",
                  f"- WorkOrder: {_text(current_blocked.get('work_order_id'))}",
                  f"- Job: {_text(current_blocked.get('job_id'))}",
                  f"- Branch: {_text(current_blocked.get('branch'), 300)}",
                  f"- Checkpoint: {_text(current_blocked.get('checkpoint_id'), 30)} / "
                  f"{_text(current_blocked.get('checkpoint_key'), 120)}",
                  f"- Reason: {_text(blocked_evidence.get('reason'))}",
                  f"- Next safe action: {_text(blocked_evidence.get('next_safe_action'), 40)}"]
        verification = blocked_evidence.get("latest_verification") or {}
        if type(verification.get("passed")) is bool:
            lines.append(f"- Latest verification: {'passed' if verification['passed'] else 'failed'}")
        for phase in (verification.get("phases") or [])[:16]:
            if isinstance(phase, dict) and type(phase.get("passed")) is bool:
                lines.append(
                    f"  - {_text(phase.get('phase'), 80)}: "
                    f"{'passed' if phase['passed'] else 'failed'}"
                )
        outcome = blocked_evidence.get("latest_outcome") or {}
        for key in ("review_verdict", "pm_outcome", "pm_action"):
            if outcome.get(key) is not None:
                lines.append(f"- {key}: {_text(outcome[key])}")
        lines += ["", "Completed durable checkpoints:"]
        completed = blocked_evidence.get("completed_work_orders") or []
        for item in completed[:30]:
            lines.append(
                f"- {_text(item.get('work_order_id'), 100)} — "
                f"{_checkpoint_line(item.get('checkpoint'))}"
            )
        if not completed:
            lines.append("- none")
        lines += ["", "Untouched pending WorkOrders:"]
        pending = blocked_evidence.get("pending_work_orders") or []
        for item in pending[:30]:
            dependencies = item.get("dependencies") or []
            dependency_text = ", ".join(_text(dep, 100) for dep in dependencies[:30]) or "none"
            lines.append(
                f"- {_text(item.get('work_order_id'), 100)} — pending; "
                f"job {_text(item.get('job_id'))}; dependencies {dependency_text}"
            )
        if not pending:
            lines.append("- none")
        lines += ["", "Last known-good checkpoint:",
                  f"- {_checkpoint_line(blocked_evidence.get('last_known_good_checkpoint'))}"]
    if checkpoint:
        lines += ["", "Last checkpoint:"]
        for key in ("work_order_id", "kind", "state", "job_id"):
            if checkpoint.get(key) is not None:
                lines.append(f"- {key}: {_text(checkpoint[key])}")
        evidence = checkpoint.get("evidence") or {}
        for key in ("source_commit", "produced_commit", "pr_number", "pr_head", "merge_commit",
                    "merged_at", "review_verdict", "pm_outcome", "pm_action"):
            if evidence.get(key) is not None:
                lines.append(f"- {key}: {_text(evidence[key])}")
        verification = evidence.get("verification")
        if isinstance(verification, dict):
            if type(verification.get("passed")) is bool:
                lines.append(f"- Verification: {'passed' if verification['passed'] else 'failed'}")
            for phase in (verification.get("phases") or [])[:16]:
                if isinstance(phase, dict) and type(phase.get("passed")) is bool:
                    lines.append(f"- Phase {_text(phase.get('phase'), 80)}: {'passed' if phase['passed'] else 'failed'}")
    lines += ["", "Next:"] + [f"- {_text(item, 100)}" for item in ready[:30]]
    if not ready:
        lines.append("- none")
    body = "\n".join(lines)
    if len(body.encode("utf-8")) > CONTENT_MAX_BYTES:
        body = body.encode("utf-8")[:CONTENT_MAX_BYTES - 24].decode("utf-8", errors="ignore") + "\n[summary truncated]"
    return transition, body
