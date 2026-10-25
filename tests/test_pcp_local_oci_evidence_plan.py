"""Adversarial synthetic data only; no Docker, network, keys or Host actions."""
from copy import deepcopy
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pcp-local-oci-evidence-plan.py"
EXAMPLE = ROOT / "profiles/pcp-local/oci-evidence-plan.example.yml"


@pytest.fixture
def tool():
    return runpy.run_path(str(SCRIPT))


@pytest.fixture
def plan():
    obj = json.loads(EXAMPLE.read_bytes())
    obj["expected"]["inputs"]["source_commit"] = "a" * 40  # explicitly fictitious
    return obj


def encode(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def envelope(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size = len(raw)
            item.mode = 0o644
            tar.addfile(item, io.BytesIO(raw))
    return out.getvalue()


def fixture(tool, plan, changes=None, compressed=False):
    """An internally consistent forgery still cannot authenticate a producer.

    Mutations run BEFORE digest generation so semantic negative cases cannot
    accidentally pass just because the fixture has an unrelated hash mismatch.
    """
    changes = changes or {}
    files = {"oci-layout": encode({"imageLayoutVersion": "1.0.0"})}
    def change(stage, obj):
        if stage in changes:
            changes[stage](obj)
        return obj
    def add(media, obj):
        raw = obj if type(obj) is bytes else encode(obj)
        digest = tool["sha"](raw)
        files["blobs/sha256/" + digest.split(":")[1]] = raw
        return {"mediaType": media, "digest": digest, "size": len(raw)}
    expanded = envelope({"app/main.py": b"# synthetic; never executed\n"})
    layer = add(tool["LAYER"] + ("+gzip" if compressed else ""),
                gzip.compress(expanded, mtime=0) if compressed else expanded)
    config = add(tool["CONFIG"], change("config", {
        "os": "linux", "architecture": "amd64", "config": {"User": "65532:65532"},
        "rootfs": {"type": "layers", "diff_ids": [tool["sha"](expanded)]}}))
    image = add(tool["MANIFEST"], change("image", {
        "schemaVersion": 2, "mediaType": tool["MANIFEST"], "config": config, "layers": [layer]}))
    inputs = deepcopy(plan["expected"]["inputs"])
    provenance = change("provenance", {
        "buildDefinition": {"buildType": tool["BUILD_TYPE"],
            "externalParameters": {"configSource": {"path": "profiles/pcp-local/runtime/Dockerfile.inspect"},
                "request": {"frontend": "dockerfile.v0", "args": {},
                            "locals": [{"name": "context"}, {"name": "dockerfile"}]}},
            "internalParameters": {"builderPlatform": "linux/amd64", "buildConfig": {
                "llbDefinition": [{"id": "step0"}, {"id": "step1", "inputs": ["step0:0"]}]}},
            "resolvedDependencies": [{"uri": "pkg:docker/python@3.13.17-slim-bookworm?platform=linux%2Famd64",
                "digest": {"sha256": inputs["base_image"].split("@sha256:")[1]}}]},
        "runDetails": {"builder": {"id": "synthetic-untrusted"}, "metadata": {
            "invocationId": "synthetic", "startedOn": "2026-10-25T00:00:00Z",
            "finishedOn": "2026-10-25T00:00:01Z", "buildkit_reproducible": False,
            "buildkit_completeness": {"request": True, "resolvedDependencies": False},
            "buildkit_metadata": {"source": {"infos": [{"filename": "profiles/pcp-local/runtime/Dockerfile.inspect"}]},
                                  "layers": {"step0:0": [[deepcopy(layer)]]}}}}})
    packages = [{"name": w["name"], "versionInfo": w["version"], "SPDXID": "SPDXRef-" + w["name"]}
                for w in inputs["wheels"]]
    spdx = change("sbom", {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT", "name": "synthetic", "documentNamespace": "https://fixture.invalid/sbom",
        "creationInfo": {"creators": ["Tool: synthetic"], "created": "2026-10-25T00:00:00Z"},
        "packages": packages, "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT",
             "relationshipType": "DESCRIBES", "relatedSpdxElement": p["SPDXID"]} for p in packages]})
    def attest(predicate_type, obj, stage):
        wrapped = change(stage, {"_type": "https://in-toto.io/Statement/v1", "predicateType": predicate_type,
            "subject": [{"name": "synthetic-image", "digest": {"sha256": image["digest"].split(":")[1]}}],
            "predicate": obj})
        return {**add(tool["STATEMENT"], wrapped), "annotations": {"in-toto.io/predicate-type": predicate_type}}
    prov = attest(tool["SLSA"], provenance, "provenance_statement")
    sbom = attest(tool["SPDX"], spdx, "sbom_statement")
    receipt = attest(tool["RECEIPT"], change("receipt", {"schema_version": 1, "inputs": inputs,
        "provenance_digest": prov["digest"], "sbom_digest": sbom["digest"]}), "receipt_statement")
    att = add(tool["MANIFEST"], change("attestation", {"schemaVersion": 2, "mediaType": tool["MANIFEST"],
        "config": add(tool["CONFIG"], {}), "layers": [prov, sbom, receipt]}))
    runtime = {**image, "platform": {"os": "linux", "architecture": "amd64"}}
    attestation = {**att, "platform": {"os": "unknown", "architecture": "unknown"}, "annotations": {
        "vnd.docker.reference.type": "attestation-manifest", "vnd.docker.reference.digest": image["digest"]}}
    selected = add(tool["INDEX"], change("index", {"schemaVersion": 2, "mediaType": tool["INDEX"],
                                                  "manifests": [runtime, attestation]}))
    files["index.json"] = encode(change("catalog", {"schemaVersion": 2, "mediaType": tool["INDEX"],
                                                   "manifests": [selected]}))
    change("files", files)
    return files


