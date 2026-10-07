from __future__ import annotations

from copy import deepcopy
from typing import Any

from .storage import now


EPOCH_KEY = "standalone_antiloop_progress_epoch"


def _verification_signature(checkpoint: dict[str, Any]) -> str:
    streak = dict(
        checkpoint.get("deterministic_verification_failure_streak") or {}
    )
    return str(streak.get("signature") or "")


def _latest_diff_hash(
    checkpoint: dict[str, Any],
    progress: dict[str, Any],
    fallback: str = "",
) -> str:
    hashes = [
        str(item)
        for item in (progress.get("diff_hashes") or [])
        if str(item)
    ]
    if hashes:
        return hashes[-1]
    streak = dict(
        checkpoint.get("deterministic_verification_failure_streak") or {}
    )
    return str(streak.get("diff_hash") or fallback or "")


def start_pm_antiloop_epoch(
    checkpoint: dict[str, Any],
    progress: dict[str, Any],
    *,
    blocker_generation: str,
    diff_hash: str,
    selectors: list[str],
) -> dict[str, Any]:
    """Start one progress-sensitive anti-loop epoch without deleting history."""

    epoch = {
        "version": 1,
        "blocker_generation": str(blocker_generation),
        "selectors": sorted({str(item) for item in selectors if str(item)}),
        "started_at": now().isoformat(),
        "failure_fingerprint_start": len(
            list(progress.get("failure_fingerprints") or [])
        ),
        "progress_marker_start": len(
            list(progress.get("progress_markers") or [])
        ),
        "diff_hash_start": len(list(progress.get("diff_hashes") or [])),
        "latest_diff_hash": _latest_diff_hash(
            checkpoint,
            progress,
            fallback=diff_hash,
        ),
        "latest_verification_signature": _verification_signature(checkpoint),
        "baseline_counters": {
            key: progress.get(key)
            for key in (
                "iteration",
                "repair_iterations",
                "model_calls",
                "tool_calls",
                "test_runs",
                "elapsed_minutes",
            )
        },
        "progress_advances": [],
    }
    checkpoint[EPOCH_KEY] = epoch
    return deepcopy(epoch)


def effective_reassessment_progress(
    checkpoint: dict[str, Any],
    progress: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Return an epoch-local anti-loop view while preserving durable history.

    Numeric counters, scope, provider and DoD fields remain cumulative. Only the
    history arrays consumed by Router anti-loop logic are projected to the
    current PM-authorized epoch.

    A changed deterministic verification signature is strong material-progress
    evidence and advances the epoch baseline. When no signature exists, a
    changed diff hash is the conservative fallback.
    """

    raw_epoch = checkpoint.get(EPOCH_KEY)
    if not isinstance(raw_epoch, dict) or raw_epoch.get("version") != 1:
        return deepcopy(progress), False

    epoch = raw_epoch
    current_signature = _verification_signature(checkpoint)
    current_diff_hash = _latest_diff_hash(checkpoint, progress)

    prior_signature = str(epoch.get("latest_verification_signature") or "")
    prior_diff_hash = str(epoch.get("latest_diff_hash") or "")

    progress_kind = ""
    if current_signature and current_signature != prior_signature:
        progress_kind = "verification_signature"
    elif not current_signature and current_diff_hash and current_diff_hash != prior_diff_hash:
        progress_kind = "diff_hash"

    changed = False
    if progress_kind:
        advances = [
            deepcopy(item)
            for item in (epoch.get("progress_advances") or [])
            if isinstance(item, dict)
        ]
        advances.append(
            {
                "kind": progress_kind,
                "at": now().isoformat(),
                "from_diff_hash": prior_diff_hash,
                "to_diff_hash": current_diff_hash,
                "from_verification_signature": prior_signature,
                "to_verification_signature": current_signature,
            }
        )
        epoch["progress_advances"] = advances[-20:]
        epoch["failure_fingerprint_start"] = len(
            list(progress.get("failure_fingerprints") or [])
        )
        epoch["progress_marker_start"] = len(
            list(progress.get("progress_markers") or [])
        )
        epoch["diff_hash_start"] = len(list(progress.get("diff_hashes") or []))
        epoch["latest_diff_hash"] = current_diff_hash
        epoch["latest_verification_signature"] = current_signature
        epoch["last_progress_at"] = now().isoformat()
        checkpoint[EPOCH_KEY] = epoch
        changed = True

    effective = deepcopy(progress)
    for field, start_key in (
        ("failure_fingerprints", "failure_fingerprint_start"),
        ("progress_markers", "progress_marker_start"),
        ("diff_hashes", "diff_hash_start"),
    ):
        values = list(progress.get(field) or [])
        try:
            start = max(0, min(len(values), int(epoch.get(start_key) or 0)))
        except (TypeError, ValueError):
            start = 0
        effective[field] = values[start:]

    return effective, changed
