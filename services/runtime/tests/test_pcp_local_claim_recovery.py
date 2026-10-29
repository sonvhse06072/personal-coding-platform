"""Private claim recovery; no model, remote publication, or live ownership."""
from copy import deepcopy
import hashlib
import json
import time

import pytest

from app import pcp_local_worker_loop as worker
from app.pcp_local_task_queue import TaskStop
from test_pcp_local_worker_loop import fixture


def test_same_identity_recovery_has_supported_read_only_plan():
    from app import pcp_local_task_queue as recovery
    assert callable(recovery.plan) and callable(recovery.register)


@pytest.fixture
def permit(tmp_path, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from app import pcp_local_task_queue as r
    task, issue, _, facts = fixture()
    task = replace(task, baseline_source_commit=task.base_sha)
    before = {**worker.claimed_source_receipt(task), 'created_at': '2026-01-01T00:00:00+00:00',
              'updated_at': '2026-01-01T00:00:01+00:00'}
    original = {k: getattr(task, k) for k in ('project_id', 'repository', 'issue_number',
        'body_sha256', 'base_sha', 'baseline_revision', 'baseline_source_commit')}
    original.update(expires_at=1, runtime_image_id='sha256:'+'1'*64,
        verification_image='sha256:'+'1'*64, developer_permission_mode='bounded')
    original_path, permit_path = tmp_path/'original.json', tmp_path/'permit.json'
    raw = (json.dumps(original, indent=2)+'\n').encode()
    original_path.write_bytes(raw); original_path.chmod(0o600)
    repair = 'c'*40
    value = dict(version=1, decision_id='fixture-recovery-831',
        execution_record='https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-1',
        not_before=time.time()-10, expires_at=time.time()+1800,
        receipt_before=before, original_activation_sha256=hashlib.sha256(raw).hexdigest(),
        original_activation_digest=r.digest(original), repair_source=repair, repair_commits=[repair],
        repair_paths=['services/runtime/app/pcp_local_task_queue.py'],
        roles={role: dict(image_id='sha256:'+str(i)*64,
            source_commit=repair if role in ('runtime','executor') else task.base_sha,
            **({} if role=='verifier' else {'configuration_sha256': 'd'*64}))
            for i,role in enumerate(('verifier','runtime','executor','router'),1)})
    def save():
        permit_path.write_text(json.dumps(value));permit_path.chmod(0o600)
    save()
    monkeypatch.setattr(r,'PERMIT',permit_path);monkeypatch.setattr(r,'ORIGINAL',original_path)
    monkeypatch.setenv(r.FLAG,'owner-approved')
    return SimpleNamespace(task=task,issue=issue,facts=facts,value=value,original=original,
        original_path=original_path,permit_path=permit_path,save=save,load=r.RecoveryPermit)


def test_original_expiry_bytes_retained_and_actual_main_required(permit):
    from app.pcp_local_task_queue import verify_issue
    p=permit; loaded=p.load();raw=p.original_path.read_bytes()
    assert loaded.activation['expires_at']==1
    assert loaded.activation['runtime_image_id']==p.original['runtime_image_id']
    current={**p.issue,'main_sha':p.value['repair_source']}
    assert loaded.verify_issue(current)==p.task
    args={k:getattr(p.task,k) for k in ('issue_number','body_sha256','base_sha','baseline_revision','baseline_source_commit')}
    with pytest.raises(TaskStop,match='github_identity_or_main_changed'):verify_issue(current,**args)
    with pytest.raises(TaskStop):loaded.verify_issue(p.issue)
    assert p.original_path.read_bytes()==raw


@pytest.mark.parametrize('change', ['expiry','activation','world_readable','generation','baseline','pilot','verifier','runtime'])
def test_invalid_permit_fails_before_any_database_access(permit,change):
    p=permit
    if change=='expiry':p.value['expires_at']=time.time()-1
    elif change=='activation':p.original_path.write_text('{}')
    elif change=='generation':p.value['receipt_before']['generation']=2
    elif change=='baseline':p.value['receipt_before']['baseline_source_commit']='d'*40
    elif change=='pilot':p.value['repair_paths']=list(p.task.allowed_paths)
    elif change=='verifier':p.value['roles']['verifier']['image_id']='sha256:'+'a'*64
    elif change=='runtime':p.value['roles']['runtime']['source_commit']=p.task.base_sha
    p.save()
    if change=='world_readable':p.permit_path.chmod(0o644)
    with pytest.raises(TaskStop):p.load()


def test_permit_revocation_and_default_off(permit,monkeypatch):
    p=permit;loaded=p.load();p.value['decision_id']='replacement-decision';p.save()
    with pytest.raises(TaskStop,match='revoked'):loaded.require_fresh()
    monkeypatch.delenv('PCP_LOCAL_CLAIM_RECOVERY_ENABLED')
    with pytest.raises(TaskStop,match='disabled'):p.load()


def test_actual_repair_main_policy_is_not_an_ordinary_admission_bypass(permit,monkeypatch):
    from app.pcp_local_worker_admission import check_worker_admission
    from test_pcp_local_worker_loop import flags
    flags(monkeypatch)
    p=permit;facts=deepcopy(p.facts);facts['baseline']['source_commit']=p.task.base_sha
    facts['isolation']['current_main_sha']=p.value['repair_source']
    row={**worker.claimed_source_receipt(p.task),'state':'pending','generation':0,'job_id':None}
    assert check_worker_admission(p.task,receipt=row,recovery=p.load(),**facts)['can_start_agent'] is False
    with pytest.raises(TaskStop,match='workspace_or_lease'):check_worker_admission(p.task,receipt=row,**facts)
    with pytest.raises(TaskStop,match='private_permit'):check_worker_admission(p.task,receipt=row,recovery=p.value,**facts)


def test_http_entry_is_authenticated_default_off_and_observer_cannot_mutate(monkeypatch,tmp_path):
    import asyncio
    import httpx
    from app import main, pcp_local_task_queue as r
    monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_worker')
    monkeypatch.setenv('RUNTIME_API_TOKEN','fixture-token')
    monkeypatch.delenv(r.FLAG,raising=False)
    monkeypatch.setattr(main.app.state,'pcp_local_worker_ready',True,raising=False)
    monkeypatch.setattr(r,'PERMIT',tmp_path/'missing')
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            for method,path in [('GET','/v1/pcp-local/claim-recovery'),
                ('POST','/v1/pcp-local/claim-recovery/register'),('POST','/v1/pcp-local/claim-recovery/execute')]:
                assert (await client.request(method,path)).status_code==401
                response=await client.request(method,path,headers={'Authorization':'Bearer fixture-token'},
                    json={'owner_approved':True,'repair_source':'c'*40})
                assert response.status_code==409 and response.json()['detail']=='claim_recovery_disabled'
            monkeypatch.setenv('PCP_RUNTIME_STARTUP_MODE','pcp_local_dashboard')
            response=await client.post('/v1/pcp-local/claim-recovery/register',headers={'Authorization':'Bearer fixture-token'})
            assert response.status_code==403
    asyncio.run(check())


def test_operator_client_defaults_read_only_and_does_not_retry_uncertainty(monkeypatch,capsys):
    import urllib.request
    from app import pcp_local_task_queue as r
    monkeypatch.setenv('RUNTIME_API_TOKEN','private-fixture-token')
    calls=[]
    def unavailable(request,timeout):
        calls.append((request.method,request.full_url))
        from pathlib import Path
        command = json.loads(next(line[4:] for line in (Path(__file__).parents[1]/'Dockerfile').read_text().splitlines() if line.startswith('CMD ')))
        assert request.full_url.startswith('http://127.0.0.1:'+command[command.index('--port')+1]+'/')
        assert request.get_header('Authorization')=='Bearer private-fixture-token'
        raise OSError('private error detail must not escape')
    monkeypatch.setattr(urllib.request,'urlopen',unavailable)
    assert r.main([])==2 and len(calls)==1 and calls[0][0]=='GET'
    output=capsys.readouterr().out
    assert 'uncertain' in output and 'private' not in output
    assert r.main(['register'])==2 and len(calls)==2 and calls[-1][0]=='POST'
