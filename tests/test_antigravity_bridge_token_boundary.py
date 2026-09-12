from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = ROOT / "scripts" / "antigravity-bridge-launcher.py"
BRIDGE_SCRIPT = ROOT / "scripts" / "antigravity-bridge.sh"


def load_launcher_module():
    spec = importlib.util.spec_from_file_location("antigravity_bridge_launcher", LAUNCHER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("configured", [None, "", "   ", "CHANGE_ME", "change-me"])
def test_launcher_rejects_missing_or_placeholder_token(monkeypatch, configured) -> None:
    launcher = load_launcher_module()
    if configured is None:
        monkeypatch.delenv("ANTIGRAVITY_BRIDGE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", configured)

    with pytest.raises(RuntimeError, match="ANTIGRAVITY_BRIDGE_TOKEN is not configured"):
        launcher.load_bridge_token()


def test_launcher_accepts_and_trims_real_token(monkeypatch) -> None:
    launcher = load_launcher_module()
    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "  real-bridge-token  ")

    assert launcher.load_bridge_token() == "real-bridge-token"


def test_launcher_removes_inherited_token_before_running_bridge(monkeypatch) -> None:
    launcher = load_launcher_module()
    monkeypatch.setenv("ANTIGRAVITY_BRIDGE_TOKEN", "real-bridge-token")
    monkeypatch.setattr(sys, "argv", [str(LAUNCHER_PATH), "--host", "127.0.0.1"])
    captured: dict[str, object] = {}

    def fake_run_path(path: str, *, run_name: str):
        captured["path"] = path
        captured["run_name"] = run_name
        captured["argv"] = list(sys.argv)
        captured["token_in_env"] = "ANTIGRAVITY_BRIDGE_TOKEN" in launcher.os.environ

    monkeypatch.setattr(launcher.runpy, "run_path", fake_run_path)
    launcher.main()

    assert captured["path"].endswith("scripts/antigravity-bridge.py")
    assert captured["run_name"] == "__main__"
    assert captured["token_in_env"] is False
    assert captured["argv"] == [
        str(ROOT / "scripts" / "antigravity-bridge.py"),
        "--host",
        "127.0.0.1",
        "--token",
        "real-bridge-token",
    ]


def test_host_script_never_places_bridge_token_in_child_argv() -> None:
    script = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert 'python3 "$BRIDGE_LAUNCHER"' in script
    assert '--token "$ANTIGRAVITY_BRIDGE_TOKEN"' not in script
    assert 'curl -fsS -H "Authorization: Bearer $ANTIGRAVITY_BRIDGE_TOKEN"' not in script
    assert 'env -u ANTIGRAVITY_BRIDGE_TOKEN curl -fsS -H @-' in script
