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


def test_service_homes_are_prepared_for_ddev_uid():
    compose = (ROOT / ".ddev/docker-compose.platform.yaml").read_text()
    runtime = (ROOT / "services/runtime/Dockerfile").read_text()
    executor = (ROOT / "services/ddev-executor/Dockerfile").read_text()

    assert "DDEV_UID: ${DDEV_UID}" in compose
    assert "DDEV_GID: ${DDEV_GID}" in compose
    for dockerfile in (runtime, executor):
        assert "ARG DDEV_UID=1000" in dockerfile
        assert "/home/coder/.cache" in dockerfile
        assert "chown -R ${DDEV_UID}:${DDEV_GID} /home/coder" in dockerfile


def test_antigravity_replaces_legacy_gemini_cli():
    models = (ROOT / "config/models.yml").read_text()
    compose = (ROOT / ".ddev/docker-compose.platform.yaml").read_text()
    factory = (ROOT / "services/runtime/app/adapters/factory.py").read_text()
    dockerfile = (ROOT / "services/runtime/Dockerfile").read_text()

    assert "antigravity_free:" in models
    assert "adapter: antigravity_host" in models
    assert "quota_group: antigravity_individual" in models
    assert "gemini_free:" not in models
    assert "gemini_cli" not in factory
    assert "@google/gemini-cli" not in dockerfile
    assert "/home/coder/.gemini" not in compose
    assert "ANTIGRAVITY_BRIDGE_URL" in compose
