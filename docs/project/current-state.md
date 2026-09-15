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
- PR #154 (`Add adaptive task budgets with emergency ceilings`) merged Phase A / issue #147. Merged Runtime source is `1.0.39`, Router source is `1.0.17`, and routing policy v9 at that point.
- PR #155 (`Prefer OpenRouter for routine standard coding`) then merged on top of #154. Current merged Router source is `1.0.18` and routing/model policy is v10; current `main` is based at merge commit `3fe8050807026c8f8f669d93c7052605a72cc556` before the active Phase B PR.
- Antigravity host bridge remains `1.10`; provider quota telemetry/proactive refresh and live Developer Activity remain implemented.
- PR #139 (`Document Telegram terminal operations gateway`) is merged; the terminal gateway remains an approved target, not implemented.
- Issue #98 (`Implement constrained PM-controlled PR merge in Runtime`) remains open and is still required for full executable alignment with the approved PM merge governance.

## Efficiency initiative — active platform priority

Authoritative policy/design: `docs/project/efficiency-model.md`.

Tracking:

- #146 — umbrella efficiency initiative;
- #147 — Phase A adaptive task budgets: implemented and merged through PR #154;
- #148 — Phase B layered verification and failure-budget separation: active through PR #156;
- #149 — Phase C bounded inter-agent collaboration and review dialogue;
- #150 — Phase D risk-proportionate review and role-specific evidence packs;
- #151 — Phase E telemetry calibration, Human-attention metrics, and continuity automation;
- #98 — constrained PM-controlled merge remains part of the low-touch delivery target.

PR #155 also partially addresses #153 by preferring the existing OpenRouter coding model for healthy routine standard work while preserving privacy/quota/risk fallback behavior. A second OpenRouter model remains out of scope until current tool-use/provider-policy evidence supports activation.

Approved execution priority remains:

1. #147 adaptive budgeting — complete/merged;
2. #148 layered verification/failure accounting — active now;
3. #149 bounded collaboration;
4. #150 risk-proportionate review/context compaction;
5. #151 telemetry calibration/continuity automation;
6. complete #98 as part of removing the remaining routine end-of-task human checkpoint.

Telegram terminal convenience work remains lower priority unless an operational need changes the ordering.

## Active Phase B / issue #148 state

Branch: `ai/layered-verification-148`.

Pull request: #156 (`Add layered verification and retry attribution`), targeting `main`.

The branch is based directly on current `main` after PR #155 and targets Coding Runtime `1.0.40`.

Implemented behavior on the branch:

- WorkOrder verification can declare `intermediate_phases` separately from `required_phases`;
- persisted/legacy WorkOrders without `intermediate_phases` normalize to the historical verification path;
- intermediate checks stop later expensive checks for a known-bad repair candidate, while WorkOrder-required final verification remains mandatory for acceptance;
- fast/standard WorkOrders that require `full_tests` still receive that final gate through the existing governance facade;
- provider recovery, infrastructure retry, verification retry and delivery retry have separate counters/categories and do not consume engineering repair iterations merely for retrying infrastructure/provider/delivery work;
- an actual GitHub CI failure still counts as engineering repair because code repair is required;
- verification layers and retry categories emit Runtime activity for telemetry;
- regression coverage includes layered progression/final-gate behavior, legacy compatibility, provider recovery, preflight/infrastructure retry, verification retry and delivery retry attribution.

No local Router/Runtime/DDEV/n8n rollout has been performed for Phase B. PR/CI evidence must be green at the exact PR head before merge. A merge does not authorize a local service restart while an engineering job is active.

## Active `chonhac` DEC-025C state

GitHub ticket: `chonhac` GH-5.

Orchestration identity:

- plan: `pm-gh-5650852312`;
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`;
- job: `eec59b13651c54559c10ce204380a68e`;
- branch: `ai/eec59b13651c`;
- workspace: `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`.

The same job/workspace has been preserved across recovery. Under the currently deployed pre-adaptive Runtime semantics, C1 is stably blocked with:

- job status: `blocked`;
- result reason: `reassessment_stopped`;
- reassessment action: `stop`;
- reassessment reason: `repair budget exhausted`;
- signal: `hard_budget_guard`.

Last recorded counters remain:

- model calls: `21 / 22`;
- tool calls: `65 / 160`;
- test runs: `14 / 14`;
- wall time: `93.168 / 110` minutes;
- repair iterations: `4 / 4`.

Fresh exact recovery action recorded for that state:

- action id: `abXzvyU2pvALZ5YpovNveDcr`;
- type: `budget_extend`;
- payload: `max_repair_iterations +1`;
- last recorded status: pending/valid.

C2/C3 remain gated behind C1 completion. No manual DB/job mutation, counter reset, job replacement, or generic `/v1/jobs/{job_id}/run` bypass is allowed. The new adaptive/layered policies must not be simulated by manually altering this preserved job's counters/state.

## Durable efficiency policy already approved

- Profile remains a staffing/risk signal, but fixed profile counters are not the sole task resource estimate.
- Budget semantics have estimate, autonomous healthy working envelope and deterministic emergency hard ceiling.
- Reaching an estimate/working target alone must not stop healthy execution or require Human Owner approval.
- Provider quota/resource exhaustion is separate from task-budget estimation.
- Anti-loop/no-progress/oscillation/scope/cost/quota/emergency-ceiling signals are primary circuit breakers.
- Final deterministic verification remains mandatory; targeted/focused checks optimize iteration rather than weaken Definition of Done.
- Engineering repair accounting is separate from provider, infrastructure, verification and delivery retries.
- Inter-agent collaboration is bounded: one primary writer by default, read-only consultants/reviewers, Router-selected logical roles, compact evidence packs, normally 1-2 rounds, no recursive swarm.
- Review strength is risk-proportionate and should be calibrated using useful-finding telemetry.
- Human Owner attention is a first-class resource; routine targets are `human_interventions_per_task -> 0` and `avoidable_blocks_per_task -> 0`.

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

1. require exact-head deterministic CI for PR #156 and fix any failure on the same branch;
2. when #156 is green and review/governance gates are satisfied, merge it under the approved routine PM authority;
3. do not roll out Runtime `1.0.40` locally merely because the PR merges; respect the active-job service-restart gate and revalidate the preserved C1 job before/after any explicitly chosen targeted rollout;
4. after Phase B is merged, continue with #149 bounded inter-agent collaboration/review dialogue unless new evidence changes priority.

DEC-025C:

- the fresh `max_repair_iterations +1` action remains the normal recovery path if the Human Owner chooses to continue C1 under the currently deployed semantics;
- future adaptive/layered Runtime behavior must not be backported to C1 by manual state manipulation.
