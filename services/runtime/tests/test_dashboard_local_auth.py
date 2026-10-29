"""Local-only authentication exception: real startup latch and HTTP boundaries."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy

import httpx
import pytest

from app import main
from app.dashboard import _require_session
from test_dashboard_local import ReadStore, held_row

ORIGIN = 'https://localhost:18443'


@pytest.fixture
def observer(monkeypatch):
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE', 'pcp_local_dashboard')
    monkeypatch.setenv('PCP_LOCAL_DASHBOARD_AUTH', 'loopback_readonly')
    monkeypatch.delenv('DASHBOARD_READ_TOKEN', raising=False)
    monkeypatch.setattr(main, 'projects_doc', lambda: {'projects': {'pcp-local': {}}})
    monkeypatch.setattr(main, 'harden_runtime_process_secret_boundary', lambda: None)
    def forbidden(*args, **kwargs):
        pytest.fail('Observer attempted a schema, worker, orchestration or model operation')
    for target, name in [(main.storage, 'init'), (main.engine, 'start'),
                         (main.plan_orchestrator.store, 'ensure')]:
        monkeypatch.setattr(target, name, forbidden)
    store = ReadStore([held_row(), {**held_row(), 'id': 'a'*32, 'project_id': 'foreign'}])
    monkeypatch.setattr(main.storage, 'connect', store.connect)
    monkeypatch.setattr(main.storage, 'events_after', store.events_after)
    return store


@asynccontextmanager
async def client(*, peer='127.0.0.1', lifespan=True):
    transport = httpx.ASGITransport(app=main.app, client=(peer, 12345))
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as http:
        if lifespan:
            async with main.lifespan(main.app):
                yield http
        else:
            yield http


def test_fresh_local_observer_reads_without_token_form_or_cookie(observer):
    before = deepcopy(observer.jobs)
    async def run():
        async with client() as c:
            page = await c.get('/dashboard')
            assert page.status_code == 200
            assert '<form' not in page.text and 'Dashboard read token' not in page.text
            assert '/v1/dashboard/session' not in page.text
            assert page.headers['cache-control'] == 'no-store'
            assert page.headers['content-security-policy'] == "frame-ancestors 'none'"
            for headers in ({}, {'Origin': ORIGIN, 'Sec-Fetch-Site': 'same-origin'}):
                snapshot = await c.get('/v1/dashboard/snapshot', headers=headers)
                assert snapshot.status_code == 200
                assert [j['id'] for j in snapshot.json()['jobs']] == [held_row()['id']]
                assert 'set-cookie' not in snapshot.headers
            events = await c.get('/v1/dashboard/jobs/'+held_row()['id']+'/events')
            assert events.status_code == 200 and events.json()['events'] == []
            assert not c.cookies and 'set-cookie' not in page.headers
    asyncio.run(run())
    assert observer.jobs == before
    assert observer.trace and all(sql.startswith(('SELECT', 'SET TRANSACTION')) for sql, _ in observer.trace)
    assert not main.app.state.pcp_local_dashboard_ready
    assert main.app.state.pcp_local_dashboard_auth is None


@pytest.mark.parametrize('peer', ['192.168.1.50', '172.22.0.2', 'localhost', '::ffff:127.0.0.1'])
def test_remote_peer_cannot_read_even_with_local_headers(observer, peer):
    async def run():
        async with client(peer=peer) as c:
            for path in ('/dashboard', '/v1/dashboard/snapshot', '/health'):
                assert (await c.get(path)).status_code == 403
    asyncio.run(run())
    assert not observer.trace


@pytest.mark.parametrize('headers', [
    {'Host': 'localhost.attacker.invalid:18443'}, {'Host': '127.0.0.1:18443'},
    {'Host': 'localhost'}, {'Host': 'localhost:18444'},
    {'Origin': 'https://attacker.invalid'}, {'Origin': 'null'},
    {'Origin': 'http://localhost:18443'}, {'Origin': ORIGIN+'/'},
    {'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'},
    {'Forwarded': 'for=127.0.0.1;proto=https;host=localhost:18443'},
    {'X-Forwarded-For': '127.0.0.1'}, {'X-Forwarded-Host': 'localhost:18443'},
    {'X-Forwarded-Proto': 'https'}, {'X-Real-IP': '127.0.0.1'},
    [('Host', 'localhost:18443'), ('Host', 'evil.invalid')],
    [('Origin', ORIGIN), ('Origin', ORIGIN)],
])
def test_rebinding_cross_origin_and_proxy_spoof_are_denied_before_db(observer, headers):
    async def run():
        async with client() as c:
            response = await c.get('/v1/dashboard/snapshot', headers=headers)
            assert response.status_code == 403
            assert 'access-control-allow-origin' not in response.headers
    asyncio.run(run())
    assert not observer.trace


def test_controls_sessions_and_foreign_project_remain_denied(observer):
    async def run():
        async with client() as c:
            for method, path in [
                ('POST','/v1/dashboard/session'), ('DELETE','/v1/dashboard/session'),
                ('POST','/v1/dashboard/control-session'), ('GET','/v1/dashboard/quota'),
                ('GET','/v1/dashboard/project-previews'), ('POST','/v1/intake'),
                ('GET','/v1/jobs'), ('POST','/v1/pcp-local/run-once'),
                ('POST','/v1/pcp-local/deliver'), ('POST','/v1/pcp-local/retire'),
                ('GET','/v1/dashboard/jobs/'+'b'*32+'/preview'),
                ('OPTIONS','/v1/dashboard/snapshot'),
            ]:
                r = await c.request(method, path)
                assert r.status_code == 403 and 'set-cookie' not in r.headers
            for suffix in ('events', 'stream'):
                assert (await c.get('/v1/dashboard/jobs/'+'a'*32+'/'+suffix)).status_code == 404
    asyncio.run(run())


@pytest.mark.parametrize('startup,auth,token', [
    ('normal','loopback_readonly',''), ('inspect','loopback_readonly',''),
    ('pcp_local_worker','loopback_readonly',''), ('pcp_local_inspect','loopback_readonly',''),
    ('pcp_local_dashboard','', ''), ('pcp_local_dashboard','none',''),
    ('pcp_local_dashboard','loopback_readonly','leftover-token'),
])
def test_invalid_configuration_stops_before_side_effects(observer, monkeypatch, startup, auth, token):
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE', startup)
    monkeypatch.setenv('PCP_LOCAL_DASHBOARD_AUTH', auth)
    monkeypatch.setenv('DASHBOARD_READ_TOKEN', token)
    async def run():
        with pytest.raises(RuntimeError, match='authentication configuration'):
            async with main.lifespan(main.app):
                pytest.fail('Invalid startup succeeded')
        async with client(lifespan=False) as c:
            assert (await c.get('/v1/dashboard/snapshot')).status_code == 403
    asyncio.run(run())
    assert not observer.trace


def test_opt_in_requires_successful_latch_and_cannot_be_flipped(observer, monkeypatch):
    async def run():
        async with client(lifespan=False) as c:
            assert (await c.get('/dashboard')).status_code == 403
        async with client() as c:
            monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE', 'normal')
            assert (await c.get('/v1/dashboard/snapshot')).status_code == 403
            monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE', 'pcp_local_dashboard')
            monkeypatch.setenv('PCP_LOCAL_DASHBOARD_AUTH', 'token')
            assert (await c.get('/v1/dashboard/snapshot')).status_code == 403
        async with client(lifespan=False) as c:
            assert (await c.get('/v1/dashboard/snapshot')).status_code == 403
    asyncio.run(run())


def test_failed_registry_cannot_latch_observer(observer, monkeypatch):
    monkeypatch.setattr(main, 'projects_doc', lambda: {'projects': {'foreign': {}}})
    async def run():
        with pytest.raises(RuntimeError, match='singleton'):
            async with main.lifespan(main.app):
                pytest.fail('Foreign registry accepted')
        async with client(lifespan=False) as c:
            assert (await c.get('/dashboard')).status_code == 403
    asyncio.run(run())


@pytest.mark.parametrize('explicit', [True, False])
def test_default_and_explicit_token_mode_preserve_secure_login(observer, monkeypatch, explicit):
    if explicit:
        monkeypatch.setenv('PCP_LOCAL_DASHBOARD_AUTH', 'token')
    else:
        monkeypatch.delenv('PCP_LOCAL_DASHBOARD_AUTH')
    monkeypatch.setenv('DASHBOARD_READ_TOKEN', 'fixture-read-secret')
    async def run():
        async with client() as c:
            assert 'Dashboard read token' in (await c.get('/dashboard')).text
            assert (await c.get('/v1/dashboard/snapshot')).status_code == 401
            login = await c.post('/v1/dashboard/session', json={'token': 'fixture-read-secret'})
            assert login.status_code == 200
            assert all(flag in login.headers['set-cookie'] for flag in ('Secure','HttpOnly','SameSite=strict'))
            assert (await c.get('/v1/dashboard/snapshot')).status_code == 200
            monkeypatch.setenv('PCP_LOCAL_DASHBOARD_AUTH', 'loopback_readonly')
            assert (await c.get('/v1/dashboard/snapshot')).status_code == 403
    asyncio.run(run())
    # Shared/privileged authentication was never relaxed by the new env mode.
    with pytest.raises(Exception) as error:
        _require_session(None)
    assert error.value.status_code == 401


def test_local_sse_uses_same_scope_guard_and_sanitized_events(observer, monkeypatch):
    from starlette.requests import Request
    from datetime import datetime, timezone
    monkeypatch.setattr(main.storage, 'events_after', lambda *a, **kw: [
        dict(id=1, job_id=held_row()['id'], event_type='runtime_activity', phase='verified',
             level='info', message='GITHUB_TOKEN=ghp_12345678901234567',
             created_at=datetime.now(timezone.utc), data={})])
    endpoint = next(r.endpoint for r in main.app.routes if getattr(r, 'path', '') == '/v1/dashboard/jobs/{job_id}/stream')
    async def run():
        async def receive():
            return {'type': 'http.request', 'body': b''}
        async with client() as c:
            replay = (await c.get('/v1/dashboard/jobs/'+held_row()['id']+'/events')).json()
            assert 'ghp_' not in str(replay) and 'redacted' in str(replay)
            assert replay['events'][0]['data'] == {}
        async with main.lifespan(main.app):
            request = Request({'type':'http', 'method':'GET', 'path':'/v1/dashboard/jobs/'+held_row()['id']+'/stream',
                'app':main.app, 'client':('::1',12345), 'headers':[(b'host',b'localhost:18443')]}, receive=receive)
            response = await endpoint(request=request, job_id=held_row()['id'], after=0, pcp_dashboard_session=None)
            event = await anext(response.body_iterator)
            assert 'event: activity' in event and 'ghp_' not in event and 'redacted' in event
            assert 'set-cookie' not in response.headers
            await response.body_iterator.aclose()
    asyncio.run(run())
