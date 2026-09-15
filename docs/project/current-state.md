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
- PR #154 (`Add adaptive task budgets with emergency ceilings`) merged Phase A / issue #147.
- PR #155 (`Prefer OpenRouter for routine standard coding`) merged the routine Standard OpenRouter preference.
- PR #156 (`Add layered verification and retry attribution`) merged Phase B / issue #148 at merge commit `6b57976c6e6dfd1e3a40052003b2fa59c125f9b7`.
- PR #157 (`Add bounded inter-agent collaboration`) merged Phase C / issue #149 at merge commit `754233a17572b4631f418dfbab1c667790dc7fc5`. Merged Runtime source is `1.0.41`, Router source is `1.0.19`, and routing policy is v10.
- Phase C leaves one primary write-capable Developer, bounded read-only Router-staffed collaborators/reviewers, durable compact `CollaborationThread` artifacts, max two dialogue rounds, structured PM handoff, and no coding-agent Runtime credential exposure.
- Antigravity host bridge remains `1.10`; provider quota telemetry/proactive refresh and live Developer Activity remain implemented.
- PR #139 (`Document Telegram terminal operations gateway`) is merged; the terminal gateway remains an approved target, not implemented.
- Issue #98 (`Implement constrained PM-controlled PR merge in Runtime`) remains open and is still required for full executable alignment with the approved PM merge governance.

## Efficiency initiative — active platform priority

Authoritative policy/design: `docs/project/efficiency-model.md`.

Tracking:

- #146 — umbrella efficiency initiative;
- #147 — Phase A adaptive task budgets: complete/merged through PR #154;
- #148 — Phase B layered verification and failure-budget separation: complete/merged through PR #156;
- #149 — Phase C bounded inter-agent collaboration and review dialogue: complete/merged through PR #157;
- #150 — Phase D risk-proportionate review and role-specific evidence packs: active through PR #158;
- #151 — Phase E telemetry calibration, Human-attention metrics, and continuity automation;
- #98 — constrained PM-controlled merge remains part of the low-touch delivery target.

PR #155 also partially addresses #153 by preferring the existing OpenRouter coding model for healthy routine standard work while preserving privacy/quota/risk fallback behavior. A second OpenRouter model remains out of scope until current tool-use/provider-policy evidence supports activation.

Approved execution priority remains:

1. #147 adaptive budgeting — complete/merged;
2. #148 layered verification/failure accounting — complete/merged;
3. #149 bounded collaboration — complete/merged;
4. #150 risk-proportionate review/context compaction — active now;
5. #151 telemetry calibration/continuity automation;
6. complete #98 as part of removing the remaining routine end-of-task human checkpoint.

Telegram terminal convenience work remains lower priority unless an operational need changes the ordering.

## Active Phase D / issue #150 state

Branch: `ai/risk-proportionate-review-150`.

Pull request: #158 (`Add risk-proportionate review and compact evidence packs`), targeting `main` from the exact post-#157 merge baseline.

Target service/policy versions on this branch:

- Coding Runtime `1.0.42`;
- Router `1.0.20`;
- routing policy v11.

Implemented behavior on the branch:

- routed execution strategy carries a typed review policy with review level, required/conditional behavior, reviewer-independence requirements, compact evidence mode and JIT repository-retrieval permission;
- review level and high-impact thresholds live in `config/routing-policy.yml` v11 so PM calibration within approved policy does not require a code change;
- routine/fast work prepares a lightweight alternate reviewer but Runtime skips the model call when deterministic evidence is strong;
- standard work receives bounded independent review;
- complex work prefers a stronger reviewer on a different model;
- critical/security/architecture/high-risk work requires a different model/provider reviewer when eligible capacity exists; capacity degradation is recorded rather than hidden;
- reviewer prompts consume compact role-specific evidence packs instead of full default transcripts/logs; deterministic command stdout/stderr and full diff tails are omitted by default;
- reviewers may retrieve the smallest additional in-scope repository context just in time through the existing read-only evaluator sandbox, but may not request or reconstruct full model/developer transcripts;
- canonical WorkOrder authority is preserved in the compact reviewer pack, including compatibility for callers that carry only the canonical task description;
- reviewer output has a structured `ReviewReport` with verdict, summary, actionable findings, evidence references and JIT-context-use flag while retaining legacy PASS/FAIL compatibility;
- failed review is returned to the Developer as a compact repair evidence pack rather than a reviewer transcript;
- accepted results include compact review and PM evidence packs;
- telemetry tracks review runs, findings, findings that lead to a later diff change, review input/output tokens, estimated review cost, JIT-context use and useful-finding yield;
- useful-finding yield is updated immediately when a pending finding is followed by a changed diff, including when the next iteration is accepted immediately;
- deterministic verification and Human Owner protected-decision boundaries remain unchanged.

