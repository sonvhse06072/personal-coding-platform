#!/usr/bin/env python3
"""PCP-light #734: one-use, zero-model continuation of the ORIGINAL worktree.

Only repairs a verified *single* "new blank line at EOF" Git index error,
with identical Python AST and an immutable private original-file snapshot.
Never re-dispatches Codex, deletes jobs, resets git or touches other projects.
The new draft PR still requires isolated hosted pytest CI and PM review.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

REPO = "sonvhse06072/personal-coding-platform"
ISSUE = 734
KEY = "pr-readiness-report-v1"
BASE = "86d34a495f87bb17a07fb18fc8ec64cbe4c6ecef"
BODY_SHA256 = "f01e7379f5eb4b4e9715cfb1984f2df13af181a6e6a5b249c694cb8b5e9cbcff"
BRANCH = "ai/pcp-light/" + KEY
FILES = frozenset({
    "scripts/pcp-light-pr-review.py",
    "tests/test_pcp_light_pr_review.py",
})
ROOT = Path.home() / ".pcp-light" / "jobs" / KEY
WS = ROOT / "workspace"
JOURNAL = ROOT / "journal.json"
RECEIPT = ROOT / "pr734-one-use-delivery.json"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
PR_RE = re.compile(
    r"https://github\.com/sonvhse06072/personal-coding-platform/pull/\d+\Z"
)


class Stop(RuntimeError):
    """Sanitized failure only; no raw tool outputs or private source."""


def require(value: bool, code: str) -> None:
    if not value:
        raise Stop(code)


def run(argv: list[str], *, cwd: Path | None = None, timeout: int = 30
        ) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, cwd=cwd, timeout=timeout, input=None,
            capture_output=True, text=True, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("pcp_light_734_tool_unavailable_or_timeout") from exc


def checked(argv: list[str], *, cwd: Path | None = None,
            timeout: int = 30) -> str:
    result = run(argv, cwd=cwd, timeout=timeout)
    require(result.returncode == 0, "pcp_light_734_host_command_failed")
    return result.stdout.strip()


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return run([
        "git", "-c", "core.fsmonitor=false",
        "-c", "core.hooksPath=/dev/null",
        "-C", str(WS), *args,
    ])


def git_ok(*args: str) -> str:
    value = git(*args)
    require(value.returncode == 0, "pcp_light_734_readonly_git_failed")
    return value.stdout.strip()


def validate_journal(j: Any) -> None:
    require(
        isinstance(j, dict)
        and j.get("issue") == ISSUE
        and j.get("key") == KEY
        and j.get("body_sha256") == BODY_SHA256
        and j.get("base_sha") == BASE
        and j.get("branch") == BRANCH
        and j.get("state") == "source_checked"
        and type(j.get("model_calls")) is int
        and j["model_calls"] == 1
        and isinstance(j.get("usage"), dict)
        and j["usage"].get("terminal") == "turn.completed"
        and j.get("changed_paths") == sorted(FILES)
        and j.get("syntax_checked_paths") == sorted(FILES)
        and j.get("local_tests_executed") == 0
        and j.get("hosted_full_ci") == "PENDING",
        "pcp_light_734_original_journal_incompatible",
    )


def exact_staged_paths(raw: str) -> set[str]:
    """Allow only new staged regular Python files, no renames or deletions."""
    entries = raw.split("\0")
    if entries and entries[-1] == "":
        entries.pop()
    require(len(entries) == 2 * len(FILES),
            "pcp_light_734_staged_scope_mismatch")
    names: set[str] = set()
    for i in range(0, len(entries), 2):
        status, name = entries[i:i + 2]
        require(status == "A" and name in FILES and name not in names,
                "pcp_light_734_staged_scope_mismatch")
        names.add(name)
    require(names == FILES, "pcp_light_734_staged_scope_mismatch")
    return names


def warning_target(rc: int, out: str, err: str) -> str:
    """Never print diagnostic source lines; fix ONLY recognized EOF warning."""
    require(rc == 2 and not err
            and len(out.splitlines()) == 1,
            "pcp_light_734_unrecognized_git_check")
    match = re.fullmatch(r"(.+):([1-9]\d*): new blank line at EOF\.",
                         out.strip())
    require(match is not None and match.group(1) in FILES,
            "pcp_light_734_unrecognized_git_check")
    return match.group(1)


def corrected_eof(original: bytes) -> bytes:
    """Remove only blank extra LF lines at EOF with Python AST unchanged."""
    require(0 < len(original) <= 262144
            and b"\r" not in original
            and original.endswith(b"\n\n"),
            "pcp_light_734_eof_not_simple_blank")
    corrected = original.rstrip(b"\n") + b"\n"
    require(corrected != original,
            "pcp_light_734_no_eof_change")
    try:
        before = ast.dump(ast.parse(original), include_attributes=False)
        after = ast.dump(ast.parse(corrected), include_attributes=False)
    except (SyntaxError, TypeError, ValueError) as exc:
        raise Stop("pcp_light_734_python_syntax_invalid") from exc
    require(before == after, "pcp_light_734_semantic_change_denied")
    return corrected


def private_create(path: Path, value: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def receipt(state: str, **values: Any) -> None:
    # Separate one-use metadata, never mutate original one-call journal.
    if state == "claimed":
        private_create(RECEIPT, (json.dumps(
            {"state": state, "additional_model_calls": 0, **values},
            sort_keys=True,
        ) + "\n").encode())
        return
    old = json.loads(RECEIPT.read_text(encoding="utf-8"))
    payload = {**old, "state": state, **values}
    temp = ROOT / "pr734-one-use-delivery.tmp"
    private_create(temp, (json.dumps(payload, sort_keys=True) + "\n").encode())
    os.replace(temp, RECEIPT)


def validate_owner_issue() -> None:
    data = checked(["gh", "api", "--method", "GET",
                    f"repos/{REPO}/issues/{ISSUE}"], timeout=30)
    try:
        issue = json.loads(data)
        require(
            isinstance(issue, dict)
            and issue.get("number") == ISSUE
            and issue.get("state") == "open"
            and issue.get("user", {}).get("login") == "sonvhse06072"
            and isinstance(issue.get("body"), str)
            and hashlib.sha256(issue["body"].encode("utf-8")).hexdigest()
            == BODY_SHA256,
            "pcp_light_734_issue_identity_drift",
        )
    except (ValueError, TypeError, AttributeError) as exc:
        raise Stop("pcp_light_734_issue_unreadable") from exc


def preflight(repo: Path, expected_main: str) -> dict[str, Any]:
    require(os.geteuid() != 0
            and isinstance(expected_main, str)
            and SHA_RE.fullmatch(expected_main) is not None,
            "pcp_light_734_identity_or_main_sha_invalid")
    require(repo.is_dir() and not repo.is_symlink(),
            "pcp_light_734_repo_invalid")
    require(checked(["git", "-C", str(repo), "rev-parse",
                     "--show-toplevel"]) == str(repo)
            and checked(["git", "-C", str(repo), "branch",
                         "--show-current"]) == "main"
            and checked(["git", "-C", str(repo), "rev-parse",
                         "HEAD"]) == expected_main
            and not checked(["git", "-C", str(repo), "status",
                             "--porcelain"]),
            "pcp_light_734_local_main_mismatch")
    require(checked(["git", "-C", str(repo), "remote", "get-url",
                     "origin"]) in {
        f"https://github.com/{REPO}.git", f"https://github.com/{REPO}",
        f"git@github.com:{REPO}.git", f"git@github.com:{REPO}",
    }, "pcp_light_734_wrong_origin")

    for path in (ROOT, WS, JOURNAL):
        require(path.exists() and not path.is_symlink()
                and path.stat().st_uid == os.geteuid(),
                "pcp_light_734_original_files_unavailable")
    require(ROOT.is_dir() and WS.is_dir() and JOURNAL.is_file()
            and stat.S_IMODE(ROOT.stat().st_mode) == 0o700
            and stat.S_IMODE(JOURNAL.stat().st_mode) == 0o600,
            "pcp_light_734_journal_not_private")
    require(not RECEIPT.exists() and not RECEIPT.is_symlink()
            and not (ROOT / "pr734-one-use-delivery.tmp").exists(),
            "pcp_light_734_already_claimed")

    try:
        original_journal = JOURNAL.read_bytes()
        data = json.loads(original_journal)
    except (ValueError, OSError) as exc:
        raise Stop("pcp_light_734_original_journal_unreadable") from exc
    validate_journal(data)
    require(git_ok("rev-parse", "--show-toplevel") == str(WS)
            and git_ok("branch", "--show-current") == BRANCH
            and git_ok("rev-parse", "HEAD") == BASE,
            "pcp_light_734_workspace_provenance_drift")
    common = git_ok("rev-parse", "--git-common-dir")
    require(Path(common).resolve() == (repo / ".git").resolve(),
            "pcp_light_734_foreign_worktree")

    require(not git_ok("diff", "--no-ext-diff", "--name-only")
            and not git_ok("ls-files", "--others", "--exclude-standard"),
            "pcp_light_734_unstaged_or_untracked_files")
    paths = exact_staged_paths(
        git_ok("diff", "--cached", "--no-ext-diff",
               "--no-renames", "--name-status", "-z")
        # .strip() in git_ok is okay only for NUL boundaries; no whitespace paths
    )
    assert paths == FILES
    require(set(git_ok("diff", "--cached", "--no-ext-diff",
                       "--name-only").splitlines()) == FILES,
            "pcp_light_734_diff_scope_mismatch")
    for relative in FILES:
        target = WS / relative
        require(target.is_file() and not target.is_symlink()
                and target.stat().st_uid == os.geteuid(),
                "pcp_light_734_changed_path_not_regular")
    check = git("diff", "--cached", "--no-ext-diff", "--check")
    target_name = warning_target(check.returncode, check.stdout, check.stderr)
    source = (WS / target_name).read_bytes()
    corrected = corrected_eof(source)
    validate_owner_issue()
    return {
        "issue": ISSUE, "source_parent": BASE,
        "branch": BRANCH, "original_model_calls": 1,
        "changed_paths": sorted(FILES),
        "warning_type": "new_blank_line_at_eof",
        "warning_path": target_name,
        "corrected_bytes_removed": len(source) - len(corrected),
        "original_journal_sha256": hashlib.sha256(original_journal).hexdigest(),
        "model_elapsed_seconds": data.get("elapsed_seconds"),
        "original_file_sha256": hashlib.sha256(source).hexdigest(),
        "usage": {
            k: data["usage"].get(k)
            for k in (
                "input_tokens", "cached_input_tokens",
                "uncached_input_tokens", "output_tokens",
                "cached_input_share_percent",
            )
        },
        "context_footprint": data.get("context_footprint", {}),
    }


def draft_pr_body(state: dict[str, Any], candidate_sha: str) -> str:
    """Metadata only: carry existing #734 model evidence to the draft PR."""
    require(SHA_RE.fullmatch(candidate_sha) is not None,
            "pcp_light_734_candidate_sha_invalid")
    usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}
    sizes = state.get("context_footprint")
    sizes = sizes if isinstance(sizes, dict) else {}

    def token(name: str) -> int | None:
        item = usage.get(name)
        return item if type(item) is int and item >= 0 else None

    share = usage.get("cached_input_share_percent")
    if type(share) not in {int, float} or not math.isfinite(share):
        share = None
    elif not 0 <= share <= 100:
        share = None

    elapsed = state.get("model_elapsed_seconds")
    if type(elapsed) not in {int, float} or not math.isfinite(elapsed):
        elapsed = None
    elif elapsed < 0:
        elapsed = None
    evidence = {
        "schema": "pcp-light-pr-evidence-v1",
        "issue": ISSUE,
        "issue_body_sha256": BODY_SHA256,
        "base_sha": BASE,
        "candidate_sha": candidate_sha,
        "branch": BRANCH,
        "model_calls": 1,
        "additional_model_calls": 0,
        "terminal": "turn.completed",
        "model_elapsed_seconds": elapsed,
        "input_tokens": token("input_tokens"),
        "cached_input_tokens": token("cached_input_tokens"),
        "uncached_input_tokens": token("uncached_input_tokens"),
        "output_tokens": token("output_tokens"),
        "cached_input_share_percent": share,
        "provider_cash_cost": "UNAVAILABLE",
        "approved_changed_paths": sorted(FILES),
        "repair": "one_new_blank_line_at_eof",
        "python_ast_semantics": "UNCHANGED",
        "local_tests_executed": 0,
        "hosted_full_ci": "PENDING",
        "pm_review": "PENDING",
        "context_metadata": {
            key: val if type(val) is int and val >= 0 else None
            for key, val in sizes.items()
            if key in {
                "required_authority_bytes",
                "required_authority_files_present",
                "required_authority_files_expected",
                "allowlisted_existing_source_bytes",
                "allowlisted_existing_files",
                "prompt_utf8_bytes",
            }
        },
    }
    return (
        "PCP-light #734 one-turn Codex output, delivered with ONE "
        "bounded ZERO-MODEL same-worktree whitespace correction. "
        "Original journal preserved in state source_checked. "
        "Existing Codex file bytes privately snapshotted. "
        "Metadata is informative, not signed attestation.\n\n"
        "## Execution evidence\n\n```json\n"
        + json.dumps(evidence, sort_keys=True, indent=2)
        + "\n```\n\n"
        "**Quality gate:** Full GitHub-hosted exact-HEAD PR CI "
        "and human PM source review are mandatory before merge; "
        "no local generated tests were executed on Owner WSL. "
        "No automatic merge, deployment, model rerun or cash-cost claim."
    )


