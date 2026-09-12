from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "require-ddev-version.sh"
N8N_SYNC = ROOT / ".ddev" / "commands" / "host" / "n8n-sync"


def run_guard(tmp_path: Path, version_output: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_ddev = bin_dir / "ddev"
    fake_ddev.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ ${1:-} == '--version' ]]; then\n"
        f"  printf '%s\\n' {version_output!r}\n"
        "  exit 0\n"
        "fi\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_ddev.chmod(0o755)

    return subprocess.run(
        ["bash", str(GUARD), "1.25.4"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )


def test_guard_rejects_ddev_before_service_scoped_env_support(tmp_path: Path) -> None:
    completed = run_guard(tmp_path, "ddev version v1.25.3")

    assert completed.returncode != 0
    assert "DDEV >= 1.25.4 is required" in completed.stderr
    assert "found v1.25.3" in completed.stderr


def test_guard_accepts_minimum_supported_ddev(tmp_path: Path) -> None:
    completed = run_guard(tmp_path, "ddev version v1.25.4")

    assert completed.returncode == 0, completed.stderr


def test_guard_accepts_newer_ddev(tmp_path: Path) -> None:
    completed = run_guard(tmp_path, "ddev version v1.26.0")

    assert completed.returncode == 0, completed.stderr


def test_n8n_sync_checks_ddev_before_secret_migration() -> None:
    command = N8N_SYNC.read_text(encoding="utf-8")

    version_check = "bash ./scripts/require-ddev-version.sh 1.25.4"
    secret_scope = "bash ./scripts/scope-service-secrets.sh"
    assert version_check in command
    assert secret_scope in command
    assert command.index(version_check) < command.index(secret_scope)
