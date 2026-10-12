#!/usr/bin/env python3
"""Conservative CI classifier for a Git --name-status -z diff.

Only T1 state and T3 Markdown changes can skip service tests.
Missing or malformed evidence always means the full test suite.
"""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath

FULL = "full"
DOCS = "docs_only"


def classify(raw: bytes) -> str:
    if not raw or len(raw) > 200_000 or not raw.endswith(b"\0"):
        return FULL
    try:
        parts = raw[:-1].decode("utf-8", "strict").split("\0")
    except UnicodeDecodeError:
        return FULL
    if not parts or len(parts) % 2 or len(parts) > 2000:
        return FULL
    seen: set[str] = set()
    for i in range(0, len(parts), 2):
        status, path = parts[i:i+2]
        if status not in {"A", "M"} or not path or path in seen:
            return FULL
        if path.startswith("/") or "\\" in path or any(
            ord(c) < 32 or ord(c) == 127 for c in path
        ):
            return FULL
        components = PurePosixPath(path).parts
        if path != "/".join(components) or any(
            c in {".", ".."} for c in components
        ):
            return FULL
        seen.add(path)
        if path == "docs/project/current-state.md":
            continue
        if (
            path.startswith("docs/project/history/")
            and path.endswith(".md")
            and len(components) >= 4
        ):
            continue
        return FULL
    return DOCS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diff-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        content = Path(args.diff_file).read_bytes()
        mode = classify(content)
    except OSError:
        mode = FULL
    with Path(args.output).open("a", encoding="utf-8") as stream:
        stream.write(f"mode={mode}\n")
    print(f"PCP CI scope: {mode}; root governance always runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
