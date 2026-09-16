# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. Durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-16

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
- Phase D #150 merged through PR #158 at `8eca5469f1a884511e0cf36cb9b6b51e0602a7bf`: risk-proportionate review and compact evidence packs.
- Phase E #151 merged through PR #159 at `71db5f20a7ee1bd5b0c525b51b3433d7f9dfeec7`: telemetry calibration, Human Owner attention metrics and continuity proposals.
- Constrained PM-controlled merge #98 merged through PR #160 at `a9dfde049196ff2d02e56e99a86f80ca2af88dad`; post-merge continuity PR #161 merged at `b465cc016dd063032ad5a06188f2c552a8ffe39b`.
- The A-F source implementation sequence for initiative #146 is complete. Operational rollout/validation is tracked by #162.
- #163 is the active pre-rollout prerequisite: give the post-#98 Runtime and ddev-executor distinct deployed identities so #162 can prove rebuilt containers are actually running the new source.
- Router remains `1.0.21`, routing policy v12, and Antigravity host bridge remains `1.10`.
- `chonhac` still has `autonomy.allow_auto_merge_low_risk: false`; do not change it merely to exercise auto-merge.
- PR #139 / Telegram terminal gateway remains approved but lower priority than #162 operational validation.

## Active version-identity prerequisite / issue #163

Branch: `ai/version-identity-163`, created from main `b465cc016dd063032ad5a06188f2c552a8ffe39b`.

Scope is version/build identity only. No PM-merge policy, Runtime state-machine, credentials, project autonomy or rollout behavior changes are allowed.

Target identities after #163 merges and #162 performs a rebuild:

- Coding Runtime source/FastAPI/health: `1.0.44`;
- ddev-executor source/FastAPI/health: `1.0.15`;
- Router: unchanged at `1.0.21`;
- routing policy: unchanged at v12.

Branch changes:

- Runtime FastAPI and `/health` identity bumped from `1.0.43` to `1.0.44`;
- ddev-executor FastAPI and `/health` identity bumped from `1.0.14` to `1.0.15`;
- Runtime exact version regression assertion updated;
- ddev-executor version and health regression assertions added;
- no local rollout/restart is performed by #163.

#162 remains the operational rollout/validation issue after #163 merges.

## Operational validation / issue #162

Target proof:

`WorkOrder -> implementation -> targeted/focused verification -> final deterministic verification -> proportional review -> PR/CI -> constrained PM merge -> telemetry/continuity`

with zero avoidable Human Owner intervention on one eligible routine fixture.

Safety gates before any local rebuild/restart:

- query durable Runtime state and require every existing job to be stable blocked/terminal;
- preserve the existing `chonhac` DEC-025C job/workspace/counters and pending recovery action exactly;
- do not resume, replace, reset or migrate DEC-025C as part of rollout validation;
- use a clean registered fixture with `allow_auto_merge_low_risk: true`; prefer `example-drupal`, otherwise use `default` only if its verification contract is sufficient;
- never fall back to `chonhac` for the auto-merge proof;
- no production deployment or production write.

After #163 is merged, local rollout must prove Runtime `1.0.44`, Router `1.0.21`, and ddev-executor `1.0.15` before the routine end-to-end validation begins.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `rollout_version_identity_preparation`.
- Project/job: `personal-coding-platform` / `n/a`.
- Runtime state: `source_change_in_pr_flow`; outcome: `awaiting_issue_163_exact_head_ci`.
- Active issue: `#163`; parent rollout validation: `#162`; initiative: `#146`.
- Target deployed identity after the later #162 rebuild: Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`.
- Human attention: no local action required while #163 is in repository CI/merge flow.
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
- Do not restart/rebuild Runtime/Router/ddev-executor/DDEV/n8n while a job is active; require stable blocked/terminal state first.
- Runtime durable state is authoritative; never edit DB/job state manually to bypass the state machine.
- Provider/control-plane credentials remain service-scoped and must not enter Developer prompts or repository docs.

## Immediate next safe actions

Platform:

1. open the #163 PR from `ai/version-identity-163` and require exact-head Runtime/Router/ddev-executor/structure CI;
2. merge #163 only when exact-head CI and review gates are green; do not roll out merely because it merges;
3. then begin #162 by collecting pre-rollout local evidence and checking the active-job gate;
4. only after that gate passes, perform the explicit local rebuild/restart and validate deployed versions/health;
5. run one bounded routine fixture ticket end-to-end without manual merge and capture telemetry/continuity evidence;
6. keep #146 open until operational evidence demonstrates the intended low-touch behavior.

DEC-025C:

- the recorded `max_repair_iterations +1` action remains the normal recovery path only if the Human Owner chooses to continue C1 under currently deployed semantics;
- newer behavior must not be backported by manual state manipulation.
