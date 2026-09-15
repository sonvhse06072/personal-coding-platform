from __future__ import annotations

import asyncio
import json
import subprocess
from copy import deepcopy
from pathlib import Path

from app.engine_verification import RuntimeEngine as VerificationRuntimeEngine
from app.repo import diff_state


class FakeStorage:
    def __init__(self, row):
        self.row = deepcopy(row)
        self.events = []

    def get(self, job_id):
        return deepcopy(self.row) if job_id == self.row["id"] else None

    def update(self, job_id, **fields):
        assert job_id == self.row["id"]
        self.row.update(deepcopy(fields))

    def append_event(self, job_id, event):
        assert job_id == self.row["id"]
        self.events.append(deepcopy(event))


def git_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    (workspace / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=workspace, check=True)
    return workspace


def test_intent_to_add_control_artifact_is_not_mistaken_for_tracked_file(tmp_path):
    async def scenario():
        workspace = git_workspace(tmp_path)
        (workspace / "README.md").write_text("baseline\nreal change\n", encoding="utf-8")
        request_path = workspace / ".pcp-collaboration-request.json"
        request_path.write_text(
            json.dumps(
                {
                    "action": "consult",
                    "role": "consultant",
                    "topic": "pattern",
                    "objective": "challenge the repository pattern",
                    "question": "Does the current change follow the existing pattern?",
                    "evidence": [{"ref": "README.md", "summary": "The file changed by this iteration"}],
                }
            ),
            encoding="utf-8",
        )

        # This exactly mirrors the base execution loop before _verify():
        # diff_state adds intent-to-add entries for untracked files.
        dirty = diff_state(workspace, 100000)
        assert ".pcp-collaboration-request.json" in dirty["changed_files"]
        assert subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".pcp-collaboration-request.json"],
            cwd=workspace,
            capture_output=True,
        ).returncode == 0
        assert subprocess.run(
            ["git", "cat-file", "-e", "HEAD:.pcp-collaboration-request.json"],
            cwd=workspace,
            capture_output=True,
        ).returncode != 0

        progress = {
            "changed_files": dirty["changed_file_count"],
            "material_change_present": True,
            "diff_hashes": [dirty["diff_hash"]],
        }
        storage = FakeStorage(
            {
                "id": "job149git000001",
                "workspace": str(workspace),
                "progress": deepcopy(progress),
            }
        )
        engine = object.__new__(VerificationRuntimeEngine)
        engine.storage = storage

        consumed = await engine._consume_collaboration_request(
            job_id=storage.row["id"],
            workspace=workspace,
            project={"runtime": {"max_diff_bytes": 100000}},
            progress=progress,
        )

        assert consumed is not None
        assert consumed.request.role == "consultant"
        assert not request_path.exists()
        assert consumed.clean_diff["changed_files"] == ["README.md"]
        assert ".pcp-collaboration-request.json" not in consumed.clean_diff["diff"]
        assert subprocess.run(
            ["git", "ls-files", ".pcp-collaboration-request.json"],
            cwd=workspace,
            text=True,
            capture_output=True,
        ).stdout.strip() == ""
        assert progress["changed_files"] == 1
        assert progress["diff_hashes"][-1] == consumed.clean_diff["diff_hash"]

    asyncio.run(scenario())
