"""A3b.2 OCI producer SOURCE guards. No Host, Docker or provider operations."""
from pathlib import Path
import runpy
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NAME = ".github/workflows/pcp-local-inspect-image.yml"
WORKFLOW = ROOT / NAME
SOURCE = "e15aced199e180d919b5fd4a6c89bcf438d70a51"
TREE = "fd77542580bc148c8e2ed0bdce79fea22a290023"
APP = "7e667d28fea0a106280c880ed7ece6029e4e62af"
BUILDKIT = "sha256:99368f3e46177c6405b9740e4461d91cee004128daeecca78d4ceac50ec1da5c"
DEC = "DEC-PCP-B2-F3-815-A3B2-OCI-BUILD-ONEUSE-V1"
PACKAGE = "ghcr.io/sonvhse06072/pcp-local-runtime-inspect"
ACTIONS = {
    "actions/checkout": "11bd71901bbe5b1630ceea73d27597364c9af683",
    "docker/setup-buildx-action": "e468171a9de216ec08956ac3ada2f0791b6bd435",
    "docker/login-action": "5e57cd118135c172c3672efd75eb46360885c0ef",
    "docker/build-push-action": "263435318d21b8e681c14492fe198d362a7d2c83",
}


def _safe(source):
    try:
        d = yaml.load(source, Loader=yaml.BaseLoader)
        assert set(d) == {"name", "on", "permissions", "concurrency", "jobs"}
        assert d["on"] == {"workflow_dispatch": ""}
        assert d["permissions"] == {}
        assert d["concurrency"] == {"group": "pcp-local-inspect-image-singleton",
                                     "cancel-in-progress": "false"}
        assert set(d["jobs"]) == {"inspect-image-build"}
        j = d["jobs"]["inspect-image-build"]
        assert j["runs-on"] == "ubuntu-24.04" and j["timeout-minutes"] == "15"
        assert j["permissions"] == {"contents": "read", "packages": "write"}
        gate = j["if"]
        for atom in (
            "github.event_name == 'workflow_dispatch'",
            "github.repository == 'sonvhse06072/personal-coding-platform'",
            "github.ref == 'refs/heads/main'", "github.actor == 'sonvhse06072'",
            "github.run_attempt == 1",
            "vars.PCP_LOCAL_INSPECT_BUILD_WORKFLOW_SHA == github.sha",
            "vars.PCP_LOCAL_INSPECT_BUILD_DECISION == '" + DEC + "'",
        ):
            assert atom in gate
        assert gate.count("&&") == 6
        s = j["steps"]
        assert len(s) == 7
        assert {q["uses"].split("@")[0]: q["uses"].split("@")[1]
                for q in s if "uses" in q} == ACTIONS
        assert set(s[0]) == {"name", "shell", "run"}
        assert "GITHUB_RUN_ATTEMPT" in s[0]["run"]
        assert s[1]["with"] == {"repository": "sonvhse06072/personal-coding-platform",
                                 "ref": SOURCE, "fetch-depth": "1",
                                 "persist-credentials": "false",
                                 "submodules": "false", "lfs": "false"}
        for expected in (SOURCE, TREE, APP, "sha256sum --check --status",
                         "Dockerfile.inspect.dockerignore", "requirements-inspect.lock",
                         "git status --porcelain"):
            assert expected in s[2]["run"]
        assert s[3]["with"] == {
            "driver": "docker-container",
            "driver-opts": "image=moby/buildkit@" + BUILDKIT + "\nnetwork=bridge\n",
            "buildkitd-flags": "--oci-worker-net bridge",
        }
        assert s[4]["with"] == {
            "registry": "ghcr.io", "username": "${{ github.actor }}",
            "password": "${{ secrets.GITHUB_TOKEN }}",
        }
        assert s[5]["id"] == "image"
        assert s[5]["with"] == {
            "context": ".", "file": "./profiles/pcp-local/runtime/Dockerfile.inspect",
            "platforms": "linux/amd64", "push": "true",
            "tags": PACKAGE + ":source-" + SOURCE,
            "no-cache": "true", "pull": "true",
            "provenance": "mode=max", "sbom": "true",
        }
        assert s[6]["env"] == {"IMAGE_DIGEST": "${{ steps.image.outputs.digest }}"}
        assert "PCP_A3B2_CODEX_LIVE=STOP" in s[6]["run"]
        assert source.count("secrets.GITHUB_TOKEN") == 1
        assert all(set(step).issubset({"name", "shell", "run", "uses", "with", "id", "env"})
                   for step in s)
        for bad in ("OPENAI_API_KEY", "docker.sock", "self-hosted", "workflow_run",
                    "pull_request:", "schedule:", "cron:", "build-args:",
                    "cache-from:", "cache-to:", "privileged:", "network: host",
                    "id-token:", "workflow_call:", "latest", "GITHUB_DELIVERY_TOKEN",
                    "github.event.inputs"):
            assert bad not in source
        return True
    except (AssertionError, KeyError, TypeError, ValueError, IndexError,
            AttributeError, yaml.YAMLError):
        return False


