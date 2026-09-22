# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-22

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/constitution.md`, `docs/project/operating-model.md`, `docs/project/efficiency-model.md`, and `docs/project/provider-policy.md`.
3. Read this continuity document.
4. Inspect current GitHub `main`, active issue/PR and local service versions. The former `chonhac` DEC-025C orchestration is retired and must not be resumed.

## Chợ Nhạc ProjectBaseline design revision

Human Owner-approved Chợ Nhạc design governance has advanced beyond the old
DEC-025B-era baseline. Issue #258 / PR #259 is merged at
`80ec29bbda4b74a0dcf718c6498bce00228e902b` and updates the active immutable
ProjectBaseline for new `chonhac` work to:

- revision: `mvp-v1-2026-09-22-design`;
- source commit: `afc0901a6c073f763c440df4d492778c12fec11a`;
- scope: same approved MVP/product/security frame, plus the approved DEC-027 /
  DEC-028 and DF-1 through DF-4 design contracts needed for bounded frontend
  execution.

The prior `mvp-v1-2026-09-13` revision remains approved and explicitly
resolvable for audit/history. This amendment does not reopen DEC-025 for PCP:
DEC-025C–F remain Human Owner/operator-managed.

The Runtime mounts `config/` read-only but caches ProjectBaseline YAML in
process. Source merge is complete, but local activation is still pending:
Runtime must be restarted/reloaded under the zero-active-job gate before a new
PM plan is ingested; otherwise it can keep the old cached revision even though
the host file changed.

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

This DEC-025C run later served as useful live calibration for provider recovery and adaptive-budget defects. It is now historical platform evidence only. The Human Owner has taken direct ownership of the remaining DEC-025 work in `chonhac`; do not reroute or resume this job.

## Retired `chonhac` DEC-025C orchestration

The Human Owner has taken direct operator ownership of the complete remaining
DEC-025 pre-beta hardening gate in `chonhac`. Personal Coding Platform
orchestration for DEC-025 is retired.

Historical identity retained for audit:

- plan: `pm-gh-5650852312`;
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`;
- job: `eec59b13651c54559c10ce204380a68e`;
- branch: `ai/eec59b13651c`;
- workspace: `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`;
- source baseline: `b143fbb001c2006ec82570619802b607085fbeb0`.

Final retained telemetry before retirement included model calls `132`, tools
`206`, tests `122`, repairs `55`, elapsed `323.918` minutes and
cache-aware input `8,072,466`. The run exposed several PCP defects that were
subsequently fixed (#238, #240, #244, #247 and #252); those fixes remain valid
platform work independent of the retired product WorkOrder.

Retirement rules:

- do not activate #252 merely to continue this DEC job;
- do not reroute, resume, force-complete or replay historical Telegram actions;
- cancel the durable job through the Runtime API, then invoke the supported
  cleanup endpoint with `remove_workspace=true`;
- retain durable job/plan/WorkOrder records as audit history rather than
  hand-editing/deleting database rows;
- after cancellation, the old workspace may be removed because the Human Owner
  explicitly chose to discard the unmerged C1 work and execute DEC-025 manually;
- future DEC-025 progress belongs in the `chonhac` repository/operator evidence,
  not in PCP orchestration state.

The local retirement cleanup is now complete:

- Runtime job `eec59b13651c54559c10ce204380a68e` was observed `blocked` before cleanup;
- the supported `POST /v1/jobs/{job_id}/cancel` transition persisted `cancelled`;
- the supported cleanup endpoint with `remove_workspace=true` returned
  `cleaned=true` and `workspace_removed=true`;
- the exact workspace
  `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`
  no longer exists;
- a read after cleanup still returns the durable job identity with terminal
  status `cancelled`; the public `JobView` intentionally does not expose the
  internal progress/counter object, so the cleanup probe printing those fields
  as null is not evidence of counter deletion;
- ddev-executor reports `active_jobs=0`;
- deployed Router is `1.0.25` with policy v16 and deployed Runtime is
  `1.0.49`;
- credential-boundary checks passed;
- aggregate `platform-status` reported `n8n DOWN` during the cleanup check,
  but an immediate direct in-container probe of
  `http://127.0.0.1:5678/healthz` returned HTTP 200 with
  `{"status":"ok"}`; treat the earlier aggregate line as a transient
  false-negative rather than an n8n outage.

The merged #252 behavior remains part of the platform baseline: Runtime
`1.0.49`, Router `1.0.25`, routing policy v16. DEC-025 retirement is not a
reason to roll those fixes back.

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
- #252 / PR #253: adaptive cumulative input/output token thresholds made non-blocking telemetry while legacy-hard token ceilings and independent safety gates remain strict; exact-head CI #442 green; merged at `2c78d304bedbeda75a60f99b828e8820119b7f13`.

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

1. With zero active engineering jobs, sync local PCP main through merge `80ec29bbda4b74a0dcf718c6498bce00228e902b` and restart/reload Runtime so its cached ProjectBaseline resolves `mvp-v1-2026-09-22-design` at `afc0901a6c073f763c440df4d492778c12fec11a`.
2. Read back the resolved baseline inside the deployed Runtime before ingesting any new Chợ Nhạc work.
3. Only after that activation proof, ingest bounded issue #14 / UI-CL-1 responsive-test WorkOrder; keep #15 and #16 pending so there is only one active engineering task.
4. DEC-025 cleanup remains complete. Do not recreate or resume a PCP plan/job for DEC-025; future DEC-025 evidence is Human Owner-managed in `chonhac`.
5. Keep the cancelled durable DEC job/plan/WorkOrder rows as audit history and do not hand-edit Runtime database state.
6. No n8n recovery is required: the direct health probe returned HTTP 200 with `{"status":"ok"}`; retain awareness that aggregate `platform-status` can transiently false-negative this service.
7. Keep #146 open for calibration evidence already learned from the retired long-running DEC execution.
