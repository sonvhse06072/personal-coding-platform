"""GH-815 source tests. Real shell/Git/temp files; strict fake Docker/DDEV only.

Also runnable with stdlib unittest when host pytest is unavailable. No install,
real daemon, DDEV lifecycle, DB, credential store or provider is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = 'scripts/pcp-local-trusted-bootstrap.sh'
COMPOSE = 'profiles/pcp-local/docker-compose.local.yaml'
INSTANCE = 'pcp-local-fixture815'
REPO = 'https://github.com/sonvhse06072/personal-coding-platform.git'
APPROVAL = 'https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-9999999999'

# Strict command simulator: unknown requests fail, never fall through to Docker.
FAKE_DOCKER = r'''
import json, os, pathlib, sys
args = sys.argv[1:]
assert args[:2] == ['--host', 'unix:///var/run/docker.sock']
args = args[2:]
with open(os.environ['FAKE_LOG'], 'a') as out:
    out.write(json.dumps(args) + '\n')
if os.environ.get('FAKE_QUERY_FAIL') and args[0] in ('ps', 'volume', 'network', 'image'):
    sys.exit(31)
queries = (
    ['ps', '-aq', '--filter', 'name=^/pcp-local-fixture815-'],
    ['volume', 'ls', '-q', '--filter', 'name=pcp-local-fixture815'],
    ['network', 'ls', '-q', '--filter', 'name=pcp-local-fixture815'],
)
image_query = (len(args) == 5 and args[:4] == ['image', 'ls', '-q', '--filter']
               and args[4] in ['reference=pcp-local-fixture815-' + s + ':*'
                              for s in ('router', 'runtime', 'ddev-executor')])
if args in queries or image_query:
    if os.environ.get('FAKE_COLLISION') == args[0]:
        print('opaque-collision-id')
    sys.exit(0)
if args[0] == 'build':
    assert args[1:3] == ['--builder', 'default']
    args = [args[0]] + args[3:]
    if os.environ.get('FAKE_BUILD_FAIL'):
        sys.exit(32)
    context = pathlib.Path(args[-1])
    assert context.parent.name == 'services'
    assert context.name in ('router', 'runtime', 'ddev-executor')
    assert not (context / '.env').exists()
    assert not (context / '.git').exists()
    assert not (context / '.ddev').exists()
    # Inspect the real archive/tar output before the fake build accepts it.
    for directory in (context, context / 'app', context / 'app/nested'):
        assert directory.stat().st_mode & 0o555 == 0o555, directory
    for relative in ('app/__init__.py', 'app/nested/module.py', 'Dockerfile.local'):
        path = context / relative
        assert path.stat().st_mode & 0o444 == 0o444, path
        assert path.stat().st_mode & 0o111 == 0, path
    assert (context / 'app/nested/tool.sh').stat().st_mode & 0o555 == 0o555
    assert len(args) == 20, args
    assert args[1] == '--file' and args[3] == '--tag' and args[5] == '--iidfile'
    assert args[7] == args[9] == '--label'
    assert args[11] == args[13] == args[15] == args[17] == '--build-arg'
    assert args[4].startswith('pcp-local-fixture815-' + context.name + ':')
    assert 'CODEX_VERSION=0.160.0' in args
    assert 'OPENCODE_VERSION=1.2.3' in args
    recipe = pathlib.Path(args[2]).read_text()
    assert '@sha256:' in recipe.splitlines()[0]
    digest = {'router': 'a', 'runtime': 'b', 'ddev-executor': 'c'}[context.name]
    pathlib.Path(args[6]).write_text('sha256:' + digest * 64 + '\n')
    sys.exit(0)
if args[0] == 'run':
    assert args[:6] == ['run', '--rm', '--pull=never', '--network=none', '--read-only', '--cap-drop=ALL']
    assert '--security-opt=no-new-privileges' in args
    mount = args[args.index('--mount') + 1]
    assert mount.startswith('type=bind,source=') and mount.endswith(',target=/output')
    target = pathlib.Path(mount[len('type=bind,source='):].removesuffix(',target=/output'))
    assert str(target) == os.environ['FAKE_INSTALL'] + '/instance'
    assert args[args.index('--mount') + 2] == 'sha256:' + 'b' * 64
    assert args[-3:-1] == ['python3', '-c']
    # Execute the actual setup code only in the fake directory, not a container.
    # Its sole absolute output prefix is replaced; no shell/process/network calls.
    code = args[-1].replace('"/output/', '"' + str(target) + '/')
    exec(compile(code, '<container-token-setup-fixture>', 'exec'))
    sys.exit(0)
raise AssertionError('unexpected Docker command: ' + repr(args))
'''


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pcp-local-source-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'source'
        self.repo.mkdir()
        self.install = self.base / 'home' / INSTANCE
        self.bin = self.base / 'fake-bin'
        self.bin.mkdir()
        self.log = self.base / 'docker.log'
        self.env = {
            'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
            'HOME': str(self.base / 'home'),
            'LANG': 'C.UTF-8',
            'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
            'FAKE_LOG': str(self.log), 'FAKE_INSTALL': str(self.install),
        }
        Path(self.env['HOME']).mkdir()
        paths = [SCRIPT, COMPOSE,
                 'config/tool-versions.env', 'config/projects.pcp-local.yml',
                 'config/project-baselines.pcp-local.yml', 'config/models.yml',
                 'config/routing-policy.yml']
        for service in ('router', 'runtime', 'ddev-executor'):
            paths.extend('services/' + service + '/' + p for p in
                         ('Dockerfile', 'requirements.txt', 'requirements-dev.txt'))
        for path in paths:
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())
        for service in ('router', 'runtime', 'ddev-executor'):
            app = self.repo / 'services' / service / 'app'
            (app / 'nested').mkdir(parents=True)
            (app / '__init__.py').write_bytes((ROOT / 'services' / service / 'app/__init__.py').read_bytes())
            (app / 'nested/module.py').write_text('VALUE = "reviewed source"\n')
            script = app / 'nested/tool.sh'
            script.write_text('#!/bin/sh\nprintf "source fixture\\n"\n')
            script.chmod(0o755)
        # Poison legacy checkout files: none may enter instance/config/build.
        (self.repo / '.ddev').mkdir()
        (self.repo / '.ddev/config.yaml').write_text('hooks: LEGACY_MUST_NOT_RUN\n')
        (self.repo / 'config/projects.yml').write_text('FOREIGN_MUST_NOT_MOUNT\n')
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Source fixture')
        self.git('remote', 'add', 'origin', REPO)
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture inputs')
        self.head = self.git('rev-parse', 'HEAD').strip()
        self.executable('docker', '#!' + sys.executable + '\n' + FAKE_DOCKER)
        self.executable('ddev', '#!/bin/sh\necho UNEXPECTED_DDEV_CALL >&2\nexit 91\n')
        self.executable('id', '#!/bin/sh\ncase "$1" in -u|-g) echo 1000;; *) exit 92;; esac\n')
        self.executable('stat', '#!/bin/sh\nif [ "$*" = "-c %g /var/run/docker.sock" ]; then echo 999; else exec /usr/bin/stat "$@"; fi\n')

    def executable(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], env=self.env,
                              check=True, capture_output=True, text=True).stdout

    def run_script(self, *args, **env):
        return subprocess.run(['bash', str(self.repo / SCRIPT), '--root', str(self.install),
                               '--instance', INSTANCE, *args], env={**self.env, **env},
                              capture_output=True, text=True)

    def apply_args(self):
        return ('--apply', '--source-commit', self.head, '--owner-approval', APPROVAL,
                '--node-base', 'node:22-bookworm-slim@sha256:' + '1' * 64,
                '--python-base', 'python:3.13-slim-bookworm@sha256:' + '2' * 64,
                '--opencode-version', '1.2.3',
                '--postgres-image', 'postgres:17-bookworm@sha256:' + '3'*64)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_dry_run_writes_nothing_and_never_queries_host(self):
        before = sorted(str(p.relative_to(self.base)) for p in self.base.rglob('*'))
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PLAN_ONLY; RESOURCE_COLLISIONS=NOT_CHECKED', result.stdout)
        self.assertIn('CODEX_VERSION=0.160.0', result.stdout)
        self.assertIn('CODEX_LIVE=STOP', result.stdout)
        self.assertEqual(self.calls(), [])
        self.assertEqual(before, sorted(str(p.relative_to(self.base)) for p in self.base.rglob('*')))

    def test_foreign_repository_denied_before_any_host_call(self):
        self.git('remote', 'set-url', 'origin', 'https://github.com/foreign/project.git')
        result = self.run_script()
        self.assertIn('STOP_REPOSITORY_IDENTITY', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_unsafe_roots_names_and_unknown_modes(self):
        cases = [('--root', '/'), ('--root', '/mnt/c/pcp'), ('--root', str(self.repo)),
                 ('--root', str(self.repo / INSTANCE)),
                 ('--root', str(self.repo / 'nested')), ('--root', str(self.base / '../escape')),
                 ('--root', str(self.base / 'bad$HOME')), ('--instance', 'personal-coding-platform'),
                 ('--instance', 'chonhac'), ('--start',), ('--rollback',), ('--apply',)]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.run_script(*args).returncode, 2)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.install.exists())

    def test_existing_root_and_symlink_are_never_adopted(self):
        self.install.mkdir()
        sentinel = self.install / 'existing-db'
        sentinel.write_text('preserve')
        self.assertIn('STOP_ROOT_EXISTS', self.run_script().stderr)
        self.assertIn('STOP_EXISTING_OR_PARTIAL_ROOT', self.run_script(*self.apply_args()).stderr)
        self.assertEqual(sentinel.read_text(), 'preserve')
        link = self.base / 'linked'
        link.symlink_to(self.install, target_is_directory=True)
        self.assertIn('STOP_ROOT_SYMLINK', self.run_script('--root', str(link)).stderr)
        self.assertEqual(self.calls(), [])

    def test_apply_requires_new_physical_delegation_exact_head_and_pins(self):
        for extra in [('--source-commit', '0' * 40), ('--node-base', 'node:latest'),
                      ('--python-base', 'python:3.13\nRUN bad-slim-bookworm@sha256:' + '2' * 64),
                      ('--python-base', 'python:latest'), ('--opencode-version', 'latest'),
                      ('--postgres-image', 'postgres:latest'), ('--postgres-image', 'postgres:16-bookworm@sha256:'+'3'*64),
                      ('--owner-approval', 'true')]:
            with self.subTest(extra=extra):
                self.assertEqual(self.run_script(*self.apply_args(), *extra).returncode, 2)
        for comment in ('6438475541', '6438904126', '6440446016', '6446718577', '6447953456'):
            result = self.run_script(*self.apply_args(), '--owner-approval',
                                    APPROVAL.replace('9999999999', comment))
            self.assertIn('STOP_SOURCE_APPROVAL_IS_NOT_PHYSICAL', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_dirty_source_and_ambient_overrides_deny_before_docker(self):
        for key in ('DOCKER_HOST', 'COMPOSE_PROFILES', 'BUILDX_BUILDER',
                    'PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION', 'DDEV_APPROOT'):
            with self.subTest(key=key):
                result = self.run_script(*self.apply_args(), **{key: 'unsafe'})
                self.assertIn('STOP_AMBIENT_OVERRIDE', result.stderr)
        (self.repo / 'unreviewed').write_text('no')
        self.assertIn('STOP_SOURCE_DIRTY', self.run_script(*self.apply_args()).stderr)
        self.assertEqual(self.calls(), [])

    def test_all_resource_collisions_refuse_before_root_or_build(self):
        for kind in ('ps', 'volume', 'network', 'image'):
            with self.subTest(kind=kind):
                result = self.run_script(*self.apply_args(), FAKE_COLLISION=kind)
                self.assertIn('STOP_RESOURCE_COLLISION', result.stderr)
                self.assertFalse(self.install.exists())
        self.assertFalse(any(call[0] in ('build', 'run') for call in self.calls()))

    def test_inventory_failure_is_not_absence(self):
        result = self.run_script(*self.apply_args(), FAKE_QUERY_FAIL='1')
        self.assertIn('STOP_RESOURCE_QUERY_FAILED', result.stderr)
        self.assertFalse(self.install.exists())

    def test_preparation_builds_scoped_images_and_stages_no_legacy_hooks(self):
        result = self.run_script(*self.apply_args())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PREPARED; COMPOSE_START=NOT_RUN', result.stdout)
        self.assertEqual([c[0] for c in self.calls()].count('build'), 3)
        self.assertEqual([c[0] for c in self.calls()].count('run'), 1)
        instance = self.install / 'instance'
        self.assertTrue((instance / 'docker-compose.local.yaml').is_file())
        self.assertFalse((instance / '.ddev').exists())
        self.assertEqual(set(p.name for p in (instance / 'config').iterdir()),
                         {'projects.pcp-local.yml', 'project-baselines.pcp-local.yml', 'models.yml', 'routing-policy.yml'})
        env = (instance / '.env').read_text()
        for service, digest in (('ROUTER', 'a'), ('RUNTIME', 'b'), ('EXECUTOR', 'c')):
            self.assertIn('PCP_LOCAL_' + service + '_IMAGE=sha256:' + digest * 64, env)
        self.assertIn('COMPOSE_PROFILES=\n', env)
        self.assertNotIn('owner-approved', env)
        self.assertEqual((self.install / 'sources/personal-coding-platform/.git/HEAD').read_text().strip(), self.head)
        for service in ('router', 'runtime', 'ddev-executor'):
            self.assertTrue((self.install / ('logs/' + service + '.build.log')).is_file())
            self.assertIn('@sha256:', (self.install / ('build/services/' + service + '/Dockerfile.local')).read_text())
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_service_tokens_are_fresh_scoped_and_never_in_output(self):
        result = self.run_script(*self.apply_args())
        self.assertEqual(result.returncode, 0, result.stderr)
        values = {}
        for name in ('router', 'coding-runtime', 'ddev-executor', 'db'):
            path = self.install / ('instance/.env.' + name + '.local')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            values[name] = dict(line.split('=', 1) for line in path.read_text().splitlines())
        self.assertEqual(set(values['router']), {'ROUTER_API_TOKEN'})
        self.assertEqual(set(values['ddev-executor']), {'PLATFORM_INTERNAL_TOKEN'})
        self.assertEqual(set(values['coding-runtime']), {'ROUTER_API_TOKEN', 'RUNTIME_API_TOKEN', 'PLATFORM_INTERNAL_TOKEN', 'DATABASE_URL'})
        self.assertEqual(values['router']['ROUTER_API_TOKEN'], values['coding-runtime']['ROUTER_API_TOKEN'])
        self.assertEqual(values['ddev-executor']['PLATFORM_INTERNAL_TOKEN'], values['coding-runtime']['PLATFORM_INTERNAL_TOKEN'])
        tokens = {v for k,v in values['coding-runtime'].items() if k != 'DATABASE_URL'}
        self.assertEqual(len(tokens), 3)
        for token in tokens:
            self.assertEqual(len(token), 64)
            self.assertNotIn(token, result.stdout + result.stderr)
        self.assertEqual(set(values['db']), {'POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD', 'PCP_RUNTIME_PASSWORD'})
        self.assertEqual(values['db']['POSTGRES_USER'], 'pcp_bootstrap')
        self.assertEqual(values['db']['POSTGRES_DB'], 'pcp_local')
        self.assertNotIn(values['db']['POSTGRES_PASSWORD'], result.stdout + result.stderr)
        uri = values['coding-runtime']['DATABASE_URL']
        self.assertTrue(uri.startswith('postgresql://pcp_runtime:'))
        password = uri.split(':', 2)[2].split('@')[0]
        self.assertEqual(len(password), 64)
        self.assertNotEqual(password, values['db']['POSTGRES_PASSWORD'])
        self.assertNotIn(password, result.stdout + result.stderr)
        sql = (self.install/'instance/initdb/01-runtime.sql').read_text()
        self.assertIn('NOSUPERUSER NOCREATEDB NOCREATEROLE', sql)
        self.assertNotIn(password, sql)
        self.assertNotIn(values['db']['POSTGRES_PASSWORD'], sql)
        self.assertEqual(values['db']['PCP_RUNTIME_PASSWORD'], password)
        self.assertIn("PASSWORD :'runtime_password'", sql)
        self.assertIn('getenv runtime_password PCP_RUNTIME_PASSWORD', sql)
        self.assertNotIn('DATABASE_URL', values['ddev-executor'])
        self.assertEqual(list((self.install / 'runtime-home').iterdir()), [])
        self.assertEqual(list((self.install / 'executor-home').iterdir()), [])

    def test_only_build_contexts_become_readable_preserving_source_and_execute_bits(self):
        result = self.run_script(*self.apply_args())
        self.assertEqual(result.returncode, 0, result.stderr)
        for service in ('router', 'runtime', 'ddev-executor'):
            source = self.repo / 'services' / service
            context = self.install / 'build/services' / service
            for path in context.rglob('*'):
                with self.subTest(service=service, path=path.relative_to(context)):
                    mode = path.stat().st_mode & 0o777
                    if path.is_dir():
                        self.assertEqual(mode, 0o755)
                    else:
                        executable = path.name == 'tool.sh'
                        self.assertEqual(mode, 0o755 if executable else 0o644)
                        if path.name != 'Dockerfile.local':
                            self.assertEqual(path.read_bytes(), (source / path.relative_to(context)).read_bytes())
            self.assertEqual(context.stat().st_mode & 0o777, 0o755)
        for relative in ('', 'build', 'build/services', 'instance', 'instance/config',
                         'logs', 'runtime-home', 'executor-home'):
            self.assertEqual((self.install / relative).stat().st_mode & 0o777, 0o700, relative)
        for path in (self.install / 'instance').glob('.env*'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600, path)

    def test_failed_permission_normalization_retains_partial_state_without_retry(self):
        self.executable('chmod', '#!/bin/sh\n'
                        'case "$*" in "-R go+rX ' + str(self.install) + '/build/services/runtime") exit 73;; esac\n'
                        'exec /usr/bin/chmod "$@"\n')
        result = self.run_script(*self.apply_args())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('STOP_BUILD_PERMISSIONS', result.stderr)
        self.assertIn('PARTIAL_STOP; PRESERVE_ROOT_AND_IMAGES', result.stderr)
        self.assertTrue((self.install / 'intent').is_file())
        self.assertFalse((self.install / 'prepared').exists())
        self.assertTrue((self.install / 'build/services/runtime/Dockerfile.local').is_file())
        self.assertEqual((self.install / 'build/services/runtime/app/__init__.py').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.install.stat().st_mode & 0o777, 0o700)
        calls = self.calls()
        self.assertEqual(len([c for c in calls if c[0] == 'build']), 1)
        self.assertFalse(any(c[0] in ('run', 'rm', 'rmi', 'stop', 'prune', 'compose') for c in calls))
        retry = self.run_script(*self.apply_args())
        self.assertIn('STOP_EXISTING_OR_PARTIAL_ROOT', retry.stderr)
        self.assertEqual(self.calls(), calls)

    def test_symlink_and_secret_contexts_stop_before_normalization_or_build(self):
        context = self.repo / 'services/router'
        for relative, content in (('app/unsafe-link', None), ('.env.local', 'TOKEN=fixture\n'),
                                  ('app/auth.json', '{"token": "fixture"}\n'),
                                  ('app/key.txt', '-----BEGIN PRIVATE KEY-----\nfixture\n')):
            with self.subTest(relative=relative):
                path = context / relative
                if content is None:
                    path.symlink_to('/outside-context')
                else:
                    path.write_text(content)
                self.git('add', str(path))
                self.git('commit', '-qm', 'unsafe context fixture')
                self.head = self.git('rev-parse', 'HEAD').strip()
                # Separate fresh root for each refused archived context.
                self.install = self.base / ('home-' + path.name.replace('.', '-')) / INSTANCE
                self.install.parent.mkdir()
                self.env['HOME'] = str(self.install.parent)
                self.env['FAKE_INSTALL'] = str(self.install)
                result = self.run_script(*self.apply_args())
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('STOP_BUILD_SYMLINK' if content is None else 'STOP_BUILD_SECRET', result.stderr)
                self.assertIn('PARTIAL_STOP; PRESERVE_ROOT_AND_IMAGES', result.stderr)
                self.assertFalse((self.install / 'prepared').exists())
                self.assertEqual((self.install / 'build/services/router/app/__init__.py').stat().st_mode & 0o777, 0o600)
                self.git('rm', str(path))
                self.git('commit', '-qm', 'remove unsafe fixture')
        self.assertFalse(any(c[0] in ('build', 'run') for c in self.calls()))

    def test_exact_retry_is_noop_and_changed_inputs_stop(self):
        first = self.run_script(*self.apply_args())
        self.assertEqual(first.returncode, 0, first.stderr)
        calls = self.calls()
        result = self.run_script(*self.apply_args())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ALREADY_PREPARED; NO_ACTION; HEALTH=NOT_ATTESTED', result.stdout)
        self.assertEqual(self.calls(), calls)
        changed = self.run_script(*self.apply_args(), '--opencode-version', '1.2.4')
        self.assertIn('STOP_EXISTING_OR_PARTIAL_ROOT', changed.stderr)
        self.assertEqual(self.calls(), calls)

    def test_build_failure_retains_evidence_and_retry_does_not_mutate(self):
        result = self.run_script(*self.apply_args(), FAKE_BUILD_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PARTIAL_STOP; PRESERVE_ROOT_AND_IMAGES', result.stderr)
        self.assertTrue((self.install / 'intent').exists())
        self.assertFalse((self.install / 'prepared').exists())
        self.assertTrue((self.install / 'logs/router.build.log').exists())
        calls = self.calls()
        retry = self.run_script(*self.apply_args())
        self.assertIn('STOP_EXISTING_OR_PARTIAL_ROOT', retry.stderr)
        self.assertEqual(self.calls(), calls)
        self.assertFalse(any(c[0] in ('rm', 'rmi', 'stop', 'prune', 'compose') for c in calls))

    def test_authority_checker_rejects_in_place_local_baseline_change(self):
        path = self.repo / 'config/project-baselines.pcp-local.yml'
        before = {'projects': {'pcp-local': {'active_revision': None, 'revisions': {
            'r1': {'status': 'approved', 'source_commit': 'a' * 40},
        }}}}
        path.write_text(yaml.safe_dump(before))
        self.git('add', str(path))
        self.git('commit', '-qm', 'approved baseline fixture')
        base = self.git('rev-parse', 'HEAD').strip()
        before['projects']['pcp-local']['revisions']['r1']['source_commit'] = 'b' * 40
        path.write_text(yaml.safe_dump(before))
        self.git('add', str(path))
        self.git('commit', '-qm', 'forbidden rewrite fixture')
        head = self.git('rev-parse', 'HEAD').strip()
        check = runpy.run_path(str(ROOT / 'scripts/check_project_doc_authority.py'))['check']
        body = ('Owner-Approval-Issue: https://github.com/sonvhse06072/personal-coding-platform/issues/815\n'
                'Approved-Protected-Paths: `config/project-baselines.pcp-local.yml`')
        with self.assertRaisesRegex(ValueError, 'changed in place'):
            check(self.repo, base, head, body)


class ConfigurationTests(unittest.TestCase):
    def test_tmpfs_mounts_preserve_options_as_single_yaml_scalars(self):
        services = yaml.safe_load((ROOT / COMPOSE).read_text())['services']
        for service, size in (('router', 67108864), ('coding-runtime', 268435456),
                              ('ddev-executor', 268435456)):
            with self.subTest(service=service):
                self.assertEqual(services[service]['tmpfs'],
                                 [f'/tmp:rw,nosuid,nodev,size={size}'])
        self.assertEqual(services['db']['tmpfs'], [
            '/tmp:rw,nosuid,nodev,size=67108864',
            '/var/run/postgresql:rw,nosuid,nodev,uid=999,gid=999,mode=3775,size=16777216',
        ])

    def test_dependencies_and_real_runtime_build_contract(self):
        services = yaml.safe_load((ROOT / COMPOSE).read_text())['services']
        self.assertEqual(set(services), {'router', 'coding-runtime', 'ddev-executor', 'db'})
        runtime = services['coding-runtime']
        self.assertEqual(runtime['depends_on'], {s: {'condition': 'service_healthy'} for s in ('router', 'ddev-executor', 'db')})
        self.assertEqual(runtime['environment']['ROUTER_URL'], 'http://router:8090')
        self.assertEqual(runtime['environment']['DDEV_EXECUTOR_URL'], 'http://ddev-executor:8790')
        self.assertNotIn('DATABASE_URL', runtime['environment'])
        self.assertEqual(services['db']['image'], '${PCP_LOCAL_POSTGRES_IMAGE:?PostgreSQL 17 digest required}')
        self.assertIn('@openai/codex@${CODEX_VERSION}', (ROOT / 'services/runtime/Dockerfile').read_text())
        for service in services.values():
            self.assertEqual(service['profiles'], ['pcp-local'])
            self.assertEqual(service['pull_policy'], 'never')
            self.assertNotIn('ports', service)
            self.assertNotIn('command', service)

    def test_socket_source_and_credentials_do_not_reach_developer_container(self):
        services = yaml.safe_load((ROOT / COMPOSE).read_text())['services']
        for name, service in services.items():
            with self.subTest(service=name):
                self.assertNotIn('env_file', service.get('environment', {}))
                self.assertEqual(service['env_file'], ['.env.' + name + '.local'])
                self.assertNotIn('privileged', service)
                self.assertNotIn('network_mode', service)
                self.assertEqual(service['cap_drop'], ['ALL'])
                self.assertEqual(service['security_opt'], ['no-new-privileges:true'])
                for mount in service['volumes']:
                    self.assertTrue(mount.startswith(('${PCP_LOCAL_ROOT}/', '/var/run/docker.sock:', 'postgres-data:')), mount)
                    if 'docker.sock' in mount or '/sources:' in mount:
                        self.assertEqual(name, 'ddev-executor')
                for forbidden in ('HOST_HOME', '/config/projects.yml', 'GITHUB_TOKEN', 'GITHUB_DELIVERY_TOKEN', 'host.docker.internal', 'chonhac'):
                    self.assertNotIn(forbidden, str(service))
        self.assertEqual(services['coding-runtime']['environment']['PCP_RUNTIME_STARTUP_MODE'], 'pcp_local_inspect')
        self.assertNotIn('PCP_LOCAL_TASK_', (ROOT / COMPOSE).read_text())

    def test_native_resources_are_explicit_private_and_bounded(self):
        doc = yaml.safe_load((ROOT / COMPOSE).read_text())
        self.assertEqual(doc['name'], '${PCP_LOCAL_INSTANCE:?explicit instance required}')
        self.assertEqual(set(doc['networks']), {'private'})
        self.assertEqual(doc['networks']['private']['name'], '${PCP_LOCAL_INSTANCE}-private')
        self.assertEqual(set(doc['volumes']), {'postgres-data'})
        self.assertEqual(doc['volumes']['postgres-data']['name'], '${PCP_LOCAL_INSTANCE}-postgres-data')
        self.assertEqual(sum(s['cpus'] for s in doc['services'].values()), 4)
        for name, service in doc['services'].items():
            self.assertEqual(service['networks'], ['private'])
            self.assertEqual(service['memswap_limit'], service['mem_limit'])
            self.assertTrue(service['read_only'])
            self.assertGreater(service['pids_limit'], 0)
            self.assertEqual(service['container_name'], '${PCP_LOCAL_INSTANCE}-' + name)
            self.assertNotIn('build', service)
            self.assertNotIn('ports', service)
            self.assertNotIn('volumes_from', service)
        db = doc['services']['db']
        self.assertEqual(db['user'], '999:999')
        self.assertEqual(db['volumes'], ['postgres-data:/var/lib/postgresql/data',
            '${PCP_LOCAL_ROOT}/instance/initdb:/docker-entrypoint-initdb.d:ro'])
        self.assertEqual(db['env_file'], ['.env.db.local'])
        self.assertNotIn('ddev-global-cache', (ROOT / COMPOSE).read_text())
        self.assertNotIn('ddev-router', (ROOT / COMPOSE).read_text())
        requirements = (ROOT / 'services/runtime/requirements-dev.txt').read_text()
        self.assertIn('pytest==8.4.1', requirements)
        self.assertIn('PyYAML==6.0.2', (ROOT / 'services/runtime/requirements.txt').read_text())
        self.assertIn('/opt/venv', (ROOT / 'services/runtime/Dockerfile').read_text())

    def test_registry_and_baseline_stay_inactive(self):
        cfg = yaml.safe_load((ROOT / 'config/projects.pcp-local.yml').read_text())['projects']
        self.assertEqual(set(cfg), {'pcp-local'})
        self.assertEqual(cfg['pcp-local']['repository'], 'sonvhse06072/personal-coding-platform')
        self.assertIsNone(cfg['pcp-local']['path'])
        self.assertEqual(cfg['pcp-local']['registration_status'], 'draft')
        self.assertTrue(all(v is False for v in cfg['pcp-local']['autonomy'].values()))
        self.assertFalse(cfg['pcp-local']['ddev']['enabled'])
        baseline = yaml.safe_load((ROOT / 'config/project-baselines.pcp-local.yml').read_text())
        self.assertEqual(baseline['projects'], {'pcp-local': {'active_revision': None, 'revisions': {}}})

    def test_bootstrap_and_future_reader_are_protected(self):
        policy = runpy.run_path(str(ROOT / 'scripts/check_project_doc_authority.py'))
        for path in (SCRIPT, COMPOSE, 'services/ddev-executor/app/main.py', 'services/runtime/app/pcp_local_trusted_readers.py'):
            self.assertEqual(policy['classify_path'](path), 'protected')
        before = {'projects': {'pcp-local': {'revisions': {'r1': {'status': 'approved', 'source_commit': 'a' * 40}}}}}
        after = {'projects': {'pcp-local': {'revisions': {'r1': {'status': 'approved', 'source_commit': 'b' * 40}}}}}
        with self.assertRaisesRegex(ValueError, 'changed in place'):
            policy['require_existing_baseline_revisions_immutable'](before, after)


if __name__ == '__main__':
    unittest.main()