Regression coverage includes review-level selection, cross-provider reviewer requirements and capacity degradation, evidence-pack minimization, canonical WorkOrder preservation, JIT retrieval contract, structured review parsing, review resource telemetry, finding-to-diff attribution, and role-specific Developer/consultant/reviewer/PM evidence packs.

The first PR #158 CI run on head `83f591d7c356d8c72234efde8f7790290fe22dd8` had Router/structure/DDEV green and one Runtime compatibility failure: the compact evaluator prompt no longer exposed the canonical WorkOrder object when only canonical task text was supplied. The branch now parses that canonical task contract into the compact evidence object instead of reintroducing raw context. A new exact-head CI run is required after the subsequent policy/version/continuity commits.

No local Router/Runtime/DDEV/n8n rollout has been performed for Phase D. Merge still does not authorize a local service restart while an engineering job is active.

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

C2/C3 remain gated behind C1 completion. No manual DB/job mutation, counter reset, job replacement, or generic `/v1/jobs/{job_id}/run` bypass is allowed. Newer adaptive/layered/collaboration/review policies must not be simulated by manually altering this preserved job's counters/state.

## Durable efficiency policy already approved

- Profile remains a staffing/risk signal, but fixed profile counters are not the sole task resource estimate.
- Budget semantics have estimate, autonomous healthy working envelope and deterministic emergency hard ceiling.
- Reaching an estimate/working target alone must not stop healthy execution or require Human Owner approval.
- Provider quota/resource exhaustion is separate from task-budget estimation.
- Anti-loop/no-progress/oscillation/scope/cost/quota/emergency-ceiling signals are primary circuit breakers.
- Final deterministic verification remains mandatory; targeted/focused checks optimize iteration rather than weaken Definition of Done.
- Engineering repair accounting is separate from provider, infrastructure, verification and delivery retries.
- Inter-agent collaboration is bounded: one primary writer by default, read-only consultants/reviewers, Router-selected logical roles, compact evidence packs, normally 1-2 rounds, no recursive swarm.
- Review strength is risk-proportionate and calibrated through approved routing policy plus useful-finding/resource telemetry, never by weakening protected decision boundaries.
- Role-specific evidence packs and just-in-time read-only repository retrieval are preferred over raw transcript propagation.
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

1. require exact-head deterministic CI for PR #158 after Runtime `1.0.42`, Router `1.0.20`, routing policy v11 and this continuity update; fix any failure on the same branch;
2. when #158 is green and review/governance gates are satisfied, merge it under the approved routine PM authority;
3. do not roll out Runtime `1.0.42` / Router `1.0.20` locally merely because the PR merges; respect the active-job service-restart gate and revalidate the preserved C1 job before/after any explicitly chosen targeted rollout;
4. after Phase D is merged, continue with #151 telemetry calibration, Human-attention metrics and continuity automation unless new evidence changes priority.

DEC-025C:

- the fresh `max_repair_iterations +1` action remains the normal recovery path if the Human Owner chooses to continue C1 under the currently deployed semantics;
- future adaptive/layered/collaboration/review Runtime behavior must not be backported to C1 by manual state manipulation.
