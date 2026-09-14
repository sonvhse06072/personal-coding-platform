import asyncio
import sys
from pathlib import Path

import pytest

from app.shell import CommandTimeoutError, run_command


def test_cancelled_command_kills_spawned_children(tmp_path: Path):
    marker = tmp_path / "child-survived"
    child_code = (
        "import time; "
        "time.sleep(1.0); "
        f"open({str(marker)!r}, 'w').write('alive')"
    )
    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(60)"
    )

    async def scenario():
        task = asyncio.create_task(
            run_command([sys.executable, "-c", parent_code], cwd=tmp_path, timeout=30)
        )
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(1.15)

    asyncio.run(scenario())
    assert not marker.exists(), "cancelling a coding CLI must terminate its child process group"


def test_timeout_is_typed_sanitized_and_kills_spawned_children(tmp_path: Path):
    marker = tmp_path / "timeout-child-survived"
    child_code = (
        "import time; "
        "time.sleep(0.5); "
        f"open({str(marker)!r}, 'w').write('alive')"
    )
    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(60)"
    )

    async def scenario():
        with pytest.raises(CommandTimeoutError) as caught:
            await run_command(
                [sys.executable, "-c", parent_code],
                cwd=tmp_path,
                timeout=0.1,
            )
        assert caught.value.timeout == 0.1
        assert caught.value.argv[0] == sys.executable
        assert parent_code not in str(caught.value)
        await asyncio.sleep(0.55)

    asyncio.run(scenario())
    assert not marker.exists(), "timing out a coding CLI must terminate its child process group"
