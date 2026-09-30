from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "antigravity-bridge-quota-safe.py"


def load_module():
    spec = importlib.util.spec_from_file_location("antigravity_bridge_quota_safe", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_settings_bytes(module) -> bytes:
    legacy = module.quota19.quota18.live.legacy
    return (
        json.dumps(
            {
                **legacy.REQUIRED_SETTINGS,
                "permissions": {
                    "allow": sorted(legacy.REQUIRED_ALLOW_RULES),
                    "deny": sorted(legacy.REQUIRED_DENY_RULES),
                    "ask": ["command(*)"],
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def get_json(base_url: str, path: str) -> tuple[int, dict]:
    request = Request(
        f"{base_url}{path}",
        headers={"Authorization": "Bearer test-token"},
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


@contextmanager
def running_bridge(module, monkeypatch, tmp_path: Path, *, health_started=None):
    settings = tmp_path / "settings.json"
    settings.write_bytes(safe_settings_bytes(module))
    os.chmod(settings, 0o600)
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()

    monkeypatch.setattr(module.quota19, "_real_agy", lambda: "/usr/bin/agy")
    monkeypatch.setattr(
        module.quota19,
        "_print_usage_supported",
        lambda binary: (True, (1, 1, 11)),
    )
    monkeypatch.setattr(module.quota19.quota18, "_read_live_quota", lambda: None)
    monkeypatch.setattr(module.quota19.quota18, "_read_quota_snapshot", lambda: None)

    bridge = module.SafeQuotaRefreshBridge(
        token="test-token",
        workspaces=workspaces,
        agy_bin="/usr/bin/agy",
        settings=settings,
    )
    ParentHandler = bridge.handler()

    class Handler(ParentHandler):
        def do_GET(self):
            if self.path == "/health" and health_started is not None:
                health_started.set()
            return super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    host, port = server.server_address
    try:
        yield bridge, settings, f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)


def request_in_thread(base_url: str, path: str, result: dict, done: threading.Event) -> None:
    try:
        result["response"] = get_json(base_url, path)
    except BaseException as exc:
        result["error"] = exc
    finally:
        done.set()


class ObservedLock:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempt_lock = threading.Lock()
        self._attempts = 0
        self.health_waiting = threading.Event()

    def __enter__(self):
        with self._attempt_lock:
            self._attempts += 1
            if self._attempts == 2:
                self.health_waiting.set()
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._lock.release()


def test_quota_probe_restores_settings_bytes_and_mode(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    settings = tmp_path / "settings.json"
    original = safe_settings_bytes(module)
    settings.write_bytes(original)
    os.chmod(settings, 0o600)

    def fake_read_cli_usage(binary: str):
        assert binary == "/usr/bin/agy"
        settings.write_text(
            json.dumps({"enableTerminalSandbox": True}) + "\n",
            encoding="utf-8",
        )
        os.chmod(settings, 0o644)
        return {"quota": {"Gemini": {"remaining_fraction": 0.5}}}, "ok"

    monkeypatch.setattr(module.quota19, "_read_cli_usage", fake_read_cli_usage)

    snapshot, status = module._read_cli_usage_preserving_settings(
        "/usr/bin/agy",
        settings,
    )

    assert status == "ok"
    assert snapshot is not None
    assert settings.read_bytes() == original
    assert settings.stat().st_mode & 0o777 == 0o600


def test_quota_probe_restores_settings_when_cli_raises(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    settings = tmp_path / "settings.json"
    original = safe_settings_bytes(module)
    settings.write_bytes(original)
    os.chmod(settings, 0o600)

    def fake_read_cli_usage(binary: str):
        settings.write_text("{}\n", encoding="utf-8")
        os.chmod(settings, 0o644)
        raise RuntimeError("simulated CLI failure")

    monkeypatch.setattr(module.quota19, "_read_cli_usage", fake_read_cli_usage)

    snapshot, status = module._read_cli_usage_preserving_settings(
        "/usr/bin/agy",
        settings,
    )

    assert snapshot is None
    assert status == "cli_usage_error:RuntimeError"
    assert settings.read_bytes() == original
    assert settings.stat().st_mode & 0o777 == 0o600


def test_quota_health_waits_for_exact_settings_restore(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    mutated = threading.Event()
    release_cli = threading.Event()
    inspected_settings: list[bytes] = []
    legacy = module.quota19.quota18.live.legacy
    real_settings_status = legacy.settings_status

    def fake_read_cli_usage(binary: str):
        assert binary == "/usr/bin/agy"
        settings.write_text("{}\n", encoding="utf-8")
        os.chmod(settings, 0o644)
        mutated.set()
        if not release_cli.wait(timeout=3):
            raise TimeoutError("test did not release quota CLI")
        return {"quota": {"Gemini": {"remaining_fraction": 0.5}}}, "ok"

    def observed_settings_status(path: Path):
        inspected_settings.append(path.read_bytes())
        return real_settings_status(path)

    monkeypatch.setattr(module.quota19, "_read_cli_usage", fake_read_cli_usage)
    monkeypatch.setattr(legacy, "settings_status", observed_settings_status)

    quota_result: dict = {}
    health_result: dict = {}
    quota_done = threading.Event()
    health_done = threading.Event()

    with running_bridge(module, monkeypatch, tmp_path) as (bridge, settings, base_url):
        original = settings.read_bytes()
        original_mode = settings.stat().st_mode & 0o777
        assert bridge._quota_settings_lock is not bridge._agy_lock
        observed_lock = ObservedLock()
        bridge._quota_settings_lock = observed_lock

        quota_thread = threading.Thread(
            target=request_in_thread,
            args=(base_url, "/quota", quota_result, quota_done),
            name="quota-request",
        )
        health_thread = threading.Thread(
            target=request_in_thread,
            args=(base_url, "/health", health_result, health_done),
            name="health-request",
        )
        quota_thread.start()
        try:
            assert mutated.wait(timeout=2)
            assert settings.read_bytes() == b"{}\n"

            health_thread.start()
            assert observed_lock.health_waiting.wait(timeout=2)
            assert health_done.is_set() is False
            assert inspected_settings == []
        finally:
            release_cli.set()

        quota_thread.join(timeout=3)
        health_thread.join(timeout=3)
        assert quota_thread.is_alive() is False
        assert health_thread.is_alive() is False
        assert quota_done.is_set() is True
        assert health_done.is_set() is True
        assert "error" not in quota_result
        assert "error" not in health_result

        quota_status, quota_payload = quota_result["response"]
        health_status, health_payload = health_result["response"]
        assert quota_status == 200
        assert quota_payload["source"] == "antigravity_cli_usage"
        assert settings.read_bytes() == original
        assert settings.stat().st_mode & 0o777 == original_mode
        assert health_status == 200
        assert health_payload["status"] == "ok"
        assert health_payload["safe_settings"] is True
        assert health_payload["safety"]["mismatches"] == {}
        assert inspected_settings == [original]


def test_health_rejects_persistently_unsafe_settings(monkeypatch, tmp_path: Path) -> None:
    module = load_module()

    with running_bridge(module, monkeypatch, tmp_path) as (_, settings, base_url):
        settings.write_text("{}\n", encoding="utf-8")

        status, payload = get_json(base_url, "/health")

    assert status == 503
    assert payload["status"] == "degraded"
    assert payload["safe_settings"] is False
    assert payload["safety"]["mismatches"]


def test_health_does_not_wait_for_antigravity_run_lock(monkeypatch, tmp_path: Path) -> None:
    module = load_module()
    health_started = threading.Event()
    health_done = threading.Event()
    health_result: dict = {}

    with running_bridge(
        module,
        monkeypatch,
        tmp_path,
        health_started=health_started,
    ) as (bridge, _, base_url):
        bridge._agy_lock.acquire()
        health_thread = threading.Thread(
            target=request_in_thread,
            args=(base_url, "/health", health_result, health_done),
        )
        try:
            health_thread.start()
            assert health_started.wait(timeout=2)
            health_thread.join(timeout=1)
            assert health_thread.is_alive() is False
        finally:
            bridge._agy_lock.release()
            health_thread.join(timeout=3)

    assert health_done.is_set() is True
    assert "error" not in health_result
    status, payload = health_result["response"]
    assert status == 200
    assert payload["safe_settings"] is True


def test_quota_probe_lock_order_and_version() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "with bridge._agy_lock:" in source
    assert "with bridge._quota_settings_lock:" in source
    assert "_read_cli_usage_preserving_settings(" in source
    assert 'server_version = "PersonalCodingAntigravityBridge/1.12"' in source
    assert 'version": "1.12"' in source
    assert "Antigravity host bridge 1.12 listening" in source
