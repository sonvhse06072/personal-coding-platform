from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "agy-workspace-wrapper.sh"


def test_wrapper_registers_exact_absolute_cwd_before_original_args(tmp_path: Path):
    workspace = tmp_path / "workspaces" / "job-123"
    workspace.mkdir(parents=True)
    capture = tmp_path / "args.txt"
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
