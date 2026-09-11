from __future__ import annotations

import asyncio
import os
import signal
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


async def _terminate_process_group(proc: asyncio.subprocess.Process) -> None:
    """Terminate the whole CLI process tree, not only its immediate wrapper."""
    if proc.returncode is not None:
        return
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.communicate(), timeout=5)
        return
    except TimeoutError:
        pass
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    with suppress(Exception):
        await proc.communicate()


async def run_command(
    argv: list[str],
    *,
    cwd: str | Path,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
) -> CommandResult:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=merged,
        # Coding CLIs can spawn tool/shell children. A dedicated session lets a
        # job cancellation terminate the entire process group deterministically.
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.CancelledError:
        await _terminate_process_group(proc)
        raise
    except TimeoutError:
        await _terminate_process_group(proc)
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(argv)}")
    return CommandResult(
        argv=argv,
        returncode=int(proc.returncode or 0),
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )
