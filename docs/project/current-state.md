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

Issue #284 / PR #285 is merged on `main` at
`836af29f3ee308e1ea5aab8a47194b2ada682331`.

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
(`89 passed`). PR CI run `35901028807` passed Runtime, Router, ddev-executor and
structure jobs on head `00c7851ab63e6ce7441bb96f52e1f71d4f988a19`.
The following continuity-only commit records that result without changing
executable behavior. No Router source changed. The blocked Chợ Nhạc R2 job and
live PCP services were not queried, resumed, rerouted, rebuilt or restarted.

## Repeated-failure current-tail correction #286

Issue #286 / PR #287 is merged on `main` at
`3075a4f588074a2206909360b56b20029003e335`. The implementation head was
`6725b3afa171c0b824cde28e54051678525380f7` and the final continuity head was
`ebcca7e56257c8c3d4a65db7c30c207e1f073704`.

The Router repeated-failure circuit breaker now reverse-scans only the
consecutive suffix matching the most recent durable failure fingerprint. The
complete `failure_fingerprints` history remains unchanged for audit and
telemetry, and the existing strict `count > limit` threshold is preserved.
Focused reassessment regressions prove:

- `A,A,A` triggers `repeated_failure:A`;
- historical `A,A,A` followed by one or two `B` failures does not report a
  repeated failure;
- a later `B,B,B` current tail triggers `repeated_failure:B`;
- alternating fingerprints do not trigger repetition;
- reassessment preserves the complete durable input history;
- satisfied definition-of-done still completes before circuit-break analysis;
- the live resumed-job shape with historical reviewer fingerprint
  `36cc7091c604759ae89c94f4` followed by one new deterministic failure remains
  runnable without reporting the stale reviewer fingerprint.

Local source verification passes the targeted reassessment file (`23 passed`),
the full Router suite (`99 passed`, one existing dependency deprecation
warning), and structure tests (`89 passed`). No Runtime contract/import or
ddev-executor source changed, so those conditional suites were not required.
R2 job `812aabd7ab0a5adbb18a7a5edc8d7009`, its workspace/durable history and Chợ
Nhạc were not queried or mutated. Live PCP services were not restarted, rebuilt
or modified, and cache/GC was not run.
GitHub Actions run `35910395359` passed Runtime, Router, ddev-executor and
structure jobs on the implementation head. Final exact-head run `35910569565`
passed all four jobs before PR #287 merged. The blocked R2 job was not resumed
or otherwise mutated as part of that merge.

## GitHub Actions pre-run failure classification #288

Issue #288 / PR #289 is merged on `main` at
`2174a1efd595aa79f6a750fc3d5cba150e7db737`. Its implementation branch was
`ai/issue-288-ci-infrastructure-classification`, based on then-current `main`
`3075a4f588074a2206909360b56b20029003e335`. Follow-up implementation head
`95a6c2326f881d3ba24689f5b82525983a37f2cd` corrects pre-follow-up head
`1334c0a96669726fe9ba40b99f274bd7dad2aef1` after PM blocking review comment
`5803004566` identified one legacy live-recovery gap.

The bounded delivery fix preserves the existing top-level CI state contract and
adds explicit failure evidence/classification:

- failed Actions jobs retain runner identity, steps, timestamps, whether any
  repository execution started, and available log excerpts;
- `startup_failure` and the exact runnerless `runner_id=0` / `steps=[]` shape
  classify as delivery infrastructure;
- assigned-runner/executed-step failures, legacy commit-status failures and
  ambiguous/missing evidence remain engineering failures fail-closed;
- Runtime blocks pre-run failures as `github_ci_infrastructure_failure` while
  preserving the accepted result, verified commit, branch and pull request;
- this path does not increment `ci_failures` or `repair_iterations`, append an
  engineering failure fingerprint, invoke the implementation engine, or require
  another material repository change;
