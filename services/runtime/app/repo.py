from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any




READ_ONLY_TASK_TYPES = {"analysis", "review", "explain", "research", "question", "read_only", "read-only"}
CHANGE_TASK_TYPES = {"implementation", "bugfix", "feature", "refactor", "test", "config", "documentation", "docs"}
CHANGE_VERBS = (
    "add ", "create ", "implement ", "fix ", "change ", "update ", "remove ",
    "refactor ", "write ", "modify ", "migrate ", "upgrade ", "generate ",
)


def task_requires_material_change(task: dict[str, Any]) -> bool:
    task_type = str(task.get("task_type") or "unknown").strip().lower()
    if task_type in READ_ONLY_TASK_TYPES:
        return False
    if task_type in CHANGE_TASK_TYPES:
        return True
    text = f"{task.get('title','')} {task.get('description','')}".strip().lower()
    return any(verb in text for verb in CHANGE_VERBS)

STOPWORDS = {
    "the", "and", "with", "from", "that", "this", "into", "when", "then", "for", "fix", "add", "update",
    "change", "create", "implement", "issue", "bug", "feature", "please", "should", "would", "could",
}


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def tokenize(text: str) -> list[str]:
    items = re.findall(r"[A-Za-z0-9_\-]{3,}", text.lower())
    out: list[str] = []
    for item in items:
        if item in STOPWORDS or item.isdigit() or item in out:
            continue
        out.append(item)
    return out[:8]


