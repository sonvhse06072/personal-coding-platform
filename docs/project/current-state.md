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
- Phase D #150 merged through PR #158 at `8eca5469f1a884511e0cf36cb9b6b51e0602a7bf`: policy-driven risk-proportionate review, compact role evidence packs, read-only JIT repository retrieval, structured review reports and review-usefulness telemetry.
- Phase E #151 merged through PR #159 at `71db5f20a7ee1bd5b0c525b51b3433d7f9dfeec7` after exact-head CI passed all four jobs. Merged source versions are Runtime `1.0.43`, Router `1.0.21`, routing policy v12.
- Phase E adds compact per-job telemetry persistence/aggregation, bounded historical Router calibration, first-class Human Owner attention metrics and compact continuity proposals without weakening deterministic verification or governance boundaries.
- PR #155 keeps the healthy routine Standard OpenRouter preference. A second OpenRouter model remains out of scope until provider/tool-use evidence supports activation.
- Antigravity host bridge remains `1.10`.
- Issue #98 constrained PM-controlled merge is the active remaining low-touch delivery dependency before PCP can claim a routine zero-human-touch happy path.
- PR #139 documents the separate Telegram terminal gateway target; it remains lower priority and unimplemented.

## Efficiency initiative

Authoritative policy/design: `docs/project/efficiency-model.md`.

Tracking:

- #146 umbrella initiative;
- #147 Phase A — complete/merged;
- #148 Phase B — complete/merged;
- #149 Phase C — complete/merged;
- #150 Phase D — complete/merged;
- #151 Phase E — complete/merged through PR #159;
- #98 constrained PM-controlled merge — active through PR #160.

## Active constrained PM merge / issue #98 state

Branch: `ai/pm-controlled-merge-98`, created from the exact Phase E merge commit `71db5f20a7ee1bd5b0c525b51b3433d7f9dfeec7`.

Pull request: #160, `Add constrained PM-controlled pull request merge`.

Current branch implementation:

- Runtime derives PM merge eligibility deterministically from durable project/ExecutionPlan/WorkOrder/job evidence rather than asking a model to decide merge authority;
- the existing project gate `autonomy.allow_auto_merge_low_risk` is the explicit opt-in; projects with it disabled keep the stable manual merge gate;
- eligible work must be an accepted completed non-dry-run job with exact WorkOrder/job/PR identity, a verified commit, deterministic verification success, required review success or the policy-authorized strong-evidence fast skip, finalized successful CI and no unexpected scope;
- protected scope/architecture/dependency/security/auth/trust-boundary/destructive-data/production/governance/material-budget signals cannot enter automatic merge unless the matching Human Owner decision was durably approved; unresolved/high-risk work remains at the owner/manual merge gate;
- accepted actual changed-file paths receive a second fail-closed classification before merge, so sensitive governance/workflow, project-scope, dependency/service-manifest, authentication/security, migration/schema and production/deployment paths cannot silently bypass an initially incomplete task-risk classification; mutable `docs/project/current-state.md` is not treated as a protected policy document;
- merge capability stays Runtime -> constrained ddev-executor -> GitHub. Developer/model processes receive no GitHub delivery or merge credentials;
- ddev-executor independently re-reads and validates the configured repository, exact PR number, AI branch, base branch, expected head SHA, pinned source ancestry and current GitHub CI immediately before mutation;
- GitHub merge uses the expected-head guard, no force push, and a fresh post-merge PR read before Runtime may mark the WorkOrder completed;
- Runtime persists a durable PM merge approval/result audit before/after the side effect. Existing approval records are never blindly replayed;
- approved-without-result crash recovery is observation-only: if GitHub confirms the exact PR was merged, Runtime records that observation; otherwise it blocks as an uncertain merge attempt;
- transport or confirmation ambiguity after mutation starts is treated as uncertain and fail-closed, not as permission to retry;
- downstream WorkOrders remain gated until GitHub confirms the exact PR merged;
- confirmed PM merge may emit the existing Phase E continuity `pr_merged` evidence, but continuity persistence failure cannot invalidate a merge already confirmed by GitHub;
- no production deployment or production side effect is added.

Regression coverage on the branch includes low-risk eligible one-shot merge and downstream unlock, manual opt-out stability, protected-change owner gating and durable owner approval, sensitive actual-path classification, stale head rejection, source-ancestry failure, non-success CI rejection, replay rejection, exact merge confirmation, approved-without-result crash recovery and constrained PM-bridge policy/auth boundaries.

CI history on PR #160:

- exact-head `a3d7ef499ec1844ebf0790182e42415e9bc1e246`: Router, structure and ddev-executor passed; Runtime had one test-fixture compatibility failure because the synthetic plan omitted `baseline_revision` when the downstream WorkOrder was unlocked;
- the fixture was corrected on the same branch to match the real orchestration shape;
- exact-head `3e77a6445f14738fc1972fa7559759dd3891d44e`, workflow run #308, passed Runtime, Router, ddev-executor and structure-tests;
- self-review then added the actual changed-file protected-path guard plus regression coverage, so run #308 was deliberately superseded;
- exact-head `fbbad479f22f204b392ecaca818705f27f27dc69`, workflow run #310 (`34999137678`), passed Runtime, Router, ddev-executor and structure-tests. This continuity-only commit must receive one final exact-head CI run before merge.

No local Runtime/ddev-executor/DDEV/n8n rollout has been performed for #98. Merge must not be treated as permission to restart active local services.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `pm_controlled_merge_exact_head_green`.
- Project/job: `personal-coding-platform` / `n/a`.
- Runtime state: `development`; outcome: `pending_final_doc_only_ci_and_merge_gate`.
- WorkOrder: `GH-98`; branch: `ai/pm-controlled-merge-98`; PR: `#160`.
- Verification: code head `fbbad479f22f204b392ecaca818705f27f27dc69`; workflow run #310 passed Runtime, Router, ddev-executor and structure-tests.
- Human attention: issue #96 / PR #97 already provide the Human Owner-approved governance delegation that #98 implements; protected merge boundaries remain fail-closed.
- Deployment: not performed.
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

C2/C3 remain gated behind C1. Do not manually mutate DB/job state, reset counters, replace the job, or simulate newer adaptive/layered/collaboration/review/telemetry/PM-merge semantics inside this preserved job.

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
- PM may merge routine in-scope PRs only through the constrained authority path and only after required deterministic/review/CI gates pass with no unresolved protected Human Owner decision.

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

1. require final exact-head CI for PR #160 after this continuity-only commit;
2. inspect PR comments/reviews and verify the exact head, mergeability and absence of unresolved Human Owner decision triggers;
3. merge #160 only when the final exact-head CI and review gates are green, using an expected-head guard;
4. do not roll out/restart Runtime or ddev-executor merely because #160 merges;
5. after merge, reassess the roadmap from the new main baseline before starting another feature branch.

DEC-025C:

- the recorded `max_repair_iterations +1` action remains the normal recovery path only if the Human Owner chooses to continue C1 under currently deployed semantics;
- newer adaptive/layered/collaboration/review/telemetry/PM-merge behavior must not be backported by manual state manipulation.