def stop(tool, plan, files, expected=None):
    with pytest.raises(tool["Stop"]) as exc:
        tool["inspect"](plan, envelope(files))
    if expected:
        assert str(exc.value) == expected
    return str(exc.value)


@pytest.mark.parametrize("compressed", [False, True])
def test_matching_forged_graph_integrity_pass_never_authenticity_or_host(tool, plan, compressed):
    result = tool["inspect"](plan, envelope(fixture(tool, plan, compressed=compressed)))
    assert result["integrity"] == "PASS"
    assert result["result"] == "STOP"
    assert result["authenticated_provenance"] == "NOT_VERIFIED"
    assert result["reproducibility"] == "NOT_TESTED"
    assert result["host_allowed"] is result["runtime_allowed"] is result["live_allowed"] is False
    observed = result["observed"]
    assert set(observed) == tool["OUTPUTS"]
    assert len(set(observed.values())) == 7  # catalog/index/manifest are different bytes
    plan["expected"]["outputs"] = observed
    assert tool["inspect"](plan, envelope(fixture(tool, plan, compressed=compressed)))["result"] == "STOP"


def test_checked_in_plan_has_no_outputs_root_or_per_phase_permissions(tool):
    plan = tool["bounded_json"](EXAMPLE.read_bytes())
    tool["validate_plan"](plan)
    assert plan["expected"]["inputs"]["source_commit"] is None
    assert not any(plan["observed"].values())
    assert not any(plan["authority"]["phase_permits"].values())
    assert plan["verification"]["trust_root"] is None


def test_reviewed_input_pins_match_actual_existing_recipe_lock_and_git_archive(tool):
    inputs = json.loads(EXAMPLE.read_bytes())["expected"]["inputs"]
    old = runpy.run_path(str(ROOT / "scripts/pcp-local-image-provenance-plan.py"))
    files = old["_read_git_inputs"](old["git_read"]("rev-parse", "HEAD"))
    for key, path in (("dockerfile_sha256", old["DOCKERFILE"]), ("requirements_sha256", old["LOCK"]),
                      ("ignore_sha256", old["IGNORE"])):
        assert inputs[key] == hashlib.sha256(files[str(path.relative_to(ROOT))]).hexdigest()
    app = {p.removeprefix("services/runtime/app/"): b for p, b in files.items() if p.startswith("services/runtime/app/")}
    assert old["app_digest"](app) == inputs["app_tree_sha256"]
    lock = files["profiles/pcp-local/runtime/requirements-inspect.lock"].decode()
    actual = [{"name": n.replace("[binary]", ""), "version": v, "sha256": d} for n, v, d in re.findall(
        r"^([a-z][a-z0-9-]*(?:\[binary\])?)==([0-9.]+) --hash=sha256:([0-9a-f]{64})$", lock, re.M)]
    assert inputs["wheels"] == actual


