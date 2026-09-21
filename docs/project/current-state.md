# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-21

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/constitution.md`, `docs/project/operating-model.md`, `docs/project/efficiency-model.md`, and `docs/project/provider-policy.md`.
3. Read this continuity document.
4. Inspect current GitHub `main`, active issue/PR, local service versions, and the exact durable DEC-025C-r2 state before any rollout or resume action.

## Platform baseline

- Efficiency initiative #146 source phases A-F are implemented; calibration and evidence-driven follow-ups remain.
- PM-controlled routine merge #98 is implemented and operationally proven. Developer agents never merge; production remains Human Owner-controlled.
- Low-touch validation #162 completed with zero avoidable Human Owner intervention.
- Healthy-progress non-blocking is mandatory: static task/profile counters are not sufficient Human Owner stop reasons while work is making meaningful progress inside the approved resource envelope.
- Hard stops remain required for independent abnormal/material conditions such as repeated failure/no progress, solution/diff oscillation, unexpected scope growth, authoritative provider exhaustion **without eligible fallback**, protected decisions, runaway/material resource growth, or a justified emergency hard ceiling.
- Routine provider recovery is Runtime/Router responsibility. Human Owner attention is a scarce resource and should not be used merely because one provider/model/quota bucket failed while another eligible route remains.

## Local activation evidence through 2026-09-18

The Human Owner completed guarded local activation/diagnostics after #224:

- local PCP checkout was exact `2bef1bcbbfa3cfc52e21e06f5314ccb676551853`;
- Router `1.0.21` was rebuilt from reviewed source and serves routing policy v13;
- rebuilt Router tests passed `81 passed` and host/container `engine_adaptive.py` hashes matched;
- Runtime still reports `1.0.44`, but read-only diagnostics confirmed its #224 files match the reviewed host source;
- direct n8n `/healthz` returned HTTP 200 and PCP workflows were active; the aggregate `platform-status` n8n line has shown a false-negative/transient mismatch and should not override the direct probe without further evidence.

No further Router/Runtime rebuild should occur while engineering work is active.

## Healthy-progress executable alignment #224: live proof obtained

Issue #224 / PR #226 is merged; final source CI #401 passed.

The preserved DEC-025C-r2 job subsequently proved the merged behavior in durable state:

- same job/workspace/source/branch identity was preserved;
- legacy adaptive adoption audit exists;
- fresh adaptive route uses `max_input_tokens = 8,000,000`;
- `adaptive_budget.enabled = true`;
- fresh reassessment returned `continue`;
- consumed counters were not reset;
- the job resumed and continued beyond the historical 2,000,000-token route prior.

This closes the earlier question of whether #224 works in the live preserved job: it does.

## Autonomous provider recovery #228: merged and activated

Issue #228, **Keep provider recovery autonomous until eligible capacity is exhausted**, is closed `completed`.

PR #229, **runtime: keep provider recovery autonomous**, was PM-reviewed and merged from exact final head `ebabb195f2fef171e0ce9d90519c7870cb544c6b` into `main` at merge commit `bd24f18a0983ed370681f253edeb0606cf9e80cf`.

Exact-head CI run #408 passed all required jobs: structure, Router, Runtime, and ddev-executor. The earlier run #407 exposed only an incomplete new test harness; the harness was corrected without changing production semantics before the green final run.

Merged behavior:

- `max_provider_failovers` is planning/telemetry evidence, not a Human Owner continuation gate;
- every observed provider/model/quota failure is persisted before Router selects another distinct eligible candidate;
- planner, executor and evaluator share the same autonomous provider recovery semantics;
- quota, rate-limit, authentication, configuration and provider-unavailable failures may fall through automatically while eligible capacity remains;
- failed provider/model/quota health remains durable, so automatic recovery cannot cycle back to already-proven-bad capacity merely to stay under a counter;
- Router reassessment no longer treats `provider_failovers > max_provider_failovers` as an unconditional hard-budget overrun;
- no eligible route, contradictory same-choice routing, protected decisions, scope anomalies, repeated/no-progress/oscillation guards and material resource boundaries remain fail-closed;
- merged service labels are Runtime `1.0.45` and Router `1.0.22`; routing policy remains v13.

Local activation of #228/#229 is complete. The guarded activation re-entry passed with exit code 0 on source `141d630f2523a968352ee86e80d2002d5f3fe6b3`: Router `1.0.22`, Runtime `1.0.45`, routing policy v13, deterministic platform tests green, and the preserved DEC-025C-r2 remained blocked and was not resumed during rollout. The workspace was exactly 14/14 semantic files and no job/counter/provider-state reset or replacement occurred.

The next operation is no longer a rollout. Recover the exact same DEC-025C-r2 job once through a fresh explicit reroute with `reset_transient_provider_failures=false`; then let Runtime/Router autonomously traverse eligible provider capacity. Do not use historical Telegram reroute buttons merely to advance provider selection.

## Preserved `chonhac` DEC-025C-r2

Identity remains:

- plan: `pm-gh-5650852312`;
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`;
- job: `eec59b13651c54559c10ce204380a68e`;
- branch: `ai/eec59b13651c`;
- workspace: `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`;
- approved source baseline: `b143fbb001c2006ec82570619802b607085fbeb0`.

