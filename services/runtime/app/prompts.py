from __future__ import annotations

import json
from typing import Any


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


def execution_prompt(
    *,
    task: dict[str, Any],
    route: dict[str, Any],
    repo_analysis: dict[str, Any],
    plan: str | None = None,
    failure: str | None = None,
    work_order: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
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
    if failure:
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
) -> str:
    lines = [
        "Review the current workspace changes read-only. Do not edit files.",
        "Use built-in file tools and sandboxed/read-only Git commands only. Do not request sandbox bypass or unsandboxed execution.",
        "Return PASS only if the implementation satisfies the authoritative WorkOrder (when present), acceptance criteria, project alignment, and deterministic evidence with no material correctness, security, regression, scope, or missing-test issue. Otherwise return FAIL and concise actionable findings.",
    ]
    lines += _contract_lines(work_order=work_order, baseline=baseline)
    lines += [
        f"CANONICAL TASK: {task.get('title')}\n{task.get('description','')}",
        f"VERIFICATION: {json.dumps(verification, ensure_ascii=False)}",
        "DIFF:",
        diff,
    ]
    return "\n".join(lines)