def analyze_repo(repo: Path, task: dict[str, Any], hints: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    text = f"{task.get('title','')} {task.get('description','')}".strip()
    lower = text.lower()
    words = tokenize(text)
    candidates: list[str] = []
    if words:
        pattern = "|".join(re.escape(w) for w in words)
        proc = subprocess.run(
            ["rg", "-l", "-i", "--glob", "!vendor/**", "--glob", "!node_modules/**", pattern, str(repo)],
            text=True, capture_output=True,
        )
        if proc.returncode in (0, 1):
            candidates = [str(Path(line).relative_to(repo)) for line in proc.stdout.splitlines()[:30] if line.strip()]

    candidate_modules: list[str] = []
    for path in candidates:
        parts = Path(path).parts
        if "custom" in parts:
            idx = parts.index("custom")
            if idx + 1 < len(parts):
                candidate_modules.append(parts[idx + 1])
        elif parts:
            candidate_modules.append(parts[0])
    candidate_modules = list(dict.fromkeys(candidate_modules))[:12]

    related = 0
    if words:
        grep = words[0]
        proc = subprocess.run(["git", "-C", str(repo), "log", "--all", "--oneline", "--grep", grep, "-i", "-n", "10"], text=True, capture_output=True)
        if proc.returncode == 0:
            related = len([line for line in proc.stdout.splitlines() if line.strip()])

    tracked = _git(repo, "ls-files").splitlines()
    tests_available = any(re.search(r"(^|/)(tests?|spec)(/|$)|Test\.(php|py|js|ts)$", p, re.I) for p in tracked)
    existing_pattern = related > 0 or len(candidates) >= 2

    schema_change = any(k in lower for k in ["schema", "database migration", "db migration", "entity schema"])
    destructive = any(k in lower for k in ["drop table", "drop column", "destructive migration", "delete existing data"])
    authn = any(k in lower for k in ["authentication", "login", "oauth", "sso", "password"])
    authz = any(k in lower for k in ["authorization", "permission", "access control", "role access"])
    security = authn or authz or any(k in lower for k in ["security", "secret", "csrf", "xss", "sql injection"])
    external_api = any(k in lower for k in [" api", "api ", "webhook", "integration", "salesforce", "stripe"])
    production_write = any(k in lower for k in ["production database", "production write", "deploy production"])

    derived = {
        "estimated_files": max(1, min(30, len(candidates) or 1)),
        "affected_components": max(1, min(12, len(candidate_modules) or 1)),
        "dependency_depth": 2 if external_api else 1,
        "tests_available": tests_available,
        "existing_pattern": existing_pattern,
        "historical_churn": 20,
        "schema_change": schema_change,
        "security_sensitive": security,
        "authentication_change": authn,
        "authorization_change": authz,
        "external_api": external_api,
        "production_write": production_write,
        "destructive_migration": destructive,
        "likely_change_types": [],
        "candidate_modules": candidate_modules,
        "related_commits_found": related,
    }
    for key, value in hints.items():
        if value is not None:
            derived[key] = value

    semantic = task.get("semantic") or {}
    if not semantic:
        semantic = {
            "ambiguity": 45 if any(k in lower for k in ["investigate", "unknown", "occasionally", "intermittent"]) else 20,
            "architecture_impact": 75 if any(k in lower for k in ["architecture", "redesign", "new subsystem"]) else 15,
            "verification_difficulty": 65 if any(k in lower for k in ["race condition", "intermittent", "concurrency"]) else 30,
            "risk": 70 if security else (55 if schema_change else 20),
            "context_requirement": min(90, 25 + derived["affected_components"] * 8),
            "novelty": 20 if existing_pattern else 45,
            "reasoning_requirement": 80 if any(k in lower for k in ["race condition", "intermittent", "architecture", "root cause"]) else 45,
        }
    flags = list(task.get("flags") or [])
    if task_requires_material_change(task) and "material_change_required" not in flags:
        flags.append("material_change_required")
    if destructive and "destructive_migration" not in flags:
        flags.append("destructive_migration")
    if production_write and "production_write" not in flags:
        flags.append("production_write")
    if (authn or authz) and "security_boundary_change" not in flags:
        flags.append("security_boundary_change")
    task_enriched = dict(task)
    task_enriched["semantic"] = semantic
    task_enriched["flags"] = flags
    return derived, task_enriched


def _status_entries(workspace: Path) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain=v1", "--untracked-files=all"],
        text=True, capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git status failed")
    entries: list[tuple[str, str]] = []
    for raw in proc.stdout.splitlines():
        if len(raw) < 4:
            continue
        entries.append((raw[:2], raw[3:]))
    return entries


def diff_state(workspace: Path, max_bytes: int) -> dict[str, Any]:
    # Intent-to-add makes untracked agent-created files visible to `git diff`
    # without staging their contents for commit.
    proc = subprocess.run(
        ["git", "-C", str(workspace), "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
    )
    untracked = [p.decode("utf-8", errors="replace") for p in proc.stdout.split(b"\0") if p]
    untracked = [p for p in untracked if p != ".ddev/config.coding-platform.yaml"]
    if untracked:
        add = subprocess.run(["git", "-C", str(workspace), "add", "-N", "--", *untracked], text=True, capture_output=True)
        if add.returncode != 0:
            raise RuntimeError(add.stderr.strip() or "git add -N failed")

    entries = _status_entries(workspace)
    names = [name for _, name in entries if name != ".ddev/config.coding-platform.yaml"]
    stat = _git(workspace, "diff", "--stat")
    diff = _git(workspace, "diff", "--binary", check=False)
    truncated = len(diff.encode()) > max_bytes
    visible = diff.encode()[:max_bytes].decode("utf-8", errors="replace") if truncated else diff
    return {
        "changed_files": names,
        "changed_file_count": len(names),
        "diff_stat": stat,
        "diff": visible,
        "diff_truncated": truncated,
        "diff_hash": hashlib.sha256(diff.encode()).hexdigest(),
    }


def commit_changes(workspace: Path, message: str) -> str | None:
    actual = [(status, name) for status, name in _status_entries(workspace) if name != ".ddev/config.coding-platform.yaml"]
    if not actual:
        return None
    # Keep runtime-only DDEV override untracked so cleanup can still address the
    # job-specific DDEV project without polluting the user's commit.
    proc = subprocess.run(
        ["git", "-C", str(workspace), "add", "-A", "--", ".", ":(exclude).ddev/config.coding-platform.yaml"],
        text=True, capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git add failed")
    _git(workspace, "commit", "-m", message)
    return _git(workspace, "rev-parse", "HEAD")