@pytest.mark.parametrize("stage,mutate,expected", [
    ("catalog", lambda x: x["manifests"].append(deepcopy(x["manifests"][0])), "CATALOG_SELECTION_AMBIGUOUS"),
    ("catalog", lambda x: x["manifests"][0].update(urls=["https://secret.invalid"]), "SCHEMA_INVALID"),
    ("catalog", lambda x: x["manifests"][0].update(size=1), "BLOB_SIZE_OR_DIGEST_MISMATCH"),
    ("catalog", lambda x: x["manifests"][0].update(size=True), "DESCRIPTOR_INVALID"),
    ("catalog", lambda x: x["manifests"][0].update(digest="sha256:" + "a" * 64), "BLOB_MISSING"),
    ("index", lambda x: x["manifests"][0]["platform"].update(architecture="arm64"), "RUNTIME_PLATFORM_INVALID"),
    ("index", lambda x: x["manifests"][1].update(platform={"os": "linux", "architecture": "amd64"}), "RUNTIME_PLATFORM_INVALID"),
    ("index", lambda x: x["manifests"].pop(), "RUNTIME_OR_ATTESTATION_COUNT_INVALID"),
    ("index", lambda x: x["manifests"][1]["annotations"].update({"vnd.docker.reference.digest": "sha256:" + "a" * 64}), "DESCRIPTOR_CROSSLINK_INVALID"),
    ("index", lambda x: x["manifests"][0].update(mediaType="application/vnd.oci.image.index.v1+json"), "DESCRIPTOR_INVALID"),
    ("config", lambda x: x.update(os="windows"), "CONFIG_PLATFORM_INVALID"),
    ("config", lambda x: x["rootfs"]["diff_ids"].append("sha256:" + "b" * 64), "ROOTFS_INVALID"),
    ("config", lambda x: x["rootfs"].update(diff_ids=["sha256:" + "b" * 64]), "LAYER_DIFF_ID_MISMATCH"),
    ("image", lambda x: x["layers"][0].update(mediaType="application/vnd.oci.image.layer.v1.tar+zstd"), "LAYER_COMPRESSION_UNSUPPORTED"),
    ("image", lambda x: x.update(subject={"digest": "sha256:" + "a" * 64}), "SCHEMA_INVALID"),
    ("attestation", lambda x: x["layers"].pop(), "ATTESTATION_SET_INCOMPLETE"),
    ("attestation", lambda x: x["layers"].append(deepcopy(x["layers"][0])), "ATTESTATION_SET_INCOMPLETE"),
    ("attestation", lambda x: x["layers"][1].update(annotations={"in-toto.io/predicate-type": "wrong"}), "ATTESTATION_SET_INVALID"),
    ("provenance_statement", lambda x: x["subject"][0].update(digest={"sha256": "a" * 64}), "ATTESTATION_SUBJECT_INVALID"),
    ("sbom_statement", lambda x: x["subject"].append(x["subject"][0]), "ATTESTATION_SUBJECT_INVALID"),
    ("receipt_statement", lambda x: x.update(predicateType="wrong"), "ATTESTATION_PREDICATE_INVALID"),
    ("provenance_statement", lambda x: x.update(trust_root="attacker"), "SCHEMA_INVALID"),
    ("provenance", lambda x: x["buildDefinition"].update(buildType="unknown"), "PROVENANCE_BUILD_TYPE_INVALID"),
    ("provenance", lambda x: x["buildDefinition"]["externalParameters"]["request"]["args"].update({"build-arg:TOKEN": "secret"}), "PROVENANCE_REQUEST_INVALID"),
    ("provenance", lambda x: x["buildDefinition"]["internalParameters"].pop("buildConfig"), "SCHEMA_INVALID"),
    ("provenance", lambda x: x["buildDefinition"]["internalParameters"]["buildConfig"].update(llbDefinition=[]), "PROVENANCE_MAX_DETAILS_MISSING"),
    ("provenance", lambda x: x["runDetails"]["metadata"]["buildkit_completeness"].update(request=False), "PROVENANCE_MAX_DETAILS_MISSING"),
    ("provenance", lambda x: x["runDetails"]["metadata"]["buildkit_metadata"].update(layers={}), "PROVENANCE_MAX_DETAILS_MISSING"),
    ("provenance", lambda x: x["runDetails"]["metadata"]["buildkit_metadata"]["layers"]["step0:0"][0][0].update(mediaType="wrong"), "PROVENANCE_LAYER_MAP_INVALID"),
    ("provenance", lambda x: x["buildDefinition"]["resolvedDependencies"][0]["digest"].update(sha256="b" * 64), "PROVENANCE_BASE_MATERIAL_INVALID"),
    ("provenance", lambda x: x.update(mode="max"), "SCHEMA_INVALID"),
    ("sbom", lambda x: x["packages"][0].update(versionInfo="0.0.0"), "SBOM_WHEEL_VERSION_MISMATCH"),
    ("sbom", lambda x: x["packages"].append(deepcopy(x["packages"][0])), "SBOM_PACKAGES_INVALID"),
    ("sbom", lambda x: x.update(relationships=[]), "SBOM_RELATIONSHIP_INVALID"),
    ("receipt", lambda x: x["inputs"].update(source_commit="b" * 40), "SOURCE_INPUT_LEDGER_MISMATCH"),
    ("receipt", lambda x: x["inputs"]["wheels"][0].update(sha256="b" * 64), "SOURCE_INPUT_LEDGER_MISMATCH"),
    ("receipt", lambda x: x.update(provenance_digest="sha256:" + "b" * 64), "SOURCE_INPUT_LEDGER_MISMATCH"),
    ("receipt", lambda x: x.update(sbom_digest="sha256:" + "b" * 64), "SOURCE_INPUT_LEDGER_MISMATCH"),
])
def test_semantic_substitutions_remain_stop_after_rehash(tool, plan, stage, mutate, expected):
    stop(tool, plan, fixture(tool, plan, {stage: mutate}), expected)


