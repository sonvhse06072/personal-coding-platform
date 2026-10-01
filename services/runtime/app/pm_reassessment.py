from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .adapters import build_adapter
from .model_capabilities import validate_model_choice
from .repo import diff_state


PMReassessmentAction = Literal[
    "approve_continue",
    "approve_baseline_covered_protected",
    "request_developer_response",
    "request_repair",
    "human_decision",
    "block",
]

_PM_BASELINE_COVERED_PROTECTED_SIGNALS = {
    "security_boundary_change",
}

_PM_HUMAN_TRIGGERS = {
    "architecture_choice",
    "product_ambiguity_high_impact",
    "scope_change",
    "product_scope_change",
    "non_goal_change",
    "major_dependency_addition",
    "security_boundary_change",
    "destructive_migration",
    "production_write",
    "high_authority_governance",
    "project_baseline_authority_change",
    "material_budget_expansion",
}


class PMReassessmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: PMReassessmentAction
    summary: str = Field(min_length=1, max_length=4000)
    developer_message: str | None = Field(default=None, max_length=4000)
    human_necessity: str | None = Field(default=None, max_length=4000)
    unresolved_risks: list[str] = Field(default_factory=list, max_length=12)
    human_triggers: list[str] = Field(default_factory=list, max_length=12)
    authorized_protected_signals: list[str] = Field(default_factory=list, max_length=4)
    baseline_authority_refs: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("PM reassessment summary must not be blank")
        return value

    @field_validator("developer_message", "human_necessity")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator(
        "unresolved_risks",
        "human_triggers",
        "authorized_protected_signals",
        "baseline_authority_refs",
    )
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for raw in values:
            value = str(raw).strip()
            if value and value not in result:
                result.append(value)
        return result

    @model_validator(mode="after")
    def validate_action_shape(self) -> "PMReassessmentDecision":
        if self.action in {"request_developer_response", "request_repair"} and not self.developer_message:
            raise ValueError(f"{self.action} requires developer_message")
        if self.action == "human_decision" and not self.human_triggers:
            raise ValueError("human_decision requires at least one human trigger")
        if self.action == "human_decision" and not self.human_necessity:
            raise ValueError("human_decision requires human_necessity")
        if self.action != "human_decision" and self.human_triggers:
            raise ValueError("human_triggers are valid only for human_decision")
        if self.action != "human_decision" and self.human_necessity:
            raise ValueError("human_necessity is valid only for human_decision")
        unknown = sorted(set(self.human_triggers) - _PM_HUMAN_TRIGGERS)
        if unknown:
            raise ValueError(f"PM reassessment returned unsupported Human Owner triggers: {unknown}")
        if self.action == "approve_baseline_covered_protected":
            if not self.authorized_protected_signals:
                raise ValueError(
                    "approve_baseline_covered_protected requires authorized_protected_signals"
                )
            unsupported = sorted(
                set(self.authorized_protected_signals)
                - _PM_BASELINE_COVERED_PROTECTED_SIGNALS
            )
            if unsupported:
                raise ValueError(
                    "approve_baseline_covered_protected supports only: "
                    + ", ".join(sorted(_PM_BASELINE_COVERED_PROTECTED_SIGNALS))
                )
            if self.unresolved_risks:
                raise ValueError(
                    "approve_baseline_covered_protected cannot retain unresolved risks"
                )
            if not self.baseline_authority_refs:
                raise ValueError(
                    "approve_baseline_covered_protected requires baseline_authority_refs"
                )
        elif self.authorized_protected_signals or self.baseline_authority_refs:
            raise ValueError(
                "authorized_protected_signals and baseline_authority_refs are valid "
                "only for approve_baseline_covered_protected"
            )
        if self.action == "approve_continue" and self.unresolved_risks:
            raise ValueError("approve_continue cannot retain unresolved risks")
        return self


def _compact(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 20)] + "...<truncated>"


def baseline_covered_protected_authorized_signals(
    checkpoint: dict[str, Any],
    *,
    diff_hash: str,
    current_signals: list[str] | set[str],
) -> set[str]:
    """Return exact-diff PM authorizations for baseline-covered protected signals."""

    current = {str(item) for item in current_signals if str(item)}
    if not diff_hash or not current:
        return set()
    for raw in reversed(
        list(checkpoint.get("pm_baseline_covered_protected_authorizations") or [])
    ):
        item = dict(raw) if isinstance(raw, dict) else {}
        if str(item.get("diff_hash") or "") != diff_hash:
            continue
        authorized = {
            str(signal)
            for signal in item.get("protected_signals") or []
            if str(signal)
        }
        if (
            authorized
            and authorized <= _PM_BASELINE_COVERED_PROTECTED_SIGNALS
            and authorized <= current
        ):
            return authorized
    return set()


