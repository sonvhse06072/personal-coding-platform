"""Real producer/Git tests, no provider, credentials, model or live resources."""
import asyncio
import ctypes
import os
from pathlib import Path

import pytest

from app import pcp_local_worker_loop as guard
from app.pcp_local_recovery import recover_verified_job
from app.pcp_local_task_queue import TaskStop
from pcp_sparse_fixture import sparse_verified  # noqa:F401
from test_pcp_local_consolidation import verified  # noqa:F401


@pytest.fixture(params=['verified', 'sparse_verified'])
def committed(request):
    v = request.getfixturevalue(request.param)
    asyncio.run(recover_verified_job(v.engine, v.reader, v.task, v.store.row))
    return v


def check(v):
    with guard._retained_git(v.path) as proof:
        assert proof(v.store.row, v.task.base_sha) == v.store.row['result']['commit']


@pytest.fixture
def watched(tmp_path_factory):
    """Kernel evidence that Git never opened/read an external include target."""
    path = tmp_path_factory.mktemp('external') / 'external-config'
    path.write_text('[core]\nfsmonitor = forbidden\n')
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    assert fd >= 0
    assert libc.inotify_add_watch(fd, os.fsencode(path), 0x01 | 0x20) >= 0  # ACCESS | OPEN
    try:
        yield path
        with pytest.raises(BlockingIOError):
            os.read(fd, 65536)
    finally:
        os.close(fd)


def test_real_producer_proof_preserves_every_original_byte_and_metadata(committed):
    v = committed
    before = guard._retained_snapshot(v.path)
    check(v)
    check(v)
    assert guard._retained_snapshot(v.path) == before


@pytest.mark.parametrize('location', ['config', 'config.worktree'])
@pytest.mark.parametrize('attack', ['include', 'includeIf', 'filter', 'fsmonitor', 'diff',
    'hooks', 'worktree', 'attributes', 'excludes', 'extension', 'promisor', 'duplicate', 'filemode'])
def test_hostile_configuration_denied_before_any_proof_or_external_read(
        committed, watched, tmp_path, monkeypatch, location, attack):
    v = committed
    marker = watched.parent / 'executed'
    script = watched.parent / 'hostile'
    script.write_text('#!/bin/sh\ntouch "{}"\n'.format(marker))
    script.chmod(0o755)
    commands = {
        'include': '[include]\npath = {}\n'.format(watched),
        'includeIf': '[includeIf "gitdir:/**"]\npath = {}\n'.format(watched),
        'filter': '[filter "evil"]\nclean = {}\n'.format(script),
        'fsmonitor': '[core]\nfsmonitor = {}\n'.format(script),
        'diff': '[diff]\nexternal = {}\n'.format(script),
        'hooks': '[core]\nhooksPath = {}\n'.format(tmp_path),
        'worktree': '[core]\nworktree = {}\n'.format(tmp_path),
        'attributes': '[core]\nattributesFile = {}\n'.format(watched),
        'excludes': '[core]\nexcludesFile = {}\n'.format(watched),
        'extension': '[extensions]\npartialClone = origin\n',
        'promisor': '[remote "origin"]\npromisor = true\n',
        'duplicate': '[CORE]\nFileMode = true\n',
        'filemode': '[core]\nfileMode = false\n',
    }
    with (v.path / '.git' / location).open('a') as out:
        out.write('\n' + commands[attack])
    def forbidden(*a, **kw):
        pytest.fail('proof must not execute for rejected configuration')
    monkeypatch.setattr(guard, '_retained_proof', forbidden)
    before = guard._retained_snapshot(v.path)
    with pytest.raises(TaskStop):
        check(v)
    assert guard._retained_snapshot(v.path) == before and not marker.exists()


@pytest.mark.parametrize('attack', ['config_link', 'index_link', 'file_link', 'hardlink',
    'alternates', 'http_alternates', 'commondir', 'grafts', 'replacement', 'fifo'])
