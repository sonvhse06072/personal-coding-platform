import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts" / "antigravity-bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("antigravity_bridge", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_settings():
    return {
        "enableTerminalSandbox": True,
        "toolPermission": "proceed-in-sandbox",
        "artifactReviewPolicy": "always-proceed",
        "allowNonWorkspaceAccess": False,
        "enableTelemetry": False,
        "permissions": {
            "allow": [
                "read_file(.)",
                "write_file(.)",
                "unsandboxed(git status)",
                "unsandboxed(git diff)",
                "unsandboxed(git log)",
                "unsandboxed(git show)",
                "unsandboxed(git ls-files)",
                "unsandboxed(git grep)",
                "unsandboxed(git rev-parse)",
            ],
            "deny": [
                "read_file(.git/)",
                "write_file(.git/)",
                "command(ddev)",
                "command(docker)",
                "command(sudo)",
                "unsandboxed(ddev)",
                "unsandboxed(docker)",
                "unsandboxed(sudo)",
                "unsandboxed(git push)",
                "unsandboxed(git fetch)",
                "unsandboxed(git pull)",
                "unsandboxed(git commit)",
                "unsandboxed(git checkout)",
                "unsandboxed(git switch)",
                "unsandboxed(git reset)",
                "unsandboxed(git clean)",
                "unsandboxed(git merge)",
                "unsandboxed(git rebase)",
            ],
            "ask": ["command(*)", "execute_url(aws.amazon.com)"],
        },
    }


def test_settings_status_accepts_non_file_ask_rules(tmp_path: Path):
    bridge = load_bridge_module()
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(safe_settings()), encoding="utf-8")

    ok, details = bridge.settings_status(path)

    assert ok is True
    assert details["mismatches"] == {}


def test_settings_status_rejects_file_ask_rule_that_shadows_allow(tmp_path: Path):
    bridge = load_bridge_module()
    settings = safe_settings()
    settings["permissions"]["ask"].append("read_file(*)")
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")

    ok, details = bridge.settings_status(path)

    assert ok is False
    assert details["mismatches"]["permissions.ask.file_rules"] == ["read_file(*)"]
