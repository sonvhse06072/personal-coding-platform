"""Private exact test-repair release binding; no approval from HTTP or names."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
from .pcp_local_held import _read, unique, enabled as held_enabled
from .pcp_local_claim_recovery import require, enabled as claim_enabled

PERMIT=Path('/config/pcp-local-review-repair.json')
ORIGINAL=Path('/config/pcp-local-review-original-activation.json')
PATCH=Path('/config/pcp-local-review-repair.patch')


def enabled():return os.getenv('PCP_LOCAL_REVIEW_REPAIR_ENABLED')=='owner-approved'


def activation():
    require(enabled() and not held_enabled() and not claim_enabled()
        and not Path('/config/pcp-local-activation.json').exists(),'local_repair_conflicting_authority')
    original=_read(ORIGINAL);a=json.loads(original,object_pairs_hook=unique)
    p=json.loads(_read(PERMIT),object_pairs_hook=unique)
    require(set(p)=={'version','decision_id','execution_record','not_before','expires_at',
        'original_activation_sha256','before','repair_source','repair_commits','repair_paths',
        'roles','verification_seconds','patch_plan','pr_number','expected_head','review_id','review_body_sha256'}
        and type(p['version']) is int and p['version']==1
        and re.fullmatch('[A-Za-z0-9._-]{8,100}',p['decision_id'])
        and p['execution_record'].startswith('https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-')
        and p['original_activation_sha256']==hashlib.sha256(original).hexdigest()
        and all(type(p[k]) in (int,float) for k in ('not_before','expires_at'))
        and p['not_before']<=time.time()<p['expires_at'] and 0<p['expires_at']-p['not_before']<=86400,
        'local_repair_authority_invalid')
    j,r,l=p['before']['job'],p['before']['receipt'],p['before']['lease'];e=j['checkpoint']['pcp_local_execution']
    plan=p['patch_plan'];result=j['result']
    require(r['state']=='running' and r['generation']==2 and r['job_id']==j['id']==l['owner_job_id']
        and l['state']=='active' and l['generation']==e['lease_generation']
        and j['status']=='blocked' and j['error']=='pcp_local_hosted_ci_not_passed'
        and e['state']=='verified' and e['commit']==result['commit']==p['expected_head']
        and result['delivery_finalized'] is False and result['delivery']['state']=='ci_failure'
        and result['delivery']['pull_request']['number']==p['pr_number']
        and [j['progress'].get(k,0) for k in ('model_calls','test_runs','delivery_attempts')]==[1,2,1]
        and all(a[k]==r[k] for k in ('issue_number','base_sha','body_sha256','baseline_revision','baseline_source_commit')),
        'local_repair_original_identity_changed')
    require(set(plan)=={'path','patch_sha256','before','before_file_sha256','after_file_sha256','candidate'}
        and plan['path'] in r['allowed_paths'] and re.fullmatch(r'tests/test_pcp_light_[A-Za-z0-9_]+\.py',plan['path'])
        and hashlib.sha256(_read(PATCH)).hexdigest()==plan['patch_sha256']
        and plan['candidate']['identity']['parent']==p['expected_head']
        and p['roles']['verifier']['image_id']==a['verification_image']==a['runtime_image_id'], 'local_repair_patch_invalid')
    return {**a,'local_review_repair':p}
