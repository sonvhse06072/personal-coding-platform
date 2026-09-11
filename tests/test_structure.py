from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_required_platform_files_exist():
    required = [
        ".ddev/config.yaml", ".ddev/docker-compose.platform.yaml",
        "config/models.yml", "config/routing-policy.yml", "config/projects.yml",
        "services/router/app/main.py", "services/runtime/app/main.py", "services/ddev-executor/app/main.py",
    ]
    for item in required:
        assert (ROOT / item).exists(), item


def test_projects_yaml_parses():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    assert "default" in doc["projects"]
