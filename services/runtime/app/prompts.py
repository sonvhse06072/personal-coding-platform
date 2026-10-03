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


def _capability_boundary_lines(
    context: dict[str, Any] | None,
    *,
    evaluator: bool,
) -> list[str]:
    if not context:
        return []

    unavailable = {
        str(capability)
        for capability in (context.get("unavailable_capabilities") or [])
        if str(capability)
    }
    if not unavailable:
        return []

    raw_phase_map = context.get("capability_phases")
    phase_map: dict[str, list[str]] = {}
    if isinstance(raw_phase_map, dict):
        for capability, raw_phases in raw_phase_map.items():
            if str(capability) not in unavailable or not isinstance(raw_phases, list):
                continue
            phases = [str(phase) for phase in raw_phases if str(phase)]
            if phases:
                phase_map[str(capability)] = phases

    all_phases = [
        str(phase)
        for phase in (context.get("runtime_owned_verification_phases") or [])
        if str(phase)
    ]
    if not phase_map and len(unavailable) == 1 and all_phases:
        phase_map[next(iter(unavailable))] = all_phases

    lines = ["", "AGENT CAPABILITY BOUNDARY:"]

    listener_phases = phase_map.get("local_listener") or []
    if "local_listener" in unavailable and listener_phases:
        lines.append(
            "This agent invocation cannot run checks that require opening a local network listener."
        )
        if evaluator:
            lines += [
                "Do not attempt or repeatedly retry recreating those listener-dependent checks in this invocation.",
                "Judge the authoritative Runtime/DDEV verification evidence for these required phases:",
            ]
        else:
            lines += [
                "Do not attempt or repeatedly retry those listener-dependent checks.",
                "Runtime/ddev-executor owns these listener-dependent verification phases when they are applicable:",
            ]
        lines += [f"  - {phase}" for phase in listener_phases]

    php_phases = phase_map.get("php_runtime") or []
    if "php_runtime" in unavailable and php_phases:
        lines.append(
            "This agent invocation has no PHP runtime; direct PHP, PHPCS, PHPUnit, PHPStan, and Drupal PHP test commands cannot run in this sandbox."
        )
        if evaluator:
            lines += [
                "Do not attempt or repeatedly retry recreating PHP-dependent checks in this invocation.",
                "Judge the authoritative Runtime/DDEV verification evidence for these required PHP-dependent phases:",
            ]
        else:
            lines += [
                "Do not attempt or repeatedly retry PHP, PHPCS, PHPUnit, PHPStan, or other PHP-runtime commands here.",
                "Runtime/ddev-executor owns these PHP-dependent verification phases when they are applicable:",
            ]
        lines += [f"  - {phase}" for phase in php_phases]

    if len(lines) == 2:
        return []

    if evaluator:
        lines += [
            "The lack of an in-agent unavailable-capability check is not evidence that it passed.",
            "Missing or failing required Runtime/DDEV evidence must produce an actionable finding and must not receive PASS.",
            "Final Runtime/DDEV verification remains authoritative; do not automatically trust developer prose.",
        ]
    else:
        lines += [
            "Continue deterministic checks supported in this sandbox.",
            "Runtime/DDEV will run applicable project-owned final verification.",
            "Skipping an impossible in-agent check is not evidence that it passed.",
            "Final Runtime/DDEV verification remains authoritative.",
        ]
    return lines

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
    preview_context: dict[str, Any] | None = None,
    capability_context: dict[str, Any] | None = None,
    trusted_local_developer: bool = False,
) -> str:
    strategy = route["strategy"]
    if trusted_local_developer:
        lines = [
            "You are executing a bounded coding job in an exact Human-Owner-approved trusted local project workspace.",
            "The repository is the source of truth. Read existing requirements, architecture docs, tests and implementation before changing code.",
            "Use the local development environment directly when it helps finish the WorkOrder faster. You may run DDEV, Drupal/PHP tools, Node tooling, network-dependent package/test commands and local preview checks available to this workspace.",
            "Run focused authoritative tests yourself during implementation/repair when practical instead of deferring obvious failures to the later Runtime verification pass.",
            "Do not commit, push, merge, deploy, modify git remotes, alter PCP control-plane configuration, or change ProjectBaseline authority. Runtime/PM owns delivery and control-plane actions.",
            "Do not broaden scope. If you discover desirable unrelated work, mention it in your final note but do not implement it.",
            "Stop when the requested behavior and focused verification are complete. Runtime still owns final deterministic acceptance.",
        ]
    else:
        lines = [
            "You are executing a bounded coding job inside an isolated git workspace.",
            "The repository is the source of truth. Read existing requirements, architecture docs, tests and implementation before changing code.",
            "Do not commit, push, merge, deploy, modify git remotes, or run Docker/DDEV. The runtime owns those actions.",
            "Do not request sandbox bypass or unsandboxed execution. Use built-in file tools and sandboxed/read-only Git commands only; if a command is denied, continue without it.",
            "Do not broaden scope. If you discover desirable unrelated work, mention it in your final note but do not implement it.",
            "Stop when the requested behavior is implemented. The runtime will run deterministic verification afterward.",
        ]
    lines += _contract_lines(work_order=work_order, baseline=baseline)
    lines += _capability_boundary_lines(capability_context, evaluator=False)
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
        if str(collaboration_context.get("status") or "") == "pm_handoff":
            lines += [
                "This collaboration already reached its maximum bounded dialogue rounds and was handed to PM. Do not create another collaboration request or recheck for this thread.",
                "If PM resumed the job, act only on a concrete code-side repair identified by the latest handoff. If the handoff says no code-side repair remains and asks for deterministic/runtime verification, do not invent a code change; leave the diff unchanged and let Runtime verification execute.",
            ]
    if preview_context:
        lines += [
            "",
            "LOCAL PREVIEW CONTEXT (SANITIZED, ADVISORY):",
            json.dumps(preview_context, ensure_ascii=False, sort_keys=True),
            "Use it only for bounded local application review where your tooling supports browser/network access. Do not claim visual/browser review unless you actually performed it and have observable evidence.",
        ]
    if failure:
        if failure.startswith("PCP_COLLABORATION_CONTEXT:"):
            payload = failure.split(":", 1)[1].strip()
            try:
                collaboration_failure = json.loads(payload)
            except json.JSONDecodeError:
                collaboration_failure = {}
            lines += [
                "",
                "LATEST COLLABORATION ARTIFACT (STRUCTURED, ADVISORY; WORKORDER REMAINS AUTHORITATIVE):",
                payload,
            ]
            if str(collaboration_failure.get("status") or "") == "pm_handoff":
                lines += [
                    "This collaboration is already at its maximum bounded round and has been handed to PM. Do not request another recheck or create a replacement thread for the same question.",
                    "If PM resumed the job and the handoff identifies no remaining code-side repair, do not invent changes merely to continue; leave the diff unchanged so Runtime can perform the required deterministic verification.",
                ]
            else:
                lines += [
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
    preview_context: dict[str, Any] | None = None,
    capability_context: dict[str, Any] | None = None,
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
    lines = [
        "Review the current workspace changes read-only. Do not edit files.",
        "AUTHORITATIVE WORKORDER / TASK CONTRACT: preserve the canonical contract embedded in REVIEW_EVIDENCE_PACK; it overrides advisory context.",
        "Treat developer_report as advisory repair/rebuttal evidence: reconsider prior findings against it, but do not accept a developer claim automatically.",
        "The authoritative WorkOrder and deterministic repository evidence remain decisive when they conflict with developer_report.",
        "The compact REVIEW_EVIDENCE_PACK is the default context. Do not request or reconstruct full agent/model transcripts.",
        "If the pack is insufficient for one concrete finding, use the permitted read-only repository access just in time and retrieve only the smallest relevant context.",
        "PASS only when the authoritative Task Contract/WorkOrder, scope, deterministic evidence, correctness, security, regressions and required tests are satisfactory.",
        "FAIL only for concise actionable findings that can change code/tests/decision; avoid style-only or speculative findings.",
    ]
    lines += _capability_boundary_lines(capability_context, evaluator=True)
    lines += [
        "Return exactly two lines: first PASS or FAIL; second REVIEW_JSON: followed by one compact JSON object.",
        'REVIEW_JSON schema: {"verdict":"pass|fail","summary":"...","findings":[{"id":"...","severity":"low|medium|high|critical","category":"correctness|security|regression|scope|tests|other","message":"...","evidence_refs":["path/check/ref"]}],"jit_context_used":false}',
        f"BASELINE_REF: {json.dumps(baseline_summary, ensure_ascii=False, sort_keys=True)}",
        (
            "LOCAL_PREVIEW_CONTEXT: "
            + json.dumps(preview_context, ensure_ascii=False, sort_keys=True)
            if preview_context
            else "LOCAL_PREVIEW_CONTEXT: unavailable"
        ),
        "A Ready preview is an optional review surface, not proof that visual/browser review occurred. Claim browser evidence only when tooling actually used it.",
        f"REVIEW_EVIDENCE_PACK: {json.dumps(pack, ensure_ascii=False, sort_keys=True)}",
    ]
    return "\n".join(lines)
