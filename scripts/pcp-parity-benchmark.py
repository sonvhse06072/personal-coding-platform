#!/usr/bin/env python3
"""Read-only, evidence-labeled PCP vs direct-Codex accepted-outcome comparator.

This script never invokes agents, providers, DDEV, GitHub, or local workspaces.
It validates operator-collected paired records and abstains when a comparable
cohort is too small. Synthetic test records MUST NOT be presented as results.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import statistics
import sys
from typing import Any

ARMS = ("direct", "pcp")
CATEGORIES = ("drupal", "frontend", "repair", "php")
PRODUCT_CATEGORIES = ("drupal", "frontend", "repair")
COMPARE_FIELDS = (
    "task_id",
    "task_type",
    "source_sha",
    "acceptance_sha256",
    "environment_id",
    "environment_class",
    "model_id",
    "reasoning_effort",
    "verification_policy",
    "review_policy",
)
REQUIRED_FIELDS = frozenset((
    "trial_id", "arm", *COMPARE_FIELDS, "started_at", "ended_at",
    "outcome", "quality", "evidence_url",
))
OPTIONAL_COUNTS = frozenset((
    "model_calls", "tool_calls", "test_runs", "repair_iterations",
    "owner_interventions", "input_tokens", "cached_input_tokens",
    "output_tokens",
))
QUALITY_KEYS = frozenset(("deterministic", "review", "ci", "visual"))
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MIN_P50_PAIRS = 3
MIN_P90_PAIRS = 10


def _text(value: Any, label: str, *, limit: int = 160) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise ValueError(f"{label} must be nonempty text (max {limit})")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _clock(value: Any, label: str) -> datetime:
    raw = _text(value, label, limit=60)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include an explicit UTC offset")
    return parsed


def validate_record(raw: Any, number: int) -> dict[str, Any]:
    label = f"records[{number}]"
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    unexpected = set(raw) - REQUIRED_FIELDS - OPTIONAL_COUNTS
    missing = REQUIRED_FIELDS - set(raw)
    if unexpected or missing:
        raise ValueError(f"{label} has unknown/missing fields: {sorted(unexpected)}/{sorted(missing)}")

    record = {key: _text(raw[key], f"{label}.{key}") for key in
              ("trial_id", *COMPARE_FIELDS, "arm", "outcome", "evidence_url")}
    if record["arm"] not in ARMS:
        raise ValueError(f"{label}.arm must be direct or pcp")
    if record["task_type"] not in CATEGORIES:
        raise ValueError(f"{label}.task_type is not an accepted fixture class")
    if record["environment_class"] not in ("isolated_fixture", "historical_record"):
        raise ValueError(f"{label}.environment_class cannot authorize live workspace use")
    if record["outcome"] not in ("accepted", "failed", "aborted"):
        raise ValueError(f"{label}.outcome must be accepted/failed/aborted")
    if not HEX40.fullmatch(record["source_sha"]):
        raise ValueError(f"{label}.source_sha must be an exact 40-hex source revision")
    if not HEX64.fullmatch(record["acceptance_sha256"]):
        raise ValueError(f"{label}.acceptance_sha256 must hash identical acceptance criteria")
    if not record["evidence_url"].startswith("https://github.com/"):
        raise ValueError(f"{label}.evidence_url must be a GitHub evidence URL")

    start = _clock(raw["started_at"], f"{label}.started_at")
    end = _clock(raw["ended_at"], f"{label}.ended_at")
    elapsed_seconds = (end - start).total_seconds()
    if not 0 < elapsed_seconds <= 60 * 60 * 24 * 30:
        raise ValueError(f"{label} has an invalid positive bounded wall interval")
    record["elapsed_seconds"] = elapsed_seconds

    quality = raw["quality"]
    if not isinstance(quality, dict) or set(quality) != QUALITY_KEYS:
        raise ValueError(f"{label}.quality requires deterministic/review/ci/visual")
    if any(type(quality[k]) is not bool for k in ("deterministic", "review", "ci")):
        raise ValueError(f"{label}.quality requires real boolean final gates")
    if quality["visual"] is not None and type(quality["visual"]) is not bool:
        raise ValueError(f"{label}.quality.visual must be bool or null")
    if record["outcome"] == "accepted":
        if not all(quality[k] for k in ("deterministic", "review", "ci")):
            raise ValueError(f"{label} cannot claim accepted with failed/missing final checks")
        if record["task_type"] == "frontend" and quality["visual"] is not True:
            raise ValueError(f"{label} frontend acceptance requires actual visual pass")
    record["quality"] = quality
    for key in OPTIONAL_COUNTS:
        value = raw.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{label}.{key} must be a nonnegative integer or null")
        record[key] = value
    return record


def _quantile(values: list[float], percentile: int) -> float:
    sorted_values = sorted(values)
    if percentile == 50:
        return statistics.median(sorted_values)
    if percentile == 90:
        return sorted_values[math.ceil(0.90 * len(sorted_values)) - 1]
    raise ValueError("unsupported quantile")


def _ratio(pcp: float, direct: float) -> float:
    return round(pcp / direct, 4)


def summarize(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != {"schema_version", "records"}:
        raise ValueError("input requires exactly schema_version and records")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported benchmark schema_version")
    raw_records = data["records"]
    if not isinstance(raw_records, list) or len(raw_records) > 500:
        raise ValueError("records must be a list with at most 500 entries")

    by_trial: dict[str, dict[str, dict[str, Any]]] = {}
    outcome_counts = {arm: {"accepted": 0, "failed": 0, "aborted": 0} for arm in ARMS}
    telemetry_observed = {arm: {name: 0 for name in OPTIONAL_COUNTS} for arm in ARMS}
    for i, raw in enumerate(raw_records):
        record = validate_record(raw, i)
        arms = by_trial.setdefault(record["trial_id"], {})
        if record["arm"] in arms:
            raise ValueError("duplicate trial_id + arm; repeated runs must use distinct trial IDs")
        arms[record["arm"]] = record
        outcome_counts[record["arm"]][record["outcome"]] += 1
        for name in OPTIONAL_COUNTS:
            telemetry_observed[record["arm"]][name] += record[name] is not None

    accepted: list[tuple[dict[str, Any], dict[str, Any]]] = []
    excluded: list[dict[str, str]] = []
    historical_accepted_pairs = 0
    php_smoke_pairs = 0
    for trial_id, arms in sorted(by_trial.items()):
        if set(arms) != set(ARMS):
            excluded.append({"trial_id": trial_id, "reason": "missing_arm"})
            continue
        direct, pcp = arms["direct"], arms["pcp"]
        if any(direct[key] != pcp[key] for key in COMPARE_FIELDS):
            excluded.append({"trial_id": trial_id, "reason": "noncomparable_pinned_conditions"})
            continue
        if direct["outcome"] != "accepted" or pcp["outcome"] != "accepted":
            excluded.append({"trial_id": trial_id, "reason": "at_least_one_arm_not_accepted"})
            continue
        # Historical outcomes are useful evidence, but never a controlled A/B
        # experiment. A generic PHP smoke fixture is not a Drupal integration
        # task and must not inflate the G0 product-cohort percentiles.
        if direct["environment_class"] == "historical_record":
            historical_accepted_pairs += 1
            excluded.append({"trial_id": trial_id, "reason": "historical_not_controlled"})
            continue
        if direct["task_type"] == "php":
            php_smoke_pairs += 1
            excluded.append({"trial_id": trial_id, "reason": "php_smoke_not_drupal"})
            continue
        accepted.append((direct, pcp))

    count = len(accepted)
    coverage = {category: sum(a["task_type"] == category for a, _ in accepted)
                for category in PRODUCT_CATEGORIES}
    durations = {arm: [pair[0 if arm == "direct" else 1]["elapsed_seconds"]
                       for pair in accepted] for arm in ARMS}
    quantiles: dict[str, Any] = {"p50": None, "p90": None}
    for name, percentile, threshold in (("p50", 50, MIN_P50_PAIRS),
                                        ("p90", 90, MIN_P90_PAIRS)):
        if count >= threshold:
            d = _quantile(durations["direct"], percentile)
            p = _quantile(durations["pcp"], percentile)
            quantiles[name] = {
                "direct_seconds": round(d, 3),
                "pcp_seconds": round(p, 3),
                "pcp_to_direct_ratio": _ratio(p, d),
                "target_ratio_max": 1.25 if percentile == 50 else 1.50,
            }

    sufficient = count >= MIN_P90_PAIRS and all(coverage.values())
    return {
        "schema_version": 1,
        "measurement_kind": "paired_end_to_end_accepted_outcomes",
        "status": "metrics_available_human_g0_gate_required" if sufficient else "insufficient_evidence",
        "total_records": len(raw_records),
        "paired_trial_ids": sum(set(arms) == set(ARMS) for arms in by_trial.values()),
        "accepted_comparable_pairs": count,
        "historical_accepted_pairs_excluded": historical_accepted_pairs,
        "php_smoke_pairs_excluded": php_smoke_pairs,
        "task_type_coverage": coverage,
        "excluded_trials": excluded,
        "all_attempt_outcomes": outcome_counts,
        "telemetry_records_with_value": telemetry_observed,
        "latency": quantiles,
        "qualifications": [
            "Measured trial records are externally collected; this tool neither runs nor authenticates them.",
            "Historical records and generic PHP smoke cases never contribute to controlled G0 percentiles.",
            "Drupal-category entries require independently verified actual Drupal test evidence.",
            "Unmatched, failed, aborted, or quality-ineligible trials are not silently called accepted.",
            "G0 Go/No-Go and protected trust-boundary changes always require separate human decision.",
            "Unavailable token/cached/quota evidence is not inferred or converted from characters.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Real evidence records in JSON")
    parser.add_argument("--output", type=Path, help="JSON report path (otherwise stdout)")
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > 2_000_000:
            raise ValueError("benchmark input exceeds the 2 MB bounded size")
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        report = summarize(payload)
        content = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.output:
            args.output.write_text(content, encoding="utf-8")
        else:
            sys.stdout.write(content)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"benchmark input rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
