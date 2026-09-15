from app.pm_merge import _changed_paths, _path_protected_signals


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