@pytest.mark.parametrize("field", ["source_tar_sha256", "dockerfile_sha256", "ignore_sha256",
                                  "requirements_sha256", "app_tree_sha256"])
def test_caller_cannot_replace_reviewed_input_pins(tool, plan, field):
    files = fixture(tool, plan)
    plan["expected"]["inputs"][field] = "a" * 64
    stop(tool, plan, files, "REVIEWED_INPUT_PIN_DRIFT")


@pytest.mark.parametrize("section,key,value,expected", [
    ("verification", "trust_root", "artifact-key", "TRUST_ROOT_UNAVAILABLE"),
    ("verification", "signature_verifier", "fake-pass", "TRUST_ROOT_UNAVAILABLE"),
    ("verification", "authenticated_provenance", "PASS", "TRUST_ROOT_UNAVAILABLE"),
    ("verification", "reproducibility", "PASS", "TRUST_ROOT_UNAVAILABLE"),
    ("observed", "manifest", "sha256:" + "a" * 64, "OBSERVATION_CANNOT_GRANT_TRUST"),
    ("authority", "host_allowed", True, "HOST_AUTHORITY_UNAPPROVED"),
    ("authority", "host_allowed", 0, "HOST_AUTHORITY_UNAPPROVED"),
    ("authority", "runtime_allowed", True, "HOST_AUTHORITY_UNAPPROVED"),
    ("authority", "live_allowed", True, "HOST_AUTHORITY_UNAPPROVED"),
    ("authority", "resource_owner", "fake-builder-owner", "HOST_AUTHORITY_UNAPPROVED"),
    ("prospective_caps", "enforcement", "ENFORCED", "RESOURCE_ENFORCEMENT_UNAVAILABLE"),
    ("prospective_caps", "disk_bytes", 2**50, "RESOURCE_ENFORCEMENT_UNAVAILABLE"),
    ("prospective_caps", "cpu", True, "RESOURCE_ENFORCEMENT_UNAVAILABLE"),
    ("prospective_caps", "egress_bytes", 0, "RESOURCE_ENFORCEMENT_UNAVAILABLE"),
    ("prospective_caps", "deadline_seconds", 1800, "RESOURCE_ENFORCEMENT_UNAVAILABLE"),
])
def test_untrusted_success_ownership_and_resource_claims_cannot_authorize(tool, plan, section, key, value, expected):
    files = fixture(tool, plan)
    plan[section][key] = value
    stop(tool, plan, files, expected)