def test_exact_manual_gate_and_safe_build_graph():
    assert _safe(WORKFLOW.read_text(encoding="utf-8"))


def test_protected_classification():
    mod = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    assert mod["classify_path"](NAME) == "protected"
    assert mod["classify_path"]("services/runtime/app/main.py") == "protected"


def test_tier1_remains_below_cap_and_live_stops():
    state = (ROOT / "docs/project/current-state.md").read_text()
    assert len(state.encode("utf-8")) < 15000
    assert "A3B2_IMAGE_BUILD=STOP" in state and "CODEX_LIVE=STOP" in state


def test_pinned_image_is_inspection_only():
    f = (ROOT / "profiles/pcp-local/runtime/Dockerfile.inspect").read_text()
    assert "PCP_RUNTIME_STARTUP_MODE=pcp_local_inspect" in f
    assert "USER 65532:65532" in f and "HOME=/tmp" in f
    assert "127.0.0.1" in f
    assert "codex" not in f.lower()
    assert "--require-hashes" in (ROOT / "profiles/pcp-local/runtime/requirements-inspect.lock").read_text()


@pytest.mark.parametrize("old,new", [
    ("workflow_dispatch:", "push:"),
    ("github.actor == 'sonvhse06072'", "github.actor == 'other'"),
    ("github.run_attempt == 1", "github.run_attempt >= 1"),
    ("vars.PCP_LOCAL_INSPECT_BUILD_WORKFLOW_SHA == github.sha", "true"),
    ("vars.PCP_LOCAL_INSPECT_BUILD_DECISION == '" + DEC + "'", "true"),
    ("permissions: {}", "permissions: {contents: write}"),
    ("runs-on: ubuntu-24.04", "runs-on: self-hosted"),
    ("timeout-minutes: 15", "timeout-minutes: 360"),
    ("ref: " + SOURCE, "ref: main"),
    ("persist-credentials: false", "persist-credentials: true"),
    ("submodules: false", "submodules: true"),
    ("image=moby/buildkit@" + BUILDKIT, "image=moby/buildkit:latest"),
    ("network=bridge", "network=host"),
    ("buildkitd-flags: --oci-worker-net bridge",
     "buildkitd-flags: --allow-insecure-entitlement security.insecure"),
    ("push: true", "push: false"),
    ("no-cache: true", "no-cache: false"),
    ("provenance: mode=max", "provenance: false"),
    ("sbom: true", "sbom: false"),
    ("platforms: linux/amd64", "platforms: linux/arm64"),
    (PACKAGE + ":source-" + SOURCE, PACKAGE + ":latest"),
    ("PCP_A3B2_CODEX_LIVE=STOP", "PCP_A3B2_CODEX_LIVE=PASS"),
    ("@11bd71901bbe5b1630ceea73d27597364c9af683", "@v4"),
    ("@e468171a9de216ec08956ac3ada2f0791b6bd435", "@v3"),
    ("@263435318d21b8e681c14492fe198d362a7d2c83", "@v6"),
])
def test_adversarial_source_mutations_fail_closed(old, new):
    s = WORKFLOW.read_text(encoding="utf-8")
    assert s.count(old) == 1
    assert not _safe(s.replace(old, new, 1))


def test_extra_trigger_and_secret_injection_fail_closed():
    s = WORKFLOW.read_text(encoding="utf-8")
    assert not _safe(s.replace("  workflow_dispatch:\n",
                "  workflow_dispatch:\n  pull_request:\n", 1))
    assert not _safe(s.replace("push: true", "push: true\n          build-args: OPENAI_API_KEY=evil", 1))
