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
    assert "DASHBOARD_CONTROL_TOKEN" in script
    assert '"dashboard_control_present":%s' in script
    assert '"dashboard_control_absent":%s' in script
    assert '"ok":%s' in script
    assert '"platform_internal_present":%s' in script
    assert '"github_delivery_present":%s' in script
    assert '"github_delivery_absent":%s' in script
    assert '[[ "$MODE" == "--strict" && "$ok" != "true" ]]' in script

    # Only validated environment-variable names may be interpolated into the
    # container-side probe command. The value must never be emitted.
    assert '[[ "$1" =~ ^[A-Z_][A-Z0-9_]*$ ]]' in script
    assert 'echo "$value"' not in script
    assert 'printf "%s" "$value"' not in script
    assert "printenv" not in script


def test_service_secret_status_uses_one_ddev_shell_command_argument() -> None:
    script = STATUS.read_text(encoding="utf-8")

    # DDEV interprets a single command argument in the target container shell.
    # Do not reintroduce the broken sh -lc + positional-argument shape, which
    # loses the expected $1 contract through ddev exec command parsing.
    assert 'ddev exec -s "$service" "$command"' in script
    assert "sh -lc" not in script
    assert 'sh "$variable"' not in script
    assert 'name="$1"' not in script
    assert 'eval "value=\\${$name-}"' not in script


def test_platform_status_reports_credential_boundary() -> None:
    script = PLATFORM_STATUS.read_text(encoding="utf-8")

    assert '"credential-boundary"' in script
    assert "bash ./scripts/service-secret-status.sh" in script
