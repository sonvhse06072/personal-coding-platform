from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts" / "antigravity-bridge.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("pcp_antigravity_bridge_effort", BRIDGE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_omits_effort_when_model_does_not_support_it() -> None:
    module = load_bridge()

    cmd = module.build_run_command(
        "/usr/bin/agy",
        prompt="bounded prompt",
        model="claude-sonnet-4-6",
        effort=None,
        timeout=30,
        output_format="stream-json",
    )

    assert "--model" in cmd
    assert "claude-sonnet-4-6" in cmd
    assert "--effort" not in cmd


def test_bridge_keeps_explicit_supported_effort() -> None:
    module = load_bridge()

    cmd = module.build_run_command(
        "/usr/bin/agy",
        prompt="bounded prompt",
        model="gemini-3.8-flash-medium",
        effort="low",
        timeout=30,
        output_format="json",
    )

    assert cmd[cmd.index("--effort") + 1] == "low"


def test_bridge_trusted_local_run_keeps_terminal_sandbox() -> None:
    module = load_bridge()

    cmd = module.build_run_command(
        "/usr/bin/agy",
        prompt="implement",
        model="gemini-3.8-flash-medium",
        effort="medium",
        timeout=60,
        output_format="stream-json",
        sandbox=True,
    )

    assert "--sandbox" in cmd
    assert "--dangerously-skip-permissions" not in cmd


def test_bridge_trusted_local_permission_grants_only_ddev(tmp_path: Path) -> None:
    module = load_bridge()
    settings = tmp_path / "settings.json"
    original = {
        "enableTerminalSandbox": True,
        "toolPermission": "proceed-in-sandbox",
        "artifactReviewPolicy": "always-proceed",
        "allowNonWorkspaceAccess": False,
        "enableTelemetry": False,
        "permissions": {
            "allow": ["unsandboxed(git status)"],
            "deny": [
                "command(ddev)",
                "unsandboxed(ddev)",
                "command(docker)",
                "unsandboxed(docker)",
                "command(sudo)",
                "unsandboxed(sudo)",
            ],
            "ask": ["command(*)"],
        },
    }
    import json
    settings.write_text(json.dumps(original), encoding="utf-8")

    snapshot = module.apply_trusted_local_ddev_permission(settings)
    active = json.loads(settings.read_text(encoding="utf-8"))

    assert snapshot == original
    assert "unsandboxed(ddev)" in active["permissions"]["allow"]
    assert "command(ddev)" not in active["permissions"]["deny"]
    assert "unsandboxed(ddev)" not in active["permissions"]["deny"]
    assert "command(docker)" in active["permissions"]["deny"]
    assert "command(sudo)" in active["permissions"]["deny"]
    assert active["permissions"]["ask"] == ["command(*)"]

    module.restore_settings(settings, snapshot)
    assert json.loads(settings.read_text(encoding="utf-8")) == original


def test_bridge_bounded_run_keeps_sandbox_and_permissions() -> None:
    module = load_bridge()

    cmd = module.build_run_command(
        "/usr/bin/agy",
        prompt="inspect",
        model="gemini-3.8-flash-medium",
        effort=None,
        timeout=60,
        output_format="json",
    )

    assert "--sandbox" in cmd
    assert "--dangerously-skip-permissions" not in cmd
