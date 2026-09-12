#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys


INVALID_TOKENS = {"CHANGE_ME", "change-me"}


def load_bridge_token() -> str:
    token = os.environ.get("ANTIGRAVITY_BRIDGE_TOKEN", "").strip()
    if not token or token in INVALID_TOKENS:
        raise RuntimeError("ANTIGRAVITY_BRIDGE_TOKEN is not configured")
    return token


def main() -> None:
    token = load_bridge_token()
    bridge = Path(__file__).with_name("antigravity-bridge.py")
    if not bridge.is_file():
        raise SystemExit(f"Missing {bridge}")

    # Keep the bearer secret out of the OS process command line. The existing
    # bridge still receives its --token argument internally through Python's
    # sys.argv, but /proc/<pid>/cmdline contains only this launcher's non-secret
    # arguments. Remove the inherited environment copy before starting the bridge.
    forwarded = list(sys.argv[1:])
    os.environ.pop("ANTIGRAVITY_BRIDGE_TOKEN", None)
    sys.argv = [str(bridge), *forwarded, "--token", token]
    runpy.run_path(str(bridge), run_name="__main__")


if __name__ == "__main__":
    main()
