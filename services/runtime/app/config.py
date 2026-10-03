from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


SERVICE_DIR = Path(__file__).resolve().parent.parent


def _default_config_file(name: str, container_default: str) -> str:
    candidates: list[Path] = []
    if SERVICE_DIR.parent.name == "services":
        candidates.append(SERVICE_DIR.parent.parent / "config" / name)
    candidates.append(Path(container_default))
    candidates.append(SERVICE_DIR / "config" / name)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return container_default


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML object in {path}")
    return value


def expand_env(value: str) -> str:
    # os.path.expandvars leaves unknown variables unchanged, which is useful for
    # producing a clear config error instead of silently changing the path.
    return os.path.expanduser(os.path.expandvars(value))


@lru_cache(maxsize=1)
def models_doc() -> dict[str, Any]:
    from .model_capabilities import validate_model_registry

    document = _load_yaml(
        os.getenv("MODELS_FILE", _default_config_file("models.yml", "/config/models.yml"))
    )
    validate_model_registry(document)
    return document


def model_config(model_id: str) -> dict[str, Any]:
    models = models_doc().get("models", {})
    return dict(models.get(model_id, {}))


def projects_doc() -> dict[str, Any]:
    """Read the bind-mounted project registry on every access.

    Project registrations are operational configuration shared with the
    ddev-executor. Keeping an in-process snapshot here lets Runtime and the
    executor disagree after a reviewed config-only update until Runtime is
    restarted. The registry is small, so correctness is preferable to caching.
    """
    return _load_yaml(os.getenv("PROJECTS_FILE", _default_config_file("projects.yml", "/config/projects.yml")))


@lru_cache(maxsize=1)
def project_baselines_doc() -> dict[str, Any]:
    return _load_yaml(
        os.getenv(
            "PROJECT_BASELINES_FILE",
            _default_config_file("project-baselines.yml", "/config/project-baselines.yml"),
        )
    )


@lru_cache(maxsize=1)
def routing_policy_doc() -> dict[str, Any]:
    return _load_yaml(
        os.getenv(
            "ROUTING_POLICY_FILE",
            _default_config_file("routing-policy.yml", "/config/routing-policy.yml"),
        )
    )


def project_config(project_id: str) -> dict[str, Any]:
    projects = projects_doc().get("projects", {})
    if project_id not in projects:
        raise KeyError(f"Unknown project_id: {project_id}")
    cfg = dict(projects[project_id])
    raw_path = str(cfg.get("path", ""))
    path = expand_env(raw_path)
    if not path or re.search(r"\$\{[^}]+\}", path):
        raise ValueError(f"Project {project_id} has unresolved path: {raw_path}")
    cfg["path"] = path

    runtime = dict(cfg.get("runtime") or {})
    workspace_mode = str(runtime.get("workspace_mode") or "isolated_clone").strip()
    if workspace_mode not in {"isolated_clone", "direct"}:
        raise ValueError(
            f"Project {project_id} has unsupported runtime.workspace_mode: {workspace_mode!r}"
        )
    exclusive_project_lease = bool(runtime.get("exclusive_project_lease", False))
    developer_permission_mode = str(
        runtime.get("developer_permission_mode") or "bounded"
    ).strip()
    if developer_permission_mode not in {"bounded", "trusted_local"}:
        raise ValueError(
            f"Project {project_id} has unsupported runtime.developer_permission_mode: "
            f"{developer_permission_mode!r}"
        )
    if workspace_mode == "direct" and not exclusive_project_lease:
        raise ValueError(
            f"Project {project_id} direct workspace mode requires exclusive_project_lease=true"
        )
    if developer_permission_mode == "trusted_local" and workspace_mode != "direct":
        raise ValueError(
            f"Project {project_id} trusted_local developer permission requires workspace_mode=direct"
        )
    runtime["workspace_mode"] = workspace_mode
    runtime["exclusive_project_lease"] = exclusive_project_lease
    runtime["developer_permission_mode"] = developer_permission_mode
    cfg["runtime"] = runtime
    return cfg


def clear_config_cache() -> None:
    project_baselines_doc.cache_clear()
    models_doc.cache_clear()
    routing_policy_doc.cache_clear()
