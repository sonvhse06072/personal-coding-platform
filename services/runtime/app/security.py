from __future__ import annotations

import ctypes
import os
import sys


PR_SET_DUMPABLE = 4


def harden_runtime_process_secret_boundary() -> None:
    """Prevent same-UID coding-agent children from inspecting Runtime memory/env.

    Runtime and coding CLIs intentionally share one container today. Sanitizing a
    child's environment is not sufficient on Linux because a same-UID child can
    otherwise inspect its parent through procfs/ptrace access checks. Mark Runtime
    non-dumpable before any coding-agent subprocess can be launched.

    Normal non-privileged child executables become dumpable again after exec, so
    this protects Runtime without changing the coding CLI's own execution model.
    """
    if sys.platform != "linux":
        return

    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
    if result != 0:
        error_number = ctypes.get_errno()
        detail = os.strerror(error_number) if error_number else "unknown error"
        raise RuntimeError(f"Unable to harden Runtime process secret boundary: {detail}")