Provider recovery #228 was activated and the same preserved job was explicitly rerouted once without resetting counters/provider state. The job resumed successfully, advanced through additional execution/verification work, and later blocked again.

Latest durable state:

- status: `blocked`;
- result reason: `reassessment_stopped`;
- reassessment reason: `model-call budget exhausted`;
- model calls: `40/40`;
- iterations: `24/24`;
- repair iterations: `12/12`;
- tool calls: `106/400`;
- tests: `34/40`, with `tests_passed=true`;
- input tokens: `3,931,952/8,000,000`;
- output tokens: `236,484/1,000,000`;
- changed files: `16/14`;
- `unexpected_scope=true`;
- executor remains `codex_terra / openai`;
- evaluator route remains `openrouter_qwen3_coder_free / openrouter`.

The same-job recovery preserved job/workspace/source/branch/counters and proved that provider failover is no longer the immediate Human Owner gate. The current stop is instead the configured emergency execution ceiling plus an apparent scope signal.

The scope signal was confirmed as a Runtime accounting defect rather than semantic WorkOrder expansion: the workspace was verified at exactly 14/14 semantic files immediately before recovery, and agent/test traces repeatedly generated `infra/staging/dec025c/__pycache__/*.pyc`. Issue #238 / PR #239 fixed Runtime so untracked Python bytecode cannot be intent-added, counted, diffed or committed while intentionally tracked bytecode remains visible; PR #239 merged at `b21868ec157aa5a7d3d550813de8b7c51c1cdb88` after exact-head CI #418 passed.

The remaining block exposed a second executable mismatch. Model calls `40/40`, iterations `24/24`, and repair iterations `12/12` are static work-shape counters. The Human Owner reaffirmed that healthy-progress work must not stop solely at those counters.

Issue #240 / PR #241 is now merged. Exact-head CI #422 passed structure, Router, Runtime and ddev-executor at `c92f75a9b6738c8bd572d4103d71e84989846e57`; PM merged PR #241 at `757a35f8823c9c3c30c1dfc95084dce369ef2308`. At that rollout stage, effective adaptive WorkOrders treated model/tool/test/iteration/repair/model-failover/provider-failover thresholds as telemetry/reassessment inputs while token volume, wall time, hard cost, changed-file scope, anomaly, protected-decision and authoritative provider-exhaustion boundaries remained fail-closed. Router was labeled `1.0.23`, Runtime `1.0.46`, routing policy v14.

Local activation is complete. The guarded activation/re-entry passed on exact main `6c26bb3a4eb0bc6547f17e9dd7baa681dd61af97`: Router `1.0.23`, Runtime `1.0.46`, routing policy v14, direct n8n health green, zero active work before both selective rebuilds, Runtime deterministic suite `349 passed`, and startup did not mutate the preserved DEC job.

