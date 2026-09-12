from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_required_platform_files_exist():
    required = [
        ".ddev/config.yaml", ".ddev/docker-compose.platform.yaml", ".ddev/.env.example",
        "config/models.yml", "config/routing-policy.yml", "config/projects.yml",
        "services/router/app/main.py", "services/runtime/app/main.py", "services/ddev-executor/app/main.py",
        "services/ddev-executor/app/github_delivery.py",
    ]
    for item in required:
        assert (ROOT / item).exists(), item


def test_projects_yaml_parses():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    assert "default" in doc["projects"]


def test_chonhac_targeted_tests_execute_phpunit_and_static_analysis_executes_phpcs():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    ddev = doc["projects"]["chonhac"]["ddev"]
    targeted = ddev["targeted_tests"]
    static = ddev["static_analysis"]

    assert len(targeted) == 1
    assert "vendor/bin/phpunit" in targeted[0]
    assert "tests/src/Unit/*Test.php" in targeted[0]
    assert "web/core/phpunit.xml.dist" in targeted[0]
    assert static == ["ddev exec vendor/bin/phpcs web/modules/custom"]
    assert all("|| true" not in command for command in targeted + static)


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


def test_github_delivery_token_is_scoped_to_privileged_executor():
    doc = yaml.safe_load((ROOT / ".ddev/docker-compose.platform.yaml").read_text())
    services = doc["services"]
    assert "GITHUB_DELIVERY_TOKEN" in services["ddev-executor"]["environment"]
    assert "GITHUB_DELIVERY_TOKEN" not in services["coding-runtime"]["environment"]
    assert "GITHUB_DELIVERY_TOKEN" not in services["router"]["environment"]
    assert "GITHUB_DELIVERY_TOKEN" not in services["n8n"]["environment"]


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


def test_antigravity_bridge_is_bounded_for_headless_automation():
    bridge = (ROOT / "scripts" / "antigravity-bridge.py").read_text()
    launcher = (ROOT / "scripts" / "antigravity-bridge.sh").read_text()
    models = yaml.safe_load((ROOT / "config/models.yml").read_text())
    privacy = models["models"]["antigravity_free"]["privacy"]

    assert '"--sandbox"' in bridge
    assert "dangerously-skip-permissions" not in bridge
    assert 'data["toolPermission"] = "proceed-in-sandbox"' in launcher
    assert 'data["artifactReviewPolicy"] = "always-proceed"' in launcher
    assert 'data["enableTerminalSandbox"] = True' in launcher
    assert 'data["allowNonWorkspaceAccess"] = False' in launcher
    assert 'data["enableTelemetry"] = False' in launcher
    assert 'workspace_file_rules(workspace' in bridge
    assert 'f"read_file({workspace})"' in bridge
    assert 'f"write_file({workspace})"' in bridge
    assert 'f"read_file({git_dir})"' in bridge
    assert 'f"write_file({git_dir})"' in bridge
    assert 'self._agy_lock = threading.Lock()' in bridge
    assert 'rule.startswith("read_file(")' in launcher
    assert 'rule.startswith("write_file(")' in launcher
    assert '"unsandboxed(git status)"' in launcher
    assert '"unsandboxed(git diff)"' in launcher
    assert '"unsandboxed(git push)"' in launcher
    assert '"unsandboxed(docker)"' in launcher
    assert 'FORBIDDEN_ALLOW_RULES = {"unsandboxed(*)", "read_file(*)", "write_file(*)"}' in bridge
    assert 'FORBIDDEN_ASK_PREFIXES = ("read_file(", "write_file(")' in bridge
    assert privacy["training_policy_basis"] == "user_opt_out_enforced"
    assert privacy["enterprise_data_guarantee"] is False
    assert privacy["telemetry_opt_out_required"] is True


def test_patch_backups_are_not_committed():
    backups = [path for path in ROOT.rglob("*.bak-*") if ".git" not in path.parts]
    assert backups == []
