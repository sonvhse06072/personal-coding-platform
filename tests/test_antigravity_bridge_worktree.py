from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_SCRIPT = ROOT / "scripts" / "antigravity-bridge.sh"


def test_bridge_start_does_not_chmod_tracked_quota_sink() -> None:
    script = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert 'AGY_QUOTA_SINK_SOURCE="$ROOT/scripts/antigravity-quota-sink.py"' in script
    assert 'AGY_QUOTA_SINK="$STATE_DIR/antigravity-quota-sink.py"' in script
    assert 'install -m 700 "$AGY_QUOTA_SINK_SOURCE" "$AGY_QUOTA_SINK"' in script
    assert 'chmod 700 "$AGY_WRAPPER" "$AGY_QUOTA_SINK"' not in script
    assert 'chmod 700 "$AGY_QUOTA_SINK_SOURCE"' not in script


def test_statusline_configuration_migrates_previous_pcp_sink_only() -> None:
    script = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert 'python3 - "$AGY_SETTINGS" "$AGY_QUOTA_SINK" "$AGY_QUOTA_SINK_SOURCE"' in script
    assert 'elif existing_command in {sink, legacy_sink}:' in script
    assert 'status_line["command"] = sink' in script
    assert 'custom status line preserved' in script


def test_bridge_exports_runtime_sink_not_repository_source() -> None:
    script = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert 'export ANTIGRAVITY_QUOTA_SINK="$AGY_QUOTA_SINK"' in script
    assert 'export ANTIGRAVITY_QUOTA_SINK="$AGY_QUOTA_SINK_SOURCE"' not in script
