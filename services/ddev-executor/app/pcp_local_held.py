"""Read-only exact task-Q/platform-repair binding, never claimed-job recovery."""
import hashlib
import json
import os
from pathlib import Path
import stat
import time
from .pcp_local_claim_recovery import require, enabled as claim_enabled

PERMIT=Path('/config/pcp-local-held-verification.json')
ORIGINAL=Path('/config/pcp-local-held-original-activation.json')


def enabled():
    return os.getenv('PCP_LOCAL_HELD_VERIFY_ENABLED') == 'owner-approved'


def _read(path):
    """Read only a stable private authority file, never a substituted target."""
    require(path.is_absolute() and path.resolve()==path,'held_private_path_substitution')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1
            and before.st_uid in (0,os.getuid()) and before.st_mode & 0o077==0
            and before.st_size<=2_000_000,'held_private_file_invalid')
        data=b''
        while chunk:=os.read(fd,65536):
            data+=chunk
            require(len(data)<=2_000_000,'held_private_file_invalid')
        def identity(s):
            return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,
                    s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        require(identity(os.fstat(fd))==identity(before)==identity(path.stat(follow_symlinks=False)),
                'held_private_file_raced')
        return data
    finally:
        os.close(fd)


def unique(pairs):
    out={}
    for k,v in pairs:
        require(k not in out,'held_duplicate_key');out[k]=v
    return out


def activation():
    require(enabled() and not claim_enabled() and not Path('/config/pcp-local-activation.json').exists(),
            'held_conflicting_authority')
    original=_read(ORIGINAL);a=json.loads(original,object_pairs_hook=unique)
    p=json.loads(_read(PERMIT),object_pairs_hook=unique)
    require(set(p)=={'version','decision_id','execution_record','not_before','expires_at',
        'original_activation_sha256','before','candidate','invocation_attestation',
        'repair_source','repair_commits','repair_paths','roles','verification_seconds'}
        and p['version']==1 and type(p['version']) is int
        and p['original_activation_sha256']==hashlib.sha256(original).hexdigest()
        and all(type(p[k]) in (int,float) for k in ('not_before','expires_at'))
        and p['not_before'] <= time.time() < p['expires_at']
        and 0 < p['expires_at']-p['not_before'] <= 86400,'held_authority_invalid')
    r=p['before']['receipt'];j=p['before']['job'];l=p['before']['lease']
    require(r['state']=='running' and r['generation']==2 and r['job_id']==j['id']==l['owner_job_id']
        and l['state']=='active' and j['status']=='blocked' and j['result'] is None
        and j['error']=='pcp_local_unreviewed_codex_configuration'
        and all(a[k]==r[k] for k in ('issue_number','base_sha','body_sha256','baseline_revision','baseline_source_commit')),
        'held_original_identity_changed')
    return {**a,'held_verification':p}
