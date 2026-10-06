from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any


READ_ONLY_TASK_TYPES = {"analysis", "review", "explain", "research", "question", "read_only", "read-only"}
CHANGE_TASK_TYPES = {"implementation", "bugfix", "feature", "refactor", "test", "config", "documentation", "docs"}
CHANGE_VERBS = (
    "add ", "create ", "implement ", "fix ", "change ", "update ", "remove ",
    "refactor ", "write ", "modify ", "migrate ", "upgrade ", "generate ",
)


_RUNTIME_UNTRACKED_EXACT_EXCLUDES = {".ddev/config.coding-platform.yaml"}

_STRUCTURED_DEPENDENCY_MANIFESTS = {
    "package.json",
    "composer.json",
    "pyproject.toml",
    "cargo.toml",
}

_ALWAYS_MATERIAL_DEPENDENCY_MANIFESTS = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "composer.lock",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
    "go.mod",
    "go.sum",
    "cargo.lock",
    "gemfile",
    "gemfile.lock",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}


def _read_base_file(workspace: Path, base: str, path: str) -> bytes | None:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "show", f"{base}:{path}"],
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _read_working_file(workspace: Path, path: str) -> bytes | None:
    target = workspace / path
    if not target.is_file():
        return None
    return target.read_bytes()


def _package_dependency_surface(document: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
        "bundledDependencies",
        "bundleDependencies",
        "overrides",
        "resolutions",
    )
    return {key: document.get(key) for key in keys if key in document}


def _composer_dependency_surface(document: dict[str, Any]) -> dict[str, Any]:
    keys = ("require", "require-dev", "repositories")
    return {key: document.get(key) for key in keys if key in document}


def _collect_named_dependency_tables(
    value: Any,
    *,
    path: tuple[str, ...] = (),
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(value, dict):
        return out
    for key, child in value.items():
        next_path = (*path, str(key))
        normalized = str(key).lower()
        if normalized in {
            "dependencies",
            "dev-dependencies",
            "build-dependencies",
            "optional-dependencies",
        }:
            out[".".join(next_path)] = child
        if isinstance(child, dict):
            out.update(_collect_named_dependency_tables(child, path=next_path))
    return out


def _pyproject_dependency_surface(document: dict[str, Any]) -> dict[str, Any]:
    surface = _collect_named_dependency_tables(document)
    build_system = document.get("build-system")
    if isinstance(build_system, dict) and "requires" in build_system:
        surface["build-system.requires"] = build_system.get("requires")
    return surface


def _cargo_dependency_surface(document: dict[str, Any]) -> dict[str, Any]:
    return _collect_named_dependency_tables(document)


def _structured_dependency_surface(name: str, raw: bytes) -> dict[str, Any]:
    if name in {"package.json", "composer.json"}:
        document = json.loads(raw.decode("utf-8"))
    elif name in {"pyproject.toml", "cargo.toml"}:
        document = tomllib.loads(raw.decode("utf-8"))
    else:
        raise ValueError(f"Unsupported structured dependency manifest: {name}")
    if not isinstance(document, dict):
        raise ValueError(f"Dependency manifest is not an object: {name}")
    if name == "package.json":
        return _package_dependency_surface(document)
    if name == "composer.json":
        return _composer_dependency_surface(document)
    if name == "pyproject.toml":
        return _pyproject_dependency_surface(document)
    return _cargo_dependency_surface(document)


def dependency_manifest_changes(
    workspace: Path,
    base: str,
    changed_paths: list[str],
) -> list[str]:
    """Return changed paths whose dependency graph surface actually changed.

    Structured manifests are compared semantically against the exact diff base.
    Lockfiles and other dependency/runtime manifests remain fail-closed: any
    change to those paths is treated as material.
    """
    changes: list[str] = []
    for raw_path in changed_paths:
        path = str(raw_path).replace("\\", "/")
        name = Path(path).name.lower()

        if (
            name in _ALWAYS_MATERIAL_DEPENDENCY_MANIFESTS
            or (name.startswith("requirements") and name.endswith(".txt"))
            or path.lower().startswith(("helm/", "charts/", "k8s/", "kubernetes/"))
        ):
            changes.append(path.lower())
            continue

        if name not in _STRUCTURED_DEPENDENCY_MANIFESTS:
            continue

        before = _read_base_file(workspace, base, path)
        after = _read_working_file(workspace, path)
        if before is None or after is None:
            changes.append(path.lower())
            continue

        try:
            before_surface = _structured_dependency_surface(name, before)
            after_surface = _structured_dependency_surface(name, after)
        except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError, ValueError):
            changes.append(path.lower())
            continue

        if before_surface != after_surface:
            changes.append(path.lower())

    return list(dict.fromkeys(changes))


