#!/usr/bin/env python3
"""PCP-light #725: one *verification/delivery only* continuation.

Reuses the ORIGINAL Codex-edited worktree and journal. No Codex, no new job,
no new worktree, no Docker/PCP Runtime, no package install, no cleanup/retry.
No unreviewed Codex test code is executed on Owner WSL. Locally attest Python
syntax and exact scope; draft PR runs the FULL pytest suite on isolated hosted CI.
Any STOP leaves original code and both evidence files unchanged/preserved.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

REPO = "sonvhse06072/personal-coding-platform"
ISSUE = 725
KEY = "focused-tests-v1"
BASE = "1dcb7696dba25695054bb4743967ae71fc38c896"
ISSUE_SHA256 = "f9bbf88e12b01e0718bbd36d60e4bd591e0ba7ad8bf3eaf5b18a613a6258c04f"
BRANCH = "ai/pcp-light/" + KEY
FILES = frozenset({
    "scripts/pcp-light-run.py",
    "tests/test_pcp_light_run.py",
})
ROOT = Path.home() / ".pcp-light" / "jobs" / KEY
WORKSPACE = ROOT / "workspace"
JOURNAL = ROOT / "journal.json"
EVIDENCE = ROOT / "verification-continuation-v1.json"
SHA_RE = re.compile(r"[a-f0-9]{40}\Z")
PR_RE = re.compile(
    r"https://github\.com/sonvhse06072/personal-coding-platform/pull/[0-9]+\Z"
)


class Stop(RuntimeError):
    """A fixed code, never raw stdout, stderr, secrets, or model output."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise Stop(code)


def command(argv: list[str], *, cwd: Path | None = None,
            timeout: int = 45, env: dict[str, str] | None = None
            ) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("pcp_light_command_unavailable_or_timeout") from exc


def checked(argv: list[str], *, cwd: Path | None = None,
            timeout: int = 45, env: dict[str, str] | None = None) -> str:
    result = command(argv, cwd=cwd, timeout=timeout, env=env)
    require(result.returncode == 0, "pcp_light_host_command_failed")
    return result.stdout.strip()


def git(where: Path, *args: str) -> str:
    return checked(["git", "-C", str(where), *args], timeout=45)


