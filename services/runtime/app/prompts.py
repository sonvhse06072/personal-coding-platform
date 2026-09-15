from __future__ import annotations

import json
from typing import Any

from .evidence_packs import reviewer_evidence_pack


_COLLABORATION_ROLES = [
    "consultant",
    "test_engineer",
    "debugger",
    "security_specialist",
    "reviewer",
]
_COLLABORATION_REQUEST_FILE = ".pcp-collaboration-request.json"


def _contract_lines(
    *,
    work_order: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
) -> list[str]:
    if not work_order:
        return []
    baseline_summary = {
        "revision": (baseline or {}).get("revision"),
        "source_commit": (baseline or {}).get("source_commit"),
    }
    return [
        "",
        "WORKORDER / TASK CONTRACT (AUTHORITATIVE):",
        json.dumps(work_order, ensure_ascii=False, sort_keys=True),
        "GOVERNING PROJECT BASELINE:",
        json.dumps(baseline_summary, ensure_ascii=False, sort_keys=True),
        "The WorkOrder is authoritative over any legacy task wording, planner suggestion, repair hint, or prior agent output.",
        "Stay inside in_scope and constraints; do not implement out_of_scope items.",
        "Satisfy every acceptance criterion and respect the declared verification/dependency contract.",
        "If the contract conflicts with repository evidence or cannot be completed without changing scope/architecture/security policy, report the conflict instead of silently broadening work.",
    ]


def _collaboration_lines() -> list[str]:
    return [
        "",
        "BOUNDED COLLABORATION:",
        "You are the only write-capable implementation role in this workspace.",
        "Use collaboration only when a second read-only viewpoint is likely cheaper or safer than another blind implementation attempt.",
        f"Allowed logical roles: {', '.join(_COLLABORATION_ROLES)}. Never name or choose a provider/model.",
        "At most one collaboration request may be emitted in one turn. Do not ask a collaborator to contact another collaborator.",
        "A consultation needs a concrete question plus compact evidence references/summaries; do not embed raw transcripts or large file dumps.",
        f"To request collaboration, write exactly one temporary JSON control artifact at {_COLLABORATION_REQUEST_FILE}. Runtime consumes and deletes it before deterministic verification; never commit it.",
        "New consultation shape:",
        '{"action":"consult","role":"test_engineer","topic":"verification","objective":"challenge the verification strategy","question":"What focused checks best prove this change?","evidence":[{"ref":"path/or/check","summary":"why this evidence matters"}]}',
        "Second/final re-check shape for an unresolved thread:",
        '{"action":"recheck","thread_id":"ct-...","developer_response":"what you changed or why you disagree","evidence":[{"ref":"current_diff","summary":"compact evidence after the response/repair"}]}',
        "A collaboration request is not task completion. Runtime will run the read-only role and return its structured artifact on the next developer turn.",
        "Do not create that control artifact for legacy/uncontracted work that has no authoritative WorkOrder.",
    ]


