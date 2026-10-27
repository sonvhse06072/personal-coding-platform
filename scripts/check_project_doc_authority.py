#!/usr/bin/env python3
"""Read-only, deterministic guard for direct GitHub PM documentation PR writes.

GitHub's owner-linked PR-body fields are *declared audit evidence*, not proof
of independent Human Owner action. Protected approvals must still be confirmed
by the PM against the actual owner request before merge.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

PROTECTED_PATHS = frozenset({
    "AGENTS.md",
    ".github/workflows/tests.yml",
    ".github/workflows/guardian-static.yml",
    ".github/workflows/pcp-guardian.yml",
    ".github/workflows/pcp-local-inspect-image.yml",
    "scripts/check_project_doc_authority.py",
    "scripts/pcp-local-trusted-bootstrap.sh",
    "services/runtime/app/pcp_local_trusted_readers.py",
    "scripts/pcp-local-gate-a-inspect.sh",
    "scripts/pcp-shared-docker-ownership-check.sh",
    "scripts/pcp-local-image-provenance-plan.py",
    "scripts/pcp-local-oci-evidence-plan.py",
    "profiles/pcp-local/ddev-install-plan.example.yml",
    "scripts/pcp-local-ddev-install-plan.py",
    "docs/pcp-portable/h1c-ddev-install-plan.md",
    "profiles/pcp-local/oci-evidence-plan.example.yml",
    "docs/pcp-portable/h1b3-oci-evidence-plan.md",
    "profiles/pcp-local/image-provenance.example.yml",
    "profiles/pcp-local/runtime/Dockerfile.inspect",
    "profiles/pcp-local/runtime/Dockerfile.inspect.dockerignore",
    "profiles/pcp-local/runtime/requirements-inspect.lock",
    "profiles/pcp-local/.ddev/config.yaml",
    "profiles/pcp-local/.ddev/docker-compose.platform.yaml",
    "config/project-baselines.yml",
    "config/project-baselines.pcp-local.yml",
    "config/projects.yml",
    "config/projects.pcp-local.yml",
    "services/runtime/app/main.py",
    "services/runtime/app/pcp_local_worker_loop.py",
    "services/runtime/app/engine.py",
    "services/runtime/app/engine_core.py",
    "services/runtime/app/engine_delivery.py",
    "services/runtime/app/storage.py",
    "config/pm-bridge.yml",
    "config/routing-policy.yml",
    "config/models.yml",
    "docs/project/README.md",
    "docs/project/constitution.md",
    "docs/project/architecture.md",
    "docs/project/business-strategy.md",
    "docs/project/operating-model.md",
    "docs/project/efficiency-model.md",
    "docs/project/provider-policy.md",
    "docs/project/provider-quota-telemetry.md",
    "docs/project/context-memory-architecture.md",
    "docs/project/service-secret-upgrades.md",
    "docs/project/telegram-terminal-operations.md",
    "docs/project/roadmap.md",
})

MUTABLE_PATHS = frozenset({
    "README.md",
    "docs/project/current-state.md",
})
EVIDENCE_PREFIXES = (
    "docs/project/history/",
    "docs/project/pilot-successor-",
)
ISSUE_RE = re.compile(
    r"(?m)^Owner-Approval-Issue:\s*(https://github\.com/sonvhse06072/"
    r"personal-coding-platform/issues/\d+)\s*$"
)
PATHS_RE = re.compile(r"(?m)^Approved-Protected-Paths:\s*(.+)$")
SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def classify_path(path: str) -> str:
    if path in PROTECTED_PATHS:
        return "protected"
    if path in MUTABLE_PATHS:
        return "mutable"
    if path.startswith(EVIDENCE_PREFIXES) and path.endswith(".md"):
        return "evidence"
    if path.startswith("docs/project/") and path.endswith(".md"):
        return "unclassified"
    return "other"


def require_approval_scope(changed_protected: set[str], pr_body: str) -> str | None:
    if not changed_protected:
        return None
    evidence = ISSUE_RE.search(pr_body)
    if evidence is None:
        raise ValueError(
            "Protected changes require Owner-Approval-Issue: "
            "https://github.com/sonvhse06072/personal-coding-platform/issues/N"
        )
    match = PATHS_RE.search(pr_body)
    if match is None:
        raise ValueError("Protected changes require Approved-Protected-Paths: ...")
    approved = set(re.findall(r"`([^`]+)`", match.group(1)))
    missing = sorted(changed_protected - approved)
    if missing:
        raise ValueError(
            "Protected path(s) absent from declared Owner approval scope: "
            + ", ".join(missing)
        )
    return evidence.group(1)


def require_existing_baseline_revisions_immutable(
    before: dict[str, Any], after: dict[str, Any]
) -> None:
    """Approved revision objects, including source SHA and authority, are immutable."""
    old_projects = dict(before.get("projects") or {})
    new_projects = dict(after.get("projects") or {})
    for project_id, old_project in old_projects.items():
        old_revisions = dict((old_project or {}).get("revisions") or {})
        new_revisions = dict((new_projects.get(project_id) or {}).get("revisions") or {})
        for revision, definition in old_revisions.items():
            if (definition or {}).get("status") not in {"approved", "superseded"}:
                continue
            if new_revisions.get(revision) != definition:
                raise ValueError(
                    f"Approved ProjectBaseline {project_id}/{revision} changed in place; "
                    "create an approved successor revision instead"
                )


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError(
            "Git evidence unavailable: " + " ".join(args[:2]) + ": "
            + (result.stderr or result.stdout).strip()[:300]
        )
    return result.stdout


def changed_paths(repo: Path, base: str, head: str) -> set[str]:
    paths: set[str] = set()
    diff = git(repo, "diff", "--name-status", "-M", "--diff-filter=ACMRD", base, head)
    for line in diff.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            raise ValueError("Malformed Git changed-path evidence")
        for path in fields[1:]:
            if not path or path.startswith("/") or ".." in Path(path).parts:
                raise ValueError("Unsafe changed Git path")
            paths.add(path)
    return paths


def check(repo: Path, base: str, head: str, pr_body: str) -> dict[str, Any]:
    if not SHA_RE.fullmatch(base) or not SHA_RE.fullmatch(head):
        raise ValueError("Base/head must be exact Git SHA")
    merge_base = git(repo, "merge-base", base, head).strip()
    if not SHA_RE.fullmatch(merge_base):
        raise ValueError("Unable to derive exact PR merge-base")

    changed = changed_paths(repo, merge_base, head)
    all_paths = git(repo, "ls-tree", "-r", "--name-only", head, "--", "docs/project")
    missing_classification = [
        path for path in all_paths.splitlines()
        if classify_path(path) == "unclassified"
    ]
    if missing_classification:
        raise ValueError(
            "New/unclassified project document(s) need a reviewed authority rule: "
            + ", ".join(sorted(missing_classification))
        )
    changed_unclassified = sorted(p for p in changed if classify_path(p) == "unclassified")
    if changed_unclassified:
        raise ValueError("Changed document is unclassified: " + ", ".join(changed_unclassified))

    for config_path in ("config/project-baselines.yml", "config/project-baselines.pcp-local.yml"):
        if config_path in changed:
            old = yaml.safe_load(git(repo, "show", f"{merge_base}:{config_path}")) or {}
            new = yaml.safe_load(git(repo, "show", f"{head}:{config_path}")) or {}
            if not isinstance(old, dict) or not isinstance(new, dict):
                raise ValueError("ProjectBaseline registry YAML must be an object")
            require_existing_baseline_revisions_immutable(old, new)

    protected = {path for path in changed if classify_path(path) == "protected"}
    declared_owner_ref = require_approval_scope(protected, pr_body)
    return {
        "merge_base": merge_base,
        "head": head,
        "changed_file_count": len(changed),
        "protected_files": sorted(protected),
        "declared_owner_approval": declared_owner_ref,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    try:
        result = check(repo, args.base.lower(), args.head.lower(), __import__("os").environ.get("DOC_PR_BODY", ""))
    except (ValueError, yaml.YAMLError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print("PCP documentation authority check passed:", result)
    if result["protected_files"]:
        print("WARNING: PR declaration is not independent Human Owner proof; PM must verify approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
