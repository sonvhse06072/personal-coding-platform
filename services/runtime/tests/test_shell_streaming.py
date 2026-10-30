import asyncio
import sys
from pathlib import Path

import pytest

from app.shell import CommandTimeoutError, run_command


def test_full_large_context_stdin_round_trip_and_closed_pipe(tmp_path):
    import hashlib
    payload = 'Tiêu chí không được cắt — original criteria\n' * 20000
    result = asyncio.run(run_command([sys.executable, '-c',
        'import sys,hashlib; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'],
        cwd=tmp_path, timeout=5, input_text=payload))
    assert result.returncode == 0 and result.stdout.strip() == hashlib.sha256(payload.encode()).hexdigest()
    early = asyncio.run(run_command([sys.executable, '-c', 'pass'],
        cwd=tmp_path, timeout=5, input_text=payload))
    assert early.returncode == 0


def test_context_stdin_timeout_is_bounded_and_does_not_disclose_prompt(tmp_path):
    payload = 'private context' * 100000
    with pytest.raises(CommandTimeoutError) as exc:
        asyncio.run(run_command([sys.executable, '-c', 'import time;time.sleep(10)'],
            cwd=tmp_path, timeout=0.1, input_text=payload))
    assert 'private context' not in str(exc.value)


def test_run_command_closes_stdin_for_noninteractive_subprocess(tmp_path: Path):
    result = asyncio.run(
        run_command(
            [
                sys.executable,
                "-c",
                "import sys; data=sys.stdin.read(); print(repr(data), flush=True)",
            ],
            cwd=tmp_path,
            timeout=5,
        )
    )

    assert result.returncode == 0
    assert result.stdout == "''\n"


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

def test_run_command_timeout_preserves_streamed_output_without_prompt_in_error(tmp_path: Path):
    async def run():
        with pytest.raises(CommandTimeoutError) as exc_info:
            await run_command(
                [
                    sys.executable,
                    "-c",
                    "import time; print('partial-before-timeout', flush=True); time.sleep(1)",
                ],
                cwd=tmp_path,
                timeout=0.05,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.stdout == "partial-before-timeout\n"
    assert exc.stderr == ""
    assert "partial-before-timeout" not in str(exc)
    assert "Command timed out after" in str(exc)



def test_run_command_survives_oversized_single_line_and_streams_later_line(tmp_path: Path):
    seen: list[str] = []
    oversized_chars = 1024 * 1024 + 8192
    script = (
        "import sys; "
        f"sys.stdout.write('x' * {oversized_chars} + '\\n'); "
        "sys.stdout.flush(); "
        "print('after-oversized-line', flush=True)"
    )

    result = asyncio.run(
        run_command(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            timeout=10,
            on_stdout_line=seen.append,
        )
    )

    assert result.returncode == 0
    assert result.stdout.startswith("x" * 1024)
    assert result.stdout.endswith("after-oversized-line\n")
    assert seen == ["after-oversized-line"]
