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
