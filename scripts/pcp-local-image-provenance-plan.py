#!/usr/bin/env python3
"""H1a PCP-local image provenance review, SOURCE ONLY.

No Docker/Buildx/DDEV/network requests, image writes, or worker activation.
A metadata/label assertion is not independently verified provenance.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "profiles/pcp-local/image-provenance.example.yml"
DOCKERFILE = ROOT / "services/runtime/Dockerfile"
PIN_FILE = ROOT / "config/tool-versions.env"
PROFILE = ROOT / "profiles/pcp-local/.ddev/docker-compose.platform.yaml"
REPO = "sonvhse06072/personal-coding-platform"
ORIGINS = {
    "https://github.com/sonvhse06072/personal-coding-platform.git",
    "git@github.com:sonvhse06072/personal-coding-platform.git",
}
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.]+)?$")
IMAGE = re.compile(r"^pcp-local-runtime@sha256:[0-9a-f]{64}$")
KEYS = {"schema_version", "project_id", "repository", "approval_state", "source_commit",
        "build", "artifact", "independent_provenance"}
BUILD_KEYS = {"context", "dockerfile", "dockerfile_sha256",
              "base_image", "codex_version", "opencode_version",
              "requirements_sha256", "requirements_dev_sha256"}
ARTIFACT_KEYS = {"image_ref", "digest", "buildx_metadata_sha256", "attestation_sha256"}
DANGEROUS_ENV = (
    "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH", "PCP_LOCAL_TASK_SOURCE_ENABLED",
    "PCP_LOCAL_TASK_WORKER_ENABLED", "PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION",
)


class Stop(Exception):
    """A fixed, redacted, auditable STOP reason."""


def require(test: bool, reason: str) -> None:
    if not test:
        raise Stop(reason)


def read_exact(path: Path, limit: int = 1024 * 1024) -> bytes:
    require(path.is_file() and not path.is_symlink(), "SOURCE_FILE_UNSAFE")
    require(path.resolve().is_relative_to(ROOT.resolve()), "SOURCE_FILE_OUTSIDE_PCP")
    raw = path.read_bytes()
    require(len(raw) <= limit and b"\x00" not in raw, "SOURCE_FILE_UNSAFE")
    return raw


def git_read(*args: str) -> str:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "-c", "core.fsmonitor=false",
             "-c", "core.hooksPath=/dev/null", *args],
            cwd=ROOT, env=env, text=True, capture_output=True,
            timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("SOURCE_GIT_NOT_VERIFIED") from exc
    require(completed.returncode == 0, "SOURCE_GIT_NOT_VERIFIED")
    return completed.stdout.strip()


def check_checkout() -> str:
    for key in DANGEROUS_ENV:
        require(not os.environ.get(key), "ENV_OVERRIDE_OR_ACTIVATION")
    require(os.geteuid() != 0, "ROOT_FORBIDDEN")
    require(git_read("rev-parse", "--show-toplevel") == str(ROOT),
            "WRONG_SOURCE_ROOT")
    require(git_read("remote", "get-url", "origin") in ORIGINS,
            "WRONG_SOURCE_ORIGIN")
    sha = git_read("rev-parse", "HEAD")
    require(bool(SHA.fullmatch(sha)), "SOURCE_SHA_INVALID")
    require(not git_read("status", "--porcelain=v1", "--untracked-files=normal"),
            "SOURCE_NOT_CLEAN")
    return sha


def document(data: Any) -> dict[str, Any]:
    require(type(data) is dict and set(data) == KEYS, "MANIFEST_SCHEMA_INVALID")
    require(data["schema_version"] == 1
            and type(data["schema_version"]) is int, "MANIFEST_SCHEMA_INVALID")
    require(data["project_id"] == "pcp-local" and data["repository"] == REPO,
            "FOREIGN_IMAGE_PROJECT")
    require(data["approval_state"] == "draft",
            "IMAGE_AUTHORITY_NOT_APPROVED")
    require(type(data["build"]) is dict
            and set(data["build"]) == BUILD_KEYS, "MANIFEST_SCHEMA_INVALID")
    require(type(data["artifact"]) is dict
            and set(data["artifact"]) == ARTIFACT_KEYS,
            "MANIFEST_SCHEMA_INVALID")
    require(data["build"]["context"] == "services/runtime"
            and data["build"]["dockerfile"] == "services/runtime/Dockerfile",
            "FOREIGN_BUILD_CONTEXT")
    return data


def validate_optional_digest(value: Any) -> bool:
    require(value is None or (type(value) is str
                             and bool(DIGEST.fullmatch(value))
                             and value != "sha256:" + "0" * 64),
            "DIGEST_FORMAT_UNSAFE")
    return value is not None


def validate_optional_sha(value: Any) -> bool:
    require(value is None or (type(value) is str
                             and bool(re.fullmatch(r"[a-f0-9]{64}", value))
                             and value != "0" * 64), "HASH_FORMAT_UNSAFE")
    return value is not None


def assess(
    doc: dict[str, Any], *,
    head: str, dockerfile: bytes, pinned_codex: str,
    requirements: bytes, requirements_dev: bytes, compose: dict[str, Any],
) -> str:
    """Pure negative-gate evaluation. NO return value authorizes execution."""
    d = document(doc)
    require(bool(SHA.fullmatch(head)), "SOURCE_SHA_INVALID")

    # Never let a caller turn an unreviewed manifest into Owner authority.
    source = d["source_commit"]
    require(source is None or
            (type(source) is str and bool(SHA.fullmatch(source))),
            "SOURCE_COMMIT_INVALID")
    if source is not None:
        require(source == head, "SOURCE_COMMIT_MISMATCH")

    b = d["build"]
    art = d["artifact"]
    require(type(pinned_codex) is str and bool(SEMVER.fullmatch(pinned_codex)),
            "CODEX_VERSION_PIN_INVALID")
    require(b["codex_version"] == pinned_codex, "CODEX_VERSION_PIN_DRIFT")

    for k in ("dockerfile_sha256", "requirements_sha256",
              "requirements_dev_sha256"):
        validate_optional_sha(b[k])
    for k in ("digest",):
        validate_optional_digest(art[k])
    for k in ("buildx_metadata_sha256", "attestation_sha256"):
        validate_optional_sha(art[k])

    base = b["base_image"]
    require(base is None or
            (type(base) is str
             and re.fullmatch(r"node:22-bookworm-slim@sha256:[a-f0-9]{64}", base)
             and base != "node:22-bookworm-slim@sha256:" + "0" * 64),
            "BASE_IMAGE_NOT_DIGEST_PINNED")
    opencode = b["opencode_version"]
    require(opencode is None or
            (type(opencode) is str and bool(SEMVER.fullmatch(opencode))),
            "OPENCODE_NOT_VERSION_PINNED")
    image_ref = art["image_ref"]
    require(image_ref is None or
            (type(image_ref) is str and bool(IMAGE.fullmatch(image_ref))
             and image_ref != "pcp-local-runtime@sha256:" + "0" * 64),
            "UNSAFE_IMAGE_REFERENCE")
    if image_ref is not None and art["digest"] is not None:
        require(image_ref.endswith(art["digest"]), "IMAGE_DIGEST_MISMATCH")

    identity = d["independent_provenance"]
    require(identity is None or (
            type(identity) is dict
            and set(identity) == {"verifier", "statement_sha256"}
            and identity["verifier"] == "independent"
            and validate_optional_sha(identity["statement_sha256"])),
            "INDEPENDENT_PROVENANCE_SHAPE_INVALID")

    # Legacy template must remain parked, with no default image pull. The exact
    # untrusted :local name must not be interpreted as satisfying image identity.
    require(type(compose) is dict and set(compose) == {"services"},
            "COMPOSE_POLICY_INVALID")
    services = compose["services"]
    require(type(services) is dict and set(services) == {"coding-runtime"},
            "COMPOSE_POLICY_INVALID")
    svc = services["coding-runtime"]
    require(svc.get("profiles") == ["pcp-inspect"]
            and svc.get("pull_policy") == "never"
            and svc.get("image") == "personal-coding-platform-coding-runtime:local"
            and svc.get("read_only") is True
            and svc.get("cap_drop") == ["ALL"]
            and svc.get("security_opt") == ["no-new-privileges:true"],
            "COMPOSE_NOT_PARKED")
    require("ports" not in svc and "build" not in svc
            and "privileged" not in svc and "entrypoint" not in svc,
            "COMPOSE_UNSAFE")

    # Completeness is NOT inferred from local OCI labels or metadata fields.
    if source is None:
        return "SOURCE_AUTHORITY_NOT_PINNED"
    if any(b[k] is None for k in ("dockerfile_sha256", "base_image",
                                 "opencode_version", "requirements_sha256",
                                 "requirements_dev_sha256")):
        return "BUILD_RECIPE_NOT_PINNED"

    expected = {
        "dockerfile_sha256": hashlib.sha256(dockerfile).hexdigest(),
        "requirements_sha256": hashlib.sha256(requirements).hexdigest(),
        "requirements_dev_sha256": hashlib.sha256(requirements_dev).hexdigest(),
    }
    require(all(b[k] == v for k, v in expected.items()),
            "BUILD_INPUT_DIGEST_DRIFT")

    # The current legacy Dockerfile is deliberately NOT rewritten by H1a.
    # A3 source reviewers may not claim its FROM/latest inputs are pinned.
    lines = dockerfile.decode("utf-8").splitlines()
    froms = [line.strip().removeprefix("FROM ").strip()
             for line in lines if line.startswith("FROM ")]
    require(froms == [base], "DOCKERFILE_BASE_NOT_PINNED")
    require(not any(line.strip() == "ARG OPENCODE_VERSION=latest"
                    for line in lines), "DOCKERFILE_OPENCODE_FLOATING")

    if any(art[k] is None for k in ARTIFACT_KEYS):
        return "ARTIFACT_DIGEST_NOT_ATTESTED"
    if identity is None:
        return "INDEPENDENT_ATTESTATION_NOT_VERIFIED"

    # Even complete locally reported hashes and a declared verifier need an
    # independently reviewed *external* provenance verification step. A build
    # label/metadata file is not cryptographic attestation or approval.
    return "INDEPENDENT_ATTESTATION_NOT_VERIFIED"


def main(argv: list[str]) -> int:
    try:
        require(argv == ["--check"], "USAGE_SOURCE_ONLY")
        head = check_checkout()
        raw = read_exact(MANIFEST)
        try:
            doc = yaml.safe_load(raw)
            compose = yaml.safe_load(read_exact(PROFILE))
        except yaml.YAMLError as exc:
            raise Stop("MANIFEST_YAML_INVALID") from exc
        version_lines = read_exact(PIN_FILE).decode("utf-8").splitlines()
        pins = [v.split("=", 1)[1] for v in version_lines
                if v.startswith("CODEX_VERSION=")]
        require(len(pins) == 1, "CODEX_VERSION_PIN_INVALID")
        reason = assess(
            doc, head=head, dockerfile=read_exact(DOCKERFILE),
            pinned_codex=pins[0],
            requirements=read_exact(ROOT / "services/runtime/requirements.txt"),
            requirements_dev=read_exact(ROOT / "services/runtime/requirements-dev.txt"),
            compose=compose,
        )
    except Stop as exc:
        reason = str(exc)
    except (OSError, UnicodeError, ValueError, TypeError):
        reason = "SOURCE_EVIDENCE_UNAVAILABLE"
    print("PCP_H1A_RESULT=STOP")
    print(f"PCP_H1A_REASON={reason}")
    print("PCP_H1A_IMAGE_PROVENANCE=NOT_INDEPENDENTLY_ATTESTED")
    print("PCP_H1A_LEGACY_LOCAL_TAG=NOT_AUTHORIZED_FOR_NEW_PCP")
    print("PCP_H1A_IMAGE_BUILD=NOT_RUN")
    print("PCP_H1A_DOCKER_MUTATION=NONE")
    print("PCP_H1A_HOST_INSTALL=NOT_AUTHORIZED")
    print("PCP_H1A_CLEANUP=NOT_AUTHORIZED")
    print("PCP_B22C1_LIVE=STOP")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
