"""C3B separated F2 service topology: static source contract, never Docker."""
from __future__ import annotations

from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]
C3B = ROOT / "deploy/fullpath/compose.c3b-services.yml"
SOURCE = "79f265aeb305be8b4b9d87af200730f9eb950fb2"
TRIAL_PROFILE = "owner-gated-c3b-one-job"
IMAGES = {
    "fullpath-router": f"pcp-f2-c3b-router:{SOURCE[:12]}",
    "fullpath-executor": f"pcp-f2-c3b-executor:{SOURCE[:12]}",
    "fullpath-runtime": f"pcp-f2-c3b-runtime:{SOURCE[:12]}",
}


def topology():
    return yaml.safe_load(C3B.read_text(encoding="utf-8"))


def test_c3b_contains_only_explicit_profiled_existing_services_and_exact_images():
    compose = topology()
    assert compose["name"] == "pcp-f2-fullpath"
    assert set(compose["services"]) == set(IMAGES)
    assert compose["x-f2-c3b"]["status"] == "not_activated"
    assert compose["x-f2-c3b"]["source_sha"] == SOURCE

    for name, image in IMAGES.items():
        cfg = compose["services"][name]
        assert cfg["image"] == image
        assert cfg["profiles"] == [TRIAL_PROFILE]
        assert cfg["pull_policy"] == "never"
        assert cfg["restart"] == "no"
        assert cfg["platform"] == "linux/amd64"
        assert cfg["read_only"] is True
        assert cfg["cap_drop"] == ["ALL"]
        assert cfg["security_opt"] == ["no-new-privileges:true"]
        assert cfg["user"].startswith("${PCP_F2_UID:")
        assert cfg["mem_limit"].endswith("m")
        assert cfg["container_name"] == f"pcp-f2-fullpath-{name}-1"
        assert not set(cfg).intersection({
            "ports", "privileged", "build", "extra_hosts", "pid",
            "network_mode", "devices", "group_add",
        })
        assert "pcp-f2-fullpath" in cfg["container_name"]
        assert "fullpath-private" in cfg["networks"]
        for mount in cfg["volumes"]:
            assert mount["type"] == "bind"
            assert mount["bind"]["create_host_path"] is False
            assert mount["source"].startswith("${PCP_F2_")
            assert mount["target"].startswith((
                "/fullpath/", "/home/coder/.codex-fullpath",
            ))


def test_c3b_reuses_c2_private_network_not_database_or_any_host_ports():
    c3b = topology()
    nets = c3b["networks"]
    assert nets["fullpath-private"] == {
        "name": "pcp-f2-fullpath-private", "external": True,
    }
    assert set(nets) == {
        "fullpath-private", "github-egress", "provider-egress",
    }
    assert nets["github-egress"]["name"] == "pcp-f2-fullpath-github-egress"
    assert nets["provider-egress"]["name"] == "pcp-f2-fullpath-provider-egress"
    assert nets["github-egress"]["internal"] is False
    assert nets["provider-egress"]["internal"] is False

    assert c3b["services"]["fullpath-router"]["networks"] == ["fullpath-private"]
    assert c3b["services"]["fullpath-executor"]["networks"] == [
        "fullpath-private", "github-egress",
    ]
    assert c3b["services"]["fullpath-runtime"]["networks"] == [
        "fullpath-private", "provider-egress",
    ]
    assert "fullpath-db" not in c3b["services"]
    c2 = yaml.safe_load((ROOT / "deploy/fullpath/compose.c2-db-only.yml").read_text(
        encoding="utf-8",
    ))
    assert set(c2["services"]) == {"fullpath-db"}
    assert c2["networks"]["fullpath-private"]["name"] == (
        c3b["networks"]["fullpath-private"]["name"]
    )


def test_runtime_and_executor_secrets_are_independent_from_db_bootstrap():
    services = topology()["services"]
    router, executor, runtime = (
        services["fullpath-router"], services["fullpath-executor"],
        services["fullpath-runtime"],
    )
    assert "secrets" not in router
    assert executor["secrets"] == ["f2_executor_github_token"]
    assert runtime["secrets"] == ["f2_runtime_app_password"]

    exscript = executor["entrypoint"][2]
    rt_script = runtime["entrypoint"][2]
    assert executor["entrypoint"][:2] == ["/bin/sh", "-euc"]
    assert runtime["entrypoint"][:2] == ["/bin/sh", "-euc"]
    assert "/run/secrets/f2_executor_github_token" in exscript
    assert "export GITHUB_DELIVERY_TOKEN=" in exscript
    assert "export DATABASE_URL=" in rt_script
    assert "/run/secrets/f2_runtime_app_password" in rt_script
    assert "fullpath-db:5432/fullpath" in rt_script

    assert not {"GITHUB_DELIVERY_TOKEN", "DATABASE_URL"} & set(executor["environment"])
    assert not {"GITHUB_DELIVERY_TOKEN", "DATABASE_URL"} & set(runtime["environment"])
    assert not {"GITHUB_DELIVERY_TOKEN", "DATABASE_URL"} & set(router["environment"])
    assert "PCP_F2_GIT_ONLY_ENABLED" in executor["environment"]
    assert "PCP_F2_WORKER_ONLY_ENABLED" in runtime["environment"]
    assert runtime["environment"]["PCP_FULLPATH_SOURCE_ONLY"] == ""
    assert runtime["environment"]["PCP_FULLPATH_OPERATIONAL_ACTIVATION"] == ""
    for item in (executor, runtime):
        assert item["environment"]["PYTHONDONTWRITEBYTECODE"] == "1"
        assert item["environment"]["GIT_AUTHOR_NAME"].startswith(
            "${PCP_F2_GIT_AUTHOR_NAME:"
        )
        assert item["environment"]["GIT_AUTHOR_EMAIL"].startswith(
            "${PCP_F2_GIT_AUTHOR_EMAIL:"
        )
        assert item["environment"]["GIT_COMMITTER_NAME"] == (
            item["environment"]["GIT_AUTHOR_NAME"]
        )
        assert item["environment"]["GIT_COMMITTER_EMAIL"] == (
            item["environment"]["GIT_AUTHOR_EMAIL"]
        )
    assert any("/home/coder/.cache:" in path for path in runtime["tmpfs"])
    assert any("/home/coder/.config:" in path for path in runtime["tmpfs"])
    assert any("/home/coder/.local:" in path for path in runtime["tmpfs"])

    secrets = topology()["secrets"]
    assert secrets["f2_executor_github_token"]["file"].startswith(
        "${PCP_F2_GITHUB_TOKEN_FILE:"
    )
    assert secrets["f2_runtime_app_password"]["file"].startswith(
        "${PCP_F2_RUNTIME_DB_APP_PASSWORD_FILE:"
    )


def test_f2_source_only_unchanged_and_no_implicit_runtime_activation():
    active = yaml.safe_load(
        (ROOT / "deploy/fullpath/compose.source-only.yml").read_text(encoding="utf-8")
    )
    for name in IMAGES:
        assert active["services"][name]["entrypoint"] == ["/bin/false"]

    assert topology()["services"]["fullpath-runtime"]["environment"][
        "PCP_F2_WORKER_ONLY_ENABLED"
    ] == "${PCP_F2_WORKER_ONLY_ENABLED:-}"
    assert topology()["services"]["fullpath-executor"]["environment"][
        "PCP_F2_GIT_ONLY_ENABLED"
    ] == "${PCP_F2_GIT_ONLY_ENABLED:-}"

    assert "/var/run/docker.sock" not in str(topology())
    assert "github.com" not in str(topology())  # no fake FQDN egress guarantee