Runtime #238 recomputed the workspace as exactly 14 semantic files, proving the prior `16/14` / `unexpected_scope=true` state was generated-bytecode residue. Before re-entry the material gate still had headroom: input `3,931,952/8,000,000`, output `236,484/1,000,000`, wall `158.232/180`, cost `0/5`, and zero important decisions.

The exact same DEC job was then explicitly rerouted once with transient provider failures preserved. Identity and counters were unchanged across re-entry. Immediate live state was `verifying`, plan `executing`, WorkOrder `running`, effective `budget_mode=adaptive`, with work-shape counters still at model calls `40`, iterations `24`, repairs `12`, tests `34`, and tools `106`. This is the first live proof that the v14 route accepts a same-job re-entry at previously blocking work-shape thresholds.

The v14 live run then provided stronger calibration evidence. Without any counter reset or replacement job, DEC-025C-r2 advanced from model calls `40` / iterations `24` / repairs `12` to model calls `59` / iterations `34` / repairs `21`, with tools `127`, tests `52`, semantic changed files `14`, `unexpected_scope=false`, input tokens `4,578,495/8,000,000`, and the same adaptive route. This proves #240 removed the former work-shape gates in live execution.

The next block occurred at total elapsed wall time `180.084/180` with result reason `execution_budget_exhausted`; plan and WorkOrder both became blocked. No concurrent scope, token, cost, protected-decision, provider-capacity, repeated-failure, no-progress, or oscillation reason was reported. This is a fixed wall-time continuation gate of the exact kind the approved efficiency policy classifies as avoidable Human Owner attention.

Issue #244 / PR #245 is now merged. Exact-head CI #428 passed structure, Router, Runtime and ddev-executor at `b58e590adf3c722249395babd219e804d4f4768b`; PM merged PR #245 at `5d7a812a6945c94fe85d27e7aa16e882ca2e85b0`. At that rollout stage, effective adaptive WorkOrders treated total elapsed wall time as telemetry/calibration rather than a standalone stop gate. Planner/executor/evaluator/verification operations remained bounded by their per-operation timeout caps; adaptive GitHub delivery kept its own bounded attempt cap; input/output token ceilings, hard cost, scope, behavioral circuit breakers, protected decisions, and provider exhaustion remained fail-closed. Legacy-hard WorkOrders kept strict total wall-time behavior. Router was labeled `1.0.24`, Runtime `1.0.47`, routing policy v15.

Local activation of #244 completed during the guarded provider diagnostic: Router `1.0.24`, Runtime `1.0.47`, routing policy v15, deterministic suites green, and the preserved job was not resumed by activation. The same job had already advanced under v15 semantics to model calls `94`, iterations `51`, repairs `37`, tools `162`, tests `84`, input `5,814,761/8,000,000`, output `363,928/1,000,000`, elapsed `218.588`, semantic files `14`, and `unexpected_scope=false`.

The current blocker is now a genuine provider-capacity state: `codex_terra / openai` returned `quota_exhausted`, Runtime recorded `provider_failure_without_fallback`, and a fresh RouterClient diagnostic using durable provider state plus live quota telemetry returned `NO_ELIGIBLE_ROUTE`. No job/counter/provider-state reset occurred.

Source review then exposed a recovery-liveness defect: pre-fix Codex quota failures can be stored provider-wide, and live authoritative quota telemetry was merged with durable failed-state using fail-closed AND semantics, so a quota bucket could remain durably unavailable even after an authoritative post-reset observation proved capacity returned.

Issue #247 / PR #248 is now merged. Exact-head CI #432 passed structure, Router, Runtime and ddev-executor at `b3a2c9aec07fe5326b50d2c59969a549face6e22`; PM merged PR #248 at `edb30cbcc9b3ce67bf971289a3bb1c193686b7e8`. Runtime now narrows quota/rate-limit failures to registered quota scope, timestamps durable quota failures, accepts rehabilitation only from a newer authoritative available observation for the exact quota key, and uses the existing orchestrator polling loop to reopen the exact same blocked job only when a fresh Router route also succeeds. Stale observations, reset time alone, auth/config/provider-wide failures, and fresh-route failures remain fail-closed without durable mutation.

