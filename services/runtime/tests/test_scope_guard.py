from app.scope_guard import (
    baseline_authority_changes,
    changed_path_protected_signals,
    normalize_changed_paths,
)


def test_changed_path_normalization_handles_renames_and_duplicates() -> None:
    assert normalize_changed_paths([
        "./Frontend/A.tsx",
        "Frontend/A.tsx",
        "old.yml -> .github/workflows/ci.yml",
    ]) == [
        "frontend/a.tsx",
        "old.yml",
        ".github/workflows/ci.yml",
    ]


def test_sensitive_paths_are_protected_independently_of_file_count() -> None:
    signals = changed_path_protected_signals([
        "frontend/component.tsx",
        "config/routing-policy.yml",
        "src/Auth/PermissionChecker.php",
    ])

    assert "high_authority_governance" in signals
    assert "security_boundary_change" in signals


def test_pinned_human_owner_document_authority_is_a_protected_signal() -> None:
    checkpoint = {
        "project_baseline": {
            "authority": [
                {
                    "path": "docs/04-business-rules.md",
                    "authority": "human_owner_protected",
                },
                {
                    "path": "docs/17-design-language.md",
                    "authority": "delegated_design_owner",
                },
            ]
        }
    }

    authority = baseline_authority_changes(
        ["docs/04-business-rules.md", "docs/17-design-language.md"],
        checkpoint,
    )
    signals = changed_path_protected_signals(
        ["docs/04-business-rules.md", "docs/17-design-language.md"],
        checkpoint,
    )

    assert authority["docs/04-business-rules.md"] == "human_owner_protected"
    assert authority["docs/17-design-language.md"] == "delegated_design_owner"
    assert "project_baseline_authority_change" in signals


def test_ordinary_frontend_files_do_not_create_protected_signal() -> None:
    assert changed_path_protected_signals([
        "frontend/src/components/ui/action-bar.tsx",
        "frontend/src/features/musician-profile/owner-profile-editor.tsx",
        "frontend/tests/action-bar.test.tsx",
    ]) == set()


def test_drupal_config_schema_metadata_is_not_destructive_migration() -> None:
    signals = changed_path_protected_signals([
        "web/modules/custom/cho_nhac_show/config/schema/cho_nhac_show.schema.yml",
    ])

    assert "destructive_migration" not in signals


def test_real_migration_and_schema_paths_remain_protected() -> None:
    for path in (
        "database/migrations/20261003_add_index.sql",
        "web/modules/custom/demo/migrations/UpdateThing.php",
        "database/user_schema.sql",
    ):
        signals = changed_path_protected_signals([path])
        assert "destructive_migration" in signals, path


def test_package_json_script_only_change_is_not_dependency_addition_with_semantic_evidence() -> None:
    signals = changed_path_protected_signals(
        ["frontend/package.json"],
        dependency_manifest_changes=[],
    )

    assert "major_dependency_addition" not in signals


def test_package_json_dependency_change_remains_protected() -> None:
    signals = changed_path_protected_signals(
        ["frontend/package.json"],
        dependency_manifest_changes=["frontend/package.json"],
    )

    assert "major_dependency_addition" in signals


def test_legacy_package_json_without_semantic_evidence_remains_fail_closed() -> None:
    signals = changed_path_protected_signals(["frontend/package.json"])

    assert "major_dependency_addition" in signals


def test_lockfile_remains_protected_even_when_semantic_list_is_empty() -> None:
    signals = changed_path_protected_signals(
        ["frontend/package-lock.json"],
        dependency_manifest_changes=[],
    )

    assert "major_dependency_addition" in signals
