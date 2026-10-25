"""H1c supplied fixtures/source bytes only. No DDEV/Docker/Host observation."""
import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pcp-local-ddev-install-plan.py"
EXAMPLE = ROOT / "profiles/pcp-local/ddev-install-plan.example.yml"


@pytest.fixture
def tool():
    return runpy.run_path(str(SCRIPT))


@pytest.fixture
def plan():
    return json.loads(EXAMPLE.read_bytes())


def stop(tool, plan, code):
    with pytest.raises(tool["Stop"], match="^" + code + "$"):
        tool["inspect"](plan)


def parked(plan):
    return yaml.safe_load(next(f["content"] for f in plan["observed"]["source"]["files"]
                              if f["path"].endswith("docker-compose.platform.yaml")))


def test_checked_in_plan_and_parked_effective_fixture_never_authorize(tool, plan):
    for config in (None, parked(plan)):
        plan["observed"]["effective_config"] = config
        result = tool["inspect"](plan)
        assert result["structure"] == "PASS" and result["result"] == "STOP"
        assert result["host"] is result["db"] is result["live"] is False
        assert result["checkout"] == "NOT_ATTESTED"
        assert result["authenticated_provenance"] == "NOT_VERIFIED"
        assert result["source_binding"] == "SUBMITTED_PINS_ONLY"
        assert "PARKED_USER_HOME_MISMATCH" in result["blockers"]
        assert "OCI_PRODUCER_NOT_VERIFIED" in result["blockers"]
        assert not any(plan["authority"]["phase_permits"].values())
        assert plan["observed"]["layout"]["install_root"] is None


def test_example_exact_payloads_match_four_accepted_repository_inputs(tool, plan):
    # Verify real SOURCE fixture identities; no Git/Host API call or probing.
    files = plan["observed"]["source"]["files"]
    assert len(files) == len(tool["PINS"]) == 4
    for item in files:
        raw = (ROOT / item["path"]).read_bytes()
        assert item["content"].encode() == raw
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == item["git_blob"]
    cfg = parked(plan)["services"]["coding-runtime"]
    assert cfg["user"] == "${DDEV_UID}:${DDEV_GID}" and cfg["environment"]["HOME"] == "/home/coder"
    assert cfg["profiles"] == ["pcp-inspect"] and cfg["pull_policy"] == "never"
    assert cfg["command"] == ["/PCP_H1B_SOURCE_ONLY_NOT_AUTHORIZED"]


@pytest.mark.parametrize("key,value", [("commit", "b" * 40), ("origin", "https://foreign.invalid/repo"),
                                      ("repository", "foreign/repo")])
def test_source_identity_cannot_chase_other_revision_or_origin(tool, plan, key, value):
    plan["observed"]["source"][key] = value
    stop(tool, plan, "SOURCE_IDENTITY_DRIFT")


@pytest.mark.parametrize("mode", ["120000", "160000", "100755", 100644])
def test_symlink_submodule_executable_and_wrong_mode_type(tool, plan, mode):
    plan["observed"]["source"]["files"][0]["mode"] = mode
    stop(tool, plan, "SOURCE_IDENTITY_DRIFT")


@pytest.mark.parametrize("path", ["../secret", "/foreign", ".ddev/config.yaml", "other.py"])
def test_extra_and_traversal_source_path_rejected(tool, plan, path):
    plan["observed"]["source"]["files"][0]["path"] = path
    stop(tool, plan, "SOURCE_INVENTORY_INVALID")


def test_duplicate_missing_extra_and_rehashed_policy_drift(tool, plan):
    for change in (lambda f: f.pop(), lambda f: f.append(deepcopy(f[0])),
                   lambda f: f.__setitem__(1, deepcopy(f[0]))):
        p = deepcopy(plan)
        change(p["observed"]["source"]["files"])
        stop(tool, p, "SOURCE_INVENTORY_INVALID")
    plan["expected"]["inputs"][next(iter(tool["PINS"]))]["sha256"] = "f" * 64
    stop(tool, plan, "EXPECTED_POLICY_DRIFT")


@pytest.mark.parametrize("payload", ["hooks: {pre-start: [{exec-host: malicious}]}\n",
    "x: &a [*a]\n", "!!python/object/apply:os.system ['fake']\n", "name: first\nname: second\n"])
