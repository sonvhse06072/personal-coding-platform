from __future__ import annotations

import json
from typing import Any


def execution_prompt(*, task: dict[str, Any], route: dict[str, Any], repo_analysis: dict[str, Any], plan: str | None = None, failure: str | None = None) -> str:
    strategy = route["strategy"]
    lines = [
        "You are executing a bounded coding job inside an isolated git workspace.",
        "The repository is the source of truth. Read existing requirements, architecture docs, tests and implementation before changing code.",
        "Do not commit, push, merge, deploy, modify git remotes, or run Docker/DDEV. The runtime owns those actions.",
        "Do not broaden scope. If you discover desirable unrelated work, mention it in your final note but do not implement it.",
        "Stop when the requested behavior is implemented. The runtime will run deterministic verification afterward.",
        "",
        f"TASK:\n{task.get('title')}\n{task.get('description','')}",
        "",
        f"PROFILE: {strategy.get('profile')}",
        f"DEFINITION OF DONE: {json.dumps(strategy.get('definition_of_done', {}), ensure_ascii=False)}",
        f"REPOSITORY SIGNALS: {json.dumps(repo_analysis, ensure_ascii=False)}",
    ]
    if plan:
        lines += ["", "PLANNER OUTPUT:", plan]
    if failure:
        lines += ["", "PREVIOUS VERIFICATION FAILURE:", failure, "Fix the root cause without expanding scope."]
    return "\n".join(lines)


def planning_prompt(*, task: dict[str, Any], repo_analysis: dict[str, Any]) -> str:
    return "\n".join([
        "Analyze this repository and produce a concise implementation plan. Do not edit files.",
        "Prefer existing project patterns and tests. Identify risks and exact verification steps.",
        f"TASK: {task.get('title')}\n{task.get('description','')}",
        f"REPOSITORY SIGNALS: {json.dumps(repo_analysis, ensure_ascii=False)}",
    ])


def evaluator_prompt(*, task: dict[str, Any], diff: str, verification: dict[str, Any]) -> str:
    return "\n".join([
        "Review the current workspace changes read-only. Do not edit files.",
        "Return PASS if the implementation satisfies the task with no material correctness, security, regression, or missing-test issue. Otherwise return FAIL and concise actionable findings.",
        f"TASK: {task.get('title')}\n{task.get('description','')}",
        f"VERIFICATION: {json.dumps(verification, ensure_ascii=False)}",
        "DIFF:", diff,
    ])
