import os
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_required_platform_files_exist():
    required = [
        ".ddev/config.yaml", ".ddev/docker-compose.platform.yaml", ".ddev/.env.example",
        ".ddev/.env.router.local.example", ".ddev/.env.coding-runtime.local.example",
        ".ddev/.env.ddev-executor.local.example", ".ddev/.env.n8n.local.example",
        ".ddev/.env.host.local.example",
        "config/models.yml", "config/routing-policy.yml", "config/projects.yml",
        "services/router/app/main.py", "services/runtime/app/main.py", "services/ddev-executor/app/main.py",
        "services/ddev-executor/app/github_delivery.py",
        "scripts/pcp-build-images.sh", "scripts/pcp-resource-inventory.sh",
        "scripts/pcp-resource-gc.sh",
    ]
    for item in required:
        assert (ROOT / item).exists(), item


def test_projects_yaml_parses():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    assert "default" in doc["projects"]


def test_chonhac_enables_constrained_pm_merge_without_production_deploy():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    autonomy = doc["projects"]["chonhac"]["autonomy"]

    assert autonomy["allow_auto_merge_low_risk"] is True
    assert autonomy["allow_production_deploy"] is False


def test_chonhac_targeted_tests_execute_phpunit_and_static_analysis_executes_phpcs():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    ddev = doc["projects"]["chonhac"]["ddev"]
    targeted = ddev["targeted_tests"]
    static = ddev["static_analysis"]

    preflight = ddev["preflight"]
    assert preflight == [
        "ddev start -y",
        "ddev composer install --no-interaction",
    ]
    assert len(targeted) == 2
    assert targeted[0] == "ddev drush cr"
    targeted_runner = targeted[1]
    assert targeted_runner.startswith("ddev exec --raw -- bash -lc 'set -euo pipefail;")
    assert "ddev exec bash -lc" not in targeted_runner
    assert 'modules="$(git diff --name-only HEAD -- web/modules/custom |' in targeted_runner
    assert 'if [ -z "$modules" ]' in targeted_runner
    assert '\\"$modules\\"' not in targeted_runner
    assert "git diff --name-only HEAD -- web/modules/custom" in targeted_runner
    assert "for module in $modules" in targeted_runner
    assert "for layer in Unit Kernel Functional" in targeted_runner
    assert 'web/modules/custom/$module/tests/src/$layer' in targeted_runner
    assert "vendor/bin/phpunit -c web/core/phpunit.xml.dist" in targeted_runner
    assert "ShowDomainTest.php" not in targeted_runner
    assert "cho_nhac_show/tests" not in targeted_runner
    assert static == ["ddev exec vendor/bin/phpcs web/modules/custom"]
    assert all("|| true" not in command for command in targeted + static)



def test_chonhac_targeted_runner_preserves_variables_through_raw_ddev(tmp_path):
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    runner = doc["projects"]["chonhac"]["ddev"]["targeted_tests"][1]

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_ddev = bin_dir / "ddev"
    fake_ddev.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == "exec" ]]
