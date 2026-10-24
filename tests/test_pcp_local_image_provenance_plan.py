"""H1a offline provenance review: fake/static only; NEVER run Docker/Buildx."""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import runpy

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pcp-local-image-provenance-plan.py"
CONTRACT = ROOT / "profiles/pcp-local/image-provenance.example.yml"
COMPOSE = ROOT / "profiles/pcp-local/.ddev/docker-compose.platform.yaml"
PIN = "0.160.0"
HEAD = "a" * 40
BASE = "node:22-bookworm-slim@sha256:" + "b" * 64
ARTIFACT_DIGEST = "sha256:" + "c" * 64
TEST_DOCKERFILE = ("FROM " + BASE + "\nARG OPENCODE_VERSION=1.2.3\n").encode()
REQ = b"fastapi==0.116.1\n"
REQ_DEV = b"pytest==8.4.2\n"


@pytest.fixture
def plan():
    return runpy.run_path(str(SCRIPT))


@pytest.fixture
def manifest():
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


@pytest.fixture
def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def reason(fn, expected):
    with pytest.raises(Exception) as exc:
        fn()
    assert type(exc.value).__name__ == "Stop"
    assert str(exc.value) == expected


def evaluate(plan, manifest, compose, *, dockerfile=TEST_DOCKERFILE):
    return plan["assess"](
        manifest, head=HEAD, dockerfile=dockerfile, pinned_codex=PIN,
        requirements=REQ, requirements_dev=REQ_DEV, compose=compose,
    )


def complete_recipe(manifest, *, dockerfile=TEST_DOCKERFILE):
    m = deepcopy(manifest)
    m["source_commit"] = HEAD
    build = m["build"]
    build["base_image"] = BASE
    build["opencode_version"] = "1.2.3"
    build["dockerfile_sha256"] = hashlib.sha256(dockerfile).hexdigest()
    build["requirements_sha256"] = hashlib.sha256(REQ).hexdigest()
    build["requirements_dev_sha256"] = hashlib.sha256(REQ_DEV).hexdigest()
    return m


def complete_artifact(manifest):
    m = deepcopy(manifest)
    artifact = m["artifact"]
    artifact["image_ref"] = "pcp-local-runtime@" + ARTIFACT_DIGEST
    artifact["digest"] = ARTIFACT_DIGEST
    artifact["buildx_metadata_sha256"] = "d" * 64
    artifact["attestation_sha256"] = "e" * 64
    return m


def test_example_is_draft_and_never_auto_promotes(plan, manifest, compose):
    assert manifest["approval_state"] == "draft"
    assert manifest["source_commit"] is None
    assert manifest["build"]["base_image"] is None
    assert manifest["build"]["opencode_version"] is None
    assert all(v is None for v in manifest["artifact"].values())
    assert manifest["independent_provenance"] is None
    assert evaluate(plan, manifest, compose) == "SOURCE_AUTHORITY_NOT_PINNED"


