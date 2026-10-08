import sys
import threading
import time
from pathlib import Path

from app.main import cancel_active, run_tracked


def test_cancel_active_kills_command_process_group(tmp_path: Path):
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
    result = {}

    def target():
        result["value"] = run_tracked(
            "job12345",
            [sys.executable, "-c", parent_code],
            cwd=tmp_path,
            timeout=30,
        )

    thread = threading.Thread(target=target)
    thread.start()
    time.sleep(0.15)
    assert cancel_active("job12345") is True
    thread.join(timeout=5)
    assert not thread.is_alive()
    time.sleep(1.1)
    assert not marker.exists(), "job cancellation must kill child commands as well"


def test_tracked_timeout_kills_command_children(tmp_path: Path):
    marker = tmp_path / "timed-out-child-survived"
    child_code = (
        "import time; "
        "time.sleep(2.0); "
        f"open({str(marker)!r}, 'w').write('alive')"
    )
    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(60)"
    )

    returncode, _stdout, stderr, timed_out = run_tracked(
        "jobtimeout123",
        [sys.executable, "-c", parent_code],
        cwd=tmp_path,
        timeout=1,
    )

    assert returncode == 124
    assert timed_out is True
    assert "Command timed out after 1s" in stderr
    assert cancel_active("jobtimeout123") is False  # Registry was released.
    time.sleep(1.2)
    assert not marker.exists(), "timed-out command must kill its child group"
