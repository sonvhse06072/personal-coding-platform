from pathlib import Path

import pytest

from app import config


def _write_projects(path: Path, projects: dict[str, str]) -> None:
    if not projects:
        path.write_text("version: 1\nprojects: {}\n", encoding="utf-8")
        return

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


def test_project_config_defaults_to_isolated_clone(tmp_path, monkeypatch):
    registry = tmp_path / "projects.yml"
    project_path = tmp_path / "demo"
    project_path.mkdir()
    _write_projects(registry, {"demo": str(project_path)})
    monkeypatch.setenv("PROJECTS_FILE", str(registry))

    runtime = config.project_config("demo")["runtime"]

    assert runtime["workspace_mode"] == "isolated_clone"
    assert runtime["exclusive_project_lease"] is False
    assert runtime["developer_permission_mode"] == "bounded"


def test_project_config_accepts_direct_only_with_exclusive_lease(tmp_path, monkeypatch):
    registry = tmp_path / "projects.yml"
    project_path = tmp_path / "demo"
    project_path.mkdir()
    registry.write_text(
        "version: 1\n"
        "projects:\n"
        "  demo:\n"
        f"    path: {project_path}\n"
        "    base_branch: main\n"
        "    runtime:\n"
        "      workspace_mode: direct\n"
        "      exclusive_project_lease: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECTS_FILE", str(registry))

    runtime = config.project_config("demo")["runtime"]

    assert runtime["workspace_mode"] == "direct"
    assert runtime["exclusive_project_lease"] is True


@pytest.mark.parametrize(
    "runtime_yaml, expected",
    [
        ("      workspace_mode: direct\n", "requires exclusive_project_lease=true"),
        ("      workspace_mode: magic\n", "unsupported runtime.workspace_mode"),
    ],
)
def test_project_config_rejects_unsafe_workspace_modes(
    tmp_path, monkeypatch, runtime_yaml, expected
):
    registry = tmp_path / "projects.yml"
    project_path = tmp_path / "demo"
    project_path.mkdir()
    registry.write_text(
        "version: 1\n"
        "projects:\n"
        "  demo:\n"
        f"    path: {project_path}\n"
        "    runtime:\n"
        + runtime_yaml,
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECTS_FILE", str(registry))

    with pytest.raises(ValueError, match=expected):
        config.project_config("demo")


def test_project_config_accepts_trusted_local_permission_mode(tmp_path, monkeypatch):
    registry = tmp_path / "projects.yml"
    project_path = tmp_path / "demo"
    project_path.mkdir()
    registry.write_text(
        "version: 1\n"
        "projects:\n"
        "  demo:\n"
        f"    path: {project_path}\n"
        "    runtime:\n"
        "      workspace_mode: direct\n"
        "      exclusive_project_lease: true\n"
        "      developer_permission_mode: trusted_local\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECTS_FILE", str(registry))

    runtime = config.project_config("demo")["runtime"]

    assert runtime["developer_permission_mode"] == "trusted_local"


def test_project_config_rejects_unknown_developer_permission_mode(tmp_path, monkeypatch):
    registry = tmp_path / "projects.yml"
    project_path = tmp_path / "demo"
    project_path.mkdir()
    registry.write_text(
        "version: 1\n"
        "projects:\n"
        "  demo:\n"
        f"    path: {project_path}\n"
        "    runtime:\n"
        "      developer_permission_mode: root_everything\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECTS_FILE", str(registry))

    with pytest.raises(ValueError, match="unsupported runtime.developer_permission_mode"):
        config.project_config("demo")
