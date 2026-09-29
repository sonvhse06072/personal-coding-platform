"""One bounded managed issue comment. Repository resolution/auth live in PM bridge."""
from __future__ import annotations

import fcntl
import hashlib
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_BYTES = 12 * 1024
MAX_PAGES = 5


class ProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=200)
    issue_number: int = Field(strict=True, gt=0, le=2**63 - 1)
    handoff_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    body: str = Field(min_length=1, max_length=MAX_BYTES)
    known_comment_id: int | None = Field(default=None, strict=True, gt=0, le=2**63 - 1)

    @model_validator(mode="after")
    def validate_identity(self):
        expected = hashlib.sha256(f"{self.project_id}:{self.issue_number}".encode()).hexdigest()
        if self.handoff_key != expected:
            raise ValueError("Progress handoff key does not match project/issue")
        if "PCP:" in self.body.upper() or "<!--" in self.body or "\x00" in self.body:
            raise ValueError("Caller cannot supply managed markers")
        if len(self.rendered.encode("utf-8")) > MAX_BYTES:
            raise ValueError("Progress comment exceeds UTF-8 byte bound")
        return self

    @property
    def marker(self) -> str:
        return f"<!-- PCP:PLAN-PROGRESS:{self.handoff_key} -->"

    @property
    def rendered(self) -> str:
        return f"{self.marker}\n\n{self.body}"


def _json(response: httpx.Response) -> Any:
    response.raise_for_status()
    return response.json()


def _validate_comment(raw: Any, payload: ProgressRequest, repository: str, base: str,
                      expected_id: int | None = None) -> int:
    if not isinstance(raw, dict):
        raise ValueError("Invalid progress comment response")
    number = raw.get("id")
    if type(number) is not int or number <= 0 or (expected_id is not None and number != expected_id):
        raise ValueError("Mismatched progress comment id")
    if (raw.get("issue_url") != f"{base}/repos/{repository}/issues/{payload.issue_number}"
            or raw.get("url") != f"{base}/repos/{repository}/issues/comments/{number}"
            or raw.get("html_url") != f"https://github.com/{repository}/issues/{payload.issue_number}#issuecomment-{number}"):
        raise ValueError("Mismatched progress comment repository/issue")
    body = raw.get("body")
    if not isinstance(body, str) or body.count(payload.marker) != 1 or body.count("<!-- PCP:") != 1:
        raise ValueError("Mismatched progress comment marker")
    return number


def upsert_progress(delivery: Any, repository: str, payload: ProgressRequest) -> dict[str, Any]:
    # Cross-thread/process serialization includes discovery + uncertain-create
    # recovery. Never unlink this inode: a timed-out caller may still be running.
    # A single lock is sufficient for the existing single-host executor topology.
    directory = Path("/tmp/pcp-plan-progress")
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / "publication.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Progress publication already in flight") from exc
        with delivery._client() as client:
            client.timeout = httpx.Timeout(8)
            client.follow_redirects = False
            return _upsert(client, delivery.base, repository, payload)


def _upsert(client: httpx.Client, base: str, repository: str, payload: ProgressRequest) -> dict[str, Any]:
    issue_url = f"{base}/repos/{repository}/issues/{payload.issue_number}"
    issue = _json(client.get(issue_url))
    if (not isinstance(issue, dict) or type(issue.get("number")) is not int
            or issue["number"] != payload.issue_number or issue.get("url") != issue_url
            or issue.get("html_url") != f"https://github.com/{repository}/issues/{payload.issue_number}"
            or "pull_request" in issue):
        raise ValueError("Progress target is not the exact configured issue")

    known = None
    if payload.known_comment_id:
        response = client.get(f"{base}/repos/{repository}/issues/comments/{payload.known_comment_id}")
        if response.status_code != 404:
            known = _validate_comment(_json(response), payload, repository, base, payload.known_comment_id)

    # Even a valid known ID must not hide a duplicate marker. Exhaust the bounded
    # scan before any mutation; a pagination cap never means 'no marker'.
    matches: dict[int, dict[str, Any]] = {}
    for page in range(1, MAX_PAGES + 1):
        response = client.get(f"{issue_url}/comments", params={"per_page": 100, "page": page})
        comments = _json(response)
        if not isinstance(comments, list) or len(comments) > 100:
            raise ValueError("Invalid progress discovery response")
        for raw in comments:
            if not isinstance(raw, dict):
                raise ValueError("Invalid progress discovery comment")
            body = raw.get("body") or ""
            if isinstance(body, str) and payload.marker in body:
                number = _validate_comment(raw, payload, repository, base)
                matches[number] = raw
        if len(matches) > 1:
            raise ValueError("Multiple exact progress markers")
        if len(comments) < 100 and "next" not in response.links:
            break
    else:
        raise ValueError("Progress discovery pagination bound exhausted")

    if known is not None and known not in matches:
        raise ValueError("Known progress comment missing from issue discovery")
    number = next(iter(matches), None)
    state = "created"
    if number is not None:
        url = f"{base}/repos/{repository}/issues/comments/{number}"
        # Revalidate immediately before PATCH; discovery is not mutation authority.
        _validate_comment(_json(client.get(url)), payload, repository, base, number)
        raw = _json(client.patch(url, json={"body": payload.rendered}))
        _validate_comment(raw, payload, repository, base, number)
        state = "updated" if known == number else "recovered"
    else:
        raw = _json(client.post(f"{issue_url}/comments", json={"body": payload.rendered}))
        number = _validate_comment(raw, payload, repository, base)
    observed = _json(client.get(f"{base}/repos/{repository}/issues/comments/{number}"))
    _validate_comment(observed, payload, repository, base, number)
    if observed["body"] != payload.rendered:
        raise ValueError("Progress comment body postcondition mismatch")
    return {"repository": repository, "issue_number": payload.issue_number, "comment_id": number,
            "comment_url": observed["html_url"], "state": state,
            "observed_body_sha256": hashlib.sha256(observed["body"].encode("utf-8")).hexdigest()}
