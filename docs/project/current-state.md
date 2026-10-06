# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
fresh Runtime/GitHub evidence remain authoritative over chat history. This file
is an index, not authority to change the approved baseline or protected scope.

Last updated: 2026-10-05 theo owner v5 release recovery lúc
`2026-10-04T18:31:55.449578+00:00`. Generation 1 đã release; AP-MVP-01 đang execution.

## Resume order

1. Read root `AGENTS.md`, `docs/project/README.md`, then this snapshot.
2. Read only relevant T2 contracts and T3 episodes in `history/episodes.md`.
3. Check live issue/PR, exact source, Runtime health, active jobs, project lease
   and local Git before any mutation. Older snapshots are evidence, not live locks.

Memory-tier policy: `context-memory-architecture.md`.

## Accepted platform / local state

- Runtime `1.0.106`; Router/executor healthy; executor `1.0.31`.
- Owner audit v2 observed active engineering jobs = 0 and executor active_jobs = 0.
- Local PCP is clean `main@e7fb6d364f109a2ddee979d3a040367b03d87f73`.
  Later PCP handoff PRs are docs-only; do not restart just to obtain them.
- Chợ Nhạc is clean `main@aa8e68dd9aea6740de446151eb97615931de9b40`.
  Historical `ai/c02defa348fc` ref remains at
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`.
- #463 / PR #464 is complete: planning source references are restricted to the
  sorted/deduplicated `ProjectBaseline.references` allowlist. Authority-only
  paths never become eligible references by implication.
- #466 / PR #468 is implemented, merged and locally accepted. Historical GET
  reads preserve template visual routes through non-executable snapshot models;
  executable WorkOrder / PM proposal validators remain strict. No repeat rollout,
  diagnostic or restart is needed.
- In-process replay proof is not described as an HTTP POST replay test. Digests
  from different probes are compared only with the same serialization contract.

## Chợ Nhạc approved frame

- Active baseline for new work: `pilot-v1-2026-10-04-dec033-r3`.
- Immutable authority source: `aa8e68dd9aea6740de446151eb97615931de9b40`.
- r3 preserves r2 source/authority and adds the authorized local-only
  `docs/26-local-demo-workflow.md` to requirements/quality-policy references.
  There are 27 reference paths; `docs/12-launch-metrics.md` remains authority-only.
- r2 at the same source, r1 at `132c2ef767b595833677e9672d655872e07ba9b7`,
  and the original `pilot-v1-2026-10-03-dec033` stay immutable/resolvable.
  Do not create r4, rewrite r3, or add references to fit a rejected proposal.
- Direct project root `/home/sonvh/chonhac`; configured base `main`;
  `workspace_mode=direct`, exclusive engineering lease enabled, AI prefix `ai`.
- DEC-033 remains the controlled-pilot execution decision. Historical DEC-025 and
  GH-42 execution are retired, not candidates for resume/reroute/recreation.
- PILOT-01 / GH #61 is accepted and merged through Chợ Nhạc PR #67 at the current
  authority source. The product head was `88dd4f60...`; final product diff was
  16 files / +223 / -56, within its <=25-file budget. Do not reimplement it.
- CI governance repairs #68/#69 and #70/#71 preserve documentation authority and
  isolated PostgreSQL 17 verification; the repository runner does not gain
  Docker/DDEV privileges.

## Historical reconciliation and lease — complete

Supersession snapshot `2026-10-04T16:20:55.930831+00:00` proved 29 exact supported
supersessions with zero model calls. Historical plan
`pm-5cd9ec06f74b4feba4db5a1507ab35f0` and the three rejected plans
`pm-095d6aea0fe94901bbf692fa7d113fc2`,
`pm-a72e960c0f3b458897831cff3fb51a30`,
`pm-ac6a52e6019947adab8744a7ada72011` are lifecycle=superseded.
PILOT-02..08 map to the approved seven successor WorkOrders; PILOT-01 has no
replacement because its product was merged. Source state/history is not rewritten
as implementation success. Mapping details:
`pilot-successor-reconciliation-map-b0748be-2026-10-04.md`.

The supported historical cancel was sent once. Audit v2 now proves:

- job `c02defa348fc5b19a0bd021e2697571e` is `cancelled`;
- exact generation-9 lease is `released`, with recorded update
  `2026-10-04T16:47:00.470307+00:00`; owner identity is retained;
- preview absent; `resource_quiesce` is quiesced=false/data_removed=false;
- `direct_base_restore` succeeded to clean `main@aa8e68dd...`, reused=false;
- progress/result and all five immutable plan rows are preserved;
- full pre-cancel checkpoint hash is reproduced by restoring the pre-existing
  blocked `resource_quiesce` on a RAM copy and removing the new restore field.
  Matched case: `RESTORE_PREEXISTING_BLOCKED_QUIESCE`.
- The hash is `639bf30eb2b7e796d5a5eafe8ffd315375c65491f844f42e12e0ccb16136344c`.
  No reconstruction was written to the database.

Owner artifact `chonhac_post_cancel_audit_v2.json` SHA256:
`b7e11836b7c5a1ab7339fb36e727445a4695ac719871f30e40436f46f312d76b`.
Acceptance and conditional next action are recorded in Chợ Nhạc #63 comment
`5982524270`. Do not repeat cancel, alignment, supersession, intake or checkpoint
probes. The old audit's pop-both-fields comparison was invalid for a field that
already existed and was overwritten; its STOP did not imply rollback.

## Approved candidate — generation 1 released

Plan: `pm-b0748be27f8446a0813c2d1fe7d697fd`.
Content approval: #63 comment `5981710459`;
review details: `pilot-successor-pm-review-b0748be-2026-10-04.md`;
contract/fixture ownership: `pilot-successor-review-2026-10-04.md`.
These are execution evidence, not added ProjectBaseline references.

Plan digest remains
`f667ffe9d27fc3824f550089cf09269b0cfa7ccc58654d8c9e8a30e91ac7ab7d`.
Owner v5 evidence shows generation 1 / checkpoint 45 was released through the
supported `/continue` endpoint with exact continuation key
`plan:continue:eb370313ac975fc2b6d9331b73cde0ebbd944bf0d54ade8f12eb7805e9722fe3`.
Runtime acknowledged `status=released`, `idempotent=false`, and launched only
`AP-MVP-01-artist-profile-data-curation` as deterministic child job
`6b89482673ea5d2a92cc46b6ba7acf84`.

Immediate observation after release: plan `executing`, lifecycle active,
generation 1 supervision state `released`; AP-MVP-01 row `running` with the
exact child job; the other six successor rows remain pending with no job IDs.
The first child-job observation was `status=routing`; later Runtime progress
must be read fresh rather than inferred from this launch snapshot.

The seven sequential WorkOrders / issues / adaptive file targets are:

1. `AP-MVP-01-artist-profile-data-curation` — #48 / 45 / complex.
2. `AP-MVP-02-artist-profile-public-experience` — #49 / 55 / complex.
3. `EE-0-01-event-backend-domain-api-access` — #56 / 90 / critical.
4. `EE-0-02-public-event-discovery-detail` — #57 / 55 / complex.
5. `EE-0-03-studio-event-management-participation-program` — #58 / 65 / complex.
6. `AP-MVP-03-generalized-verified-performance` — #50 / 45 / complex.
7. `EE-0-04-event-engagement-analytics` — #59 / 35 / critical.

Keep all 42 acceptance criteria, linear dependencies, risk flags/profile floors,
concrete visual routes and local fixture ownership. #50 has frontend_quality
before visual_quality and only EventParticipation as a live pilot provider.
No Booking provider/query/contribution, public recruitment, Reviews, Band domain,
Audience identity/feedback, payment or staging/production seed/deployment.

## Generation-1 execution — active

The historical reconciliation/lease gate and generation-1 release gate are
complete. Do **not** rerun v1-v5 release helpers, delete either durable attempt
marker, repeat cancel/alignment/supersession/intake, or manually create another
AP-MVP-01 job.

The successful v5 recovery was valid only because pinned v4 evidence proved the
prior attempt had `continue_post_attempted=false`. V5 preserved the original
marker, created a second O_EXCL recovery marker, re-ran all generation-1 gates,
and observed healthy Runtime/router/executor with zero active engineering jobs
before POST. Planner/executor deterministic preview used `codex_terra` with
fresh observed Codex quota pressure 0.16. Evaluator preview used
`openrouter_qwen3_coder_free`; its checked-in registry explicitly declares no
authoritative remaining-quota telemetry. No provider was forced and the standard
Router/failover policy remains authoritative.

Accepted continuation result:
- plan `pm-b0748be27f8446a0813c2d1fe7d697fd`;
- exact generation 1 / checkpoint 45 continuation;
- WorkOrder `AP-MVP-01-artist-profile-data-curation`;
- child job `6b89482673ea5d2a92cc46b6ba7acf84`;
- continue acknowledged, `idempotent=false`;
- six later WorkOrders still pending and unauthorized.

Release acceptance is recorded in Chợ Nhạc #63 comment `5983110319` and #48
comment `5983110686`.

Next PM behavior is the normal supervised execution flow, not another release:
read the exact live job/orchestration before any mutation; preserve the direct
workspace while engineering is active; review implementation evidence, exact
diff/head and required verification; require exact-head CI; then take the
generation-1 supervised checkpoint decision. Generation 2 remains unauthorized
until generation 1 reaches that checkpoint and PM review accepts it.

The v4/v5 markers are historical anti-replay evidence and must remain untouched.
A dirty/new AI branch after the running job enters workspace execution may be
legitimate progress; do not reset/stash/clean merely to recreate the launch
snapshot.
## Active separate platform follow-up

PCP #474: fix `_quiesce_stable_manual_job` detection of persisted orchestrated
jobs. Raw `cp_jobs` does not contain top-level work_order_id; durable identity is
in checkpoint metadata. Existing tests used synthetic top-level fields and did
not cover this Storage shape. Current source is not fixed by this docs update.

The accepted Chợ Nhạc incident is a direct-workspace preserve/no-op, not data
removal. #474 does not require restarting/replanning this accepted successor.
Do not generalize that safety conclusion to isolated-workspace cleanup. The
issue still requires a bounded implementation and real-shaped regressions.

## Active DDEV direct-workspace recovery — PCP #493

Chợ Nhạc AP-MVP-02 exposed a deterministic DDEV bootstrap failure after the
planner recovered successfully. The preserved direct workspace remained clean
and its existing Chợ Nhạc web/database containers remained healthy, but every
Runtime verification phase unconditionally ran `ddev start -y` first.

Bounded diagnosis ruled out project Dockerfile/build-context correctness and
current registry metadata resolution. The dedicated `pcp-builder`
(`docker-container`) can build both project targets from cache, but PostgreSQL
local-image export stalls in the `type=docker` tar-transfer path. The default
Docker builder can export, tag and unpack both images but the multi-target build
still fails to return before the bounded timeout. `DOCKER_BUILDKIT=0` also
timed out and is not an accepted fallback. Do not increase timeouts, prune
builders/images, replace the preserved AP-MVP-02 job, or bypass Runtime state.

Repair branch `ai/493-reuse-running-direct-ddev` scopes a safer direct-workspace
path behind `ddev.reuse_running_direct_ddev`. When enabled, a non-frontend
phase may reuse an already-running direct DDEV project only when the tracked
`.ddev` configuration has no uncommitted changes and `ddev exec true`
succeeds within a short readiness bound. A failed readiness probe or dirty
`.ddev` tree falls back to the existing fail-closed `ddev start -y` path.
`frontend_quality` still forces startup/reconciliation because it may write a
managed DDEV Node override. Chợ Nhạc preflight no longer duplicates
`ddev start -y` as a configured command because infrastructure startup/reuse is
owned by the executor phase wrapper.

This recovery does not relax isolated-workspace resume semantics and does not
remove the dedicated PCP builder from Router/Runtime/ddev-executor platform
image builds. CI and zero-active-work rollout evidence are required before
resuming the exact AP-MVP-02 job.

## PM-handoff verification-only recovery — PCP #495

AP-MVP-02 exposed a contract mismatch after a bounded collaboration exhausted
its two rounds and handed an unresolved design question to PM. The execution
prompt correctly tells a resumed developer not to invent a repository edit when
PM has resolved the decision and no code-side repair remains, but the ordinary
per-invocation material-change guard still treated that safe no-effect turn as a
failure.

The repair is explicit and single-use rather than a global relaxation. A caller
must set `verification_only_after_pm_handoff=true` on the existing blocked job.
Runtime accepts it only for a durable `pm_handoff` collaboration context bound
to the exact thread and round, forbids provider reset/reroute in the same
request, and arms one verification-only turn. That marker is consumed on the
next executor turn whether or not the developer changes files. All ordinary
no-effect turns remain fail-closed.

This recovery preserves the same job, workspace, route, cumulative diff and
usage counters. It does not reopen collaboration, reset budget telemetry or
authorize a new product/design decision. The owner/PM must resolve the actual
handoff decision outside Runtime before using the flag.

## Orchestrated stable-job quiesce classification — PCP #474

A historical Chợ Nhạc lease-retirement audit exposed that
`_quiesce_stable_manual_job()` classified orchestration using a nonexistent
top-level `cp_jobs.work_order_id` field. Persisted orchestration identity is
owned by the durable `checkpoint.orchestrator_launch` reservation.

The bounded repair uses the existing validated `orchestrator_launch(job)`
predicate before any manual workspace quiesce. A genuinely orchestrated stable
job is left to PlanOrchestrator resource handling, while standalone/manual jobs
— including a standalone WorkOrder that has `checkpoint.work_order` but no
orchestrator launch reservation — retain existing quiesce behavior.

Regression coverage uses a Storage-shaped row with WorkOrder identity only
inside the checkpoint plus the canonical launch marker; no top-level
`work_order_id` test-only field remains.

## Chợ Nhạc visual-runtime prerequisite — PCP #498

AP-MVP-02 reached the Runtime-owned `visual_quality` phase and the locked
Playwright Chromium executable failed to launch because the active DDEV web
container was missing `libnspr4.so`. The existing `frontend_quality` phase
already uses the repository-local Playwright CLI as root to install Chromium OS
dependencies, but that installation is imperative container state and is not a
durable guarantee for a later visual phase after container/image recreation.

The bounded repair makes `visual_quality` self-contained: immediately before
`npm run test:visual`, Runtime executes the same local
`npx playwright install-deps chromium` command as root inside the active DDEV
web container. This intentionally does not reintroduce a hard-coded
`webimage_extra_packages` list in the application repository and does not
change application code or Playwright versions.

The visual test remains the second command in the phase, so dependency
provisioning must succeed before capture begins. Ordinary DDEV/Runtime phase
timeouts and fail-closed command handling remain unchanged.

## Flash High fixed-effort compatibility — PCP #500

AP-MVP-02 completed deterministic verification and then exposed a model-registry
mismatch in the evaluator. PCP selected logical model
`antigravity_flash_high`, upstream `gemini-3.8-flash-high`, with persisted
`reasoning_effort=medium`. The Antigravity CLI rejected the invocation because
the explicit model preset already encodes the effort level and conflicts with
`--effort=medium`.

The bounded repair follows the same compatibility pattern already used for
`gemini-3.8-flash-medium`:

- `antigravity_flash_high` declares `supports_reasoning_effort: false`;
- historical `low/medium/high` values remain accepted as
  `legacy_ignored_reasoning_efforts` so durable routes can resume;
- fresh Router choices omit explicit effort;
- Runtime's Antigravity adapter omits the effort payload even when a preserved
  pre-fix evaluator choice still carries one;
- registry version advances to 13 and Runtime advances to 1.0.113.

This correction does not change the upstream model, model role, quota group,
provider routing priority or AP-MVP-02 source/workspace. It does not generalize
the same rule to `gemini-3.1-pro-high` without direct compatibility evidence.

Because this incident occurred only after deterministic verification had
already passed, the existing explicit PM-handoff verification-only recovery may
also be armed for `evaluator_provider_failure_without_fallback` when the
checkpoint proves `last_verification_summary.passed=true` and retains an exact
durable evaluator choice. This avoids inventing an application edit or rerouting
the WorkOrder merely to retry an evaluator after a platform capability repair.

## Provider success rehabilitation + PM staffing recovery — PCP #502

AP-MVP-02 exposed a durable health-state contradiction after the evaluator
successfully completed on Google Antigravity. The checkpoint still retained a
provider-wide `provider:google_antigravity=unavailable` marker from an older
pre-fix evaluator failure. PM reassessment forwarded that stale state to Router
staffing, leaving no eligible Product Manager candidate and producing HTTP 422
from `/v1/staff`.

Runtime now treats a successful planner/executor/evaluator invocation as
authoritative evidence only for the exact provider/model that just succeeded:

- remove a stale `provider:<provider>` marker for that provider;
- remove a stale model-id health marker for that exact model;
- preserve unrelated quota-group markers and unrelated model/provider failures;
- retain a bounded rehabilitation audit in the checkpoint.

For an already-blocked `pm_reassessment_failed` job, the existing explicit
verification-only PM-handoff recovery is extended only when all of these are
durably true:

- deterministic verification passed;
- independent review passed with a valid protocol;
- the blocked result retains the exact diff hash;
- the failure is an HTTP 422 from Router `/v1/staff`;
- PM-handoff collaboration context is still exact;
- review history identifies the successful reviewer provider/model;
- a stale health marker contradicted by that successful review is actually
  present.

That recovery removes only the contradicted provider/model marker. It does not
use the broad transient-provider reset and therefore does not clear unrelated
quota state.

To reduce repeated model work, the prior independent-review PASS may be reused
once when the resumed run produces the same exact diff hash and deterministic
verification passes again. Any diff change, verification failure, prior-review
failure or invalid review protocol disables reuse and returns to ordinary
review behavior.

Runtime version: `1.0.114`.

## Semantic dependency protected signals — PCP #504

AP-MVP-02 exposed a false protected boundary after Runtime correctly reached
deterministic verification and independent review PASS. The current diff still
touches `frontend/package.json`, but only to change `test:browser` and
`test:visual` script commands. No dependency declaration changes. Historical
scope-guard behavior classified every dependency-manifest path as
`major_dependency_addition`, so this script-only edit incorrectly forced the
same Human/PM dependency gate as a real package addition.

Runtime diff evidence now records `dependency_manifest_changes` against the
exact persisted source commit:

- `package.json`, `composer.json`, `pyproject.toml`, and `Cargo.toml`
  are compared semantically on their dependency surfaces;
- unrelated script/metadata changes in those structured manifests do not create
  `major_dependency_addition`;
- actual dependency additions/removals/version changes still do;
- lockfiles, requirements files, Pipfile/Gemfile, Docker/Compose and
  Helm/Kubernetes dependency surfaces remain fail-closed on any change;
- missing semantic evidence on legacy/durable results remains fail-closed.

Runtime execution and PM merge eligibility consume the same durable semantic
evidence, so a protected signal cannot disappear between execution and merge
without an exact diff change.

Runtime version: `1.0.115`.

## PM merge authority follows protected decisions, not risk labels — PCP #506

AP-MVP-02 completed every deterministic, independent-review and exact-head CI
gate with no unresolved protected signal, but still entered manual merge because
the merge evaluator treated every WorkOrder above `standard` risk as a Human
Owner decision. That contradicted the operating contract: risk level determines
routing/profile/verification rigor, while Human Owner involvement is reserved
for unresolved protected decisions.

The merge policy now separates those concerns:

- `autonomy.allow_pm_merge` is the explicit project-level PM merge authority;
- legacy `allow_auto_merge_low_risk` remains a backward-compatible fallback
  when the new key is absent;
- Chợ Nhạc explicitly sets `allow_pm_merge: true`;
- `high` and `critical` risk levels remain durable merge evidence but do not,
  by themselves, create a Human Owner merge blocker;
- unresolved plan/job decisions, protected signals without matching durable
  approval, PM protected-decision evidence, verification/review/CI failures,
  PR/head/base mismatches and project merge opt-out remain fail-closed;
- production deployment authority is unchanged.

This allows a high/critical WorkOrder whose stricter engineering gates are all
green and whose protected decisions are already resolved to complete through
PM-controlled merge without an avoidable owner loop.

Runtime version: `1.0.116`.

## Standing execution / quality boundaries

- Normal flow: bounded issue/WorkOrder -> implementation/evidence -> deterministic
  checks and required review -> exact-head CI -> PM review -> eligible PM merge.
- Developers never merge; force push and production deployment remain forbidden.
- Human Owner retains protected scope/architecture/security/destructive-data/
  production/governance/material-resource decisions. CI alone is not approval.
- Preserve durable history, counters, anomaly circuit breakers and adaptive
  healthy-progress behavior. Never use SQL/state rewrites, reset, clean, stash,
  quota overrides or endless retries to remove an operational gate.
- Never restart/rebuild while engineering work is active. No broad Docker/image/
  volume prune. Routine in-frame work should not create avoidable owner loops.
- Trusted-local Chợ Nhạc execution remains scoped to direct workspace plus
  antigravity_host execute/repair. Plan/evaluate, Codex/OpenCode, Docker/sudo,
  remote/destructive Git, merge and deploy do not gain authority by this handoff.
- Runtime owns preview/visual evidence. Visual quality follows frontend quality,
  exact lease and 1..4 renderable local routes. Screenshot capture alone is not
  multimodal/pixel review; image_reviewed=false forbids aesthetic claims.
- Current changed-module Drupal verification covers Unit/Kernel/Functional;
  CI, supported phases, authority rules and anti-loop behavior are not weakened.
- Helper tests must exercise real-shaped collector -> gate -> failure reporting,
  missing fields, false-vs-zero, timeout/partial outcomes and refusal-before-write.

Completed platform chronology belongs in T3 and GitHub, not active blockers.
Relevant completed references include #146, #387/#388, #389/#391/#393/#395/#397,
#399, #400 (Chợ Nhạc #64 / DEC-034), #401/#402, #404/#405, #406/#436,
#421/#437 (Chợ Nhạc #65/#66), #426/#427, #430/#431, #432/#433, #434/#435,
#438/#439, #440/#442, #441/#443, #446/#447, #451/#452, #453/#454,
#455/#456, #457/#458, #459, #461/#462, #463/#464 and #466/#468.
Failed/non-orchestrated planning attempts and the original intake attempt marker
remain evidence; `usage=null` never proves a model call did not occur.
