"""G0 dual ChatGPT auth/source-parity safety: no Docker/provider/GitHub activity."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/g0-codex-auth-operator.py"
SPEC = importlib.util.spec_from_file_location("g0_codex_auth_operator", SCRIPT)
auth = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auth)
SHA = "a" * 40


def doc():
    return yaml.safe_load(auth.OVERLAY.read_text(encoding="utf-8"))


def valid_rendered_compose():
    """Model Docker Compose long-form mount normalization without Docker."""
    mounts = {}
    for arm, path in auth.G0_AUTH_DIRS.items():
        mounts["auth_" + arm] = {
            "volumes": [
                {"type": "bind", "source": "/private/g0/" + arm,
                 "target": path},
                {"type": "tmpfs", "target": "/tmp",
                 "tmpfs": {"size": "134217728"}},
            ],
        }
    mounts["direct"] = {
        "volumes": [
            {"type": "bind", "source": "/private/g0/direct",
             "target": auth.G0_AUTH_DIRS["direct"]},
            {"type": "bind", "source": "/private/g0/arms/direct",
             "target": "/g0/direct-workspace"},
            {"type": "tmpfs", "target": "/tmp",
             "tmpfs": {"size": "134217728"}},
        ],
    }
    return {"services": mounts}


def test_overlay_is_nondefault_and_has_same_codex_image_with_separate_auth_roots():
    auth._validate_overlay()
    document = doc()
    services = document["services"]
    assert set(services) == {"auth_pcp", "auth_direct", "direct"}
    assert len({s["image"] for s in services.values()}) == 1
    assert all("docker.sock" not in str(s) for s in services.values())
    for name, service in services.items():
        assert "tmpfs" not in service  # no ambiguous top-level short syntax
        assert service["volumes"][-1] == {
            "type": "tmpfs", "target": "/tmp",
            "tmpfs": {"size": 134217728},
        }
    assert all(not s.get("ports") and s["read_only"] for s in services.values())
    assert all(s.get("profiles") for s in services.values())
    assert services["auth_pcp"]["volumes"][0]["target"] != (
        services["auth_direct"]["volumes"][0]["target"]
    )
    assert services["direct"]["volumes"][0] == services["auth_direct"]["volumes"][0]
    assert "/g0/direct-workspace" in str(services["direct"]["volumes"])
    assert all(s["command"] == ["--version"] for s in services.values())
    assert all(s["entrypoint"] == ["codex"] for s in services.values())
    assert all("GITHUB_DELIVERY_TOKEN" not in str(s) for s in services.values())
    assert document["x-g0-provider-contract"]["g0d_t01_dispatch"] is False
    assert document["x-g0-provider-contract"]["network_domain_allowlist_verified"] is False


@pytest.mark.parametrize("modify", [
    lambda d: d["services"]["auth_pcp"].update(privileged=True),
    lambda d: d["services"]["auth_direct"].update(
        ports=["127.0.0.1:15333:15333"]),
    lambda d: d["services"]["direct"].update(
        env_file=["/home/sonvh/.env"]),
    lambda d: d["services"]["auth_pcp"]["volumes"].append({
        "type": "bind", "source": "/var/run/docker.sock",
        "target": "/var/run/docker.sock",
    }),
    lambda d: d["services"]["auth_direct"]["volumes"][0].update(
        source="/home/sonvh/.codex"),
    lambda d: d["services"]["direct"]["environment"].update(
        GITHUB_DELIVERY_TOKEN="untrusted"),
    lambda d: d["services"]["direct"].update(network_mode="host"),
    lambda d: d["services"]["direct"].update(profiles=[]),
    lambda d: d["services"]["auth_pcp"].update(read_only=False),
    lambda d: d["services"]["direct"].update(image="node:latest"),
    lambda d: d["services"]["auth_pcp"].update(
        tmpfs=["/tmp:rw,nosuid,size=128m"]),
    lambda d: d["services"]["auth_direct"]["volumes"][-1].update(
        target="size=128m"),
    lambda d: d["services"]["direct"]["volumes"][-1]["tmpfs"].update(
        size=0),
    lambda d: d["services"]["auth_pcp"]["volumes"].append({
        "type": "tmpfs", "target": "/other"
    }),
    lambda d: d["networks"]["g0-provider-pcp"].update(
        name="shared-host-provider"),
    lambda d: d["x-g0-provider-contract"].update(
        g0_runtime_activation=True),
    lambda d: d["x-g0-provider-contract"].update(
        g0d_t01_dispatch=True),
    lambda d: d["services"].update({
        "legacy-runtime": {"image": "unsanctioned"},
    }),
])
def test_any_credential_mount_scope_or_activation_broadening_is_denied(
    monkeypatch, modify
):
    original = deepcopy(doc())
    modify(original)
    monkeypatch.setattr(auth.yaml, "safe_load", lambda *_a, **_k: original)
    with pytest.raises(auth.g0.GateError):
        auth._validate_overlay()


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    root = tmp_path / ".pcp-g0d01"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(auth, "_root", lambda: root)
    monkeypatch.setattr(auth.g0, "require_local_docker_context", lambda: None)
    monkeypatch.setattr(auth.g0, "require_exact_repo", lambda *a, **k: SHA)
    monkeypatch.setattr(auth.g0, "guard_source", lambda *a: None)
    monkeypatch.setattr(auth.g0, "read_private_state", lambda *a:
                        (auth.DEPLOYED_SHA, "a" * 48, root / "workspaces"))
    monkeypatch.setattr(auth.upgrader, "_verify_g0_resources", lambda *a: None)
    monkeypatch.setattr(auth.upgrader, "_require_empty_g0_job_store", lambda: None)
    monkeypatch.setattr(auth.upgrader, "_codex_cli_version",
                        lambda: auth.CLI_VERSION)
    monkeypatch.setattr(auth.g0, "exists", lambda *a: False)

    def fake_inspect(kind, name):
        if kind == "container":
            return {"Image": "sha256:" + "b" * 64}
        if kind == "image":
            return {"Id": "sha256:" + "b" * 64}
        raise AssertionError(kind)
    monkeypatch.setattr(auth.g0, "inspect", fake_inspect)
    monkeypatch.setattr(auth.g0, "compose_env",
                        lambda *a: {"PATH": "/usr/bin", "PCP_G0_RUNTIME_IMAGE":
                                    "pcp-g0d01-runtime:b60824e65af3"})
    return root


def test_read_only_preflight_no_docker_mutation(isolated, monkeypatch, tmp_path):
    commands = []
    def fake_run(argv, **kwargs):
        commands.append((argv, kwargs))
        assert argv[-3:] == ["config", "--format", "json"]
        return json.dumps(valid_rendered_compose())
    monkeypatch.setattr(auth.g0, "run", fake_run)
    report = auth.preflight(tmp_path, tmp_path, SHA)
    assert report["status"] == "PASS"
    assert report["ready_to_dispatch_g0d_t01"] is False
    assert report["installed_codex_cli_version"] == auth.CLI_VERSION
    assert report["network_domain_allowlist_verified"] is False
    assert len(commands) == 1
    assert commands[0][0][-3:] == ["config", "--format", "json"]
    assert not (isolated / "provider").exists()
    assert not any("up" in cmd or "run" in cmd for cmd, _ in commands)


def test_private_profiles_are_new_empty_no_token_copy(isolated, monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "preflight", lambda *a: {"status": "PASS"})
    result = auth.prepare(tmp_path, tmp_path, SHA)
    assert result["status"] == "PASS"
    assert result["phase"] == "g0_auth_profiles_prepared"
    for arm in ("pcp", "direct"):
        path = isolated / "provider" / arm
        auth._check_private_existing(path, directory=True)
        assert (path / "config.toml").read_text() == auth.AUTH_CONFIG
        auth._check_private_existing(path / "config.toml", directory=False)
        assert not (path / "auth.json").exists()
    assert (isolated / "arms/direct/workspace").is_dir()
    assert not (isolated / "arms/direct/workspace/.git").exists()
    with pytest.raises(auth.g0.GateError, match="collision|already_prepared"):
        auth.prepare(tmp_path, tmp_path, SHA)


@pytest.mark.parametrize("mutation", [
    lambda d: d["services"]["auth_pcp"]["volumes"][-1].update(
        target="size=128m"),
    lambda d: d["services"]["auth_pcp"]["volumes"][-1].update(
        type="volume", source="size=128m"),
    lambda d: d["services"]["auth_direct"]["volumes"][-1]["tmpfs"].update(
        size=268435456),
    lambda d: d["services"]["direct"]["volumes"].append({
        "type": "bind", "target": "/var/run/docker.sock"
    }),
])
def test_rendered_docker_mount_validation_rejects_daemon_invalid_or_broadening(
    isolated, monkeypatch, tmp_path, mutation
):
    sample = valid_rendered_compose()
    mutation(sample)
    monkeypatch.setattr(auth.g0, "run",
                        lambda argv, **kw: json.dumps(sample))
    with pytest.raises(auth.g0.GateError, match="g0_.*mount|g0_.*tmpfs"):
        auth._verify_rendered_tmpfs_mounts(tmp_path, {})


@pytest.mark.parametrize("size", [134217728, "134217728"])
def test_rendered_tmpfs_accepts_exact_integer_and_compose_json_string(size):
    assert auth._is_exact_rendered_tmpfs({
        "type": "tmpfs", "target": "/tmp", "tmpfs": {"size": size},
    })


@pytest.mark.parametrize("size", [
    "128m", "128MiB", "size=128m", "134217727", "134217729",
    134217727, 134217729, 134217728.0, 0, None, True, False, {},
])
def test_rendered_tmpfs_rejects_untrusted_or_broadened_size(size):
    assert not auth._is_exact_rendered_tmpfs({
        "type": "tmpfs", "target": "/tmp", "tmpfs": {"size": size},
    })


def test_rendered_mounts_allow_exact_mixed_compose_json_integer_encodings(
    isolated, monkeypatch, tmp_path
):
    sample = valid_rendered_compose()
    sample["services"]["auth_direct"]["volumes"][-1]["tmpfs"]["size"] = 134217728
    monkeypatch.setattr(auth.g0, "run",
                        lambda argv, **kw: json.dumps(sample))
    auth._verify_rendered_tmpfs_mounts(tmp_path, {})


def test_rendered_compose_validates_both_login_mounts_without_any_docker_call(
    isolated, monkeypatch, tmp_path
):
    commands = []
    def safe_config(argv, **kwargs):
        commands.append(argv)
        return json.dumps(valid_rendered_compose())
    monkeypatch.setattr(auth.g0, "run", safe_config)
    auth._verify_rendered_tmpfs_mounts(tmp_path, {})
    assert len(commands) == 1
    assert commands[0][-3:] == ["config", "--format", "json"]


def test_provider_identity_collision_rejected_without_reading_secrets(
    isolated, monkeypatch, tmp_path
):
    (isolated / "provider").mkdir(mode=0o700)
    with pytest.raises(auth.g0.GateError, match="already_prepared"):
        auth._context(tmp_path, tmp_path, SHA, require_prepared=False)
    monkeypatch.setattr(auth.g0, "exists", lambda kind, name: kind == "network")
    monkeypatch.setattr(auth.g0, "inspect", lambda kind, name: {
        "Labels": {"com.docker.compose.project": "foreign-project"},
        "Internal": False,
    } if kind == "network" else {
        "Image": "sha256:" + "b" * 64, "Id": "sha256:" + "b" * 64,
    })
    with pytest.raises(auth.g0.GateError, match="network_collision"):
        auth._context(tmp_path, tmp_path, SHA, require_prepared=False)


def test_symlink_or_untrusted_token_file_is_not_followed(
    isolated, monkeypatch, tmp_path
):
    (isolated / "provider").mkdir(mode=0o700)
    directory = isolated / "provider/pcp"
    directory.mkdir(mode=0o700)
    (directory / "config.toml").write_text(auth.AUTH_CONFIG, encoding="utf-8")
    (directory / "config.toml").chmod(0o600)
    (directory / "auth.json").symlink_to(tmp_path / "external-secret")
    with pytest.raises(auth.g0.GateError, match="private_auth_path_invalid"):
        auth._check_config("pcp")


def test_interactive_device_auth_cannot_touch_model_or_send_credentials(
    isolated, monkeypatch, tmp_path
):
    monkeypatch.setattr(auth, "preflight", lambda *a: {"status": "PASS"})
    auth.prepare(tmp_path, tmp_path, SHA)
    commands = []
    monkeypatch.setattr(
        auth.g0, "run",
        lambda argv, **kw: commands.append(argv) or json.dumps(valid_rendered_compose()),
    )
    def fake_docker(argv, **kw):
        commands.append(argv)
        assert kw["check"] is False
        assert kw["timeout"] == 900
        assert kw["env"]["PCP_G0_AUTH_PCP_DIR"] == str(isolated / "provider/pcp")
        assert "OPENAI_API_KEY" not in kw["env"]
        assert "GITHUB_DELIVERY_TOKEN" not in kw["env"]
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(auth.subprocess, "run", fake_docker)
    report = auth.device_login(tmp_path, tmp_path, SHA, "pcp")
    assert report["phase"] == "g0_device_login_completed"
    assert not report["ready_to_dispatch_g0d_t01"]
    assert len(commands) == 2
    argv = commands[-1]
    assert argv[-3:] == ["auth_pcp", "login", "--device-auth"]
    assert "run" in argv and "--rm" in argv and "--no-deps" in argv
    assert "exec" not in argv and "workspace" not in argv
    assert "auth_direct" not in argv
    with pytest.raises(auth.g0.GateError, match="unknown_login_arm"):
        auth.device_login(tmp_path, tmp_path, SHA, "chonhac")


def test_repeat_device_login_never_replaces_or_revokes_existing_g0_auth(
    isolated, monkeypatch, tmp_path
):
    monkeypatch.setattr(auth, "preflight", lambda *a: {"status": "PASS"})
    auth.prepare(tmp_path, tmp_path, SHA)
    cache = isolated / "provider/pcp/auth.json"
    cache.write_text('{"private":"not-for-tool-logs"}', encoding="utf-8")
    cache.chmod(0o600)
    monkeypatch.setattr(auth.g0, "run",
                        lambda *a, **kw: pytest.fail("no compose call for cached login"))
    monkeypatch.setattr(auth.subprocess, "run",
                        lambda *a, **kw: pytest.fail("no login for existing cache"))
    with pytest.raises(auth.g0.GateError, match="already_has_cached_credentials"):
        auth.device_login(tmp_path, tmp_path, SHA, "pcp")
    assert cache.read_text(encoding="utf-8") == '{"private":"not-for-tool-logs"}'


def test_altered_cli_or_deployed_source_refused_prior_to_login(isolated, monkeypatch, tmp_path):
    monkeypatch.setattr(auth.upgrader, "_codex_cli_version", lambda: "0.999.0")
    with pytest.raises(auth.g0.GateError, match="codex_cli_version_changed"):
        auth._context(tmp_path, tmp_path, SHA, require_prepared=False)


def test_script_does_not_auto_login_dispatch_or_boot_legacy_services():
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "docker system prune", "ddev start", "ddev poweroff",
        "docker restart", "--remove-orphans", "--volumes",
        "codex exec", "gh pr create", "git reset --hard",
        "git push", 'auth.json").read_text(',
        "OPENAI_API_KEY=", "GITHUB_DELIVERY_TOKEN=",
    ):
        assert forbidden not in source
    assert 'ready_to_dispatch_g0d_t01": False' in source
