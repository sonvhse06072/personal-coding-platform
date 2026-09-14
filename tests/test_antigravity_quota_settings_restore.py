from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "antigravity-bridge-quota-safe.py"


def load_module():
    spec = importlib.util.spec_from_file_location("antigravity_bridge_quota_safe", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_settings_bytes() -> bytes:
    return (
        json.dumps(
            {
                "enableTerminalSandbox": True,
                "toolPermission": "proceed-in-sandbox",
                "artifactReviewPolicy": "always-proceed",
                "allowNonWorkspaceAccess": False,
                "enableTelemetry": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def test_quota_probe_restores_settings_bytes_and_mode(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    settings = tmp_path / "settings.json"
    original = safe_settings_bytes()
    settings.write_bytes(original)
    os.chmod(settings, 0o600)

    def fake_read_cli_usage(binary: str):
        assert binary == "/usr/bin/agy"
        settings.write_text(
            json.dumps({"enableTerminalSandbox": True}) + "\n",
            encoding="utf-8",
        )
        os.chmod(settings, 0o644)
        return {"quota": {"Gemini": {"remaining_fraction": 0.5}}}, "ok"

    monkeypatch.setattr(module.quota19, "_read_cli_usage", fake_read_cli_usage)

    snapshot, status = module._read_cli_usage_preserving_settings(
        "/usr/bin/agy",
        settings,
    )

    assert status == "ok"
    assert snapshot is not None
    assert settings.read_bytes() == original
    assert settings.stat().st_mode & 0o777 == 0o600


def test_quota_probe_restores_settings_when_cli_raises(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    settings = tmp_path / "settings.json"
    original = safe_settings_bytes()
    settings.write_bytes(original)
    os.chmod(settings, 0o600)

    def fake_read_cli_usage(binary: str):
        settings.write_text("{}\n", encoding="utf-8")
        os.chmod(settings, 0o644)
        raise RuntimeError("simulated CLI failure")

    monkeypatch.setattr(module.quota19, "_read_cli_usage", fake_read_cli_usage)

    snapshot, status = module._read_cli_usage_preserving_settings(
        "/usr/bin/agy",
        settings,
    )

    assert snapshot is None
    assert status == "cli_usage_error:RuntimeError"
    assert settings.read_bytes() == original
    assert settings.stat().st_mode & 0o777 == 0o600


def test_quota_probe_is_serialized_with_antigravity_runs() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "with bridge._agy_lock:" in source
    assert "_read_cli_usage_preserving_settings(" in source
    assert 'version": "1.10"' in source