def deliver(repo: Path, expected_main: str) -> dict[str, Any]:
    state = preflight(repo, expected_main)
    warning_path = state["warning_path"]
    source = (WS / warning_path).read_bytes()
    replacement = corrected_eof(source)
    # Claim before the first modification. Any STOP after this is terminal.
    receipt("claimed", **state)
    backup = ROOT / "pr734-original-codex-staged.snapshot"
    private_create(backup, source)  # Exact original bytes retained privately.
    fd = os.open(WS / warning_path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise Stop("pcp_light_734_eof_write_failed") from exc

    require(
        set(git_ok("diff", "--no-ext-diff", "--name-only").splitlines())
        == {warning_path},
        "pcp_light_734_unexpected_unstaged_change")
    checked(["git", "-C", str(WS), "add", "--", warning_path])
    result = git("diff", "--cached", "--no-ext-diff", "--check")
    require(result.returncode == 0 and not result.stdout and not result.stderr,
            "pcp_light_734_whitespace_gate_still_failed")
    require(exact_staged_paths(git_ok(
        "diff", "--cached", "--no-ext-diff", "--no-renames",
        "--name-status", "-z")) == FILES
            and not git_ok("diff", "--no-ext-diff", "--name-only")
            and not git_ok("ls-files", "--others", "--exclude-standard"),
            "pcp_light_734_changed_scope_after_fix")
    receipt("quality_gate_passed")

    checked([
        "git", "-C", str(WS), "-c", "core.hooksPath=/dev/null",
        "-c", "user.name=PCP-light Operator",
        "-c", "user.email=pcp-light@localhost",
        "commit", "-m", "feat(pcp-light): read-only PR readiness report",
    ], timeout=90)
    commit_sha = git_ok("rev-parse", "HEAD")
    require(SHA_RE.fullmatch(commit_sha) is not None
            and git_ok("rev-parse", "HEAD^") == BASE
            and set(git_ok("diff", "--no-ext-diff", "--name-only",
                           BASE, "HEAD").splitlines()) == FILES
            and not git_ok("status", "--porcelain"),
            "pcp_light_734_commit_provenance_failed")
    receipt("committed", candidate_sha=commit_sha)
    checked(["git", "-C", str(WS), "push", "origin",
             "HEAD:refs/heads/" + BRANCH], timeout=140)
    receipt("pushed", candidate_sha=commit_sha)
    body = draft_pr_body(state, commit_sha)
    pr_url = checked([
        "gh", "pr", "create", "--repo", REPO,
        "--draft", "--base", "main", "--head", BRANCH,
        "--title", "PCP-light #734: read-only PR readiness report",
        "--body", body,
    ], cwd=WS, timeout=90)
    require(PR_RE.fullmatch(pr_url) is not None,
            "pcp_light_734_pr_not_confirmed")
    receipt("draft_pr_created", pr=pr_url)
    return {
        "status": "PCP_LIGHT_734_DRAFT_PR_AWAITING_HOSTED_CI",
        "candidate_sha": commit_sha,
        "pr": pr_url,
        "original_model_calls": 1,
        "additional_model_calls": 0,
        "original_journal_preserved": True,
        "eof_whitespace_repair_lines": 1,
        "local_tests_executed": 0,
        "hosted_full_ci": "PENDING",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--expected-main-sha", required=True)
    parser.add_argument("--deliver", action="store_true")
    args = parser.parse_args()
    try:
        repo = Path(args.repo_root).expanduser().resolve()
        result = (
            deliver(repo, args.expected_main_sha)
            if args.deliver
            else {"status": "PCP_LIGHT_734_READONLY_READY",
                  "additional_model_calls": 0,
                  **preflight(repo, args.expected_main_sha)}
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Stop, OSError, ValueError, FileExistsError) as exc:
        marker = str(exc) if isinstance(exc, Stop) else "pcp_light_734_io_stop"
        print(json.dumps({
            "status": "STOP_PCP_LIGHT_734_DELIVERY",
            "blocker": marker,
            "no_automatic_retry": True,
            "no_cleanup": True,
            "additional_model_calls": 0,
            "original_journal_preserved": True,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
