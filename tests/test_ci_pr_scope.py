"""CI scope must fail closed: only T1/T3 Markdown allows service no-op."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ci_pr_scope", ROOT / "scripts/ci_pr_scope.py"
)
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)


def diff(*items):
    return "".join(status + "\0" + path + "\0" for status, path in items).encode()


@pytest.mark.parametrize("value,expected", [
    (diff(("M", "docs/project/current-state.md")), scope.DOCS),
    (diff(("A", "docs/project/history/new-evidence.md")), scope.DOCS),
    (diff(("M", "docs/project/history/episodes.md"),
          ("M", "docs/project/current-state.md")), scope.DOCS),
    (diff(("M", "docs/project/constitution.md")), scope.FULL),
    (diff(("M", "docs/project/architecture.md")), scope.FULL),
    (diff(("M", "README.md")), scope.FULL),
    (diff(("M", "docs/project/current-state.md"),
          ("M", "services/runtime/app/main.py")), scope.FULL),
    (diff(("M", ".github/workflows/tests.yml")), scope.FULL),
    (diff(("M", "scripts/ci_pr_scope.py")), scope.FULL),
    (diff(("M", "tests/test_ci_pr_scope.py")), scope.FULL),
    (diff(("D", "docs/project/history/old.md")), scope.FULL),
    (diff(("R100", "docs/project/history/a.md"),
          ("A", "docs/project/history/b.md")), scope.FULL),
    (diff(("M", "docs/project/history/file.txt")), scope.FULL),
    (diff(("M", "docs/project/history/../current-state.md")), scope.FULL),
    (diff(("M", "/docs/project/history/a.md")), scope.FULL),
    (diff(("M", "docs\\project\\history\\a.md")), scope.FULL),
    (diff(("M", "docs/project/history/a.md"),
          ("M", "docs/project/history/a.md")), scope.FULL),
    (b"", scope.FULL),
    (b"invalid", scope.FULL),
    (b"M\0docs/project/history/a.md", scope.FULL),
    (b"M\0docs/project/history/a.md\0M\0", scope.FULL),
    (b"M\0\xff\0", scope.FULL),
])
def test_doc_only_classifier_never_skips_uncertain_source(value, expected):
    assert scope.classify(value) == expected


def test_bounded_diff_and_control_characters_are_full():
    assert scope.classify(diff(("M", "docs/project/history/a\n.md"))) == scope.FULL
    assert scope.classify(b"a" * 200001) == scope.FULL
    assert scope.classify(diff(*[("M", "docs/project/history/x%d.md" % i)
                                 for i in range(1001)])) == scope.FULL


def test_test_workflow_retains_all_four_named_gates_and_hosted_pr_runner():
    source = (ROOT / ".github/workflows/tests.yml").read_text()
    config = yaml.safe_load(source)
    assert config["name"] == "tests"
    assert set(config["jobs"]) == {"python-tests", "structure-tests"}
    matrix = config["jobs"]["python-tests"]["strategy"]["matrix"]["service"]
    assert set(matrix) == {
        "services/runtime", "services/router", "services/ddev-executor"
    }
    # CP-665 Option A: both PR and trusted main must use hosted runners.
    assert "  push:\\n    branches: [main]\\n  pull_request:".replace("\\n", "\n") in source
    assert "self-hosted" not in source
    for job in config["jobs"].values():
        assert job["runs-on"] == "ubuntu-24.04"
        checks = [step for step in job["steps"]
                  if step.get("name") == "Verify ephemeral GitHub-hosted runner"]
        assert len(checks) == 1
        assert "if" not in checks[0]  # Must run on PR and push, never be skipped.
        assert 'test "${RUNNER_ENVIRONMENT:-}" = github-hosted' in checks[0]["run"]
        assert 'test "${RUNNER_OS:-}" = Linux' in checks[0]["run"]
    assert "pull_request_target" not in source
    assert "persist-credentials: false" in source
    assert "Enforce direct-PM documentation authority" in source
    assert "ci_pr_scope.py" in source
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in source
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in source

def test_changed_pr_cannot_replace_its_own_scope_or_authority_checker():
    source = (ROOT / ".github/workflows/tests.yml").read_text()
    assert 'git show "$PR_BASE_SHA:scripts/ci_pr_scope.py"' in source
    assert 'python3 "$trusted_classifier"' in source
    assert 'git show "$DOC_BASE_SHA:scripts/check_project_doc_authority.py"' in source
    assert 'python3 "$trusted_authority"' in source
    assert '--repo-root "$GITHUB_WORKSPACE"' in source
    assert 'PR_BASE_REF:' in source and 'PR_BASE_REPO:' in source
    assert 'DOC_BASE_REF:' in source and 'DOC_BASE_REPO:' in source
    assert '"$PR_BASE_REF" != "main"' in source
    assert '"$DOC_BASE_REF" == "main"' in source
    assert 'echo \'mode=full\' >> "$GITHUB_OUTPUT"' in source
    assert '[[ "$(cat "$scoped")" == "mode=docs_only" ]]' in source
    assert "python3 scripts/ci_pr_scope.py" not in source
    assert "run: python scripts/check_project_doc_authority.py" not in source
