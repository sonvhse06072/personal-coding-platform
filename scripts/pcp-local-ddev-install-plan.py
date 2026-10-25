#!/usr/bin/env python3
"""H1c supplied-data inspection only. No Host/DDEV/Git API or installer.

Strict JSON (a YAML subset) plans, fixed source bytes and prospective receipts
can establish structural consistency only. Every invocation exits 2 / STOP.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

import yaml

EXAMPLE = Path(__file__).resolve().parents[1] / "profiles/pcp-local/ddev-install-plan.example.yml"
REPO = "sonvhse06072/personal-coding-platform"
ORIGIN = "https://github.com/" + REPO + ".git"
# Approved implementation anchor; never an automatically advanced baseline.
SOURCE_COMMIT = "a97bb3fb4901a425a53743a37d818caea15a3b29"
PINS = {
    "profiles/pcp-local/.ddev/config.yaml": {
        "mode": "100644", "git_blob": "525d2798dcd60ea745839b4f2f127d2b6e700ea4",
        "sha256": "b350c76fad14e88886bff3519f08050f1928a01da789c57be4ab254f22457b0f"},
    "profiles/pcp-local/.ddev/docker-compose.platform.yaml": {
        "mode": "100644", "git_blob": "95c41ce6c696488cac70354daa99116fc296c9bd",
        "sha256": "5dfb39789f89f8396917726e0515027fdc07433508fc00fc6add3e780b3a7a6b"},
    "config/projects.pcp-local.yml": {
        "mode": "100644", "git_blob": "9935771e9ef22c2f6b48f36a15c045a31d57e642",
        "sha256": "880383618e9a629f12e70932ed38a430bf2927e12e84e14c235b673b33c5f8ae"},
    "config/project-baselines.pcp-local.yml": {
        "mode": "100644", "git_blob": "21a0a97731643e3cec7b5786e118c5c49df79826",
        "sha256": "c5ffea92761c3bd9a8e6e0d3a5fa3437fd379582cbe1e7f653b4aef69aa39052"},
}
PHASES = ["SOURCE_INSPECT", "HOST_PLAN_RO", "SOURCE_PROVISION_APPLY", "RENDER_REVIEW",
          "FIRST_START_BASE", "FIRST_START_INSPECT", "HEALTH", "ROLLBACK"]
LAYOUT = {"source": "source/" + SOURCE_COMMIT, "instance": "instance", "evidence": "evidence"}
INVENTORY = {"ddev_projects", "containers", "volumes", "networks", "images", "ports", "shared_effects"}
LIMITS = {"deadline_seconds", "cpu", "memory_bytes", "disk_bytes", "egress_bytes"}
MAX_BYTES = 256 * 1024
MAX_NODES = 12000
MAX_DEPTH = 20
MAX_STRING = 65536
BLOCKERS = ["HOST_OWNERSHIP_NOT_ATTESTED", "OCI_PRODUCER_NOT_VERIFIED",
            "PARKED_USER_HOME_MISMATCH", "ACTIVE_PROFILE_SUCCESSOR_UNAPPROVED",
            "DDEV_SHARED_EFFECTS_NOT_ATTESTED", "RESOURCE_ENFORCEMENT_NOT_ATTESTED"]


class Stop(Exception):
    """Fixed redacted reason, never artifact-supplied text."""


def need(ok, code):
    if not ok:
        raise Stop(code)


def shape(obj, keys):
    need(type(obj) is dict and set(obj) == set(keys), "SCHEMA_INVALID")
    return obj


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def same(left, right):
    return canonical(left) == canonical(right)


def parse(raw):
    """JSON-only input rejects YAML anchors/tags before constructing objects."""
    need(type(raw) is bytes and len(raw) <= MAX_BYTES, "INPUT_RESOURCE_LIMIT")
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, "DUPLICATE_KEY")
            out[key] = value
        return out
    def constant(_):
        raise Stop("NUMBER_UNSAFE")
    try:
        obj = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Stop("JSON_SUBSET_REQUIRED") from exc
    count = 0
    def walk(value, depth=0):
        nonlocal count
        count += 1
        need(count <= MAX_NODES and depth <= MAX_DEPTH, "INPUT_RESOURCE_LIMIT")
        if type(value) is dict:
            for key, child in value.items():
                need(len(key) <= 256, "INPUT_RESOURCE_LIMIT")
                walk(child, depth + 1)
        elif type(value) is list:
            for child in value:
                walk(child, depth + 1)
        elif type(value) is str:
            need(len(value) <= MAX_STRING and "\0" not in value, "INPUT_STRING_UNSAFE")
        else:
            need(value is None or type(value) in (bool, int), "VALUE_UNSUPPORTED")
            if type(value) is int:
                need(abs(value) < 2**63, "NUMBER_UNSAFE")
    walk(obj)
    return obj


def source_inputs(source):
    shape(source, {"repository", "origin", "commit", "files"})
    need(source["repository"] == REPO and source["origin"] == ORIGIN
         and source["commit"] == SOURCE_COMMIT, "SOURCE_IDENTITY_DRIFT")
    files = source["files"]
    need(type(files) is list and len(files) == len(PINS), "SOURCE_INVENTORY_INVALID")
    documents, seen = {}, set()
    for item in files:
        shape(item, {"path", "mode", "git_blob", "sha256", "content"})
        path = item["path"]
        need(type(path) is str and path in PINS and path not in seen, "SOURCE_INVENTORY_INVALID")
        seen.add(path)
        need(same({k: item[k] for k in PINS[path]}, PINS[path]), "SOURCE_IDENTITY_DRIFT")
        need(type(item["content"]) is str, "SOURCE_CONTENT_INVALID")
        raw = item["content"].encode("utf-8")
        need(len(raw) <= MAX_STRING and b"\0" not in raw, "SOURCE_CONTENT_INVALID")
        need(hashlib.sha256(raw).hexdigest() == PINS[path]["sha256"]
             and hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
             == PINS[path]["git_blob"], "SOURCE_BLOB_MISMATCH")
        # ONLY exact hash-pinned accepted YAML reaches this parser; arbitrary
        # supplied YAML/aliases/tags can never reach safe_load.
        documents[path] = yaml.safe_load(raw)
    cfg = documents["profiles/pcp-local/.ddev/config.yaml"]
    compose = documents["profiles/pcp-local/.ddev/docker-compose.platform.yaml"]
    svc = compose["services"]["coding-runtime"]
    need(cfg["name"] == "pcp-local" and "hooks" not in cfg
         and svc["profiles"] == ["pcp-inspect"] and svc["pull_policy"] == "never"
         and svc["command"] == ["/PCP_H1B_SOURCE_ONLY_NOT_AUTHORIZED"]
         and svc["image"] == "pcp-local-runtime-inspect:source-unresolved-do-not-run",
         "PARKED_CONTRACT_INVALID")
    # Known intentional mismatch is a blocker, never a reason to edit inputs.
    need(svc["user"] == "${DDEV_UID}:${DDEV_GID}"
         and svc["environment"]["HOME"] == "/home/coder", "PARKED_CONTRACT_INVALID")
    projects = documents["config/projects.pcp-local.yml"]["projects"]
    baselines = documents["config/project-baselines.pcp-local.yml"]["projects"]
    need(set(projects) == {"pcp-local"} and projects["pcp-local"]["path"] is None
         and projects["pcp-local"]["registration_status"] == "draft"
         and all(value is False for value in projects["pcp-local"]["autonomy"].values())
         and projects["pcp-local"]["ddev"]["enabled"] is False
         and baselines == {"pcp-local": {"active_revision": None, "revisions": {}}},
         "DRAFT_REGISTRY_INVALID")
    return compose


def safe_root(value):
    need(type(value) is str and 1 < len(value) <= 512 and value.startswith("/")
         and not value.startswith("//") and "\\" not in value and ":" not in value
         and all(ord(c) >= 32 and ord(c) != 127 for c in value)
         and all(part not in ("", ".", "..") for part in value.split("/")[1:])
         and PurePosixPath(value).parts[1] not in {"mnt", "media", "net", "proc", "sys", "dev"},
         "LAYOUT_UNSAFE")
    return PurePosixPath(value)


def overlaps(left, right):
    return left.is_relative_to(right) or right.is_relative_to(left)


def validate_layout(layout):
    shape(layout, {"install_root", "source_root", "instance_root", "evidence_root",
                   "foreign_roots", "symlinks", "exclusive"})
    need(type(layout["symlinks"]) is list and not layout["symlinks"], "LAYOUT_SYMLINK_UNSAFE")
    need(type(layout["foreign_roots"]) is list and len(layout["foreign_roots"]) <= 32,
         "LAYOUT_UNSAFE")
    foreign = [safe_root(path) for path in layout["foreign_roots"]]
    keys = ("install_root", "source_root", "instance_root", "evidence_root")
    if any(layout[k] is not None for k in keys):
        roots = {k: safe_root(layout[k]) for k in keys}
        root = roots["install_root"]
        need(all(not overlaps(root, path) for path in foreign), "LAYOUT_FOREIGN_OVERLAP")
        children = [roots[k] for k in keys[1:]]
        need(all(not overlaps(a, b) for i, a in enumerate(children) for b in children[i+1:]),
             "LAYOUT_OVERLAP")
        need(all(roots[k + "_root"] == root / path for k, path in LAYOUT.items()), "LAYOUT_UNSAFE")
        # Lexical plausibility is not observed filesystem ownership or absence.
        raise Stop("HOST_LAYOUT_NOT_ATTESTED")
    need(layout["exclusive"] is None and not foreign, "OWNERSHIP_NOT_ATTESTED")


def idempotency_key(*, root, install_id, revision):
    """Prospective DATA identity, not an authorization/signature or Host journal."""
    need(root is None or isinstance(safe_root(root), PurePosixPath), "LAYOUT_UNSAFE")
    need(type(install_id) is str and re.fullmatch(r"fixture-[a-z0-9-]{1,48}", install_id)
         and type(revision) is int and 1 <= revision <= 1000, "JOURNAL_INVALID")
    return hashlib.sha256(canonical({"source_commit": SOURCE_COMMIT, "inputs": PINS,
        "root": root, "project": "pcp-local", "install_id": install_id, "revision": revision})).hexdigest()


def validate_journal(journal, revision):
    if journal is None:
        return "NO_OPERATION"
    shape(journal, {"phase", "state", "root", "install_id", "revision", "key", "previous_key"})
    need(journal["phase"] == "SOURCE_INSPECT", "HOST_JOURNAL_NOT_TRUSTED")
    need(journal["state"] == "recorded" and journal["root"] is None
         and type(journal["revision"]) is int and journal["revision"] == revision, "JOURNAL_PARTIAL_OR_DRIFT")
    key = idempotency_key(root=None, install_id=journal["install_id"], revision=revision)
    need(journal["key"] == key and journal["previous_key"] == key, "JOURNAL_REPLAY_OR_DRIFT")
    # At most an unsigned null-root SOURCE receipt; operational replay is denied.
    return "NO_OP_PROPOSAL"


def validate_resources(resources):
    shape(resources, {"limits", "observed", "enforcement"})
    limits, observed = shape(resources["limits"], LIMITS), shape(resources["observed"], LIMITS)
    for name in sorted(LIMITS):
        limit, value = limits[name], observed[name]
        for item in (limit, value):
            need(item is None or (type(item) is int and 0 <= item < 2**63), "RESOURCE_VALUE_INVALID")
        need(limit is None or value is None or value <= limit, "RESOURCE_OVERRUN")
    need(not any(v is not None for v in [*limits.values(), *observed.values(), resources["enforcement"]]),
         "RESOURCE_ENFORCEMENT_NOT_ATTESTED")


def validate_rollback(rollback):
    shape(rollback, {"requested_ids", "owned_new_ids", "foreign_ids", "consumers", "ownership_proof"})
    for key in ("requested_ids", "owned_new_ids", "foreign_ids", "consumers"):
        need(type(rollback[key]) is list and len(rollback[key]) <= 64
             and all(type(x) is str for x in rollback[key]), "ROLLBACK_INVALID")
    requested, owned, foreign = (set(rollback[k]) for k in ("requested_ids", "owned_new_ids", "foreign_ids"))
    need(not requested & foreign and not rollback["consumers"], "ROLLBACK_FOREIGN_OR_SHARED")
    need(requested <= owned, "ROLLBACK_OWNERSHIP_UNKNOWN")
    need(not requested and not owned and not foreign and rollback["ownership_proof"] is None,
         "ROLLBACK_NOT_AUTHORIZED")


def _inspect(plan):
    shape(plan, {"schema_version", "project_id", "repository", "approval_state", "plan_revision",
                 "expected", "observed", "verification", "authority"})
    need(type(plan["schema_version"]) is int and plan["schema_version"] == 1
         and plan["project_id"] == "pcp-local" and plan["repository"] == REPO
         and plan["approval_state"] == "source_only_draft"
         and type(plan["plan_revision"]) is int and 1 <= plan["plan_revision"] <= 1000,
         "PLAN_IDENTITY_INVALID")
    expected = {"source_commit": SOURCE_COMMIT, "inputs": PINS, "project_name": "pcp-local",
                "layout": LAYOUT, "phases": PHASES}
    need(same(plan["expected"], expected), "EXPECTED_POLICY_DRIFT")
    observed = shape(plan["observed"], {"source", "layout", "environment", "extra_files",
        "effective_config", "inventory", "journal", "resources", "rollback"})
    parked = source_inputs(observed["source"])
    need(same(observed["environment"], {}), "ENVIRONMENT_OVERRIDE_UNSAFE")
    need(same(observed["extra_files"], []), "LEGACY_OR_EXTRA_FILES_UNSAFE")
    config = observed["effective_config"]
    if config is not None:
        # A submitted config must remain byte-policy equivalent to PARKED data,
        # never an approval of a renderer, ancillary images or active runtime.
        need(same(config, parked), "EFFECTIVE_CONFIG_NOT_PARKED")
    inventory = shape(observed["inventory"], INVENTORY)
    for key in sorted(INVENTORY):
        need(type(inventory[key]) is list and not inventory[key], "RESOURCE_COLLISION_OR_UNKNOWN")
    validate_layout(observed["layout"])
    validate_resources(observed["resources"])
    action = validate_journal(observed["journal"], plan["plan_revision"])
    validate_rollback(observed["rollback"])
    verification = {"source_binding": "SUBMITTED_PINS_ONLY", "checkout": "NOT_ATTESTED",
        "host": "NOT_ATTESTED", "oci": {"image_digest": None, "producer": None,
            "trust_root": None, "signature_verifier": None, "authenticated_provenance": "NOT_VERIFIED",
            "export_compatibility": "NOT_TESTED", "ancillary_images": None}, "enforcement_proof": None}
    need(same(plan["verification"], verification), "VERIFICATION_CLAIM_NOT_TRUSTED")
    authority = {"phase_permits": dict.fromkeys(PHASES), "host": False, "db": False,
                 "apply": False, "render": False, "start": False, "stop": False,
                 "rollback": False, "live": False}
    need(same(plan["authority"], authority), "HOST_AUTHORITY_NOT_APPROVED")
    return {"structure": "PASS", "source_binding": "SUBMITTED_PINS_ONLY",
            "checkout": "NOT_ATTESTED", "proposed_action": action, "blockers": list(BLOCKERS),
            "authenticated_provenance": "NOT_VERIFIED", "host": False, "db": False, "live": False,
            "result": "STOP", "reason": "HOST_EVIDENCE_NOT_ATTESTED"}


def inspect(plan):
    # Bound/type-check even pure dictionary callers, not only the CLI parser.
    try:
        return _inspect(parse(canonical(plan)))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, UnicodeError, yaml.YAMLError) as exc:
        raise Stop("EVIDENCE_SCHEMA_INVALID") from exc


def read_data(path):
    """Only the explicitly supplied data file; no symlink, FIFO, scan or reread."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            first = os.fstat(stream.fileno())
            need(stat.S_ISREG(first.st_mode) and first.st_size <= MAX_BYTES, "INPUT_FILE_UNSAFE")
            raw = stream.read(MAX_BYTES + 1)
            last = os.fstat(stream.fileno())
            need(len(raw) == first.st_size <= MAX_BYTES
                 and (first.st_size, first.st_mtime_ns, first.st_ctime_ns)
                 == (last.st_size, last.st_mtime_ns, last.st_ctime_ns), "INPUT_FILE_CHANGED")
            return raw
    except OSError as exc:
        raise Stop("INPUT_FILE_UNSAFE") from exc


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    structure, code = "NOT_CHECKED", "USAGE_SOURCE_ONLY"
    try:
        need(1 <= len(argv) <= 2 and argv[0] == "--check"
             and all(not a.startswith("-") for a in argv[1:]), "USAGE_SOURCE_ONLY")
        result = inspect(parse(read_data(argv[1] if len(argv) == 2 else EXAMPLE)))
        structure, code = result["structure"], result["reason"]
    except Stop as exc:
        code = str(exc)
    print("PCP_H1C_RESULT=STOP")
    print("PCP_H1C_REASON=" + code)
    print("PCP_H1C_STRUCTURE=" + structure)
    print("PCP_H1C_CHECKOUT=NOT_ATTESTED")
    print("PCP_H1C_PARKED_USER_HOME=MISMATCH_UNRESOLVED")
    print("PCP_H1C_OCI_PROVENANCE=NOT_VERIFIED")
    print("PCP_H1C_HOST_INSTALL=STOP")
    print("PCP_H1C_DB=STOP")
    print("PCP_H1C_LIVE=STOP")
    print("PCP_B22C1_LIVE=STOP")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
