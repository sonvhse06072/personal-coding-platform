from app.pm_merge import (
    _baseline_authority_changes,
    _changed_paths,
    _path_protected_signals,
)


def job_with_paths(*paths: str) -> dict:
    return {"result": {"diff": {"changed_files": list(paths)}}}


def test_actual_sensitive_paths_map_to_protected_owner_decisions() -> None:
    signals = _path_protected_signals(
        job_with_paths(
            "AGENTS.md",
            "docs/project/roadmap.md",
            "composer.json",
            "src/Auth/PermissionChecker.php",
            "database/migrations/20260915_drop_legacy.php",
            "deploy/production.yml",
        )
    )

    assert "high_authority_governance" in signals
    assert "scope_change" in signals
    assert "major_dependency_addition" in signals
    assert "security_boundary_change" in signals
    assert "destructive_migration" in signals
    assert "production_write" in signals


def test_mutable_continuity_path_does_not_create_a_protected_signal() -> None:
    assert _path_protected_signals(job_with_paths("docs/project/current-state.md")) == set()


def test_workflow_and_renamed_sensitive_paths_fail_closed() -> None:
    job = job_with_paths(
        ".github/workflows/ci.yml -> .github/workflows/release.yml",
        "config/projects.yml",
    )
    assert _changed_paths(job) == [
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "config/projects.yml",
    ]
    assert "high_authority_governance" in _path_protected_signals(job)


def test_pinned_baseline_human_owner_path_fails_closed() -> None:
    job = job_with_paths("docs/04-business-rules.md")
    job["checkpoint"] = {
        "project_baseline": {
            "revision": "v1",
            "source_commit": "a" * 40,
            "authority": [
                {
                    "path": "docs/04-business-rules.md",
                    "authority": "human_owner_protected",
                }
            ],
        }
    }

    assert _baseline_authority_changes(job) == {
        "docs/04-business-rules.md": "human_owner_protected"
    }
    assert "project_baseline_authority_change" in _path_protected_signals(job)


def test_delegated_design_and_mutable_paths_do_not_create_owner_gate() -> None:
    job = job_with_paths(
        "docs/17-design-language.md",
        "PROJECT-CONTEXT.md",
        "docs/history/episodes.md",
    )
    job["checkpoint"] = {
        "project_baseline": {
            "revision": "v1",
            "source_commit": "b" * 40,
            "authority": [
                {
                    "path": "docs/17-design-language.md",
                    "authority": "delegated_design_owner",
                },
                {
                    "path": "PROJECT-CONTEXT.md",
                    "authority": "mutable_execution",
                },
                {
                    "path": "docs/history/episodes.md",
                    "authority": "evidence_history",
                },
            ],
        }
    }

    assert _baseline_authority_changes(job) == {
        "docs/17-design-language.md": "delegated_design_owner",
        "project-context.md": "mutable_execution",
        "docs/history/episodes.md": "evidence_history",
    }
    assert "project_baseline_authority_change" not in _path_protected_signals(job)
