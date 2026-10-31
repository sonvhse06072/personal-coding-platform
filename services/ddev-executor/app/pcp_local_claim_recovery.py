"""Private repair-release observation; no repair authority accepted over HTTP."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from fastapi import HTTPException
from .pcp_local_observer import configuration_digest

PERMIT = Path('/config/pcp-local-claim-recovery.json')
ORIGINAL = Path('/config/pcp-local-original-activation.json')


def require(ok, code='claim_recovery_release_binding_invalid'):
    if not ok:
        raise HTTPException(409, code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def enabled():
    return os.getenv('PCP_LOCAL_CLAIM_RECOVERY_ENABLED', '') == 'owner-approved'


def _read(path):
    require(path.is_file() and not path.is_symlink(), 'claim_recovery_private_file_missing')
    stat = path.stat()
    require(stat.st_uid in (0, os.getuid()) and stat.st_mode & 0o077 == 0)
    return path.read_bytes()


def activation():
    require(enabled(), 'claim_recovery_disabled')
    raw = _read(ORIGINAL)
    a, p = json.loads(raw), json.loads(_read(PERMIT))
    require(set(p) == {'version', 'decision_id', 'execution_record', 'not_before', 'expires_at',
        'receipt_before', 'original_activation_sha256', 'original_activation_digest',
        'repair_source', 'repair_commits', 'repair_paths', 'roles'}
        and type(p['version']) is int and p['version'] == 1
        and p['original_activation_sha256'] == hashlib.sha256(raw).hexdigest()
        and p['original_activation_digest'] == digest(a)
        and all(type(p[k]) in (int, float) for k in ('not_before', 'expires_at'))
        and p['not_before'] <= time.time() < p['expires_at']
        and 0 < p['expires_at'] - p['not_before'] <= 86400
        and p['execution_record'].startswith('https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-')
        and a['project_id'] == 'pcp-local'
        and a['repository'] == 'sonvhse06072/personal-coding-platform'
        and all(a[k] == p['receipt_before'][k] for k in ('issue_number', 'base_sha', 'body_sha256',
            'baseline_revision', 'baseline_source_commit'))
        and p['receipt_before']['state'] == 'claimed' and type(p['receipt_before']['generation']) is int
        and p['receipt_before']['generation'] == 1)
    return {**a, 'claim_recovery': p}


def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], check=False,
        capture_output=True, text=True, timeout=20,
        env={'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'GIT_CONFIG_NOSYSTEM': '1',
             'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_OPTIONAL_LOCKS': '0'})
    require(result.returncode == 0, 'claim_recovery_git_evidence_unavailable')
    return result.stdout.strip()


def release(a, repo, root, inspect, *, binding_key="claim_recovery"):
    require(binding_key in {"claim_recovery", "held_verification", "local_review_repair"})
    p = a[binding_key]
    receipt_before = p["receipt_before"] if binding_key == "claim_recovery" else p["before"]["receipt"]
    source, repair = a['base_sha'], p['repair_source']
    require(re.fullmatch('[0-9a-f]{40}', repair) and repair != source)
    git(repo, 'merge-base', '--is-ancestor', source, repair)
    commits = git(repo, 'rev-list', '--reverse', '--topo-order', source+'..'+repair).splitlines()
    paths = git(repo, 'diff', '--no-renames', '--name-only', source, repair, '--').splitlines()
    require(commits == p['repair_commits'] and sorted(paths) == p['repair_paths'],
            'claim_recovery_repair_range_changed')
    require(not git(repo, 'log', '--full-history', '--format=%H', source+'..'+repair, '--',
                    *receipt_before['allowed_paths']), 'claim_recovery_pilot_paths_changed')
    # Router at S is permitted only when its complete build context and registry
    # inputs are unchanged across every repair commit, including reverted edits.
    require(not git(repo, 'log', '--full-history', '--format=%H', source+'..'+repair, '--',
        'services/router', 'config/models.yml', 'config/routing-policy.yml'),
        'claim_recovery_router_inputs_changed')
    require(set(p['roles']) == {'runtime', 'executor', 'router', 'verifier'})
    for role, binding in p['roles'].items():
        expected_source = repair if role in ('runtime', 'executor') else source
        if binding_key != 'claim_recovery' and role == 'router':
            expected_source = binding['source_commit']
            require(re.fullmatch('[0-9a-f]{40}', expected_source))
            git(repo, 'merge-base', '--is-ancestor', expected_source, source)
            require(not git(repo, 'log', '--full-history', '--format=%H', expected_source+'..'+repair, '--',
                'services/router', 'config/models.yml', 'config/routing-policy.yml'), 'held_router_inputs_changed')
        require(binding['source_commit'] == expected_source
            and re.fullmatch('sha256:[0-9a-f]{64}', binding['image_id']))
        image = inspect('image', binding['image_id'])
        labels = image.get('Config', {}).get('Labels', {})
        require(image['Id'] == binding['image_id']
            and labels.get('org.opencontainers.image.revision') == expected_source
            and labels.get('org.pcp.local.instance') == root.name,
            'claim_recovery_image_changed')
        if role == 'verifier':
            require(binding['image_id'] == a['verification_image'] == a['runtime_image_id'])
            continue
        name = root.name + '-' + {'runtime': 'coding-runtime', 'executor': 'ddev-executor', 'router': 'router'}[role]
        row = inspect('container', name)
        require(row['Name'] == '/'+name and row['State']['Running'] is True
            and row['Image'] == row['Config']['Image'] == binding['image_id']
            and row['Config']['Labels'].get('org.opencontainers.image.revision') == expected_source
            and row['Config']['Labels'].get('org.pcp.local.instance') == root.name
            and configuration_digest(row) == binding['configuration_sha256'],
            'claim_recovery_container_changed')
        # Configuration fingerprint includes ALL mounts/env/capabilities. Every
        # bind must additionally be nonrecursive; images cannot override it.
        require(all(m.get('BindOptions') == {'NonRecursive': True}
            for m in row['HostConfig'].get('Mounts', []) if m.get('Type') == 'bind'),
            'claim_recovery_recursive_mount')
    return repair