def test_source_pinned_but_build_recipe_incomplete(plan, manifest, compose):
    manifest["source_commit"] = HEAD
    assert evaluate(plan, manifest, compose) == "BUILD_RECIPE_NOT_PINNED"


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("source_commit", "f" * 39, "SOURCE_COMMIT_INVALID"),
    ("source_commit", "b" * 40, "SOURCE_COMMIT_MISMATCH"),
    ("source_commit", 42, "SOURCE_COMMIT_INVALID"),
    ("source_commit", True, "SOURCE_COMMIT_INVALID"),
])
def test_manifest_source_identity_validation(
    plan, manifest, compose, field, value, expected,
):
    manifest[field] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("schema_version", True, "MANIFEST_SCHEMA_INVALID"),
    ("schema_version", 2, "MANIFEST_SCHEMA_INVALID"),
    ("project_id", "chonhac", "FOREIGN_IMAGE_PROJECT"),
    ("repository", "someone/foreign", "FOREIGN_IMAGE_PROJECT"),
    ("approval_state", "approved", "IMAGE_AUTHORITY_NOT_APPROVED"),
    ("approval_state", None, "IMAGE_AUTHORITY_NOT_APPROVED"),
])
def test_unauthorized_schema_or_authority_stops(
    plan, manifest, compose, field, value, expected,
):
    manifest[field] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("context", "../../other-project", "FOREIGN_BUILD_CONTEXT"),
    ("dockerfile", "/tmp/Dockerfile", "FOREIGN_BUILD_CONTEXT"),
    ("codex_version", "latest", "CODEX_VERSION_PIN_DRIFT"),
    ("codex_version", "0.159.0", "CODEX_VERSION_PIN_DRIFT"),
    ("base_image", "node:22-bookworm-slim", "BASE_IMAGE_NOT_DIGEST_PINNED"),
    ("base_image", "node:22-bookworm-slim@sha256:" + "0" * 64,
     "BASE_IMAGE_NOT_DIGEST_PINNED"),
    ("opencode_version", "latest", "OPENCODE_NOT_VERSION_PINNED"),
    ("opencode_version", "", "OPENCODE_NOT_VERSION_PINNED"),
    ("dockerfile_sha256", "bad", "HASH_FORMAT_UNSAFE"),
    ("requirements_sha256", True, "HASH_FORMAT_UNSAFE"),
])
def test_build_contract_rejects_mutable_unsafe_values(
    plan, manifest, compose, field, value, expected,
):
    manifest["build"][field] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("image_ref", "personal-coding-platform-coding-runtime:local",
     "UNSAFE_IMAGE_REFERENCE"),
    ("image_ref", "pcp-local-runtime:latest", "UNSAFE_IMAGE_REFERENCE"),
    ("image_ref", "pcp-local-runtime@sha256:" + "0" * 64,
     "UNSAFE_IMAGE_REFERENCE"),
    ("image_ref", "foreign@sha256:" + "f" * 64, "UNSAFE_IMAGE_REFERENCE"),
    ("digest", "sha256:bad", "DIGEST_FORMAT_UNSAFE"),
    ("digest", "sha256:" + "0" * 64, "DIGEST_FORMAT_UNSAFE"),
    ("buildx_metadata_sha256", "0" * 64, "HASH_FORMAT_UNSAFE"),
    ("attestation_sha256", "malformed", "HASH_FORMAT_UNSAFE"),
])
def test_artifact_never_accepts_legacy_mutable_or_unpinned(
    plan, manifest, compose, field, value, expected,
):
    manifest["artifact"][field] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


def test_digest_mismatch_stops(plan, manifest, compose):
    manifest["artifact"]["image_ref"] = (
        "pcp-local-runtime@sha256:" + "a" * 64
    )
    manifest["artifact"]["digest"] = ARTIFACT_DIGEST
    reason(
        lambda: evaluate(plan, manifest, compose),
        "IMAGE_DIGEST_MISMATCH",
    )


@pytest.mark.parametrize(("value", "expected"), [
    ({}, "INDEPENDENT_PROVENANCE_SHAPE_INVALID"),
    ({"verifier": "unreviewed", "statement_sha256": "f" * 64},
     "INDEPENDENT_PROVENANCE_SHAPE_INVALID"),
    ({"verifier": "independent", "statement_sha256": None},
     "INDEPENDENT_PROVENANCE_SHAPE_INVALID"),
    ("trusted", "INDEPENDENT_PROVENANCE_SHAPE_INVALID"),
])
def test_external_attestation_claim_shape_never_self_approves(
    plan, manifest, compose, value, expected,
):
    manifest["independent_provenance"] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


def test_current_legacy_recipe_still_requires_new_source_approval(
    plan, manifest, compose,
):
    doc = complete_recipe(manifest)
    current_dockerfile = (
        ROOT / "services/runtime/Dockerfile"
    ).read_bytes()
    doc["build"]["dockerfile_sha256"] = (
        hashlib.sha256(current_dockerfile).hexdigest()
    )
    assert evaluate(
        plan, doc, compose, dockerfile=current_dockerfile,
    ) == "DOCKERFILE_BASE_NOT_PINNED"


