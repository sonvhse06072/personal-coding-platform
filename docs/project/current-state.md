# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. Durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-15

## How to resume in a new chat or agent session

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/project/README.md`;
3. this file;
4. topical documents referenced by the active work, especially `efficiency-model.md`;
5. the active GitHub issue/PR and current branch diff before editing.

Repository docs and current executable evidence are authoritative over chat history according to `AGENTS.md`.

## Current platform baseline

- PM routine in-scope PR review/merge authority is approved by issue #96 / PR #97; Developer agents still cannot merge and production deployment remains Human Owner-controlled.
- Phase A #147 merged through PR #154: adaptive task budgets with emergency ceilings.
- Phase B #148 merged through PR #156: layered verification and separated retry/failure accounting.
- Phase C #149 merged through PR #157 at `754233a17572b4631f418dfbab1c667790dc7fc5`: bounded single-writer collaboration with compact durable artifacts.
- Phase D #150 merged through PR #158 at `8eca5469f1a884511e0cf36cb9b6b51e0602a7bf` after exact-head CI run #300 passed Router, Runtime, DDEV executor and structure-tests. Merged source versions are Runtime `1.0.42`, Router `1.0.20`, routing policy v11.
- Phase D provides policy-driven risk-proportionate review, compact role evidence packs, read-only JIT repository retrieval, structured `ReviewReport`, review resource telemetry and useful-finding attribution.
- PR #155 keeps the healthy routine Standard OpenRouter preference. A second OpenRouter model remains out of scope until provider/tool-use evidence supports activation.
- Antigravity host bridge remains `1.10`.
- Issue #98 constrained PM-controlled merge remains open and is still required before PCP can claim a routine zero-human-touch happy path.
- PR #139 documents the separate Telegram terminal gateway target; it remains lower priority and unimplemented.

## Efficiency initiative

Authoritative policy/design: `docs/project/efficiency-model.md`.

Tracking:

- #146 umbrella initiative;
- #147 Phase A — complete/merged;
- #148 Phase B — complete/merged;
- #149 Phase C — complete/merged;
- #150 Phase D — complete/merged;
- #151 Phase E telemetry calibration, Human-attention metrics and continuity automation — active now;
- #98 constrained PM-controlled merge — next low-touch delivery dependency after Phase E unless evidence changes priority.

## Active Phase E / issue #151 state

Branch: `ai/telemetry-continuity-151`, created from the exact Phase D merge commit `8eca5469f1a884511e0cf36cb9b6b51e0602a7bf`.

Target source/policy versions on this branch:

- Coding Runtime `1.0.43`;
- Router `1.0.21`;
- routing policy v12.

Current branch implementation:

- Runtime derives one compact telemetry snapshot per job containing project/task class/logical role/provider/model, estimate-vs-actual resources, first-pass success, engineering repairs, layered verification counts/retries, CI result, review findings/useful yield, model/tool/token/wall/cost use, provider/quota failures, retry categories and final TaskOutcome;
- stable blocked/waiting states are observable but only terminal job snapshots participate in historical calibration; resumed jobs update the same row rather than becoming duplicate samples;
- PostgreSQL persistence adds `cp_task_telemetry`, `cp_attention_events` and `cp_continuity_proposals` without adding another service;
- Human Owner attention distinguishes protected decision-boundary interventions from routine operational interventions, tracks avoidable legacy budget-continuation blocks and records owner wait time;
- sparse historical samples fall back to existing policy defaults; after the configured minimum sample size, simple bounded observed resource ratios may refine task estimates and per-model observed success may feed the existing Router `predicted_success` signal;
- Router remains authoritative for whether calibration is usable and clamps observed multipliers; telemetry cannot expand adaptive emergency hard maxima or protected decision policy;
- telemetry read failure is advisory/fail-soft and falls back to ordinary deterministic Router policy instead of causing a routing outage;
- continuity triggers produce compact proposals after terminal/stable-blocked/governance transitions, and authenticated external `pr_merged`/`rollout`/`governance_decision` events can create the same proposal shape;
- continuity code can replace only the explicit managed section of `docs/project/current-state.md`; direct durable architecture/policy rewrites are denied and applying a proposal still uses the normal Git branch/PR authority path;
- Runtime exposes bounded authenticated telemetry calibration/attention and continuity-proposal endpoints for PM/operator evidence consumption.

Regression coverage added on the branch includes telemetry snapshot/aggregation, budget-without-useful-outcome evidence, attention classification, persistence triggers, sparse-sample fallback, bounded Router calibration, telemetry-to-Router model-success feedback, telemetry-store failure fallback, continuity compaction and durable-document authority rejection.

No local Runtime/Router/DDEV/n8n rollout has been performed for Phase E. Merge must not be treated as permission to restart active local services.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `phase_e_implementation_active`.
- Project/job: `personal-coding-platform` / `n/a`.
- Runtime state: `development`; outcome: `pending_pr_ci`.
- WorkOrder: `GH-151`; branch: `ai/telemetry-continuity-151`.
- Human attention: interventions `0`, avoidable `0`, owner wait `0.0` seconds.
- Execution evidence: first-pass `n/a`, repairs `n/a`, provider failures `n/a`, quota failures `n/a`.
- This section is mutable execution state only. Durable architecture/policy changes still require their normal reviewed Git path.
<!-- PCP:CONTINUITY:END -->

## Active `chonhac` DEC-025C state

GitHub ticket: `chonhac` GH-5.

Preserved orchestration identity:

- plan: `pm-gh-5650852312`;
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`;
- job: `eec59b13651c54559c10ce204380a68e`;
- branch: `ai/eec59b13651c`;
- workspace: `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`.