Merged service target is Runtime `1.0.48`; Router remains `1.0.24`; routing policy remains v15.

Local activation is complete on exact main `85b2b79a89279063f7178da3ff68b87752701f91`. Guarded rollout preserved the exact DEC-025C-r2 identity, workspace, source, branch and counters. Runtime `1.0.48`, Router `1.0.24`, policy v15 and direct n8n health all passed.

The live provider-capacity recovery path was then proven end-to-end. Before recovery, `provider_capacity_recoveries=0`. A fresh authoritative Codex quota snapshot reported `quota:codex_chatgpt_plus` available with `used_percent=0` / `remaining_percent=100`; the orchestrator recorded `authoritative_quota_capacity_recovered`, rehabilitated exactly `quota:codex_chatgpt_plus`, obtained a valid fresh route, and automatically reopened the exact same job/WorkOrder/plan without any Human Owner continuation action. The audit record preserved the prior block reason `provider_failure_without_fallback` and the authoritative observation timestamp.

After automatic reopen:
- job status: `verifying`;
- WorkOrder state: `running`;
- plan status: `executing`;
- executor: `codex_terra / openai`;
- evaluator: `codex_sol / openai`;
- model calls `94`, iterations `51`, repairs `37`, tools `162`, tests `84`;
- input `5,814,761`, output `363,928`, elapsed `218.588`;
- semantic changed files `14`;
- `unexpected_scope=false`;
- same-job identity unchanged;
- counters unchanged across reopen and monotonicity passed;
- `provider_capacity_recoveries` increased `0 -> 1`;
- no blanket provider reset occurred.

Durable provider-wide failures for OpenRouter and Google Antigravity remained preserved. The recovered Codex quota key was not blanket-cleared with unrelated failure state; only the authoritative recovered quota scope was rehabilitated.

The stored `result_reason=provider_failure_without_fallback` immediately after reopen is historical terminal-result context from the prior blocked state, not the active state: durable job/orchestration state is authoritative and shows `verifying / running / executing`.

The same preserved job later advanced again without resets to model calls `132`, tools `206`, tests `122`, repairs `55`, elapsed `323.918` minutes and cache-aware input `8,072,466`. It then blocked at reassessment solely because the cumulative input counter crossed the adaptive high-water value `8,000,000`; no independent scope/protected-decision/provider-exhaustion condition was reported with that stop.

## #252 cumulative-token healthy-progress alignment: source change in progress

Live DEC-025C evidence proves that a fixed cumulative token total has the same structural problem previously found in work-shape and total-wall counters: a sufficiently large healthy ticket eventually crosses any absolute per-job total even when it is still making useful progress.

Issue #252 therefore aligns executable behavior with the already-approved Constitution/#224 invariant rather than raising the 8M number again:

- for effective `budget_mode=adaptive`, cumulative input/output token totals remain durable cache-aware telemetry and estimate/working/high-water signals, not standalone continuation gates;
- strict cumulative token ceilings remain for explicit/legacy `legacy_hard` work;
- hard monetary cost, authoritative provider exhaustion without fallback, scope/protected decisions, repeated failure/no-progress/diff oscillation and per-operation/provider context limits remain fail-closed;
- historical #221 input-token owner-extension controls remain legacy compatibility only and are not exposed for adaptive jobs;
- legacy-adaptive recovery may reopen the exact same blocked job only after a fresh route and fresh reassessment independently report healthy continuation;
- no counter reset, job replacement, scope widening or production/trust-boundary change is authorized.

Implementation branch: `ai/252-adaptive-cumulative-token-telemetry`.

Planned rollout identities on that branch are Runtime `1.0.49`, Router `1.0.25`, routing policy v16.

