"""Real release Git/private files; Docker/GitHub inputs are synthetic FIXTURE."""
from copy import deepcopy
import hashlib
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from app import main,pcp_local_finalization as f,pcp_local_review_repair as repair
from app.pcp_local_claim_recovery import digest
from app.pcp_local_observer import configuration_digest
from test_pcp_local_claim_recovery import release  # noqa:F401


@pytest.fixture
def finalization(release,tmp_path,monkeypatch):
    s=release; original=deepcopy(s.a);mapping=original.pop('claim_recovery');job='a'*32;head='b'*40;diff='d'*64
    original.update(project_id='pcp-local',repository=main._PCP_REPOSITORY,issue_number=848,
        body_sha256='e'*64,baseline_revision='fixture-H',baseline_source_commit=original['base_sha'],
        pm_login='fixture-pm',runtime_network=s.root.name+'-private')
    receipt=dict(state='running',generation=2,job_id=job,issue_number=848,base_sha=original['base_sha'],
        body_sha256=original['body_sha256'],baseline_revision='fixture-H',baseline_source_commit=original['base_sha'],allowed_paths=['tests/test_pcp_light_pilot.py'])
    oldjob=dict(id=job,status='blocked',error='pcp_local_hosted_ci_not_passed',progress=dict(model_calls=1,test_runs=2,delivery_attempts=1),
        checkpoint={'pcp_local_execution':dict(state='verified',commit='c'*40,lease_generation=4)},
        result=dict(commit='c'*40,delivery_finalized=False,delivery=dict(state='ci_failure',pull_request={'number':850})))
    before=dict(job=oldjob,receipt=receipt,lease=dict(state='active',owner_job_id=job,generation=4))
    patch=tmp_path/'test.patch';patch.write_bytes(b'FIXTURE exact old patch');patch.chmod(0o600)
    old=dict(version=1,decision_id='fixture-expired-repair',execution_record='https://github.com/'+main._PCP_REPOSITORY+'/issues/835#issuecomment-1',
        not_before=time.time()-1200,expires_at=time.time()-600,original_activation_sha256='',before=before,
        repair_source=mapping['repair_source'],repair_commits=mapping['repair_commits'],repair_paths=mapping['repair_paths'],roles=deepcopy(mapping['roles']),verification_seconds=60,
        patch_plan=dict(path=receipt['allowed_paths'][0],patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),before={},before_file_sha256='0'*64,after_file_sha256='1'*64,
            candidate=dict(identity={'parent':'c'*40},diff={'diff_hash':diff})),pr_number=850,expected_head='c'*40,review_id=80,review_body_sha256='e'*64)
    origin=tmp_path/'original.json';origin.write_text(json.dumps(original));origin.chmod(0o600)
    old['original_activation_sha256']=hashlib.sha256(origin.read_bytes()).hexdigest()
    history=tmp_path/'old.json';history.write_text(json.dumps(old));history.chmod(0o600)
    current=deepcopy(before);j=current['job'];j.update(source_commit=original['base_sha'],error='awaiting_independent_pm_review',progress=dict(model_calls=1,test_runs=4,delivery_attempts=2))
    verification={'passed':True,'test_runs':2};e=j['checkpoint']['pcp_local_execution'];e.update(commit=head,verified_tree=old['patch_plan']['candidate']['identity'],diff={'diff_hash':diff},verification=verification)
    j['checkpoint']['pcp_local_review_repair']=dict(permit_sha256=digest(old),original=before,state='awaiting_pm_review',verification=verification)
    j['result']=dict(commit=head,diff={'diff_hash':diff},verification=verification,delivery_finalized=False,delivery=dict(state='ci_success',pull_request={'number':850}))
    report=dict(schema_version=1,job_id=job,source_commit=original['base_sha'],expected_head=head,branch='ai/'+job[:12],baseline_revision='fixture-H',pr_number=850,ci_run_id=9,diff_hash=diff,
        verdict='pass',findings=[],summary='FIXTURE independent exact reviewed synthetic task evidence only.')
    body='<!-- coding-platform:pcp-local-pm-review:v1 -->\n'+json.dumps(report)
    a=dict(version=1,decision_id='fixture-finalization-only',execution_record='https://github.com/'+main._PCP_REPOSITORY+'/issues/835#issuecomment-2',not_before=time.time()-1,expires_at=time.time()+600,
        original_repair_raw_sha256=hashlib.sha256(history.read_bytes()).hexdigest(),original_repair_digest=digest(old),before=current,workspace_sha256='a'*64,expected_head=head,diff_hash=diff,pr_number=850,
        review=dict(id=81,body_sha256=hashlib.sha256(body.encode()).hexdigest(),ci_run_id=9),repair_source=mapping['repair_source'],repair_commits=mapping['repair_commits'],repair_paths=mapping['repair_paths'],roles=mapping['roles'],
        resources=dict(worker_ids={},database=dict(container_id='4'*64,image_id='sha256:'+'5'*64,configuration_sha256=''),network_id='6'*64,observer_binding_sha256=digest(None)))
    for i,role in enumerate(('runtime','executor','router'),1):
        name=s.root.name+'-'+{'runtime':'coding-runtime','executor':'ddev-executor','router':'router'}[role]
        row=s.items['container',name];row['Id']=str(i)*64
        if role=='router':row['State']['Running']=False
        a['roles'][role]['configuration_sha256']=configuration_digest(row)
        s.items['container',row['Id']]=row;a['resources']['worker_ids'][role]=row['Id']
    db=dict(Id='4'*64,Name='/'+s.root.name+'-db',State={'Running':True},Image='sha256:'+'5'*64,Config={},HostConfig={},Mounts=[])
    a['resources']['database']['configuration_sha256']=configuration_digest(db);s.items['container',db['Id']]=db
    s.items['network','6'*64]=dict(Id='6'*64,Name=original['runtime_network'],Containers={})
    file=tmp_path/'finalization.json'
    def seal():file.write_text(json.dumps(a));file.chmod(0o600)
    seal()
    s.git('checkout','--detach',original['base_sha'])
    monkeypatch.setattr(f,'PERMIT',file);monkeypatch.setattr(f,'REPAIR',history)
    monkeypatch.setattr(repair,'PERMIT',history);monkeypatch.setattr(repair,'ORIGINAL',origin);monkeypatch.setattr(repair,'PATCH',patch)
    monkeypatch.setenv(f.FLAG,'owner-approved')
    return SimpleNamespace(s=s,a=a,file=file,seal=seal,body=body,report=report,history=history,original=origin,patch=patch,job=job,head=head)