def test_unpinned_yaml_never_reaches_yaml_parser(tool, plan, monkeypatch, payload):
    plan["observed"]["source"]["files"][0]["content"] = payload
    def forbidden(*a, **kw):
        raise AssertionError("untrusted YAML was parsed")
    monkeypatch.setattr(yaml, "safe_load", forbidden)
    stop(tool, plan, "SOURCE_BLOB_MISMATCH")


@pytest.mark.parametrize("field", ["clean", "host_verified", "git_worktree", "alternate_objects", "signature"])
def test_self_reported_source_checkout_proof_is_not_schema(tool, plan, field):
    plan["observed"]["source"][field] = True
    stop(tool, plan, "SCHEMA_INVALID")


@pytest.mark.parametrize("name", ["COMPOSE_PROFILES", "COMPOSE_FILE", "COMPOSE_PROJECT_NAME",
    "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_TLS_VERIFY", "HOST_HOME",
    "DDEV_APPROOT", "DDEV_SITENAME", "DDEV_GLOBAL_CONFIG", "GITHUB_TOKEN", "OPENAI_API_KEY",
    "PCP_LOCAL_TASK_SOURCE_ENABLED", "PCP_LOCAL_TASK_WORKER_ENABLED", "PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION",
    "PYTHONPATH", "LD_PRELOAD"])
def test_inherited_profiles_and_secret_or_context_overrides(tool, plan, name):
    plan["observed"]["environment"][name] = "*"
    stop(tool, plan, "ENVIRONMENT_OVERRIDE_UNSAFE")


@pytest.mark.parametrize("path", [".ddev/config.local.yaml", ".ddev/docker-compose.extra.yaml",
    ".ddev/.env", ".ddev/commands/host/bridge", ".ddev/homeadditions/.ssh/id", ".ddev/providers/live.yaml",
    "public/index.php", "/home/foreign/.codex/auth.json", "foreign/jobs/lease.json"])
def test_legacy_hooks_addons_hidden_files_credentials_and_old_state(tool, plan, path):
    plan["observed"]["extra_files"] = [path]
    stop(tool, plan, "LEGACY_OR_EXTRA_FILES_UNSAFE")


