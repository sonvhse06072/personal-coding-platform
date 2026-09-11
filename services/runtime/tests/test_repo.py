import subprocess
from pathlib import Path

from app.repo import analyze_repo, task_requires_material_change, tokenize


def test_tokenize_removes_common_words():
    result = tokenize("Fix the intermittent payment synchronization bug with Salesforce API")
    assert "fix" not in result
    assert "payment" in result
    assert "salesforce" in result


def test_tokenize_ignores_generic_repo_scope_language():
    result = tokenize(
        "Inspect the existing custom Drupal modules and add one small automated test for existing behavior"
    )
    assert result == []


def test_material_change_intent_is_inferred():
    assert task_requires_material_change({"title": "Add a small automated test", "task_type": "unknown"}) is True
    assert task_requires_material_change({"title": "Explain how this service works", "task_type": "analysis"}) is False


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    return repo


def test_generic_test_request_does_not_inflate_scope(tmp_path: Path):
    repo = _repo(tmp_path)
    for idx in range(20):
        path = repo / f"web/modules/custom/mod_{idx}/tests/ExampleTest.php"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("existing custom Drupal module automated test behavior\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

    analysis, _ = analyze_repo(
        repo,
        {
            "title": "Add a small automated test",
            "description": (
                "Inspect the existing custom Drupal modules and add one small automated test "
                "for existing behavior. Keep the change minimal and do not refactor unrelated code."
            ),
            "task_type": "test",
        },
        {},
    )
    assert analysis["estimated_files"] == 1
    assert analysis["affected_components"] == 1
    assert analysis["relevance"] == []


def test_specific_terms_rank_small_relevant_set(tmp_path: Path):
    repo = _repo(tmp_path)
    relevant = repo / "web/modules/custom/payments/src/SalesforceSync.php"
    relevant.parent.mkdir(parents=True, exist_ok=True)
    relevant.write_text("class SalesforceSync { /* invoice_sync */ }\n")
    other = repo / "web/modules/custom/catalog/src/Catalog.php"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("class Catalog {}\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

    analysis, _ = analyze_repo(
        repo,
        {
            "title": "Fix Salesforce invoice_sync failure",
            "description": "Repair invoice_sync in SalesforceSync without unrelated refactors.",
            "task_type": "bugfix",
        },
        {},
    )
    assert analysis["estimated_files"] == 1
    assert analysis["candidate_modules"] == ["payments"]
    assert analysis["relevance"][0]["path"].endswith("SalesforceSync.php")
    assert "salesforce" in analysis["relevance"][0]["matched_terms"]