def validate_baseline_covered_protected_approval(
    decision: dict[str, Any],
    *,
    protected_flags: list[str],
    verification: dict[str, Any],
    review_summary: dict[str, Any] | None,
    baseline: dict[str, Any],
) -> str | None:
    """Fail closed unless a PM approval exactly matches the allowed protected set."""

    authorized = {
        str(item)
        for item in decision.get("authorized_protected_signals") or []
        if str(item)
    }
    current = {str(item) for item in protected_flags if str(item)}
    if not verification.get("passed", False):
        return "deterministic verification must pass"
    review = dict(review_summary or {})
    if str(review.get("verdict") or "") != "pass":
        return "independent review must pass"
    if review.get("protocol_valid") is False:
        return "independent review protocol must be valid"
    if not authorized:
        return "authorized protected signals are required"
    if authorized != current:
        return "authorized protected signals must exactly match current protected signals"
    unsupported = authorized - _PM_BASELINE_COVERED_PROTECTED_SIGNALS
    if unsupported:
        return (
            "baseline-covered protected approval does not support: "
            + ", ".join(sorted(unsupported))
        )
    authority_refs = {
        str(item)
        for item in decision.get("baseline_authority_refs") or []
        if str(item)
    }
    if not authority_refs:
        return "baseline authority references are required"
    baseline_paths: set[str] = set()
    for raw in baseline.get("authority") or []:
        item = dict(raw) if isinstance(raw, dict) else {}
        path = str(item.get("path") or "").strip()
        if path:
            baseline_paths.add(path)
    references = dict(baseline.get("references") or {})
    for group in references.values():
        for raw in group or []:
            item = dict(raw) if isinstance(raw, dict) else {}
            path = str(item.get("path") or "").strip()
            if path:
                baseline_paths.add(path)
    unknown_refs = sorted(authority_refs - baseline_paths)
    if unknown_refs:
        return "baseline authority references are not pinned: " + ", ".join(unknown_refs)
    return None


def changed_file_reassessment_state(
    strategy: dict[str, Any],
    *,
    changed_files: int,
) -> dict[str, int] | None:
    """Return a PM-reviewable adaptive changed-file working-target overage."""

    if str(strategy.get("budget_mode") or "") != "adaptive":
        return None
    adaptive = dict(strategy.get("adaptive_budget") or {})
    dimensions = dict(adaptive.get("dimensions") or {})
    envelope = dict(dimensions.get("max_changed_files") or {})
    try:
        working_target = int(float(envelope["working_target"]))
        emergency_limit = int(float(envelope["emergency_limit"]))
    except (KeyError, TypeError, ValueError):
        return None

    if changed_files <= working_target or changed_files > emergency_limit:
        return None
    return {
        "used": int(changed_files),
        "working_target": working_target,
        "emergency_limit": emergency_limit,
    }


def has_pm_changed_file_authorization(
    checkpoint: dict[str, Any],
    *,
    diff_hash: str,
    used: int,
) -> bool:
    for raw in reversed(list(checkpoint.get("pm_reassessment_authorizations") or [])):
        item = dict(raw) if isinstance(raw, dict) else {}
        if item.get("signal") != "changed_file_working_target_exceeded":
            continue
        if str(item.get("diff_hash") or "") != diff_hash:
            continue
        try:
            approved_used = int(item.get("used") or 0)
            emergency = int(item.get("emergency_limit") or 0)
        except (TypeError, ValueError):
            continue
        return used <= approved_used <= emergency
    return False


