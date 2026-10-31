"""Real release Git ranges/private files and actual Draft-PR transport fences."""
from copy import deepcopy
import hashlib
import json
import time
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from app import pcp_local_review_repair as review,pcp_local_claim_recovery as release_binding,main
from test_pcp_local_claim_recovery import release  # noqa:F401


@pytest.mark.parametrize('drift',['none','old_flag','expiry','patch_hash','path','owner','verifier','range','source','version'])
def test_exact_private_review_release(release,tmp_path,monkeypatch,drift):
    s=release;a=deepcopy(s.a);mapping=a.pop('claim_recovery');job='a'*32;head='e'*40;target='tests/test_pcp_light_pilot.py'
    before=dict(receipt=dict(state='running',generation=2,job_id=job,issue_number=848,base_sha=a['base_sha'],body_sha256='b'*64,baseline_revision='fixture',baseline_source_commit=a['base_sha'],allowed_paths=[target]),
        job=dict(id=job,status='blocked',error='pcp_local_hosted_ci_not_passed',progress=dict(model_calls=1,test_runs=2,delivery_attempts=1),
            checkpoint={'pcp_local_execution':dict(state='verified',commit=head,lease_generation=4)},result=dict(commit=head,delivery_finalized=False,delivery=dict(state='ci_failure',pull_request={'number':7}))),
        lease=dict(state='active',owner_job_id=job,generation=4))
    a.update({k:before['receipt'][k] for k in ('issue_number','body_sha256','baseline_revision','baseline_source_commit')})
    original=tmp_path/'original.json';original.write_text(json.dumps(a));original.chmod(0o600)
    patch=tmp_path/'test.patch';patch.write_bytes(b'exact independently approved fixture patch');patch.chmod(0o600)
    plan=dict(path=target,patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),before={},before_file_sha256='a'*64,after_file_sha256='b'*64,candidate={'identity':{'parent':head}})
    value=dict(version=1,decision_id='fixture-review-repair',execution_record='https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-1',not_before=time.time()-1,expires_at=time.time()+600,
        original_activation_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),before=before,repair_source=mapping['repair_source'],repair_commits=mapping['repair_commits'],repair_paths=mapping['repair_paths'],roles=mapping['roles'],verification_seconds=60,patch_plan=plan,pr_number=7,expected_head=head,review_id=80,review_body_sha256='f'*64)
    if drift=='old_flag':monkeypatch.setenv('PCP_LOCAL_HELD_VERIFY_ENABLED','owner-approved')
    elif drift=='expiry':value['expires_at']=time.time()-1
    elif drift=='patch_hash':plan['patch_sha256']='f'*64
    elif drift=='path':plan['path']='../escape'
    elif drift=='owner':before['lease']['owner_job_id']='e'*32
    elif drift=='verifier':value['roles']['verifier']['source_commit']=mapping['repair_source']
    elif drift=='range':value['repair_paths']=['unapproved.py']
    elif drift=='source':value['roles']['runtime']['source_commit']=a['base_sha']
    elif drift=='version':value['version']=2
    permit=tmp_path/'permit.json';permit.write_text(json.dumps(value));permit.chmod(0o600)
    monkeypatch.setattr(review,'PERMIT',permit);monkeypatch.setattr(review,'ORIGINAL',original);monkeypatch.setattr(review,'PATCH',patch);monkeypatch.setenv('PCP_LOCAL_REVIEW_REPAIR_ENABLED','owner-approved')
    def check():
        actual=review.activation();assert actual['local_review_repair']['before']==before
        return release_binding.release(actual,s.root,s.root,s.inspect,binding_key='local_review_repair')
    if drift=='none':assert check()==mapping['repair_source']
    else:
        with pytest.raises(HTTPException):check()