shift
[[ "$1" == "--raw" ]]
shift
[[ "$1" == "--" ]]
shift
exec "$@"
""",
        encoding="utf-8",
    )
    fake_ddev.chmod(0o755)

    repo = tmp_path / "repo"
    test_dir = repo / "web/modules/custom/demo/tests/src/Unit"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "DemoTest.php"
    test_file.write_text("<?php\n// baseline\n", encoding="utf-8")

    phpunit = repo / "vendor/bin/phpunit"
    phpunit.parent.mkdir(parents=True)
    phpunit.write_text(
        "#!/usr/bin/env bash\nprintf 'PHPUNIT:%s\\n' \"$*\"\n",
        encoding="utf-8",
    )
    phpunit.chmod(0o755)

    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "pcp-test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "PCP Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, check=True, capture_output=True)
    test_file.write_text("<?php\n// changed\n", encoding="utf-8")

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        ["bash", "-lc", f'PATH="{bin_dir}:$PATH"; {runner}'],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Running targeted tests for demo" in result.stdout
    assert (
        "PHPUNIT:-c web/core/phpunit.xml.dist "
        "web/modules/custom/demo/tests/src/Unit/DemoTest.php"
    ) in result.stdout

def test_service_homes_are_prepared_for_ddev_uid():
    compose = (ROOT / ".ddev/docker-compose.platform.yaml").read_text()
    runtime = (ROOT / "services/runtime/Dockerfile").read_text()
    executor = (ROOT / "services/ddev-executor/Dockerfile").read_text()

    build_helper = (ROOT / "scripts/pcp-build-images.sh").read_text()
    assert 'DDEV_UID="${DDEV_UID:-$(id -u)}"' in build_helper
    assert 'DDEV_GID="${DDEV_GID:-$(id -g)}"' in build_helper
    for dockerfile in (runtime, executor):
        assert "ARG DDEV_UID=1000" in dockerfile
        assert "/home/coder/.cache" in dockerfile
        assert "chown -R ${DDEV_UID}:${DDEV_GID} /home/coder" in dockerfile


def test_pcp_custom_images_use_explicit_isolated_builder_path():
    compose = yaml.safe_load((ROOT / ".ddev/docker-compose.platform.yaml").read_text())
    services = compose["services"]
    expected = {
        "router": "personal-coding-platform-router:local",
        "coding-runtime": "personal-coding-platform-coding-runtime:local",
        "ddev-executor": "personal-coding-platform-ddev-executor:local",
    }
    for service, image in expected.items():
        assert services[service]["image"] == image
        assert "build" not in services[service]
    assert services["n8n"]["image"] == "${N8N_IMAGE:-n8nio/n8n:2.38.6}"

    hooks = yaml.safe_load((ROOT / ".ddev/config.yaml").read_text())["hooks"]["pre-start"]
    assert hooks[0]["exec-host"] == "bash ./scripts/pcp-build-images.sh"
    assert "antigravity-bridge.sh start" in hooks[1]["exec-host"]

    executor = services["ddev-executor"]
    assert executor["environment"]["PCP_BUILDX_BUILDER"] == "pcp-builder"
    assert executor["environment"]["PCP_BUILDX_CONFIG"] == "/home/coder/.pcp-buildx"
    assert "${HOST_HOME}/.coding-platform/buildx:/home/coder/.pcp-buildx" in executor["volumes"]
    assert all("/.docker" not in volume for volume in executor["volumes"])


def test_github_delivery_token_is_scoped_to_privileged_executor():
    doc = yaml.safe_load((ROOT / ".ddev/docker-compose.platform.yaml").read_text())
    services = doc["services"]
    for service in ("ddev-executor", "coding-runtime", "router", "n8n"):
        assert "GITHUB_DELIVERY_TOKEN" not in services[service]["environment"]

    global_env = (ROOT / ".ddev/.env.example").read_text()
    executor_env = (ROOT / ".ddev/.env.ddev-executor.local.example").read_text()
    runtime_env = (ROOT / ".ddev/.env.coding-runtime.local.example").read_text()
    n8n_env = (ROOT / ".ddev/.env.n8n.local.example").read_text()
    gitignore = (ROOT / ".gitignore").read_text().splitlines()
    assert "GITHUB_DELIVERY_TOKEN" not in global_env
    assert "GITHUB_DELIVERY_TOKEN=" in executor_env
    assert "GITHUB_DELIVERY_TOKEN" not in runtime_env
    assert "GITHUB_DELIVERY_TOKEN" not in n8n_env
    assert ".ddev/.env.ddev-executor.local" in gitignore


def test_antigravity_replaces_legacy_gemini_cli():
    models = (ROOT / "config/models.yml").read_text()
    compose = (ROOT / ".ddev/docker-compose.platform.yaml").read_text()
    factory = (ROOT / "services/runtime/app/adapters/factory.py").read_text()
    dockerfile = (ROOT / "services/runtime/Dockerfile").read_text()

    assert "antigravity_free:" in models
    assert "adapter: antigravity_host" in models
    assert "model: gemini-3.8-flash-medium" in models
    assert "quota_group: antigravity_gemini" in models
    assert "antigravity_claude_sonnet:" in models
    assert "quota_group: antigravity_claude_gpt" in models
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

def test_chonhac_frontend_quality_installs_playwright_browser_for_runtime_user():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    ddev = doc["projects"]["chonhac"]["ddev"]
    commands = ddev["frontend_quality"]

    assert ddev["workspace_nodejs_version"] == "24"
    assert ddev["verification_phase_capabilities"] == {
        "targeted_tests": {"requires": ["php_runtime"]},
        "static_analysis": {"requires": ["php_runtime"]},
        "frontend_quality": {"requires": ["local_listener"]},
        "visual_quality": {"requires": ["local_listener"]},
    }
    assert ddev["auto_required_phases"] == [
        {"phase": "frontend_quality", "path_prefixes": ["frontend/"]},
    ]
    assert len(commands) == 9
    assert any(
        "playwright install-deps chromium" in command
        and "ddev exec -u root" in command
        for command in commands
    )
    assert any(
        "playwright install chromium" in command
        and "ddev exec -u root" not in command
        for command in commands
    )
    assert any("npm run test:browser" in command for command in commands)
    assert all(
        "playwright install --with-deps chromium" not in command
        for command in commands
    )


def test_chonhac_visual_quality_is_local_bounded_and_after_frontend_quality():
    doc = yaml.safe_load((ROOT / "config/projects.yml").read_text())
    project = doc["projects"]["chonhac"]
    preview = project["preview"]
    ddev = project["ddev"]

    assert project["runtime"]["workspace_mode"] == "direct"
    assert project["runtime"]["exclusive_project_lease"] is True
    assert preview["frontend"]["enabled"] is True
    assert preview["visual_evidence"]["internal_base_url"] == "http://127.0.0.1:3100"
    assert preview["visual_evidence"]["viewports"] == [360, 390, 430, 768, 1024, 1440]
    assert ddev["visual_quality"] == [
        "ddev exec bash -lc 'cd frontend && npm run test:visual'"
    ]
    assert ddev["verification_phase_capabilities"]["visual_quality"]["requires"] == [
        "local_listener"
    ]
