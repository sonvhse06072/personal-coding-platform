"""Real PostgreSQL + real Git; opt-in disposable DSN, never the installed PCP DB."""
import asyncio
from copy import deepcopy
import os
from types import SimpleNamespace
import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from app.storage import Storage
from app.pcp_local_readiness import initialize_schema, schema_readiness
from app.pcp_local_recovery import recover_verified_job
from app.pcp_local_task_queue import TaskStop, REPOSITORY
from app.dashboard_local import build_local_snapshot
from app.engine_core import RuntimeEngineCore
from app.adapters.base import AgentRun
from test_pcp_local_consolidation import verified  # noqa: F401


@pytest.fixture
def database():
    dsn = os.getenv('PCP_CHECKPOINT_TEST_DSN')
    if not dsn:
        pytest.skip('requires disposable PCP_CHECKPOINT_TEST_DSN')
    schema = 'consolidation_' + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(schema)))
        conn.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(schema),sql.Identifier(schema)))
    class Scoped(Storage):
        def connect(self):
            return psycopg.connect(dsn, row_factory=dict_row, options=f'-csearch_path={schema} -crole={schema}')
    db = Scoped()
    try:
        yield db
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(schema)))


def seed(db, v):
    initialize_schema(db)
    db.create(v.store.row)
    binding = v.store.row['checkpoint']['pcp_local_source']['receipt']
    receipt = dict(binding, repository=REPOSITORY, project_id='pcp-local', task_key=v.task.task_key,
                   state='running', generation=2, job_id=v.store.row['id'])
    with db.connect() as conn:
        conn.execute(sql.SQL('INSERT INTO cp_pcp_local_source_receipts ({}) VALUES ({})').format(
            sql.SQL(',').join(map(sql.Identifier, receipt)),
            sql.SQL(',').join(sql.Placeholder() for _ in receipt)),
            [Jsonb(val) if isinstance(val,list) else val for val in receipt.values()])
    db.acquire_project_lease('pcp-local', v.store.row['id'])


def ownership(db):
    with db.connect() as conn:
        return (conn.execute('SELECT * FROM cp_pcp_local_source_receipts').fetchall(),
                conn.execute('SELECT * FROM cp_project_leases').fetchall())


@pytest.mark.parametrize('change', ['none', 'usage', 'lease', 'receipt'])
def test_real_schema_cas_recovery_and_ownership(database, verified, change):
    db, v = database, verified
    seed(db, v)
    before = ownership(db)
    initialize_schema(db)
    assert ownership(db) == before and schema_readiness(db) == []
    expected = db.get(v.store.row['id'])
    if change != 'none':
        with db.connect() as conn:
            if change == 'usage':
                conn.execute("UPDATE cp_jobs SET progress=jsonb_set(progress,'{model_calls}','2')")
            elif change == 'lease':
                conn.execute('UPDATE cp_project_leases SET generation=generation+1')
            else:
                conn.execute('UPDATE cp_pcp_local_source_receipts SET generation=generation+1')
        preserved = ownership(db), db.get(expected['id'])
        with pytest.raises(TaskStop):
            asyncio.run(recover_verified_job(SimpleNamespace(storage=db),v.reader,v.task,expected))
        assert (ownership(db),db.get(expected['id'])) == preserved
        assert v.git('rev-parse','HEAD') == v.task.base_sha
    else:
        result = asyncio.run(recover_verified_job(SimpleNamespace(storage=db),v.reader,v.task,expected))
        assert result['status']=='delivering' and result['checkpoint']['pcp_local_execution']['state']=='verified'
        assert result['progress']==expected['progress'] and ownership(db)==before
        for stale in (expected, result):
            with pytest.raises(TaskStop):
                asyncio.run(recover_verified_job(SimpleNamespace(storage=db),v.reader,v.task,stale))
        assert ownership(db)==before


@pytest.mark.parametrize('raw,output,cost', [(None,None,None),({'output_tokens':0,'cost_usd':0},0,0),({'output_tokens':9},9,None)])
def test_real_recording_database_dashboard(database, verified, raw, output, cost):
    db,v=database,verified
    seed(db,v)
    progress={'model_calls':1,'input_tokens':0,'output_tokens':0}
    RuntimeEngineCore._record_usage(progress,'codex_gpt6_luna',raw)
    RuntimeEngineCore._record_agent_attempt(progress,{'id':'codex_gpt6_luna'},
        AgentRun(adapter='codex_cli',model='gpt-6-luna',returncode=0,output='',usage=raw))
    db.update(v.store.row['id'], progress=progress)
    before=ownership(db),db.get(v.store.row['id'])
    snapshot=build_local_snapshot(db)
    assert snapshot['observation']=='available'
    usage=snapshot['jobs'][0]['usage']
    assert usage['output_tokens']==output and usage['cost_usd']==cost
    assert (ownership(db),db.get(v.store.row['id']))==before


def test_missing_sequence_and_insufficient_rights_are_readiness_blockers(database):
    db=database
    initialize_schema(db)
    with db.connect() as conn:
        conn.execute('REVOKE INSERT ON cp_jobs FROM CURRENT_USER')
    assert any(b['object']=='cp_jobs' and b['code']=='role_permissions' for b in schema_readiness(db))
    with db.connect() as conn:
        conn.execute('GRANT INSERT ON cp_jobs TO CURRENT_USER')
        conn.execute('DROP SEQUENCE cp_attention_events_id_seq CASCADE')
    blockers=schema_readiness(db)
    assert any(b['object']=='cp_attention_events_id_seq' and b['code']=='sequence_permissions' for b in blockers)
