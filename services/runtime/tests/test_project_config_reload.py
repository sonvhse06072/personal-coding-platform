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


def test_project_config_rejects_trusted_local_on_isolated_workspace(tmp_path, monkeypatch):
    registry = tmp_path / "projects.yml"
    project_path = tmp_path / "demo"
    project_path.mkdir()
    registry.write_text(
        "version: 1\n"
        "projects:\n"
        "  demo:\n"
        f"    path: {project_path}\n"
        "    runtime:\n"
        "      workspace_mode: isolated_clone\n"
        "      developer_permission_mode: trusted_local\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECTS_FILE", str(registry))

    with pytest.raises(ValueError, match="trusted_local developer permission requires workspace_mode=direct"):
        config.project_config("demo")


def test_trusted_project_contract_only_accepts_exact_disposable_g1(
    tmp_path, monkeypatch,
):
    import yaml

    config_file = tmp_path / "projects.yml"
    project_path = tmp_path / "source"
    project_path.mkdir()
    monkeypatch.setenv("PROJECTS_FILE", str(config_file))

    good = {
        "path": str(project_path),
        "runtime": {
            "workspace_mode": "isolated_clone",
            "exclusive_project_lease": False,
            "developer_permission_mode": "trusted_project",
        },
        "ddev": {"enabled": True},
    }
    config_file.write_text(
        yaml.safe_dump({"version": 1, "projects": {
            "pcp-benchmark-g1-smoke": good,
        }}), encoding="utf-8",
    )
    assert config.project_config("pcp-benchmark-g1-smoke")["runtime"][
        "developer_permission_mode"
    ] == "trusted_project"

    for id_, case in [
        ("chonhac", good),
        ("pcp-benchmark-other", good),
        ("pcp-benchmark-g1-smoke", {**good, "ddev": {"enabled": False}}),
        ("pcp-benchmark-g1-smoke", {**good, "runtime": {
            **good["runtime"], "workspace_mode": "direct",
            "exclusive_project_lease": True,
        }}),
        ("pcp-benchmark-g1-smoke", {**good, "runtime": {
            **good["runtime"], "exclusive_project_lease": True,
        }}),
    ]:
        config_file.write_text(
            yaml.safe_dump({"version": 1, "projects": {id_: case}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="trusted_project requires exact"):
            config.project_config(id_)


def test_trusted_project_is_not_trusted_local_host_execution(
    tmp_path, monkeypatch,
):
    from app import developer_permissions

    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(developer_permissions, "projects_doc", lambda: {
        "projects": {"pcp-benchmark-g1-smoke": {
            "path": str(source),
            "runtime": {
                "workspace_mode": "isolated_clone",
                "developer_permission_mode": "trusted_project",
            },
        }}
    })
    assert developer_permissions.trusted_local_developer_enabled(
        source, "execute", adapter="codex_cli",
    ) is False
    assert developer_permissions.trusted_local_developer_enabled(
        source, "repair", adapter="antigravity_host",
    ) is False
