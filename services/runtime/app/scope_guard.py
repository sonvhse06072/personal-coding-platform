from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable


_HIGH_AUTHORITY_PATHS = {
    "agents.md",
    "docs/project/constitution.md",
    "docs/project/architecture.md",
    "docs/project/operating-model.md",
    "docs/project/efficiency-model.md",
    "config/projects.yml",
    "config/routing-policy.yml",
    "config/models.yml",
}
_SCOPE_PATHS = {
    "docs/project/roadmap.md",
    "docs/project/requirements.md",
    "docs/project/project-plan.md",
}
_DEPENDENCY_MANIFESTS = {
    "composer.json",
    "composer.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
    "gemfile",
    "gemfile.lock",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}
_SECURITY_PATH_TERMS = {
    "auth",
    "authentication",
    "authorization",
    "permission",
    "permissions",
    "security",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "access_control",
}
_PRODUCTION_PATH_TERMS = {
    "deploy",
    "deployment",
    "production",
    "prod",
    "terraform",
    "ansible",
    "helm",
    "kubernetes",
    "k8s",
}


def _is_drupal_config_schema_metadata(path: str, name: str) -> bool:
    """Return True for Drupal config-schema metadata, not DB/data migrations."""
    return "/config/schema/" in f"/{path}" and name.endswith(".schema.yml")


def normalize_changed_paths(raw_paths: Iterable[Any]) -> list[str]:
    paths: list[str] = []
    for raw in raw_paths:
        value = str(raw).strip().replace("\\", "/")
        if not value:
            continue
        candidates = value.split(" -> ") if " -> " in value else [value]
        for candidate in candidates:
            normalized = candidate.strip()
            while normalized.startswith("./"):
                normalized = normalized[2:]
            normalized = normalized.lower()
            if normalized and normalized not in paths:
                paths.append(normalized)
    return paths


def baseline_authority_changes(
    paths: Iterable[str],
    checkpoint: dict[str, Any] | None,
) -> dict[str, str]:
    checkpoint = dict(checkpoint or {})
    baseline = dict(checkpoint.get("project_baseline") or {})
    authority_by_path: dict[str, str] = {}
    for raw in baseline.get("authority") or []:
        rule = dict(raw) if isinstance(raw, dict) else {}
        path = str(rule.get("path") or "").strip().replace("\\", "/").lower()
        authority = str(rule.get("authority") or "").strip()
        if path and authority:
            authority_by_path[path] = authority

    changed: dict[str, str] = {}
    for path in normalize_changed_paths(paths):
        authority = authority_by_path.get(path)
        if authority:
            changed[path] = authority
    return changed


def changed_path_protected_signals(
    paths: Iterable[str],
    checkpoint: dict[str, Any] | None = None,
) -> set[str]:
    """Classify actual changed paths into protected decision signals.

    This is shared by Runtime execution reassessment and the PM merge gate so a
    sensitive path cannot be treated as routine merely because the raw file
    count is within the WorkOrder's expected work shape.
    """

    normalized_paths = normalize_changed_paths(paths)
    signals: set[str] = set()
    authority = baseline_authority_changes(normalized_paths, checkpoint)
    if "human_owner_protected" in set(authority.values()):
        signals.add("project_baseline_authority_change")

    for path in normalized_paths:
        pure = PurePosixPath(path)
        name = pure.name.lower()
        parts = {part.lower() for part in pure.parts}
        stem_parts = set(name.replace("-", "_").replace(".", "_").split("_"))

        if path in _HIGH_AUTHORITY_PATHS or path.startswith(".github/workflows/"):
            signals.add("high_authority_governance")
        if path in _SCOPE_PATHS:
            signals.add("scope_change")

        if (
            name in _DEPENDENCY_MANIFESTS
            or (name.startswith("requirements") and name.endswith(".txt"))
            or path.startswith(("helm/", "charts/", "k8s/", "kubernetes/"))
        ):
            signals.add("major_dependency_addition")

        if _SECURITY_PATH_TERMS & (parts | stem_parts):
            signals.add("security_boundary_change")

        schema_filename_signal = (
            "schema" in stem_parts
            and not _is_drupal_config_schema_metadata(path, name)
        )
        if "migration" in parts or "migrations" in parts or schema_filename_signal:
            signals.add("destructive_migration")

        if _PRODUCTION_PATH_TERMS & (parts | stem_parts):
            signals.add("production_write")

    return signals
