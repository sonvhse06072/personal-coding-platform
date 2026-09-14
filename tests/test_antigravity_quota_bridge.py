from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts" / "antigravity-bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("pcp_antigravity_bridge", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quota_payload_sanitizer_drops_credential_shaped_fields():
    bridge = load_bridge_module()

    sanitized = bridge.sanitize_quota_payload({
        "quota": {
            "gemini-weekly": {
                "remaining_fraction": 0.5,
                "reset_time": "2026-09-20T00:00:00Z",
                "access_token": "must-not-leak",
            }
        },
        "password": "must-not-leak",
    })

    assert sanitized["quota"]["gemini-weekly"]["remaining_fraction"] == 0.5
    assert "access_token" not in sanitized["quota"]["gemini-weekly"]
    assert "password" not in sanitized


def test_quota_endpoint_command_is_read_only_usage_print_mode(monkeypatch, tmp_path: Path):
    bridge = load_bridge_module()
    commands = []

    class FakeProc:
        returncode = 0
        pid = 12345

        def __init__(self, cmd, **kwargs):
            commands.append(list(cmd))

        def communicate(self, timeout=None):
            return (
                '{"quota":{"gemini-weekly":{"remaining_fraction":0.75,'
                '"reset_time":"2026-09-20T00:00:00Z"}}}',
                "",
            )

        def poll(self):
            return self.returncode

    monkeypatch.setattr(bridge, "settings_status", lambda path: (True, {}))
    monkeypatch.setattr(bridge.subprocess, "Popen", FakeProc)

    service = bridge.Bridge(
        token="test-token",
        workspaces=tmp_path,
        agy_bin="/usr/bin/agy",
        settings=tmp_path / "settings.json",
    )
    status, payload = service.quota(timeout=20)

    assert status == 200
    assert commands == [[
        "/usr/bin/agy",
        "-p", "/usage",
        "--output-format", "json",
        "--print-timeout", "20s",
    ]]
    assert "--sandbox" not in commands[0]
    assert "--model" not in commands[0]
    assert payload["source"] == "agy_print_usage_json"
    assert payload["payload"]["quota"]["gemini-weekly"]["remaining_fraction"] == 0.75
