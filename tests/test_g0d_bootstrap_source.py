"""Source-only bootstrap safety tests; never invoke real DDEV or local workspaces."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1] / "scripts/g0-drupal11-bootstrap"
CHECKER = ROOT / "check_ddev_name.py"
TARGET = "pcp-g0-drupal-fixture"


def ddev(raw):
    return subprocess.run(
        [sys.executable, str(CHECKER), TARGET],
        input=json.dumps(raw),
        text=True, capture_output=True, check=False,
    )


def test_official_ddev_json_shape_and_active_project_stop():
    # DDEV list -j returns projects in .raw[] (not .raw.projects).
    assert ddev({"level": "info", "raw": []}).returncode == 0
    assert ddev({"raw": [{"name": "stopped-fixture", "status": "stopped"}]}).returncode == 0
    assert ddev({"raw": [{"name": "chonhac", "status": "running"}]}).returncode == 4
    assert ddev({"raw": [{"name": "other", "status": "paused"}]}).returncode == 4
    assert ddev({"raw": [{"name": TARGET, "status": "stopped"}]}).returncode == 4
    assert ddev({}).returncode == 3


def test_packaged_source_manifest_is_exact():
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 3
    assert len(manifest["files"]) == 14
    for relative, sha in manifest["files"].items():
        path = ROOT / relative
        assert ".." not in Path(relative).parts
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha


def test_bootstrap_bash_static_safety():
    shell = ROOT / "bootstrap.sh"
    p = subprocess.run(["bash", "-n", str(shell)], capture_output=True, text=True, check=False)
    assert p.returncode == 0, p.stderr
    content = shell.read_text(encoding="utf-8")
    assert 'ddev list -j' in content
    assert 'ddev list --json' not in content
    assert 'check_ddev_name.py' in content
    assert 'gh repo create "$REMOTE" --private' in content
    for forbidden in ("ddev restart", "docker system prune", "git reset --hard", "rm -rf"):
        assert forbidden not in content


def test_real_drupal_coder_rejects_file_docblock_before_class_namespace():
    module = ROOT / "template/web/modules/custom/pcp_g0_fixture"
    classes = sorted(module.rglob("*.php"))
    assert len(classes) == 3
    for path in classes:
        text = path.read_text(encoding="utf-8")
        assert "namespace " in text
        assert "@file" not in text.split("namespace ", 1)[0]
