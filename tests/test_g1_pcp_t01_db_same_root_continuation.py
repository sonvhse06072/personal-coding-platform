"""Source-only regression for ONE exact existing PCP G1 database STOP state.

No Docker daemon/Compose operation, HTTP call, model, GitHub mutation or WSL.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts/g1-pcp-t01-db-same-root-continuation.py"
SOURCE = ROOT / "scripts/g1-pcp-t01-one-shot.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class G1PcpDbContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = load("g1_db_recovery", TARGET)
        cls.old = load("g1_db_original", SOURCE)

    def test_identical_original_pilot_and_single_shared_postdb_path(self):
        self.assertEqual(self.rec.SEED, self.old.SEED)
        self.assertEqual(self.rec.ROOT, self.old.ROOT)
        self.assertEqual(self.rec.JOURNAL, self.old.JOURNAL)
        self.assertEqual(self.rec.NETWORK, "pcp-g1-pilot-control")
        self.assertEqual(self.rec.VOLUME, "pcp-g1-pilot-postgres")
        self.assertEqual(self.rec.DB, "pcp-g1-pilot-db-1")
        self.assertTrue(callable(self.old.continue_after_database))
        self.assertIn("return continue_after_database(env, started)",
                      SOURCE.read_text())

    def test_resume_is_exact_original_without_model_before_db(self):
        text = TARGET.read_text()
        self.assertIn('prior.get("model_calls")', text)
        self.assertIn('prior.get("state") == EXPECTED_STATE', text)
        self.assertIn("not any(ws.iterdir())", text)
        self.assertIn('"refs/remotes/"', text)
        self.assertIn("m.continue_after_database(env, started)", text)
        self.assertIn("m.JOURNAL = EVIDENCE", text)
        self.assertIn("original_journal_preserved", text)
        for forbidden in (
            "g1-pcp-t01-one-shot.py --expected",
            "git reset --hard", "docker compose down",
            "docker volume rm", "docker network rm",
            "docker system prune", "docker restart",
            "/home/sonvh/chonhac", "/opt/chonhac",
        ):
            self.assertNotIn(forbidden, text)

    def test_rejects_unreviewed_sha_before_any_subprocess(self):
        with patch.object(self.rec, "call") as dispatch:
            with self.assertRaisesRegex(self.rec.Stop, "exact_unprivileged_sha"):
                self.rec.safe_checkpoint({}, "not-a-sha", self.old)
            dispatch.assert_not_called()

    def test_original_marker_is_exclusive_and_no_new_root(self):
        source = TARGET.read_text()
        self.assertIn("not EVIDENCE.exists()", source)
        self.assertIn("not CREDENTIALS.exists()", source)
        self.assertIn('state": "db_continuation_started"', source)
        self.assertIn('m.private(EVIDENCE,', source)
        self.assertNotIn("ROOT.mkdir(", source)
        self.assertNotIn("bootstrap(", source)
        self.assertNotIn("create_workspace(", source)
        self.assertIn('no_automatic_retry": True', source)

    def test_one_db_up_but_no_implicit_wait_or_recreate(self):
        fake = subprocess.CompletedProcess([], 0, stdout="created", stderr="")
        with patch.object(self.rec.subprocess, "run", return_value=fake) as sent:
            proof = self.rec.launch_db_once(self.old, {"SAFE": "1"})
        self.assertEqual(proof["exit_code"], 0)
        args = sent.call_args.args[0]
        self.assertEqual(args[-4:], ["up", "-d", "--no-deps", "db"])
        self.assertIn("up", args)
        self.assertNotIn("--wait", args)
        self.assertNotIn("--force-recreate", args)
        self.assertNotIn("direct", args)
        self.assertEqual(sent.call_count, 1)

    def test_failed_db_create_reports_only_allowlisted_classes(self):
        fake = subprocess.CompletedProcess([], 125, stdout="",
            stderr="secret=DO_NOT_ECHO Error response from daemon: "
                   "no space left on device")
        with patch.object(self.rec.subprocess, "run", return_value=fake):
            result = self.rec.launch_db_once(self.old, {})
        self.assertFalse(result["passed"])
        self.assertEqual(result["exit_code"], 125)
        self.assertIn("DISK_FULL", result["failure_classes"])
        self.assertNotIn("DO_NOT_ECHO", str(result))

    def test_rendered_compose_fails_closed_on_parked_entrypoint(self):
        good = {
            "services": {"db": {
                "image": "postgres:16-alpine", "entrypoint": None,
                "read_only": False, "cap_add": ["CHOWN"],
                "networks": {"g1-pilot-control": None},
                "volumes": [{"type": "volume", "source": "g1-pilot-db",
                             "target": "/var/lib/postgresql/data"}]}},
            "volumes": {"g1-pilot-db": {"name": self.rec.VOLUME}},
            "networks": {"g1-pilot-control": {
                "name": self.rec.NETWORK, "internal": True}},
        }
        with patch.object(self.old, "compose",
                          return_value=json.dumps(good)) as fn:
            self.rec.validate_rendered_db(self.old, {})
            fn.assert_called_once()
        good["services"]["db"]["entrypoint"] = ["/bin/false"]
        with patch.object(self.old, "compose", return_value=json.dumps(good)):
            with self.assertRaisesRegex(self.rec.Stop,
                                        "rendered_db_contract_not_safe"):
                self.rec.validate_rendered_db(self.old, {})

    def test_db_readonly_health_attestation_requires_exact_provenance(self):
        good = {
            "Name": "/" + self.rec.DB,
            "Config": {"Labels": {
                "com.docker.compose.project": "pcp-g1-pilot",
                "com.docker.compose.service": "db"}},
            "HostConfig": {"Privileged": False, "ReadonlyRootfs": False},
            "State": {"Running": True, "Health": {"Status": "healthy"}},
            "NetworkSettings": {"Networks": {self.rec.NETWORK: {}}},
            "Mounts": [{"Name": self.rec.VOLUME,
                        "Destination": "/var/lib/postgresql/data"}],
        }
        with patch.object(self.rec, "inspect_database", return_value=good):
            self.assertTrue(self.rec.verify_database({})["healthy"])
        good["NetworkSettings"]["Networks"] = {"ddev_default": {}}
        with patch.object(self.rec, "inspect_database", return_value=good):
            with self.assertRaisesRegex(self.rec.Stop,
                                        "g1_db_container_provenance_drift"):
                self.rec.verify_database({})

    def test_db_stop_does_not_change_original_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            original = Path(temp) / "job-evidence.json"
            original.write_text("original-evidence")
            marker = Path(temp) / "db-continuation-evidence.json"
            with patch.object(self.rec, "EVIDENCE", marker), patch.object(
                self.rec, "JOURNAL", original,
            ):
                self.assertNotEqual(self.rec.EVIDENCE, self.rec.JOURNAL)
                self.assertEqual(original.read_text(), "original-evidence")


if __name__ == "__main__":
    unittest.main()
