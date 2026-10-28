from pathlib import Path

import pytest

from app.github_delivery import github_git_env


def test_github_git_env_isolates_host_credential_helpers(monkeypatch, tmp_path: Path):
    host_gitconfig = tmp_path / ".gitconfig"
    host_gitconfig.write_text(
        "[credential]\n\thelper = !/usr/bin/gh auth git-credential\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(host_gitconfig))
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)

    env = github_git_env("delivery-token")

    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_ASKPASS_REQUIRE"] == "force"
    assert env["GITHUB_DELIVERY_TOKEN"] == "delivery-token"

    askpass = Path(env["GIT_ASKPASS"])
    assert askpass.exists()
    assert askpass.stat().st_mode & 0o777 == 0o755
    askpass_text = askpass.read_text(encoding="utf-8")
    assert "GITHUB_DELIVERY_TOKEN" in askpass_text
    assert "delivery-token" not in askpass_text


def test_github_git_env_requires_delivery_token():
    with pytest.raises(RuntimeError, match="GITHUB_DELIVERY_TOKEN is not configured"):
        github_git_env("")


def test_askpass_is_immutable_and_runs_without_tmp_execution(monkeypatch):
    import subprocess
    from app.github_delivery import ensure_askpass_script
    def no_write(*args, **kwargs):
        raise AssertionError('askpass must not write /tmp or secrets')
    monkeypatch.setattr(Path, 'write_text', no_write)
    helper = ensure_askpass_script()
    assert '/tmp/' not in helper and helper.endswith('/app/github_askpass.sh')
    result = subprocess.run([helper, 'Username for HTTPS'], env={'PATH':'/usr/bin:/bin'}, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == 'x-access-token'
    result = subprocess.run([helper, 'Password for HTTPS'], env={'PATH':'/usr/bin:/bin','GITHUB_DELIVERY_TOKEN':'synthetic-only'}, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == 'synthetic-only'
