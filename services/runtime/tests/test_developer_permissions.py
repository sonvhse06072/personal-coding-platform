from pathlib import Path

from app import developer_permissions


def test_trusted_local_mode_applies_only_to_exact_direct_workspace(monkeypatch, tmp_path: Path):
    direct = tmp_path / "chonhac"
    direct.mkdir()
    clone = tmp_path / "workspaces" / "job"
    clone.mkdir(parents=True)

    monkeypatch.setattr(
        developer_permissions,
        "projects_doc",
        lambda: {
            "projects": {
                "chonhac": {
                    "path": str(direct),
                    "runtime": {
                        "workspace_mode": "direct",
                        "developer_permission_mode": "trusted_local",
                    },
                }
            }
        },
    )

    assert developer_permissions.trusted_local_developer_enabled(
        direct, "execute", adapter="antigravity_host"
    ) is True
    assert developer_permissions.trusted_local_developer_enabled(
        direct, "repair", adapter="antigravity_host"
    ) is True
    assert developer_permissions.trusted_local_developer_enabled(
        direct, "execute", adapter="codex_cli"
    ) is False
    assert developer_permissions.trusted_local_developer_enabled(direct, "plan") is False
    assert developer_permissions.trusted_local_developer_enabled(direct, "evaluate") is False
    assert developer_permissions.trusted_local_developer_enabled(clone, "execute") is False


def test_bounded_mode_does_not_enable_trusted_local(monkeypatch, tmp_path: Path):
    direct = tmp_path / "chonhac"
    direct.mkdir()

    monkeypatch.setattr(
        developer_permissions,
        "projects_doc",
        lambda: {
            "projects": {
                "chonhac": {
                    "path": str(direct),
                    "runtime": {
                        "workspace_mode": "direct",
                        "developer_permission_mode": "bounded",
                    },
                }
            }
        },
    )

    assert developer_permissions.trusted_local_developer_enabled(direct, "execute") is False