def _prompt(
    *,
    work_order: dict[str, Any],
    baseline: dict[str, Any],
    trigger: dict[str, Any],
    diff: dict[str, Any],
    verification: dict[str, Any],
    review_summary: dict[str, Any] | None,
    developer_report: str | None,
    decision_context: dict[str, Any] | None,
) -> str:
    schema = PMReassessmentDecision.model_json_schema()
    evidence = {
        "trigger": trigger,
        "diff": {
            "changed_file_count": diff.get("changed_file_count"),
            "changed_files": list(diff.get("changed_files") or [])[:80],
            "diff_stat": str(diff.get("diff_stat") or "")[:6000],
            "diff_hash": diff.get("diff_hash"),
        },
        "verification": verification,
        "review": review_summary or {},
        "developer_report": (developer_report or "")[-6000:],
        "decision_context": decision_context or {},
    }
    return "\n".join(
        [
            "You are the Product Manager performing a bounded Runtime reassessment.",
            "This is an engineering-governance checkpoint, not implementation. Work read-only.",
            "Do not edit files, run write operations, commit, push, merge, deploy, or amend governance.",
            "The approved WorkOrder and pinned ProjectBaseline are authoritative.",
            "The Primary Developer has crossed a semantic working target. File count alone is not proof of scope drift.",
            "Approve continuation only when the evidence shows the change remains inside the approved WorkOrder and no Human Owner protected/material decision is required.",
            "Plain approve_continue remains forbidden while any protected_execution_signal is present.",
            "For the special action approve_baseline_covered_protected, use it only when deterministic verification PASS and independent review PASS, every current protected flag is exactly security_boundary_change, the exact diff is already covered by the pinned ProjectBaseline/WorkOrder, and no new auth mechanism, credential transport, trust boundary, or security boundary is introduced.",
            "For approve_baseline_covered_protected, authorized_protected_signals MUST exactly equal the current protected_decision_flags, baseline_authority_refs MUST name one or more exact paths present in the pinned ProjectBaseline authority/references, and human_triggers MUST be [] with human_necessity null.",
            "Never use approve_baseline_covered_protected for scope changes, dependency additions, destructive migrations, production writes, governance/baseline authority changes, or actual auth/trust-boundary changes.",
            "If evidence is insufficient, ask the developer one concrete bounded question. If implementation should change, request a bounded repair.",
            "A removable implementation choice that violates the WorkOrder or an out-of-scope rule is ordinarily a PM repair decision, not a request to expand scope. Prefer request_repair or request_developer_response when the approved objective can still be met by reverting/replacing the offending change.",
            "Do not escalate merely because a protected signal exists. Escalate to Human Owner only when the evidence shows PM cannot resolve the issue inside the approved baseline, such as when the protected/material change is genuinely necessary and no viable in-scope repair is available.",
            "For any action other than human_decision, human_triggers MUST be [] and human_necessity MUST be null.",
            "For any action other than approve_baseline_covered_protected, authorized_protected_signals and baseline_authority_refs MUST both be [].",
            "Never put a reviewed-but-not-escalated protected signal in human_triggers. Describe that review in summary or unresolved_risks instead.",
            f"For human_decision, human_triggers MUST contain only exact trigger IDs from: {', '.join(sorted(_PM_HUMAN_TRIGGERS))}.",
            "For human_decision, human_necessity must state why repair, revert, or bounded developer dialogue cannot resolve the issue. Human Owner is not an implementation convenience.",
            "Escalate to Human Owner only for a decision the PM lacks authority to make: product/scope/non-goal, architecture invariant, major dependency/service, security/auth/trust, destructive data, production, protected governance/baseline authority, or material resource expansion.",
            "A Human Owner is not a substitute for ordinary engineering judgment.",
            "A prior Human Owner approval does not rewrite the WorkOrder or ProjectBaseline. Reassess within the still-authoritative baseline after considering that decision history.",
            "Do not repeat an already-resolved Human trigger. A rejected Human decision means the requested expansion is not approved: repair/revert inside the current baseline or block if impossible. If an approved answer still requires a baseline/scope amendment, request repair/block rather than treating the approval as permission to bypass the current contract.",
            "Return EXACTLY one JSON object and no Markdown/prose outside it.",
            f"WORK_ORDER: {_compact(work_order, 12000)}",
            f"PROJECT_BASELINE: {_compact(baseline, 12000)}",
            f"EVIDENCE: {_compact(evidence, 18000)}",
            "OUTPUT_JSON_SCHEMA:",
            json.dumps(schema, ensure_ascii=False, sort_keys=True),
        ]
    )


def _parse(output: str) -> PMReassessmentDecision:
    text = (output or "").strip()
    if not text:
        raise ValueError("Product Manager reassessment returned empty output")
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise ValueError("Product Manager reassessment returned an unterminated fenced response")
        text = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Product Manager reassessment output must be one JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("Product Manager reassessment output must be a JSON object")
    return PMReassessmentDecision.model_validate(payload)


