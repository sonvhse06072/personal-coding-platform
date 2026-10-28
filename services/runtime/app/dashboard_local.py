"""PCP-scoped SELECT projection. No orchestrator, initialization or actions."""
from __future__ import annotations
from datetime import datetime, timezone
import os
import re
from pathlib import Path
from .developer_stream import safe_activity_text
from .activity import public_event
from .pcp_local_task_queue import PROJECT_ID, REPOSITORY


def iso(v):
    return v.isoformat() if hasattr(v, 'isoformat') else v


def age(v, clock):
    try:
        value = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return max(0, (clock - value).total_seconds())
    except (TypeError, ValueError):
        return None


def safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_:,-]{0,200}', value) else 'unclassified_failure'


def job_projection(row, receipt, lease, events, clock):
    cp, progress, result = (row.get(k) or {} for k in ('checkpoint', 'progress', 'result'))
    execution = cp.get('pcp_local_execution') or {}
    binding = (cp.get('pcp_local_source') or {}).get('receipt') or {}
    verification = execution.get('verification') or result.get('verification') or {}
    delivery = result.get('delivery') or {}
    status = row['status']
    error = safe_code(row['error']) if row.get('error') else None
    last_age = age(row.get('updated_at'), clock)
    paused = status in {'blocked', 'failed', 'interrupted', 'waiting_human'} or bool(error)
    actor = 'PM' if error == 'awaiting_independent_pm_review' else 'operator' if paused else 'Runtime'
    next_action = ('Review exact-head CI and independent evidence' if actor == 'PM' else
        'Reconcile the preserved same-job evidence; do not replay uncertain development' if actor == 'operator' else
        'Observe the next durable transition')
    commit = result.get('commit')
    if not isinstance(commit, str) or not re.fullmatch('[a-f0-9]{40}', commit):
        commit = None
    pr = delivery.get('pull_request') or {}
    number = pr.get('number')
    choice = execution.get('model_choice') or {}
    runs = (delivery.get('ci') or {}).get('actions_runs') or []
    ci_runs = [dict(state=r.get('status'), conclusion=r.get('conclusion'), head=r.get('head_sha'),
        url=f'https://github.com/{REPOSITORY}/actions/runs/{r["run_id"]}') for r in runs
        if type(r.get('run_id')) is int and r.get('head_sha') == commit]

    attempts = progress.get('agent_attempts') or []
    usage = attempts[-1].get('usage', {}) if attempts else {}
    timeline = []
    for raw in events:
        event = public_event(raw)
        if event:
            event['message'] = safe_activity_text(event['message'], workspace=Path(row.get('workspace') or '/unavailable'))
            event['data'] = {}  # No raw command output, paths or credential-bearing data.
            timeline.append(event)
    return dict(id=row['id'], issue=binding.get('issue_number'),
        issue_url=f'https://github.com/{REPOSITORY}/issues/{binding["issue_number"]}' if type(binding.get('issue_number')) is int else None,
        status=status, stage=execution.get('state') or status,
        activity='blocked' if paused else 'stale' if last_age is not None and last_age > 120 else 'active' if status in {'executing','verifying','delivering'} else status,
        admitted_at=iso(row.get('created_at')), started_at=execution.get('started_at'), last_activity_at=iso(row.get('updated_at')),
        elapsed_seconds=age(execution.get('started_at'), clock), activity_age_seconds=last_age,
        observed_execution_seconds=progress['elapsed_minutes']*60 if type(progress.get('elapsed_minutes')) in (int,float) else None,
        source=row.get('source_commit'), branch=row.get('branch'),
        model={k:choice.get(k) for k in ('id','model','reasoning_effort','adapter')},
        blocker=error, responsible_actor=actor, next_action=next_action,
        last_attempt_usage={k:usage.get(k) for k in ('gross_input_tokens','cached_input_tokens','input_tokens','output_tokens','reported_cost_usd')},
        usage={**{k:progress.get(k) for k in ('model_calls','test_runs')},
               **{k:progress.get(k) if any(k in (a.get('usage') or {}) for a in attempts) else None for k in ('input_tokens','output_tokens')},
               'tool_calls':usage.get('tool_calls'),
               'cost_usd':progress.get('cost_usd') if any((a.get('usage') or {}).get('reported_cost_usd') is not None for a in attempts) else None,
               'returned_invocations':sum(a.get('returncode') is not None for a in attempts) if attempts else None},
        local_verification={k:verification.get(k) for k in ('passed','test_runs','passed_tests','failed_tests','skipped_tests')},
        phases=[dict(phase=p.get('phase'), passed=p.get('passed'), commands_executed=len(p.get('commands') or [])) for p in verification.get('phases',[])],
        hosted_ci={'state':delivery.get('state'), 'head':commit, 'observed':delivery.get('ci') is not None, 'runs':ci_runs},
        commit=commit, commit_url=f'https://github.com/{REPOSITORY}/commit/{commit}' if commit else None,
        pr_url=f'https://github.com/{REPOSITORY}/pull/{number}' if type(number) is int else None,
        receipt={k:receipt.get(k) for k in ('state','generation','job_id')} if receipt else None,
        lease={k:lease.get(k) for k in ('state','generation','owner_job_id')} if lease else None,
        assisted_recovery=bool(cp.get('pcp_local_assisted_recovery')),
        timeline=timeline,
        milestones=dict(admission=bool(binding), execution=progress.get('model_calls'),
            verification=verification.get('passed'), delivery=delivery.get('state'),
            hosted_ci=delivery.get('ci',{}).get('state'), pm_outcome=cp.get('pcp_local_pm_review',{}).get('verdict')))