@pytest.mark.parametrize('drift',['none','expired','revoked','wrong_raw','wrong_digest','history','proof','head','role','worker_id','config','db','network','router_running','recursive','canonical','canonical_dirty','original','patch','execution_flag'])
def test_private_authority_and_exact_release_resources(finalization,monkeypatch,drift):
    v=finalization;s=v.s;a=v.a
    if drift=='expired':a['expires_at']=time.time()-1;v.seal()
    elif drift=='revoked':
        p=f.Authority();v.file.unlink()
        with pytest.raises((HTTPException,OSError)):p.revalidate()
        return
    elif drift in ('wrong_raw','wrong_digest'):a['original_repair_raw_sha256' if drift=='wrong_raw' else 'original_repair_digest']='0'*64;v.seal()
    elif drift=='history':a['before']['job']['checkpoint']['pcp_local_review_repair']['original']['job']['progress']['model_calls']=0;v.seal()
    elif drift=='proof':a['before']['job']['checkpoint']['pcp_local_execution']['verified_tree']={'parent':'0'*40};v.seal()
    elif drift=='head':a['expected_head']='0'*40;v.seal()
    elif drift=='role':a['roles']['runtime']['source_commit']=s.a['base_sha'];v.seal()
    elif drift=='worker_id':a['resources']['worker_ids']['runtime']='7'*64;v.seal()
    elif drift=='config':s.items['container','1'*64]['Config']['unapproved']='extra'
    elif drift=='db':s.items['container','4'*64]['Image']='sha256:'+'0'*64
    elif drift=='network':s.items['network','6'*64]['Id']='7'*64
    elif drift=='router_running':s.items['container','3'*64]['State']['Running']=True
    elif drift=='recursive':s.items['container','1'*64]['HostConfig']['Mounts'][0]['BindOptions']={}
    elif drift=='canonical':s.git('checkout','--detach',a['repair_source'])
    elif drift=='canonical_dirty':(s.root/'services/runtime/app.py').write_text('unapproved source')
    elif drift=='original':v.original.write_text('{}')
    elif drift=='patch':v.patch.write_bytes(b'wrong')
    elif drift=='execution_flag':monkeypatch.setenv('PCP_LOCAL_TASK_SOURCE_ENABLED','owner-approved')
    def check():
        p=f.Authority();p.resources(s.root,s.root,s.inspect);p.revalidate()
    if drift=='none':check()
    else:
        with pytest.raises((HTTPException,OSError,KeyError)):check()