@pytest.mark.parametrize('state',['exact','different_pr','absent','closed','non_draft'])
def test_same_draft_pr_is_a_fence_not_a_creation_hint(monkeypatch,state):
    job='a'*32;head='b'*40;repo=main._PCP_REPOSITORY;calls=[]
    pr=dict(number=7,state='open',merged=False,draft=True,html_url=f'https://github.com/{repo}/pull/7',head=dict(sha=head,ref='ai/'+job[:12],repo={'full_name':repo}),base={'ref':'main'})
    if state=='different_pr':pr['number']=8
    if state=='closed':pr['state']='closed'
    if state=='non_draft':pr['draft']=False
    def handler(request):
        calls.append(request.method)
        if request.method=='GET':return httpx.Response(200,json=[] if state in ('absent','closed') else [pr])
        assert request.method=='PATCH' and request.url.path.endswith('/pulls/7')
        assert json.loads(request.content)=={'body':'latest pinned proof/context'}
        return httpx.Response(200,json=pr)
    delivery=SimpleNamespace(base='https://fixture.invalid',assert_branch_commit=lambda *a:None,_client=lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(main,'_pcp_identity',lambda *a:({'local_review_repair':{'pr_number':7}},dict(autonomy={'allow_create_pr':True}),None));monkeypatch.setattr(main,'_github_context',lambda cfg:(delivery,repo))
    payload=main.PullRequestRequest(job_id=job,project_id='pcp-local',branch='ai/'+job[:12],expected_commit=head,title='task',body='latest pinned proof/context',expected_pr_number=7)
    if state=='exact':assert main._pcp_draft_pr(payload)['number']==7 and calls==['GET','PATCH']
    else:
        with pytest.raises(HTTPException):main._pcp_draft_pr(payload)
        assert calls==['GET']


@pytest.mark.parametrize('drift',['none','parent','tree','pr','path'])
def test_real_git_guarded_append_uses_same_private_branch(tmp_path,monkeypatch,drift):
    import subprocess
    repo=tmp_path/'workspace';repo.mkdir();job='a'*32;branch='ai/'+job[:12];target='tests/test_pcp_light_task.py'
    def git(*a):return subprocess.check_output(['git','-C',str(repo),*a],text=True).strip()
    git('init','-b',branch);git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    path=repo/target;path.parent.mkdir();path.write_text('original\n');git('add','.');git('commit','-m','base');source=git('rev-parse','HEAD')
    path.write_text('delivered\n');git('commit','-am','original verified task');old=git('rev-parse','HEAD')
    bare=tmp_path/'remote.git';subprocess.run(['git','init','--bare',str(bare)],check=True,capture_output=True)
    git('push',str(bare),old+':refs/heads/'+branch)
    path.write_text('reviewed test-only correction\n');git('commit','-am','approved test repair');head=git('rev-parse','HEAD');tree=git('rev-parse','HEAD^{tree}')
    if drift=='parent':
        merge=subprocess.check_output(['git','-C',str(repo),'commit-tree',tree,'-p',old,'-p',source],input=b'unexpected parents\n').decode().strip();git('update-ref','refs/heads/'+branch,merge);head=merge
    binding=dict(pr_number=7,expected_head=old,patch_plan=dict(path=target,candidate={'identity':{'tree':tree}}))
    if drift=='tree':binding['patch_plan']['candidate']['identity']['tree']='f'*40
    elif drift=='path':binding['patch_plan']['path']='other.py'
    cfg=dict(base_branch='main',runtime=dict(branch_prefix='ai',workspace_mode='isolated_clone'),autonomy=dict(allow_push_ai_branch=True,allow_create_pr=True))
    monkeypatch.setattr(main,'project',lambda _:cfg);monkeypatch.setattr(main,'_validate_workspace',lambda *a:repo)
    monkeypatch.setattr(main,'_workspace_instance_mode',lambda *a,**kw:'isolated_clone')
    monkeypatch.setattr(main,'_pcp_identity',lambda *a:({'local_review_repair':binding},cfg,None))
    monkeypatch.setattr(main,'_source_origin',lambda cfg:(repo,'https://github.com/'+main._PCP_REPOSITORY+'.git'))
    monkeypatch.setattr(main,'github_push_url',lambda repository:str(bare))
    class Delivery:
        configured=True;token='fixture-only-token'
        def verify_review_repair(self,**kw):
            actual=subprocess.check_output(['git','--git-dir',str(bare),'rev-parse','refs/heads/'+branch],text=True).strip()
            if actual!=kw['expected_commit']:raise RuntimeError('private remote head changed')
            return {'number':7,'head':actual}
    monkeypatch.setattr(main,'GitHubDelivery',Delivery)
    payload=main.PublishBranchRequest(job_id=job,project_id='pcp-local',workspace=str(repo),branch=branch,source_commit=source,expected_commit=head,
        review_repair_pr_number=8 if drift=='pr' else 7,review_repair_previous_commit=old)
    if drift=='none':assert main.publish_branch(payload)['commit']==head
    else:
        with pytest.raises(HTTPException):main.publish_branch(payload)
    observed=subprocess.check_output(['git','--git-dir',str(bare),'rev-parse','refs/heads/'+branch],text=True).strip()
    assert observed==(head if drift=='none' else old)
