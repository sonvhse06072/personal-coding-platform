"""Guardrails for a single G0D-01 proof on GitHub-hosted infrastructure.

These tests inspect the workflow contract. Only the separate hosted workflow
can actually verify Composer, real DDEV, Drupal Kernel and PHPUnit.
"""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/g0d01-hosted-drupal-proof.yml"
STABLE_ACTION_COMMIT = "fdf2f5c97943bae638f31df6df86f1defa6210c0"
STABLE_DDEV_COMMIT = "5da91aeb9ebab0b0e66171c450b72099308d332c"


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps():
    return workflow()["jobs"]["isolated-drupal-proof"]["steps"]


def test_proof_runs_only_on_same_repo_pr_with_disposable_hosted_runner():
    cfg = workflow()
    assert cfg["permissions"] == {"contents": "read"}
    assert set(cfg["jobs"]) == {"isolated-drupal-proof"}
    job = cfg["jobs"]["isolated-drupal-proof"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] <= 25
    assert job["if"] == (
        "github.event.pull_request.head.repo.full_name == github.repository"
    )
    triggers = cfg.get("on", cfg.get(True))
    assert set(triggers) == {"pull_request"}
    assert triggers["pull_request"]["branches"] == ["main"]
    assert "scripts/g0-drupal11-bootstrap/**" in triggers["pull_request"]["paths"]


def test_ddev_install_is_pinned_and_does_not_autostart():
    actions = [step for step in steps() if step.get("uses")]
    checkout = next(item for item in actions if "actions/checkout" in item["uses"])
    assert checkout["with"]["persist-credentials"] is False
    ddev = next(
        item for item in actions if "ddev/github-action-setup-ddev" in item["uses"]
    )
    assert ddev["uses"].endswith("@" + STABLE_ACTION_COMMIT)
    assert ddev["with"]["version"] == "1.25.4"
    assert ddev["with"]["autostart"] == "false"
    assert STABLE_DDEV_COMMIT in ddev["with"]["installScriptUrl"]


def test_ddev_bootstrap_is_restricted_to_one_new_target_without_remote_auth():
    commands = "\n".join(item.get("run", "") for item in steps())
    assert "RUNNER_ENVIRONMENT" in commands
    assert "github-hosted" in commands
    assert 'test ! -e "$HOME/pcp-g0-fixtures/pcp-g0-drupal-fixture"' in commands
    assert "env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN" in commands
    assert "bash scripts/g0-drupal11-bootstrap/bootstrap.sh" in commands
    assert "ddev restart" not in commands
    assert "ddev stop" not in commands
    assert "docker " not in commands
    assert "gh repo create" not in commands
    assert "curl " not in commands
    assert "rm -rf" not in commands


def test_proof_requires_actual_core_lock_two_equal_baselines_and_clean_git():
    commands = "\n".join(item.get("run", "") for item in steps())
    assert 'test -f "$root/composer.lock"' in commands
    assert 'test -f "$root/web/core/tests/bootstrap.php"' in commands
    assert "refs/heads/benchmark/direct" in commands
    assert "refs/heads/benchmark/pcp" in commands
    assert 'test "$direct" = "$pcp"' in commands
    assert 'test "$main" = "$pcp"' in commands
    assert 'test -z "$(git -C "$root" status --porcelain=v1)"' in commands


def test_artifact_is_only_locked_source_evidence_never_vendor_or_database():
    uploads = [item for item in steps() if "actions/upload-artifact" in item.get("uses", "")]
    assert len(uploads) == 1
    assert uploads[0]["with"]["path"] == "${{ runner.temp }}/pcp-g0-evidence/"
    assert uploads[0]["with"]["retention-days"] <= 7
    commands = "\n".join(item.get("run", "") for item in steps())
    assert '"$evidence/composer.lock"' in commands
    assert '"$evidence/seed-commit-sha.txt"' in commands
    assert '"$evidence/composer-lock-sha256.txt"' in commands
    assert "cp -R" not in commands
    assert "vendor/" not in uploads[0]["with"]["path"]


def test_seed_export_is_git_archive_with_fail_closed_allowlist():
    items = steps()
    export_index = next(i for i, step in enumerate(items)
                        if step["name"] == "Export only committed, sanitized fixture source")
    upload_index = next(i for i, step in enumerate(items)
                        if step["name"].startswith("Publish only locked source"))
    assert export_index > next(i for i, step in enumerate(items)
                               if step["name"] == "Record exact real verification result without secrets")
    assert export_index < upload_index
    cmd = items[export_index]["run"]
    assert 'os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"' in cmd
    assert '"ls-tree", "-r", "-z", "HEAD"' in cmd
    assert '"archive", "--format=zip"' in cmd
    assert "actual == expected" in cmd
    assert "stat.S_ISLNK" in cmd
    assert 'git("status", "--porcelain=v1") == ""' in cmd
    assert 'git("rev-parse", "benchmark/direct") == sha' in cmd
    assert 'git("rev-parse", "benchmark/pcp") == sha' in cmd
    assert 'assert lock_hash == (evidence / "composer-lock-sha256.txt").read_text().strip()' in cmd
    assert '"fixture-seed-source-sha256.txt"' in cmd
    for blocked in ("vendor/", "web/core/", ".git/", "settings.php", ".env"):
        assert blocked in cmd
    assert "rm -rf" not in cmd
    assert "gh repo" not in cmd
    assert "docker " not in cmd


def test_exported_seed_and_composer_evidence_stay_in_one_short_lived_artifact():
    items = steps()
    uploads = [item for item in items if "actions/upload-artifact" in item.get("uses", "")]
    assert len(uploads) == 1
    assert uploads[0]["with"]["path"] == "${{ runner.temp }}/pcp-g0-evidence/"
    assert uploads[0]["with"]["retention-days"] <= 7
    cmd = "\n".join(item.get("run", "") for item in items)
    assert '"fixture-seed-source.zip"' in cmd
    assert '"fixture-seed-source-sha256.txt"' in cmd
    assert '"composer-lock-sha256.txt"' in cmd
    assert "secrets." not in WORKFLOW.read_text(encoding="utf-8")
