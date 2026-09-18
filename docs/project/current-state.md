# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-18

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

## Autonomous provider recovery #228: merged, activation pending

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

Latest owner-visible provider sequence:

1. `antigravity_free` / `google_antigravity` failed with `quota_exhausted` during execution;
2. the Human Owner manually chose **Chuyển provider**;
3. the same job continued;
4. evaluator `openrouter_qwen3_coder_free` / `openrouter` then failed with `authentication`;
5. latest notification again reports `evaluator_provider_failure_without_fallback`.

Latest notification metrics were model calls `30/40`, tool calls `93/400`, test runs `24/40`, wall time `140.757/180`, repair iterations `7/12`.

Those manual reroute clicks are now classified as avoidable Human Owner attention when another valid provider remains; #228 is the executable fix.

Do not reset counters/provider state, create a replacement job, force-complete, or broaden the WorkOrder simply to recover this job.

A separate read-only diagnostic observed `changed_files=16` while the WorkOrder route limit was `14`; agent evidence reported generated `infra/staging/dec025c/__pycache__` residue. This is not permission to raise `max_changed_files`. Before same-job recovery after #228 activation, verify that any overage is exactly generated residue and that the semantic diff remains inside the approved 14-file scope.

## Relevant completed follow-ups

- #215 / PR #216: bounded legacy adaptive adoption, merged at `6bc1f1a13c02acc6d747329c332a777535b75733`.
- #219 / PR #220: effective adaptive-envelope reconciliation, merged at `d078f5e3ce8e47555b12e459cdce4fa43114cae0`.
- #221 / PR #222: bounded Human Owner input-token recovery compatibility path, merged at `2f4babbe33dfcf96fe6d6ef500243d2a0baec020`.
- PR #225: mandatory healthy-progress non-blocking policy amendment, merged at `101062e9db554a7c610de634d8e7b3c4e72cbf48`.
- #224 / PR #226: executable healthy-progress autonomy, merged at `892fd2ba30f0ba0426c6239384ead43d1b2c3d95` after CI #401 passed.
- PR #227: continuity after #224 merge, merged at `2bef1bcbbfa3cfc52e21e06f5314ccb676551853`.
- #228 / PR #229: autonomous provider recovery, exact-head CI #408 green, merged at `bd24f18a0983ed370681f253edeb0606cf9e80cf`.

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

1. Re-check DEC-025C-r2 is still the same blocked job/workspace/source/branch/WorkOrder and that no unrelated engineering work is active.
2. Issue exactly one explicit same-job fresh reroute with `reroute=true` and `reset_transient_provider_failures=false`.
3. Do not reset counters or clear durable provider/quota state. The explicit reroute must preserve the same job/workspace/plan/WorkOrder.
4. After enqueue, observe the same job. Runtime/Router should automatically move through distinct eligible provider/model/quota capacity without Human Owner clicks.
5. If a provider fails, do not press old Telegram provider buttons while the job remains active; allow automatic failover to proceed.
6. Human Owner attention is required only if Router proves no eligible route remains or an independent anomaly/protected/material boundary fires.
7. If the WorkOrder reaches verification/delivery/PR, continue the normal deterministic CI and PM merge gates. Operator WorkOrders remain pending until their own authorized execution.
8. Keep #146 open for naturally occurring calibration evidence.