- `retry_delivery` / `recheck_ci` reuse the accepted commit. Each delivery
  attempt remains bounded and a repeated pre-run failure blocks again with the
  infrastructure-specific reason rather than entering an automatic loop;
- a later CI success for the exact accepted commit finalizes the same durable
  job normally.

The PM blocker concerned jobs already damaged by the old classification before
#288 is activated. `ExecutionRuntimeEngine._block()` replaced the previously
accepted `result` when the obsolete engineering-repair turn later produced
`material_change_missing_without_model_fallback`; therefore checking only
`result.status=accepted` or `result.accepted_result` could still send an
already-delivered job back to coding.

The selected recovery is design A, using only authoritative PCP-owned durable
evidence. Runtime recognizes the legacy shape only when its own
`checkpoint.delivery` records that CI delivery had begun and failed. It
reconstructs the accepted delivery result only when all of these bindings agree:

- same Runtime job through pull-request delivery metadata;
- exact 40-character verified commit, source commit and AI branch across the
  delivery, publish, PR and CI records;
- published/open PR repository and base/head identities;
- deterministic test and required-check progress already passed with no
  unexpected scope;
- required independent review policy, satisfied independence, passing
  protocol-valid review summary/history, reviewer model/provider identity and
  no pending findings;
- original route permissions for commit, AI-branch push and PR creation.

Workspace cleanliness, branch ancestry, commit existence and PR existence are
never used as acceptance proof. A complete match returns directly to bounded
delivery/CI observation on the exact accepted commit without invoking the
implementation engine, requiring a new diff, or changing engineering counters.
If any authoritative binding is missing or inconsistent, Runtime blocks as
`legacy_delivery_acceptance_evidence_incomplete`; control actions offer neither
coding reroute nor delivery retry in that incomplete state. Ordinary
implementation-only `material_change_missing_without_model_fallback` jobs keep
their existing bounded reroute behavior.

Code-path analysis shows the legacy R2 lineage is automatically recoverable if
the delivery checkpoint fields written by the old Runtime remain intact. The
follow-up deliberately did not query R2 to confirm its live row. If any required
field is absent, the same job/workspace/branch/PR/history instead remains
fail-closed for authoritative operator evidence and never falls through to
coding. A focused live-shape regression proves legacy result loss followed by a
runnerless infrastructure failure and later exact-SHA CI success with zero new
model calls and zero engineering repair increments.

Follow-up local verification passes focused Runtime delivery and control-action
tests (`37 passed`), the full Runtime suite (`405 passed`), the full
ddev-executor suite (`60 passed`) and the structure suite (`89 passed`). Router
contracts were not changed by the follow-up, so its suite is not required. The
blocked Chợ Nhạc R2 job, its workspace and
PR #18 were not queried or mutated; live PCP services were not restarted,
rebuilt or modified, and cache/GC was not run. Later repository-level
self-hosted CI supplied the required executing/green merge evidence; the
implementation-engineer did not merge the PR.

GitHub Actions run `35920237209` on implementation/continuity head
`5e62b8e7d44d0ee9a142ffc022357c48a0375ffa` failed before repository execution
on both the initial attempt and one bounded direct rerun. All four required jobs
reported `runner_id=0`, empty `runner_name` and `steps=[]`, completing in about
two seconds. Attempt 2 exposed GitHub's annotation that the jobs were not
started because recent account payments failed or the spending limit must be
increased. This is delivery infrastructure evidence, not an engineering test
failure. PR #289 is therefore not merge-ready; after the external GitHub billing
condition is repaired, re-run CI on its exact current head and require all four
jobs to pass. Do not send this failure through source repair or activate/restart
PCP merely to retry it.

Follow-up implementation run `35923484857` on exact source head
`95a6c2326f881d3ba24689f5b82525983a37f2cd` has the same external failure. Its
four required jobs each reported `runner_id=0`, empty `runner_name` and
`steps=[]`; GitHub annotated every job as not started because of failed account
payments or a spending-limit condition. No repository command ran. This remains
delivery infrastructure evidence and is not a reason for another source change.

