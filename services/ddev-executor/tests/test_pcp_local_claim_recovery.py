"""Real temporary Git ancestry/ranges; Docker inspect is an explicit fixture."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
from fastapi import HTTPException
from app import pcp_local_claim_recovery as r


@pytest.fixture
def release(tmp_path):
    root=tmp_path/'pcp-local-recovery-test';root.mkdir()
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True).stdout.strip()
    git('init','-b','main');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    for path in ('services/router/app.py','services/runtime/app.py','tests/test_pcp_light_pilot.py'):
        file=root/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('original\n')
    git('add','.');git('commit','-m','original');source=git('rev-parse','HEAD')
    (root/'services/runtime/app.py').write_text('approved repair\n')
    git('commit','-am','repair');repair=git('rev-parse','HEAD')
    roles={};items={}
    for i,role in enumerate(('runtime','executor','router','verifier'),1):
        sha=repair if role in ('runtime','executor') else source
        image='sha256:'+str(i)*64
        labels={'org.pcp.local.instance':root.name,'org.opencontainers.image.revision':sha}
        items['image',image]={'Id':image,'Config':{'Labels':deepcopy(labels)}}
        roles[role]={'image_id':image,'source_commit':sha}
        if role=='verifier':continue
        name=root.name+'-'+{'runtime':'coding-runtime','executor':'ddev-executor','router':'router'}[role]
        row={'Name':'/'+name,'State':{'Running':True},'Image':image,
             'Config':{'Image':image,'Labels':labels},'HostConfig':{'Mounts':[
                {'Type':'bind','Source':str(root/'config'),'Target':'/config','BindOptions':{'NonRecursive':True}}]},
             'Mounts':[{'Source':str(root/'config'),'Destination':'/config','RW':False}]}
        items['container',name]=row
        roles[role]['configuration_sha256']=r.configuration_digest(row)
    a={'base_sha':source,'runtime_image_id':roles['verifier']['image_id'],
       'verification_image':roles['verifier']['image_id'],'claim_recovery':{
        'repair_source':repair,'repair_commits':[repair],'repair_paths':['services/runtime/app.py'],
        'receipt_before':{'allowed_paths':['tests/test_pcp_light_pilot.py']},'roles':roles}}
    return SimpleNamespace(a=a,root=root,git=git,items=items,inspect=lambda kind,name:items[kind,name])


def check(s):return r.release(s.a,s.root,s.root,s.inspect)


def test_actual_git_repair_with_retained_router_and_verifier(release):
    s=release
    assert check(s)==s.a['claim_recovery']['repair_source']
    assert s.a['claim_recovery']['roles']['verifier']['source_commit']==s.a['base_sha']


@pytest.mark.parametrize('path',['tests/test_pcp_light_pilot.py','services/router/app.py'])
def test_intermediate_changed_and_reverted_pilot_or_router_is_rejected(release,path):
    s=release;file=s.root/path;file.write_text('changed\n');s.git('commit','-am','unapproved intermediate')
    file.write_text('original\n');s.git('commit','-am','reverted')
    p=s.a['claim_recovery'];p['repair_source']=s.git('rev-parse','HEAD')
    p['repair_commits']=s.git('rev-list','--reverse','--topo-order',s.a['base_sha']+'..HEAD').splitlines()
    with pytest.raises(HTTPException) as error:check(s)
    assert error.value.detail in ('claim_recovery_pilot_paths_changed','claim_recovery_router_inputs_changed')


@pytest.mark.parametrize('change',['range','paths','ancestry','image_label','image_id','mount','container_source','verifier'])
def test_wrong_range_image_and_mount_fail_closed(release,change):
    s=release;p=s.a['claim_recovery'];role=p['roles']['runtime'];row=s.items['container',s.root.name+'-coding-runtime']
    if change=='range':p['repair_commits']=[s.a['base_sha'],p['repair_source']]
    elif change=='paths':p['repair_paths']=['unapproved.py']
    elif change=='ancestry':s.a['base_sha']='f'*40
    elif change=='image_label':s.items['image',role['image_id']]['Config']['Labels']['org.opencontainers.image.revision']=s.a['base_sha']
    elif change=='image_id':row['Image']='sha256:'+'a'*64
    elif change=='mount':row['Mounts'].append({'Destination':'/foreign','Source':'/foreign','RW':True})
    elif change=='container_source':row['Config']['Labels']['org.opencontainers.image.revision']=s.a['base_sha']
    elif change=='verifier':p['roles']['verifier']['source_commit']=p['repair_source']
    with pytest.raises(HTTPException):check(s)

from test_pcp_local_observer import topology, observe  # noqa:F401,E402


@pytest.mark.parametrize('actual_main', ['repair','old','other'])
def test_observe_reports_real_main_and_preserves_original_verifier(topology,monkeypatch,actual_main):
    from app import main
    s=topology;repair='9'*40;runtime_image='sha256:'+'d'*64
    original_image=s.activation['runtime_image_id']
    s.activation['claim_recovery']={'repair_source':repair,'roles':{'runtime':{'image_id':runtime_image}}}
    s.worker['Image']=runtime_image
    monkeypatch.setattr(r,'release',lambda *args:repair)  # Real Git/inspect validation covered above.
    observed=repair if actual_main=='repair' else s.activation['base_sha'] if actual_main=='old' else 'f'*40
    class Client:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:
                {'object':{'sha':observed}} if url.endswith('/git/ref/heads/main') else {'permissions':{'push':True}})
    monkeypatch.setattr(main,'_github_context',lambda _:(SimpleNamespace(base='https://fixture.invalid',_client=Client),main._PCP_REPOSITORY))
    response=observe(s)
    if actual_main=='repair':
        assert response.status_code==200,response.text
        assert response.json()['isolation']['current_main_sha']==repair
        assert response.json()['source_commit']==s.activation['base_sha']
        assert ('image',original_image) in s.inspections
        assert s.activation['runtime_image_id']==s.activation['verification_image']==original_image
    else:
        assert response.status_code==409 and response.json()['detail']=='claim_recovery_actual_main_changed'


@pytest.mark.parametrize('path,denial',[
    ('tests/test_pcp_light_pilot.py','claim_recovery_pilot_paths_changed'),
    ('services/router/app.py','claim_recovery_router_inputs_changed')])
def test_merged_reverted_side_history_cannot_hide_protected_input_edits(release,path,denial):
    s=release;p=s.a['claim_recovery'];source=s.a['base_sha']
    s.git('checkout','-b','reverted-side',source)
    file=s.root/path;file.write_text('intermediate side change\n');s.git('commit','-am','side change')
    file.write_text('original\n');s.git('commit','-am','side revert')
    s.git('checkout','main');s.git('merge','--no-ff','reverted-side','-m','merge reverted history')
    repair=s.git('rev-parse','HEAD');p['repair_source']=repair
    p['repair_commits']=s.git('rev-list','--reverse','--topo-order',source+'..HEAD').splitlines()
    # Every current image/config is otherwise valid at the synthetic merge R.
    for role in ('runtime','executor'):
        binding=p['roles'][role];binding['source_commit']=repair
        s.items['image',binding['image_id']]['Config']['Labels']['org.opencontainers.image.revision']=repair
        name=s.root.name+'-'+('coding-runtime' if role=='runtime' else 'ddev-executor')
        row=s.items['container',name];row['Config']['Labels']['org.opencontainers.image.revision']=repair
        binding['configuration_sha256']=r.configuration_digest(row)
    with pytest.raises(HTTPException) as error:check(s)
    assert error.value.detail==denial


def test_reviewed_merge_range_with_unchanged_pilot_and_router_passes(release):
    s=release;p=s.a['claim_recovery'];source=s.a['base_sha']
    s.git('checkout','-b','approved-side',source)
    (s.root/'repair-note.md').write_text('approved release evidence\n');s.git('add','repair-note.md');s.git('commit','-m','evidence')
    s.git('checkout','main');s.git('merge','--no-ff','approved-side','-m','accepted repair merge')
    repair=s.git('rev-parse','HEAD');p['repair_source']=repair
    p['repair_commits']=s.git('rev-list','--reverse','--topo-order',source+'..HEAD').splitlines()
    p['repair_paths']=sorted(['services/runtime/app.py','repair-note.md'])
    for role in ('runtime','executor'):
        binding=p['roles'][role];binding['source_commit']=repair
        s.items['image',binding['image_id']]['Config']['Labels']['org.opencontainers.image.revision']=repair
        name=s.root.name+'-'+('coding-runtime' if role=='runtime' else 'ddev-executor')
        row=s.items['container',name];row['Config']['Labels']['org.opencontainers.image.revision']=repair
        binding['configuration_sha256']=r.configuration_digest(row)
    assert check(s)==repair


@pytest.mark.parametrize('drift',['none','paths','verifier','runtime','task'])
def test_distinct_held_binding_keeps_task_Q_and_platform_repair(release,drift):
    s=release;p=s.a.pop('claim_recovery');p['before']={'receipt':p.pop('receipt_before')}
    s.a['held_verification']=p
    if drift=='paths':p['repair_paths']=['other.py']
    elif drift=='verifier':p['roles']['verifier']['source_commit']=p['repair_source']
    elif drift=='runtime':p['roles']['runtime']['source_commit']=s.a['base_sha']
    elif drift=='task':p['before']['receipt']['allowed_paths']=['services/runtime/app.py']
    if drift=='none':assert r.release(s.a,s.root,s.root,s.inspect,binding_key='held_verification')==p['repair_source']
    else:
        with pytest.raises(HTTPException):r.release(s.a,s.root,s.root,s.inspect,binding_key='held_verification')


@pytest.mark.parametrize('kind',['regular','hardlink','symlink','directory_link','permissions','replace'])
def test_held_authority_file_cannot_be_substituted(tmp_path,monkeypatch,kind):
    import os
    from app import pcp_local_held as h
    root=tmp_path/'private';root.mkdir();path=root/'permit.json'
    path.write_text('{}');path.chmod(0o600)
    if kind=='regular':assert h._read(path)==b'{}';return
    if kind=='hardlink':os.link(path,root/'alias')
    elif kind=='symlink':path.rename(root/'original');path.symlink_to(root/'original')
    elif kind=='directory_link':
        alias=tmp_path/'alias';alias.symlink_to(root,target_is_directory=True);path=alias/path.name
    elif kind=='permissions':path.chmod(0o644)
    else:
        real_read=os.read;replaced=False
        def race(fd,n):
            nonlocal replaced
            result=real_read(fd,n)
            if not replaced:
                replaced=True
                replacement=root/'replacement';replacement.write_text('{}');replacement.chmod(0o600)
                replacement.replace(path)
            return result
        monkeypatch.setattr(os,'read',race)
    with pytest.raises(HTTPException):h._read(path)


@pytest.mark.parametrize('drift',['none','old_flag','version','expiry','error','model_replay','verifier'])
def test_artifact_permit_is_separate_and_release_retains_original_verifier(release,tmp_path,monkeypatch,drift):
    import json,time,hashlib
    from app import pcp_local_held as h
    s=release;a=deepcopy(s.a);mapping=a.pop('claim_recovery')
    before=dict(receipt=dict(state='running',generation=2,job_id='a'*32,issue_number=999,
        base_sha=a['base_sha'],body_sha256='b'*64,baseline_revision='fixture-H',baseline_source_commit=a['base_sha'],
        allowed_paths=['tests/test_pcp_light_pilot.py']),
        job=dict(id='a'*32,status='blocked',result=None,error='pcp_local_changed_paths_denied',workspace=str(s.root/'workspace'),
            progress=dict(model_calls=1,test_runs=0,delivery_attempts=0),checkpoint={'pcp_local_execution':dict(
                state='held',held_from='invocation_returned',returned_invocation=dict(returncode=0,provider_failed=False))}),
        lease=dict(state='active',owner_job_id='a'*32))
    a.update({k:before['receipt'][k] for k in ('issue_number','body_sha256','baseline_revision','baseline_source_commit')})
    original=tmp_path/'original-artifact.json';original.write_text(json.dumps(a));original.chmod(0o600)
    candidate={'identity':{},'diff':{}}
    p=dict(version=2,decision_id='fixture-artifact-decision',execution_record='fixture',
        not_before=time.time()-1,expires_at=time.time()+600,original_activation_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
        before=before,candidate=candidate,artifact_plan=dict(version=1,workspace=before['job']['workspace'],job_id='a'*32,
            root='pytest-of-node',extra_roots=[],before={},provenance=dict(kind='independent_pm_inventory'),candidate=candidate),
        invocation_attestation={},repair_source=mapping['repair_source'],repair_commits=mapping['repair_commits'],
        repair_paths=mapping['repair_paths'],roles=mapping['roles'],verification_seconds=60)
    path=tmp_path/'artifact-permit.json'
    if drift=='old_flag':monkeypatch.setenv('PCP_LOCAL_HELD_VERIFY_ENABLED','owner-approved')
    else:monkeypatch.delenv('PCP_LOCAL_HELD_VERIFY_ENABLED',raising=False)
    if drift=='version':p['version']=1
    elif drift=='expiry':p['expires_at']=time.time()-1
    elif drift=='error':p['before']['job']['error']='another_scope_failure'
    elif drift=='model_replay':p['before']['job']['progress']['model_calls']=2
    elif drift=='verifier':p['roles']['verifier']['source_commit']=mapping['repair_source']
    path.write_text(json.dumps(p));path.chmod(0o600)
    monkeypatch.setattr(h,'ARTIFACT_PERMIT',path);monkeypatch.setattr(h,'ARTIFACT_ORIGINAL',original)
    monkeypatch.setenv('PCP_LOCAL_ARTIFACT_RECOVERY_ENABLED','owner-approved')
    if drift=='none':
        value=h.activation();assert value['base_sha']==a['base_sha']
        assert r.release(value,s.root,s.root,s.inspect,binding_key='held_verification')==mapping['repair_source']
    else:
        with pytest.raises(HTTPException):
            value=h.activation();r.release(value,s.root,s.root,s.inspect,binding_key='held_verification')