@pytest.mark.parametrize("key,value", [
    ("profiles", []), ("profiles", ["*"]), ("image", "legacy:local"),
    ("image", "pcp-local-runtime-inspect@sha256:" + "a" * 64), ("user", "0"), ("user", "65532:65532"),
    ("command", ["python", "-m", "uvicorn", "app.main:app"]), ("privileged", True),
    ("volumes", [{"source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}]),
    ("volumes", [{"source": "/home/foreign", "target": "/home/coder"}]),
    ("ports", ["8787:8787"]), ("network_mode", "host"), ("cap_add", ["ALL"]),
    ("build", {"context": "."}), ("environment", {"HOME": "/tmp"}),
    ("env_file", ["secret.env"]), ("entrypoint", ["sh"]),
])
def test_effective_config_values_not_just_keys_and_no_active_successor(tool, plan, key, value):
    config = parked(plan)
    config["services"]["coding-runtime"][key] = value
    plan["observed"]["effective_config"] = config
    stop(tool, plan, "EFFECTIVE_CONFIG_NOT_PARKED")


@pytest.mark.parametrize("service", ["web", "db", "router", "ddev-executor", "n8n"])
def test_ancillary_services_cannot_be_invented_as_approved(tool, plan, service):
    config = parked(plan)
    config["services"][service] = {"image": "unknown:latest"}
    plan["observed"]["effective_config"] = config
    stop(tool, plan, "EFFECTIVE_CONFIG_NOT_PARKED")


@pytest.mark.parametrize("kind", ["ddev_projects", "containers", "volumes", "networks", "images", "ports", "shared_effects"])
@pytest.mark.parametrize("status", ["stopped", "unlabeled", "claimed_owned"])
def test_collisions_or_shared_router_cache_consumers_never_adopted(tool, plan, kind, status):
    plan["observed"]["inventory"][kind] = [{"name": "pcp-local", "status": status,
        "labels": {"project": "pcp-local"}, "owner": "self-reported", "approved": True}]
    stop(tool, plan, "RESOURCE_COLLISION_OR_UNKNOWN")


def layout(tool, plan, root="/fixture/pcp-install"):
    obj = plan["observed"]["layout"]
    obj["install_root"] = root
    for key, relative in tool["LAYOUT"].items():
        obj[key + "_root"] = root + "/" + relative
    return obj


@pytest.mark.parametrize("root", ["relative/path", "/", "//server/share", "C:\\pcp", "/mnt/c/pcp",
    "/fixture/../pcp", "/fixture//pcp", "/fixture/pcp/", "/proc/pcp", "/fixture/\nsecret"])
def test_layout_unsafe_paths_do_not_probe_filesystem(tool, plan, root):
    layout(tool, plan, root)
    stop(tool, plan, "LAYOUT_UNSAFE")


def test_layout_overlap_symlink_nonexclusive_and_plausible_claims(tool, plan):
    p = deepcopy(plan); obj = layout(tool, p); obj["evidence_root"] = obj["instance_root"] + "/evidence"
    stop(tool, p, "LAYOUT_OVERLAP")
    for foreign in ("/fixture", "/fixture/pcp-install/foreign"):
        p = deepcopy(plan); obj = layout(tool, p); obj["foreign_roots"] = [foreign]
        stop(tool, p, "LAYOUT_FOREIGN_OVERLAP")
    p = deepcopy(plan); p["observed"]["layout"]["symlinks"] = ["/fixture/pcp-install"]
    stop(tool, p, "LAYOUT_SYMLINK_UNSAFE")
    p = deepcopy(plan); p["observed"]["layout"]["exclusive"] = True
    stop(tool, p, "OWNERSHIP_NOT_ATTESTED")
    layout(tool, plan)
    stop(tool, plan, "HOST_LAYOUT_NOT_ATTESTED")


@pytest.mark.parametrize("phase", ["SOURCE_INSPECT", "HOST_PLAN_RO", "SOURCE_PROVISION_APPLY", "RENDER_REVIEW",
                                   "FIRST_START_BASE", "FIRST_START_INSPECT", "HEALTH", "ROLLBACK"])
@pytest.mark.parametrize("permit", [True, {"approved": True, "signature": "fake", "expires": "2000-01-01"}])
def test_fake_expired_or_replayed_permits_have_no_authority(tool, plan, phase, permit):
    plan["authority"]["phase_permits"][phase] = permit
    stop(tool, plan, "HOST_AUTHORITY_NOT_APPROVED")


@pytest.mark.parametrize("flag", ["host", "db", "apply", "render", "start", "stop", "rollback", "live"])
@pytest.mark.parametrize("value", [True, 0])
def test_no_boolean_or_numeric_permission_shortcut(tool, plan, flag, value):
    plan["authority"][flag] = value
    stop(tool, plan, "HOST_AUTHORITY_NOT_APPROVED")


@pytest.mark.parametrize("field,value", [("image_digest", "sha256:" + "f" * 64), ("producer", "trusted-self"),
    ("trust_root", "artifact-key"), ("signature_verifier", "mock-pass"), ("authenticated_provenance", "PASS"),
    ("export_compatibility", "PASS"), ("ancillary_images", {"web": "latest"})])
def test_missing_independent_oci_producer_cannot_be_claimed_verified(tool, plan, field, value):
    plan["verification"]["oci"][field] = value
    stop(tool, plan, "VERIFICATION_CLAIM_NOT_TRUSTED")


@pytest.mark.parametrize("field", ["source_binding", "checkout", "host", "enforcement_proof"])
def test_fake_clean_render_and_enforcement_proof_cannot_promote_evidence(tool, plan, field):
    plan["verification"][field] = "VERIFIED"
    stop(tool, plan, "VERIFICATION_CLAIM_NOT_TRUSTED")


def source_receipt(tool, plan):
    key = tool["idempotency_key"](root=None, install_id="fixture-id", revision=plan["plan_revision"])
    return {"phase": "SOURCE_INSPECT", "state": "recorded", "root": None, "install_id": "fixture-id",
            "revision": plan["plan_revision"], "key": key, "previous_key": key}


def test_unsigned_identical_source_receipt_proposes_noop_only(tool, plan):
    plan["observed"]["journal"] = source_receipt(tool, plan)
    result = tool["inspect"](plan)
    assert result["proposed_action"] == "NO_OP_PROPOSAL" and result["result"] == "STOP"
    assert not result["host"] and not result["live"]
    first = tool["idempotency_key"](root="/fixture/a", install_id="fixture-id", revision=1)
    assert first != tool["idempotency_key"](root="/fixture/b", install_id="fixture-id", revision=1)
    assert first != tool["idempotency_key"](root="/fixture/a", install_id="fixture-other", revision=1)
    assert first != tool["idempotency_key"](root="/fixture/a", install_id="fixture-id", revision=2)


@pytest.mark.parametrize("field,value,code", [("phase", "FIRST_START_INSPECT", "HOST_JOURNAL_NOT_TRUSTED"),
    ("phase", "UNKNOWN", "HOST_JOURNAL_NOT_TRUSTED"), ("state", "partial", "JOURNAL_PARTIAL_OR_DRIFT"),
    ("root", "/fixture/claim", "JOURNAL_PARTIAL_OR_DRIFT"), ("revision", 2, "JOURNAL_PARTIAL_OR_DRIFT"),
    ("previous_key", "f" * 64, "JOURNAL_REPLAY_OR_DRIFT"), ("key", "f" * 64, "JOURNAL_REPLAY_OR_DRIFT")])
def test_partial_journal_race_drift_and_operational_replay(tool, plan, field, value, code):
    receipt = source_receipt(tool, plan); receipt[field] = value
    plan["observed"]["journal"] = receipt
    stop(tool, plan, code)


@pytest.mark.parametrize("name", ["deadline_seconds", "cpu", "memory_bytes", "disk_bytes", "egress_bytes"])
def test_resource_overrun_timeout_or_merely_declared_limits_stop(tool, plan, name):
    resources = plan["observed"]["resources"]
    resources["limits"][name], resources["observed"][name] = 10, 11
    stop(tool, plan, "RESOURCE_OVERRUN")
    resources["observed"][name] = 1
    stop(tool, plan, "RESOURCE_ENFORCEMENT_NOT_ATTESTED")
    resources["limits"][name] = True
    stop(tool, plan, "RESOURCE_VALUE_INVALID")


@pytest.mark.parametrize("change,code", [
    ({"requested_ids": ["new"]}, "ROLLBACK_OWNERSHIP_UNKNOWN"),
    ({"requested_ids": ["new"], "owned_new_ids": ["new"]}, "ROLLBACK_NOT_AUTHORIZED"),
    ({"requested_ids": ["old"], "foreign_ids": ["old"]}, "ROLLBACK_FOREIGN_OR_SHARED"),
    ({"consumers": ["shared-router"]}, "ROLLBACK_FOREIGN_OR_SHARED"),
    ({"ownership_proof": {"signature": "self"}}, "ROLLBACK_NOT_AUTHORIZED"),
])
def test_rollback_exact_ids_are_not_self_authorizing(tool, plan, change, code):
    plan["observed"]["rollback"].update(change)
    stop(tool, plan, code)


@pytest.mark.parametrize("raw,code", [(b'{"x":1,"x":2}', "DUPLICATE_KEY"),
    (b'x: &x [*x]', "JSON_SUBSET_REQUIRED"), (b'!!python/object/apply:os.system [fake]', "JSON_SUBSET_REQUIRED"),
    (b'{"x":NaN}', "NUMBER_UNSAFE"), (b'{"x":1.2}', "VALUE_UNSUPPORTED"),
    (b'[' * 22 + b'0' + b']' * 22, "INPUT_RESOURCE_LIMIT"), (b'"\\u0000"', "INPUT_STRING_UNSAFE")])
def test_parser_bombs_ambiguity_and_aliases_fail_closed(tool, raw, code):
    with pytest.raises(tool["Stop"], match=code):
        tool["parse"](raw)


def test_resource_size_cycle_and_non_schema_claims(tool, plan):
    with pytest.raises(tool["Stop"], match="INPUT_RESOURCE_LIMIT"):
        tool["parse"](b" " * (tool["MAX_BYTES"] + 1))
    cyclic = {}; cyclic["self"] = cyclic
    stop(tool, cyclic, "EVIDENCE_SCHEMA_INVALID")
    plan["observed"]["host_ready"] = True
    stop(tool, plan, "SCHEMA_INVALID")


def test_cli_stop_two_redaction_no_network_or_subprocess(tool, plan, tmp_path, capsys, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("external execution attempted")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    p = tmp_path / "data.json"; p.write_text(json.dumps(plan))
    for args in (["--check"], ["--check", str(p)], [], ["--start"], ["--apply"], ["--render"],
                 ["--stop"], ["--rollback"], ["--prepare"], ["--check", "--trust-root"]):
        assert tool["main"](args) == 2
        out = capsys.readouterr().out
        for line in ("PCP_H1C_RESULT=STOP", "PCP_H1C_HOST_INSTALL=STOP", "PCP_H1C_DB=STOP",
                     "PCP_H1C_LIVE=STOP", "PCP_H1C_OCI_PROVENANCE=NOT_VERIFIED"):
            assert line in out
    plan["observed"]["inventory"]["volumes"] = ["secret-path-and-id"]
    p.write_text(json.dumps(plan))
    assert tool["main"](["--check", str(p)]) == 2
    out = capsys.readouterr().out
    assert "RESOURCE_COLLISION_OR_UNKNOWN" in out and "secret-path-and-id" not in out
    link = tmp_path / "link"; link.symlink_to(p)
    assert tool["main"](["--check", str(link)]) == 2
    assert "INPUT_FILE_UNSAFE" in capsys.readouterr().out
    fifo = tmp_path / "fifo"; os.mkfifo(fifo)
    with pytest.raises(tool["Stop"], match="INPUT_FILE_UNSAFE"):
        tool["read_data"](fifo)


def test_no_host_adapter_or_dynamic_execution_and_new_paths_protected():
    tree = ast.parse(SCRIPT.read_text())
    imported = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not imported & {"subprocess", "socket", "urllib", "requests", "httpx", "ssl", "ctypes", "importlib"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"eval", "exec", "__import__"} for n in ast.walk(tree))
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    for path in (SCRIPT, EXAMPLE, ROOT / "docs/pcp-portable/h1c-ddev-install-plan.md"):
        assert policy["classify_path"](str(path.relative_to(ROOT))) == "protected"


def test_explicit_data_file_race_and_size_bound(tool, plan, tmp_path, monkeypatch):
    p = tmp_path / "data.json"; p.write_text(json.dumps(plan))
    original = os.fstat
    seen = []
    def race(fd):
        before = original(fd)
        seen.append(fd)
        if len(seen) == 1:
            p.write_text("{}")
        return before
    monkeypatch.setattr(os, "fstat", race)
    with pytest.raises(tool["Stop"], match="INPUT_FILE_CHANGED"):
        tool["read_data"](p)
    assert len(seen) == 2 and seen[0] == seen[1]
    monkeypatch.setattr(os, "fstat", original)
    p.write_bytes(b" " * (tool["MAX_BYTES"] + 1))
    with pytest.raises(tool["Stop"], match="INPUT_FILE_UNSAFE"):
        tool["read_data"](p)


def test_cli_coherent_structure_pass_still_complete_stop_contract(tool, capsys):
    assert tool["main"](["--check"]) == 2
    out = capsys.readouterr().out
    assert "PCP_H1C_STRUCTURE=PASS" in out
    assert "PCP_H1C_CHECKOUT=NOT_ATTESTED" in out
    assert "PCP_H1C_PARKED_USER_HOME=MISMATCH_UNRESOLVED" in out
    assert "PCP_H1C_RESULT=STOP" in out and "PCP_B22C1_LIVE=STOP" in out


def test_fixed_source_and_input_identities_participate_in_prospective_key(tool):
    fn = tool["idempotency_key"]
    args = dict(root=None, install_id="fixture-id", revision=1)
    first = fn(**args)
    anchor = fn.__globals__["SOURCE_COMMIT"]
    fn.__globals__["SOURCE_COMMIT"] = "b" * 40
    assert fn(**args) != first
    fn.__globals__["SOURCE_COMMIT"] = anchor
    pins = deepcopy(tool["PINS"])
    pins[next(iter(pins))]["sha256"] = "f" * 64
    fn.__globals__["PINS"] = pins
    assert fn(**args) != first
