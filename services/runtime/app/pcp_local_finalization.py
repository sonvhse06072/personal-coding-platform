"""Finite private finalization-only authority, separate from immutable repair proof.

No HTTP field, historical permit, or completed flag can grant this capability.
Only the existing PM finalizer consumes it. All execution readers reject it.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

from . import pcp_local_recovery as h, pcp_local_review_repair as repair
from .pcp_local_task_queue import require, _unique, PROJECT_ID, REPOSITORY

FLAG = 'PCP_LOCAL_FINALIZATION_ENABLED'
PERMIT = Path('/config/pcp-local-finalization.json')
FIELDS = {'version', 'decision_id', 'execution_record', 'not_before', 'expires_at',
    'original_repair_raw_sha256', 'original_repair_digest', 'before', 'workspace_sha256',
    'expected_head', 'diff_hash', 'pr_number', 'review', 'repair_source', 'repair_commits',
    'repair_paths', 'roles', 'resources'}


def enabled():
    return os.getenv(FLAG) == 'owner-approved'


def execution_forbidden():
    require(not os.getenv(FLAG), 'local_finalization_execution_forbidden')


def match(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


class Authority:
    def __init__(self):
        self.require_mode()
        self.raw = h.private_bytes(PERMIT)
        self.value = json.loads(self.raw, object_pairs_hook=_unique)
        p = self.value
        require(type(p) is dict and set(p) == FIELDS, 'local_finalization_shape')
        require(type(p['version']) is int and p['version'] == 1
            and match(r'[A-Za-z0-9._-]{8,100}', p['decision_id'])
            and match(r'https://github.com/'+REPOSITORY+r'/issues/835#issuecomment-[1-9][0-9]*', p['execution_record']),
            'local_finalization_approval_invalid')
        for k in ('original_repair_raw_sha256','original_repair_digest','workspace_sha256','diff_hash'):
            require(match('[0-9a-f]{64}', p[k]), 'local_finalization_digest_invalid')
        self.sha256 = h.digest(p)
        self.historical = repair.HistoricalPermit()
        old = self.historical
        require(hashlib.sha256(old.raw).hexdigest() == p['original_repair_raw_sha256']
            and old.sha256 == p['original_repair_digest'], 'local_finalization_original_changed')
        self.task = old.task
        before = p['before']; row = before['job']; e = row['checkpoint']['pcp_local_execution']
        require(set(before) == {'job','receipt','lease'}
            and repair.same(before['receipt'], old.value['before']['receipt'])
            and repair.same(before['lease'], old.value['before']['lease'])
            and row['checkpoint'][repair.KEY]['state'] == 'awaiting_pm_review'
            and row['status'] == 'blocked' and row['error'] == 'awaiting_independent_pm_review'
            and e['state'] == 'verified' and e['commit'] == row['result']['commit'] == p['expected_head']
            and match('[0-9a-f]{40}', p['expected_head'])
            and row['result']['diff']['diff_hash'] == p['diff_hash']
            and row['result']['delivery']['pull_request']['number'] == p['pr_number'] == old.value['pr_number']
            and row['result']['delivery']['state'] == 'ci_success'
            and row['result']['delivery_finalized'] is False
            and [row['progress'][k] for k in ('model_calls','test_runs','delivery_attempts')] == [1,4,2],
            'local_finalization_afterimage_invalid')
        repair.validate_latest(row, old)
        review = p['review']
        require(set(review) == {'id','body_sha256','ci_run_id'} and type(review['id']) is int and review['id'] > 0
            and type(review['ci_run_id']) is int and review['ci_run_id'] > 0
            and match('[0-9a-f]{64}', review['body_sha256']), 'local_finalization_review_invalid')
        require(match('[0-9a-f]{40}',p['repair_source']) and p['repair_source'] != self.task.base_sha
            and p['repair_commits'] and p['repair_commits'][-1] == p['repair_source']
            and all(match('[0-9a-f]{40}', x) for x in p['repair_commits'])
            and p['repair_paths'] == sorted(set(p['repair_paths']))
            and not set(p['repair_paths']) & set(self.task.allowed_paths)
            and set(p['roles']) == {'runtime','executor','router','verifier'}, 'local_finalization_release_invalid')
        for role,b in p['roles'].items():
            require(set(b) == ({'image_id','source_commit'} | (set() if role == 'verifier' else {'configuration_sha256'}))
                and match('sha256:[0-9a-f]{64}',b['image_id']) and match('[0-9a-f]{40}',b['source_commit'])
                and (role not in ('runtime','executor') or b['source_commit'] == p['repair_source'])
                and (role == 'verifier' or match('[0-9a-f]{64}',b['configuration_sha256'])), 'local_finalization_role_invalid')
        require(p['roles']['verifier'] == old.value['roles']['verifier'], 'local_finalization_verifier_changed')
        r=p['resources']
        require(set(r) == {'worker_ids','database','network_id','observer_binding_sha256'}
            and set(r['worker_ids']) == {'runtime','executor','router'}
            and all(match('[0-9a-f]{64}', x) for x in r['worker_ids'].values())
            and len(set(r['worker_ids'].values())) == 3
            and set(r['database']) == {'container_id','image_id','configuration_sha256'}
            and match('[0-9a-f]{64}',r['database']['container_id'])
            and match('sha256:[0-9a-f]{64}',r['database']['image_id'])
            and match('[0-9a-f]{64}',r['database']['configuration_sha256'])
            and match('[0-9a-f]{64}',r['network_id'])
            and r['observer_binding_sha256'] == h.digest(old.activation.get('observer_binding')),
            'local_finalization_resources_invalid')
        # Original activation/repair bytes stay historical. Only this separate
        # mapping owns the current platform release and finite capability.
        self.activation = {k:deepcopy(v) for k,v in old.activation.items() if k != 'local_review_repair'}
        self.activation['local_finalization'] = deepcopy(p)
        self.require_fresh()

    @staticmethod
    def require_mode():
        require(enabled() and not any(os.getenv(k) for k in (
            repair.FLAG, 'PCP_LOCAL_ARTIFACT_RECOVERY_ENABLED','PCP_LOCAL_HELD_VERIFY_ENABLED',
            'PCP_LOCAL_CLAIM_RECOVERY_ENABLED','PCP_LOCAL_TASK_SOURCE_ENABLED',
            'PCP_LOCAL_TASK_WORKER_ENABLED','PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION'))
            and not Path('/config/pcp-local-activation.json').exists(), 'local_finalization_conflicting_authority')

    def require_fresh(self):
        self.require_mode()
        p = self.value
        require(all(type(p[k]) in (float,int) and math.isfinite(p[k]) for k in ('not_before','expires_at'))
            and p['not_before'] <= time.time() < p['expires_at']
            and 0 < p['expires_at']-p['not_before'] <= 86400, 'local_finalization_authority_expired')
        require(h.private_bytes(PERMIT) == self.raw and h.digest(p) == self.sha256,
            'local_finalization_authority_revoked')
        self.historical.require_integrity()

    def validate_before(self, rows, payload):
        self.require_fresh()
        p = self.value
        require(repair.same(rows,p['before']), 'local_finalization_rows_changed')
        require(payload.source_commit == self.task.base_sha and payload.expected_head == p['expected_head']
            and payload.branch == rows['job']['branch'] and payload.pr_number == p['pr_number']
            and payload.review_id == p['review']['id'] and payload.baseline_revision == self.task.baseline_revision,
            'local_finalization_request_changed')
        repair.validate_latest(rows['job'],self.historical)
        from .pcp_local_worker_loop import _retained_snapshot
        require(h.digest(h.frozen(_retained_snapshot(Path(rows['job']['workspace'])))) == p['workspace_sha256'],
            'local_finalization_workspace_changed')
        require(h.reconcile_commit(rows['job'], self.task) == p['expected_head'], 'local_finalization_head_changed')

    def validate_remote(self, proof):
        from .required_ci import required_github_actions_pass
        p=self.value
        require(proof.get('review_id') == p['review']['id']
            and proof.get('review_body_sha256') == p['review']['body_sha256']
            and proof.get('ci_run_id') == p['review']['ci_run_id']
            and proof.get('report',{}).get('diff_hash') == p['diff_hash']
            and required_github_actions_pass(proof.get('ci') or {}, repository=REPOSITORY,
                commit=p['expected_head'], workflow_name='tests'), 'local_finalization_remote_changed')

    def audit(self):
        return dict(authority_sha256=self.sha256, decision_id=self.value['decision_id'],
            original_repair_digest=self.historical.sha256, review_id=self.value['review']['id'])

    @staticmethod
    def completion_digest(rows):
        rows=deepcopy(h.frozen(rows))
        for v in rows.values():
            v.pop('updated_at',None)
        rows['job']['result']['finalization'].pop('completed_sha256',None)
        return h.digest(rows)

    def validate_completed(self, rows, payload):
        """Exact acknowledged retry is read-only. Drift never becomes a new before."""
        self.require_fresh()
        row=rows['job']; before=self.value['before']; old=before['job']
        recorded=deepcopy(row['result'].get('finalization') or {})
        seal=recorded.pop('completed_sha256',None)
        require(seal == self.completion_digest(rows), 'local_finalization_completed_drift')
        require(recorded == self.audit() and payload.review_id == self.value['review']['id']
            and payload.expected_head == self.value['expected_head'] and payload.pr_number == self.value['pr_number']
            and payload.source_commit == self.task.base_sha and payload.baseline_revision == self.task.baseline_revision
            and payload.branch == old['branch'], 'local_finalization_conflicting_retry')
        require(row['status']=='completed' and row['error'] is None and row['result']['delivery_finalized'] is True,
            'local_finalization_conflicting_retry')
        require(all(repair.same(v,row[k]) for k,v in old.items() if k not in {'status','error','updated_at','result'}),
            'local_finalization_completed_drift')
        for name,state,gen in (('receipt','delivered',3),('lease','released',before['lease']['generation'])):
            v=rows[name]; original=before[name]
            require(v is not None and v['state']==state and v['generation']==gen
                and all(repair.same(x,v[k]) for k,x in original.items() if k not in {'state','generation','updated_at'}),
                'local_finalization_completed_ownership_changed')
        result=row['result']; allowed={'review','delivery_finalized','delivery','acceptance_phase','pm_merge_eligibility','finalization'}
        require(all(repair.same(v,result[k]) for k,v in old['result'].items() if k not in allowed)
            and set(result)==set(old['result'])|allowed and result['review']['review_id']==payload.review_id
            and result['review']['report']['diff_hash']==self.value['diff_hash']
            and result['acceptance_phase']=='pm_review_accepted', 'local_finalization_completed_drift')
