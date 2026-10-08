#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from context_memory import compose_context, read_all_docs_chars


def _matches(identity: str, needle: str) -> bool:
    return needle.lower() in identity.lower()


def evaluate(repo_root: Path, fixture: dict[str, Any]) -> dict[str, Any]:
    baseline_chars = read_all_docs_chars(repo_root)
    rows: list[dict[str, Any]] = []

    required_total = 0
    required_hits = 0
    current_cases = 0
    stale_current_failures = 0
    authority_cases = 0
    authority_failures = 0
    unsupported_cases = 0
    unsupported_hits = 0
    selected_chars_total = 0
    composed_cases = 0
    compose_duration_ms: list[float] = []
    required_content_total = 0
    required_content_hits = 0

    for case in fixture.get("cases", []):
        started = time.perf_counter()
        try:
            pack = compose_context(repo_root, case["request"])
        except ValueError as exc:
            expected_error = str(case.get("expected_error_contains") or "")
            if not expected_error or expected_error.lower() not in str(exc).lower():
                raise
            rows.append({
                "id": case["id"],
                "kind": case.get("kind"),
                "passed": True,
                "expected_error_matched": expected_error,
                "compose_ms": round((time.perf_counter() - started) * 1000, 2),
            })
            continue

        if case.get("expected_error_contains"):
            rows.append({
                "id": case["id"],
                "kind": case.get("kind"),
                "passed": False,
                "missing_expected_error": case["expected_error_contains"],
            })
            continue

        compose_duration_ms.append((time.perf_counter() - started) * 1000)
        composed_cases += 1
        selected = [*pack.get("pinned", []), *pack.get("retrieved", [])]
        identities = [str(item.get("identity") or "") for item in selected]
        retrieved = pack.get("retrieved", [])

        required = list(case.get("required_identity_contains") or [])
        required_total += len(required)
        case_required_hits = 0
        missing: list[str] = []
        for needle in required:
            if any(_matches(identity, needle) for identity in identities):
                required_hits += 1
                case_required_hits += 1
            else:
                missing.append(needle)

        # Check that the *selected text* contains essential evidence; heading-only
        # recall can pass even when the correct passage was clipped or omitted.
        selected_text = "\n".join(str(item.get("content") or "") for item in selected).lower()
        retrieved_text = "\n".join(
            str(item.get("content") or "") for item in retrieved
        ).lower()
        required_content = list(case.get("required_content_contains") or [])
        required_content_total += len(required_content)
        missing_content = [
            needle for needle in required_content
            if str(needle).lower() not in selected_text
        ]
        required_content_hits += len(required_content) - len(missing_content)
        forbidden_retrieved = [
            needle for needle in case.get("forbidden_retrieved_content_contains") or []
            if str(needle).lower() in retrieved_text
        ]

        current_failure = False
        if case.get("kind") == "current":
            current_cases += 1
            if case.get("require_no_retrieved_t3") and any(
                item.get("tier") == "T3" for item in retrieved
            ):
                stale_current_failures += 1
                current_failure = True

        authority_failure = False
        if case.get("kind") == "authority":
            authority_cases += 1
            if missing:
                authority_failures += 1
                authority_failure = True

        unsupported_failure = False
        if case.get("kind") == "unsupported":
            unsupported_cases += 1
            if pack["retrieval"]["supported_memory_found"]:
                unsupported_failure = True
            else:
                unsupported_hits += 1

        supported_mismatch = False
        if "expect_supported_memory" in case:
            supported_mismatch = bool(
                pack["retrieval"]["supported_memory_found"]
            ) != bool(case["expect_supported_memory"])

        budget_failure = False
        if case.get("max_selected_chars") is not None:
            budget_failure = pack["selected_chars"] > int(
                case["max_selected_chars"]
            )

        selected_chars_total += pack["selected_chars"]
        rows.append(
            {
                "id": case["id"],
                "kind": case.get("kind"),
                "passed": not any(
                    [
                        missing,
                        missing_content,
                        forbidden_retrieved,
                        current_failure,
                        authority_failure,
                        unsupported_failure,
                        supported_mismatch,
                        budget_failure,
                    ]
                ),
                "required_hits": case_required_hits,
                "required_total": len(required),
                "missing_required": missing,
                "missing_required_content": missing_content,
                "forbidden_retrieved_content": forbidden_retrieved,
                "selected_chars": pack["selected_chars"],
                "retrieved_count": len(retrieved),
                "retrieved": [
                    {
                        "tier": item.get("tier"),
                        "identity": item.get("identity"),
                        "score": item.get("score"),
                    }
                    for item in retrieved
                ],
                "supported_memory_found": pack["retrieval"][
                    "supported_memory_found"
                ],
                "current_t3_failure": current_failure,
                "authority_failure": authority_failure,
                "unsupported_failure": unsupported_failure,
                "supported_expectation_failure": supported_mismatch,
                "budget_failure": budget_failure,
            }
        )

    case_count = len(rows)
    mean_selected = selected_chars_total / composed_cases if composed_cases else 0.0
    target_recall = required_hits / required_total if required_total else 1.0
    content_recall = (
        required_content_hits / required_content_total if required_content_total else 1.0
    )
    mean_compose_ms = (
        sum(compose_duration_ms) / len(compose_duration_ms)
        if compose_duration_ms else 0.0
    )
    stale_false_positive_rate = (
        stale_current_failures / current_cases if current_cases else 0.0
    )
    authority_conflict_failure_rate = (
        authority_failures / authority_cases if authority_cases else 0.0
    )
    abstention_accuracy = (
        unsupported_hits / unsupported_cases if unsupported_cases else 1.0
    )
    mean_context_ratio = mean_selected / baseline_chars if baseline_chars else 0.0

    return {
        "evaluation_version": fixture.get("version", 1),
        "cases": rows,
        "metrics": {
            "case_count": case_count,
            "composed_case_count": composed_cases,
            "required_target_recall": target_recall,
            "required_content_recall": content_recall,
            "mean_compose_ms": round(mean_compose_ms, 2),
            "stale_historical_false_positive_rate": stale_false_positive_rate,
            "authority_conflict_failure_rate": authority_conflict_failure_rate,
            "abstention_accuracy": abstention_accuracy,
            "read_all_docs_chars": baseline_chars,
            "mean_composed_context_chars": round(mean_selected, 2),
            "mean_context_ratio_vs_read_all": round(mean_context_ratio, 4),
            "mean_irrelevant_context_reduction": round(
                max(0.0, 1.0 - mean_context_ratio),
                4,
            ),
        },
        "passed": all(row["passed"] for row in rows)
        and target_recall == 1.0
        and content_recall == 1.0
        and stale_false_positive_rate == 0.0
        and authority_conflict_failure_rate == 0.0
        and abstention_accuracy == 1.0
        and mean_context_ratio < 0.50,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the deterministic PCP context composer."
    )
    parser.add_argument("--repo-root")
    parser.add_argument(
        "--fixture",
        default="config/context-memory-eval.json",
    )
    args = parser.parse_args()

    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else Path(__file__).resolve().parents[1]
    )
    fixture = json.loads(
        (repo_root / args.fixture).read_text(encoding="utf-8")
    )
    result = evaluate(repo_root, fixture)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
