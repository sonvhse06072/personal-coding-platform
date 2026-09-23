# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-24

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
process. Local activation is now proven:

- local PCP main synced to `91b31010e038944d2365f32bd30dc96faaa8ca37`;
- preflight and post-restart checks both reported zero active engineering work;
- Runtime read-back resolved project `chonhac` to revision
  `mvp-v1-2026-09-22-design`, status `approved`, source commit
  `afc0901a6c073f763c440df4d492778c12fec11a`;
- baseline activation exited successfully.

Issue #14 / `UI-CL-1-responsive-regression-matrix` has now been submitted for
orchestration via PM-plan comment `5771302871`. Issues #15 and #16 remain
pending to preserve single-active-engineering-task execution.

Immediately after restart, aggregate `platform-status` reported
`antigravity-bridge down` and `n8n DOWN` while Router, Runtime,
ddev-executor and credential-boundary checks were healthy. Treat those two lines
as requiring direct probe before claiming orchestration/provider health; they do
not invalidate the ProjectBaseline activation proof.

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

## Chợ Nhạc UI-CL-1 routing false-positive and R2 recovery

The first bounded Design Closure WorkOrder for `chonhac#14` was ingested on the
approved design baseline as:

- plan: `pm-gh-5771361558`;
- WorkOrder: `UI-CL-1-responsive-regression-matrix`;
- job: `4283bb02a28a5c96b71f7bb1bc5e3676`;
- source commit: `afc0901a6c073f763c440df4d492778c12fec11a`;
- baseline: `mvp-v1-2026-09-22-design`.

The job blocked before any planner/executor/model work ran:

- status: `blocked`;
- profile/executor remained unset;
- reason: `work_order_policy_rejected`;
- failure: Router selected profile `critical` while WorkOrder
  `max_profile=standard`.

Root cause was a platform false-positive, not Chợ Nhạc task complexity. The
canonical WorkOrder description contains explicit out-of-scope/preservation
language. Repo keyword analysis interpreted phrases about authentication,
security, schema/API changes and proof secrecy as intended protected changes.
That stale analysis forced Router's protected minimum-profile logic.

PCP #262 / PR #263 fixes the boundary and is merged at
`427b930c44a91b1e262419d488aa8469298c80c1`:

- plan-orchestrated WorkOrders now supply authoritative protected-change
  RepoHints from explicit WorkOrder risk flags;
- final task protected flags are derived from the final repo analysis rather
  than raw pre-hint keyword booleans;
- legacy free-text jobs keep their historical keyword inference;
- CI #459 passed structure, Runtime, Router and ddev-executor suites.

The Human Owner then activated the merge locally under the zero-active-work
gate. Live Runtime proof confirmed:

- PCP main is `427b930c44a91b1e262419d488aa8469298c80c1`;
- WorkOrder protected-change hint probe passed with false values for
  schema/security/auth/authz/external-api/production/destructive changes when
  those flags are absent;
- Chợ Nhạc baseline still resolves
  `mvp-v1-2026-09-22-design` at
  `afc0901a6c073f763c440df4d492778c12fec11a`;
- direct n8n and Antigravity bridge probes are healthy;
- original job `4283bb02...` remains blocked and untouched.

Do not resume/reroute the original job. It persisted the stale false-positive
repo analysis/task flags, and explicit reroute reuses persisted analysis. Keep
the original plan/job/workspace as durable audit evidence.

The safe recovery is one fresh R2 WorkOrder, using the same approved baseline,
source, test-only scope and bounded budget after the fixed analyzer is live.

R2 is now live and routed cleanly:

- plan: `pm-gh-5772402026`;
- WorkOrder: `UI-CL-1-responsive-regression-matrix-r2`;
- job: `812aabd7ab0a5adbb18a7a5edc8d7009`;
- status: `executing`;
- source commit: `afc0901a6c073f763c440df4d492778c12fec11a`;
- baseline: `mvp-v1-2026-09-22-design`;
- profile: `standard`;
- executor: `openrouter_qwen3_coder_free`;
- branch: `ai/812aabd7ab0a`;
- workspace:
  `/home/sonvh/.coding-platform/workspaces/812aabd7ab0a5adbb18a7a5edc8d7009`;
- route reason/failure: none;
- orchestration plan: `executing`;
- tracked WorkOrder state: `running`.

This proves #262 corrected the protected-change false-positive for the same
bounded test-only design contract: the R2 route remains within the WorkOrder
`standard` ceiling. The original job `4283bb02...` remains blocked and
audit-only.

R2 later exposed three PCP/runtime infrastructure defects while preserving the
same job/workspace/diff/counters:

