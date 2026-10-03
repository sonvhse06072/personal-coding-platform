from __future__ import annotations

from pathlib import Path

from .config import expand_env, projects_doc


TRUSTED_LOCAL_MODE = "trusted_local"


def trusted_local_developer_enabled(workspace: Path, mode: str) -> bool:
    """Return whether one exact direct project authorizes trusted local execution.

    This is intentionally project-scoped and execute/repair-only. Planning and
    evaluation remain bounded/read-only. Isolated clones do not inherit the
    trusted-local grant merely because they belong to the same project.
    """

    if mode not in {"execute", "repair"}:
        return False

    try:
        resolved = workspace.resolve()
    except OSError:
        return False

    projects = projects_doc().get("projects", {})
    if not isinstance(projects, dict):
        return False

    for raw in projects.values():
        if not isinstance(raw, dict):
            continue
        runtime = raw.get("runtime") or {}
        if not isinstance(runtime, dict):
            continue
        if str(runtime.get("developer_permission_mode") or "").strip() != TRUSTED_LOCAL_MODE:
            continue
        if str(runtime.get("workspace_mode") or "isolated_clone").strip() != "direct":
            continue

        raw_path = str(raw.get("path") or "").strip()
        if not raw_path:
            continue
        expanded = expand_env(raw_path)
        if "$" in expanded:
            continue
        try:
            project_path = Path(expanded).expanduser().resolve()
        except OSError:
            continue
        if resolved == project_path:
            return True

    return False
