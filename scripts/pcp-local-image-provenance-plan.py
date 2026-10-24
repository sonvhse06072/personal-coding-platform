#!/usr/bin/env python3
"""H1b2 candidate PCP-local image provenance review, SOURCE ONLY.

No Docker/Buildx/DDEV/network requests, image writes, or worker activation.
A metadata/label assertion is not independently verified provenance.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "profiles/pcp-local/image-provenance.example.yml"
DOCKERFILE = ROOT / "profiles/pcp-local/runtime/Dockerfile.inspect"
LOCK = ROOT / "profiles/pcp-local/runtime/requirements-inspect.lock"
IGNORE = ROOT / "profiles/pcp-local/runtime/Dockerfile.inspect.dockerignore"
BASE_IMAGE = "python:3.13.17-slim-bookworm@sha256:4cea12ab7d78a3312c85f8cab19b6971d4fe9704da25443986c0bc20a6678850"
APP = ROOT / "services/runtime/app"
PROFILE = ROOT / "profiles/pcp-local/.ddev/docker-compose.platform.yaml"
REPO = "sonvhse06072/personal-coding-platform"
ORIGINS = {
    "https://github.com/sonvhse06072/personal-coding-platform.git",
    "git@github.com:sonvhse06072/personal-coding-platform.git",
}
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE = re.compile(r"^pcp-local-runtime-inspect@sha256:[0-9a-f]{64}$")
PARKED_IMAGE = "pcp-local-runtime-inspect:source-unresolved-do-not-run"
PARKED_COMMAND = ["/PCP_H1B_SOURCE_ONLY_NOT_AUTHORIZED"]
KEYS = {"schema_version", "project_id", "repository", "approval_state", "source_commit",
        "build", "artifact", "evidence", "independent_provenance"}
BUILD_KEYS = {"context", "dockerfile", "requirements", "platform", "startup_mode",
              "dockerfile_sha256", "base_image", "requirements_sha256", "app_tree_sha256",
              "context_ignore", "context_ignore_sha256"}
ARTIFACT_KEYS = {"image_ref", "digest", "config_digest", "buildx_metadata_sha256",
                 "attestation_sha256", "sbom_sha256"}
EVIDENCE_KEYS = {"exporter", "image_store", "provenance_mode", "sbom_required"}
PROVENANCE_KEYS = {"verifier", "statement_sha256", "subject_digest", "source_commit",
                   "dockerfile_sha256", "requirements_sha256", "app_tree_sha256", "context_ignore_sha256"}
# Exact reviewed instruction policy: no appended RUN/COPY/ENTRYPOINT escape.
RECIPE = (
    "FROM --platform=linux/amd64 " + BASE_IMAGE,
    "WORKDIR /app",
    "COPY profiles/pcp-local/runtime/requirements-inspect.lock /app/requirements-inspect.lock",
    "RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r /app/requirements-inspect.lock",
    "COPY services/runtime/app /app/app",
    "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PCP_RUNTIME_STARTUP_MODE=pcp_local_inspect PROJECTS_FILE=/config/projects.pcp-local.yml PROJECT_BASELINES_FILE=/config/project-baselines.pcp-local.yml HOME=/tmp",
    "USER 65532:65532",
    'CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8787", "--loop", "asyncio", "--http", "h11", "--ws", "none", "--lifespan", "on", "--no-access-log"]',
)
DIRECT_PACKAGES = {"fastapi", "uvicorn", "pydantic", "pyyaml", "httpx", "psycopg[binary]"}
# Candidate closure only; syntax checks NEVER assert resolver/wheel availability.
LOCK_PACKAGES = DIRECT_PACKAGES | {
    "annotated-types", "anyio", "certifi", "click", "h11", "httpcore", "idna",
    "psycopg-binary", "pydantic-core", "starlette", "typing-extensions", "typing-inspection",
}
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
    require(type(data["schema_version"]) is int and data["schema_version"] == 3,
            "MANIFEST_SCHEMA_INVALID")
    require(data["project_id"] == "pcp-local" and data["repository"] == REPO,
            "FOREIGN_IMAGE_PROJECT")
    require(data["approval_state"] == "draft", "IMAGE_AUTHORITY_NOT_APPROVED")
    for key, keys in (("build", BUILD_KEYS), ("artifact", ARTIFACT_KEYS),
                      ("evidence", EVIDENCE_KEYS)):
        require(type(data[key]) is dict and set(data[key]) == keys,
                "MANIFEST_SCHEMA_INVALID")
    build = data["build"]
    require(build["context"] == "."
            and build["dockerfile"] == DOCKERFILE.relative_to(ROOT).as_posix()
            and build["requirements"] == LOCK.relative_to(ROOT).as_posix()
            and build["context_ignore"] == IGNORE.relative_to(ROOT).as_posix(),
            "FOREIGN_BUILD_CONTEXT")
    require(build["platform"] == "linux/amd64", "BUILD_PLATFORM_UNSAFE")
    require(build["startup_mode"] == "pcp_local_inspect", "STARTUP_MODE_UNSAFE")
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


def validate_profile(compose: Any) -> None:
    require(type(compose) is dict and set(compose) == {"services"},
            "COMPOSE_POLICY_INVALID")
    services = compose["services"]
    require(type(services) is dict and set(services) == {"coding-runtime"},
            "COMPOSE_POLICY_INVALID")
    expected = {
        "image": PARKED_IMAGE, "command": PARKED_COMMAND, "pull_policy": "never",
        "container_name": "ddev-${DDEV_SITENAME}-coding-runtime",
        "profiles": ["pcp-inspect"], "restart": "no",
        "user": "${DDEV_UID}:${DDEV_GID}", "read_only": True,
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "environment": {
            "PCP_RUNTIME_STARTUP_MODE": "pcp_local_inspect",
            "PROJECTS_FILE": "/config/projects.pcp-local.yml",
            "PROJECT_BASELINES_FILE": "/config/project-baselines.pcp-local.yml",
            "HOME": "/home/coder", "PYTHONDONTWRITEBYTECODE": "1",
        },
        "volumes": [
            {"type": "bind", "source": "${DDEV_APPROOT}/config/" + name,
             "target": "/config/" + name, "read_only": True}
            for name in ("projects.pcp-local.yml", "project-baselines.pcp-local.yml")
        ],
        "tmpfs": ["/tmp:rw,nosuid,nodev,size=67108864"],
    }
    svc = services["coding-runtime"]
    require(type(svc) is dict and set(svc) == set(expected), "COMPOSE_UNSAFE")
    # Equality alone accepts YAML integers in place of bools; compare types too.
    require(svc == expected and type(svc["read_only"]) is bool
            and all(type(v.get("read_only")) is bool for v in svc["volumes"]),
            "COMPOSE_NOT_PARKED")


def validate_lock(raw: bytes) -> bool:
    """Only validate offline syntax; unresolved drafts are explicitly parked."""
    lines = [v.strip() for v in raw.decode("utf-8").replace("\\\n", " ").splitlines()
             if v.strip() and not v.lstrip().startswith("#")]
    require(lines[:2] == ["--require-hashes", "--only-binary=:all:"],
            "DEPENDENCY_LOCK_UNSAFE")
    seen = set()
    complete = True
    for line in lines[2:]:
        match = re.fullmatch(
            r"([A-Za-z0-9_-]+(?:\[binary\])?)==([0-9]+(?:\.[0-9]+){1,3})"
            r"((?: +--hash=sha256:[a-f0-9]{64})*)", line,
        )
        require(match is not None, "DEPENDENCY_LOCK_UNSAFE")
        name = match[1].lower().replace("_", "-")
        require(name in LOCK_PACKAGES and name not in seen, "DEPENDENCY_LOCK_UNSAFE")
        seen.add(name)
        hashes = re.findall(r"--hash=sha256:([a-f0-9]{64})", match[3])
        for value in hashes:
            validate_optional_sha(value)
        complete = complete and bool(hashes)
    require(DIRECT_PACKAGES <= seen, "DEPENDENCY_LOCK_UNSAFE")
    return complete and seen == LOCK_PACKAGES


def app_inputs() -> dict[str, bytes]:
    """Read only committed Python package inputs; reject symlinks/extra payloads."""
    require(APP.is_dir() and not APP.is_symlink(), "SOURCE_FILE_UNSAFE")
    inputs = {}
    for path in sorted(APP.rglob("*")):
        require(not path.is_symlink(), "SOURCE_FILE_UNSAFE")
        # Python may create these during local tests; they are not image inputs.
        require("__pycache__" not in path.parts, "APP_GENERATED_INPUT_UNSAFE")
        if path.is_file():
            require(path.suffix == ".py", "APP_NON_PYTHON_INPUT_UNSAFE")
            inputs[path.relative_to(APP).as_posix()] = read_exact(path)
    require("main.py" in inputs and "__init__.py" in inputs, "APP_INPUTS_INCOMPLETE")
    return inputs


def app_digest(inputs: dict[str, bytes]) -> str:
    # Canonical path NUL content-sha256 LF, sorted by relative POSIX path.
    content = "".join(name + "\0" + hashlib.sha256(raw).hexdigest() + "\n"
                      for name, raw in sorted(inputs.items()))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def context_paths(raw: bytes) -> set[str]:
    """Restricted Docker ignore policy: deny **, then literal file exceptions.

    General Docker glob semantics are deliberately not reimplemented. This
    subset was compared to pinned upstream Moby; source staging is mandatory
    defense in depth, so the future builder never receives the repository.
    """
    lines = [line for line in raw.decode("utf-8").splitlines()
             if line and not line.startswith("#")]
    require(lines and lines[0] == "**", "CONTEXT_NOT_DENY_BY_DEFAULT")
    paths = set()
    exceptions = [line for line in lines[1:] if line.startswith("!")]
    for line in exceptions:
        path = line[1:]
        require(bool(re.fullmatch(r"[A-Za-z0-9_./-]+", path))
                and all(part not in {"", ".", "..", "__pycache__"}
                        and not part.startswith(".") for part in path.split("/")),
                "CONTEXT_PATTERN_UNSAFE")
        require(path not in paths, "CONTEXT_PATTERN_UNSAFE")
        require(path in {DOCKERFILE.relative_to(ROOT).as_posix(), LOCK.relative_to(ROOT).as_posix()}
                or (path.startswith("services/runtime/app/") and path.endswith(".py")),
                "CONTEXT_FOREIGN_INPUT")
        paths.add(path)
    require({DOCKERFILE.relative_to(ROOT).as_posix(), LOCK.relative_to(ROOT).as_posix(),
             "services/runtime/app/main.py", "services/runtime/app/__init__.py"} <= paths,
            "CONTEXT_INPUTS_INCOMPLETE")
    # Moby matches parent exceptions too. Explicit child denials prevent a
    # reviewed filename replaced by a directory from exposing its descendants.
    require(lines == ["**"] + ["!" + path for path in sorted(paths)]
            + [path + "/*" for path in sorted(paths)], "CONTEXT_PATTERN_UNSAFE")
    # No allowed file can also be a parent directory, which Moby would allow
    # descendants through. Reject file/directory ambiguity before staging.
    require(not any(parent.startswith(path + "/") for path in paths for parent in paths),
            "CONTEXT_FILE_DIRECTORY_COLLISION")
    return paths


def source_context(*, dockerfile: bytes, requirements: bytes,
                   context_ignore: bytes, inputs: dict[str, bytes]) -> bytes:
    """Create a deterministic source-only TAR IN MEMORY; never write/build/run.

    A later separately approved Host wrapper must send ONLY these bytes. It may
    not pass root '.', alternate contexts, symlinks, Git data or host paths.
    """
    allowed = context_paths(context_ignore)
    payload = {"services/runtime/app/" + path: raw for path, raw in inputs.items()}
    payload[DOCKERFILE.relative_to(ROOT).as_posix()] = dockerfile
    payload[LOCK.relative_to(ROOT).as_posix()] = requirements
    require(set(payload) == allowed, "CONTEXT_INPUT_SET_MISMATCH")
    # Dockerfile-specific ignore is the one additional build-control file,
    # necessarily sent by Docker even when excluded from image COPY access.
    payload[IGNORE.relative_to(ROOT).as_posix()] = context_ignore
    require(all(type(raw) is bytes and len(raw) <= 1024 * 1024 for raw in payload.values())
            and sum(map(len, payload.values())) <= 8 * 1024 * 1024,
            "CONTEXT_RESOURCE_BOUND")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in sorted(payload.items()):
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(raw), 0o644
            member.uid = member.gid = member.mtime = 0
            archive.addfile(member, io.BytesIO(raw))
    return buffer.getvalue()


def assess(
    doc: dict[str, Any], *, head: str, dockerfile: bytes,
    requirements: bytes, app_tree_sha256: str, compose: dict[str, Any], context_ignore: bytes,
) -> str:
    """Pure negative gates. NO return value authorizes build or execution."""
    d = document(doc)
    require(type(head) is str and bool(SHA.fullmatch(head)), "SOURCE_SHA_INVALID")
    source = d["source_commit"]
    require(source is None or (type(source) is str and bool(SHA.fullmatch(source))),
            "SOURCE_COMMIT_INVALID")
    if source is not None:
        require(source == head, "SOURCE_COMMIT_MISMATCH")
    b, art, evidence = d["build"], d["artifact"], d["evidence"]
    validate_profile(compose)
    instructions = tuple(v.strip() for v in dockerfile.decode("utf-8").splitlines()
                         if v.strip() and not v.lstrip().startswith("#"))
    # Parser directives (e.g. # syntax=...) can fetch/execute another frontend.
    require(not re.search(r"(?mi)^\s*#\s*(syntax|escape|check)\s*=", dockerfile.decode()),
            "DOCKERFILE_RECIPE_UNSAFE")
    require(instructions == RECIPE, "DOCKERFILE_RECIPE_UNSAFE")
    context_paths(context_ignore)
    lock_complete = validate_lock(requirements)
    expected = {
        "dockerfile_sha256": hashlib.sha256(dockerfile).hexdigest(),
        "requirements_sha256": hashlib.sha256(requirements).hexdigest(),
        "app_tree_sha256": app_tree_sha256,
        "context_ignore_sha256": hashlib.sha256(context_ignore).hexdigest(),
    }
    require(validate_optional_sha(app_tree_sha256), "APP_INPUTS_INCOMPLETE")
    for key, value in expected.items():
        if validate_optional_sha(b[key]):
            require(b[key] == value, "BUILD_INPUT_DIGEST_DRIFT")
    base = b["base_image"]
    require(base is None or (type(base) is str and "@" in base
            and base.split("@", 1)[0] == BASE_IMAGE.split("@", 1)[0]
            and validate_optional_digest(base.split("@", 1)[1])), "BASE_IMAGE_NOT_DIGEST_PINNED")
    require(base is None or base == BASE_IMAGE, "BASE_IMAGE_PIN_DRIFT")
    for key in ("digest", "config_digest"):
        validate_optional_digest(art[key])
    for key in ("buildx_metadata_sha256", "attestation_sha256", "sbom_sha256"):
        validate_optional_sha(art[key])
    image = art["image_ref"]
    require(image is None or (type(image) is str and bool(IMAGE.fullmatch(image))
            and validate_optional_digest(image.split("@", 1)[1])), "UNSAFE_IMAGE_REFERENCE")
    if image is not None and art["digest"] is not None:
        require(image == "pcp-local-runtime-inspect@" + art["digest"], "IMAGE_DIGEST_MISMATCH")
    require(evidence["provenance_mode"] == "max" and evidence["sbom_required"] is True,
            "ATTESTATION_POLICY_UNSAFE")
    require(evidence["exporter"] in (None, "registry", "oci_layout"),
            "ATTESTATION_EXPORT_UNSAFE")
    require(evidence["image_store"] in (None, "registry", "oci_layout", "containerd"),
            "IMAGE_STORE_ATTESTATION_UNSAFE")
    if evidence["exporter"] is not None and evidence["image_store"] is not None:
        require((evidence["exporter"], evidence["image_store"]) in
                (("registry", "registry"), ("oci_layout", "oci_layout")),
                "IMAGE_STORE_EXPORT_MISMATCH")
    identity = d["independent_provenance"]
    if identity is not None:
        require(type(identity) is dict and set(identity) == PROVENANCE_KEYS
                and identity["verifier"] == "independent", "INDEPENDENT_PROVENANCE_SHAPE_INVALID")
        require(validate_optional_sha(identity["statement_sha256"]),
                "INDEPENDENT_PROVENANCE_SHAPE_INVALID")
        require(art["digest"] is not None and identity["subject_digest"] == art["digest"],
                "ATTESTATION_SUBJECT_MISMATCH")
        require(source is not None and identity["source_commit"] == source,
                "ATTESTATION_SOURCE_MISMATCH")
        require(all(identity[key] == value for key, value in expected.items()),
                "ATTESTATION_MATERIALS_MISMATCH")
    if source is None:
        return "SOURCE_AUTHORITY_NOT_PINNED"
    if base is None or any(b[key] is None for key in expected):
        return "BUILD_RECIPE_NOT_PINNED"
    if not lock_complete:
        return "DEPENDENCY_LOCK_NOT_RESOLVED"
    if any(art[key] is None for key in ARTIFACT_KEYS):
        return "ARTIFACT_DIGEST_NOT_ATTESTED"
    if evidence["exporter"] is None or evidence["image_store"] is None:
        return "IMAGE_STORE_NOT_ATTESTED"
    # All submitted identities remain claims. No network verifier or trust root
    # exists in this offline planner. Registry outages have NO fallback to :local.
    return "INDEPENDENT_ATTESTATION_NOT_VERIFIED"


def main(argv: list[str]) -> int:
    try:
        require(argv == ["--check"], "USAGE_SOURCE_ONLY")
        head = check_checkout()
        try:
            doc = yaml.safe_load(read_exact(MANIFEST))
            compose = yaml.safe_load(read_exact(PROFILE))
        except yaml.YAMLError as exc:
            raise Stop("MANIFEST_YAML_INVALID") from exc
        recipe, requirements, ignore = read_exact(DOCKERFILE), read_exact(LOCK), read_exact(IGNORE)
        inputs = app_inputs()
        # Pure in-memory staging proves the exact source payload; no disk or
        # Docker action is exposed by this CLI.
        source_context(dockerfile=recipe, requirements=requirements,
                       context_ignore=ignore, inputs=inputs)
        reason = assess(doc, head=head, dockerfile=recipe,
                        requirements=requirements, context_ignore=ignore,
                        app_tree_sha256=app_digest(inputs), compose=compose)
    except Stop as exc:
        reason = str(exc)
    except (OSError, UnicodeError, ValueError, TypeError):
        reason = "SOURCE_EVIDENCE_UNAVAILABLE"
    # Retain the H1a redacted output keys for existing operator consumers.
    print("PCP_H1A_RESULT=STOP")
    print(f"PCP_H1A_REASON={reason}")
    print("PCP_H1B2_SOURCE=DRAFT_NOT_ACCEPTED")
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
