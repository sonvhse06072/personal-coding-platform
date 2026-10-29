#!/usr/bin/env python3
"""Summarize bounded JSON evidence records without assigning authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

CLASSES = ("SOURCE", "FIXTURE", "PHYSICAL", "LIVE")
OUTCOMES = ("PASS", "FAIL", "NOT_TESTED")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
FIELDS = frozenset({"id", "class", "outcome", "source_sha"})


class InputError(ValueError):
    pass


def summarize(records: Any) -> dict[str, Any]:
    if not isinstance(records, list):
        raise InputError("top_level_must_be_array")
    by_class = dict.fromkeys(CLASSES, 0)
    by_outcome = dict.fromkeys(OUTCOMES, 0)
    seen_ids: set[str] = set()
    common_sha: str | None = None
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise InputError(f"record_{index}_schema_invalid")
        record_id = record["id"]
        evidence_class = record["class"]
        outcome = record["outcome"]
        source_sha = record["source_sha"]
        if not isinstance(record_id, str) or not record_id.strip():
            raise InputError(f"record_{index}_id_invalid")
        if record_id in seen_ids:
            raise InputError("duplicate_id")
        seen_ids.add(record_id)
        if not isinstance(evidence_class, str) or evidence_class not in CLASSES:
            raise InputError(f"record_{index}_class_invalid")
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            raise InputError(f"record_{index}_outcome_invalid")
        if not isinstance(source_sha, str) or SHA_RE.fullmatch(source_sha) is None:
            raise InputError(f"record_{index}_source_sha_invalid")
        if common_sha is not None and source_sha != common_sha:
            raise InputError("source_sha_mismatch")
        common_sha = source_sha
        by_class[evidence_class] += 1
        by_outcome[outcome] += 1
    return {
        "count": len(records),
        "source_sha": common_sha,
        "by_class": by_class,
        "by_outcome": by_outcome,
        "fixture_evidence_is_live": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON file containing an array of evidence records")
    args = parser.parse_args(argv)
    try:
        records = json.loads(args.input.read_text(encoding="utf-8"))
        result = summarize(records)
    except (OSError, UnicodeError, json.JSONDecodeError, InputError) as exc:
        reason = str(exc) if isinstance(exc, InputError) else "input_unavailable_or_invalid"
        print(json.dumps({"status": "INVALID", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