Keep DEC-025C-r2 blocked until #252 exact-head CI is green, the PR is merged, and a guarded local activation starts from zero active engineering work. Do not use the historical Telegram +1M token path to advance this adaptive job.

## Relevant completed follow-ups

- #215 / PR #216: bounded legacy adaptive adoption, merged at `6bc1f1a13c02acc6d747329c332a777535b75733`.
- #219 / PR #220: effective adaptive-envelope reconciliation, merged at `d078f5e3ce8e47555b12e459cdce4fa43114cae0`.
- #221 / PR #222: bounded Human Owner input-token recovery compatibility path, merged at `2f4babbe33dfcf96fe6d6ef500243d2a0baec020`.
- PR #225: mandatory healthy-progress non-blocking policy amendment, merged at `101062e9db554a7c610de634d8e7b3c4e72cbf48`.
- #224 / PR #226: executable healthy-progress autonomy, merged at `892fd2ba30f0ba0426c6239384ead43d1b2c3d95` after CI #401 passed.
- PR #227: continuity after #224 merge, merged at `2bef1bcbbfa3cfc52e21e06f5314ccb676551853`.
- #228 / PR #229: autonomous provider recovery, exact-head CI #408 green, merged at `bd24f18a0983ed370681f253edeb0606cf9e80cf`.
- #238 / PR #239: generated Python bytecode excluded from Runtime diff/commit scope, exact-head CI #418 green, merged at `b21868ec157aa5a7d3d550813de8b7c51c1cdb88`.
- #240 / PR #241: adaptive work-shape counters made non-blocking while material/anomaly boundaries remain strict; exact-head CI #422 green; merged at `757a35f8823c9c3c30c1dfc95084dce369ef2308`.
- #244 / PR #245: adaptive total wall time made telemetry while per-operation timeouts and independent safety gates remain strict; exact-head CI #428 green; merged at `5d7a812a6945c94fe85d27e7aa16e882ca2e85b0`.
- #247 / PR #248: authoritative quota-capacity rehabilitation plus same-job automatic reopen; exact-head CI #432 green; merged at `edb30cbcc9b3ce67bf971289a3bb1c193686b7e8`.

## Global operational gates

- Normal engineering flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> PM review -> eligible PM merge.
- Never force push.
- Developer agents never merge.
- Human Owner retains protected scope/architecture/security/destructive-data/production/governance/material-budget authority.
- Healthy-progress non-blocking is mandatory; static task/profile/provider-failover counters alone are not Human Owner gates.
- Production deployment is never implied by PR merge.
- Do not restart/rebuild platform services while engineering work is active.
- Runtime durable state is authoritative; never edit durable state to bypass its state machine.
- Potentially failing Human Owner command blocks must run in an isolated subshell/process.

## Immediate next safe actions

1. Keep exact job `eec59b13651c54559c10ce204380a68e` blocked while #252 is under review. Do not reset counters/provider state, replace the job, force-complete it, or execute historical Telegram token actions.
2. Complete #252 exact-head CI and PM review. The source change must prove adaptive cumulative-token thresholds are non-blocking while legacy-hard token ceilings, hard cost and independent anomaly/protected/provider gates remain strict.
3. After merge, perform a guarded local activation only from zero active engineering work. Rebuild the affected Router/Runtime services from the merged source and run deterministic platform tests before allowing same-job recovery.
4. On startup/reconciliation, permit automatic same-job legacy-adaptive recovery only if fresh Router route + fresh reassessment return healthy continuation. Preserve input `8,072,466` and every other durable counter monotonically.
5. Preserve unrelated OpenRouter/Google Antigravity provider-wide failure state; do not blanket-clear it during #252 activation.
6. If DEC-025C then reaches delivery/PR, apply normal deterministic CI and PM merge gates. If it blocks again, classify only the new independent blocker rather than another static cumulative counter.
7. Keep #146 open for calibration evidence from this long-running same-job execution.
