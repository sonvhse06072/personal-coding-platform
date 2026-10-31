"""Focused contract tests for the pure evidence-summary CLI."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pcp-light-evidence-summary.py"
SPEC = importlib.util.spec_from_file_location("evidence_summary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)

SHA = "a" * 40


def record(record_id="r1", evidence_class="SOURCE", outcome="PASS", source_sha=SHA):
    return {"id": record_id, "class": evidence_class, "outcome": outcome,
            "source_sha": source_sha}


def test_summary_counts_classes_and_outcomes_without_live_promotion():
    result = summary.summarize([
        record("fixture", "FIXTURE", "PASS"),
        record("live", "LIVE", "NOT_TESTED"),
        record("source", "SOURCE", "FAIL"),
        record("physical", "PHYSICAL", "PASS"),
    ])
    assert result == {
        "count": 4, "source_sha": SHA,
        "by_class": {"SOURCE": 1, "FIXTURE": 1, "PHYSICAL": 1, "LIVE": 1},
        "by_outcome": {"PASS": 2, "FAIL": 1, "NOT_TESTED": 1},
        "by_class_and_outcome": {
            "SOURCE": {"PASS": 0, "FAIL": 1, "NOT_TESTED": 0},
            "FIXTURE": {"PASS": 1, "FAIL": 0, "NOT_TESTED": 0},
            "PHYSICAL": {"PASS": 1, "FAIL": 0, "NOT_TESTED": 0},
            "LIVE": {"PASS": 0, "FAIL": 0, "NOT_TESTED": 1},
        },
        "fixture_evidence_is_live": False,
    }


def test_empty_list_is_valid():
    result = summary.summarize([])
    assert result == {
        "count": 0, "source_sha": None,
        "by_class": {"SOURCE": 0, "FIXTURE": 0, "PHYSICAL": 0, "LIVE": 0},
        "by_outcome": {"PASS": 0, "FAIL": 0, "NOT_TESTED": 0},
        "by_class_and_outcome": {
            evidence_class: {"PASS": 0, "FAIL": 0, "NOT_TESTED": 0}
            for evidence_class in ("SOURCE", "FIXTURE", "PHYSICAL", "LIVE")
        },
        "fixture_evidence_is_live": False,
    }


@pytest.mark.parametrize("bad", [
    {}, {"id": "x"}, record("", "SOURCE"), record("x", "UNKNOWN"),
    record("x", "SOURCE", "MAYBE"), record("x", "SOURCE", "PASS", "a" * 39),
    {**record(), "extra": True},
])
def test_invalid_records_rejected(bad):
    with pytest.raises(summary.InputError):
        summary.summarize([bad])


def test_duplicate_ids_rejected():
    with pytest.raises(summary.InputError, match="duplicate_id"):
        summary.summarize([record("same"), record("same", "LIVE")])


def test_mixed_source_shas_rejected():
    with pytest.raises(summary.InputError, match="source_sha_mismatch"):
        summary.summarize([record("one"), record("two", source_sha="b" * 40)])


def test_order_does_not_change_json_output(tmp_path):
    items = [record("z", "LIVE", "FAIL"), record("a", "FIXTURE", "PASS"),
             record("b", "SOURCE", "NOT_TESTED"), record("c", "PHYSICAL", "PASS")]
    outputs = []
    for n, data in enumerate((items, list(reversed(items)))):
        path = tmp_path / f"{n}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        run = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                             capture_output=True, text=True, check=False)
        assert run.returncode == 0
        outputs.append(run.stdout)
    assert outputs[0] == outputs[1]


def test_cli_invalid_input_returns_nonzero(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([record("x", "NOT_A_CLASS")]), encoding="utf-8")
    run = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                         capture_output=True, text=True, check=False)
    assert run.returncode != 0
    assert json.loads(run.stdout)["status"] == "INVALID"


@pytest.mark.parametrize("raw", [
    # Top-level record object: the last member otherwise silently wins.
    b'[{"id":"x","class":"FIXTURE","class":"LIVE",'
    b'"outcome":"PASS","source_sha":"' + SHA.encode() + b'"}]',
    # A nested object is still part of the same JSON input and must be checked.
    b'[{"id":"x","class":"SOURCE","outcome":"PASS",'
    b'"source_sha":"' + SHA.encode() + b'",'
    b'"nested":{"a":1,"a":2}}]',
    # Duplicate names in a top-level object are rejected even though the value
    # would later fail the array schema check.
    b'{"x":1,"x":2}',
])
def test_cli_rejects_duplicate_json_members_without_disclosure_or_partial_counts(tmp_path, raw):
    path = tmp_path / "ambiguous.json"
    path.write_bytes(raw)
    before = path.read_bytes()

    run = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                         capture_output=True, check=False)

    assert run.returncode != 0
    assert run.stdout == b'{"reason": "duplicate_json_member", "status": "INVALID"}\n'
    assert run.stderr == b""
    assert b"FIXTURE" not in run.stdout and b"LIVE" not in run.stdout
    assert b"class" not in run.stdout and raw not in run.stdout
    assert path.read_bytes() == before


def test_cli_preserves_input_bytes_on_success_and_source_mismatch_error(tmp_path):
    valid = json.dumps([record()], separators=(",", ":")).encode()
    mismatch = json.dumps([record("one"), record("two", source_sha="b" * 40)],
                          separators=(",", ":")).encode()
    outputs = []
    for name, raw in (("valid.json", valid), ("mismatch.json", mismatch)):
        path = tmp_path / name
        path.write_bytes(raw)
        run = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                             capture_output=True, check=False)
        outputs.append(run)
        assert path.read_bytes() == raw
    assert outputs[0].returncode == 0
    assert json.loads(outputs[0].stdout) == summary.summarize([record()])
    assert outputs[1].returncode != 0
    assert json.loads(outputs[1].stdout) == {
        "status": "INVALID", "reason": "source_sha_mismatch"
    }


@pytest.mark.parametrize("nested", [
    pytest.param(b"[" * 2000 + b'"never-disclose"' + b"]" * 2000, id="deep-array"),
    pytest.param(b"[" + b'{"child":' * 2000
                 + b'{"private-sentinel":"never-disclose"}' + b"}" * 2000 + b"]",
                 id="deep-object-in-array"),
])
def test_cli_rejects_deep_nesting_sanitized_and_preserves_input(tmp_path, nested):
    # Prove structural validity independently of the decoder's ordinary depth
    # ceiling. This is real JSON parsing in a separate process, not a mocked
    # exception. The CLI below retains the interpreter's default limits.
    syntax = subprocess.run([
        sys.executable, "-c",
        "import json,sys; sys.setrecursionlimit(20000); "
        "json.loads(sys.stdin.buffer.read()); print('valid')",
    ], input=nested, capture_output=True, check=False)
    assert syntax.returncode == 0 and syntax.stdout == b"valid\n"
    assert syntax.stderr == b""
    path = tmp_path / "deep.json"
    path.write_bytes(nested)
    before = path.read_bytes()

    run = subprocess.run([sys.executable, str(SCRIPT), str(path)],
                         capture_output=True, check=False)

    assert run.returncode != 0
    # Python 3.11 can hit its decoder recursion ceiling; newer decoders can
    # reach the unchanged record-schema guard. Both are bounded INVALID paths.
    assert json.loads(run.stdout) in (
        {"reason": "input_unavailable_or_invalid", "status": "INVALID"},
        {"reason": "record_0_schema_invalid", "status": "INVALID"},
    )
    assert run.stderr == b""
    assert b"never-disclose" not in run.stdout + run.stderr
    assert b"count" not in run.stdout
    assert path.read_bytes() == before
