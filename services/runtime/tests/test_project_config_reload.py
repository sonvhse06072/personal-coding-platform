from pathlib import Path

import pytest

from app import config


def _write_projects(path: Path, projects: dict[str, str]) -> None:
    lines = ["version: 1", "projects:"]
    for project_id, project_path in projects.items():
        lines.extend(
            [
                f"  {project_id}:",
                f"    path: {project_path}",
                "    base_branch: main",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_project_config_observes_registry_updates_without_restart(tmp_path, monkeypatch):
    registry = tmp_path / "projects.yml"
    first_path = tmp_path / "first"
    second_path = tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()

    _write_projects(registry, {"first": str(first_path)})
    monkeypatch.setenv("PROJECTS_FILE", str(registry))

    assert config.project_config("first")["path"] == str(first_path)

    _write_projects(
        registry,
        {
            "first": str(first_path),
            "second": str(second_path),
        },
    )

    # No clear_config_cache() and no process restart: bind-mounted operational
    # project config must stay consistent with ddev-executor's live reads.
    assert config.project_config("second")["path"] == str(second_path)


def test_project_config_still_fails_closed_for_unknown_project(tmp_path, monkeypatch):
    registry = tmp_path / "projects.yml"
    _write_projects(registry, {})
    monkeypatch.setenv("PROJECTS_FILE", str(registry))

    with pytest.raises(KeyError, match="Unknown project_id: missing"):
        config.project_config("missing")