The same job/workspace remains stably blocked under the currently deployed pre-adaptive Runtime semantics:

- reason: `reassessment_stopped` / `repair budget exhausted` / `hard_budget_guard`;
- model calls `21 / 22`;
- tool calls `65 / 160`;
- test runs `14 / 14`;
- wall time `93.168 / 110` minutes;
- repair iterations `4 / 4`.

Latest recorded recovery action:

- action id `abXzvyU2pvALZ5YpovNveDcr`;
- `budget_extend` for `max_repair_iterations +1`;
- last recorded status pending/valid.

C2/C3 remain gated behind C1. Do not manually mutate DB/job state, reset counters, replace the job, or simulate newer adaptive/layered/collaboration/review/telemetry semantics inside this preserved job.

## Durable efficiency policy already approved

- Profile is a staffing/risk signal; task resource estimates are task-specific where evidence supports them.
- Estimate and working targets are planning/reassessment signals; emergency hard ceilings remain circuit breakers.
- Provider quota is separate from task-budget estimation.
- Full required deterministic verification and CI remain mandatory.
- Engineering repair accounting remains separate from provider/infrastructure/verification/delivery retries.
- Collaboration remains bounded and single-writer by default.
- Review remains risk-proportionate; stronger/scarce models are used where evidence/risk justifies them.
- Historical telemetry may calibrate heuristics only after meaningful sample sizes and must fall back to policy priors when samples are sparse.
- Human attention is a first-class resource; routine targets remain `human_interventions_per_task -> 0` and `avoidable_blocks_per_task -> 0`.
- Continuity automation updates mutable execution state compactly and cannot silently amend higher-authority project documents.

## Global operational gates

- Normal implementation flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> PM merge when eligible.
- Never force push.
- Developer agents never merge and never receive GitHub merge credentials.
- Human Owner retains final authority over Constitution-protected decisions.
- Production deployment is not implied by PR merge.
- Do not restart/rebuild Runtime/DDEV/n8n while a job is active; require a stable blocked/terminal state for an explicitly chosen local rollout.
- Runtime durable state is authoritative; never edit DB/job state manually to bypass the state machine.
- Provider/control-plane credentials remain service-scoped and must not enter Developer prompts or repository docs.

## Immediate next safe actions

Platform development:

1. open the Phase E PR from `ai/telemetry-continuity-151` and run exact-head deterministic CI;
2. fix any Runtime/Router/structure compatibility failures on the same branch and re-run exact-head CI;
3. review telemetry/attention/continuity authority boundaries plus unresolved Human Owner triggers before merge;
4. merge Phase E only when exact-head CI and review gates are green;
5. do not roll out Runtime `1.0.43` / Router `1.0.21` locally merely because the PR merges; respect the preserved active-job/restart gate;
6. after Phase E, continue #98 unless new evidence changes priority.

DEC-025C:

- the recorded `max_repair_iterations +1` action remains the normal recovery path only if the Human Owner chooses to continue C1 under currently deployed semantics;
- Phase E telemetry/calibration behavior must not be backported by manual state manipulation.
