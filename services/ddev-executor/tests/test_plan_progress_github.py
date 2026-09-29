import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import plan_progress_github as progress
from app import pm_bridge_github as bridge


REPO = "owner/repo"
BASE = "https://api.github.com"
KEY = hashlib.sha256(b"demo:123").hexdigest()


def payload(**changes):
    return progress.ProgressRequest(**{
        "project_id": "demo", "issue_number": 123, "handoff_key": KEY,
        "body": "## PCP execution progress\nState: executing", **changes,
    })


class GitHub:
    base = BASE

    def __init__(self):
        self.comments = {}
        self.calls = []
        self.issue = {"number": 123, "url": f"{BASE}/repos/{REPO}/issues/123",
                      "html_url": f"https://github.com/{REPO}/issues/123"}
        self.uncertain = None
        self.before_create = None
        self.after_write = None
        self.list_override = None
        self.get_override = None

    def comment(self, number, body=None):
        return {"id": number, "issue_url": self.issue['url'],
                "url": f"{BASE}/repos/{REPO}/issues/comments/{number}",
                "html_url": f"https://github.com/{REPO}/issues/123#issuecomment-{number}",
                "body": body or payload().rendered}

    def _client(self):
        return httpx.Client(transport=httpx.MockTransport(self.request))

    def request(self, request):
        path, method = request.url.path, request.method
        self.calls.append((method, path))
        assert request.url.host == "api.github.com"
        if method == 'GET' and path == f"/repos/{REPO}/issues/123":
            return httpx.Response(200, json=self.issue)
        if path == f"/repos/{REPO}/issues/123/comments":
            if method == 'GET':
                assert request.url.params['per_page'] == '100'
                if self.list_override:
                    return self.list_override(request)
                return httpx.Response(200, json=list(self.comments.values()))
            assert method == 'POST'
            if self.before_create:
                self.before_create()
            number = 100 + len(self.comments)
            self.comments[number] = self.comment(number, json.loads(request.content)['body'])
            return self.write_response(request, number)
        prefix = f"/repos/{REPO}/issues/comments/"
        assert path.startswith(prefix)
        number = int(path.removeprefix(prefix))
        if method == 'GET' and self.get_override:
            result = self.get_override(number)
            if result is not None:
                return httpx.Response(200, json=result)
        if number not in self.comments:
            return httpx.Response(404)
        if method == 'GET':
            return httpx.Response(200, json=self.comments[number])
        assert method == 'PATCH'
        self.comments[number]['body'] = json.loads(request.content)['body']
        return self.write_response(request, number)

    def write_response(self, request, number):
        if self.after_write:
            self.after_write(self.comments[number])
        if self.uncertain:
            mode, self.uncertain = self.uncertain, None
            if mode == 'timeout':
                raise httpx.ReadTimeout("secret raw response", request=request)
            return httpx.Response(503, text="secret raw response")
        return httpx.Response(200, json=self.comments[number])

    @property
    def writes(self):
        return [(method, path) for method, path in self.calls if method in {'PATCH', 'POST'}]


def test_create_then_update_same_comment_with_exact_readback():
    github = GitHub()
    first = progress.upsert_progress(github, REPO, payload())
    assert first['state'] == 'created' and first['comment_id'] == 100
    desired = payload(known_comment_id=100, body="State: completed")
    second = progress.upsert_progress(github, REPO, desired)
    assert second['state'] == 'updated' and second['comment_id'] == 100
    assert len(github.comments) == 1
    assert github.comments[100]['body'] == desired.rendered
    assert second['observed_body_sha256'] == hashlib.sha256(desired.rendered.encode()).hexdigest()
    assert [method for method, _ in github.writes] == ['POST', 'PATCH']
    patch_index = github.calls.index(github.writes[-1])
    assert github.calls[patch_index - 1] == ('GET', f'/repos/{REPO}/issues/comments/100')
    assert github.calls[-1] == github.calls[patch_index - 1]


@pytest.mark.parametrize('known', [None, 999])
def test_missing_or_deleted_known_id_discovers_existing(known):
    github = GitHub()
    github.comments[42] = github.comment(42)
    result = progress.upsert_progress(github, REPO, payload(known_comment_id=known))
    assert result['state'] == 'recovered' and result['comment_id'] == 42
    assert [method for method, _ in github.writes] == ['PATCH']


def test_deleted_known_and_no_marker_creates_one_replacement():
    github = GitHub()
    result = progress.upsert_progress(github, REPO, payload(known_comment_id=42))
    assert result['state'] == 'created' and len(github.comments) == 1


@pytest.mark.parametrize('mode', ['timeout', '503'])
@pytest.mark.parametrize('operation', ['create', 'update'])
def test_uncertain_mutation_retries_without_duplicate(mode, operation):
    github = GitHub()
    if operation == 'update':
        github.comments[100] = github.comment(100)
    github.uncertain = mode
    with pytest.raises(httpx.HTTPError):
        progress.upsert_progress(github, REPO, payload(body='State: blocked'))
    assert len(github.comments) == 1
    result = progress.upsert_progress(github, REPO, payload(body='State: completed'))
    assert result['state'] == 'recovered' and result['comment_id'] == 100
    assert len(github.comments) == 1
    assert sum(method == 'POST' for method, _ in github.writes) == (1 if operation == 'create' else 0)


@pytest.mark.parametrize('known', [None, 42])
def test_multiple_exact_markers_fail_closed_even_with_known_id(known):
    github = GitHub()
    github.comments = {n: github.comment(n) for n in (42, 43)}
    with pytest.raises(ValueError, match='Multiple exact'):
        progress.upsert_progress(github, REPO, payload(known_comment_id=known))
    assert github.writes == []