def test_filesystem_escape_never_opens_external_target(committed, watched, attack):
    v = committed
    gd = v.path / '.git'
    if attack in ('config_link', 'index_link'):
        target = gd / attack.removesuffix('_link')
        target.unlink(); target.symlink_to(watched)
    elif attack == 'file_link':
        (v.path / 'outside').symlink_to(watched)
    elif attack == 'hardlink':
        os.link(watched, v.path / 'outside')
    elif attack == 'fifo':
        os.mkfifo(v.path / 'pipe')
    else:
        target = gd / dict(alternates='objects/info/alternates',
            http_alternates='objects/info/http-alternates', commondir='commondir',
            grafts='info/grafts', replacement='refs/replace')[attack]
        target.write_text(str(watched))
    with pytest.raises(TaskStop):
        check(v)


@pytest.mark.parametrize('attack', ['assume', 'skip', 'skip_content', 'assume_mode',
    'sparse_pattern', 'worktree_boolean', 'config_missing', 'index_content', 'parent',
    'omitted_removed', 'omitted_materialized'])
def test_index_sparse_and_history_drift_is_rejected(committed, attack):
    v = committed
    if attack in ('assume', 'assume_mode'):
        v.git('update-index', '--assume-unchanged', 'new.py')
        if attack == 'assume_mode': (v.path / 'new.py').chmod(0o755)
    elif attack in ('skip', 'skip_content'):
        v.git('update-index', '--skip-worktree', 'new.py')
        if attack == 'skip_content': (v.path / 'new.py').write_text('concealed drift')
    elif attack == 'sparse_pattern':
        (v.path / '.git/info/sparse-checkout').write_text('/*\n!/new.py\n')
    elif attack == 'worktree_boolean':
        with (v.path / '.git/config.worktree').open('a') as out:
            out.write('[core]\nsparseCheckout = false\n')
    elif attack == 'config_missing':
        (v.path / '.git/config').unlink()
    elif attack == 'index_content':
        (v.path / 'new.py').write_text('staged drift')
        v.git('add', 'new.py')
    elif attack.startswith('omitted_'):
        if not (v.path / '.git/config.worktree').exists():
            # Non-sparse paths are fully materialized; concealed normal paths
            # are tested above. This case specifically exercises sparse output.
            v.git('update-index', '--skip-worktree', 'new.py')
        elif attack == 'omitted_removed':
            v.git('update-index', '--force-remove', '.ddev/config.yaml')
        else:
            (v.path / '.ddev').mkdir()
            (v.path / '.ddev/config.yaml').write_text('unverified excluded bytes')
    else:
        parent = v.git('rev-parse', 'HEAD')
        extra = v.git('commit-tree', 'HEAD^{tree}', '-p', parent, '-p', v.task.base_sha, '-m', 'extra parent')
        v.git('update-ref', 'HEAD', extra)
    with pytest.raises(TaskStop):
        check(v)


@pytest.mark.parametrize('location', ['config', 'config.worktree'])
def test_config_race_uses_safe_snapshot_then_rejects_original_drift(committed, watched, monkeypatch, location):
    v = committed
    original = guard._retained_proof
    ran = []
    def racing(*args):
        with (v.path / '.git' / location).open('a') as out:
            out.write('\n[include]\npath = {}\n'.format(watched))
        ran.append(original(*args))
        return ran[-1]
    monkeypatch.setattr(guard, '_retained_proof', racing)
    with pytest.raises(TaskStop, match='retained_files_changed'):
        check(v)
    assert ran == [v.store.row['result']['commit']]


def test_inherited_git_configuration_is_not_read(committed, watched, monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(watched))
    monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
    monkeypatch.setenv('GIT_CONFIG_KEY_0', 'include.path')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0', str(watched))
    monkeypatch.setenv('GIT_DIR', str(watched.parent))
    check(committed)


def test_git_case_and_boolean_aliases_are_explicit(committed):
    v = committed
    config = v.path / '.git/config'
    config.write_text(config.read_text().replace('[core]', '[CORE]').replace('filemode = true', 'FileMode = YeS'))
    check(v)
    # Git's explicit empty boolean is FALSE, not the implicit no-value TRUE.
    config.write_text(config.read_text().replace('FileMode = YeS', 'FileMode ='))
    with pytest.raises(TaskStop):
        check(v)