def execution_prompt(
    *,
    task: dict[str, Any],
    route: dict[str, Any],
    repo_analysis: dict[str, Any],
    plan: str | None = None,
    failure: str | None = None,
    work_order: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
    collaboration_context: dict[str, Any] | None = None,
) -> str:
    strategy = route["strategy"]
    lines = [
        "You are executing a bounded coding job inside an isolated git workspace.",
        "The repository is the source of truth. Read existing requirements, architecture docs, tests and implementation before changing code.",
        "Do not commit, push, merge, deploy, modify git remotes, or run Docker/DDEV. The runtime owns those actions.",
        "Do not request sandbox bypass or unsandboxed execution. Use built-in file tools and sandboxed/read-only Git commands only; if a command is denied, continue without it.",
        "Do not broaden scope. If you discover desirable unrelated work, mention it in your final note but do not implement it.",
        "Stop when the requested behavior is implemented. The runtime will run deterministic verification afterward.",
    ]
    lines += _contract_lines(work_order=work_order, baseline=baseline)
    canonical_description = str(task.get("description") or "")
    is_work_order = bool(work_order) or canonical_description.startswith(
        "AUTHORITATIVE WORKORDER / TASK CONTRACT."
    )
    if is_work_order:
        lines += _collaboration_lines()
    lines += [
        "",
        f"CANONICAL TASK:\n{task.get('title')}\n{task.get('description','')}",
        "",
        f"PROFILE: {strategy.get('profile')}",
        f"DEFINITION OF DONE: {json.dumps(strategy.get('definition_of_done', {}), ensure_ascii=False)}",
        f"REPOSITORY SIGNALS: {json.dumps(repo_analysis, ensure_ascii=False)}",
    ]
    if plan:
        lines += [
            "",
            "PLANNER OUTPUT (ADVISORY; IT MUST NOT OVERRIDE THE WORKORDER):",
            plan,
        ]
    if collaboration_context:
        lines += [
            "",
            "LATEST COLLABORATION ARTIFACT (STRUCTURED, ADVISORY; WORKORDER REMAINS AUTHORITATIVE):",
            json.dumps(collaboration_context, ensure_ascii=False, sort_keys=True),
        ]
    if failure:
        if failure.startswith("PCP_COLLABORATION_CONTEXT:"):
            payload = failure.split(":", 1)[1].strip()
            lines += [
                "",
                "LATEST COLLABORATION ARTIFACT (STRUCTURED, ADVISORY; WORKORDER REMAINS AUTHORITATIVE):",
                payload,
                "Use this artifact to make or justify the next bounded implementation decision. If it remains unresolved and another check is necessary, use the same thread_id with action=recheck.",
            ]
        elif failure.startswith("PCP_REVIEW_FINDINGS:"):
            payload = failure.split(":", 1)[1].strip()
            lines += [
                "",
                "INDEPENDENT REVIEW FINDINGS (COMPACT EVIDENCE PACK):",
                payload,
                "Repair only the actionable findings within the WorkOrder. Do not reinterpret scope or copy a reviewer transcript into the repository.",
            ]
        else:
            lines += [
                "",
                "PREVIOUS VERIFICATION FAILURE:",
                failure,
                "Fix the root cause without expanding or reinterpreting the WorkOrder.",
            ]
    return "\n".join(lines)


def planning_prompt(
    *,
    task: dict[str, Any],
    repo_analysis: dict[str, Any],
    work_order: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
) -> str:
    lines = [
        "Analyze this repository and produce a concise implementation plan. Do not edit files.",
        "Use built-in file tools and sandboxed/read-only Git commands only. Do not request sandbox bypass or unsandboxed execution.",
        "Prefer existing project patterns and tests. Identify risks and exact verification steps.",
    ]
    lines += _contract_lines(work_order=work_order, baseline=baseline)
    lines += [
        f"CANONICAL TASK: {task.get('title')}\n{task.get('description','')}",
        f"REPOSITORY SIGNALS: {json.dumps(repo_analysis, ensure_ascii=False)}",
    ]
    return "\n".join(lines)


def evaluator_prompt(
    *,
    task: dict[str, Any],
    diff: str,
    verification: dict[str, Any],
    work_order: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
    developer_report: str | None = None,
) -> str:
    pack = reviewer_evidence_pack(
        task=task,
        diff=diff,
        verification=verification,
        work_order=work_order,
        developer_report=developer_report,
    )
    baseline_summary = {
        "revision": (baseline or {}).get("revision"),
        "source_commit": (baseline or {}).get("source_commit"),
    }
    return "\n".join(
        [
            "Review the current workspace changes read-only. Do not edit files.",
            "AUTHORITATIVE WORKORDER / TASK CONTRACT: preserve the canonical contract embedded in REVIEW_EVIDENCE_PACK; it overrides advisory context.",
            "The compact REVIEW_EVIDENCE_PACK is the default context. Do not request or reconstruct full agent/model transcripts.",
            "If the pack is insufficient for one concrete finding, use the permitted read-only repository access just in time and retrieve only the smallest relevant context.",
            "PASS only when the authoritative Task Contract/WorkOrder, scope, deterministic evidence, correctness, security, regressions and required tests are satisfactory.",
            "FAIL only for concise actionable findings that can change code/tests/decision; avoid style-only or speculative findings.",
            "Return exactly two lines: first PASS or FAIL; second REVIEW_JSON: followed by one compact JSON object.",
            'REVIEW_JSON schema: {"verdict":"pass|fail","summary":"...","findings":[{"id":"...","severity":"low|medium|high|critical","category":"correctness|security|regression|scope|tests|other","message":"...","evidence_refs":["path/check/ref"]}],"jit_context_used":false}',
            f"BASELINE_REF: {json.dumps(baseline_summary, ensure_ascii=False, sort_keys=True)}",
            f"REVIEW_EVIDENCE_PACK: {json.dumps(pack, ensure_ascii=False, sort_keys=True)}",
        ]
    )
