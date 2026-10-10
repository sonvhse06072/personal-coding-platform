#!/usr/bin/env python3
"""Fail closed unless DDEV reports a collision-free, quiescent project registry.

DDEV 1.25.x uses newline-delimited JSON envelopes. ``ddev list -j`` returns
project records as ``.raw[]``; log messages may appear as separate envelopes.
A different DDEV project running on the same host is an infrastructure no-touch
risk. This checker never starts, stops, or otherwise modifies a project.
"""

from __future__ import annotations

import json
import sys
from typing import Any

STOPPED = frozenset({"stopped", "exited"})


def _documents(text: str) -> list[dict[str, Any]]:
    """Parse a single JSON envelope or newline-delimited DDEV JSON envelopes."""
    text = text.strip()
    if not text:
        raise ValueError("empty DDEV JSON output")
    try:
        single = json.loads(text)
    except json.JSONDecodeError:
        docs = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        docs = [single]
    if not docs or not all(isinstance(doc, dict) for doc in docs):
        raise ValueError("invalid DDEV JSON envelope")
    return docs


def extract_projects(text: str) -> list[dict[str, Any]]:
    candidates = []
    for doc in _documents(text):
        if str(doc.get("level", "")).lower() in {"error", "fatal"}:
            raise ValueError("DDEV reported a failed project registry lookup")
        if "raw" not in doc:
            # Non-result informational envelopes are allowed, but NEVER taken
            # as proof that there are zero projects.
            continue
        raw = doc["raw"]
        if isinstance(raw, list):
            candidates.append(raw)
        elif isinstance(raw, dict) and isinstance(raw.get("projects"), list):
            # Older fixtures/CLI representations for compatibility only.
            candidates.append(raw["projects"])
        else:
            raise ValueError("unexpected DDEV raw result structure")
    if len(candidates) != 1:
        raise ValueError("exactly one DDEV project list is required")
    projects = candidates[0]
    if any(not isinstance(p, dict) for p in projects):
        raise ValueError("invalid project in DDEV list")
    return projects


def check(text: str, name: str) -> tuple[bool, str]:
    if not name or not isinstance(name, str):
        raise ValueError("missing target DDEV project name")
    for project in extract_projects(text):
        registered = project.get("name")
        status = project.get("status")
        if not isinstance(registered, str) or not registered.strip():
            raise ValueError("DDEV project without a valid name")
        if registered.casefold() == name.casefold():
            return False, "DDEV fixture project name is already in use"
        if registered.casefold() == "router":
            continue
        if not isinstance(status, str) or not status.strip():
            raise ValueError("DDEV project without a valid status")
        if status.lower() not in STOPPED:
            # This is intentionally stricter than name collision alone:
            # starting a DDEV fixture while Chợ Nhạc or ANY other project is
            # active can disturb the shared DDEV router/services. No override.
            return False, "another DDEV project is active or status is unknown"
    return True, ""


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1]:
        return 3
    try:
        allowed, explanation = check(sys.stdin.read(), sys.argv[1])
        if not allowed:
            print(explanation, file=sys.stderr)
            return 4
        return 0
    except (ValueError, json.JSONDecodeError, UnicodeError) as exc:
        print(f"DDEV project registry cannot be safely verified: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
