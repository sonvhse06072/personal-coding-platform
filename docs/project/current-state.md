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
- Phase D #150 merged through PR #158 at `8eca5469f1a884511e0cf36cb9b6b51e0602a7bf`: policy-driven risk-proportionate review, compact role evidence packs, read-only JIT retrieval, structured review reports and review-usefulness telemetry.
- Phase E #151 merged through PR #159 at `71db5f20a7ee1bd5b0c525b51b3433d7f9dfeec7`: compact task telemetry, bounded historical Router calibration, Human Owner attention metrics and continuity proposals. Source versions remain Runtime `1.0.43`, Router `1.0.21`, routing policy v12.
- Constrained PM-controlled merge #98 merged through PR #160 at `a9dfde049196ff2d02e56e99a86f80ca2af88dad` after final exact-head workflow run #311 (`34999337692`) passed Runtime, Router, ddev-executor and structure-tests.
- #98 keeps GitHub merge authority behind Runtime -> constrained ddev-executor, revalidates exact PR/head/base/source ancestry/current CI, uses expected-head merge semantics, persists durable merge audit evidence, rejects replay/uncertain outcomes fail-closed, and advances dependencies only after GitHub confirms the exact merge.
- Accepted actual changed-file paths provide an additional fail-closed protected-decision signal for governance/workflow, scope, dependency/service, security/auth, migration/schema and production/deployment changes; matching Human Owner approval remains required where protected authority is implicated.
- `chonhac` still has `autonomy.allow_auto_merge_low_risk: false`, so its merge behavior remains manual until project policy is explicitly changed.
- PR #155 keeps the healthy routine Standard OpenRouter preference. A second OpenRouter model remains out of scope until provider/tool-use evidence supports activation.
- Antigravity host bridge remains `1.10`.
- PR #139 documents the separate Telegram terminal gateway target; it remains approved but lower priority and unimplemented.

## Efficiency initiative #146

Authoritative policy/design: `docs/project/efficiency-model.md`.

Source implementation status:

- #147 Phase A — complete/merged;
- #148 Phase B — complete/merged;
- #149 Phase C — complete/merged;
- #150 Phase D — complete/merged;
- #151 Phase E — complete/merged;
- #98 Phase F constrained PM merge — complete/merged.

The A-F source implementation sequence is complete. Issue #146 remains open for operational validation/calibration rather than additional scope by default. The next evidence should come from safe rollout and real routine-task execution: human interventions/task, avoidable blocks/task, model/test usage, CI/review yield, wall time and merge throughput. Do not close #146 solely because source code merged if the deployed system has not yet produced the intended operational evidence.

No new feature branch is automatically implied by completion of #98. In particular, do not jump to the lower-priority Telegram terminal gateway merely because the efficiency implementation sequence is source-complete.

## PM-controlled merge implementation evidence

PR #160 final head: `b5e381bd2750b6cdce55d6df152cb5daf1c2263b`.

Validation history:

- an earlier Runtime-only failure was a synthetic orchestration fixture missing `baseline_revision`; production state-machine logic was not changed to hide that failure;
- after the fixture fix, all four jobs passed;
- self-review then added actual changed-file protected-path classification and dedicated regression coverage;
- code head `fbbad479f22f204b392ecaca818705f27f27dc69` passed all four jobs in workflow run #310;
- final continuity-only head `b5e381bd2750b6cdce55d6df152cb5daf1c2263b` passed all four jobs in workflow run #311;
- PR comments, submitted reviews and inline review threads were empty; the PR was mergeable;
- merge used the exact expected-head guard and produced main merge commit `a9dfde049196ff2d02e56e99a86f80ca2af88dad`;
- issue #98 closed automatically through `Closes #98`.

No local Runtime/ddev-executor/DDEV/n8n rollout was performed as part of this merge. Source completion must not be confused with deployed behavior.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `pm_controlled_merge_source_complete`.
- Project/job: `personal-coding-platform` / `n/a`.
- Runtime state: `source_merged`; outcome: `awaiting_explicit_rollout_and_operational_validation`.
- WorkOrder: `GH-98`; merged PR: `#160`; merge commit: `a9dfde049196ff2d02e56e99a86f80ca2af88dad`.
- Verification: final exact-head workflow run #311 passed Runtime, Router, ddev-executor and structure-tests.
- Human authority: issue #96 / PR #97 provide the Human Owner-approved governance delegation implemented by #98; protected decision boundaries remain Human Owner-controlled.
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

Platform:

1. merge this docs-only post-#98 continuity update after exact-head CI;
2. keep #146 open for operational validation until real deployed evidence supports its success metrics;
3. do not roll out/restart Runtime, ddev-executor, DDEV or n8n merely because source implementation is complete;
4. when the Human Owner explicitly chooses a local rollout window and the active-job gate is satisfied, deploy the merged source, verify service health/version/merge trust boundaries, then run a bounded routine ticket through WorkOrder -> implementation -> verification -> review -> PR/CI -> PM merge and collect Phase E telemetry;
5. choose any next feature only from that evidence or an explicit Human Owner priority, rather than assuming #139 is next.

DEC-025C:

- the recorded `max_repair_iterations +1` action remains the normal recovery path only if the Human Owner chooses to continue C1 under currently deployed semantics;
- newer adaptive/layered/collaboration/review/telemetry/PM-merge behavior must not be backported by manual state manipulation.
