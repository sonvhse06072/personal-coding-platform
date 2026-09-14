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


class CommandTimeoutError(RuntimeError):
    """Typed coding-agent timeout used by Runtime state classification.

    The exception intentionally omits argv from its string form because coding
    commands carry the full model prompt as an argument. Callers that need to
    classify the timeout use the typed attributes instead of parsing logs.
    """

    def __init__(self, *, timeout: int | float, argv: list[str]) -> None:
        self.timeout = float(timeout)
        self.argv = tuple(argv)
        super().__init__(f"Command timed out after {timeout}s")


# Coding CLIs are untrusted workers. They need a normal process environment but
# must not inherit Runtime control-plane credentials or unrelated provider keys.
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
    """Build the minimal environment exposed to one coding-agent subprocess.

    Provider credentials are opt-in through ``extra``. Runtime/control-plane
    credentials are rejected even when a future adapter accidentally attempts to
    forward one explicitly.
    """
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
    merged = agent_subprocess_env(env)
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
    except TimeoutError as exc:
        await _terminate_process_group(proc)
        raise CommandTimeoutError(timeout=timeout, argv=argv) from exc
    return CommandResult(
        argv=argv,
        returncode=int(proc.returncode or 0),
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )
