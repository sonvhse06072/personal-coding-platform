from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_project_doc_authority import (  # noqa: E402
    check,
    classify_path,
    require_approval_scope,
    require_existing_baseline_revisions_immutable,
)


def test_known_authority_classes_are_distinct():
    assert classify_path("AGENTS.md") == "protected"
    for path in (
        "services/runtime/app/pcp_local_worker_loop.py",
        "services/runtime/app/engine.py",
        "services/runtime/app/storage.py",
        "scripts/check_project_doc_authority.py",
    ):
        assert classify_path(path) == "protected"
    assert classify_path("docs/project/business-strategy.md") == "protected"
    assert classify_path("config/project-baselines.yml") == "protected"
    assert classify_path("config/pm-bridge.yml") == "protected"
    assert classify_path("docs/project/current-state.md") == "mutable"
    assert classify_path("docs/project/history/episodes.md") == "evidence"
    assert classify_path("docs/project/new-undocumented-policy.md") == "unclassified"


def test_a_protected_doc_cannot_pass_on_a_generic_issue_or_unscoped_paths():
    protected = {"AGENTS.md", "docs/project/constitution.md"}
    with pytest.raises(ValueError, match="Owner-Approval-Issue"):
        require_approval_scope(protected, "Approved because I wrote Accepted")
    with pytest.raises(ValueError, match="Approved-Protected-Paths"):
        require_approval_scope(
            protected,
            "Owner-Approval-Issue: https://github.com/sonvhse06072/"
            "personal-coding-platform/issues/571",
        )
    with pytest.raises(ValueError, match="absent from declared"):
        require_approval_scope(
            protected,
            "Owner-Approval-Issue: https://github.com/sonvhse06072/"
            "personal-coding-platform/issues/571\n"
            "Approved-Protected-Paths: `AGENTS.md`",
        )


def test_exact_scoped_owner_context_is_accepted_as_declaration_only():
    result = require_approval_scope(
        {"AGENTS.md"},
        "Owner-Approval-Issue: https://github.com/sonvhse06072/"
        "personal-coding-platform/issues/571\n"
        "Approved-Protected-Paths: `AGENTS.md`, `.github/workflows/tests.yml`",
    )
    assert result is not None and result.endswith("/571")


def test_approved_baseline_cannot_be_edited_or_removed_in_place():
    before = {
        "projects": {
            "chonhac": {
                "revisions": {
                    "approved-r1": {
                        "status": "approved",
                        "source_commit": "a" * 40,
                        "references": {"goals": ["A"]},
                    }
                }
            }
        }
    }
    require_existing_baseline_revisions_immutable(before, before)
    after = {
        "projects": {
            "chonhac": {
                "revisions": {
                    "approved-r1": {
                        "status": "approved",
                        "source_commit": "b" * 40,
                        "references": {"goals": ["A"]},
                    }
                }
            }
        }
    }
    with pytest.raises(ValueError, match="changed in place"):
        require_existing_baseline_revisions_immutable(before, after)
    with pytest.raises(ValueError, match="changed in place"):
        require_existing_baseline_revisions_immutable(before, {"projects": {}})


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True, capture_output=True, check=True,
    ).stdout.strip()


def test_changed_unclassified_doc_fails_but_mutable_current_state_passes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "fixture")
    (repo / "docs/project").mkdir(parents=True)
    (repo / "docs/project/current-state.md").write_text("# State\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "docs/project/current-state.md").write_text("# New state\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "mutable")
    head = _git(repo, "rev-parse", "HEAD")
    assert check(repo, base, head, "")["protected_files"] == []

    (repo / "docs/project/new-authority.md").write_text("# Unclassified\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "unclassified")
    latest = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="unclassified"):
        check(repo, base, latest, "")
