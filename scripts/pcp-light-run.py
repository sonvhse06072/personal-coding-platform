#!/usr/bin/env python3
"""PCP-light v1: approved GitHub issue -> one local Codex turn -> draft PR.

No PCP Runtime/Router/Executor, Docker, DDEV, Postgres, provider secrets or
Chợ Nhạc project access. This is a NEW PCP-light task lane, never a recovery
entrypoint for the frozen G0/F2/G1 jobs. Default invocation is read-only.
The explicit --execute operation is one-use and stops without retry/cleanup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import time
from typing import Any

REPOSITORY = "sonvhse06072/personal-coding-platform"
AUTHOR = "sonvhse06072"
MARKER = "<!-- coding-platform:pcp-light:v1 -->"
ROOT = Path.home() / ".pcp-light" / "jobs"
MODEL_RE = re.compile(r"gpt-[a-z0-9][a-z0-9._-]{2,63}\Z")
KEY_RE = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_PREFIXES = ("scripts/pcp-light-", "tests/test_pcp_light_", "docs/pcp-light/")
SAFE_AGENT_ENV = frozenset({
    "HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE",
    "CODEX_HOME", "SSL_CERT_FILE", "SSL_CERT_DIR", "TMPDIR",
})


class Stop(RuntimeError):
    """Sanitized blocker: do not leak raw Github, Codex or subprocess output."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise Stop(code)


