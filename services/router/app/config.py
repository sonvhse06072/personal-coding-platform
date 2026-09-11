from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


SERVICE_DIR = Path(__file__).resolve().parent.parent
def _default_config_file(name: str) -> str:
    candidates: list[Path] = []
    if SERVICE_DIR.parent.name == "services":
        candidates.append(SERVICE_DIR.parent.parent / "config" / name)
    candidates.append(Path("/config") / name)
    candidates.append(SERVICE_DIR / "config" / name)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(Path("/config") / name)


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    models_file = os.getenv("ROUTER_MODELS_FILE", _default_config_file("models.yml"))
    policy_file = os.getenv("ROUTER_POLICY_FILE", _default_config_file("routing-policy.yml"))
    projects_file = os.getenv("ROUTER_PROJECTS_FILE", _default_config_file("projects.yml"))
    return {
        "models": _load_yaml(models_file),
        "policy": _load_yaml(policy_file),
        "projects": _load_yaml(projects_file),
    }


def clear_config_cache() -> None:
    get_config.cache_clear()
