from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_MAX_CONTRACT_CHARS = 6000
_MAX_DIFF_CHARS = 12000
_MAX_FAILURE_CHARS = 4000
_MAX_SUMMARY_CHARS = 3000
_MAX_FILES = 40
_DIFF_FILE_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)
_CANONICAL_WORK_ORDER_PREFIX = "AUTHORITATIVE WORKORDER / TASK CONTRACT."


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _changed_files(diff: str) -> list[str]:
    result: list[str] = []
    for _, path in _DIFF_FILE_RE.findall(diff or ""):
        if path not in result:
            result.append(path)
        if len(result) >= _MAX_FILES:
            break
    return result


def _canonical_work_order_from_task(task: dict[str, Any]) -> dict[str, Any] | None:
    """Recover the authoritative WorkOrder object from a canonical legacy task.

    Runtime passes an explicit WorkOrder on normal governed jobs. This fallback
    keeps evaluator-prompt compatibility for callers/tests that only carry the
    canonical task description, while avoiding propagation of the surrounding
    prose or an unbounded raw task transcript.
    """
    description = str(task.get("description") or "").strip()
    if not description.startswith(_CANONICAL_WORK_ORDER_PREFIX):
        return None
    for line in description.splitlines()[1:]:
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def _compact_verification(verification: dict[str, Any]) -> dict[str, Any]:
    phases: list[dict[str, Any]] = []
    for item in verification.get("phases", []) if isinstance(verification, dict) else []:
        if not isinstance(item, dict):
            continue
        commands = []
        for command in item.get("commands", []) or []:
            if not isinstance(command, dict):
                continue
            commands.append(
                {
                    "command": _clip(command.get("command"), 500),
                    "returncode": command.get("returncode"),
                    "timed_out": bool(command.get("timed_out", False)),
                }
            )
        phases.append(
            {
                "phase": item.get("phase"),
                "passed": bool(item.get("passed", False)),
                "verification_layer": item.get("verification_layer"),
                "required_for_final": item.get("required_for_final"),
                "commands": commands[:12],
            }
        )
    return {
        "passed": bool(verification.get("passed", False)),
        "tests_passed": bool(verification.get("tests_passed", False)),
        "verification_mode": verification.get("verification_mode"),
        "phases": phases[:12],
        "failure_summary": _clip(verification.get("failure_text"), _MAX_FAILURE_CHARS),
    }


def jit_retrieval_contract() -> dict[str, Any]:
    return {
        "allowed": True,
        "mode": "repository_read_only",
        "trigger": "retrieve only when the compact evidence pack is insufficient to decide a concrete finding",
        "constraints": [
            "stay inside the current WorkOrder/task scope",
            "do not modify files",
            "do not request full model/developer transcripts",
            "retrieve the smallest relevant repository context",
        ],
    }


def reviewer_evidence_pack(
    *,
    task: dict[str, Any],
    diff: str,
    verification: dict[str, Any],
    work_order: dict[str, Any] | None = None,
    developer_report: str | None = None,
) -> dict[str, Any]:
    diff_text = str(diff or "")
    canonical = _canonical_work_order_from_task(task)
    contract = work_order if isinstance(work_order, dict) else canonical
    if not isinstance(contract, dict):
        contract = {
            "title": task.get("title"),
            "description": _clip(task.get("description"), _MAX_CONTRACT_CHARS),
            "flags": list(task.get("flags") or [])[:20],
        }
    return {
        "role": "reviewer",
        "task_contract": contract,
        "changed_files": _changed_files(diff_text),
        "diff": {
            "sha256": _sha256(diff_text),
            "excerpt": _clip(diff_text, _MAX_DIFF_CHARS),
            "truncated": len(diff_text) > _MAX_DIFF_CHARS,
        },
        "verification": _compact_verification(verification),
        "developer_report": _clip(developer_report, _MAX_SUMMARY_CHARS),
        "jit_retrieval": jit_retrieval_contract(),
    }