@pytest.mark.parametrize("phase", ["PLAN_RO", "BUILD", "VERIFY", "ROLLBACK", "HEALTH"])
@pytest.mark.parametrize("permit", [True, {"owner": "fake", "expires": "2000-01-01", "approved": True}])
def test_every_phase_unapproved_even_with_fake_or_expired_permit(tool, plan, phase, permit):
    files = fixture(tool, plan)
    plan["authority"]["phase_permits"][phase] = permit
    stop(tool, plan, files, "HOST_AUTHORITY_UNAPPROVED")


def test_missing_corrupt_extra_duplicate_json_and_output_confusion(tool, plan):
    files = fixture(tool, plan)
    blob = next(name for name in files if name.startswith("blobs/"))
    stop(tool, plan, {**files, blob: files[blob] + b"corrupt"}, "BLOB_DIGEST_MISMATCH")
    missing = dict(files)
    del missing[blob]
    stop(tool, plan, missing, "BLOB_MISSING")
    extra = b"{}"
    stop(tool, plan, {**files, "blobs/sha256/" + tool["sha"](extra).split(":")[1]: extra + b" "}, "BLOB_DIGEST_MISMATCH")
    extra = b"unreferenced"
    stop(tool, plan, {**files, "blobs/sha256/" + tool["sha"](extra).split(":")[1]: extra}, "GRAPH_UNREFERENCED_BLOB")
    stop(tool, plan, {**files, "index.json": b'{"schemaVersion":2,"schemaVersion":2}'}, "JSON_DUPLICATE_KEY")
    observed = tool["inspect"](plan, envelope(files))["observed"]
    plan["expected"]["outputs"]["manifest"] = observed["index"]
    stop(tool, plan, files, "OUTPUT_PIN_MISMATCH")


@pytest.mark.parametrize("raw,expected", [
    (b'{"a":1,"a":2}', "JSON_DUPLICATE_KEY"),
    (b'{"x":NaN}', "JSON_NUMBER_UNSAFE"),
    (b'{"x":Infinity}', "JSON_NUMBER_UNSAFE"),
    (b'{"x":1.5}', "JSON_VALUE_UNSUPPORTED"),
    (b'[' * 30 + b'0' + b']' * 30, "JSON_RESOURCE_LIMIT"),
    (b'"' + b'a' * 262145 + b'"', "JSON_RESOURCE_LIMIT"),
    (b'"\\u0000"', "JSON_RESOURCE_LIMIT"),
    (b'\xff', "JSON_INVALID"),
])
def test_json_fail_closed_before_schema(tool, raw, expected):
    with pytest.raises(tool["Stop"], match=expected):
        tool["bounded_json"](raw)


