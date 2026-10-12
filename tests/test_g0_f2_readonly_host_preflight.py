"""G0 F2 read-only WSL preflight has a strict command and target allowlist.

This test never executes Docker, Git, DDEV, model, GitHub API or host commands.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/g0-f2-readonly-host-preflight.py"
SPEC = importlib.util.spec_from_file_location("f2_readonly_preflight", SCRIPT)
f2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(f2)
SHA = "a" * 40


def fake_runner(
    *, sha=SHA, context="unix:///var/run/docker.sock", colliding=None,
    stderr=None, label_ids=None, failures=None,
):
    seen = []
    colliding = set(colliding or [])
    failures = failures or {}
    label_ids = label_ids or []

    def run(argv):
        assert argv in f2.ALLOWED
        seen.append(argv)
        if argv in failures:
            return CompletedProcess(argv, 1, "", failures[argv])
        if argv == f2.GIT_QUERY:
            return CompletedProcess(argv, 0, sha + "\n", "")
        if argv == f2.CONTEXT_QUERY:
            return CompletedProcess(
                argv, 0,
                json.dumps([{"Endpoints": {"docker": {"Host": context}}}]), "",
            )
        if argv == f2.CONTAINER_LABEL_QUERY:
            return CompletedProcess(argv, 0, "\n".join(label_ids), "")
        kind, name = argv[1], argv[3]
        if (kind, name) in colliding:
            return CompletedProcess(argv, 0, '[{"Name": "not-logged"}]', "")
        return CompletedProcess(argv, 1, "", f"Error: No such {kind}: {name}")

    return run, seen


def test_real_host_inventory_contract_is_named_f2_only_without_activation(monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    run, seen = fake_runner()
    result = f2.inspect(SHA, run=run)
    assert result["status"] == "STOP"
    assert result["source_head_verified"] is True
    assert result["local_unix_docker_context"] is True
    assert result["f2_names_currently_unoccupied"] is True
    assert result["f2_collisions"] == []
    assert result["operational_activation_authorized"] is False
    assert result["resource_mutations"] == result["model_calls"] == 0
    assert set(seen) == f2.ALLOWED
    assert len(seen) == len(f2.ALLOWED) == 10
    assert all(
        "pcp-f2-fullpath" in token or token in (
            "docker", "container", "network", "volume", "ls",
            "inspect", "context", "--all", "--quiet", "--filter",
            "git", "-C", "rev-parse", "HEAD", str(f2.ROOT),
        )
        for command in seen for token in command
    )


@pytest.mark.parametrize("kind,name", [
    (kind, name)
    for kind, names in f2.RESOURCES.items()
    for name in names
])
def test_any_existing_f2_resource_fails_noncollision(kind, name, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    run, _ = fake_runner(colliding={(kind, name)})
    observed = f2.inspect(SHA, run=run)
    assert observed["status"] == "STOP"
    assert observed["f2_names_currently_unoccupied"] is False
    assert observed["f2_collisions"] == [f"{kind}:{name}"]
    assert observed["operational_activation_authorized"] is False


def test_unknown_f2_labeled_container_is_not_mistaken_for_absent(monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    run, _ = fake_runner(label_ids=["a" * 64])
    outcome = f2.inspect(SHA, run=run)
    assert outcome["f2_names_currently_unoccupied"] is False
    assert outcome["f2_collisions"] == ["container:unexpected_f2_compose_label"]


@pytest.mark.parametrize("invalid", ["", "a" * 39, "b" * 41, "HEAD", "../legacy"])
def test_untrusted_expected_head_never_calls_docker(invalid):
    _, seen = fake_runner()
    with pytest.raises(f2.SafeStop, match="expected_pcp_source_sha_invalid"):
        f2.inspect(invalid, run=lambda argv: seen.append(argv))
    assert seen == []


def test_mismatched_source_head_fails_before_docker(monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    run, seen = fake_runner(sha="b" * 40)
    with pytest.raises(f2.SafeStop, match="pcp_source_head_mismatch"):
        f2.inspect(SHA, run=run)
    assert seen == [f2.GIT_QUERY]


@pytest.mark.parametrize("host", [
    "tcp://127.0.0.1:2375", "ssh://remote-host", "npipe:////./pipe/docker_engine",
])
def test_remote_context_is_not_used(host, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    run, seen = fake_runner(context=host)
    with pytest.raises(f2.SafeStop, match="docker_context_not_local_unix"):
        f2.inspect(SHA, run=run)
    assert seen == [f2.GIT_QUERY, f2.CONTEXT_QUERY]


def test_incompatible_docker_host_override_fails_closed(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://foreign:2375")
    run, seen = fake_runner()
    with pytest.raises(f2.SafeStop, match="docker_host_override_mismatch"):
        f2.inspect(SHA, run=run)
    assert seen == [f2.GIT_QUERY, f2.CONTEXT_QUERY]


@pytest.mark.parametrize("error", [
    "Permission denied to Docker daemon",
    "Cannot connect to the Docker daemon",
    "not found",
    "No such network: chonhac",
])
def test_ambiguous_or_foreign_docker_errors_not_treated_as_absence(error, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    name = f2.RESOURCES["network"][0]
    command = ("docker", "network", "inspect", name)
    run, _ = fake_runner(failures={command: error})
    with pytest.raises(f2.SafeStop, match="f2_docker_absence_not_proven"):
        f2.inspect(SHA, run=run)


@pytest.mark.parametrize("invalid_label", ["not-a-container", "../../other", "!" * 64])
def test_invalid_labeled_container_identity_stops(monkeypatch, invalid_label):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    run, _ = fake_runner(label_ids=[invalid_label])
    with pytest.raises(f2.SafeStop, match="f2_container_label_query_invalid"):
        f2.inspect(SHA, run=run)


@pytest.mark.parametrize("argv", [
    ("docker", "ps", "-a"),
    ("docker", "run", "--rm", "image"),
    ("docker", "volume", "rm", "pcp-f2-fullpath-postgres-data"),
    ("docker", "container", "inspect", "chonhac-runtime"),
    ("docker", "network", "inspect", "pcp-g0d01-private"),
    ("ddev", "list", "-j"),
    ("git", "-C", "/home/sonvh/chonhac", "status"),
])
def test_command_allowlist_blocks_legacy_other_projects_and_mutations(argv):
    with pytest.raises(f2.SafeStop, match="outside_f2_readonly_allowlist"):
        f2._run(argv)
