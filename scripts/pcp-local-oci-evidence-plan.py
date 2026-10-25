#!/usr/bin/env python3
"""H1b3 bounded offline integrity inspection. NEVER authenticates or permits Host.

Only JSON (a YAML subset) plans and uncompressed USTAR OCI-layout envelopes are
supported. No extraction, subprocess, network, signature adapter or execution.
This deliberately narrow prospective profile is not a general OCI verifier.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "profiles/pcp-local/oci-evidence-plan.example.yml"
INDEX = "application/vnd.oci.image.index.v1+json"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"
CONFIG = "application/vnd.oci.image.config.v1+json"
LAYER = "application/vnd.oci.image.layer.v1.tar"
STATEMENT = "application/vnd.in-toto+json"
SLSA = "https://slsa.dev/provenance/v1"
SPDX = "https://spdx.dev/Document"
RECEIPT = "https://github.com/sonvhse06072/personal-coding-platform/attestations/source-input/v1"
BUILD_TYPE = "https://github.com/moby/buildkit/blob/master/docs/attestations/slsa-definitions.md"
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_BLOB = 8 * 1024 * 1024
MAX_EXPANDED = 16 * 1024 * 1024
MAX_JSON = 2 * 1024 * 1024
MAX_MEMBERS = 128
HEX = re.compile(r"[0-9a-f]{64}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
OUTPUTS = {"catalog", "index", "manifest", "config", "provenance", "sbom", "receipt"}
PHASES = {"PLAN_RO", "BUILD", "VERIFY", "ROLLBACK", "HEALTH"}
CAPS = {"cpu": 4, "memory_bytes": 4294967296, "disk_bytes": 6442450944,
        "egress_bytes": 2147483648, "deadline_seconds": 900,
        "enforcement": "NOT_IMPLEMENTED"}
INPUT_PINS = {
    "source_tar_sha256": "cb766b4845bcf77759f51e74041a4e0e379ab37a869eeb99bb0b682bdbcfc39b",
    "dockerfile_sha256": "bace204f3fae06449981d7e90a5bd90e789e456e5f2abee6bfb0856555aff70b",
    "ignore_sha256": "6e11a0630b755dcb3a5b027308ae0964642dc1d316217714388c4f843602af5e",
    "requirements_sha256": "63361fbbe8b76e25c080ff86954822301439c62a5ea5635f865001814ce49ff7",
    "app_tree_sha256": "33f73dd0064300d8a0945e81fa66c4ac7858999b9a3d685d33ba7b9ad12b1530",
    "base_image": "python:3.13.17-slim-bookworm@sha256:4cea12ab7d78a3312c85f8cab19b6971d4fe9704da25443986c0bc20a6678850",
}
WHEELS_SHA256 = "bbc489a27cc99939780a4ca19fee81cbd24c4a7d634bb2c715fdf95256ac496a"


class Stop(Exception):
    """Fixed redacted failure; never print untrusted evidence."""


def need(ok, code):
    if not ok:
        raise Stop(code)


def shape(obj, required, optional=()):
    need(type(obj) is dict and set(required) <= set(obj)
         and set(obj) <= set(required) | set(optional), "SCHEMA_INVALID")
    return obj


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def bounded_json(raw):
    need(type(raw) is bytes and len(raw) <= MAX_JSON, "JSON_RESOURCE_LIMIT")
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, "JSON_DUPLICATE_KEY")
            out[key] = value
        return out
    def constant(_):
        raise Stop("JSON_NUMBER_UNSAFE")
    try:
        obj = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Stop("JSON_INVALID") from exc
    nodes = 0
    def walk(value, depth=0):
        nonlocal nodes
        nodes += 1
        need(depth <= 24 and nodes <= 20000, "JSON_RESOURCE_LIMIT")
        if type(value) is dict:
            for key, child in value.items():
                need(len(key) <= 256, "JSON_RESOURCE_LIMIT")
                walk(child, depth + 1)
        elif type(value) is list:
            for child in value:
                walk(child, depth + 1)
        elif type(value) is str:
            need(len(value) <= 262144 and "\0" not in value, "JSON_RESOURCE_LIMIT")
        else:
            need(value is None or type(value) in (int, bool), "JSON_VALUE_UNSUPPORTED")
            if type(value) is int:
                need(abs(value) <= 2**63 - 1, "JSON_NUMBER_UNSAFE")
    walk(obj)
    return obj


def validate_plan(plan):
    shape(plan, {"schema_version", "project_id", "repository", "approval_state",
                 "expected", "observed", "verification", "authority", "prospective_caps"})
    need(type(plan["schema_version"]) is int and plan["schema_version"] == 1
         and plan["project_id"] == "pcp-local"
         and plan["repository"] == "sonvhse06072/personal-coding-platform"
         and plan["approval_state"] == "source_only_draft", "PLAN_AUTHORITY_INVALID")
    expected = shape(plan["expected"], {"inputs", "outputs"})
    inputs = shape(expected["inputs"], {"source_commit", "source_tar_sha256", "source_tar_bytes",
                   "source_members", "app_git_tree", "dockerfile_sha256", "ignore_sha256",
                   "requirements_sha256", "app_tree_sha256", "base_image", "wheels"})
    need(inputs["source_commit"] is None or (type(inputs["source_commit"]) is str
         and re.fullmatch(r"[0-9a-f]{40}", inputs["source_commit"])), "SOURCE_SHA_INVALID")
    for key in ("source_tar_sha256", "dockerfile_sha256", "ignore_sha256",
                "requirements_sha256", "app_tree_sha256"):
        need(type(inputs[key]) is str and HEX.fullmatch(inputs[key]), "INPUT_DIGEST_INVALID")
    need(inputs["source_tar_bytes"] == 1740800 and type(inputs["source_tar_bytes"]) is int
         and inputs["source_members"] == 103 and type(inputs["source_members"]) is int
         and inputs["app_git_tree"] == "314ceeddf4a9a3c39edb748e99e290d06b3e9188",
         "SOURCE_INVENTORY_INVALID")
    need(type(inputs["base_image"]) is str and re.fullmatch(
        r"python:3\.13\.17-slim-bookworm@sha256:[0-9a-f]{64}", inputs["base_image"]),
        "BASE_IMAGE_INVALID")
    wheels = inputs["wheels"]
    need(type(wheels) is list and len(wheels) == 18, "WHEEL_LEDGER_INVALID")
    names = set()
    for wheel in wheels:
        shape(wheel, {"name", "version", "sha256"})
        need(type(wheel["name"]) is str and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", wheel["name"])
             and wheel["name"] not in names and type(wheel["version"]) is str
             and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", wheel["version"])
             and type(wheel["sha256"]) is str and HEX.fullmatch(wheel["sha256"]),
             "WHEEL_LEDGER_INVALID")
        names.add(wheel["name"])
    need(all(inputs[key] == value for key, value in INPUT_PINS.items())
         and sha(canonical(wheels)) == "sha256:" + WHEELS_SHA256, "REVIEWED_INPUT_PIN_DRIFT")
    shape(expected["outputs"], OUTPUTS)
    for value in expected["outputs"].values():
        need(value is None or (type(value) is str and DIGEST.fullmatch(value)), "OUTPUT_PIN_INVALID")
    need(plan["observed"] == dict.fromkeys(OUTPUTS), "OBSERVATION_CANNOT_GRANT_TRUST")
    need(plan["verification"] == {"trust_root": None, "producer": None, "signature_verifier": None,
         "integrity": "NOT_CHECKED", "authenticated_provenance": "NOT_VERIFIED",
         "reproducibility": "NOT_TESTED"}, "TRUST_ROOT_UNAVAILABLE")
    need(canonical(plan["authority"]) == canonical({"phase_permits": dict.fromkeys(PHASES), "resource_owner": None,
         "host_allowed": False, "runtime_allowed": False, "live_allowed": False}),
         "HOST_AUTHORITY_UNAPPROVED")
    # bool == int must never smuggle a resource/authority claim.
    need(plan["prospective_caps"] == CAPS and all(type(plan["prospective_caps"][k]) is type(v)
         for k, v in CAPS.items()), "RESOURCE_ENFORCEMENT_UNAVAILABLE")
    return inputs


def safe_path(name):
    return (type(name) is str and 0 < len(name) <= 256 and "\\" not in name
            and "\0" not in name and not name.startswith("/")
            and all(ord(char) >= 32 and ord(char) != 127 for char in name)
            and all(part not in ("", ".", "..") for part in name.split("/")))


def tar_members(raw, *, layout=False):
    """Strict USTAR, regular members only, checked before any data copy.

    No tarfile extension processing, sparse expansion, extraction or links.
    Image layers with links/PAX are unsupported and STOP in this source profile.
    """
    need(type(raw) is bytes and len(raw) <= (MAX_ARCHIVE if layout else MAX_EXPANDED)
         and len(raw) % 512 == 0, "TAR_RESOURCE_OR_FORMAT")
    out, offset, total = {}, 0, 0
    while offset + 512 <= len(raw):
        header = raw[offset:offset + 512]
        if header == b"\0" * 512:
            need(len(raw) - offset >= 1024 and not any(raw[offset:]), "TAR_TRAILING_DATA")
            return out
        need(len(out) < MAX_MEMBERS, "TAR_MEMBER_LIMIT")
        need(header[257:263] == b"ustar\0" and header[263:265] == b"00"
             and header[156:157] in (b"0", b"\0") and not any(header[157:257])
             and not any(header[500:]), "TAR_TYPE_UNSUPPORTED")
        def octal(field):
            value = field.rstrip(b"\0 ").lstrip(b" ")
            need(bool(value) and re.fullmatch(rb"[0-7]+", value), "TAR_NUMBER_INVALID")
            return int(value, 8)
        checksum = octal(header[148:156])
        need(sum(header[:148]) + 8 * 32 + sum(header[156:]) == checksum, "TAR_CHECKSUM_INVALID")
        def text_field(field):
            name, _, padding = field.partition(b"\0")
            need(not any(padding), "TAR_PATH_INVALID")
            try:
                return name.decode("utf-8")
            except UnicodeError as exc:
                raise Stop("TAR_PATH_INVALID") from exc
        name, prefix = text_field(header[:100]), text_field(header[345:500])
        name = prefix + "/" + name if prefix else name
        need(safe_path(name) and name not in out, "TAR_PATH_OR_DUPLICATE")
        if layout:
            need(name in {"oci-layout", "index.json"}
                 or re.fullmatch(r"blobs/sha256/[0-9a-f]{64}", name), "LAYOUT_PATH_UNSUPPORTED")
        size = octal(header[124:136])
        total += size
        need(size <= (MAX_BLOB if layout else MAX_EXPANDED)
             and total <= (MAX_ARCHIVE if layout else MAX_EXPANDED), "TAR_RESOURCE_LIMIT")
        start, end = offset + 512, offset + 512 + size
        rounded = (end + 511) // 512 * 512
        need(rounded <= len(raw) and not any(raw[end:rounded]), "TAR_TRUNCATED_OR_PADDING")
        out[name] = raw[start:end]
        offset = rounded
    raise Stop("TAR_END_MISSING")


def expand_layer(raw, media):
    need(media in {LAYER, LAYER + "+gzip"}, "LAYER_COMPRESSION_UNSUPPORTED")
    if media == LAYER:
        need(len(raw) <= MAX_EXPANDED, "LAYER_RESOURCE_LIMIT")
        return raw
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        data = decoder.decompress(raw, MAX_EXPANDED + 1)
        need(len(data) <= MAX_EXPANDED and not decoder.unconsumed_tail, "LAYER_RESOURCE_LIMIT")
        need(decoder.eof and not decoder.unused_data, "LAYER_GZIP_INVALID")
        return data
    except zlib.error as exc:
        raise Stop("LAYER_GZIP_INVALID") from exc


def statement(raw, predicate, subject):
    obj = shape(bounded_json(raw), {"_type", "predicateType", "subject", "predicate"})
    need(obj["_type"] == "https://in-toto.io/Statement/v1"
         and obj["predicateType"] == predicate, "ATTESTATION_PREDICATE_INVALID")
    need(type(obj["subject"]) is list and len(obj["subject"]) == 1, "ATTESTATION_SUBJECT_INVALID")
    item = shape(obj["subject"][0], {"name", "digest"})
    need(type(item["name"]) is str and bool(item["name"])
         and item["digest"] == {"sha256": subject.removeprefix("sha256:")},
         "ATTESTATION_SUBJECT_INVALID")
    return obj["predicate"]


def provenance(obj, inputs):
    shape(obj, {"buildDefinition", "runDetails"})
    build = shape(obj["buildDefinition"], {"buildType", "externalParameters",
                                         "internalParameters", "resolvedDependencies"})
    need(build["buildType"] == BUILD_TYPE, "PROVENANCE_BUILD_TYPE_INVALID")
    ext = shape(build["externalParameters"], {"configSource", "request"})
    need(ext["configSource"] == {"path": "profiles/pcp-local/runtime/Dockerfile.inspect"},
         "PROVENANCE_RECIPE_INVALID")
    need(ext["request"] == {"frontend": "dockerfile.v0", "args": {},
         "locals": [{"name": "context"}, {"name": "dockerfile"}]}, "PROVENANCE_REQUEST_INVALID")
    internal = shape(build["internalParameters"], {"builderPlatform", "buildConfig"})
    config = shape(internal["buildConfig"], {"llbDefinition"})
    need(internal["builderPlatform"] == "linux/amd64" and type(config["llbDefinition"]) is list
         and 1 <= len(config["llbDefinition"]) <= 64, "PROVENANCE_MAX_DETAILS_MISSING")
    for step in config["llbDefinition"]:
        shape(step, {"id"}, {"inputs", "op"})
        need(type(step["id"]) is str and bool(step["id"]), "PROVENANCE_MAX_DETAILS_MISSING")
    deps = build["resolvedDependencies"]
    # A local TAR build does not automatically record Git or pip wheel inputs.
    need(deps == [{"uri": "pkg:docker/python@3.13.17-slim-bookworm?platform=linux%2Famd64",
                   "digest": {"sha256": inputs["base_image"].split("@sha256:")[1]}}],
         "PROVENANCE_BASE_MATERIAL_INVALID")
    run = shape(obj["runDetails"], {"builder", "metadata"})
    builder = shape(run["builder"], {"id"})
    need(type(builder["id"]) is str, "PROVENANCE_BUILDER_INVALID")
    meta = shape(run["metadata"], {"invocationId", "startedOn", "finishedOn",
                 "buildkit_reproducible", "buildkit_completeness", "buildkit_metadata"})
    for key in ("invocationId", "startedOn", "finishedOn"):
        need(type(meta[key]) is str and bool(meta[key]), "PROVENANCE_METADATA_INVALID")
    need(type(meta["buildkit_reproducible"]) is bool
         and meta["buildkit_completeness"] == {"request": True, "resolvedDependencies": False}
         and type(meta["buildkit_completeness"]["request"]) is bool
         and type(meta["buildkit_completeness"]["resolvedDependencies"]) is bool,
         "PROVENANCE_MAX_DETAILS_MISSING")
    details = shape(meta["buildkit_metadata"], {"source", "layers"})
    source = shape(details["source"], {"infos"})
    need(type(source["infos"]) is list and bool(source["infos"])
         and type(details["layers"]) is dict and bool(details["layers"]), "PROVENANCE_MAX_DETAILS_MISSING")
    for info in source["infos"]:
        shape(info, {"filename"}, {"data", "language"})
        need(info["filename"] == ext["configSource"]["path"], "PROVENANCE_RECIPE_INVALID")
    return details["layers"]


def sbom(obj, inputs):
    shape(obj, {"spdxVersion", "dataLicense", "SPDXID", "name", "documentNamespace",
                "creationInfo", "packages", "relationships"})
    need(obj["spdxVersion"] == "SPDX-2.3" and obj["dataLicense"] == "CC0-1.0"
         and obj["SPDXID"] == "SPDXRef-DOCUMENT", "SBOM_SCHEMA_INVALID")
    shape(obj["creationInfo"], {"creators", "created"})
    need(type(obj["packages"]) is list and 18 <= len(obj["packages"]) <= 256,
         "SBOM_PACKAGES_INVALID")
    packages, ids = {}, set()
    for package in obj["packages"]:
        shape(package, {"name", "versionInfo", "SPDXID"})
        name, identity = package["name"], package["SPDXID"]
        need(type(name) is str and name not in packages and type(identity) is str
             and identity.startswith("SPDXRef-") and identity not in ids
             and type(package["versionInfo"]) is str, "SBOM_PACKAGES_INVALID")
        packages[name] = package["versionInfo"]
        ids.add(identity)
    need(all(packages.get(w["name"]) == w["version"] for w in inputs["wheels"]),
         "SBOM_WHEEL_VERSION_MISMATCH")
    need(type(obj["relationships"]) is list and bool(obj["relationships"]), "SBOM_RELATIONSHIP_INVALID")
    described = set()
    for rel in obj["relationships"]:
        shape(rel, {"spdxElementId", "relationshipType", "relatedSpdxElement"})
        need(rel["spdxElementId"] == "SPDXRef-DOCUMENT" and rel["relationshipType"] == "DESCRIBES"
             and rel["relatedSpdxElement"] in ids, "SBOM_RELATIONSHIP_INVALID")
        described.add(rel["relatedSpdxElement"])
    need(described == ids, "SBOM_RELATIONSHIP_INVALID")


def _inspect(plan, archive):
    """Pure integrity result. Matching fixture data cannot create producer trust."""
    inputs = validate_plan(plan)
    files = tar_members(archive, layout=True)
    need("oci-layout" in files and "index.json" in files, "LAYOUT_INCOMPLETE")
    need(bounded_json(files["oci-layout"]) == {"imageLayoutVersion": "1.0.0"}, "LAYOUT_VERSION_INVALID")
    for name, raw in files.items():
        if name.startswith("blobs/"):
            need(sha(raw).split(":")[1] == name.split("/")[2], "BLOB_DIGEST_MISMATCH")
    used, active = set(), set()
    def blob(desc, media, *, platform=None, annotations=None):
        shape(desc, {"mediaType", "digest", "size"}, {"platform", "annotations"})
        need(desc["mediaType"] == media and type(desc["digest"]) is str
             and DIGEST.fullmatch(desc["digest"]) and type(desc["size"]) is int
             and 0 <= desc["size"] <= MAX_BLOB, "DESCRIPTOR_INVALID")
        need(desc.get("platform") == platform and desc.get("annotations") == annotations,
             "DESCRIPTOR_CROSSLINK_INVALID")
        path = "blobs/sha256/" + desc["digest"].split(":")[1]
        need(path in files, "BLOB_MISSING")
        raw = files[path]
        # Every immutable blob was hashed once above. Rehashing multi-MiB
        # layers for each repeated provenance reference would amplify CPU work.
        need(len(raw) == desc["size"], "BLOB_SIZE_OR_DIGEST_MISMATCH")
        need(path not in active, "GRAPH_CYCLE")
        used.add(path)
        return raw
    def index(raw):
        obj = shape(bounded_json(raw), {"schemaVersion", "mediaType", "manifests"})
        need(type(obj["schemaVersion"]) is int and obj["schemaVersion"] == 2
             and obj["mediaType"] == INDEX and type(obj["manifests"]) is list,
             "INDEX_SCHEMA_INVALID")
        return obj["manifests"]
    catalog = index(files["index.json"])
    # Distinct layout catalog -> selected image index -> exactly two manifests.
    need(len(catalog) == 1, "CATALOG_SELECTION_AMBIGUOUS")
    selected = blob(catalog[0], INDEX)
    active.add("blobs/sha256/" + sha(selected).split(":")[1])
    entries = index(selected)
    need(len(entries) == 2, "RUNTIME_OR_ATTESTATION_COUNT_INVALID")
    runtime = [d for d in entries if d.get("platform") == {"os": "linux", "architecture": "amd64"}]
    attests = [d for d in entries if d.get("platform") == {"os": "unknown", "architecture": "unknown"}]
    need(len(runtime) == len(attests) == 1, "RUNTIME_PLATFORM_INVALID")
    target = runtime[0]["digest"]
    image_raw = blob(runtime[0], MANIFEST, platform={"os": "linux", "architecture": "amd64"})
    def manifest(raw):
        obj = shape(bounded_json(raw), {"schemaVersion", "mediaType", "config", "layers"})
        need(type(obj["schemaVersion"]) is int and obj["schemaVersion"] == 2
             and obj["mediaType"] == MANIFEST and type(obj["layers"]) is list,
             "MANIFEST_SCHEMA_INVALID")
        return obj
    image = manifest(image_raw)
    config_raw = blob(image["config"], CONFIG)
    config = shape(bounded_json(config_raw), {"os", "architecture", "rootfs", "config"},
                   {"history", "created", "author"})
    need(config["os"] == "linux" and config["architecture"] == "amd64", "CONFIG_PLATFORM_INVALID")
    rootfs = shape(config["rootfs"], {"type", "diff_ids"})
    need(rootfs["type"] == "layers" and type(rootfs["diff_ids"]) is list
         and 1 <= len(image["layers"]) == len(rootfs["diff_ids"]) <= 32, "ROOTFS_INVALID")
    shape(config["config"], (), {"User", "Cmd", "Env", "WorkingDir", "Entrypoint",
                               "Labels", "ExposedPorts", "Volumes", "StopSignal"})
    layer_ids, layer_records, expanded_total = set(), {}, 0
    for desc, diff_id in zip(image["layers"], rootfs["diff_ids"]):
        raw = blob(desc, desc.get("mediaType"))
        expanded = expand_layer(raw, desc["mediaType"])
        expanded_total += len(expanded)
        need(expanded_total <= MAX_EXPANDED, "LAYER_RESOURCE_LIMIT")
        need(sha(expanded) == diff_id, "LAYER_DIFF_ID_MISMATCH")
        tar_members(expanded)
        layer_ids.add(desc["digest"])
        layer_records[desc["digest"]] = canonical(desc)
    att_raw = blob(attests[0], MANIFEST, platform={"os": "unknown", "architecture": "unknown"},
                   annotations={"vnd.docker.reference.type": "attestation-manifest",
                                "vnd.docker.reference.digest": target})
    att = manifest(att_raw)
    need(bounded_json(blob(att["config"], CONFIG)) == {}, "ATTESTATION_CONFIG_INVALID")
    need(len(att["layers"]) == 3, "ATTESTATION_SET_INCOMPLETE")
    evidence, evidence_ids = {}, {}
    for desc in att["layers"]:
        predicate = desc.get("annotations", {}).get("in-toto.io/predicate-type")
        need(predicate in {SLSA, SPDX, RECEIPT} and predicate not in evidence, "ATTESTATION_SET_INVALID")
        raw = blob(desc, STATEMENT, annotations={"in-toto.io/predicate-type": predicate})
        evidence[predicate] = statement(raw, predicate, target)
        evidence_ids[predicate] = desc["digest"]
    mappings = provenance(evidence[SLSA], inputs)
    # Validate max-mode layer mappings against real graph bytes, not a mode flag.
    mapped = set()
    for step, groups in mappings.items():
        need(type(step) is str and type(groups) is list and bool(groups), "PROVENANCE_LAYER_MAP_INVALID")
        for group in groups:
            need(type(group) is list and bool(group), "PROVENANCE_LAYER_MAP_INVALID")
            for desc in group:
                need(type(desc) is dict and desc.get("digest") in layer_records
                     and canonical(desc) == layer_records[desc["digest"]], "PROVENANCE_LAYER_MAP_INVALID")
                blob(desc, desc.get("mediaType"))
                mapped.add(desc["digest"])
    need(mapped == layer_ids, "PROVENANCE_LAYER_MAP_INVALID")
    sbom(evidence[SPDX], inputs)
    need(inputs["source_commit"] is not None, "SOURCE_AUTHORITY_NOT_PINNED")
    receipt = shape(evidence[RECEIPT], {"schema_version", "inputs", "provenance_digest", "sbom_digest"})
    need(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1
         and canonical(receipt["inputs"]) == canonical(inputs) and receipt["provenance_digest"] == evidence_ids[SLSA]
         and receipt["sbom_digest"] == evidence_ids[SPDX], "SOURCE_INPUT_LEDGER_MISMATCH")
    need(used == {name for name in files if name.startswith("blobs/")}, "GRAPH_UNREFERENCED_BLOB")
    observed = {"catalog": sha(files["index.json"]), "index": sha(selected),
                "manifest": target, "config": sha(config_raw),
                "provenance": evidence_ids[SLSA], "sbom": evidence_ids[SPDX], "receipt": evidence_ids[RECEIPT]}
    for name, pin in plan["expected"]["outputs"].items():
        need(pin is None or pin == observed[name], "OUTPUT_PIN_MISMATCH")
    return {"integrity": "PASS", "authenticated_provenance": "NOT_VERIFIED",
            "reproducibility": "NOT_TESTED", "observed": observed,
            "host_allowed": False, "runtime_allowed": False, "live_allowed": False,
            "result": "STOP", "reason": "TRUST_ROOT_UNAVAILABLE"}


def inspect(plan, archive):
    try:
        return _inspect(plan, archive)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise Stop("EVIDENCE_SCHEMA_INVALID") from exc


def read_data(path, limit):
    """Single open + fstat; no symlink/special file or post-hash path reread."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            need(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "INPUT_FILE_UNSAFE")
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            need(len(raw) == info.st_size <= limit and (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                 == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "INPUT_FILE_CHANGED")
            return raw
    except OSError as exc:
        raise Stop("INPUT_FILE_UNSAFE") from exc


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    integrity, code = "NOT_CHECKED", "EVIDENCE_NOT_SUPPLIED"
    try:
        need(1 <= len(argv) <= 3 and argv[0] == "--check"
             and all(not arg.startswith("-") for arg in argv[1:]), "USAGE_SOURCE_ONLY")
        plan = bounded_json(read_data(argv[1] if len(argv) > 1 else EXAMPLE, MAX_JSON))
        validate_plan(plan)
        if len(argv) == 3:
            result = inspect(plan, read_data(argv[2], MAX_ARCHIVE))
            integrity, code = result["integrity"], result["reason"]
    except Stop as exc:
        code = str(exc)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        code = "EVIDENCE_SCHEMA_INVALID"
    print("PCP_H1B3_RESULT=STOP")
    print("PCP_H1B3_REASON=" + code)
    print("PCP_H1B3_INTEGRITY=" + integrity)
    print("PCP_H1B3_AUTHENTICATED_PROVENANCE=NOT_VERIFIED")
    print("PCP_H1B3_REPRODUCIBILITY=NOT_TESTED")
    print("PCP_H1B3_HOST=NOT_AUTHORIZED")
    print("PCP_H1B3_RUNTIME=NOT_AUTHORIZED")
    print("PCP_B22C1_LIVE=STOP")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
