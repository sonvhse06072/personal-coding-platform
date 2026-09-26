#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from context_memory import compose_context, render_context_text


def _repo_root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compose a deterministic PCP Tier-0/Tier-3 context pack."
    )
    parser.add_argument("--repo-root")
    parser.add_argument("--project-id", default="personal-coding-platform")
    parser.add_argument(
        "--role",
        default="specialist",
        choices=[
            "product_manager",
            "pm",
            "developer",
            "dev",
            "reviewer",
            "debugger",
            "specialist",
        ],
    )
    parser.add_argument("--title", required=True)
    parser.add_argument("--task-type", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--issue")
    parser.add_argument("--pr")
    parser.add_argument("--job")
    parser.add_argument("--work-order")
    parser.add_argument("--file")
    parser.add_argument("--topic")
    parser.add_argument("--budget-chars", type=int, default=24000)
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
    )
    args = parser.parse_args()

    references = {
        key: value
        for key, value in {
            "issue": args.issue,
            "pr": args.pr,
            "job": args.job,
            "work_order": args.work_order,
            "file": args.file,
            "topic": args.topic,
        }.items()
        if value
    }

    pack = compose_context(
        _repo_root(args.repo_root),
        {
            "project_id": args.project_id,
            "role": args.role,
            "task": {
                "title": args.title,
                "task_type": args.task_type,
                "description": args.description,
            },
            "references": references,
            "budget_chars": args.budget_chars,
        },
    )

    if args.format == "text":
        sys.stdout.write(render_context_text(pack))
    else:
        json.dump(pack, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
