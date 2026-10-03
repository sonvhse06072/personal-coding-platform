from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts" / "antigravity-bridge.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("pcp_antigravity_bridge_direct", BRIDGE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_allows_isolated_root_and_exact_direct_repo_only(tmp_path):
    module = load_bridge()
    workspaces = tmp_path / "workspaces"
    isolated = workspaces / "job-1"
    direct = tmp_path / "chonhac"
    sibling = tmp_path / "another-project"
    for path in (isolated, direct, sibling):
        path.mkdir(parents=True, exist_ok=True)
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n", encoding="utf-8")

    bridge = module.Bridge(
        token="test",
        workspaces=workspaces,
        agy_bin="/bin/true",
        settings=settings,
        direct_workspace=direct,
    )

    assert bridge.workspace_allowed(isolated) is True
    assert bridge.workspace_allowed(direct) is True
    assert bridge.workspace_allowed(sibling) is False
    assert bridge.workspace_allowed(direct / "nested") is False


def test_bridge_without_direct_repo_keeps_legacy_isolated_boundary(tmp_path):
    module = load_bridge()
    workspaces = tmp_path / "workspaces"
    isolated = workspaces / "job-1"
    outside = tmp_path / "chonhac"
    isolated.mkdir(parents=True)
    outside.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n", encoding="utf-8")

    bridge = module.Bridge(
        token="test",
        workspaces=workspaces,
        agy_bin="/bin/true",
        settings=settings,
    )

    assert bridge.workspace_allowed(isolated) is True
    assert bridge.workspace_allowed(outside) is False


def test_trusted_local_request_requires_exact_direct_workspace_and_execute_mode(tmp_path):
    module = load_bridge()
    direct = (tmp_path / "chonhac").resolve()
    direct.mkdir()
    sibling = (tmp_path / "other").resolve()
    sibling.mkdir()

    assert module.trusted_local_request_allowed(
        requested=True,
        workspace=direct,
        direct_workspace=direct,
        mode="execute",
    ) is True
    assert module.trusted_local_request_allowed(
        requested=True,
        workspace=direct,
        direct_workspace=direct,
        mode="repair",
    ) is True
    assert module.trusted_local_request_allowed(
        requested=True,
        workspace=direct,
        direct_workspace=direct,
        mode="evaluate",
    ) is False
    assert module.trusted_local_request_allowed(
        requested=True,
        workspace=sibling,
        direct_workspace=direct,
        mode="execute",
    ) is False
    assert module.trusted_local_request_allowed(
        requested=False,
        workspace=direct,
        direct_workspace=direct,
        mode="execute",
    ) is False
