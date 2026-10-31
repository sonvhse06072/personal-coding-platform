"""Exact approved local test repair; no model, legacy runner or admission.

The private finite permit owns approval. Authenticated HTTP carries identities
only. Existing project/CAS locks, verifier, verified recovery and delivery own
side effects. Old proofs and consumed usage remain immutable epoch history.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from . import pcp_local_recovery as h
from .pcp_local_task_queue import require, LocalSourceTask, PROJECT_ID, REPOSITORY, _unique

KEY = 'pcp_local_review_repair'
PERMIT = Path('/config/pcp-local-review-repair.json')
ORIGINAL = Path('/config/pcp-local-review-original-activation.json')
PATCH = Path('/config/pcp-local-review-repair.patch')
FLAG = 'PCP_LOCAL_REVIEW_REPAIR_ENABLED'


def same(a,b):
    return h.canonical(a)==h.canonical(b)


def enabled():
    return os.getenv(FLAG) == 'owner-approved'


class HistoricalPermit:
    """Integrity/provenance only. This object grants no execution capability."""
    def __init__(self):
        self.raw=h.private_bytes(PERMIT);self.value=json.loads(self.raw,object_pairs_hook=_unique)
        p=self.value;raw=h.private_bytes(ORIGINAL);a=json.loads(raw,object_pairs_hook=_unique)
        require(set(p)=={'version','decision_id','execution_record','not_before','expires_at',
            'original_activation_sha256','before','repair_source','repair_commits','repair_paths',
            'roles','verification_seconds','patch_plan','pr_number','expected_head','review_id','review_body_sha256'}, 'local_repair_permit_shape')
        require(type(p['version']) is int and p['version']==1
            and re.fullmatch('[A-Za-z0-9._-]{8,100}',p['decision_id'])
            and p['execution_record'].startswith('https://github.com/'+REPOSITORY+'/issues/835#issuecomment-')
            and hashlib.sha256(raw).hexdigest()==p['original_activation_sha256'], 'local_repair_approval_invalid')
        r=p['before']['receipt'];self.task=LocalSourceTask(**{k:tuple(r[k]) if k=='allowed_paths' else r[k]
            for k in LocalSourceTask.__dataclass_fields__})
        require(all(a[k]==r[k] for k in ('issue_number','base_sha','body_sha256','baseline_revision','baseline_source_commit'))
            and self.task.base_sha==self.task.baseline_source_commit,'local_repair_task_changed')
        require(re.fullmatch('[0-9a-f]{40}',p['repair_source']) and p['repair_source']!=self.task.base_sha
            and p['repair_commits'] and p['repair_commits'][-1]==p['repair_source']
            and p['repair_paths']==sorted(set(p['repair_paths']))
            and not set(p['repair_paths']) & set(self.task.allowed_paths), 'local_repair_release_invalid')
        require(type(p['verification_seconds']) is int and 10<=p['verification_seconds']<=900
            and set(p['roles'])=={'runtime','executor','router','verifier'}, 'local_repair_roles_invalid')
        for role,b in p['roles'].items():
            require(set(b)==({'image_id','source_commit'} | (set() if role=='verifier' else {'configuration_sha256'}))
                and re.fullmatch('sha256:[0-9a-f]{64}',b['image_id'])
                and re.fullmatch('[0-9a-f]{40}',b['source_commit'])
                and (role=='router' or b['source_commit']==(self.task.base_sha if role=='verifier' else p['repair_source']))
                and (role=='verifier' or re.fullmatch('[0-9a-f]{64}',b['configuration_sha256'])), 'local_repair_roles_invalid')
        require(p['roles']['verifier']['image_id']==a['verification_image']==a['runtime_image_id'], 'local_repair_verifier_changed')
        self.patch=h.private_bytes(PATCH);self.sha256=h.digest(p)
        self.activation={**a,'local_review_repair':deepcopy(p)}
        require(type(p['review_id']) is int and p['review_id']>0 and re.fullmatch('[a-f0-9]{64}',p['review_body_sha256'])
            and type(p['pr_number']) is int and p['pr_number']>0 and re.fullmatch('[a-f0-9]{40}',p['expected_head']), 'local_repair_request_identity_invalid')
        eligibility(p,self.task)
        require(hashlib.sha256(self.patch).hexdigest()==p['patch_plan']['patch_sha256'], 'local_repair_patch_hash')
        require(all(type(p[k]) in (float,int) and __import__('math').isfinite(p[k])
            for k in ('not_before','expires_at')) and 0<p['expires_at']-p['not_before']<=86400,
            'local_repair_window_invalid')
        self.require_integrity()

    def require_integrity(self):
        require(h.private_bytes(PERMIT)==self.raw and h.digest(self.value)==self.sha256
            and hashlib.sha256(h.private_bytes(ORIGINAL)).hexdigest()==self.value['original_activation_sha256']
            and h.private_bytes(PATCH)==self.patch, 'local_repair_authority_revoked')


class Permit(HistoricalPermit):
    def __init__(self):
        self.require_mode()
        super().__init__()
        self.require_fresh()

    @staticmethod
    def require_mode():
        require(enabled() and not h.enabled() and not os.getenv('PCP_LOCAL_CLAIM_RECOVERY_ENABLED')
            and not os.getenv('PCP_LOCAL_FINALIZATION_ENABLED')
            and not Path('/config/pcp-local-activation.json').exists(), 'local_repair_conflicting_authority')

    def require_fresh(self):
        self.require_mode()
        p=self.value
        require(enabled() and not h.enabled() and not os.getenv('PCP_LOCAL_CLAIM_RECOVERY_ENABLED')
            and not Path('/config/pcp-local-activation.json').exists()
            and all(type(p[k]) in (float,int) for k in ('not_before','expires_at'))
            and p['not_before']<=time.time()<p['expires_at']
            and 0<p['expires_at']-p['not_before']<=86400, 'local_repair_authority_expired')
        self.require_integrity()

    def verify_issue(self,issue):
        self.require_fresh()
        task=h._verify_issue(issue,expected_main=self.value['repair_source'],**{k:getattr(self.task,k)
            for k in ('issue_number','body_sha256','base_sha','baseline_revision','baseline_source_commit')})
        require(task==self.task,'local_repair_task_changed');return task


def eligibility(p,task):
    from .pcp_local_worker_loop import stable_job_id,claimed_source_receipt
    b=p['before'];j,r,l=b['job'],b['receipt'],b['lease'];cp=j['checkpoint'];e=cp['pcp_local_execution'];result=j['result']
    require(set(b)=={'job','receipt','lease'} and KEY not in cp and 'pcp_local_retirement' not in cp
        and j['id']==stable_job_id(task)==r['job_id']==l['owner_job_id']
        and j['project_id']==PROJECT_ID and j['source_commit']==task.base_sha
        and cp['pcp_local_source']['receipt']==claimed_source_receipt(task)
        and cp['project_baseline']['source_commit']==task.baseline_source_commit
        and cp['project_baseline']['revision']==task.baseline_revision
        and j['status']=='blocked' and j['error']=='pcp_local_hosted_ci_not_passed'
        and r['state']=='running' and r['generation']==2 and l['state']=='active'
        and l['generation']==e['lease_generation'] and all(h.canonical(r[k])==h.canonical(v) for k,v in vars(task).items())
        and j['branch']=='ai/'+j['id'][:12] and e['state']=='verified'
        and e['commit']==result['commit']==p['expected_head']
        and result['verification']==e['verification'] and e['verification']['passed'] is True
        and e['verification']['test_runs']>0 and result['diff']==e['diff']
        and result['delivery_finalized'] is False and result['delivery']['state']=='ci_failure'
        and result['delivery']['pull_request']['number']==p['pr_number']
        and result['delivery']['pull_request']['head']==p['expected_head']
        and result['delivery']['pull_request']['head_ref']==j['branch'], 'local_repair_job_ineligible')
    require(all(type(j['progress'].get(k)) is int for k in ('model_calls','test_runs','delivery_attempts'))
        and [j['progress'].get(k,0) for k in ('model_calls','test_runs','delivery_attempts')]==[1,2,1], 'local_repair_counters_invalid')
    failed_ci(result['delivery']['ci'],p['expected_head'])
    plan=p['patch_plan'];target=plan['path']
    require(set(plan)=={'path','patch_sha256','before','before_file_sha256','after_file_sha256','candidate'}
        and target in task.allowed_paths and re.fullmatch(r'tests/test_pcp_light_[A-Za-z0-9_]+\.py',target)
        and all(re.fullmatch('[a-f0-9]{64}',plan[k]) for k in ('patch_sha256','before_file_sha256','after_file_sha256'))
        and plan['candidate']['identity']['parent']==p['expected_head']
        and plan['candidate']['identity']['source']==task.base_sha, 'local_repair_patch_scope')


def failed_ci(ci,head):
    require(ci.get('state')=='failure' and ci.get('repository')==REPOSITORY and ci.get('commit')==head
        and not ci.get('trusted_contract_invalid') and not ci.get('trusted_order_ambiguous')
        and ci.get('failure_class')=='engineering'
        and any(r.get('source')=='github_actions' and r.get('id')==r.get('run_id') and r.get('head_sha')==head and r.get('name')=='tests'
        and r.get('status')=='completed' and r.get('conclusion')=='failure' and type(r.get('run_id')) is int
        for r in ci.get('actions_runs',[])), 'local_repair_failed_ci_unproven')


def make_patch_plan(row,task,patch,path):
    """Plan only on a validated private clone. No Git command touches original."""
    from .pcp_local_worker_loop import _retained_repository,_retained_run,_retained_snapshot
    require(path in task.allowed_paths and re.fullmatch(r'tests/test_pcp_light_[A-Za-z0-9_]+\.py',path),'local_repair_patch_scope')
    root=Path(row['workspace']);before=h.frozen(_retained_snapshot(root))
    with _retained_repository(root) as (clone,home):
        require(not _retained_run(['git','-C',str(clone),'status','--porcelain'],home),'local_repair_dirty_workspace')
        require(h.reconcile_commit(row,task)==row['result']['commit'],'local_repair_original_proof_changed')
        old=(clone/path).read_bytes();mode=stat.S_IMODE((clone/path).stat().st_mode)
        _retained_run(['git','-C',str(clone),'apply','--check','-'],home,input=patch)
        _retained_run(['git','-C',str(clone),'apply','-'],home,input=patch)
        names=_retained_run(['git','-C',str(clone),'diff','HEAD','--name-only','-z'],home).split(b'\0')
        changed=(clone/path).lstat()
        require(names==[path.encode(),b''] and not _retained_run(['git','-C',str(clone),'ls-files','--others','--exclude-standard'],home)
            and stat.S_ISREG(changed.st_mode) and changed.st_nlink==1
            and stat.S_IMODE(changed.st_mode)&0o111==mode&0o111,'local_repair_patch_scope')
        # Git creates a replacement using the private process umask. Restore
        # the original permission bits only in this disposable preview; an
        # executable/type change from the patch was rejected above.
        (clone/path).chmod(mode)
        data=(clone/path).read_bytes();require(data!=old,'local_repair_empty_patch')
        value=_candidate_snapshot(clone,home,task.base_sha);diff=value['diff'];identity=value['identity']
        require(set(diff['changed_files'])<=set(task.allowed_paths),'local_repair_patch_scope')
    require(h.frozen(_retained_snapshot(root))==before,'local_repair_workspace_raced')
    return dict(path=path,patch_sha256=hashlib.sha256(patch).hexdigest(),before=before,
        before_file_sha256=hashlib.sha256(old).hexdigest(),after_file_sha256=hashlib.sha256(data).hexdigest(),
        candidate=dict(identity=identity,diff=diff)),data


def _candidate_snapshot(clone,home,base):
    import sys
    from .pcp_local_worker_loop import _retained_run
    program="""import sys,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
