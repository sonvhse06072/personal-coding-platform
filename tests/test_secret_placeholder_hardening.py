from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SECRET_SCRIPTS = [
    ROOT / "scripts" / "scope-service-secrets.sh",
    ROOT / "scripts" / "n8n-control-plane.sh",
]
N8N_SCRIPT = ROOT / "scripts" / "n8n-control-plane.sh"


def extract_is_real_secret(path: Path) -> str:
    script = path.read_text(encoding="utf-8")
    start = script.index("is_real_secret() {")
    end = script.index("\n}\n\nset_env_value", start) + len("\n}")
    return script[start:end]


def run_secret_check(path: Path, value: str) -> subprocess.CompletedProcess[str]:
    function = extract_is_real_secret(path)
    return subprocess.run(
        ["bash", "-c", f'{function}\nis_real_secret "$1"', "secret-check", value],
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("path", SECRET_SCRIPTS, ids=lambda path: path.name)
@pytest.mark.parametrize("placeholder", ["", "   ", "CHANGE_ME", "change-me", " change-me "])
def test_secret_helpers_reject_placeholders_and_blank_values(path: Path, placeholder: str) -> None:
    completed = run_secret_check(path, placeholder)
    assert completed.returncode != 0


@pytest.mark.parametrize("path", SECRET_SCRIPTS, ids=lambda path: path.name)
def test_secret_helpers_accept_real_secrets(path: Path) -> None:
    completed = run_secret_check(path, "real-secret-value")
    assert completed.returncode == 0, completed.stderr


def test_n8n_runtime_boundary_rejects_legacy_placeholder_values() -> None:
    script = N8N_SCRIPT.read_text(encoding="utf-8")

    assert 'const placeholders = new Set(["CHANGE_ME", "change-me"]);' in script
    assert 'const value = (process.env[key] || "").trim();' in script
    assert "return !value || placeholders.has(value);" in script
