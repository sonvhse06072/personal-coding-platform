from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_chonhac_pm_bridge_is_explicitly_allowlisted():
    path = ROOT / "config" / "pm-bridge.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg = doc["projects"]["chonhac"]

    assert doc["version"] == 1
    assert cfg["enabled"] is True
    assert cfg["allowed_authors"] == ["sonvhse06072"]
    assert cfg["marker"] == "<!-- coding-platform:pm-plan:v1 -->"
    assert cfg["max_comments_per_poll"] == 100