## Trusted exact-SHA CI revalidation #291

Issue #291 is implemented on branch
`ai/issue-291-exact-sha-ci-revalidation` from merged #288/#289 main
`2174a1efd595aa79f6a750fc3d5cba150e7db737` and is open as PR #292. PM review
identified that reviewed head `5745d7dbdea6b83c7c3d1f4cc113022c1b920ed6`
incorrectly expected creator metadata in GitHub's combined-status entries. The
source correction now authenticates creator metadata through an exact-ID-bound
list-status read while preserving combined-status ordinary semantics. Local
implementation and verification are complete. GitHub Actions run `35970427013`
passed Runtime, Router, ddev-executor and structure jobs on corrected source
head `1e6c1f995cdb3525320ac83fe319be5aa9081477`; every job used runner `SonVH`
(`runner_id=21`) with `[self-hosted, linux, x64]` and executed non-empty
repository steps. This continuity-only update changes no executable behavior;
its own exact-head CI remains required before PM re-review. The implementation
agent must not merge the PR.

The ddev-executor now recognizes one narrow recovery status context:
`pcp/exact-sha-ci`. A status is trusted only when all available legacy-status
bindings agree:

- the combined-status response SHA and requested target are the same exact
  40-character SHA;
- the context is exactly `pcp/exact-sha-ci` and the state is terminal
  `success`, `failure`, or `error`;
- `created_at` is a valid timezone-aware GitHub timestamp;
- `target_url` is an HTTPS GitHub Actions run URL for the exact same repository;
- the combined status has a positive integer GitHub status ID, and the bounded
  `GET /commits/{sha}/statuses?per_page=100` response contains exactly one
  object with that exact ID;
- that exact list-status object identifies the publisher as
  `github-actions[bot]` with type `Bot`.

The combined-status endpoint remains authoritative for the combined state and
latest-per-context ordinary commit-status semantics. Historical list-status
entries are used only to hydrate creator metadata for a combined trusted status
with the exact same status ID; context, timestamp, state, target URL or array
position can never substitute for the ID. Historical entries do not become
ordinary CI signals. A missing ID match, ambiguous duplicate ID, missing/wrong
creator, non-success list-status response or malformed list payload invalidates
trusted recovery and produces an explicit infrastructure-classified effective
failure. Transport errors continue through the existing GitHub-delivery API
error path. Both behaviors fail closed and cannot turn unauthenticated trusted
evidence into CI success.

A valid trusted success supersedes only Actions failures already positively
classified as infrastructure/startup failures whose run `updated_at` is
strictly earlier than the status `created_at`. Equal, missing, malformed or
otherwise ambiguous ordering never supersedes a failure. Engineering failures
remain effective regardless of age; a newer engineering failure or trusted
failure remains engineering CI failure; generic or wrong-context successes,
wrong-SHA/repository evidence and malformed trusted evidence have no recovery
authority. Ordinary Actions and commit-status behavior is otherwise unchanged.

All historical failures remain in `failures`, `checks`, `actions_runs` and
`audit_failure_text`. The response separately exposes trusted evidence,
`effective_state`, `effective_failures`, `superseded_failures` and whether older
infrastructure failures were superseded. Runtime source did not need to change:
the existing #288 delivery contract consumes effective `state=success` as
`delivery.state=ci_success`, preserving the exact accepted commit, workspace,
branch and PR without model/repair/engineering-failure increments or an
implementation-engine invocation. A trusted validation failure remains
`failure_class=engineering` and enters the existing repair path.

PCP remains consumption-only. The existing delivery token boundary uses
`Actions: read` and `Commit statuses: read`; workflow dispatch would require
`Actions: write` and publishing would require `Commit statuses: write`. No PCP
token permission was expanded and #291 adds neither operation.

