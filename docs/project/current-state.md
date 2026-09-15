# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. Durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-15

## How to resume in a new chat or agent session

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/project/README.md`;
3. this file;
4. topical documents referenced by the active work, especially `efficiency-model.md` for the current platform-improvement initiative;
5. the active GitHub issue/PR and current branch diff before editing.

Do not rely on chat history as authoritative project state. Repository docs and current executable evidence win according to the authority order in `AGENTS.md`.

## Mandatory continuity rule

Before a material task is complete or handed off, update the relevant topical document for durable decisions and this file for mutable execution state. Replace stale state instead of appending raw chronological history; Git history is the audit trail.

## Current platform baseline

The currently relevant merged platform state is:

- PM routine in-scope PR review/merge authority is approved by issue #96 / PR #97; developer agents still cannot merge and production deployment remains separately Human Owner-controlled.
- Runtime source is `1.0.38` after PR #137 (`Recover provider-blocked jobs with multiple exhausted budgets`).
- Router source is `1.0.16`; routing/model policy is v8.
- Antigravity host bridge is `1.10` after PR #135 and live verification proved safety settings survive proactive quota probes.
- Provider quota telemetry/proactive refresh is implemented through PRs #129/#131 plus follow-up safety fixes.
- Live Developer Activity is implemented across supported providers and Runtime-native phases.
- PR #139 (`Document Telegram terminal operations gateway`) is merged at `9683250a7669b47e9d81f6df648bb769ca5e3893`; the terminal gateway remains an approved target, not implemented.
- Issue #98 (`Implement constrained PM-controlled PR merge in Runtime`) remains open and is still required for full executable alignment with the approved PM merge governance.

## Active `chonhac` DEC-025C state

GitHub ticket: `chonhac` GH-5.

Orchestration identity:

- plan: `pm-gh-5650852312`;
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`;
- job: `eec59b13651c54559c10ce204380a68e`;
- branch: `ai/eec59b13651c`;
- workspace: `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`.

The same job/workspace has been preserved across recovery. The successful Runtime 1.0.38 owner action `7Xgt2C_4GrhIIYEeAFfG5fEc` atomically extended:

- `max_wall_time_minutes`: `90 -> 110`;
- `max_iterations`: `12 -> 14`;

and rerouted the same job while preserving failed-provider state.

C1 then progressed through verification into reassessment and is currently stably blocked with:

- job status: `blocked`;
- result reason: `reassessment_stopped`;
- reassessment action: `stop`;
- reassessment reason: `repair budget exhausted`;
- signal: `hard_budget_guard`.

Latest observed counters:

- model calls: `21 / 22`;
- tool calls: `65 / 160`;
- test runs: `14 / 14`;
- wall time: `93.168 / 110` minutes;
- repair iterations: `4 / 4`.

Fresh exact recovery action materialized for the current state:

- action id: `abXzvyU2pvALZ5YpovNveDcr`;
- type: `budget_extend`;
- payload: `max_repair_iterations +1`;
- status at last inspection: pending/valid.

Older provider-recovery controls may still exist in storage but belong to older state generations and must not be used in place of the fresh current-state action.

C2/C3 remain gated behind C1 completion. No manual DB/job mutation, counter reset, job replacement, or generic `/v1/jobs/{job_id}/run` bypass is allowed.

## Efficiency initiative — active platform priority

On 2026-09-15 the Human Owner approved a platform-wide efficiency direction whose goal is higher throughput/quality while keeping resource usage at personal scale and minimizing routine Human Owner attention.

Authoritative policy/design: `docs/project/efficiency-model.md`.

GitHub tracking:

- #146 — umbrella efficiency initiative;
- #147 — Phase A: task-specific adaptive budgets and Human-attention circuit breakers;
- #148 — Phase B: layered verification and failure-budget separation;
- #149 — Phase C: bounded inter-agent collaboration and review dialogue;
- #150 — Phase D: risk-proportionate review and role-specific evidence packs;
- #151 — Phase E: telemetry calibration, Human-attention metrics, and continuity automation;
- #98 — constrained PM-controlled merge remains part of the low-touch delivery target.

Approved execution priority:

1. #147 adaptive budgeting first because current profile-fixed hard stops are creating avoidable owner interruptions on healthy work;
2. #148 layered verification/failure accounting;
3. #149 bounded collaboration after budget semantics can absorb normal teamwork without new approval loops;
4. #150 risk-proportionate review/context compaction;
5. #151 telemetry calibration/continuity automation;
6. complete #98 as part of removing the remaining routine end-of-task human checkpoint.

Telegram terminal convenience work is lower priority than this execution-efficiency initiative unless an operational need changes the ordering.

## Durable efficiency policy now approved

- Profile remains a staffing/risk signal, but fixed profile counters should not be the only task resource estimate.
- Budget semantics target three layers: expected estimate, autonomous healthy working envelope, deterministic emergency hard ceiling.
- Reaching an estimate/working target alone must not stop a healthy execution or require Human Owner approval.
- Provider quota/resource exhaustion is separate from task-budget estimation.
- Anti-loop/no-progress/oscillation/scope/cost/quota/emergency-ceiling signals are the primary circuit breakers.
- Final deterministic verification remains mandatory, but iteration should use targeted/focused checks before expensive full-suite checkpoints.
- Engineering repair accounting must be separated from provider, infrastructure, verification and delivery retries.
- Inter-agent collaboration is bounded: one primary writer by default, read-only consultants/reviewers, Router-selected logical roles, compact evidence packs, normally 1-2 rounds, no recursive swarm.
- Review strength is risk-proportionate and should be calibrated using useful-finding telemetry.
- Human Owner attention is a first-class resource; routine targets are `human_interventions_per_task -> 0` and `avoidable_blocks_per_task -> 0`.

## Telegram terminal operations target

Authoritative topical document: `docs/project/telegram-terminal-operations.md`.

Durable interaction convention:

- ChatGPT continues to provide ordinary terminal-safe read-only blocks by default.
- Telegram-specific read-only formatting is emitted only when the Human Owner explicitly requests a Telegram-ready block.
- The future terminal bot is separate from the existing PCP Telegram governance/notification bot.
- `/run-ro` must use capability-restricted read-only execution; `/run-op` is a later named/confirmed operation layer; generic `/run-admin` stays disabled by default.

## Global operational gates

- Normal implementation flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> PM merge when eligible.
- Never force push.
- Developer agents never merge and never receive GitHub merge credentials.
- Human Owner remains final authority over protected decisions in the Constitution.
- Production deployment is not implied by PR merge.
- Do not restart/rebuild Runtime/DDEV/n8n while a job is active. A stable blocked/terminal state is required for an approved local rollout.
- Runtime durable state is authoritative; never edit DB/job state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must not enter developer prompts or repository docs.
- Avoiding human approval prompts is not permission to weaken sandbox, credential, Docker, source-repository, or production boundaries.

## Immediate next safe actions

Platform development:

1. merge the documentation update for #146 after exact-head CI is green;
2. implement #147 as the first code phase on its own `ai/*` branch/PR with backward-compatible persisted-job semantics;
3. do not roll out Router/Runtime locally while any engineering job is active; use the current stable-blocked C1 state only if/when a targeted rollout is explicitly required and revalidate the same job before/after rollout.

DEC-025C:

- the fresh `max_repair_iterations +1` action remains the current normal recovery path if the Human Owner chooses to continue C1 under the existing Runtime 1.0.38 semantics;
- the new adaptive-budget policy is a future platform behavior and must not be simulated by manually altering C1 counters/state.