- #266 / PR #267, merged at
  `ec32ab4e7367efdd997b6f848c35d151c8c1f3fa`: coding CLI timeouts are
  converted to structured `failure_kind=timeout` attempts so normal provider
  failover can run instead of crashing the Runtime worker;
- #268 / PR #269, merged at
  `60b416aedb27a6589e41a17a504b6943d3068456`: malformed reviewer protocol
  output is no longer converted into a synthetic developer repair finding;
  evaluator/model failover handles the protocol failure instead;
- #270 / PR #271, merged at
  `8cf37611e4e61a5bbdde5c85ca4496bd1bdd07c3`: ddev-executor now reconciles
  the private workspace DDEV identity at creation and before every configured
  phase using `override_config: true` and deterministic `cp-<job>` naming.

The Human Owner activated these fixes under zero-active-work gates and recovered
the same R2 job rather than creating R3. Live evidence now proves:

- the preserved workspace DDEV override resolves to `cp-812aabd7ab` while
  tracked source `.ddev/config.yaml` remains `name: chonhac`;
- the exact configured `targeted_tests` phase passes with PHPUnit 27/27
  tests / 406 assertions;
- the exact configured `static_analysis` phase passes with PHPCS 8/8;
- tracked diff remains exactly
  `frontend/tests/browser/musician-profile.spec.ts` and
  `frontend/tests/browser/verification.spec.ts`;
- R2 was resumed on the same job/workspace with durable counters preserved;
- the fresh route remains `standard` and currently selected `codex_terra`;
- orchestration resumed on the same job after those fixes;
- Antigravity bridge and n8n direct health are healthy.

R2 is now durably `blocked` with `reassessment_stopped`; it is not executing.
Its exact job/workspace/DDEV data and blocked audit evidence must remain
untouched. A 2026-09-23 read-only gate reported Runtime counts `blocked=12`,
`cancelled=1`, `completed=10`, `failed=2`, no active Runtime state, and
`ddev-executor active_jobs=0`.

Issues #15 and #16 remain pending so only one Design Closure engineering task is
active at a time.

## Reviewer repair/rebuttal re-check #284

Issue #284 implementation is in progress on branch
`ai/issue-284-reviewer-recheck`, based on latest `main` merge
`f858d4b1323a5803e818c1e2b1ae61254458e145`.

The bounded fix forwards only the current successful developer turn output to
`evaluator_prompt(..., developer_report=...)`. The existing reviewer evidence
pack remains the compaction boundary, including its 3,000-character developer
report limit. Reviewer instructions classify the report as advisory
repair/rebuttal evidence: the WorkOrder and deterministic repository evidence
remain authoritative, claims are not accepted automatically, and existing
read-only just-in-time repository retrieval remains available.

Engine-level regression coverage proves the complete dialogue edge:

- an initial reviewer failure becomes compact `PCP_REVIEW_FINDINGS` for the
  next developer turn;
- the next successful developer response reaches evaluator re-review;
- the current response is clipped while earlier developer stdout/stderr and
  unbounded tail content do not enter the re-review prompt;
- a reviewer that still finds the same issue unresolved preserves identical
  failure fingerprints and reaches the repeated-failure circuit breaker.

Local source verification currently passes the targeted reviewer/evidence
tests (`14 passed`), full Runtime tests (`393 passed`) and structure tests
(`89 passed`). No Router source changed. The blocked Chợ Nhạc R2 job and live
PCP services were not queried, resumed, rerouted, rebuilt or restarted.

## Dedicated PCP BuildKit isolation #281

Issue #281 / PR #283 is merged on `main` at
`f858d4b1323a5803e818c1e2b1ae61254458e145`. The source change introduces:

- one deterministic `pcp-builder` using the `docker-container` driver without
  changing the user's globally selected builder;
- a host pre-start image helper that explicitly builds and `--load`s fixed
  Router/Runtime/ddev-executor image tags while preserving all existing build
  args;
- Compose consumption of those explicit tags, leaving n8n unchanged;
- executor-only `BUILDX_BUILDER=pcp-builder` selection plus a narrowly mounted
  PCP Buildx metadata directory rather than the host's complete `~/.docker`;
- read-only attribution separating PCP builder cache, shared/default cache,
  platform images, exact PCP DDEV built images, volumes and container
  references;
- explicit report/execute GC with Runtime and executor-idle gates, conservative
  age retention, exact `--builder pcp-builder` cache pruning, and optional
  exact-label terminal image cleanup for completed/cancelled jobs only.