@pytest.mark.parametrize("name,kind", [
    ("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
    ("blobs/../escape", tarfile.REGTYPE), ("./index.json", tarfile.REGTYPE),
    ("foreign\\index.json", tarfile.REGTYPE), ("index.json", tarfile.SYMTYPE),
    ("index.json", tarfile.LNKTYPE), ("index.json", tarfile.CHRTYPE),
    ("index.json", tarfile.DIRTYPE), ("index.json", tarfile.GNUTYPE_SPARSE),
    ("index.json", tarfile.XHDTYPE), ("index.json", tarfile.XGLTYPE),
])
def test_layout_paths_links_devices_extensions_never_extracted(tool, name, kind):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        item = tarfile.TarInfo(name)
        item.type = kind
        item.linkname = "foreign" if kind in (tarfile.LNKTYPE, tarfile.SYMTYPE) else ""
        tar.addfile(item)
    with pytest.raises(tool["Stop"]):
        tool["tar_members"](output.getvalue(), layout=True)


def test_tar_duplicate_truncated_padding_compressed_and_bomb_limits(tool):
    raw = envelope({"index.json": b"{}"})
    # First member is exactly 1024 bytes; concatenate duplicate before end.
    for bad in (raw[:1024] * 2 + raw[1024:], raw[:-1], raw[:512],
                raw[:-512] + b"x" * 512, gzip.compress(raw)):
        with pytest.raises(tool["Stop"]):
            tool["tar_members"](bad, layout=True)
    fn = tool["tar_members"]
    fn.__globals__["MAX_MEMBERS"] = 1
    with pytest.raises(tool["Stop"], match="TAR_MEMBER_LIMIT"):
        fn(envelope({"oci-layout": b"{}", "index.json": b"{}"}), layout=True)
    fn.__globals__["MAX_ARCHIVE"] = 100
    with pytest.raises(tool["Stop"], match="TAR_RESOURCE_OR_FORMAT"):
        fn(raw, layout=True)


def test_gzip_trailing_concatenated_truncated_and_decompression_bomb(tool):
    raw = gzip.compress(b"x" * 4096)
    fn = tool["expand_layer"]
    for bad in (raw + b"trailing", raw + raw, raw[:-8]):
        with pytest.raises(tool["Stop"], match="LAYER_GZIP_INVALID"):
            fn(bad, tool["LAYER"] + "+gzip")
    fn.__globals__["MAX_EXPANDED"] = 1024
    with pytest.raises(tool["Stop"], match="LAYER_RESOURCE_LIMIT"):
        fn(raw, tool["LAYER"] + "+gzip")


def test_cli_critical_cases_always_exit_two_redacted_and_no_effect(tool, plan, tmp_path, capsys):
    p, archive = tmp_path / "plan.json", tmp_path / "layout.tar"
    p.write_bytes(encode(plan))
    archive.write_bytes(envelope(fixture(tool, plan)))
    for args in ([], ["--build"], ["--verify", "--trust-root", "fake"], ["--check"],
                 ["--check", str(p), str(archive)]):
        assert tool["main"](args) == 2
        out = capsys.readouterr().out
        assert "PCP_H1B3_RESULT=STOP" in out
        assert "PCP_H1B3_AUTHENTICATED_PROVENANCE=NOT_VERIFIED" in out
        assert "PCP_H1B3_REPRODUCIBILITY=NOT_TESTED" in out
        assert "PCP_H1B3_HOST=NOT_AUTHORIZED" in out
        assert "PCP_B22C1_LIVE=STOP" in out
    archive.write_bytes(b"secret-fixture-do-not-print")
    assert tool["main"](["--check", str(p), str(archive)]) == 2
    assert "secret-fixture-do-not-print" not in capsys.readouterr().out
    link = tmp_path / "link"
    link.symlink_to(p)
    assert tool["main"](["--check", str(link)]) == 2
    assert "INPUT_FILE_UNSAFE" in capsys.readouterr().out
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(tool["Stop"], match="INPUT_FILE_UNSAFE"):
        tool["read_data"](fifo, 100)
    with pytest.raises(tool["Stop"], match="INPUT_FILE_UNSAFE"):
        tool["read_data"](p, 1)


def test_no_network_subprocess_trust_adapter_and_all_new_paths_protected():
    tree = ast.parse(SCRIPT.read_text())
    imports = {alias.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names}
    imports |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"subprocess", "socket", "urllib", "requests", "httpx", "ctypes", "ssl", "importlib"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"exec", "eval", "__import__"} for n in ast.walk(tree))
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    for path in (SCRIPT, EXAMPLE, ROOT / "docs/pcp-portable/h1b3-oci-evidence-plan.md"):
        assert policy["classify_path"](str(path.relative_to(ROOT))) == "protected"


def test_read_detects_changed_file_without_rereading_path(tool, tmp_path, monkeypatch):
    path = tmp_path / "data"
    path.write_bytes(b"{}")
    original, seen = os.fstat, []
    def race(fd):
        info = original(fd)
        seen.append(fd)
        if len(seen) == 1:
            path.write_bytes(b"{\"changed\":true}")
        return info
    monkeypatch.setattr(os, "fstat", race)
    with pytest.raises(tool["Stop"], match="INPUT_FILE_CHANGED"):
        tool["read_data"](path, 100)
    assert len(set(seen)) == 1


def test_json_and_tar_declared_size_caps_no_large_allocation(tool):
    tool["bounded_json"].__globals__["MAX_JSON"] = 2
    with pytest.raises(tool["Stop"], match="JSON_RESOURCE_LIMIT"):
        tool["bounded_json"](b"{} ")
    raw = bytearray(envelope({"index.json": b"{}"}))
    raw[124:136] = b"77777777777\0"
    raw[148:156] = b"        "
    raw[148:156] = ("%06o\0 " % sum(raw[:512])).encode()
    with pytest.raises(tool["Stop"], match="TAR_RESOURCE_LIMIT"):
        tool["tar_members"](bytes(raw), layout=True)
