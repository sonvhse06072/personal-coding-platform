"""Actual authenticated routes and bounded one-POST operator protocol."""
import asyncio
import json
from http.client import IncompleteRead
import httpx
import pytest
from app import pcp_local_task_queue as q


@pytest.mark.parametrize('fault',['none','lost_ack','changed_head','changed_patch','after_unavailable'])
def test_single_post_and_exact_read_only_reconciliation(monkeypatch,capsys,fault):
    calls=[];job='a'*32
    def request(path,payload=None):
        assert path=='review-repair';calls.append((path,payload))
        original=dict(job_id=job,permit_sha256='b'*64,expected_head='c'*40,pr_number=7,patch_sha256='d'*64,ready=True,state='eligible')
        if payload:
            assert payload=={k:original[k] for k in ('job_id','permit_sha256','expected_head','pr_number','patch_sha256')}
            if fault=='lost_ack':raise IncompleteRead(b'private',12)
            return {'state':'awaiting_pm_review'}
        if len(calls)>1:
            original.update(ready=False,state='verifying')
            if fault=='changed_head':original['expected_head']='e'*40
            if fault=='changed_patch':original['patch_sha256']='e'*64
            if fault=='after_unavailable':raise OSError('PRIVATE bearer')
        return original
    monkeypatch.setattr(q,'session_request',request)
    code=q.session_main(['review-repair','--job-id',job,'--apply','--json']);out=capsys.readouterr().out
    assert len(calls)==3 and sum(p is not None for _,p in calls)==1
    assert 'private' not in out.lower() and json.loads(out)['mutation_requests']==1
    assert code==(0 if fault in ('none','lost_ack') else 2)


def test_route_auth_identity_and_observer_boundaries(monkeypatch):
    from app import main,pcp_local_review_repair as repair
    calls=[]
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_worker');monkeypatch.setenv('RUNTIME_API_TOKEN','fixture-local-token')
    monkeypatch.setattr(main.app.state,'pcp_local_worker_ready',True,raising=False)
    payload=dict(job_id='a'*32,permit_sha256='b'*64,expected_head='c'*40,pr_number=7,patch_sha256='d'*64)
    async def operate(engine,*,apply=False,expected=None):calls.append((apply,expected));return dict(**payload,state='eligible',ready=True)
    monkeypatch.setattr(repair,'operate',operate)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as c:
            assert (await c.post('/v1/pcp-local/review-repair',json=payload)).status_code==401
            auth={'Authorization':'Bearer fixture-local-token'}
            assert (await c.get('/v1/pcp-local/review-repair',headers=auth)).status_code==200
            assert (await c.post('/v1/pcp-local/review-repair',headers=auth,json={**payload,'patch':'arbitrary shell'})).status_code==422
            assert (await c.post('/v1/pcp-local/review-repair',headers=auth,json=payload)).status_code==200
            assert (await c.get('/v1/pcp-local/readiness',headers=auth,params={'phase':'review-repair','job_id':'e'*32})).status_code==409
            monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_dashboard')
            assert (await c.post('/v1/pcp-local/review-repair',headers=auth,json=payload)).status_code==403
    asyncio.run(run());assert sum(apply for apply,_ in calls)==1


def test_fresh_admission_cannot_use_review_authority(monkeypatch):
    from app.pcp_local_worker_loop import source_worker_flags
    from app.pcp_local_task_queue import TaskStop
    monkeypatch.setenv('PCP_LOCAL_REVIEW_REPAIR_ENABLED','owner-approved')
    with pytest.raises(TaskStop,match='local_repair_admission_forbidden'):source_worker_flags()
