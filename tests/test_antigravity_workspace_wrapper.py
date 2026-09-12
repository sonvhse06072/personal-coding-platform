from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "agy-workspace-wrapper.sh"


def safe_settings() -> dict:
    return {
        "enableTerminalSandbox": True,
        "toolPermission": "proceed-in-sandbox",
        "artifactReviewPolicy": "always-proceed",
        "allowNonWorkspaceAccess": False,
        "enableTelemetry": False,
        "permissions": {
            "allow": ["unsandboxed(git status)"],
            "deny": ["command(docker)"],
            "ask": [],
        },
    }


def test_wrapper_registers_exact_absolute_cwd_before_original_args(tmp_path: Path):
    workspace = tmp_path / "workspaces" / "job-123"
    workspace.mkdir(parents=True)
    capture = tmp_path / "args.txt"
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(safe_settings()), encoding="utf-8")
    fake_agy = tmp_path / "agy"
    fake_agy.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" > \"$CAPTURE\"\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)

    env = {
        **os.environ,
        "ANTIGRAVITY_REAL_AGY_BIN": str(fake_agy),
        "ANTIGRAVITY_SETTINGS_PATH": str(settings),
        "CAPTURE": str(capture),
    }
    completed = subprocess.run(
        ["bash", str(WRAPPER), "-p", "hello", "--sandbox"],
        cwd=workspace,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "--add-dir",
        str(workspace.resolve()),
        "-p",
        "hello",
        "--sandbox",
    ]


def test_wrapper_restores_bridge_owned_settings_after_cli_drift(tmp_path: Path):
    workspace = tmp_path / "workspaces" / "job-drift"
    workspace.mkdir(parents=True)
    settings = tmp_path / "settings.json"
    original = safe_settings()
    original["customSetting"] = "preserve-me"
    settings.write_text(json.dumps(original), encoding="utf-8")

    fake_agy = tmp_path / "agy"
    fake_agy.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "path = Path(os.environ['ANTIGRAVITY_SETTINGS_PATH'])\n"
        "data = json.loads(path.read_text())\n"
        "for key in ('enableTerminalSandbox', 'toolPermission', 'artifactReviewPolicy', 'allowNonWorkspaceAccess', 'enableTelemetry'):\n"
        "    data.pop(key, None)\n"
        "path.write_text(json.dumps(data))\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)

    env = {
        **os.environ,
        "ANTIGRAVITY_REAL_AGY_BIN": str(fake_agy),
        "ANTIGRAVITY_SETTINGS_PATH": str(settings),
    }
    completed = subprocess.run(
        ["bash", str(WRAPPER), "-p", "hello"],
        cwd=workspace,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    restored = json.loads(settings.read_text(encoding="utf-8"))
    for key, expected in safe_settings().items():
        if key != "permissions":
            assert restored[key] == expected
    assert restored["permissions"] == original["permissions"]
    assert restored["customSetting"] == "preserve-me"


def test_wrapper_preserves_agy_exit_code_after_restoring_settings(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(safe_settings()), encoding="utf-8")
    fake_agy = tmp_path / "agy"
    fake_agy.write_text(
        "#!/usr/bin/env bash\n"
        "python3 - \"$ANTIGRAVITY_SETTINGS_PATH\" <<'PY'\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "path = Path(sys.argv[1])\n"
        "data = json.loads(path.read_text())\n"
        "data.pop('enableTelemetry', None)\n"
        "path.write_text(json.dumps(data))\n"
        "PY\n"
        "exit 42\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)

    env = {
        **os.environ,
        "ANTIGRAVITY_REAL_AGY_BIN": str(fake_agy),
        "ANTIGRAVITY_SETTINGS_PATH": str(settings),
    }
    completed = subprocess.run(
        ["bash", str(WRAPPER), "-p", "hello"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 42
    restored = json.loads(settings.read_text(encoding="utf-8"))
    assert restored["enableTelemetry"] is False


def test_wrapper_fails_closed_without_real_agy(tmp_path: Path):
    env = {**os.environ}
    env.pop("ANTIGRAVITY_REAL_AGY_BIN", None)

    completed = subprocess.run(
        ["bash", str(WRAPPER), "-p", "hello"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 127
    assert "ANTIGRAVITY_REAL_AGY_BIN" in completed.stderr