def private_write_new(path: Path, contents: dict[str, Any]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(contents, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def evidence(state: str, **updates: Any) -> None:
    """Only mutate a separate verification journal, never original Codex state."""
    if state == "claimed":
        private_write_new(EVIDENCE, {"state": state, "model_calls_added": 0, **updates})
        return
    old = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    new = {**old, "state": state, **updates}
    temporary = ROOT / "verification-continuation-v1.tmp"
    private_write_new(temporary, new)
    os.replace(temporary, EVIDENCE)


def validate_journal(doc: Any) -> None:
    require(isinstance(doc, dict)
            and doc.get("issue") == ISSUE
            and doc.get("key") == KEY
            and doc.get("branch") == BRANCH
            and doc.get("base_sha") == BASE
            and doc.get("body_sha256") == ISSUE_SHA256
            and doc.get("state") == "model_finished"
            and type(doc.get("model_calls")) is int
            and doc["model_calls"] == 1
            and isinstance(doc.get("usage"), dict)
            and doc["usage"].get("terminal") == "turn.completed",
            "pcp_light_original_job_not_one_completed_codex_turn")


def inspect_changed_paths(where: Path) -> set[str]:
    changed: set[str] = set()
    for args in (
        ("diff", "--no-ext-diff", "--name-only", "HEAD"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        changed.update(git(where, *args).splitlines())
    changed.discard("")
    return changed


def validate_scope(files: set[str], *, staged: bool,
                   deleted: bool, symlinks: bool) -> None:
    require(files == FILES and not staged and not deleted and not symlinks,
            "pcp_light_exact_two_file_scope_or_index_changed")


def verify_original_issue() -> None:
    data = checked(["gh", "api", "--method", "GET", f"repos/{REPO}/issues/{ISSUE}"])
    try:
        obj = json.loads(data)
        body = obj["body"]
        require(type(obj["number"]) is int and obj["number"] == ISSUE
                and obj.get("state") == "open"
                and obj["user"]["login"] == "sonvhse06072"
                and isinstance(body, str)
                and hashlib.sha256(body.encode("utf-8")).hexdigest() == ISSUE_SHA256,
                "pcp_light_original_issue_identity_or_digest_changed")
    except (TypeError, KeyError, ValueError) as exc:
        raise Stop("pcp_light_original_issue_unavailable") from exc


def preflight(repo: Path, expected_main: str) -> dict[str, Any]:
    require(os.geteuid() != 0
            and SHA_RE.fullmatch(expected_main) is not None,
            "pcp_light_operator_identity_or_sha_invalid")
    require(repo.is_dir() and not repo.is_symlink()
            and git(repo, "rev-parse", "--show-toplevel") == str(repo)
            and git(repo, "branch", "--show-current") == "main"
            and git(repo, "rev-parse", "HEAD") == expected_main
            and git(repo, "status", "--porcelain") == "",
            "pcp_light_main_not_clean_exact_sha")
    require(git(repo, "remote", "get-url", "origin") in {
        f"https://github.com/{REPO}.git", f"https://github.com/{REPO}",
        f"git@github.com:{REPO}.git", f"git@github.com:{REPO}",
    }, "pcp_light_repository_origin_denied")
    for path in (ROOT, WORKSPACE, JOURNAL):
        require(path.exists() and not path.is_symlink()
                and path.stat().st_uid == os.geteuid(),
                "pcp_light_original_root_workspace_or_journal_missing")
    require(ROOT.is_dir() and WORKSPACE.is_dir() and JOURNAL.is_file()
            and (ROOT.stat().st_mode & 0o077) == 0
            and (JOURNAL.stat().st_mode & 0o077) == 0,
            "pcp_light_original_journal_not_private")
    require(not EVIDENCE.exists() and not EVIDENCE.is_symlink()
            and not EVIDENCE.with_suffix(".tmp").exists(),
            "pcp_light_verification_already_claimed")
    try:
        doc = json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise Stop("pcp_light_original_journal_unreadable") from exc
    validate_journal(doc)
    require(git(WORKSPACE, "rev-parse", "--show-toplevel") == str(WORKSPACE)
            and git(WORKSPACE, "branch", "--show-current") == BRANCH
            and git(WORKSPACE, "rev-parse", "HEAD") == BASE,
            "pcp_light_original_workspace_provenance_drift")
    common = git(WORKSPACE, "rev-parse", "--git-common-dir")
    require(Path(common).resolve() == (repo / ".git").resolve(),
            "pcp_light_workspace_not_linked_to_original_pcp")
    staged = bool(git(WORKSPACE, "diff", "--cached", "--name-only"))
    deleted = bool(git(WORKSPACE, "diff", "--diff-filter=D", "--name-only", "HEAD"))
    paths = inspect_changed_paths(WORKSPACE)
    symlinks = any((WORKSPACE / name).is_symlink()
                   or not (WORKSPACE / name).is_file()
                   for name in paths)
    validate_scope(paths, staged=staged, deleted=deleted, symlinks=symlinks)
    # The issue is immutable for this job: re-verify independently before any
    # mutating test/delivery action, never trust only the local journal.
    verify_original_issue()
    return {
        "issue": ISSUE, "base_sha": BASE, "branch": BRANCH,
        "original_state": doc["state"], "original_model_calls": doc["model_calls"],
        "changed_paths": sorted(paths),
    }


def validate_python_syntax(workspace: Path) -> int:
    """Parse (NEVER import/execute) Codex-edited Python in original worktree."""
    for relative in sorted(FILES):
        p = workspace / relative
        require(p.is_file() and not p.is_symlink()
                and p.stat().st_size <= 262144,
                "pcp_light_changed_python_invalid_file")
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError, UnicodeError, ValueError) as exc:
            raise Stop("pcp_light_generated_python_syntax_invalid") from exc
    return len(FILES)


def deliver(repo: Path, expected_main: str) -> dict[str, Any]:
    snapshot = preflight(repo, expected_main)
    # Claim exactly once before any mutable operation, including test execution.
    private_write_new(EVIDENCE, {
        "state": "claimed", "issue": ISSUE, "key": KEY, "base_sha": BASE,
        "original_journal_sha256": hashlib.sha256(JOURNAL.read_bytes()).hexdigest(),
        "operator_main_sha": expected_main, "model_calls_added": 0,
        "changed_paths": snapshot["changed_paths"],
    })
    started = time.monotonic()
    checked_count = validate_python_syntax(WORKSPACE)
    evidence("source_syntax_passed", syntax_files_checked=checked_count,
             local_checks_elapsed_seconds=round(time.monotonic()-started, 1))
    # Untrusted Codex-generated tests NEVER execute on the Owner host.
    # Full pytest is mandatory on GitHub-hosted PR CI before PM acceptance.
    # Tests may themselves touch files. Re-attest before Git staging.
    changed = inspect_changed_paths(WORKSPACE)
    validate_scope(changed,
                   staged=bool(git(WORKSPACE, "diff", "--cached", "--name-only")),
                   deleted=bool(git(WORKSPACE, "diff", "--diff-filter=D",
                                    "--name-only", "HEAD")),
                   symlinks=any((WORKSPACE / x).is_symlink()
                                or not (WORKSPACE / x).is_file()
                                for x in changed))
    checked(["git", "-C", str(WORKSPACE), "diff", "--check"], timeout=25)
    checked(["git", "-C", str(WORKSPACE), "add", "--", *sorted(FILES)])
    checked(["git", "-C", str(WORKSPACE), "diff", "--cached", "--check"])
    checked(["git", "-C", str(WORKSPACE),
             "-c", "core.hooksPath=/dev/null",
             "-c", "user.name=PCP-light Operator",
             "-c", "user.email=pcp-light@localhost",
             "commit", "-m", "feat(pcp-light): focus local verification on approved tests"])
    commit_sha = git(WORKSPACE, "rev-parse", "HEAD")
    require(SHA_RE.fullmatch(commit_sha) is not None
            and git(WORKSPACE, "rev-parse", "HEAD^") == BASE
            and set(git(WORKSPACE, "diff", "--name-only", BASE, "HEAD")
                    .splitlines()) == FILES
            and git(WORKSPACE, "status", "--porcelain") == "",
            "pcp_light_candidate_commit_not_exact_seed_child")
    evidence("committed", candidate_sha=commit_sha)
    # Never replay agent; delivery stays host-only with no force push or merge.
    checked(["git", "-C", str(WORKSPACE), "push", "origin",
             "HEAD:refs/heads/" + BRANCH], timeout=140)
    evidence("pushed", candidate_sha=commit_sha)
    pr = checked([
        "gh", "pr", "create", "--repo", REPO, "--draft",
        "--base", "main", "--head", BRANCH,
        "--title", "PCP-light #725: focused local verification",
        "--body", (
            "Reuses the original PCP-light #725 one-call Codex output "
            "without another model turn. Source parent: " + BASE + ". "
            "Verified original Owner issue SHA256 " + ISSUE_SHA256 + ". "
            "Zero additional model calls. Original journal preserved. "
            "Two changed Python files syntax-checked only; no generated "
            "test code executed on Owner WSL. Full hosted pytest CI "
            "and PM exact-head review required before acceptance/merge. "
            "No auto deployment."
        ),
    ], cwd=WORKSPACE, timeout=90)
    require(PR_RE.fullmatch(pr) is not None,
            "pcp_light_draft_pr_url_not_proven")
    evidence("draft_pr_created", candidate_sha=commit_sha, pr=pr)
    return {
        "status": "PCP_LIGHT_725_DRAFT_PR_AWAITING_HOSTED_CI",
        "original_model_calls": 1,
        "additional_model_calls": 0, "candidate_sha": commit_sha,
        "pr": pr, "syntax_files_checked": checked_count,
        "local_tests_executed": 0, "hosted_full_ci": "PENDING", "original_journal_preserved": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--expected-main-sha", required=True)
    parser.add_argument("--deliver", action="store_true")
    args = parser.parse_args()
    try:
        repo = Path(args.repo_root).expanduser().resolve()
        if args.deliver:
            result = deliver(repo, args.expected_main_sha)
        else:
            result = {"status": "PCP_LIGHT_725_READ_ONLY_READY",
                      "model_calls_added": 0,
                      **preflight(repo, args.expected_main_sha)}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Stop, OSError, ValueError, FileExistsError) as exc:
        blocker = str(exc) if isinstance(exc, Stop) else "pcp_light_local_io_blocked"
        print(json.dumps({
            "status": "STOP_PCP_LIGHT_725_VERIFICATION",
            "blocker": blocker, "no_automatic_retry": True,
            "no_cleanup": True, "additional_model_calls": 0,
            "original_journal_preserved": True,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