def _is_python_bytecode(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    name = parts[-1] if parts else normalized
    return "__pycache__" in parts or name.endswith((".pyc", ".pyo"))


def _is_runtime_ignored_untracked(path: str) -> bool:
    return path in _RUNTIME_UNTRACKED_EXACT_EXCLUDES or _is_python_bytecode(path)


def _tracked_in_head(workspace: Path, path: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "cat-file", "-e", f"HEAD:{path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _drop_runtime_intent_to_add(workspace: Path) -> None:
    """Remove only Runtime-owned intent-to-add placeholders that became stale.

    diff_state() uses git add -N so untracked files participate in the exact
    diff without staging their contents. A developer may later remove one of
    those files. Git then retains an index-only intent-to-add placeholder and
    renders it as a deletion from the empty blob, which cannot be applied to a
    clean clone whose source commit never contained that path.

    Remove a missing non-HEAD path only when the index carries no real staged
    diff. This preserves actual tracked deletions and staged additions. Generated
    bytecode keeps the historical exclusion behavior even while it still exists.
    No working-tree content is deleted or rewritten.
    """
    stale: list[str] = []
    for _, name in _status_entries(workspace):
        if _tracked_in_head(workspace, name):
            continue

        path = workspace / name
        if _is_python_bytecode(name):
            stale.append(name)
            continue
        if path.exists() or path.is_symlink():
            continue

        cached = subprocess.run(
            ["git", "-C", str(workspace), "diff", "--cached", "--quiet", "--", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if cached.returncode == 0:
            stale.append(name)
        elif cached.returncode != 1:
            raise RuntimeError(
                cached.stderr.strip()
                or f"git diff --cached failed while checking intent-to-add path: {name}"
            )

    if not stale:
        return
    proc = subprocess.run(
        ["git", "-C", str(workspace), "reset", "--quiet", "--", *stale],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git reset stale intent-to-add failed")

def task_requires_material_change(task: dict[str, Any]) -> bool:
    task_type = str(task.get("task_type") or "unknown").strip().lower()
    if task_type in READ_ONLY_TASK_TYPES:
        return False
    if task_type in CHANGE_TASK_TYPES:
        return True
    text = f"{task.get('title','')} {task.get('description','')}".strip().lower()
    return any(verb in text for verb in CHANGE_VERBS)


# These words describe work shape rather than repository identity. Letting them
# drive broad content searches made requests such as "add a small automated test
# for existing custom Drupal modules" look like large multi-file changes.
STOPWORDS = {
    "the", "and", "with", "from", "that", "this", "into", "when", "then", "for",
    "fix", "add", "update", "change", "create", "implement", "issue", "bug", "feature",
    "please", "should", "would", "could", "small", "minimal", "automated", "automatic",
    "test", "tests", "testing", "existing", "behavior", "behaviour", "inspect", "review",
    "code", "module", "modules", "custom", "drupal", "application", "project", "repository",
    "repo", "current", "public", "unrelated", "file", "files", "work", "working",
    "one", "single", "keep", "not", "refactor", "refactoring",
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
    return out[:12]


def _matching_paths(repo: Path, word: str) -> list[str]:
    """Return tracked files containing a fixed task term.

    Use `git grep` rather than depending on ripgrep being present. Every coding
    workspace is already a Git clone, so this keeps analysis deterministic across
    the runtime image, local development and GitHub Actions while naturally
    ignoring untracked/runtime-only files.
    """
    proc = subprocess.run(
        [
            "git", "-C", str(repo), "grep", "-l", "-i", "-F", "-e", word, "--", ".",
            ":(exclude)vendor/**", ":(exclude)node_modules/**",
        ],
        text=True,
        capture_output=True,
    )
    if proc.returncode not in (0, 1):
        return []
    return [line.strip().removeprefix("./") for line in proc.stdout.splitlines()[:200] if line.strip()]


def _relevant_files(repo: Path, words: list[str]) -> list[tuple[str, float, list[str]]]:
    """Rank files by task-token evidence rather than counting every OR match.

    A token that occurs in only a handful of files carries much more scope
    evidence than one occurring across the repository. Path matches get an
    additional bonus because named modules/classes/directories are strong task
    signals. Broad tokens can still contribute when combined with another token,
    but a single ubiquitous word cannot inflate the scope on its own.
    """
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}

    for word in words:
        paths = _matching_paths(repo, word)
        if not paths:
            continue

        count = len(paths)
        if count <= 5:
            weight = 3.0
        elif count <= 20:
            weight = 2.0
        elif count <= 60:
            weight = 1.0
        else:
            weight = 0.5

        for path in paths:
            score = weight
            if word in path.lower():
                score += 1.5
            scores[path] = scores.get(path, 0.0) + score
            evidence.setdefault(path, []).append(word)

    ranked = sorted(
        ((path, score, evidence.get(path, [])) for path, score in scores.items()),
        key=lambda row: (-row[1], row[0]),
    )
    if not ranked:
        return []

    # A score below 2 represents only weak/broad evidence. Keep at most 12
    # high-confidence files so Router scope is an estimate, not an arbitrary cap.
    return [row for row in ranked if row[1] >= 2.0][:12]


def analyze_repo(repo: Path, task: dict[str, Any], hints: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    text = f"{task.get('title','')} {task.get('description','')}".strip()
    lower = text.lower()
    words = tokenize(text)
    relevant = _relevant_files(repo, words)
    candidates = [path for path, _, _ in relevant]

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
        proc = subprocess.run(
            ["git", "-C", str(repo), "log", "--all", "--oneline", "--grep", grep, "-i", "-n", "10"],
            text=True,
            capture_output=True,
        )
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
        "estimated_files": max(1, min(12, len(candidates) or 1)),
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
        "relevance": [
            {"path": path, "score": round(score, 2), "matched_terms": terms}
            for path, score, terms in relevant[:8]
        ],
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

    # Use the final derived analysis rather than the raw keyword booleans.
    # Authoritative WorkOrder repo hints may intentionally override keywords
    # that appear only in out-of-scope/preservation text. Legacy free-text jobs
    # have no such hints, so their derived values retain the historical keyword
    # inference.
    if derived["destructive_migration"] and "destructive_migration" not in flags:
        flags.append("destructive_migration")
    if derived["production_write"] and "production_write" not in flags:
        flags.append("production_write")
    if (
        derived["authentication_change"] or derived["authorization_change"]
    ) and "security_boundary_change" not in flags:
        flags.append("security_boundary_change")
    task_enriched = dict(task)
    task_enriched["semantic"] = semantic
    task_enriched["flags"] = flags
    return derived, task_enriched


def _status_entries(workspace: Path) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain=v1", "--untracked-files=all"],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git status failed")
    entries: list[tuple[str, str]] = []
    for raw in proc.stdout.splitlines():
        if len(raw) < 4:
            continue
        entries.append((raw[:2], raw[3:]))
    return entries


def diff_state(
    workspace: Path,
    max_bytes: int,
    *,
    base_ref: str | None = None,
) -> dict[str, Any]:
    _drop_runtime_intent_to_add(workspace)

    proc = subprocess.run(
        ["git", "-C", str(workspace), "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
    )
    untracked = [p.decode("utf-8", errors="replace") for p in proc.stdout.split(b"\0") if p]
    untracked = [p for p in untracked if not _is_runtime_ignored_untracked(p)]
    if untracked:
        add = subprocess.run(
            ["git", "-C", str(workspace), "add", "-N", "--", *untracked],
            text=True,
            capture_output=True,
        )
        if add.returncode != 0:
            raise RuntimeError(add.stderr.strip() or "git add -N failed")

    # Canonical execution/review identity is the final working tree relative to
    # the persisted WorkOrder source commit. Generic callers retain HEAD-relative
    # semantics by omitting base_ref. Resolve an explicit base first so invalid
    # or option-like references fail closed instead of silently producing an
    # empty diff.
    requested_base = str(base_ref or "HEAD").strip()
    if not requested_base:
        raise RuntimeError("Diff base reference must not be blank")
    resolved = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{requested_base}^{{commit}}",
        ],
        text=True,
        capture_output=True,
    )
    if resolved.returncode != 0:
        detail = resolved.stderr.strip() or resolved.stdout.strip() or "unresolvable"
        raise RuntimeError(
            f"Invalid diff base reference {requested_base!r}: {detail}"
        )
    diff_base = resolved.stdout.strip()

    # git diff <commit> compares that committed tree with the complete working
    # tree, so already-committed WorkOrder changes, staged/unstaged edits and
    # intent-to-add paths all share one cumulative identity.
    names = [
        name
        for name in _git(workspace, "diff", diff_base, "--name-only", check=False).splitlines()
        if name
    ]
    stat = _git(workspace, "diff", diff_base, "--stat")
    diff = _git(workspace, "diff", diff_base, "--binary", check=False)
    truncated = len(diff.encode()) > max_bytes
    visible = diff.encode()[:max_bytes].decode("utf-8", errors="replace") if truncated else diff
    dependency_changes = dependency_manifest_changes(
        workspace,
        diff_base,
        names,
    )
    return {
        "changed_files": names,
        "changed_file_count": len(names),
        "dependency_manifest_changes": dependency_changes,
        "diff_stat": stat,
        "diff": visible,
        "diff_truncated": truncated,
        "diff_hash": hashlib.sha256(diff.encode()).hexdigest(),
    }


def commit_changes(workspace: Path, message: str) -> str | None:
    _drop_runtime_intent_to_add(workspace)

    actual = [
        (status, name)
        for status, name in _status_entries(workspace)
        if name not in _RUNTIME_UNTRACKED_EXACT_EXCLUDES
        and not (status == "??" and _is_python_bytecode(name))
    ]
    if not actual:
        return None

    tracked = subprocess.run(
        [
            "git", "-C", str(workspace), "add", "-u", "--", ".",
            ":(exclude).ddev/config.coding-platform.yaml",
        ],
        text=True,
        capture_output=True,
    )
    if tracked.returncode != 0:
        raise RuntimeError(tracked.stderr.strip() or "git add tracked changes failed")

    proc = subprocess.run(
        ["git", "-C", str(workspace), "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
    )
    untracked = [p.decode("utf-8", errors="replace") for p in proc.stdout.split(b"\0") if p]
    untracked = [p for p in untracked if not _is_runtime_ignored_untracked(p)]
    if untracked:
        added = subprocess.run(
            ["git", "-C", str(workspace), "add", "--", *untracked],
            text=True,
            capture_output=True,
        )
        if added.returncode != 0:
            raise RuntimeError(added.stderr.strip() or "git add untracked changes failed")

    _git(workspace, "commit", "-m", message)
    return _git(workspace, "rev-parse", "HEAD")