from app.repo import diff_state
from app.pcp_local_recovery import verified_tree
path=Path(sys.argv[2]);task=SimpleNamespace(base_sha=sys.argv[3])
d=diff_state(path,750000,base_ref=task.base_sha)
print(json.dumps(dict(identity=verified_tree(path,task,d),diff=d)))
"""
    return json.loads(_retained_run([sys.executable,'-I','-B','-c',program,
        str(Path(__file__).resolve().parent.parent),str(clone),base],home))


def current_candidate(row,task):
    from .pcp_local_worker_loop import _retained_repository
    with _retained_repository(Path(row['workspace'])) as (clone,home):
        return _candidate_snapshot(clone,home,task.base_sha)


def patch_state(row,permit):
    from .pcp_local_worker_loop import _retained_snapshot
    plan=permit.value['patch_plan'];actual=h.frozen(_retained_snapshot(Path(row['workspace'])))
    if actual==plan['before']:return 'original'
    # Only the approved file and its containing directory's rename timestamps
    # may change. Every other byte, inode, mode, index/config and path is exact.
    wanted=deepcopy(plan['before']);observed=deepcopy(actual);key='/'+plan['path'];parent='/'+str(Path(plan['path']).parent)
    require(set(wanted)==set(observed),'local_repair_patch_drift')
    require(observed[key][1]==plan['after_file_sha256'] and observed[key][0][2]==wanted[key][0][2], 'local_repair_patch_drift')
    for v in (wanted,observed):
        v.pop(key)
        v[parent][0][7:10]=[0,0,0]
    require(wanted==observed and current_candidate(row,permit.task)==plan['candidate'],'local_repair_patch_drift')
    return 'patched'


def write_patch(row,permit):
    from .pcp_local_artifacts import directory
    p=permit.value['patch_plan'];require(patch_state(row,permit)=='original','local_repair_patch_not_original')
    planned,data=make_patch_plan(row,permit.task,permit.patch,p['path'])
    require(planned==p,'local_repair_patch_plan_changed')
    path=Path(row['workspace'])/p['path'];fd=directory(path.parent);temp='.pcp-review-'+permit.sha256[:20]+'.tmp'
    try:
        permit.require_fresh()
        mode=stat.S_IMODE(p['before']['/'+p['path']][0][2])
        out=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode,dir_fd=fd)
        os.fchmod(out,mode)
        with os.fdopen(out,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        # Recheck full original and authority immediately before the atomic write.
        from .pcp_local_worker_loop import _retained_snapshot
        observed=h.frozen(_retained_snapshot(Path(row['workspace'])))
        temporary=observed.pop('/'+str(Path(p['path']).parent/temp))
        require(temporary[1]==p['after_file_sha256'],'local_repair_patch_raced')
        parent='/'+str(Path(p['path']).parent)
        observed[parent][0][7:10]=p['before'][parent][0][7:10]
        require(observed==p['before'],'local_repair_patch_raced')
        permit.require_fresh();os.replace(temp,path.name,src_dir_fd=fd,dst_dir_fd=fd);os.fsync(fd)
    finally:os.close(fd)


def snapshot(storage,permit):return h.snapshot(storage,permit)


def classify(current,permit):
    p=permit.value;a=current['job']['checkpoint'].get(KEY)
    if a is None:
        require(same(current,p['before']),'local_repair_preimage_drift');return 'eligible'
    require(a['permit_sha256']==permit.sha256 and same(a['original'],p['before'])
        and same(current['receipt'],p['before']['receipt']) and same(current['lease'],p['before']['lease']), 'local_repair_conflict')
    if a['state'] not in {'verified_uncommitted','publication_intent','awaiting_pm_review'}:
        stripped=deepcopy(current['job']);stripped['checkpoint'].pop(KEY)
        require(h.digest(stripped)==a['after_sha256'],'local_repair_afterimage_drift')
    else:validate_latest(current['job'],permit)
    return a['state']


def validate_latest(row,permit):
    row=h.frozen(row)
    p=permit.value;a=row['checkpoint'][KEY];old=p['before']['job'];e=row['checkpoint']['pcp_local_execution']
    require(a['permit_sha256']==permit.sha256 and same(a['original'],p['before'])
        and a['verification']['passed'] is True and e['verification']==a['verification']
        and e['verified_tree']==p['patch_plan']['candidate']['identity'] and e['diff']==p['patch_plan']['candidate']['diff'], 'local_repair_latest_proof_changed')
    for k,v in old.items():
        if k not in {'checkpoint','progress','result','status','error','updated_at'}:require(same(row[k],v),'local_repair_job_drift')
    for k,v in old['checkpoint'].items():
        if k not in {'pcp_local_execution','delivery','review_context','pcp_local_recovery','accepted_result_history','delivery_history','review_repair_history'}:require(same(row['checkpoint'][k],v),'local_repair_history_changed')
    for key,value in history_entries(p,permit.sha256).items():
        require(same(row['checkpoint'].get(key),value),'local_repair_history_changed')
    for k,v in old['progress'].items():
        if k not in {'test_runs','delivery_attempts','elapsed_minutes','required_checks_passed'}:require(same(row['progress'].get(k),v),'local_repair_usage_changed')
    require(row['progress']['test_runs']==old['progress']['test_runs']+a['verification']['test_runs']
        and old['progress']['delivery_attempts']<=row['progress']['delivery_attempts']<=old['progress']['delivery_attempts']+1,'local_repair_counters_changed')
    if e['state']=='verified':
        result=row['result'];require(result['commit']==e['commit'] and result['diff']==e['diff']
            and result['verification']==e['verification'],'local_repair_latest_result_changed')


def history_entries(p,request_id):
    old=p['before']['job'];cp=old['checkpoint']
    record=dict(request_id=request_id,kind='approved_test_patch',expected_commit=p['expected_head'],pr_number=p['pr_number'],
        review_id=p['review_id'],patch_sha256=p['patch_plan']['patch_sha256'])
    return dict(accepted_result_history=[*deepcopy(cp.get('accepted_result_history',[])),dict(reason='pm_review_repair',request_id=request_id,result=deepcopy(old['result']))],
        delivery_history=[*deepcopy(cp.get('delivery_history',[])),dict(reason='pm_review_repair',request_id=request_id,delivery=deepcopy(old['result']['delivery']))],
        review_repair_history=[*deepcopy(cp.get('review_repair_history',[])),record])


def transition(storage,permit,expected,state,*,verification=None,phase=None,result=None,seconds=0):
    from .storage import now
    with storage.connect() as c:
        h.project_lock(c);permit.require_fresh();current=h.read_rows(c,expected['job']['id'],lock=True)
        require(same(current,expected),'local_repair_stale_preimage');old=classify(current,permit)
        require((old,state) in {('eligible','patch_intent'),('patch_intent','patched'),('patched','verifying'),
            ('verifying','verifying'),('verifying','verification_failed'),('verifying','verified_uncommitted'),
            ('verified_uncommitted','publication_intent'),('publication_intent','awaiting_pm_review')}, 'local_repair_transition_denied')
        j=deepcopy(current['job']);cp=j['checkpoint'];audit=cp.pop(KEY,None) or dict(permit_sha256=permit.sha256,
            original=deepcopy(permit.value['before']),history=[],phases=[])
        if old=='eligible':cp.update(history_entries(permit.value,permit.sha256))
        if phase:
            phases=audit['phases']
            if result is None:
                require(phase==('targeted_tests' if not phases else 'full_tests') and (not phases or phases[-1]['result'] is not None),'local_repair_phase_order')
                phases.append(dict(phase=phase,result=None))
            else:
                require(phases and phases[-1]['phase']==phase and phases[-1]['result'] is None,'local_repair_phase_duplicate')
                phases[-1]['result']=result;j['progress']['test_runs']+=len(result.get('commands',[]))
        if verification is not None:
            require(j['progress']['test_runs']==permit.value['before']['job']['progress']['test_runs']+verification['test_runs'],'local_repair_test_accounting')
            audit['verification']=verification;j['progress']['required_checks_passed']=verification['passed']
            if verification['passed']:
                cp['pcp_local_execution'].update(state='verified_uncommitted',verification=verification,
                    verified_tree=permit.value['patch_plan']['candidate']['identity'],diff=permit.value['patch_plan']['candidate']['diff'])
                cp['pcp_local_execution'].pop('commit',None)
        if state=='patched':
            from .pcp_local_worker_loop import _retained_snapshot
            audit['patched_snapshot']=h.frozen(_retained_snapshot(Path(j['workspace'])))
        audit['state']=state;audit['history'].append(dict(state=state,phase=phase,at=now().isoformat()))
        j['progress']['elapsed_minutes']=max(j['progress'].get('elapsed_minutes',0),permit.value['before']['job']['progress'].get('elapsed_minutes',0)+seconds/60)
        j['updated_at']=now().isoformat();audit['after_sha256']=h.digest(j);cp[KEY]=audit
        c.execute('UPDATE cp_jobs SET checkpoint=%s::jsonb,progress=%s::jsonb,updated_at=%s WHERE id=%s',
            (h.canonical(cp),h.canonical(j['progress']),j['updated_at'],j['id']));c.commit()
    return snapshot(storage,permit)


async def remote(engine,permit,head):
    p=permit.value;j=p['before']['job'];pr=await engine.ddev.github_pull_request(project_id=PROJECT_ID,pr_number=p['pr_number'])
    require(pr.get('repository')==REPOSITORY and pr.get('number')==p['pr_number'] and pr.get('state')=='open'
        and pr.get('merged') is False and pr.get('head')==head and pr.get('head_ref')==j['branch']
        and pr.get('base_ref')=='main','local_repair_remote_head_changed')
    if head==p['expected_head']:
        review=await engine.ddev.github_pull_request_review(project_id=PROJECT_ID,pr_number=p['pr_number'],review_id=p['review_id'])
        require(review.get('id')==p['review_id'] and review.get('pr_number')==p['pr_number']
            and review.get('repository')==REPOSITORY and review.get('commit_id')==head
            and review.get('author')==permit.activation['pm_login']
            and review.get('state') in ('COMMENTED','CHANGES_REQUESTED')
            and isinstance(review.get('body'),str) and len(review['body'].encode())<=16000
            and hashlib.sha256(review['body'].encode()).hexdigest()==p['review_body_sha256'],'local_repair_review_identity_changed')
    ci=await engine.ddev.github_ci(project_id=PROJECT_ID,commit=head)
    return pr,ci


async def prepare(engine):
    from .pcp_local_worker_loop import TrustedReaders
    from .pm_bridge import PMBridgeGitHubClient
    from .pcp_local_readiness import schema_readiness
    require(not schema_readiness(engine.storage),'local_repair_schema_unready')
    permit=Permit();readers=TrustedReaders(engine,PMBridgeGitHubClient());task,_=await readers.source()
    require(task==permit.task and readers.local_review.sha256==permit.sha256,'local_repair_reader_identity')
    project,baseline=readers.authority();original=permit.value['before']['job']
    require(original['checkpoint']['project_baseline']==baseline.model_dump(mode='json')
        and readers.authority_digest==original['checkpoint']['pcp_local_execution']['authority_digest'],'local_repair_original_authority_changed')
    require(Path(original['workspace'])==engine.workspace_root/original['id']
        and engine.worker_task is None and not engine.active_jobs and engine.queue.empty(),'local_repair_writer_active')
    readers.route=original['route'];readers.lease_generation=permit.value['before']['lease']['generation']
    await readers.refresh_delivery(task)
    return permit,readers


async def operate(engine,*,apply=False,expected=None):
    permit,readers=await prepare(engine);p=permit.value
    identity=dict(job_id=p['before']['job']['id'],permit_sha256=permit.sha256,
        expected_head=p['expected_head'],pr_number=p['pr_number'],patch_sha256=p['patch_plan']['patch_sha256'])
    if apply:require(expected==identity,'local_repair_request_identity_changed')
    async with engine.project_operation_lock(PROJECT_ID):
        with h.operation_lock(engine.storage):
            current=snapshot(engine.storage,permit);state=classify(current,permit)
            def view(state,ready=False):return dict(**identity,state=state,ready=ready,reconcile=not ready,
                phase='review-repair',authorized=False,model_invocations=0,job_registrations=0)
            if state=='eligible':
                plan,_=make_patch_plan(current['job'],permit.task,permit.patch,p['patch_plan']['path'])
                require(plan==p['patch_plan'],'local_repair_patch_plan_changed')
                _,ci=await remote(engine,permit,p['expected_head']);failed_ci(ci,p['expected_head'])
                require(ci['actions_runs']==p['before']['job']['result']['delivery']['ci']['actions_runs'],'local_repair_failed_ci_changed')
            if not apply:
                resumable=state=='eligible'
                if state in {'patch_intent','patched'}:
                    patch_state(current['job'],permit)
                    await remote(engine,permit,p['expected_head'])
                    resumable=True
                if state=='verified_uncommitted':resumable=True
                if state=='publication_intent':
                    await remote(engine,permit,current['job']['result']['commit'])
                    resumable=True
                return view(state,resumable)
            if state=='eligible':current=transition(engine.storage,permit,current,'patch_intent');state='patch_intent'
            if state=='patch_intent':
                _,ci=await remote(engine,permit,p['expected_head']);failed_ci(ci,p['expected_head'])
                require(ci['actions_runs']==p['before']['job']['result']['delivery']['ci']['actions_runs'],'local_repair_failed_ci_changed')
                if patch_state(current['job'],permit)=='original':write_patch(current['job'],permit)
                require(patch_state(current['job'],permit)=='patched','local_repair_patch_unknown')
                current=transition(engine.storage,permit,current,'patched');state='patched'
            if state=='patched':
                from .pcp_local_worker_loop import _retained_snapshot
                require(h.frozen(_retained_snapshot(Path(current['job']['workspace'])))==current['job']['checkpoint'][KEY]['patched_snapshot'],'local_repair_candidate_drift')
                require(current_candidate(current['job'],permit.task)==p['patch_plan']['candidate'],'local_repair_candidate_drift')
                current=transition(engine.storage,permit,current,'verifying');started=time.monotonic()
                def observe(phase,result):
                    nonlocal current
                    current=transition(engine.storage,permit,current,'verifying',phase=phase,result=result,seconds=time.monotonic()-started)
                verification=await engine.verify_pcp_local(current['job']['id'],Path(current['job']['workspace']),readers.authority()[0],timeout_seconds=p['verification_seconds'],phase_observer=observe)
                await readers.refresh_delivery(permit.task)
                require(h.frozen(_retained_snapshot(Path(current['job']['workspace'])))==current['job']['checkpoint'][KEY]['patched_snapshot']
                    and current_candidate(current['job'],permit.task)==p['patch_plan']['candidate'],'local_repair_tested_candidate_drift')
                state='verified_uncommitted' if verification['passed'] else 'verification_failed'
                current=transition(engine.storage,permit,current,state,verification=verification,seconds=time.monotonic()-started)
            if state=='verified_uncommitted':
                execution=current['job']['checkpoint']['pcp_local_execution']
                if execution['state'] in {'verified_uncommitted','commit_uncertain'}:
                    raw=engine.storage.get(current['job']['id'])
                    require(h.frozen(raw)==current['job'],'local_repair_commit_row_changed')
                    await h.recover_verified_job(engine,readers,permit.task,raw);current=snapshot(engine.storage,permit)
                require(h.reconcile_commit(current['job'],permit.task)==current['job']['result']['commit'],'local_repair_commit_unknown')
                current=transition(engine.storage,permit,current,'publication_intent')
                await engine.deliver_pcp_local(current['job']['id'],readers,permit.task)
                current=snapshot(engine.storage,permit);state='publication_intent'
            if state=='publication_intent':
                # A lost publish/PR acknowledgement is read-only here. Never
                # call delivery twice: observe SAME PR/head and actual CI.
                j=current['job'];head=j['result']['commit'];pr,ci=await remote(engine,permit,head)
                from .required_ci import required_github_actions_pass
                if not required_github_actions_pass(ci,repository=REPOSITORY,commit=head,workflow_name='tests'):
                    return view('publication_intent')
                # Normal delivery must already have persisted exact success;
                # uncertain transport needs an explicit reconciled result CAS.
                if j['result'].get('delivery',{}).get('state')!='ci_success':
                    current=reconcile_publication(engine.storage,permit,current,pr,ci)
                transition(engine.storage,permit,current,'awaiting_pm_review')
                return view('awaiting_pm_review')
            return view(state)


def reconcile_publication(storage,permit,expected,pr,ci):
    from .required_ci import required_github_actions_pass
    require(required_github_actions_pass(ci,repository=REPOSITORY,commit=expected['job']['result']['commit'],workflow_name='tests'),'local_repair_ci_unproven')
    with storage.connect() as c:
        h.project_lock(c);permit.require_fresh();current=h.read_rows(c,expected['job']['id'],lock=True)
        require(same(current,expected) and classify(current,permit)=='publication_intent','local_repair_stale_publication')
        j=current['job'];result=deepcopy(j['result']);result['delivery']=dict(enabled=True,state='ci_success',branch=j['branch'],commit=result['commit'],pull_request=pr,ci=ci,reconciled_read_only=True)
        result.update(delivery_finalized=False,acceptance_phase='awaiting_independent_pm_review')
        cp=deepcopy(j['checkpoint']);cp['delivery']=result['delivery']
        c.execute("UPDATE cp_jobs SET checkpoint=%s::jsonb,result=%s::jsonb,status='blocked',error='awaiting_independent_pm_review',updated_at=NOW() WHERE id=%s",(h.canonical(cp),h.canonical(result),j['id']));c.commit()
    return snapshot(storage,permit)