@pytest.mark.parametrize('fault',['none','head','review','review_body','review_id','diff','ci','step','main','revoke'])
def test_actual_pm_endpoint_reads_exact_review_and_executed_suites(finalization,monkeypatch,fault):
    v=finalization;calls=[];s=v.s
    def handler(request):
        calls.append(request.method);assert request.method=='GET'
        path=request.url.path
        if path.endswith('/git/ref/heads/main'):result={'object':{'sha':v.a['repair_source'] if fault!='main' else '0'*40}}
        elif path.endswith('/reviews/81'):
            result=dict(id=81,commit_id=v.head,user={'login':'fixture-pm'},state='COMMENTED',body=v.body)
            if fault=='review':result['user']['login']='foreign'
            elif fault=='review_id':result['id']=82
            elif fault=='review_body':result['body']+=' '
            elif fault=='diff':result['body']=v.body.replace(v.a['diff_hash'],'0'*64)
        elif path.endswith('/pulls/850'):
            result=dict(state='open',merged=False,head=dict(sha=v.head if fault!='head' else '0'*40,ref='ai/'+v.job[:12],repo={'full_name':main._PCP_REPOSITORY}),base={'ref':'main'})
        elif path.endswith('/actions/runs'):
            result={'workflow_runs':[dict(id=9,name='tests',head_sha=v.head,event='pull_request',status='completed',conclusion='success' if fault!='ci' else 'failure')]}
        else:
            assert path.endswith('/actions/runs/9/jobs')
            result={'jobs':[dict(name=name,conclusion='success',steps=[dict(name='Run tests',conclusion='skipped' if fault=='step' else 'success')]) for name in (
                'structure-tests','python-tests (services/router)','python-tests (services/runtime)','python-tests (services/ddev-executor)')]}
            if fault=='revoke':v.file.unlink()
        return httpx.Response(200,json=result)
    monkeypatch.setattr(main,'_pcp_identity',lambda *args,**kwargs:(f.Authority().activation,{'path':str(s.root)},s.root))
    monkeypatch.setattr(main,'_pcp_docker',s.inspect)
    monkeypatch.setattr(main,'_github_context',lambda cfg:(SimpleNamespace(base='https://fixture.invalid',_client=lambda:httpx.Client(transport=httpx.MockTransport(handler))),main._PCP_REPOSITORY))
    monkeypatch.setattr(main,'github_ci',lambda *args:dict(state='success'))
    payload=main.PcpLocalReviewRequest(job_id=v.job,source_commit=s.a['base_sha'],expected_head=v.head,pr_number=850,review_id=81,activation_digest=digest(f.Authority().activation))
    if fault=='none':
        result=main.pcp_local_review(payload);assert result['review_id']==81 and result['ci_run_id']==9 and len(result['suites'])==4
    else:
        with pytest.raises((HTTPException,OSError)):main.pcp_local_review(payload)
    assert calls and set(calls)=={'GET'}


def test_finalization_never_supplies_execution_activation(finalization):
    for fn in (main._pcp_activation,repair.activation):
        with pytest.raises(HTTPException):fn()
