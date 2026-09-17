# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-17

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/constitution.md`, `docs/project/operating-model.md`, and `docs/project/efficiency-model.md`.
3. Read this continuity document.
4. Inspect the current GitHub `main`, local source/deployment state, and preserved DEC-025C durable state before any rollout or resume action.

## Platform baseline

- Efficiency initiative #146 source phases A-F are implemented; calibration and evidence-driven follow-ups remain.
- PM-controlled routine merge #98 is implemented and operationally proven. Developer agents never merge; production remains Human Owner-controlled.
- Low-touch validation #162 completed with zero avoidable Human Owner intervention.
- The Human Owner approved the mandatory **healthy-progress non-blocking** invariant on 2026-09-17: static model/token/tool/test/time/repair/iteration/profile counters are not sufficient Human Owner stop reasons while a WorkOrder is demonstrably progressing inside the approved resource envelope.
- PR #225 merged that invariant into the high-authority source of truth at `101062e9db554a7c610de634d8e7b3c4e72cbf48` after CI #394 passed.
- Hard stops remain required for independent abnormal/material conditions such as repeated failure/no progress, solution/diff oscillation, unexpected scope growth, authoritative provider exhaustion without fallback, protected decisions, runaway/material resource growth, or a justified emergency hard ceiling.
- Last verified deployed labels remain Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`, routing policy v12. The merged #224 source is not locally activated yet.

## Healthy-progress executable alignment #224: merged

Issue #224, **Make healthy-progress budget continuation autonomous**, is closed `completed`.

PR #226, **runtime: keep healthy budget progress autonomous**, was PM-reviewed and merged from exact final head `7302c3d2e3faf02d35775f30a205383e7f253468` into `main` at merge commit `892fd2ba30f0ba0426c6239384ead43d1b2c3d95`.

Final CI run #401 passed across all required jobs: structure, Router, Runtime, and ddev-executor.

Merged behavior:

- routing policy advances from v12 to v13;
- profile/default values are planning priors and working-threshold inputs rather than owner-click stop points;
- adaptive execution includes `max_input_tokens` and `max_output_tokens` alongside model/tool/iteration/repair/test/wall dimensions;
- adaptive routes use configured `hard_max` values as the technical abnormal/material-risk circuit breakers rather than synthesizing a lower per-task emergency ceiling;
- material token circuit breakers are 8,000,000 input tokens and 1,000,000 output tokens per job;
- estimates and working targets remain observable telemetry/reassessment thresholds inside those caps;
- legacy/pre-adaptive blocked jobs may adopt a fresh adaptive route only after a fresh Router reassessment returns `continue`, no anomaly/protected signal exists, and every durable counter remains below the fresh emergency ceiling;
- historical budget guard/overrun evidence is only a candidate for safe re-evaluation, never an unconditional resume signal;
- consumed counters, immutable WorkOrder, source, workspace, branch, diff, and job identity are never reset/replaced to create headroom;
- #221 Human Owner token extension remains compatibility recovery for genuinely exceptional/legacy states, not the healthy steady-state continuation path.

Final PM review also corrected two issues before merge:

1. stale tests that still expected routing policy v12 were aligned to v13;
2. Router now fails closed if a profile/default prior exceeds a configured adaptive `hard_max`, so a contradictory policy cannot silently widen a material circuit breaker.

Regression coverage proves profile token priors are non-blocking for healthy adaptive work, DEC-025C usage `2,274,574 / 2,000,000` is below the fresh material input-token circuit breaker, hard caps still stop fail-closed, repeated-failure evidence still circuit-breaks early, and a healthy DEC-like legacy block can adopt a fresh route without changing durable identity/counters.

No local Runtime/Router restart or rollout has occurred for #224/#226 yet.

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

Keep this exact job blocked/preserved until guarded local activation loads the merged Runtime/Router source. Do not execute historical/new #221 token actions, manually resume, edit DB/counters, force-complete, or create a replacement plan/job merely to bypass the state.

After guarded activation, the preferred recovery is automatic fresh-route adoption **only if** current durable evidence still proves healthy progress and no independent anomaly/protected/material-risk condition exists. Otherwise the job remains blocked fail-closed.

## Relevant completed follow-ups

- #215 / PR #216: bounded legacy adaptive adoption, merged at `6bc1f1a13c02acc6d747329c332a777535b75733`.
- #219 / PR #220: effective adaptive-envelope reconciliation, merged at `d078f5e3ce8e47555b12e459cdce4fa43114cae0`.
- #221 / PR #222: bounded Human Owner input-token recovery compatibility path, merged at `2f4babbe33dfcf96fe6d6ef500243d2a0baec020`; PM review added a fresh `status=blocked` mutation gate.
- PR #223: continuity after #221, merged at `a0b28223f10686a5fa993397e0e1084e2f4dcb3c`.
- PR #225: mandatory healthy-progress non-blocking policy amendment, merged at `101062e9db554a7c610de634d8e7b3c4e72cbf48`.
- #224 / PR #226: executable healthy-progress autonomy, merged at `892fd2ba30f0ba0426c6239384ead43d1b2c3d95` after CI #401 passed.

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

1. Fast-forward the local PCP checkout to current GitHub `main` containing `892fd2ba30f0ba0426c6239384ead43d1b2c3d95` (plus this continuity-only follow-up once merged).
2. Before any restart, verify the PCP working tree/source, no active engineering work, and the exact preserved DEC-025C job/workspace/source/branch/status/counters.
3. Run the required deterministic platform/source tests while services remain in the current safe state.
4. Only after those preflight gates pass, perform the minimum one-time Runtime/Router restart/rebuild required to load routing policy v13 and merged #224 behavior.
5. Verify startup/rollout itself did not mutate or resume DEC-025C and that its durable identity/counters remain unchanged.
6. Allow normal orchestration to re-evaluate the preserved budget-only block. It may auto-resume the same job only if fresh adaptive routing + fresh reassessment prove the state healthy and under material emergency caps.
7. If fresh evidence identifies a real anomaly/protected/material-risk condition, keep the job blocked and surface that actual reason instead of manufacturing a continuation click.
8. Keep #146 open for naturally occurring calibration evidence.
