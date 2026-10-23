#!/usr/bin/env python3
"""Read-only PCP GitHub PM handoff, with NO remote coding execution authority.

The input is an *untrusted* GitHub issue snapshot. Callers must independently
fetch and authenticate the real issue, body digest and current main SHA using
an approved GitHub client. This program only checks a bounded source-task
contract; it does not authenticate GitHub, code, dispatch, merge or deploy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

REPOSITORY = "sonvhse06072/personal-coding-platform"
OWNER = "sonvhse06072"
MARKER = "<!-- coding-platform:pcp-remote-source:v1 -->"
MODE = "github_source_pr_only"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
KEY_RE = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
RESERVED = ("g0-", "g1-", "f2-", "chonhac-")
REQUIRED_FIELDS = frozenset({
    "version", "key", "base_sha", "goal", "allowed_paths", "mode",
})
# Never let a task edit its own intake gate, including its regression test.
SELF_PROTECTED = frozenset({
    "scripts/pcp-light-remote-intake.py",
    "tests/test_pcp_light_remote_intake.py",
})


class Stop(ValueError):
    """Stable code only; never print supplied task text or credentials."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Stop(reason)


def allowed_path(value: Any) -> bool:
    """PCP-only source/test/doc type and directory scope; no protected paths."""
    if not isinstance(value, str) or not 1 <= len(value) <= 240:
        return False
    if "\\" in value or "\x00" in value or value in SELF_PROTECTED:
        return False
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value
            or any(part in {".", "..", ""} for part in value.split("/"))):
        return False
    parts = path.parts
    if len(parts) == 2 and parts[0] == "scripts":
        return (parts[1].startswith("pcp-light-")
                and parts[1].endswith(".py")
                and len(parts[1]) > len("pcp-light-.py"))
    if len(parts) == 2 and parts[0] == "tests":
        return (parts[1].startswith("test_pcp_light_")
                and parts[1].endswith(".py")
                and len(parts[1]) > len("test_pcp_light_.py"))
    return (len(parts) >= 3 and parts[:2] == ("docs", "pcp-light")
            and parts[-1].endswith(".md") and len(parts[-1]) > 3)


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in out, "task_json_duplicate_fields")
        out[key] = value
    return out


def validate_snapshot(raw: Any, *, issue_number: int,
                      body_sha256: str, expected_main_sha: str) -> dict[str, Any]:
    """Check a *reported* Owner issue contract, not independent Owner consent.

    The caller must still check live GitHub authority and exact branch/head;
    untrusted JSON cannot prove a GitHub identity or grant source writes.
    """
    require(type(issue_number) is int and issue_number > 0, "issue_number_invalid")
    require(isinstance(body_sha256, str) and DIGEST_RE.fullmatch(body_sha256) is not None,
            "body_digest_invalid")
    require(isinstance(expected_main_sha, str)
            and SHA_RE.fullmatch(expected_main_sha) is not None,
            "expected_main_sha_invalid")
    require(isinstance(raw, dict), "issue_snapshot_invalid")
    require(type(raw.get("number")) is int and raw["number"] == issue_number
            and raw.get("state") == "open" and "pull_request" not in raw
            and isinstance(raw.get("user"), dict)
            and raw["user"].get("login") == OWNER
            and raw.get("repository_url") == f"https://api.github.com/repos/{REPOSITORY}"
            and raw.get("html_url") == f"https://github.com/{REPOSITORY}/issues/{issue_number}",
            "issue_identity_invalid")
    body = raw.get("body")
    require(isinstance(body, str) and len(body.encode("utf-8")) <= 16000,
            "issue_body_invalid")
    require(body.count(MARKER) == 1 and body.lstrip().startswith(MARKER),
            "task_marker_invalid")
    require(hashlib.sha256(body.encode("utf-8")).hexdigest() == body_sha256,
            "task_body_changed")
    try:
        contract = json.loads(body.strip()[len(MARKER):].strip(),
                              object_pairs_hook=_unique_fields)
    except Stop:
        raise
    except (TypeError, ValueError) as exc:
        raise Stop("task_json_invalid") from exc
    require(isinstance(contract, dict) and set(contract) == REQUIRED_FIELDS,
            "task_schema_invalid")
    key = contract["key"]
    goal = contract["goal"]
    require(type(contract["version"]) is int and contract["version"] == 1
            and contract["mode"] == MODE
            and isinstance(key, str) and KEY_RE.fullmatch(key) is not None
            and not key.startswith(RESERVED)
            and isinstance(contract["base_sha"], str)
            and contract["base_sha"] == expected_main_sha
            and isinstance(goal, str) and 20 <= len(goal) <= 4000,
            "task_fields_invalid")
    paths = contract["allowed_paths"]
    require(isinstance(paths, list) and 2 <= len(paths) <= 4
            and all(allowed_path(path) for path in paths)
            and len(set(paths)) == len(paths)
            and any(path.startswith("tests/test_pcp_light_")
                    and path.endswith(".py") for path in paths),
            "task_paths_invalid")
    return {
        "status": "SOURCE_CONTRACT_CHECKED_NOT_AUTHORIZED",
        "repository": REPOSITORY,
        "issue_number": issue_number,
        "key": key,
        "base_sha": expected_main_sha,
        "body_sha256": body_sha256,
        "goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        "allowed_paths": paths,
        "mode": MODE,
        "requires_live_github_verification": True,
        "requires_pm_review_and_exact_head_ci": True,
        "can_execute_agent_or_model": False,
        "can_issue_credentials": False,
        "can_merge_or_deploy": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-file", type=Path, required=True)
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--body-sha256", required=True)
    parser.add_argument("--expected-main-sha", required=True)
    args = parser.parse_args(argv)
    try:
        path = args.snapshot_file
        metadata = path.lstat()
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_size <= 65536,
                "snapshot_file_invalid")
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = validate_snapshot(
            raw, issue_number=args.issue_number,
            body_sha256=args.body_sha256, expected_main_sha=args.expected_main_sha,
        )
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        reason = exc.reason if isinstance(exc, Stop) else "snapshot_unavailable_or_invalid"
        print(json.dumps({"status": "STOP_REMOTE_SOURCE_INTAKE", "reason": reason},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