def developer_repair_evidence_pack(
    *,
    work_order_ref: str,
    current_diff_ref: str,
    failing_check: str | None,
    reviewer_findings: list[dict[str, Any]] | None,
    relevant_files: list[str] | None,
    prior_attempt_summary: str | None,
) -> dict[str, Any]:
    findings = []
    for item in reviewer_findings or []:
        if not isinstance(item, dict):
            continue
        findings.append(
            {
                "id": _clip(item.get("id"), 120),
                "severity": _clip(item.get("severity"), 40),
                "message": _clip(item.get("message"), 1200),
                "evidence_refs": list(item.get("evidence_refs") or [])[:8],
            }
        )
    return {
        "role": "developer_repair",
        "work_order_ref": _clip(work_order_ref, 500),
        "current_diff_ref": _clip(current_diff_ref, 500),
        "failing_check": _clip(failing_check, _MAX_FAILURE_CHARS),
        "reviewer_findings": findings[:12],
        "relevant_files": list(dict.fromkeys(relevant_files or []))[:_MAX_FILES],
        "prior_attempt_summary": _clip(prior_attempt_summary, _MAX_SUMMARY_CHARS),
        "jit_retrieval": jit_retrieval_contract(),
    }


def consultant_evidence_pack(
    *,
    work_order_ref: str,
    objective: str,
    question: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    compact = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "ref": _clip(item.get("ref"), 500),
                "summary": _clip(item.get("summary"), 2000),
            }
        )
    return {
        "role": "consultant",
        "work_order_ref": _clip(work_order_ref, 500),
        "objective": _clip(objective, 2000),
        "question": _clip(question, 5000),
        "evidence": compact[:8],
        "jit_retrieval": jit_retrieval_contract(),
    }


def pm_evidence_pack(
    *,
    work_order_ref: str,
    outcome: str,
    verification_summary: dict[str, Any],
    review_summary: dict[str, Any] | None,
    unresolved_risks: list[str] | None,
    protected_decision_flags: list[str] | None,
    baseline_covered_protected_authorizations: list[dict[str, Any]] | None = None,
    incident_learning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "role": "product_manager",
        "work_order_ref": _clip(work_order_ref, 500),
        "outcome": _clip(outcome, 1000),
        "verification": _compact_verification(verification_summary),
        "review": review_summary or {},
        "unresolved_risks": [_clip(item, 1000) for item in (unresolved_risks or [])[:12]],
        "protected_decision_flags": list(dict.fromkeys(protected_decision_flags or []))[:20],
        "baseline_covered_protected_authorizations": [
            {
                "diff_hash": _clip(str(item.get("diff_hash") or ""), 200),
                "protected_signals": list(
                    dict.fromkeys(
                        str(signal)
                        for signal in item.get("protected_signals") or []
                        if str(signal)
                    )
                )[:8],
                "approved_by": _clip(str(item.get("approved_by") or ""), 200),
                "provider": _clip(str(item.get("provider") or ""), 100),
                "summary": _clip(str(item.get("summary") or ""), 1000),
                "baseline_authority_refs": [
                    _clip(str(ref), 300)
                    for ref in (item.get("baseline_authority_refs") or [])[:8]
                    if str(ref)
                ],
                "review_verdict": _clip(str(item.get("review_verdict") or ""), 100),
                "baseline_revision": _clip(str(item.get("baseline_revision") or ""), 200),
            }
            for item in (baseline_covered_protected_authorizations or [])[-8:]
            if isinstance(item, dict)
        ],
        "incident_learning": dict(incident_learning or {}),
        "jit_retrieval": jit_retrieval_contract(),
    }


__all__ = [
    "consultant_evidence_pack",
    "developer_repair_evidence_pack",
    "jit_retrieval_contract",
    "pm_evidence_pack",
    "reviewer_evidence_pack",
]
