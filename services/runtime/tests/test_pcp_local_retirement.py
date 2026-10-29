"""Maintenance input/physical-observer contract; process doubles, not physical proof."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.pcp_local_task_queue import TaskStop

SCRIPT=Path(__file__).resolve().parents[3]/'scripts/pcp-local-retire-job.py'


@pytest.fixture
def cli():
    if not SCRIPT.exists():pytest.skip('CLI source requires repository checkout')
    spec=importlib.util.spec_from_file_location('retirement_cli',SCRIPT)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_private_input_permissions_symlinks_and_duplicate_keys(cli,tmp_path):
    tmp_path.chmod(0o700);p=tmp_path/'approval.json';p.write_text('{"ok":true}');p.chmod(0o600)
    assert cli.private_json(p)=={'ok':True}
    p.chmod(0o644)
    with pytest.raises(TaskStop,match='custody'):cli.private_json(p)
    p.chmod(0o600);link=tmp_path/'link';link.symlink_to(p)
    with pytest.raises(TaskStop,match='symlink'):cli.private_json(link)
    p.write_text('{"approval":true,"approval":false}')
    with pytest.raises(TaskStop,match='duplicate_json'):cli.private_json(p)
    p.write_text('{}');tmp_path.chmod(0o755)
    with pytest.raises(TaskStop,match='custody'):cli.private_json(p)


def test_default_cli_is_dry_run_and_no_engine_or_initialization(cli,tmp_path,monkeypatch,capsys):
    tmp_path.chmod(0o700)
    for name,obj in [('connection',{'DATABASE_URL':'postgresql://fixture.invalid/db'}),('manifest',{'fixture':True}),('approval',{'fixture':True})]:
        p=tmp_path/name;p.write_text(json.dumps(obj));p.chmod(0o600)
    calls=[]
    def retire(storage,manifest,approval,**kw):
        assert not kw['apply'] and callable(kw['check_quiescent']);calls.append(manifest)
        return {'apply':False}
    monkeypatch.setattr(cli,'retire',retire)
    monkeypatch.setattr(cli.Storage,'init',lambda *_:pytest.fail('schema initialization forbidden'))
    cli.main(['--connection-file',str(tmp_path/'connection'),'--manifest',str(tmp_path/'manifest'),'--approval',str(tmp_path/'approval')])
    assert calls==[{'fixture':True}] and json.loads(capsys.readouterr().out)=={'apply':False}


@pytest.mark.parametrize('change',['none','active','missing','foreign','wrong_db','wrong_cluster','unknown_running'])
def test_quiescence_observes_exact_workers_database_and_all_owned_containers(cli,monkeypatch,change):
    instance='pcp-local-fixture';ids=['1'*64,'2'*64,'3'*64];dbid='4'*64
    rows=[dict(Id=i,Name='/'+instance+'-'+role,Config={'Labels':{'org.pcp.local.instance':instance}},State={'Status':'exited'})
          for i,role in zip(ids,['coding-runtime','router','ddev-executor'])]
    rows.append(dict(Id=dbid,Name='/'+instance+'-db',Config={'Labels':{'org.pcp.local.instance':instance}},State={'Status':'running'}))
    manifest=dict(instance=instance,workers=ids,database_container=dbid,database={'system_identifier':'123'})
    if change=='active':rows[0]['State']['Status']='running'
    if change=='missing':rows.pop(0)
    if change=='foreign':rows[0]['Config']['Labels']['org.pcp.local.instance']='foreign'
    if change=='wrong_db':manifest['database_container']='5'*64
    if change=='unknown_running':rows.append(dict(Id='6'*64,Name='/'+instance+'-unidentified',Config={'Labels':{'org.pcp.local.instance':instance}},State={'Status':'running'}))
    trace=[]
    def run(args,**kwargs):
        trace.append(args)
        if args[1]=='ps':out='\n'.join(r['Id'] for r in rows)
        elif args[1]=='inspect':out=json.dumps(rows)
        elif args[1]=='exec':out='Database system identifier: '+('456' if change=='wrong_cluster' else '123')
        else:pytest.fail('unexpected mutation or external process')
        return SimpleNamespace(returncode=0,stdout=out)
    monkeypatch.setattr(cli.subprocess,'run',run)
    if change=='none':cli.stopped_workers(manifest)
    else:
        with pytest.raises(TaskStop):cli.stopped_workers(manifest)
    assert all(a[1] in {'ps','inspect','exec'} for a in trace)


def test_url_digest_without_operator_authority_is_not_approval():
    from app.pcp_local_recovery import validate_approval
    with pytest.raises(TaskStop,match='approval_required'):
        validate_approval({},dict(url='https://github.com/example',sha256='a'*64))

from copy import deepcopy
from test_pcp_local_consolidation import verified  # noqa:F401


@pytest.fixture
def audit_inputs(verified):
    from app import pcp_local_recovery as r
    from test_pcp_local_retirement_postgres import approval
    j=deepcopy(verified.store.row);j['updated_at']='2026-10-01T00:00:00+00:00'
    receipt={**j['checkpoint']['pcp_local_source']['receipt'],'repository':r.REPOSITORY,
        'project_id':'pcp-local','job_id':j['id'],'state':'running','generation':2,
        'updated_at':j['updated_at']}
    lease=dict(project_id='pcp-local',owner_job_id=j['id'],state='active',generation=1,updated_at=j['updated_at'])
    m=dict(version=1,repository=r.REPOSITORY,project_id='pcp-local',instance='pcp-local-unit-fixture',
        database=dict(name='fixture',oid='1',schema='fixture',schema_oid='2',system_identifier='3'),
        database_container='4'*64,workers=['1'*64,'2'*64,'3'*64],decision_id='unit-retirement',
        reason='Synthetic incomplete work without successful delivery.',before=dict(job=j,receipt=receipt,lease=lease))
    return m,approval(m)


def test_audit_preserves_original_proof_and_only_accepts_exact_postimages(audit_inputs):
    from app import pcp_local_recovery as r
    m,a=audit_inputs;r.validate_manifest(m);r.validate_approval(m,a)
    post=r.postimages(m,a,'2026-10-29T00:00:00+00:00')
    assert r.validated_retirement(post['job'],post['receipt'])
    assert post['job']['checkpoint']['pcp_local_execution']==m['before']['job']['checkpoint']['pcp_local_execution']
    assert post['job']['progress']==m['before']['job']['progress']
    assert m['before']['job']['status']=='blocked' # No mutation of expected proof.


@pytest.mark.parametrize('change',['counter','proof','approval','outcome','error','receipt','remove_audit'])
def test_retirement_audit_is_not_a_boolean_admission_bypass(audit_inputs,change):
    from app import pcp_local_recovery as r
    m,a=audit_inputs;p=r.postimages(m,a,'2026-10-29T00:00:00+00:00');j=p['job']
    if change=='counter':j['progress']['model_calls']=0
    if change=='proof':j['checkpoint']['pcp_local_execution']['state']='executing'
    if change=='approval':j['checkpoint'][r.KEY]['approval']['attestation']='https://example.invalid/approved'
    if change=='outcome':j['checkpoint'][r.KEY]['outcome']['disposition']='completed'
    if change=='error':j['error']='invented'
    if change=='receipt':p['receipt']['generation']=99
    if change=='remove_audit':j['checkpoint'].pop(r.KEY)
    assert not r.validated_retirement(j,p['receipt'])


@pytest.mark.parametrize('field',['decision_id','authority','approver','execution_record','accepted_source','operator','attestation'])
def test_missing_authority_never_becomes_approval(audit_inputs,field):
    from app import pcp_local_recovery as r
    m,a=audit_inputs;a.pop(field)
    with pytest.raises(TaskStop):r.validate_approval(m,a)


def test_cli_apply_requires_exact_reviewed_clean_checkout_before_database(cli,tmp_path,monkeypatch):
    tmp_path.chmod(0o700)
    for name,obj in [('connection',{'DATABASE_URL':'postgresql://fixture.invalid/db'}),
                     ('manifest',{'database_container':'1'*64}),('approval',{'accepted_source':'f'*40})]:
        p=tmp_path/name;p.write_text(json.dumps(obj));p.chmod(0o600)
    monkeypatch.setattr(cli,'retire',lambda *a,**kw:pytest.fail('unreviewed APPLY reached DB logic'))
    with pytest.raises(TaskStop,match='reviewed_source_required'):
        cli.main(['--apply','--connection-file',str(tmp_path/'connection'),
                  '--manifest',str(tmp_path/'manifest'),'--approval',str(tmp_path/'approval')])
