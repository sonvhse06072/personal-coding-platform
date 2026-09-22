from __future__ import annotations

import asyncio
import os
import signal
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandTimeoutError(RuntimeError):
    """Typed coding-agent timeout used by Runtime state classification.

    The exception intentionally omits argv from its string form because coding
    commands carry the full model prompt as an argument. Callers that need to
    classify the timeout use the typed attributes instead of parsing logs.
    """

    def __init__(
        self,
        *,
        timeout: int | float,
        argv: list[str],
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.timeout = float(timeout)
        self.argv = tuple(argv)
        # Preserve bounded process output already observed before timeout so
        # adapters can classify/report the failed attempt without rerunning it.
        # argv may contain the full model prompt and intentionally remains absent
        # from the exception string.
        self.stdout = stdout[-12000:]
        self.stderr = stderr[-12000:]
        super().__init__(f"Command timed out after {timeout}s")


_SAFE_AGENT_ENV_KEYS = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "TMP",
    "TEMP",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "NODE_EXTRA_CA_CERTS",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
}

_FORBIDDEN_AGENT_ENV_KEYS = {
    "RUNTIME_API_TOKEN",
    "ROUTER_API_TOKEN",
    "PLATFORM_INTERNAL_TOKEN",
    "ANTIGRAVITY_BRIDGE_TOKEN",
    "GITHUB_DELIVERY_TOKEN",
}


def agent_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build the minimal environment exposed to one coding-agent subprocess."""
    env = {
        key: value
        for key in _SAFE_AGENT_ENV_KEYS
        if (value := os.environ.get(key)) is not None
    }
    for key, value in (extra or {}).items():
        if key in _FORBIDDEN_AGENT_ENV_KEYS:
            raise ValueError(f"Refusing to expose Runtime credential {key} to coding agent")
        if value is not None:
            env[key] = value
    return env


async def _terminate_process_group(proc: asyncio.subprocess.Process) -> None:
    """Terminate the whole CLI process tree, not only its immediate wrapper."""
    if proc.returncode is not None:
        return
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    if hasattr(proc, "wait"):
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
            return
        except TimeoutError:
            pass
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        with suppress(Exception):
            await proc.wait()
        return
    # Compatibility with lightweight process doubles that only implement the
    # historical communicate() surface. Real asyncio subprocesses use wait().
    if hasattr(proc, "communicate"):
        with suppress(Exception):
            await asyncio.wait_for(proc.communicate(), timeout=5)


async def _drain_stream(
    stream: asyncio.StreamReader | None,
    chunks: list[str],
    callback: Callable[[str], None] | None,
) -> None:
    if stream is None:
        return
    while True:
        line = await stream.readline()
        if not line:
            return
        text = line.decode("utf-8", errors="replace")
        chunks.append(text)
        if callback is not None:
            try:
                callback(text.rstrip("\r\n"))
            except Exception:
                # Live observability is explicitly fail-open for execution.
                pass


async def _run_legacy_communicate(
    proc: asyncio.subprocess.Process,
    *,
    argv: list[str],
    timeout: int,
) -> CommandResult:
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.CancelledError:
        await _terminate_process_group(proc)
        raise
    except TimeoutError as exc:
        await _terminate_process_group(proc)
        raise CommandTimeoutError(timeout=timeout, argv=argv) from exc
    return CommandResult(
        argv=argv,
        returncode=int(proc.returncode or 0),
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


async def run_command(
    argv: list[str],
    *,
    cwd: str | Path,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
    on_stdout_line: Callable[[str], None] | None = None,
    on_stderr_line: Callable[[str], None] | None = None,
) -> CommandResult:
    merged = agent_subprocess_env(env)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=merged,
        limit=1024 * 1024,
        start_new_session=True,
    )

    # Some deterministic unit tests and external adapters provide process doubles
    # that implement only the historical communicate() API. Keep that contract
    # while real asyncio subprocesses take the incremental streaming path below.
    if not hasattr(proc, "stdout") or not hasattr(proc, "stderr") or not hasattr(proc, "wait"):
        return await _run_legacy_communicate(proc, argv=argv, timeout=timeout)

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_task = asyncio.create_task(_drain_stream(proc.stdout, stdout_chunks, on_stdout_line))
    stderr_task = asyncio.create_task(_drain_stream(proc.stderr, stderr_chunks, on_stderr_line))
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        await asyncio.gather(stdout_task, stderr_task)
    except asyncio.CancelledError:
        await _terminate_process_group(proc)
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise
    except TimeoutError as exc:
        await _terminate_process_group(proc)
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise CommandTimeoutError(
            timeout=timeout,
            argv=argv,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
        ) from exc
    return CommandResult(
        argv=argv,
        returncode=int(proc.returncode or 0),
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
    )
