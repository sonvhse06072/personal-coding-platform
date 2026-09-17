# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-17

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/constitution.md`, `docs/project/operating-model.md`, and `docs/project/efficiency-model.md`.
3. Read this continuity document.
4. Inspect issue #224, active branch/PR, exact diff, and CI before editing or merging.

## Platform baseline

- Efficiency initiative #146 source phases A-F are implemented; calibration and evidence-driven follow-ups remain.
- PM-controlled routine merge #98 is implemented and operationally proven. Developer agents never merge; production remains Human Owner-controlled.
- Low-touch validation #162 completed with zero avoidable Human Owner intervention.
- The Human Owner approved a mandatory **healthy-progress non-blocking** invariant on 2026-09-17: static model/token/tool/test/time/repair/iteration/profile counters are not sufficient Human Owner stop reasons while a WorkOrder is demonstrably progressing inside the approved resource envelope.
- PR #225 merged that invariant into the high-authority source of truth at `101062e9db554a7c610de634d8e7b3c4e72cbf48` after CI #394 passed.
- Hard stops remain required for independent abnormal/material conditions such as repeated failure/no progress, solution/diff oscillation, unexpected scope growth, authoritative provider exhaustion without fallback, protected decisions, runaway/material resource growth, or a justified emergency hard ceiling.
- Last verified deployed labels remain Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`, routing policy v12. Source changes for #224 are not locally activated yet.

## Active executable alignment: #224

Issue #224, **Make healthy-progress budget continuation autonomous**, is the active implementation follow-up.

Active branch: `ai/224-healthy-progress-autonomy`.

Current source direction on the branch:

- routing policy advances from v12 to v13;
- profile/default values remain planning priors and working-threshold inputs rather than owner-click stop points;
- adaptive execution now includes `max_input_tokens` and `max_output_tokens` alongside model/tool/iteration/repair/test/wall dimensions;
- adaptive routes use the configured `hard_max` as the actual technical emergency circuit breaker rather than synthesizing another comparatively low per-task ceiling from an emergency multiplier;
- current proposed material token circuit breakers are 8,000,000 input tokens and 1,000,000 output tokens per job;
- estimates and working targets remain observable telemetry/reassessment thresholds inside those caps;
- legacy/pre-adaptive blocked jobs may adopt a fresh adaptive route only after a fresh Router reassessment returns `continue`, no anomaly/protected signal exists, and every durable counter remains below the fresh emergency ceiling;
- historical `hard_budget_overrun` for input/output tokens is only a candidate for safe re-evaluation, never an unconditional resume signal;
- consumed counters, immutable WorkOrder, source, workspace, branch, diff, and job identity are never reset/replaced to create headroom;
- #221 Human Owner token extension remains compatibility recovery for genuinely exceptional/legacy states, not the steady-state path for otherwise healthy work.

Regression coverage added on the branch proves:

1. crossing a profile token prior does not itself stop an adaptive job;
2. the preserved DEC-025C usage `2,274,574 / 2,000,000` is below the fresh material input-token circuit breaker and therefore is not, by itself, a Human Owner decision;
3. reaching the material token hard cap still fails closed;
4. repeated-failure evidence still circuit-breaks below the material token cap;
5. a DEC-like pre-adaptive blocked job can auto-adopt a healthy fresh route on the same job/workspace/source/branch with `input_tokens=2,274,574` preserved and a durable `legacy_adaptive_adoptions` audit record;
6. fresh anomaly evidence or fresh material-cap exhaustion keeps that same job blocked.

No local Runtime/Router restart or rollout has occurred for #224.

## Preserved `chonhac` DEC-025C

- plan: `pm-gh-5650852312`;
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`;
- job: `eec59b13651c54559c10ce204380a68e`;
- branch: `ai/eec59b13651c`;
- workspace: `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`;
- approved source baseline: `b143fbb001c2006ec82570619802b607085fbeb0`;
- last verified status: `blocked`;
- top-level result: `reassessment_stopped`;
- nested reassessment: `action=stop`, `reason=input-token budget exceeded`, signal `hard_budget_overrun`;
- cache-aware durable `progress.input_tokens = 2,274,574`;
- currently deployed effective `max_input_tokens = 2,000,000`.

This is legitimate cache-aware usage, not the historical cache-accounting bug.

Keep this exact job blocked/preserved while #224 source is reviewed and merged. Do not execute historical/new #221 token actions, manually resume, edit DB/counters, force-complete, or create a replacement plan/job merely to bypass the state.

After #224 is merged and a guarded local rollout is prepared, the preferred recovery is automatic fresh-route adoption **only if** the then-current durable evidence still proves healthy progress and no independent anomaly/protected/material-risk condition exists. Otherwise the job remains blocked fail-closed.

## Relevant completed follow-ups

- #215 / PR #216: bounded legacy adaptive adoption, merged at `6bc1f1a13c02acc6d747329c332a777535b75733`.
- #219 / PR #220: effective adaptive-envelope reconciliation, merged at `d078f5e3ce8e47555b12e459cdce4fa43114cae0`.
- #221 / PR #222: bounded Human Owner input-token recovery compatibility path, merged at `2f4babbe33dfcf96fe6d6ef500243d2a0baec020`; PM review added a fresh `status=blocked` mutation gate.
- PR #223: continuity after #221, merged at `a0b28223f10686a5fa993397e0e1084e2f4dcb3c`.
- PR #225: mandatory healthy-progress non-blocking policy amendment, merged at `101062e9db554a7c610de634d8e7b3c4e72cbf48`.

## Global operational gates

- Normal engineering flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> PM review -> eligible PM merge.
- Never force push.
- Developer agents never merge.
- Human Owner retains protected scope/architecture/security/destructive-data/production/governance/material-budget authority.
- Healthy-progress non-blocking is mandatory; a static task/profile counter crossing alone is not a valid Human Owner gate.
- Production deployment is never implied by PR merge.
- Do not restart/rebuild platform services while engineering work is active.
- Runtime durable state is authoritative; never edit durable state to bypass its state machine.
- Potentially failing Human Owner command blocks must run in an isolated subshell/process, not terminate the parent interactive shell.

## Immediate next safe actions

1. Review the exact #224 branch diff and run normal structure/Router/Runtime/ddev-executor CI on the exact PR head.
2. Fix only evidence-backed regressions; do not weaken anomaly/provider/protected/material-risk circuit breakers to make tests pass.
3. PM may merge #224 only from a green, current exact head with no unresolved protected decision.
4. Keep DEC-025C blocked until #224 is merged and local activation passes an idle/platform/source gate.
5. During guarded activation, verify the same DEC job/workspace/source/branch/counters before and after loading the new Runtime/Router policy.
6. Allow the orchestrator to re-evaluate the preserved budget-only block. It may auto-resume the same job only if fresh adaptive routing + fresh reassessment prove the state healthy and under material emergency caps.
7. If fresh evidence identifies a real anomaly/protected/material-risk condition, keep the job blocked and surface that actual reason instead of manufacturing a continuation click.
8. Keep #146 open for naturally occurring calibration evidence.
