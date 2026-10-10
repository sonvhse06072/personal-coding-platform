#!/usr/bin/env python3
"""Stage exactly one clean, private, frozen Drupal benchmark Git checkout.

Owner-approved G0 fixture preparation only. Never starts DDEV, runs Codex,
touches existing project checkouts, or changes global Git/host configuration.
The default mode inspects; --create is the one explicit local write action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

REPOSITORY = "sonvhse06072/pcp-g0-drupal-fixture"
SOURCE_BRANCH = "benchmark/pcp"
SOURCE_COMMIT = "39ef13c25b24c4a1b43a720ae53419f479996ed2"
LOCK_SHA256 = "3a3d086be59571b43f05301ab099dc4d710a2ca1da0b25af60341d527f531f2b"
FOLDER = "pcp-g0-drupal-fixture"


class StageStopped(Exception):
    """Safe bounded stop, with no hidden retries or destructive rollback."""


def call(argv: list[str], *, timeout: int = 40) -> str:
    if argv[0] not in {"gh", "git"}:
        raise StageStopped("unsupported_command")
    env = {
        **os.environ,
        "GH_PROMPT_DISABLED": "1",
        "GH_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
    }
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True,
            env=env, check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StageStopped("command_unavailable_or_timeout") from exc
    if result.returncode != 0:
        # Never expose gh/git stderr, remote URLs, tokens or private host paths.
        raise StageStopped("command_failed:" + argv[0])
    return result.stdout.strip()


def paths(home: Path) -> tuple[Path, Path]:
    """Check the destination is a new, ordinary, user-owned directory only."""
    if os.geteuid() == 0 or not home.is_dir() or home.is_symlink():
        raise StageStopped("regular_linux_user_required")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        raise StageStopped("owner_wsl_only_not_github_actions")

    parent = home / "pcp-g0-fixtures"
    target = parent / FOLDER
    if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
        raise StageStopped("fixture_parent_invalid")
    if parent.exists() and parent.stat().st_uid != os.geteuid():
        raise StageStopped("fixture_parent_not_user_owned")
    if target.exists() or target.is_symlink():
        raise StageStopped("fixture_target_already_exists_no_overwrite")
    return parent, target


def prove_remote_seed() -> None:
    """Use gh's current read access, never read or print auth material."""
    call(["gh", "auth", "status", "-h", "github.com"])
    try:
        info = json.loads(call(["gh", "api", "repos/" + REPOSITORY]))
    except json.JSONDecodeError as exc:
        raise StageStopped("remote_repository_metadata_invalid") from exc
    if info.get("full_name") != REPOSITORY or info.get("private") is not True:
        raise StageStopped("remote_repository_identity_or_privacy_mismatch")

    for branch in ("benchmark/direct", "benchmark/pcp"):
        try:
            ref = json.loads(call([
                "gh", "api", "repos/" + REPOSITORY + "/git/ref/heads/" + branch,
            ]))
        except json.JSONDecodeError as exc:
            raise StageStopped("remote_branch_metadata_invalid") from exc
        sha = (ref.get("object") or {}).get("sha")
        if sha != SOURCE_COMMIT:
            raise StageStopped("remote_" + branch.replace("/", "_") + "_seed_mismatch")


def allowed_origin(value: str) -> bool:
    if re.fullmatch(
        r"git@github\.com:" + re.escape(REPOSITORY) + r"(?:\.git)?", value,
    ):
        return True
    try:
        url = urlsplit(value)
    except ValueError:
        return False
    return (
        url.scheme == "https" and url.hostname == "github.com"
        and not url.username and not url.password and not url.query
        and not url.fragment
        and url.path.removeprefix("/") in (REPOSITORY, REPOSITORY + ".git")
    )


def verify_new_checkout(target: Path) -> dict[str, str]:
    """Read exactly the new target; never fix/mutate a wrong existing repo."""
    if target.is_symlink() or not (target / ".git").is_dir():
        raise StageStopped("new_checkout_is_not_an_independent_git_directory")
    if call(["git", "-C", str(target), "rev-parse", "HEAD"]) != SOURCE_COMMIT:
        raise StageStopped("new_checkout_head_mismatch")
    if call(["git", "-C", str(target), "branch", "--show-current"]) != SOURCE_BRANCH:
        raise StageStopped("new_checkout_branch_mismatch")
    if call(["git", "-C", str(target), "status", "--porcelain=v1"]):
        raise StageStopped("new_checkout_not_clean")
    if not allowed_origin(call(["git", "-C", str(target), "remote", "get-url", "origin"])):
        raise StageStopped("new_checkout_origin_mismatch")

    lock = target / "composer.lock"
    if lock.is_symlink() or not lock.is_file():
        raise StageStopped("fixture_composer_lock_missing_or_symlink")
    if hashlib.sha256(lock.read_bytes()).hexdigest() != LOCK_SHA256:
        raise StageStopped("fixture_composer_lock_digest_mismatch")
    if not (target / "PROJECT-BASELINE.md").is_file():
        raise StageStopped("fixture_baseline_document_missing")
    return {"head_sha": SOURCE_COMMIT, "branch": SOURCE_BRANCH,
            "composer_lock_sha256": LOCK_SHA256}


def stage(home: Path, *, create: bool) -> dict:
    parent, target = paths(home)
    prove_remote_seed()
    report: dict = {
        "mode": "create_new_source_only" if create else "inspect_only",
        "repository_private": True,
        "frozen_seed": SOURCE_COMMIT,
        "source_branch": SOURCE_BRANCH,
        "target_available_before_action": True,
        "local_ddev_started": False,
        "codex_changed_or_invoked": False,
        "pcp_source_or_runtime_modified": False,
        "other_project_source_modified": False,
        "ready_to_dispatch_g0d_t01": False,
    }
    if not create:
        report["stage_status"] = "eligible_for_new_checkout"
        return report

    # The only permitted filesystem writes are the new parent (if absent)
    # and the new checkout created by gh. No deleting/resetting on failure.
    if not parent.exists():
        parent.mkdir(mode=0o700)
    if target.exists() or target.is_symlink():
        raise StageStopped("fixture_target_occupied_at_create")
    call([
        "gh", "repo", "clone", REPOSITORY, str(target), "--",
        "--branch", SOURCE_BRANCH, "--single-branch", "--no-tags",
    ], timeout=180)
    report.update(verify_new_checkout(target))
    report["stage_status"] = "clean_new_source_checkout_verified"
    report["target"] = str(target)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--inspect", action="store_true",
                       help="preflight with no filesystem writes (default)")
    modes.add_argument("--create", action="store_true",
                       help="clone only the missing approved benchmark fixture")
    args = parser.parse_args()
    try:
        result = stage(Path.home(), create=args.create)
    except StageStopped as exc:
        print(json.dumps({
            "status": "STOPPED",
            "reason": str(exc),
            "workspace_or_ddev_modified_after_failure": "not_guaranteed_if_clone_began",
            "ready_to_dispatch_g0d_t01": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
