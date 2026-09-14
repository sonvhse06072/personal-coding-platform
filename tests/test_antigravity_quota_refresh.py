from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "antigravity-bridge-quota-refresh.py"


def load_module():
    spec = importlib.util.spec_from_file_location("antigravity_bridge_quota_refresh", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_usage_payload_normalizes_grouped_buckets() -> None:
    module = load_module()
    snapshot = module._usage_snapshot_from_payload(
        {
            "command": {
                "data": {
                    "plan": "Pro",
                    "groups": [
                        {
                            "name": "Gemini Models",
                            "buckets": [
                                {
                                    "id": "gemini-weekly",
                                    "window": "weekly",
                                    "remaining_fraction": 0.61,
                                    "reset_time": "2026-09-20T00:00:00Z",
                                }
                            ],
                        },
                        {
                            "name": "Claude/GPT Models",
                            "buckets": [
                                {
                                    "id": "3p-weekly",
                                    "window": "weekly",
                                    "remaining_fraction": 0.25,
                                    "reset_time": "2026-09-19T01:02:03Z",
                                }
                            ],
                        },
                    ],
                }
            }
        }
    )

    assert snapshot is not None
    assert snapshot["plan_tier"] == "Pro"
    assert snapshot["source_contract"] == "cli_print_usage_json"
    assert snapshot["quota"]["Gemini Models / gemini-weekly"]["remaining_fraction"] == 0.61
    assert snapshot["quota"]["Gemini Models / gemini-weekly"]["window"] == "weekly"
    assert snapshot["quota"]["Claude/GPT Models / 3p-weekly"]["remaining_fraction"] == 0.25


def test_usage_payload_rejects_non_command_model_result() -> None:
    module = load_module()
    assert module._usage_snapshot_from_payload(
        {
            "status": "SUCCESS",
            "response": "Here is your quota...",
            "usage": {"total_tokens": 1234},
        }
    ) is None


def test_print_usage_is_version_gated_before_invocation(monkeypatch) -> None:
    module = load_module()
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = "agy 1.1.10"
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    snapshot, status = module._read_cli_usage("/usr/bin/agy")

    assert snapshot is None
    assert status == "unsupported_cli_version:1.1.10"
    assert calls == [["/usr/bin/agy", "--version"]]


def test_safe_print_usage_command_uses_read_only_structured_path(monkeypatch) -> None:
    module = load_module()
    calls: list[list[str]] = []

    class VersionCompleted:
        returncode = 0
        stdout = "agy 1.1.27"
        stderr = ""

    class UsageCompleted:
        returncode = 0
        stdout = '{"command":{"data":{"groups":[{"name":"Gemini Models","buckets":[{"id":"gemini-weekly","remaining_fraction":0.8}]}]}}}'
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return VersionCompleted() if args[-1] == "--version" else UsageCompleted()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    snapshot, status = module._read_cli_usage("/usr/bin/agy")

    assert status == "ok"
    assert snapshot is not None
    assert snapshot["quota"]["Gemini Models / gemini-weekly"]["remaining_fraction"] == 0.8
    assert calls[1] == ["/usr/bin/agy", "-p", "/usage", "--output-format", "json"]
