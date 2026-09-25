from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scope-service-secrets.sh"
EXAMPLES = [
    ".env.router.local.example",
    ".env.coding-runtime.local.example",
    ".env.ddev-executor.local.example",
    ".env.n8n.local.example",
    ".env.host.local.example",
]
GLOBAL_SECRET_KEYS = {
    "ROUTER_API_TOKEN",
    "RUNTIME_API_TOKEN",
    "PLATFORM_INTERNAL_TOKEN",
    "ANTIGRAVITY_BRIDGE_TOKEN",
    "DASHBOARD_CONTROL_TOKEN",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key] = value
    return values


def make_harness(tmp_path: Path, global_text: str) -> Path:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    ddev = root / ".ddev"
    scripts.mkdir(parents=True)
    ddev.mkdir(parents=True)
    shutil.copy2(SCRIPT, scripts / SCRIPT.name)
    for name in EXAMPLES:
        shutil.copy2(ROOT / ".ddev" / name, ddev / name)
    (ddev / ".env").write_text(global_text, encoding="utf-8")
    return root


def run_scope(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "scripts" / SCRIPT.name)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "HOME": str(root / "home")},
    )


def test_legacy_global_credentials_are_migrated_to_only_required_consumers(tmp_path: Path):
    root = make_harness(
        tmp_path,
        "HOST_HOME=/home/test\n"
        "ANTIGRAVITY_BRIDGE_PORT=8792\n"
        "ROUTER_API_TOKEN=router-token\n"
        "RUNTIME_API_TOKEN=runtime-token\n"
        "PLATFORM_INTERNAL_TOKEN=internal-token\n"
        "ANTIGRAVITY_BRIDGE_TOKEN=agy-token\n"
        "DEEPSEEK_API_KEY=deepseek-token\n"
        "ANTHROPIC_API_KEY=\n"
        "OPENAI_API_KEY=openai-token\n"
        "GROQ_API_KEY=\n"
        "OPENROUTER_API_KEY=\n"
        "N8N_ENCRYPTION_KEY=keep-for-n8n-migration\n",
    )
    executor = root / ".ddev" / ".env.ddev-executor.local"
    shutil.copy2(root / ".ddev" / ".env.ddev-executor.local.example", executor)
    executor.write_text(
        executor.read_text(encoding="utf-8").replace("GITHUB_DELIVERY_TOKEN=", "GITHUB_DELIVERY_TOKEN=github-token"),
        encoding="utf-8",
    )

    completed = run_scope(root)
    assert completed.returncode == 0, completed.stderr

    global_env = parse_env(root / ".ddev" / ".env")
    assert not (GLOBAL_SECRET_KEYS & global_env.keys())
    assert global_env["N8N_ENCRYPTION_KEY"] == "keep-for-n8n-migration"

    router = parse_env(root / ".ddev" / ".env.router.local")
    runtime = parse_env(root / ".ddev" / ".env.coding-runtime.local")
    executor_values = parse_env(executor)
    n8n = parse_env(root / ".ddev" / ".env.n8n.local")
    host = parse_env(root / ".ddev" / ".env.host.local")

    assert router == {"ROUTER_API_TOKEN": "router-token"}
    assert runtime["ROUTER_API_TOKEN"] == "router-token"
    assert runtime["RUNTIME_API_TOKEN"] == "runtime-token"
    assert runtime["PLATFORM_INTERNAL_TOKEN"] == "internal-token"
    assert runtime["ANTIGRAVITY_BRIDGE_TOKEN"] == "agy-token"
    assert runtime["DASHBOARD_CONTROL_TOKEN"]
    assert runtime["DASHBOARD_CONTROL_TOKEN"] not in {
        "CHANGE_ME",
        "change-me",
    }
    assert runtime["DEEPSEEK_API_KEY"] == "deepseek-token"
    assert runtime["OPENAI_API_KEY"] == "openai-token"
    assert executor_values["PLATFORM_INTERNAL_TOKEN"] == "internal-token"
    assert executor_values["GITHUB_DELIVERY_TOKEN"] == "github-token"
    assert n8n["RUNTIME_API_TOKEN"] == "runtime-token"
    assert "ROUTER_API_TOKEN" not in n8n
    assert "PLATFORM_INTERNAL_TOKEN" not in n8n
    assert "ANTIGRAVITY_BRIDGE_TOKEN" not in n8n
    assert "DASHBOARD_CONTROL_TOKEN" not in n8n
    assert "DASHBOARD_CONTROL_TOKEN" not in router
    assert "DASHBOARD_CONTROL_TOKEN" not in executor_values
    assert "DASHBOARD_CONTROL_TOKEN" not in host
    assert host == {
        "RUNTIME_API_TOKEN": "runtime-token",
        "ANTIGRAVITY_BRIDGE_TOKEN": "agy-token",
    }


def test_conflicting_existing_shared_secret_fails_closed(tmp_path: Path):
    root = make_harness(tmp_path, "ROUTER_API_TOKEN=global-router-token\n")
    router = root / ".ddev" / ".env.router.local"
    shutil.copy2(root / ".ddev" / ".env.router.local.example", router)
    router.write_text("ROUTER_API_TOKEN=different-router-token\n", encoding="utf-8")

    completed = run_scope(root)
    assert completed.returncode != 0
    assert "Conflicting existing values for ROUTER_API_TOKEN" in completed.stderr
    assert "global-router-token" not in completed.stderr
    assert "different-router-token" not in completed.stderr


def test_global_template_and_compose_do_not_reintroduce_credentials():
    global_template = parse_env(ROOT / ".ddev" / ".env.example")
    assert not (GLOBAL_SECRET_KEYS & global_template.keys())

    compose = (ROOT / ".ddev" / "docker-compose.platform.yaml").read_text(encoding="utf-8")
    for key in GLOBAL_SECRET_KEYS | {"GITHUB_DELIVERY_TOKEN", "N8N_ENCRYPTION_KEY", "N8N_CONTROL_PLANE_TOKEN"}:
        assert f"${{{key}" not in compose
    assert "ROUTER_INTERNAL_URL" not in compose


def test_n8n_sync_invokes_secret_scoping_via_bash():
    command = (ROOT / ".ddev" / "commands" / "host" / "n8n-sync").read_text(encoding="utf-8")
    assert "bash ./scripts/scope-service-secrets.sh" in command
