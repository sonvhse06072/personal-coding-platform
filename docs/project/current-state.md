# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-19

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

Issue #240 / PR #241 is now merged. Exact-head CI #422 passed structure, Router, Runtime and ddev-executor at `c92f75a9b6738c8bd572d4103d71e84989846e57`; PM merged PR #241 at `757a35f8823c9c3c30c1dfc95084dce369ef2308`. Effective adaptive WorkOrders now treat model/tool/test/iteration/repair/model-failover/provider-failover thresholds as telemetry/reassessment inputs, while token volume, wall time, hard cost, changed-file scope, anomaly, protected-decision and authoritative provider-exhaustion boundaries remain fail-closed. Router is labeled `1.0.23`, Runtime `1.0.46`, routing policy v14.

Local activation is complete. The guarded activation/re-entry passed on exact main `6c26bb3a4eb0bc6547f17e9dd7baa681dd61af97`: Router `1.0.23`, Runtime `1.0.46`, routing policy v14, direct n8n health green, zero active work before both selective rebuilds, Runtime deterministic suite `349 passed`, and startup did not mutate the preserved DEC job.

Runtime #238 recomputed the workspace as exactly 14 semantic files, proving the prior `16/14` / `unexpected_scope=true` state was generated-bytecode residue. Before re-entry the material gate still had headroom: input `3,931,952/8,000,000`, output `236,484/1,000,000`, wall `158.232/180`, cost `0/5`, and zero important decisions.

The exact same DEC job was then explicitly rerouted once with transient provider failures preserved. Identity and counters were unchanged across re-entry. Immediate live state was `verifying`, plan `executing`, WorkOrder `running`, effective `budget_mode=adaptive`, with work-shape counters still at model calls `40`, iterations `24`, repairs `12`, tests `34`, and tools `106`. This is the first live proof that the v14 route accepts a same-job re-entry at previously blocking work-shape thresholds.

Do not reroute again or use historical Telegram actions while this job remains active. Observe the same job until it reaches delivery/PR or an independent material/anomaly/protected/provider-capacity boundary.

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

1. Do not reroute DEC-025C-r2 again while the job is active. Do not reset counters/provider state, replace the job, force-complete, or use historical Telegram actions.
2. Observe the same job `eec59b13651c54559c10ce204380a68e`. Work-shape counters at/above `40/24/12` are expected telemetry on the effective adaptive route and must not be treated as standalone owner gates.
3. On the next verification cycle, confirm durable `changed_files` returns to `14` and `unexpected_scope=false`; Runtime #238 already proved the fresh semantic diff is exactly 14 files.
4. If the job advances to delivery/PR, apply normal deterministic CI and PM merge gates.
5. If the job blocks again, classify the new blocker by independent evidence. Token volume, wall time, hard cost, real scope expansion, repeated/no-progress/oscillation, protected decision, or authoritative provider exhaustion remain legitimate stop classes; static work-shape counters do not.
6. The current wall-time reading before re-entry was `158.232/180`. If the next stop is only wall-time while execution remains demonstrably healthy, treat that as fresh calibration evidence before deciding whether wall-time should remain a fixed material circuit breaker or move to a healthier runaway-risk policy.
7. Keep #146 open for natural calibration evidence from this job.
