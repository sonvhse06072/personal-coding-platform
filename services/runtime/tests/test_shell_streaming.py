import asyncio
import sys
from pathlib import Path

from app.shell import run_command


def test_run_command_streams_lines_before_return(tmp_path: Path):
    seen: list[str] = []

    async def run():
        task = asyncio.create_task(
            run_command(
                [
                    sys.executable,
                    "-c",
                    "import time; print('first', flush=True); time.sleep(0.15); print('second', flush=True)",
                ],
                cwd=tmp_path,
                timeout=5,
                on_stdout_line=seen.append,
            )
        )
        await asyncio.sleep(0.05)
        assert seen == ["first"]
        result = await task
        return result

    result = asyncio.run(run())
    assert seen == ["first", "second"]
    assert result.stdout == "first\nsecond\n"
    assert result.returncode == 0


def test_stream_callback_failure_does_not_fail_command(tmp_path: Path):
    def broken_callback(line: str) -> None:
        raise RuntimeError(f"dashboard down: {line}")

    result = asyncio.run(
        run_command(
            [sys.executable, "-c", "print('still-runs')"],
            cwd=tmp_path,
            timeout=5,
            on_stdout_line=broken_callback,
        )
    )
    assert result.returncode == 0
    assert result.stdout == "still-runs\n"
