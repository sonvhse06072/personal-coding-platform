from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "scripts" / "service-secret-status.sh"
PLATFORM_STATUS = ROOT / ".ddev" / "commands" / "host" / "platform-status"


def test_service_secret_status_script_is_shell_valid_and_non_secret() -> None:
    subprocess.run(["bash", "-n", str(STATUS)], check=True)
    script = STATUS.read_text(encoding="utf-8")

    assert "PLATFORM_INTERNAL_TOKEN" in script
    assert "GITHUB_DELIVERY_TOKEN" in script
    assert "RUNTIME_API_TOKEN" in script
    assert '"ok":%s' in script
    assert '"platform_internal_present":%s' in script
    assert '"github_delivery_present":%s' in script
    assert '"github_delivery_absent":%s' in script
    assert '[[ "$MODE" == "--strict" && "$ok" != "true" ]]' in script

    # The guard may inspect values only inside the target container. It must not
    # print the value or dump the environment to operator output.
    assert 'echo "$value"' not in script
    assert 'printf "%s" "$value"' not in script
    assert "printenv" not in script
    assert " env " not in script


def test_platform_status_reports_credential_boundary() -> None:
    script = PLATFORM_STATUS.read_text(encoding="utf-8")

    assert '"credential-boundary"' in script
    assert "bash ./scripts/service-secret-status.sh" in script