def command(argv: list[str], *, cwd: Path | None = None,
            timeout: int = 45, env: dict[str, str] | None = None,
            stdin: str | None = None) -> str:
    try:
        completed = subprocess.run(
            argv, cwd=cwd, env=env, input=stdin, capture_output=True,
            text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("command_unavailable_or_timeout_" + argv[0]) from exc
    if completed.returncode:
        raise Stop("command_failed_" + argv[0] + "_" +
                   str(completed.returncode))
    return completed.stdout.strip()


def git(path: Path, *args: str) -> str:
    return command(["git", "-C", str(path), *args], timeout=40)


def allowed_path(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 240 or "\\" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in value or path.as_posix() != value:
        return False
    if value.startswith(ALLOWED_PREFIXES[:2]) and len(path.parts) != 2:
        return False
    return (value.endswith((".py", ".md"))
            and value.startswith(ALLOWED_PREFIXES))


def parse_issue(raw: dict[str, Any], issue: int, digest: str) -> dict[str, Any]:
    """One Owner-authored issue + exact body digest; --execute is explicit."""
    require(DIGEST_RE.fullmatch(digest) is not None, "invalid_issue_body_digest")
    require(type(raw.get("number")) is int and raw["number"] == issue
            and raw.get("state") == "open"
            and "pull_request" not in raw
            and (raw.get("user") or {}).get("login") == AUTHOR,
            "github_issue_identity_denied")
    body = raw.get("body")
    require(isinstance(body, str) and len(body.encode("utf-8")) <= 16000
            and body.count(MARKER) == 1 and body.lstrip().startswith(MARKER),
            "github_issue_marker_invalid")
    require(hashlib.sha256(body.encode("utf-8")).hexdigest() == digest,
            "github_issue_body_changed")
    try:
        item = json.loads(body.strip()[len(MARKER):].strip())
    except (ValueError, TypeError) as exc:
        raise Stop("handoff_invalid_json") from exc
    require(isinstance(item, dict) and set(item) == {
        "version", "key", "base_sha", "model", "reasoning", "goal", "allowed_paths",
    }, "handoff_schema_not_exact")
    require(type(item["version"]) is int and item["version"] == 1
            and isinstance(item["key"], str)
            and KEY_RE.fullmatch(item["key"]) is not None
            and not item["key"].startswith(("g0-", "g1-", "f2-", "chonhac-"))
            and isinstance(item["base_sha"], str)
            and SHA_RE.fullmatch(item["base_sha"]) is not None
            and isinstance(item["model"], str)
            and MODEL_RE.fullmatch(item["model"]) is not None
            and isinstance(item["reasoning"], str)
            and item["reasoning"] in {"low", "medium", "high", "xhigh"}
            and isinstance(item["goal"], str)
            and 20 <= len(item["goal"]) <= 8000,
            "handoff_field_invalid")
    paths = item["allowed_paths"]
    require(isinstance(paths, list) and 1 <= len(paths) <= 4
            and len(set(map(str, paths))) == len(paths)
            and all(allowed_path(x) for x in paths)
            and any(x.startswith("tests/test_pcp_light_") for x in paths),
            "handoff_allowed_files_invalid")
    return item


def load_issue(issue: int, digest: str) -> dict[str, Any]:
    require(type(issue) is int and issue > 0, "invalid_issue_number")
    raw = command(
        ["gh", "api", "--method", "GET",
         f"repos/{REPOSITORY}/issues/{issue}"],
        timeout=30,
    )
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise Stop("github_issue_unreadable") from exc
    return parse_issue(data, issue, digest)


def verify_checkout(path: Path, base_sha: str) -> None:
    require(path.is_dir() and not path.is_symlink()
            and git(path, "rev-parse", "--show-toplevel") == str(path),
            "pcp_light_repo_root_invalid")
    require(git(path, "branch", "--show-current") == "main"
            and git(path, "rev-parse", "HEAD") == base_sha
            and not git(path, "status", "--porcelain"),
            "pcp_light_main_sha_or_dirty")
    require(git(path, "remote", "get-url", "origin") in {
        f"https://github.com/{REPOSITORY}.git",
        f"https://github.com/{REPOSITORY}",
        f"git@github.com:{REPOSITORY}.git",
        f"git@github.com:{REPOSITORY}",
    }, "pcp_light_origin_denied")


def write_once(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(value, sort_keys=True) + "\n")
    path.chmod(0o600)


def update(journal: Path, state: str, **values: Any) -> None:
    prior = json.loads(journal.read_text(encoding="utf-8"))
    new = {**prior, "state": state, **values}
    temporary = journal.with_suffix(".tmp")
    write_once(temporary, new)
    os.replace(temporary, journal)


def changed_paths(workspace: Path) -> set[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only", "HEAD"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(git(workspace, *args).splitlines())
    return paths - {""}


def summarize_codex(raw: str) -> dict[str, Any]:
    terminal = ""
    usage: dict[str, Any] = {}
    for line in raw.splitlines():
        if len(line) > 32768 or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind in {"turn.completed", "turn.failed"}:
            terminal = kind
            if kind == "turn.completed":
                usage = (event.get("usage") or {})
    normalized = {}
    for name in ("input_tokens", "cached_input_tokens", "output_tokens"):
        v = usage.get(name)
        normalized[name] = v if type(v) is int and v >= 0 else None
    return {"terminal": terminal or "UNOBSERVED", **normalized}


def codex_turn(workspace: Path, task: dict[str, Any]) -> dict[str, Any]:
    argv = [
        "codex", "exec", "--json", "--sandbox", "workspace-write",
        "--config", 'approval_policy="never"',
        "--config", "features.memories=false",
        "--config", "memories.use_memories=false",
        "--config", "memories.generate_memories=false",
        "--config", "sandbox_workspace_write.network_access=false",
        "--cd", str(workspace), "--model", task["model"],
        "--config", f'model_reasoning_effort="{task["reasoning"]}"',
    ]
    prompt = (
        f"Implement this one approved PCP-light engineering task:\n{task['goal']}\n\n"
        f"Allowed files (modify ONLY these):\n"
        + "\n".join(f"- {x}" for x in task["allowed_paths"])
        + "\nDo not edit any other file, including .git, config, "
          "G0/G1/F2 files or Chợ Nhạc. Do not commit, push, create PRs, "
          "run Docker, or access the network. Finish with concise findings."
    )
    env = {k: v for k, v in os.environ.items() if k in SAFE_AGENT_ENV}
    env["GIT_TERMINAL_PROMPT"] = "0"
    argv.append(prompt)
    raw = command(argv, cwd=workspace, env=env, timeout=1200)
    return summarize_codex(raw)


def run_task(repo: Path, issue: int, digest: str, *,
             execute: bool = False) -> dict[str, Any]:
    task = load_issue(issue, digest)
    verify_checkout(repo, task["base_sha"])
    if not execute:
        return {"status": "PCP_LIGHT_HANDOFF_VERIFIED_NO_MODEL",
                "issue": issue, "key": task["key"],
                "base_sha": task["base_sha"],
                "model": task["model"], "reasoning": task["reasoning"],
                "allowed_paths": task["allowed_paths"],
                "model_calls": 0}
    require(os.geteuid() != 0, "root_operator_denied")
    parent = ROOT.parent
    require(not parent.is_symlink() and not ROOT.is_symlink(),
            "pcp_light_root_symlink_denied")
    ROOT.mkdir(parents=True, mode=0o700, exist_ok=True)
    directory = ROOT / task["key"]
    directory.mkdir(mode=0o700, exist_ok=False)
    journal = directory / "journal.json"
    branch = "ai/pcp-light/" + task["key"]
    workspace = directory / "workspace"
    write_once(journal, {
        "issue": issue, "body_sha256": digest, "key": task["key"],
        "base_sha": task["base_sha"], "branch": branch,
        "state": "claimed", "model_calls": 0,
    })
    command(["git", "-C", str(repo), "worktree", "add", "-b",
             branch, str(workspace), task["base_sha"]], timeout=100)
    require(git(workspace, "rev-parse", "HEAD") == task["base_sha"]
            and git(workspace, "branch", "--show-current") == branch
            and not git(workspace, "status", "--porcelain"),
            "pcp_light_workspace_provenance_failed")
    update(journal, "model_reserved", model_calls=1)
    started = time.monotonic()
    result = codex_turn(workspace, task)  # Only one model turn; never retry.
    model_seconds = round(time.monotonic() - started, 1)
    update(journal, "model_finished", usage=result,
           elapsed_seconds=model_seconds)
    require(result["terminal"] == "turn.completed",
            "pcp_light_codex_not_completed")
    changed = changed_paths(workspace)
    require(not any((workspace / name).is_symlink() for name in changed),
            "pcp_light_changed_symlink_denied")
    deleted = git(workspace, "diff", "--diff-filter=D", "--name-only", "HEAD")
    require(not deleted, "pcp_light_deletion_denied")
    require(bool(changed) and changed.issubset(set(task["allowed_paths"]))
            and any(x.startswith("tests/test_pcp_light_") for x in changed),
            "pcp_light_diff_outside_scope_or_missing_tests")
    command(["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
            cwd=workspace, timeout=300)
    update(journal, "tests_passed", changed_paths=sorted(changed))
    command(["git", "-C", str(workspace), "add", "--", *sorted(changed)])
    command(["git", "-C", str(workspace), "diff", "--cached", "--check"])
    command([
        "git", "-C", str(workspace), "-c", "core.hooksPath=/dev/null",
        "commit", "-m", f"feat(pcp-light): {task['key']}",
    ], timeout=120)
    commit = git(workspace, "rev-parse", "HEAD")
    require(git(workspace, "rev-parse", "HEAD^") == task["base_sha"]
            and set(git(workspace, "diff", "--name-only",
                        task["base_sha"], "HEAD").splitlines()) == changed
            and not git(workspace, "status", "--porcelain"),
            "pcp_light_commit_provenance_invalid")
    update(journal, "committed", commit=commit)
    command(["git", "-C", str(workspace), "push", "origin",
             f"HEAD:refs/heads/{branch}"], timeout=150)
    update(journal, "pushed", commit=commit)
    pr = command([
        "gh", "pr", "create", "--repo", REPOSITORY,
        "--draft", "--base", "main", "--head", branch,
        "--title", f"PCP-light: {task['key']}",
        "--body", (
            f"PCP-light Owner-authorized issue #{issue}; "
            f"body SHA-256 {digest}; source {task['base_sha']}; "
            f"model {task['model']} / {task['reasoning']}. "
            "One model turn; scoped Python tests passed. "
            "Draft pending exact-HEAD CI and PM review. "
            "No automatic merge or deployment."
        ),
    ], cwd=workspace, timeout=90)
    require(pr.startswith(f"https://github.com/{REPOSITORY}/pull/"),
            "pcp_light_pr_url_not_verified")
    update(journal, "draft_pr_created", pr=pr)
    return {"status": "PCP_LIGHT_DRAFT_PR_PENDING_CI_PM",
            "issue": issue, "branch": branch, "commit": commit,
            "pr": pr, "model_calls": 1,
            "model_elapsed_seconds": model_seconds, **result}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--body-sha256", required=True)
    p.add_argument("--repo-root", required=True)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    try:
        result = run_task(
            Path(args.repo_root).expanduser().resolve(),
            args.issue, args.body_sha256, execute=args.execute,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Stop, OSError, ValueError, FileExistsError) as exc:
        code = str(exc) if isinstance(exc, Stop) else "local_precondition_or_io_failure"
        print(json.dumps({
            "status": "STOP_PCP_LIGHT",
            "blocker": code, "no_automatic_retry": True,
            "no_cleanup": True, "frozen_g1_f2_untouched": True,
            "chonhac_untouched": True,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
