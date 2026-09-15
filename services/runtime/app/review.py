from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .usage import estimated_cost_usd, normalize_usage


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    category: str = Field(default="correctness", min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("id", "category", "message")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("review finding text must not be blank")
        return normalized


class ReviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["pass", "fail"]
    summary: str = Field(min_length=1, max_length=4000)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=20)
    jit_context_used: bool = False

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("review summary must not be blank")
        return normalized


def parse_review_output(output: str) -> ReviewReport:
    """Parse the new structured protocol while retaining legacy PASS/FAIL output."""
    text = (output or "").strip()
    if not text:
        return ReviewReport(verdict="fail", summary="Reviewer returned no output")

    lines = text.splitlines()
    first = lines[0].strip().upper()
    verdict: Literal["pass", "fail"] = "pass" if first.startswith("PASS") else "fail"

    marker = "REVIEW_JSON:"
    payload_text = None
    for line in lines[1:]:
        if line.strip().startswith(marker):
            payload_text = line.strip()[len(marker) :].strip()
            break
    if payload_text:
        try:
            payload = json.loads(payload_text)
            if isinstance(payload, dict):
                payload.setdefault("verdict", verdict)
                return ReviewReport.model_validate(payload)
        except (json.JSONDecodeError, ValueError):
            pass

    summary = text[:4000]
    findings = []
    if verdict == "fail":
        findings = [
            ReviewFinding(
                id="legacy-review-failure",
                severity="medium",
                category="review",
                message=summary,
                evidence_refs=[],
            )
        ]
    return ReviewReport(
        verdict=verdict,
        summary=summary,
        findings=findings,
        jit_context_used=False,
    )


def strong_deterministic_evidence(
    verification: dict[str, Any],
    *,
    changed_files: int,
    unexpected_scope: bool,
) -> bool:
    if not verification.get("passed", False) or unexpected_scope or changed_files > 3:
        return False
    phases = [item for item in verification.get("phases", []) if isinstance(item, dict)]
    if not phases:
        return False
    if any(not item.get("passed", False) for item in phases):
        return False
    names = {str(item.get("phase") or "") for item in phases}
    has_final = "full_tests" in names or any(
        item.get("verification_layer") == "final" and item.get("required_for_final")
        for item in phases
    )
    return has_final or len(names) >= 2


def should_run_review(
    review_policy: dict[str, Any] | None,
    verification: dict[str, Any],
    *,
    changed_files: int,
    unexpected_scope: bool,
) -> bool:
    policy = review_policy or {}
    if str(policy.get("level") or "none") == "none":
        return False
    if bool(policy.get("required", False)):
        return True
    if bool(policy.get("conditional_on_strong_evidence", False)):
        return not strong_deterministic_evidence(
            verification,
            changed_files=changed_files,
            unexpected_scope=unexpected_scope,
        )
    return False


def review_report_summary(report: ReviewReport) -> dict[str, Any]:
    return {
        "verdict": report.verdict,
        "summary": report.summary,
        "finding_count": len(report.findings),
        "findings": [item.model_dump(mode="json") for item in report.findings],
        "jit_context_used": report.jit_context_used,
    }


def _update_useful_finding_yield(progress: dict[str, Any]) -> None:
    total = int(progress.get("review_findings", 0))
    actioned = int(progress.get("review_findings_actioned", 0))
    progress["review_useful_finding_yield"] = round(actioned / total, 4) if total else 0.0


def record_review_telemetry(
    progress: dict[str, Any],
    report: ReviewReport,
    *,
    review_level: str,
    model_id: str | None,
    provider: str | None,
    raw_usage: dict[str, Any] | None = None,
) -> None:
    usage = normalize_usage(raw_usage)
    cost = estimated_cost_usd(str(model_id or ""), raw_usage) if model_id else 0.0
    progress["review_runs"] = int(progress.get("review_runs", 0)) + 1
    progress["review_findings"] = int(progress.get("review_findings", 0)) + len(report.findings)
    progress["review_jit_context_runs"] = int(progress.get("review_jit_context_runs", 0)) + int(
        report.jit_context_used
    )
    progress["review_input_tokens"] = int(progress.get("review_input_tokens", 0)) + int(
        usage["input_tokens"]
    )
    progress["review_output_tokens"] = int(progress.get("review_output_tokens", 0)) + int(
        usage["output_tokens"]
    )
    progress["review_cost_usd"] = round(float(progress.get("review_cost_usd", 0.0)) + cost, 8)
    history = list(progress.get("review_history") or [])
    history.append(
        {
            "level": review_level,
            "verdict": report.verdict,
            "finding_count": len(report.findings),
            "model": model_id,
            "provider": provider,
            "jit_context_used": report.jit_context_used,
            "input_tokens": int(usage["input_tokens"]),
            "output_tokens": int(usage["output_tokens"]),
            "estimated_cost_usd": cost,
        }
    )
    progress["review_history"] = history[-12:]
    _update_useful_finding_yield(progress)


def mark_actioned_review_findings(
    checkpoint: dict[str, Any],
    progress: dict[str, Any],
    *,
    current_diff_hash: str,
) -> None:
    pending = checkpoint.get("pending_review_findings")
    if not isinstance(pending, dict):
        return
    previous_hash = str(pending.get("diff_hash") or "")
    if not previous_hash or previous_hash == current_diff_hash:
        return
    findings = [item for item in pending.get("findings", []) if isinstance(item, dict)]
    progress["review_findings_actioned"] = int(progress.get("review_findings_actioned", 0)) + len(findings)
    checkpoint.pop("pending_review_findings", None)
    _update_useful_finding_yield(progress)


__all__ = [
    "ReviewFinding",
    "ReviewReport",
    "mark_actioned_review_findings",
    "parse_review_output",
    "record_review_telemetry",
    "review_report_summary",
    "should_run_review",
    "strong_deterministic_evidence",
]
