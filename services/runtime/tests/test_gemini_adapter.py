import asyncio
from pathlib import Path

from app.adapters.gemini import GeminiAdapter
from app.adapters.base import classify_provider_failure


class Result:
    returncode = 0
    stdout = '{"response":"done","stats":{"input_tokens":12,"output_tokens":3}}'
    stderr = ''


def test_workspace_untrusted_is_classified():
    kind, message = classify_provider_failure(
        'Gemini CLI is not running in a trusted directory. Use --skip-trust.'
    )
    assert kind == 'workspace_untrusted'
    assert '--skip-trust' in message


def test_gemini_headless_execution_skips_folder_trust(monkeypatch, tmp_path: Path):
    captured = {}

    async def fake_run(argv, *, cwd, timeout):
        captured['argv'] = argv
        captured['cwd'] = cwd
        return Result()

    monkeypatch.setattr('app.adapters.gemini.run_command', fake_run)
    run = asyncio.run(GeminiAdapter('auto').run(
        workspace=tmp_path,
        prompt='Make a small change',
        mode='execute',
        timeout=60,
    ))
    assert run.returncode == 0
    assert '--skip-trust' in captured['argv']
    assert captured['argv'][captured['argv'].index('--approval-mode') + 1] == 'yolo'
    assert captured['cwd'] == tmp_path