Chợ Nhạc still requires a separate repository-owned workflow before live
revalidation. That workflow contract is: run from the current default-branch
definition on repository self-hosted infrastructure; accept and validate an
exact 40-character `target_sha`; check out exactly that immutable SHA; run the
repository's currently approved CI commands; always publish the terminal result
to that SHA under `pcp/exact-sha-ci` using only workflow-scoped
`statuses: write`; and set `target_url` to its own GitHub Actions run. A failed
repository check must publish failure, never success. Adding that workflow is
not part of this PCP PR.

Local verification passes focused ddev-executor GitHub-delivery tests (`30
passed`), the full ddev-executor suite (`78 passed`), focused Runtime delivery
tests (`21 passed`), the full Runtime suite (`407 passed`) and structure tests
(`89 passed`). Static Python compilation and `git diff --check` pass. Chợ Nhạc,
R2, its workspace/durable state and PR #18 were not queried or mutated; R3 was
not created; PCP was not restarted or rebuilt.

## Owner-attention generation and supersession #293

Issue #293 / PR #294 is merged on `main` at
`a08e2bd58e2ea2f00b1ee8701031f9fb74d55d6a`. The executable implementation
head was `f33eb15148b9668227d5e73256e5deac55da7acb`.

The bounded Runtime correction keeps transport and merge policy unchanged:

- no-op `update_plan()` and `update_work_order()` calls no longer advance
  `updated_at`; real status, state, detail, job or PR changes still do;
- strict timestamp-bound mutation validation remains intact, while separate
  semantic attention generations exclude polling timestamps and opaque action
  IDs;
- repeated stable `awaiting_merge`, `blocked` and `waiting_human` ticks reuse
  the existing control/notification generation;
- pending or delivering notification rows from an obsolete attention state or
  generation become `superseded`; sent rows remain unchanged and no audit row
  is deleted;
- pending old-generation controls become `cancelled`; executed control history
  is unchanged;
- a historical `recheck_orchestration` callback against a completed WorkOrder
  returns benign `already_resolved`, while conflicting/non-terminal controls
  retain strict stale/fail-closed behavior;
- Runtime source version advances to `1.0.50`.

The live-shaped regression uses plan `pm-gh-5772402026`, WorkOrder
`UI-CL-1-responsive-regression-matrix-r2` and job
`812aabd7ab0a5adbb18a7a5edc8d7009`, but only as in-memory test identity. Local
source verification passes focused Runtime store/orchestration/control tests
(`38 passed`), the full Runtime suite (`418 passed`), structure tests (`89
passed`), top-level Telegram/n8n transport tests (`11 passed`), Python
compilation and `git diff --check`.

No live PCP service was restarted/rebuilt/activated. Chợ Nhạc, the completed R2
WorkOrder, its workspace/durable state and Telegram were not queried or
mutated. The n8n workflow JSON and existing send/ACK/release transport contract
are unchanged.

## Explicit superseded orchestration lifecycle #295

Issue #295 is implemented on branch
`ai/issue-295-superseded-orchestration-lifecycle` as PR #296. PM review through
head `45027a05d18c56586e7c4bc56e67e4248eac8e20` accepted the lifecycle design
and plan-level attention retirement, then identified that lifecycle filtering
must remain scoped to owner attention. The branch now includes that bounded
correction; exact-final-head CI and PM re-review remain pending.

The bounded Runtime change separates execution truth from orchestration
eligibility:

- `cp_plan_work_orders.lifecycle` defaults to `active` and may become
  `superseded` only through the exact authenticated Runtime operation;
- exact optional replacement plan/WorkOrder identity, timestamp and reason are
  durable on the retired WorkOrder; a plan becomes lifecycle `superseded` only
  when no active tracked WorkOrder remains;
- original WorkOrder state, job status/result/progress/counters/workspace and
  replacement state are not changed;
- scheduler, busy-work, reconciliation, automatic provider/adaptive recovery,
  merge and explicit resume paths exclude superseded lifecycle rows;