@pytest.mark.parametrize('field,value', [
    ('id', 1234), ('issue_url', f'{BASE}/repos/{REPO}/issues/999'),
    ('issue_url', f'{BASE}/repos/other/repo/issues/123'),
    ('url', f'{BASE}/repos/other/repo/issues/comments/42'),
    ('html_url', f'https://github.com/{REPO}/issues/999#issuecomment-42'),
    ('body', 'unmanaged comment'), ('body', payload().rendered + payload().marker),
    ('body', payload().rendered + '<!-- PCP:OTHER:marker -->'),
])
def test_known_comment_mismatch_never_falls_back_or_mutates(field, value):
    github = GitHub()
    github.comments[42] = {**github.comment(42), field: value}
    with pytest.raises(ValueError, match='Mismatched'):
        progress.upsert_progress(github, REPO, payload(known_comment_id=42))
    assert github.writes == []


def test_discovery_mismatch_fails_closed():
    github = GitHub()
    github.comments[42] = {**github.comment(42), 'issue_url': f'{BASE}/repos/other/repo/issues/123'}
    with pytest.raises(ValueError, match='repository/issue'):
        progress.upsert_progress(github, REPO, payload())
    assert github.writes == []


@pytest.mark.parametrize('change', [{'pull_request': {}}, {'number': 999}, {'url': 'https://evil.test/issue'},
                                    {'html_url': f'https://github.com/{REPO}/pull/123'}])
def test_issue_and_pr_target_validation(change):
    github = GitHub()
    github.issue.update(change)
    with pytest.raises(ValueError, match='exact configured issue'):
        progress.upsert_progress(github, REPO, payload())
    assert github.writes == []


def test_discovery_pagination_cap_never_assumes_absence(monkeypatch):
    github = GitHub()
    monkeypatch.setattr(progress, 'MAX_PAGES', 2)
    github.list_override = lambda req: httpx.Response(200, json=[github.comment(i, 'ordinary') for i in range(100)])
    with pytest.raises(ValueError, match='pagination bound'):
        progress.upsert_progress(github, REPO, payload())
    assert github.writes == []
    assert len(github.calls) == 3


def test_marker_on_later_page_is_recovered_without_following_link_url():
    github = GitHub()
    github.comments[42] = github.comment(42)
    def listing(request):
        if request.url.params['page'] == '1':
            return httpx.Response(200, json=[github.comment(200+i, 'ordinary') for i in range(100)],
                                  headers={'Link': '<https://evil.test>; rel="next"'})
        return httpx.Response(200, json=[github.comments[42]])
    github.list_override = listing
    assert progress.upsert_progress(github, REPO, payload())['comment_id'] == 42
    assert [method for method, _ in github.writes] == ['PATCH']


def test_comment_changed_between_discovery_and_patch_is_rejected():
    github = GitHub()
    github.comments[42] = github.comment(42)
    github.get_override = lambda number: {**github.comment(number), 'body': 'changed marker'}
    with pytest.raises(ValueError, match='marker'):
        progress.upsert_progress(github, REPO, payload())
    assert github.writes == []


def test_postcondition_mismatch_never_reports_success():
    github = GitHub()
    github.after_write = lambda raw: raw.update(body=raw['body'] + '\ndrift')
    with pytest.raises(ValueError, match='postcondition'):
        progress.upsert_progress(github, REPO, payload())


def test_overlapping_requests_are_serialized_through_uncertain_create():
    github = GitHub()
    entered, finish = Event(), Event()
    def block():
        entered.set()
        assert finish.wait(5)
    github.before_create = block
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(progress.upsert_progress, github, REPO, payload())
        assert entered.wait(5)
        try:
            with pytest.raises(RuntimeError, match='in flight'):
                progress.upsert_progress(github, REPO, payload())
        finally:
            finish.set()
        assert first.result()['state'] == 'created'
    assert len(github.comments) == 1


@pytest.mark.parametrize('change', [
    {'body': '<!-- PCP:PLAN-PROGRESS:spoof -->'}, {'body': '<!-- other -->'},
    {'body': 'PCP:CONTINUITY:START'}, {'body': '音' * 4096}, {'body': 'x' * (12*1024)},
    {'handoff_key': 'a'*64}, {'issue_number': 0}, {'issue_number': True},
    {'issue_number': '123'}, {'known_comment_id': True}, {'known_comment_id': -1},
    {'repository': 'evil/repo'}, {'token': 'secret'}, {'url': 'https://evil.test'},
])
def test_request_rejects_unbounded_or_arbitrary_identity(change):
    with pytest.raises(ValidationError):
        payload(**change)


def test_endpoint_auth_project_resolution_and_sanitized_failures(monkeypatch):
    github = GitHub()
    seen = []
    monkeypatch.setenv('PLATFORM_INTERNAL_TOKEN', 'internal-test')
    def repository(project_id):
        seen.append(project_id)
        return github, REPO
    monkeypatch.setattr(bridge, '_repository', repository)
    app = FastAPI()
    app.include_router(bridge.router)
    client = TestClient(app)
    path = '/v1/github/pm-bridge/progress'
    body = payload().model_dump()
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert seen == []
    headers = {'Authorization': 'Bearer internal-test'}
    github.uncertain = '503'
    failure = client.post(path, json=body, headers=headers)
    assert failure.status_code == 502 and 'secret' not in failure.text
    result = client.post(path, json=body, headers=headers)
    assert result.status_code == 200 and result.json()['state'] == 'recovered'
    assert seen == ['demo', 'demo'] and len(github.comments) == 1
    monkeypatch.delenv('PLATFORM_INTERNAL_TOKEN')
    assert client.post(path, json=body, headers=headers).status_code == 503
