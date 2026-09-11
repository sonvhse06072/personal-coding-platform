import asyncio
import sys
from pathlib import Path

import pytest

from app.shell import run_command


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
