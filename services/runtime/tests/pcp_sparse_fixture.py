"""Real Executor handler in a separate interpreter; only synthetic local custody."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from app import pcp_local_recovery as recovery
from app.pcp_local_worker_loop import stable_job_id
from test_pcp_local_consolidation import make_verified


@pytest.fixture
def sparse_verified(tmp_path):
    root = tmp_path / 'pcp-local-sparse-fixture'
    source = root / 'sources/personal-coding-platform'
    source.mkdir(parents=True)
    (root / 'home').mkdir()
    v = make_verified(source, legacy_ddev=True)
    v.git('branch', '-m', 'main')  # A canonical source is not already the task branch.
    registry = root / 'projects.yml'
    registry.write_text(yaml.safe_dump({'projects': {'pcp-local': {
        'path': str(source), 'repository': v.task.repository,
        'registration_status': 'approved', 'base_branch': 'main',
        'runtime': {'workspace_mode': 'isolated_clone', 'developer_permission_mode': 'bounded'},
        'ddev': {'enabled': True},
    }}}))
    activation = dict(root=str(root), issue_number=v.task.issue_number,
        body_sha256=v.task.body_sha256, base_sha=v.task.base_sha,
        baseline_revision=v.task.baseline_revision)
    executor = Path(__file__).resolve().parents[2] / 'ddev-executor'
    program = '''
import json,sys
sys.path.insert(0,sys.argv[1])
from app import main
a=json.load(sys.stdin)
main._pcp_activation=lambda:a['activation']  # Only external authority is synthetic.
result=main.create_workspace(main.WorkspaceRequest(job_id=a['job_id'],
    project_id='pcp-local',ref=a['activation']['base_sha'],workspace_mode='isolated_clone'))
print(json.dumps(result))
'''
    env = dict(PATH=os.defpath, HOME=str(root/'home'), GIT_CONFIG_NOSYSTEM='1',
        GIT_CONFIG_GLOBAL='/dev/null', PYTHONDONTWRITEBYTECODE='1',
        PROJECTS_FILE=str(registry), CODING_PROJECTS_ROOT=str(root/'sources'),
        CODING_WORKSPACES_ROOT=str(root/'workspaces'),
        PLATFORM_INTERNAL_TOKEN='synthetic-executor-token')
    result = subprocess.run([sys.executable, '-I', '-B', '-c', program, str(executor)],
        input=json.dumps(dict(activation=activation, job_id=stable_job_id(v.task))),
        cwd=root, env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    path = Path(json.loads(result.stdout)['workspace'])
    assert not (path/'.ddev').exists() and (source/'.ddev/config.yaml').is_file()
    (path/'new.py').write_bytes((source/'new.py').read_bytes())
    # Construct verified A only AFTER the real producer has created its metadata.
    v.path = path
    v.git = lambda *args: recovery.git(path, *args)
    v.store.row['workspace'] = str(path)
    proof = v.store.row['checkpoint']['pcp_local_execution']
    proof['verified_tree'] = recovery.verified_tree(path, v.task, proof['diff'])
    return v
