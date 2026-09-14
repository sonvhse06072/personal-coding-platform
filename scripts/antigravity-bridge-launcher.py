#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys


INVALID_TOKENS = {"CHANGE_ME", "change-me"}
TOKEN_FD_ENV = "ANTIGRAVITY_BRIDGE_TOKEN_FD"
TOKEN_ENV = "ANTIGRAVITY_BRIDGE_TOKEN"


def load_bridge_token() -> str:
    fd_text = os.environ.get(TOKEN_FD_ENV, "").strip()
    if fd_text:
        try:
            fd = int(fd_text)
        except ValueError as exc:
            raise RuntimeError("ANTIGRAVITY_BRIDGE_TOKEN_FD is invalid") from exc
        try:
            raw = os.read(fd, 8192).decode("utf-8")
        except OSError as exc:
            raise RuntimeError("Unable to read ANTIGRAVITY_BRIDGE_TOKEN_FD") from exc
    else:
        raw = os.environ.get(TOKEN_ENV, "")

    token = raw.strip()
    if not token or token in INVALID_TOKENS:
        raise RuntimeError("ANTIGRAVITY_BRIDGE_TOKEN is not configured")
    return token


def main() -> None:
    token = load_bridge_token()
    bridge = Path(__file__).with_name("antigravity-bridge-live.py")
    if not bridge.is_file():
        raise SystemExit(f"Missing {bridge}")

    # The host wrapper supplies the bearer over a private inherited fd and starts
    # this process without the secret in argv or the initial environment. Keep the
    # legacy env fallback only for direct local invocation/tests, then scrub both
    # control variables before entering the long-running bridge implementation.
    forwarded = list(sys.argv[1:])
    os.environ.pop(TOKEN_ENV, None)
    os.environ.pop(TOKEN_FD_ENV, None)
    sys.argv = [str(bridge), *forwarded, "--token", token]
    runpy.run_path(str(bridge), run_name="__main__")


if __name__ == "__main__":
    main()
