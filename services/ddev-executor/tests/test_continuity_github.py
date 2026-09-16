from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.continuity_github import (
    _CONTINUITY_PATH,
    _assert_one_file_pr,
    _config,
    _replace_managed,
    _validate_managed_section,
)


START = "<!-- PCP:CONTINUITY:START -->"
END = "<!-- PCP:CONTINUITY:END -->"


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, files) -> None:
        self.files = files

    def get(self, url, params=None):
        return FakeResponse(self.files)


class FakeDelivery:
    base = "https://api.github.test"


def test_managed_section_accepts_exact_marker_bounded_content() -> None:
    value = f"{START}\n## Automated continuity snapshot\n- Event: `pr_merged`.\n{END}"

    assert _validate_managed_section(value) == value


@pytest.mark.parametrize(
    "value",
    [
        f"prefix\n{START}\nvalue\n{END}",
        f"{START}\nvalue\n{END}\nsuffix",
        f"{START}\none\n{START}\ntwo\n{END}",
        f"{END}\nvalue\n{START}",
    ],
)
def test_managed_section_rejects_content_outside_or_invalid_marker_pair(value: str) -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_managed_section(value)

    assert exc.value.status_code == 422


def test_replace_managed_changes_only_the_bounded_section() -> None:
    existing = (
        "# Current state\n\n"
        f"{START}\nold\n{END}\n\n"
        "## Durable policy note\nKeep me.\n"
    )
    section = f"{START}\nnew\n{END}"

    result = _replace_managed(existing, section)

    assert "old" not in result
    assert f"{START}\nnew\n{END}" in result
    assert "## Durable policy note\nKeep me." in result


def test_replace_managed_is_idempotent_when_snapshot_is_already_current() -> None:
    section = f"{START}\nnew\n{END}"
    existing = f"# Current state\n\n{section}\n\n## Durable policy note\nKeep me.\n"

    assert _replace_managed(existing, section) == existing


def test_one_file_guard_allows_only_current_state() -> None:
    _assert_one_file_pr(
        FakeClient([{"filename": _CONTINUITY_PATH}]),
        FakeDelivery(),
        "owner/repo",
        12,
    )


@pytest.mark.parametrize(
    "files",
    [
        [],
        [{"filename": "docs/project/roadmap.md"}],
        [
            {"filename": _CONTINUITY_PATH},
            {"filename": "docs/project/architecture.md"},
        ],
    ],
)
def test_one_file_guard_rejects_missing_wrong_or_extra_files(files) -> None:
    with pytest.raises(RuntimeError, match="must change exactly"):
        _assert_one_file_pr(FakeClient(files), FakeDelivery(), "owner/repo", 12)


def test_repository_authority_is_executor_side_configuration(monkeypatch) -> None:
    monkeypatch.setenv("CONTINUITY_GITHUB_REPOSITORY", "sonvhse06072/personal-coding-platform")
    monkeypatch.setenv("CONTINUITY_BASE_BRANCH", "main")

    repository, base = _config()

    assert repository == "sonvhse06072/personal-coding-platform"
    assert base == "main"


def test_invalid_executor_side_repository_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("CONTINUITY_GITHUB_REPOSITORY", "")

    with pytest.raises(HTTPException) as exc:
        _config()

    assert exc.value.status_code == 503