def test_explicit_latest_in_dockerfile_never_qualifies(
    plan, manifest, compose,
):
    raw = ("FROM " + BASE + "\nARG OPENCODE_VERSION=latest\n").encode()
    doc = complete_recipe(manifest, dockerfile=raw)
    assert evaluate(
        plan, doc, compose, dockerfile=raw,
    ) == "DOCKERFILE_OPENCODE_FLOATING"


def test_pinned_input_hash_drift_rejected(plan, manifest, compose):
    doc = complete_recipe(manifest)
    doc["build"]["dockerfile_sha256"] = "f" * 64
    reason(
        lambda: evaluate(plan, doc, compose),
        "BUILD_INPUT_DIGEST_DRIFT",
    )


def test_complete_recipe_without_artifact_stays_stop(plan, manifest, compose):
    assert evaluate(
        plan, complete_recipe(manifest), compose,
    ) == "ARTIFACT_DIGEST_NOT_ATTESTED"


def test_even_complete_claimed_artifact_requires_external_attestation(
    plan, manifest, compose,
):
    doc = complete_artifact(complete_recipe(manifest))
    assert evaluate(plan, doc, compose) == (
        "INDEPENDENT_ATTESTATION_NOT_VERIFIED"
    )
    doc["independent_provenance"] = {
        "verifier": "independent", "statement_sha256": "f" * 64,
    }
    assert evaluate(plan, doc, compose) == (
        "INDEPENDENT_ATTESTATION_NOT_VERIFIED"
    )


@pytest.mark.parametrize(("key", "value"), [
    ("profiles", []),
    ("image", "pcp-local-runtime:latest"),
    ("pull_policy", "always"),
    ("read_only", False),
    ("cap_drop", []),
])
def test_compose_tampering_stays_fail_closed(
    plan, manifest, compose, key, value,
):
    compose["services"]["coding-runtime"][key] = value
    reason(lambda: evaluate(plan, manifest, compose), "COMPOSE_NOT_PARKED")


@pytest.mark.parametrize("key", ["ports", "build", "privileged", "entrypoint"])
def test_compose_capability_expansion_refused(plan, manifest, compose, key):
    compose["services"]["coding-runtime"][key] = {"unsafe": True}
    reason(lambda: evaluate(plan, manifest, compose), "COMPOSE_UNSAFE")


def test_document_rejects_unclassified_extra_fields(plan, manifest, compose):
    manifest["silently_activate"] = True
    reason(lambda: evaluate(plan, manifest, compose), "MANIFEST_SCHEMA_INVALID")
    manifest.pop("silently_activate")
    manifest["artifact"]["unsafe"] = True
    reason(lambda: evaluate(plan, manifest, compose), "MANIFEST_SCHEMA_INVALID")


def test_source_plan_is_pure_and_no_host_tool_action():
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
    ]
    # A single allowlisted Git read helper; NEVER a docker/ddev/buildx process.
    assert len(calls) == 1
    assert '"git", "-C"' in source
    assert '"docker",' not in source
    assert '"ddev",' not in source
    assert '"buildx",' not in source
    assert "docker run" not in source
    assert "docker build" not in source
    assert "docker image rm" not in source
    assert "docker system prune" not in source
    assert "GIT_OPTIONAL_LOCKS" in source
    assert 'return 2' in source


def test_only_check_cli_supported_and_never_returns_success(plan, capsys):
    assert plan["main"](["--build"]) == 2
    s = capsys.readouterr().out
    assert "PCP_H1A_REASON=USAGE_SOURCE_ONLY" in s
    assert "PCP_H1A_IMAGE_BUILD=NOT_RUN" in s
    assert "PCP_H1A_CLEANUP=NOT_AUTHORIZED" in s
    assert "PCP_B22C1_LIVE=STOP" in s


def test_checked_in_scope_and_protected_classification():
    paths = [
        "scripts/pcp-local-image-provenance-plan.py",
        "profiles/pcp-local/image-provenance.example.yml",
        "profiles/pcp-local/.ddev/docker-compose.platform.yaml",
    ]
    p = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    assert all(p["classify_path"](x) == "protected" for x in paths)
    data = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert data["artifact"]["image_ref"] is None
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    assert services["coding-runtime"]["pull_policy"] == "never"
