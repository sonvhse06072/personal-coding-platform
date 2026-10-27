"""Current PCP-only profile; obsolete placeholder compatibility retired by V3."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'profiles/pcp-local/.ddev'


def test_instance_template_has_no_legacy_hooks_or_addons():
    cfg = yaml.safe_load((PROFILE / 'config.yaml').read_text())
    assert cfg['database'] == {'type': 'postgres', 'version': '17'}
    assert 'hooks' not in cfg
    assert set(p.name for p in PROFILE.iterdir()) == {'config.yaml', 'docker-compose.platform.yaml'}
    assert not PROFILE.is_relative_to(ROOT / '.ddev')


def test_current_profile_uses_real_service_entrypoints_and_opt_in():
    services = yaml.safe_load((PROFILE / 'docker-compose.platform.yaml').read_text())['services']
    assert set(services) == {'router', 'coding-runtime', 'ddev-executor'}
    for service in services.values():
        assert service['profiles'] == ['pcp-local']
        assert service['pull_policy'] == 'never'
        assert service['restart'] == 'no'
        assert 'command' not in service and 'entrypoint' not in service
        assert 'ports' not in service and 'build' not in service
        assert 'source-unresolved' not in service['image']


def test_preparation_does_not_register_or_activate_a_project():
    projects = yaml.safe_load((ROOT / 'config/projects.pcp-local.yml').read_text())
    assert set(projects['projects']) == {'pcp-local'}
    project = projects['projects']['pcp-local']
    assert project['repository'] == 'sonvhse06072/personal-coding-platform'
    assert project['registration_status'] == 'draft' and project['path'] is None
    assert all(value is False for value in project['autonomy'].values())
    assert project['runtime']['developer_permission_mode'] == 'bounded'
    assert project['runtime']['workspace_mode'] == 'isolated_clone'
    baseline = yaml.safe_load((ROOT / 'config/project-baselines.pcp-local.yml').read_text())
    assert baseline['projects'] == {'pcp-local': {'active_revision': None, 'revisions': {}}}