async def run_pm_reassessment(
    *,
    router: Any,
    ddev: Any,
    workspace: Path,
    job_id: str,
    project_id: str,
    source_commit: str,
    profile: str,
    current_executor: dict[str, Any],
    provider_state: dict[str, Any],
    work_order: dict[str, Any],
    baseline: dict[str, Any],
    trigger: dict[str, Any],
    diff: dict[str, Any],
    verification: dict[str, Any],
    review_summary: dict[str, Any] | None,
    developer_report: str | None,
    decision_context: dict[str, Any] | None,
    max_diff_bytes: int,
    timeout_seconds: int,
    adapter_builder=build_adapter,
    precharge_call: Callable[[], None] | None = None,
) -> dict[str, Any]:
    pm_profile = profile if profile in {"complex", "critical"} else "standard"
    current_model_id = str(current_executor.get("id") or "").strip()
    staffing = await router.staff(
        {
            "request_id": f"{job_id}:pm-reassess",
            "project_id": project_id,
            "role": "product_manager",
            "profile": pm_profile,
            "semantic": {
                "ambiguity": 45,
                "architecture_impact": 35,
                "verification_difficulty": 35,
                "risk": 45,
                "context_requirement": 75,
                "novelty": 30,
                "reasoning_requirement": 85,
            },
            "provider_state": provider_state,
            "exclude_model_ids": [current_model_id] if current_model_id else [],
        }
    )
    choice = dict(staffing.get("choice") or {})
    if not choice.get("id"):
        raise RuntimeError("PM reassessment staffing returned no model")
    if current_model_id and choice.get("id") == current_model_id:
        raise RuntimeError("PM reassessment must use a different model from the Primary Developer")
    validate_model_choice(choice)

    # Snapshot the developer diff, then review it in a disposable isolated clone.
    # The PM never receives write access to the owning developer workspace.
    original = diff_state(workspace, max_diff_bytes)
    patch_proc = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--binary"],
        text=True,
        capture_output=True,
    )
    if patch_proc.returncode != 0:
        raise RuntimeError(patch_proc.stderr.strip() or "Unable to snapshot developer diff")
    patch = patch_proc.stdout

    review_job_id = (
        f"pmr-{job_id[:20]}-{str(original.get('diff_hash') or '')[:10]}"
    )
    workspace_info: dict[str, Any] | None = None
    try:
        workspace_info = await ddev.create_workspace(
            job_id=review_job_id,
            project_id=project_id,
            ref=source_commit,
            workspace_mode="isolated_clone",
        )
        review_source = str(workspace_info.get("source_commit") or "").lower()
        if review_source != str(source_commit).lower():
            raise RuntimeError(
                "PM reassessment workspace source commit does not match the developer job"
            )
        review_workspace = Path(str(workspace_info["workspace"]))

        if patch:
            applied = subprocess.run(
                [
                    "git",
                    "-C",
                    str(review_workspace),
                    "apply",
                    "--binary",
                    "--whitespace=nowarn",
                    "-",
                ],
                input=patch,
                text=True,
                capture_output=True,
            )
            if applied.returncode != 0:
                raise RuntimeError(
                    applied.stderr.strip()
                    or "Unable to materialize developer diff for PM reassessment"
                )

        before = diff_state(review_workspace, max_diff_bytes)
        if (
            before.get("diff_hash") != original.get("diff_hash")
            or before.get("changed_files") != original.get("changed_files")
        ):
            raise RuntimeError(
                "PM reassessment clone does not match the exact developer diff"
            )

        if precharge_call is not None:
            precharge_call()
        run = await adapter_builder(
            str(choice["adapter"]),
            str(choice["model"]),
            choice.get("reasoning_effort"),
        ).run(
            workspace=review_workspace,
            prompt=_prompt(
                work_order=work_order,
                baseline=baseline,
                trigger=trigger,
                diff=diff,
                verification=verification,
                review_summary=review_summary,
                developer_report=developer_report,
                decision_context=decision_context,
            ),
            mode="evaluate",
            timeout=timeout_seconds,
        )
        after = diff_state(review_workspace, max_diff_bytes)
        if (
            before.get("diff_hash") != after.get("diff_hash")
            or before.get("changed_files") != after.get("changed_files")
        ):
            raise RuntimeError(
                "Product Manager reassessment modified its read-only review workspace"
            )
        if run.provider_failed:
            raise RuntimeError(
                f"Product Manager reassessment provider failure: {run.failure_kind or 'unknown'}"
            )
        if run.returncode != 0:
            raise RuntimeError("Product Manager reassessment model failed")

        decision = _parse(run.output)
        return {
            "decision": decision.model_dump(mode="json"),
            "staffing": staffing,
            "usage": run.usage,
            "model_id": str(choice["id"]),
            "provider": str(choice.get("provider") or ""),
        }
    finally:
        if workspace_info and workspace_info.get("workspace"):
            await ddev.remove_workspace(
                job_id=review_job_id,
                project_id=project_id,
                workspace=str(workspace_info["workspace"]),
            )
