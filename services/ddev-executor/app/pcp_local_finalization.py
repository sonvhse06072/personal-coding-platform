"""Executor half of the private finalization-only capability; never execution."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from .pcp_local_held import _read, unique
from .pcp_local_claim_recovery import require, digest, release, git
from .pcp_local_observer import configuration_digest, validate_network_peers
from .pcp_local_review_repair import historical_activation, PERMIT as REPAIR

FLAG='PCP_LOCAL_FINALIZATION_ENABLED'
PERMIT=Path('/config/pcp-local-finalization.json')
FIELDS={'version','decision_id','execution_record','not_before','expires_at','original_repair_raw_sha256',
    'original_repair_digest','before','workspace_sha256','expected_head','diff_hash','pr_number','review',
    'repair_source','repair_commits','repair_paths','roles','resources'}


def enabled():return os.getenv(FLAG)=='owner-approved'


def execution_forbidden():
    require(not os.getenv(FLAG), 'local_finalization_execution_forbidden')


class Authority:
    def __init__(self):
        require(enabled() and not any(os.getenv(k) for k in ('PCP_LOCAL_REVIEW_REPAIR_ENABLED',
            'PCP_LOCAL_HELD_VERIFY_ENABLED','PCP_LOCAL_ARTIFACT_RECOVERY_ENABLED','PCP_LOCAL_CLAIM_RECOVERY_ENABLED',
            'PCP_LOCAL_TASK_SOURCE_ENABLED','PCP_LOCAL_TASK_WORKER_ENABLED','PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION'))
            and not Path('/config/pcp-local-activation.json').exists(), 'local_finalization_conflicting_authority')
        self.raw=_read(PERMIT);p=json.loads(self.raw,object_pairs_hook=unique);self.value=p
        require(type(p) is dict and set(p)==FIELDS and type(p['version']) is int and p['version']==1
            and re.fullmatch('[A-Za-z0-9._-]{8,100}',p['decision_id'])
            and re.fullmatch(r'https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-[1-9][0-9]*',p['execution_record']),
            'local_finalization_shape')
        require(all(type(p[k]) in (int,float) and math.isfinite(p[k]) for k in ('not_before','expires_at'))
            and p['not_before']<=time.time()<p['expires_at'] and 0<p['expires_at']-p['not_before']<=86400,
            'local_finalization_authority_expired')
        old=historical_activation();history=old.pop('local_review_repair')
        require(hashlib.sha256(_read(REPAIR)).hexdigest()==p['original_repair_raw_sha256']
            and digest(history)==p['original_repair_digest'], 'local_finalization_original_changed')
        self.original=old
        b=p['before'];j=b['job'];e=j['checkpoint']['pcp_local_execution'];audit=j['checkpoint']['pcp_local_review_repair']
        require(set(b)=={'job','receipt','lease'} and b['receipt']==history['before']['receipt']
            and b['lease']==history['before']['lease'] and audit['permit_sha256']==p['original_repair_digest']
            and audit['original']==history['before'] and audit['state']=='awaiting_pm_review'
            and j['status']=='blocked' and j['error']=='awaiting_independent_pm_review'
            and e['state']=='verified' and e['commit']==j['result']['commit']==p['expected_head']
            and e['verified_tree']==history['patch_plan']['candidate']['identity']
            and j['result']['diff']==e['diff']==history['patch_plan']['candidate']['diff']
            and j['result']['verification']==e['verification']==audit['verification']
            and audit['verification']['passed'] is True
            and j['result']['diff']['diff_hash']==p['diff_hash']
            and j['result']['delivery']['pull_request']['number']==p['pr_number']==history['pr_number']
            and j['result']['delivery']['state']=='ci_success' and j['result']['delivery_finalized'] is False
            and [j['progress'][k] for k in ('model_calls','test_runs','delivery_attempts')]==[1,4,2],
            'local_finalization_afterimage_invalid')
        require(set(p['review'])=={'id','body_sha256','ci_run_id'}
            and all(type(p['review'][k]) is int and p['review'][k]>0 for k in ('id','ci_run_id'))
            and re.fullmatch('[0-9a-f]{64}',p['review']['body_sha256'])
            and p['roles']['verifier']==history['roles']['verifier'], 'local_finalization_review_invalid')
        require(set(p['roles'])=={'runtime','executor','router','verifier'}, 'local_finalization_role_invalid')
        for role,binding in p['roles'].items():
            require(set(binding)==({'image_id','source_commit'} | (set() if role=='verifier' else {'configuration_sha256'}))
                and re.fullmatch('sha256:[0-9a-f]{64}',binding['image_id'])
                and re.fullmatch('[0-9a-f]{40}',binding['source_commit'])
                and (role=='verifier' or re.fullmatch('[0-9a-f]{64}',binding['configuration_sha256'])),
                'local_finalization_role_invalid')
        r=p['resources']
        require(set(r)=={'worker_ids','database','network_id','observer_binding_sha256'}
            and set(r['worker_ids'])=={'runtime','executor','router'}
            and len(set(r['worker_ids'].values()))==3
            and all(re.fullmatch('[0-9a-f]{64}',v) for v in r['worker_ids'].values())
            and set(r['database'])=={'container_id','image_id','configuration_sha256'}
            and re.fullmatch('[0-9a-f]{64}',r['database']['container_id'])
            and re.fullmatch('sha256:[0-9a-f]{64}',r['database']['image_id'])
            and re.fullmatch('[0-9a-f]{64}',r['database']['configuration_sha256'])
            and re.fullmatch('[0-9a-f]{64}',r['network_id'])
            and r['observer_binding_sha256']==digest(old.get('observer_binding')), 'local_finalization_resources_invalid')
        self.activation={**old,'local_finalization':p}

    def request(self,payload):
        p=self.value;j=p['before']['job']
        require(payload.job_id==j['id'] and payload.expected_head==p['expected_head']
            and payload.pr_number==p['pr_number'] and payload.review_id==p['review']['id']
            and payload.source_commit==j['source_commit']
            and payload.activation_digest==digest(self.activation), 'local_finalization_request_changed')

    def resources(self,repo,root,inspect):
        p=self.value;r=p['resources']
        require(git(repo,'rev-parse','HEAD')==self.original['base_sha'] and not git(repo,'status','--porcelain'),
            'local_finalization_canonical_source_changed')
        release(self.activation,repo,root,inspect,binding_key='local_finalization')
        for role,cid in r['worker_ids'].items():
            row=inspect('container',cid)
            require(row['Id']==cid and row['Name']=='/'+root.name+'-'+{
                'runtime':'coding-runtime','executor':'ddev-executor','router':'router'}[role]
                and configuration_digest(row)==p['roles'][role]['configuration_sha256'], 'local_finalization_worker_changed')
        db=inspect('container',r['database']['container_id'])
        require(db['Id']==r['database']['container_id'] and db['State']['Running'] is True
            and db['Name']=='/'+root.name+'-db' and db['Image']==r['database']['image_id']
            and configuration_digest(db)==r['database']['configuration_sha256'], 'local_finalization_database_changed')
        network=inspect('network',r['network_id'])
        require(network['Id']==r['network_id'] and network['Name']==self.original['runtime_network'],
            'local_finalization_network_changed')
        validate_network_peers(self.original,root,network,inspect)

    def revalidate(self):
        require(_read(PERMIT)==self.raw and Authority().activation==self.activation,
            'local_finalization_authority_revoked')