def build_local_snapshot(storage, *, clock=None):
    clock = clock or datetime.now(timezone.utc)
    view = dict(mode='pcp_local', generated_at=clock.isoformat(), instance=os.getenv('PCP_LOCAL_INSTANCE'),
                source=os.getenv('PCP_LOCAL_SOURCE_COMMIT'), observation='available',
                services='not_checked', developer_activity='unknown', quota=None,
                readiness={'state':'not_observed', 'next_action':'Use authenticated read-only readiness before admission'}, jobs=[])
    try:
        with storage.connect() as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            rows = conn.execute("SELECT * FROM cp_jobs WHERE project_id=%s AND checkpoint ? 'pcp_local_source' ORDER BY created_at DESC LIMIT 30", (PROJECT_ID,)).fetchall()
            receipts = conn.execute('SELECT * FROM cp_pcp_local_source_receipts WHERE project_id=%s AND repository=%s', (PROJECT_ID,REPOSITORY)).fetchall()
            lease = conn.execute('SELECT * FROM cp_project_leases WHERE project_id=%s', (PROJECT_ID,)).fetchone()
            if conn.execute("SELECT to_regclass('cp_quota_snapshots') AS present").fetchone()['present']:
                quota = conn.execute('SELECT provider,quota_id,used_percent,remaining_percent,observed_at,expires_at,available '
                    'FROM cp_quota_snapshots ORDER BY observed_at DESC LIMIT 20').fetchall()
                view['quota'] = [{**{k:iso(v) for k,v in q.items()},
                    'fresh':age(q.get('expires_at'),clock)==0} for q in quota]

            if conn.execute("SELECT to_regclass('cp_quota_collectors') AS present").fetchone()['present']:
                collectors = conn.execute("SELECT source,status,last_attempt_at,last_success_at,"
                    "coalesce(lower(error) LIKE '%%authentication required%%', false) AS waiting_auth "
                    "FROM cp_quota_collectors").fetchall()
                view['readiness'] = {'state':'waiting_auth' if any(c['waiting_auth'] for c in collectors) else 'not_observed',
                    'collector_observations':[{k:iso(v) for k,v in c.items()} for c in collectors]}
            for row in rows:
                if row.get('project_id') != PROJECT_ID:
                    continue
                events = conn.execute('SELECT * FROM cp_job_events WHERE job_id=%s ORDER BY id DESC LIMIT 100', (row['id'],)).fetchall()
                receipt = next((r for r in receipts if r['job_id']==row['id']),None)
                owned_lease = lease if lease and lease['owner_job_id']==row['id'] else None
                view['jobs'].append(job_projection(row,receipt,owned_lease,events,clock))
        view['developer_activity'] = 'observed_job_activity' if any(j['activity']=='active' for j in view['jobs']) else 'none_observed'
        view['state'] = 'jobs' if view['jobs'] else 'waiting_auth' if view['readiness']['state']=='waiting_auth' else 'empty'
    except Exception:
        # Never return partial/mixed observations or raw SQL/credential errors.
        view.update(observation='unavailable', state='unavailable', jobs=[], developer_activity='unknown')
    return view