PR review identified that the original zero-work gate used the newest-500
Runtime job inventory and therefore was not exhaustive once job history exceeded
that bound. The merge blocker is corrected in source: Runtime now exposes an
authenticated server-side active-work count over the complete `cp_jobs` table,
and GC fails closed unless that authoritative count is exactly zero. The capped
inventory remains attribution-only, so unmapped older images stay preserved.
Regression coverage models 500 newer terminal jobs hiding one older active job
and proves GC refuses before any Docker mutation. No additional live restart,
validation fixture, or GC was performed; the prior isolation rollout evidence
below remains valid. Updated source verification passes structure `89`, Router
`92`, Runtime `391`, ddev-executor `57`, `bash -n`, and ShellCheck. CI run
`35890188011` passed all four required jobs on corrected source head
`9d2df810df9f7cacdde2f47182a0687ca1f62171`; the following continuity-only
commit does not change executable behavior.

Original implementation source verification passed structure `89`, Router
`92`, Runtime `388`, ddev-executor `57`, script `bash -n`, Compose render, and
scoped ShellCheck. PR CI run `35856810259` passed all four required jobs on
implementation head `761606dcbb58741efc3534e2bffc08f26be198a6`.

Local activation is complete under the required rollout gate:

- pre-activation Runtime counts were `blocked=12`, `cancelled=1`,
  `completed=10`, `failed=2`; R2 was `blocked`; ddev-executor reported
  `active_jobs=0`; Antigravity reported `active_runs=0`;
- the global selected builder was and remains `default` with driver `docker`;
  its pre-activation usage was `24.36GB` total/reclaimable (`18.1GB` private,
  `6.263GB` shared);
- exactly one normal DDEV restart ran after source/CI green; the pre-start hook
  created one `pcp-builder` with driver `docker-container`, built/loaded all
  three deterministic PCP tags, then preserved the existing Antigravity hook;
- the running Router, Runtime and ddev-executor containers reference those
  exact local tags and ddev-executor reports version `1.0.19`;
- after the first platform build, `pcp-builder` held `3.421GB` while the
  shared/default builder stayed exactly `24.36GB`;
- a no-source-change repeat build reused 20 cached steps, retained one named
  builder and kept both cache totals unchanged;
- a disposable `pcp-validation-fixture` workspace build through the live
  executor grew only PCP cache from `3.421GB` to `6.322GB`; shared/default
  remained exactly `24.36GB`, proving no silent fallback for the
  executor-owned build path;
- the exact fixture DDEV data/images and Git workspace were then removed; no
  fixture container, volume, image or workspace remains;
- inventory distinguishes both builders, all three platform images, exact
  Runtime-correlated DDEV built images, PCP volumes and container references;
- GC dry-run preserved every remaining blocked/failed image; cache-only GC with
  `until=168h` passed both zero-work gates and retained `6.322GB` PCP cache
  because it was newly accessed;
- before/after GC shared/default usage remained exactly `24.36GB`, and the old
  shared cache was intentionally not pruned;
- post-activation live tests passed Router `92`, Runtime `388` and
  ddev-executor `57`; direct n8n/Antigravity health and strict credential
  boundaries passed; R2 remained blocked and untouched.

DDEV's platform/base web and database image machinery still ran independently
after the PCP custom-image hook. This implementation proves isolation for the
three PCP custom services and executor-owned workspace DDEV builds; it does not
claim every DDEV build on the machine uses `pcp-builder`.

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

1. Complete issue #284 through one unmerged PR with exact-head CI green; do not
   activate the Runtime change or resume R2 as part of that implementation PR.
2. Keep the retained shared/default BuildKit cache unchanged. Any later cleanup
   decision must remain separate from #281's proof of isolation.
3. Keep R2 job `812aabd7ab0a5adbb18a7a5edc8d7009` durably blocked; do not
   resume, reroute, clean, or use its workspace/resources as the #281 rollout
   fixture.
4. Treat any future deterministic verification failure as project evidence only
   after confirming the command actually reached PHPUnit/PHPCS/Playwright;
   infrastructure-start failures must not be sent back to the developer as code
   repairs.
5. If R2 reports a genuine responsive product defect requiring production-code
   change, keep UI-CL-1 test-only and open a separate bounded defect issue
   rather than broadening the current WorkOrder.
6. Keep Chợ Nhạc #15 and #16 pending until #14 R2 is reviewed and merged.
7. Keep the original blocked UI-CL-1 job/plan as platform-defect audit history;
   do not resume/reroute it or hand-edit durable Runtime state.
8. DEC-025 cleanup remains complete. Do not recreate or resume a PCP plan/job
   for DEC-025; future DEC-025 evidence is Human Owner-managed in `chonhac`.
9. Keep #146 open for calibration evidence already learned from the retired
   long-running DEC execution.
