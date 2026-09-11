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
                "unsandboxed(git status)",
                "unsandboxed(git diff)",
                "unsandboxed(git log)",
                "unsandboxed(git show)",
                "unsandboxed(git ls-files)",
                "unsandboxed(git grep)",
                "unsandboxed(git rev-parse)",
            ],
            "deny": [
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
    assert details["file_permission_strategy"] == "per-run-absolute-workspace"


def test_settings_status_rejects_file_ask_rule_that_shadows_allow(tmp_path: Path):
    bridge = load_bridge_module()
    settings = safe_settings()
    settings["permissions"]["ask"].append("read_file(*)")
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")

    ok, details = bridge.settings_status(path)

    assert ok is False
    assert details["mismatches"]["permissions.ask.file_rules"] == ["read_file(*)"]


def test_workspace_file_rules_use_exact_absolute_clone_and_git_deny(tmp_path: Path):
    bridge = load_bridge_module()
    workspace = (tmp_path / "workspaces" / "job-123").resolve()

    allow, deny = bridge.workspace_file_rules(workspace)

    assert allow == {
        f"read_file({workspace})",
        f"write_file({workspace})",
    }
    assert deny == {
        f"read_file({workspace / '.git'})",
        f"write_file({workspace / '.git'})",
    }


def test_workspace_rules_are_temporary_and_preserve_non_file_policy(tmp_path: Path):
    bridge = load_bridge_module()
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(safe_settings()), encoding="utf-8")
    workspace = tmp_path / "workspaces" / "job-456"
    workspace.mkdir(parents=True)

    scoped_allow, scoped_deny = bridge.add_workspace_file_rules(path, workspace)
    active = json.loads(path.read_text(encoding="utf-8"))

    assert scoped_allow.issubset(set(active["permissions"]["allow"]))
    assert scoped_deny.issubset(set(active["permissions"]["deny"]))
    assert "unsandboxed(git status)" in active["permissions"]["allow"]
    assert "command(*)" in active["permissions"]["ask"]

    bridge.remove_workspace_file_rules(path, scoped_allow, scoped_deny)
    cleaned = json.loads(path.read_text(encoding="utf-8"))

    assert scoped_allow.isdisjoint(set(cleaned["permissions"]["allow"]))
    assert scoped_deny.isdisjoint(set(cleaned["permissions"]["deny"]))
    assert "unsandboxed(git status)" in cleaned["permissions"]["allow"]
    assert "command(*)" in cleaned["permissions"]["ask"]


def test_cancel_before_process_start_is_consumed_once(tmp_path: Path):
    bridge_module = load_bridge_module()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(safe_settings()), encoding="utf-8")
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    bridge = bridge_module.Bridge(
        token="secret",
        workspaces=workspaces,
        agy_bin="/bin/true",
        settings=settings,
    )

    assert bridge.cancel_run("queued-run") is True
    assert bridge.consume_cancelled("queued-run") is True
    assert bridge.consume_cancelled("queued-run") is False
