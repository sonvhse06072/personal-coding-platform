from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


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
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(argv)}")
    return CommandResult(
        argv=argv,
        returncode=int(proc.returncode or 0),
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )
