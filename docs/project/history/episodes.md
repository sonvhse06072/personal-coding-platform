# PCP Episodic Memory Index

Status: Tier-3 historical index under #313/#314.

This file is intentionally compact. It records reusable lessons and authoritative references for completed incidents/rollouts without turning `current-state.md` into an append-only history.

Detailed chronology remains in Git history, GitHub issues/PRs, Runtime durable state and CI.

## 2026-09 — execution-efficiency and recovery

### Healthy-progress executable alignment — #224 / PR #226

Outcome: merged and live-proven.

Durable lesson:
- healthy work may adopt adaptive headroom without replacing the durable job/workspace or resetting consumed counters;
- static budget thresholds alone are not Human Owner gates.

Evidence:
- issue #224;
- PR #226;
- final source CI #401;
- preserved DEC-025C-r2 live proof.

Status: historical implementation evidence; policy remains current in `efficiency-model.md`.

### Autonomous provider recovery — #228 / PR #229

Outcome: merged and locally activated.

Durable lesson:
- provider/model/quota failures should fall through autonomously while another eligible route remains;
- failed capacity must remain durable so routing cannot loop back to already-proven-bad capacity;
- provider-failover counts are telemetry/reassessment inputs, not standalone owner gates.

Evidence:
- issue #228;
- PR #229;
- merge `bd24f18a0983ed370681f253edeb0606cf9e80cf`;
- exact-head CI #408.

Status: historical rollout; current policy lives in T2.

### Retired Chợ Nhạc DEC-025C orchestration

Outcome: PCP orchestration retired by Human Owner; durable history preserved.

Historical identity:
- plan `pm-gh-5650852312`;
- WorkOrder `DEC-025C-1-recovery-tooling-r2`;
- job `eec59b13651c54559c10ce204380a68e`;
- branch `ai/eec59b13651c`.

Durable lesson:
- do not revive a retired product WorkOrder merely because its historical job remains queryable;
- use supported Runtime cancellation/cleanup and retain durable audit records;
- historical product evidence must not masquerade as active work.

Status: retired/historical. The missing-workspace legacy cleanup compatibility gap discovered later is tracked in open issue #282.

## 2026-09 — Chợ Nhạc UI-CL-1 platform hardening

### WorkOrder protected-change false positive — #262 / PR #263

Outcome: fixed and activated.

Durable lesson:
- explicit WorkOrder risk flags are authoritative for plan-orchestrated protected-change hints;
- preservation/out-of-scope wording must not be misread as intended security/schema/API changes;
- legacy free-text routing may retain keyword inference separately.

Evidence:
- issue #262;
- PR #263;
- merge `427b930c44a91b1e262419d488aa8469298c80c1`.

Status: historical defect/lesson.

### Reviewer repair/rebuttal re-check — #284 / PR #285

Outcome: merged.

Durable lesson:
- reviewer re-check may consume only the bounded current developer repair/rebuttal report;
- WorkOrder and deterministic repository evidence remain authoritative;
- prior raw stdout/stderr must not grow reviewer context without bound.

Evidence:
- issue #284;
- PR #285;
- merge `836af29f3ee308e1ea5aab8a47194b2ada682331`.

Status: historical implementation evidence.

### Current-tail repeated-failure detection — #286 / PR #287

Outcome: merged.

Durable lesson:
- circuit breaking must evaluate the consecutive suffix matching the most recent durable failure fingerprint, not stale repetitions earlier in history;
- complete failure history remains audit evidence.

Evidence:
- issue #286;
- PR #287;
- merge `3075a4f588074a2206909360b56b20029003e335`.

Status: historical implementation evidence.

### GitHub Actions pre-run failure classification — #288 / PR #289

Outcome: merged.

Durable lesson:
- runner/startup failures that occur before repository execution are delivery infrastructure failures, not engineering repair evidence;
- accepted source identity must survive delivery retry;
- legacy recovery must reconstruct accepted delivery state only from authoritative PCP-owned durable evidence.

Evidence:
- issue #288;
- PR #289;
- merge `2174a1efd595aa79f6a750fc3d5cba150e7db737`.

Status: historical implementation evidence.

### Trusted exact-SHA CI revalidation — #291 / PR #292

Outcome: completed after the historical current-state snapshot.

Durable lesson:
- CI recovery must bind evidence to the exact requested commit SHA;
- trusted commit status needs exact repository/run/publisher identity and must fail closed on ambiguous/missing metadata.

Evidence:
- issue #291;
- PR #292;
- GitHub/CI history is authoritative for final merge identity.

Status: historical implementation evidence.

### Owner-attention generation and supersession — #293 / PR #294

Outcome: merged.

Durable lesson:
- polling/no-op timestamps must not create fresh Human Owner attention generations;
- obsolete pending owner attention/control actions should become superseded/cancelled while sent/executed audit history remains immutable.

Evidence:
- issue #293;
- PR #294;
- merge `a08e2bd58e2ea2f00b1ee8701031f9fb74d55d6a`.

Status: historical implementation evidence.

### Explicit superseded orchestration lifecycle — #295 / PR #296

Outcome: completed after the historical current-state snapshot.

Durable lesson:
- supersession is an explicit lifecycle operation bound to exact identities; it is never inferred from timestamps, later success or prose;
- superseded orchestration remains queryable as history but is excluded from new execution/owner-attention eligibility.

Evidence:
- issue #295;
- PR #296;
- GitHub/Runtime history is authoritative for final merge/activation identity.

Status: historical implementation evidence.

## 2026-09 — resource hygiene

### Dedicated PCP BuildKit isolation — #281 / PR #283

Outcome: source merged, locally activated and live accepted; #281 and parent #277 later closed as stale-open completed issues.

Durable lesson:
- PCP custom-service and executor-owned workspace builds use a dedicated `pcp-builder` cache namespace without changing the user's globally selected builder;
- destructive cleanup must use authoritative zero-active-work gates and exact PCP ownership;
- shared/default BuildKit cache must never be pruned merely because PCP has its own GC path.

Evidence:
- issue #281;
- PR #283;
- merge `f858d4b1323a5803e818c1e2b1ae61254458e145`;
- local activation/disk evidence in Git history and issue comments.

Status: historical rollout. Legacy terminal cleanup without an existing workspace remains a separate open compatibility issue #282.

### Missing-workspace terminal DDEV cleanup — #282 / PR #320

Outcome: implemented, deployed and live accepted with a disposable `pcp-validation-fixture` Runtime job.

Durable lesson:
- normal workspace-present cleanup remains the preferred lifecycle path;
- when a terminal `completed/cancelled` isolated job has already lost its Git workspace, cleanup may derive only the exact deterministic `cp-<10-hex-job-prefix>` identity after proving the 10-hex prefix maps uniquely back to the full durable Runtime job/project;
- orphan cleanup must inspect first, revalidate immediately before mutation, refuse active/running/foreign-referenced resources, and remove only exact stopped containers, exact project-prefixed volumes and exact PCP-built image refs;
- repeated cleanup is idempotent;
- `blocked`, `failed`, `waiting_human` and nonterminal work remain preserved by default;
- acceptance fixtures must use the configured `CODING_WORKSPACES_ROOT` and supported Runtime lifecycle rather than hard-coded workspace roots or direct durable-state edits.

Evidence:
- issue #282;
- PR #320 exact head `a3a29e447fa1ef5efa1feb45081d9e85d5cc7d19`;
- exact-head CI #641 passed all four required jobs;
- merge `9a477d15c0a51054779a41f40b24230aa230484d`;
- deployed Runtime `1.0.56`;
- deployed ddev-executor `1.0.24`;
- final live acceptance v2 passed: supported Runtime job creation/cancel, deliberate exact missing workspace, orphan inspect, exact resource release, unrelated-resource preservation, idempotent second cleanup, terminal state preservation and final zero-work invariants.

Status: historical rollout; bounded missing-workspace cleanup remains current capability.


## 2026-09 — direct workspace and preview

### Chợ Nhạc direct workspace + job-owned live preview — #297

Outcome: locally accepted and closed.

Durable lesson:
- direct mode requires an exclusive project lease and exact registered workspace;
- Dashboard mutation uses a separate control boundary;
- preview transport resets must reconcile durable state rather than treating a dropped HTTP connection as proof of failure;
- frontend health must avoid nested shell reconstruction through DDEV; raw argv execution with Python-owned retries is the accepted approach;
- terminal job-owned preview retirement must precede lease release.

Primary evidence:
- #298 / PR #300;
- #299 / PR #301;
- corrective PRs #304, #306 and #307;
- implementation merge through `56e5abe52c6129b5c198c661bfef95242c7dd8c4`;
- final rollout documentation PR #308.

Status: historical rollout; capability remains current.

### Project-level Current site preview — #309

Outcome: locally accepted and closed.

Durable lesson:
- idle project preview is not an engineering job and does not hold the engineering lease;
- when a direct job starts, it first acquires the normal lease, retires idle preview, then prepares/switches the direct workspace;
- terminal direct-job cleanup must return the exact clean job-owned branch to the existing local base branch before lease release;
- dirty or externally changed source fails closed and keeps the lease rather than resetting/stashing/cleaning Human Owner work.

Primary evidence:
- PR #310 — project-level Current site;
- PR #311 — safe terminal return-to-base lifecycle;
- PR #312 — rollout documentation;
- implementation merge `add228f7258887390651686aa711529eaf6c0d3b`;
- documentation merge `d2dc61e7d34082bb88925639c3ee8129b8f30056`.

Last accepted local outcome:
- zero active engineering jobs;
- zero Chợ Nhạc engineering lease;
- Chợ Nhạc clean on `main`;
- Current site Frontend Ready at `https://chonhac.ddev.site:3100`.

Status: historical rollout; capability remains current.

## 2026-09 — tiered context and memory

### PCP Tiered Context & Memory Architecture — #313 / #314 / #317

Outcome: implemented and accepted without introducing vector infrastructure.

Durable lesson:
- the main documentation risk was stale/current information mixing, not corpus size alone;
- T0 governance and T1 current state should be pinned, while T2 semantic knowledge and T3 history are retrieved only when relevant;
- current state must be replace-in-place rather than an append-only rollout log;
- deterministic exact-reference/role/heading-aware retrieval is sufficient for the current PCP corpus and should remain the baseline;
- vector/hybrid RAG is an optional optimization, not an architectural requirement, and must be justified by a measured retrieval gap.

Evidence:
- issue #313 — umbrella architecture;
- issue #314 / PR #315 — T1 compaction, T3 index and tier contract;
- PR #316 — Phase-1 continuity closeout;
- issue #317 / PR #318 — deterministic Context Composer and evaluation;
- #318 merge `58ef2e6a714088359dca3b65eaf257ad644390f1`;
- exact-head CI #637 passed all required jobs.

Accepted evaluation gates:
- required evidence target recall 1.0;
- stale historical false-positive rate 0.0 for current-state cases;
- authority-conflict failure rate 0.0;
- unsupported-memory abstention accuracy 1.0;
- mean composed context below 50% of read-all-docs baseline.

Status: historical architecture rollout; deterministic tiered retrieval remains current. Reconsider vector/hybrid RAG only after a future benchmark shows a material gap.

## 2026-10 — Chợ Nhạc GH-42 WO-01 platform-hardening episode

### Show-domain/API WorkOrder dogfood — GH-42 WO-01 / Chợ Nhạc PR #44

Outcome: product WorkOrder completed and merged; the preserved same job exposed
and drove a sequence of PCP control-plane/verification fixes while maintaining
the original workspace/diff/counters until delivery.

Product evidence:

- Chợ Nhạc WorkOrder: `GH-42-WO-01-show-domain-api`;
- preserved job: `579cdcd715bf5aba9f9ec26d7abca121`;
- product PR #44 exact final head:
  `afe8aa81340d66ce0b010103d8302a97f4f38441`;
- merge/main commit:
  `e8ccde0f9854fa86a9fa37fe9504fb63c90a477f`;
- final local evidence included PHPCS PASS, Unit 39/39 PASS, Kernel 75/75 PASS
  on PHP 8.3/PostgreSQL, full verification PASS and independent review PASS;
- exact-head GitHub CI passed before PM merge.

Durable lessons:

- preserve the same WorkOrder/job/workspace/diff/counters while diagnosing a
  platform blocker; replacement jobs hide the real state-machine defect;
- evaluator/PM prompts and strict output validators are one protocol and must be
  regression-tested together; an approval action cannot retain unresolved
  blocking risks merely because the model calls them caveats;
- coarse protected-path signals require semantic PM review, but a baseline-
  covered exact diff can be authorized only through a narrow exact-diff/
  baseline-bound mechanism rather than by weakening the protected gate;
- bounded collaboration must respect adaptive execution semantics, return
  resolved context to the same worker, permit an eligible round-2 recheck, stop
  at the configured round limit and preserve latest PM-handoff evidence;
- agent-sandbox capability failures such as missing PHP are not authoritative
  project-test failures when DDEV owns PHP verification; capability context
  should prevent impossible repeated tool attempts;
- authoritative verification must execute the actual required test class in the
  correct runtime. Drupal Kernel PHPUnit needs explicit test-database wiring
  when invoked directly;
- broad verification can create misleading unrelated failures. Prefer the
  narrow required target during iteration while keeping final project/CI gates
  proportionate to the WorkOrder;
- repeated deterministic verification failures must use a stable signature
  based on diff/phase/command/result rather than volatile stdout/stderr, or a
  single infrastructure/configuration defect can consume large test/model
  quota;
- when a live WorkOrder exposes many related platform failures, consolidate the
  reusable conclusion into one incident-learning review/episode and prefer
  executable prevention over prose-only memory.

Primary PCP evidence:

- #385 / PR #386 — PM reassessment output-contract mismatch;
- #387 / PR #388 — exact-diff baseline-covered protected authorization;
- #389 / PR #390 — adaptive collaboration budget semantics;
- #391 / PR #392 — same-worker collaboration continuation;
- #393 / PR #394 — bounded recheck after a resolved round;
- #395 / PR #396 — PM-handoff context preservation;
- #397 / PR #398 — legacy PM-handoff hydration;
- #401 / PR #402 — approval `unresolved_risks` prompt/validator alignment;
- #404 / PR #405 — focused Kernel DB wiring and stable deterministic
  verification anti-loop;
- #406 — Human Owner-approved incident-learning/PM-advisory direction.

Open follow-ups:

- #399 — advertise unavailable PHP runtime/capability to coding agents;
- #400 — remaining Chợ Nhạc repository-CI Kernel-verification alignment;
- #406 — implement deterministic incident candidate generation and bounded PM
  classification using existing TaskOutcome/continuity/tiered-memory paths.

Status: historical incident/lesson. Live GH-42 state belongs in T1 and Runtime;
open follow-ups remain current work, not proof that WO-01 itself is incomplete.

## 2026-10 — historical ExecutionPlan read compatibility

### Persisted audit snapshot versus current execution validator — #466 / PR #468

Outcome: source repair merged at
`6fcf5b79a35921ebd887736138b0279222e93224`; local activation evidence remains
a T1 concern.

Durable lesson:
- persisted plans are audit evidence and may legitimately predate stricter
  execution-time validation introduced later;
- read compatibility must not be implemented by weakening the executable
  `WorkOrder` validator or rewriting historical rows;
- a read/response model should remain a non-executable type, preserve historical
  values, and validate unrelated current invariants on an isolated copy;
- a snapshot that can be read must still fail when replayed through current
  planning/execution authority;
- field-level compatibility handling must not hide parent-level invariant
  failures such as self-dependency, duplicate acceptance IDs or contradictory
  scope.

Evidence:
- issue #466;
- PR #468;
- exact implementation head
  `66f9a38d2fe01762054cd6a1f1e6e3b0008cae1a`;
- required workflow run `37199654326` passed structure, Runtime, Router and
  ddev-executor tests before merge;
- owner diagnostic classified the original incident as
  `TEMPLATE_READ_REGRESSION_CONFIRMED_IN_PROCESS` without mutating the record.

Status: source implementation complete. Local Runtime rollout/acceptance and
time-sensitive orchestration state belong in T1 rather than this episode.

## 2026-10 — G0D-T01 reduced-path PCP/Direct coding outcome

### Model completion is not clean process or product acceptance — #595 / fixture #2

Outcome: one **code-valid paired Drupal output** (two independent GitHub-hosted CI/review PASS), **zero clean end-to-end pairs**; Direct original wrapper timeout preserved with read-only model/session and exact worktree forensic recovery.

Durable lesson:
- separate model terminal, code-quality acceptance, host wrapper exit, unattended delivery and product throughput;
- do not count a connector-delivered blob-equivalent PR as original Codex process exit/automated PCP delivery;
- G0 fixture-only Runtime bypasses normal PCP Planner/Router/Orchestrator/Verifier; representative product benchmark still pending and **G0 NOT GO**;
- preserve immutable original journals, benchmark seed refs and approved project boundaries; no silent model retries or extra operator framework.

Evidence: [T3 first paired outcome](g0-02-first-paired-outcome-2026-10-12.md), [PCP #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6116517408), fixture [PR #4](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/4) / [PR #5](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/5).

## 2026-10 — ordinary PCP lifecycle and PM critique

### Managed Agents critique and C843 review-binding lesson — #835 / PR845

Outcome: source-level critique recorded; C843 delivery reached PR/CI, finalization
remains a separate live checkpoint. Owner approved retaining this analysis.

Lessons: durable job identity does not require permanent worker identity;
existing event logs are not proof of replayability; criterion schemas need
evidence mapping; measure operator effort separately from Owner prompts.
A PM-created full-index diff hash mismatched Runtime's abbreviated diff hash.
Correct the review representation, never the retained proof to fit a review.

Sources: [analysis and bounded recommendations](2026-10-30-managed-agents-critique.md),
[execution and binding incident](2026-10-30-ordinary-c843-live.md).
Tags: recovery, acceptance, operator-attention, review-binding.
Status: T3 analysis/lesson; no new architecture, authority or benchmark claim.
Current finalization/review IDs belong in T1 and GitHub.

## Retrieval guidance

Use this file when the current task asks:

- why a current policy exists;
- whether a similar platform defect happened before;
- what lesson came from a prior rollout/incident;
- which issue/PR contains detailed evidence.

Do not use an episode as proof of current live state. For current state, consult T1 plus live Runtime/GitHub/source evidence.
