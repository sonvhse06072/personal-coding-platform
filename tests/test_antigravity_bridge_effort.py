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