- startup/tick notification materialization and control creation exclude them;
  pending/delivering owner attention becomes `superseded`, pending controls
  become `cancelled`, and sent/executed audit history remains unchanged;
- plan/WorkOrder lifecycle is authoritative specifically for owner-attention
  eligibility: owner-attention claim and emission reject non-active lifecycle,
  including plan-level rows with no WorkOrder identity; when the final active
  WorkOrder is superseded, pending/delivering owner attention for the whole plan
  is superseded with its lease cleared, while sent history stays sent and
  unrelated non-owner/audit events retain normal outbox emission and delivery;
- historical callbacks return benign `status=superseded`; active WorkOrders
  retain strict state-fingerprint validation;
- dashboard/read state exposes both historical execution status/reason and the
  supersession relationship without presenting the record as completed.

Local synthetic PostgreSQL proof created a pre-#295 schema/row set, applied
`ensure()` twice, and verified additive/defaulted columns, old-row validity,
idempotent supersession and persistence across store instances. The synthetic
database was then removed. Current local verification passes focused Runtime
orchestration/outbox/control/dashboard tests (`63 passed`), full Runtime (`432
passed`), Router (`99 passed`), ddev-executor (`78 passed`), structure (`10
passed`) and Telegram/n8n transport (`11 passed`). Python compilation and
`git diff --check` pass.

The real Chợ Nhạc original job/plan, completed R2 WorkOrder/PR #18, Telegram,
n8n and live PCP durable state were not queried or mutated. No service was
restarted/rebuilt, and no live supersession was performed.

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

1. Require all four GitHub Actions jobs to execute repository steps and pass on
   PR #296's exact final head when runner infrastructure is available. Do not
   merge or activate PCP services from the implementation-engineer role.
2. Keep the retained shared/default BuildKit cache unchanged. Any later cleanup
   decision must remain separate from #281's proof of isolation.
3. Keep completed R2 WorkOrder
   `UI-CL-1-responsive-regression-matrix-r2` and merged PR #18 unchanged.
4. Treat any future deterministic verification failure as project evidence only
   after confirming the command actually reached PHPUnit/PHPCS/Playwright;
   infrastructure-start failures must not be sent back to the developer as code
   repairs.
5. Keep the original blocked UI-CL-1 job/plan as platform-defect audit history;
   do not resume/reroute it or hand-edit durable Runtime state. Any eventual
   live supersession requires post-merge controlled activation and an explicit
   Human Owner operation against only that exact identity.
6. DEC-025 cleanup remains complete. Do not recreate or resume a PCP plan/job
   for DEC-025; future DEC-025 evidence is Human Owner-managed in `chonhac`.
7. Keep #146 open for calibration evidence already learned from the retired
   long-running DEC execution.


## Direct workspace + live preview initiative #297

Human Owner approved a new local-development workflow on 2026-09-25: selected
projects may let PCP work directly in the registered local repository so the
Human Owner and developer agents can inspect the same running frontend/backend.

The initiative is intentionally split:

- #298 / PR #300: core direct-workspace execution with a durable exclusive
  per-project lease, exact direct-repository mount, clean-repo/branch guards,
  isolated-clone backward compatibility, and safe executor/Antigravity access;
- #299: Dashboard live-preview controls for direct workspaces after #298 is
  merged.

Chợ Nhạc is the first acceptance project and its registered path is
`/home/sonvh/chonhac`. Direct mode is **not activated yet**. The currently
running Chợ Nhạc engineering job continues under the existing isolated
workspace contract. Source merge of #298 does not authorize a PCP restart or a
mid-job workspace migration.

Activation later requires a safe engineering boundary, adding the exact
`CODING_DIRECT_PROJECT_ROOT=/home/sonvh/chonhac` local setting, enabling the
reviewed project runtime mode, and rebuilding/restarting PCP under the normal
guarded activation process.
