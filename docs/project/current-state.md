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
- Version-identity prerequisite #163 completed through PR #164 / merge `a4735880fbabcc57303ee80f971204906a51fbb0`: Runtime `1.0.44`, ddev-executor `1.0.15`; Router remains `1.0.21`, routing policy v12.
- Operator shell-safety follow-up #165 completed through PR #166 / merge `d4109c77244b3e53cb751af085c71204971cd805`; pasted validation blocks that can fail must isolate `exit`/non-zero status from the Human Owner's parent Ubuntu/WSL shell.
- Host-secret test-harness follow-up #167 completed through PR #168 / merge `7c7ff717ef9f38c4d5a6ed8559a1a99636e5bd99`; `platform-test` now invokes Antigravity bridge status through `scripts/with-host-secrets.sh`.
- Runtime local/container test-portability follow-up #169 completed through PR #170 / merge `fcc92eff906d89d3a6eb10ddf3925d8e0bdb93f9`; exact-head CI #324 passed all four jobs.
- Validation-procedure correction #171 completed through PR #172 / merge `45291e41aa797d71ecf8f82a9a2aedab8d46ecbe`; corrected Runtime tests are baked into the service image and therefore required the second safety-gated no-cache rebuild.
- Current `main` later advanced to `796337b3150398b1291af7d591eb8fbdc57127d8` through an immediately reverted accidental empty-file creation. Compare against `45291e41aa797d71ecf8f82a9a2aedab8d46ecbe` has zero file diff, so those two history commits changed no rollout source and require no rebuild.
- `chonhac` still has `autonomy.allow_auto_merge_low_risk: false`; do not change it merely to exercise auto-merge.
- PR #139 / Telegram terminal gateway remains approved but lower priority than #162 operational validation.

## Operational validation / issue #162

Target proof:

`WorkOrder -> implementation -> targeted/focused verification -> final deterministic verification -> proportional review -> PR/CI -> constrained PM merge -> telemetry/continuity`

with zero avoidable Human Owner intervention on one eligible routine fixture.

### Rollout health/test/preservation gate completed

The Human Owner completed the pre-rollout and second-rebuild safety gates before any restart. At each rebuild gate, authenticated Runtime state contained only stable blocked/terminal jobs, ddev-executor reported `active_jobs: 0`, and Antigravity reported `active_runs: 0`.

The final post-rebuild deployed identity and health evidence is:

- Antigravity host bridge: healthy, version `1.10`, no active runs, safety settings intact;
- Router: healthy, version `1.0.21`, routing policy v12;
- Coding Runtime: healthy, version `1.0.44`, Router/executor health `ok`;
- ddev-executor: healthy, version `1.0.15`, `active_jobs: 0`, GitHub delivery configured;
- n8n: healthy.

After #167/#169/#171 were incorporated into the rebuilt images, `ddev platform-test` passed completely:

- Router: `76 passed`;
- Runtime: `289 passed`;
- ddev-executor: `34 passed`.

The preserved `chonhac` DEC-025C state also survived rollout unchanged:

- job `eec59b13651c54559c10ce204380a68e`;
- WorkOrder `DEC-025C-1-recovery-tooling-r2`;
- branch `ai/eec59b13651c`;
- workspace `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`;
- status `blocked`;
- result still `reassessment_stopped` / `repair budget exhausted` / `hard_budget_guard`;
- consumed model calls `21 / 22`;
- consumed tool calls `65 / 160`;
- consumed test runs `14 / 14`;
- consumed wall time `93.168 / 110` minutes;
- consumed repair iterations `4 / 4`.

A direct read-only query of `cp_control_actions` confirmed recovery action `abXzvyU2pvALZ5YpovNveDcr` remains:

- `budget_extend` for `max_repair_iterations +1`;
- exact plan `pm-gh-5650852312`, WorkOrder and job identity;
- status `pending`;
- result `null`;
- unexpired;
- `created_at == updated_at`, proving it was never mutated by rollout.

The earlier validation attempt that searched `/v1/plans/{plan_id}/orchestration` for this action id was invalid: that endpoint does not expose `cp_control_actions`. Missing the action id from orchestration JSON did not indicate durable state loss.

Therefore the #162 rollout health/test/DEC-025C preservation acceptance is complete. Do not repeat another rollout rebuild unless later source changes actually require one.

### Trust boundary and fixture readiness

Source configuration preserves the intended credential boundary:

- coding-runtime receives Runtime/Router/internal/provider credentials but not `GITHUB_DELIVERY_TOKEN`;
- ddev-executor is the only service configured for `GITHUB_DELIVERY_TOKEN` and Docker socket access;
- n8n receives Runtime/control-plane/Telegram credentials but no GitHub delivery credential;
- Runtime reaches merge authority only through the constrained ddev-executor service.

`config/projects.yml` registers `example-drupal` with `autonomy.allow_auto_merge_low_risk: true`, production deploy disabled, base branch `develop`, and a usable deterministic DDEV verification contract: preflight (`ddev start -y`, `ddev drush cr`), targeted PHPCS, PHPStan static analysis, PHPUnit full tests, and cleanup. `chonhac` remains ineligible for the auto-merge proof.

Source configuration alone does not prove the local `example-drupal` repository exists, is clean, has the expected base branch/remote, or can currently execute the configured verification. Confirm those local facts before creating the routine validation job.

### Remaining #162 gates before the routine WorkOrder

- perform one local trust-boundary check that inspects only variable names/presence, never secret values, and confirms coding-runtime does not receive GitHub delivery credentials while ddev-executor does;
- record the Phase-E `rollout` continuity event through authenticated `POST /v1/continuity/events` now that health/tests/preservation passed;
- confirm local `example-drupal` exists, is a clean Git repository, expected base branch `develop` exists, its configured remote is usable for GitHub delivery, and its DDEV verification surface is available;
- if `example-drupal` is unsuitable, stop and record the blocker; use `default` only if its verification contract is sufficient for the selected task, and never fall back to `chonhac`;
- then run one small non-security/non-architecture/non-dependency/non-migration/non-production WorkOrder with a deterministic non-empty diff and no manual merge;
- capture telemetry/continuity/PM-merge audit evidence and post it to #162 and #146;
- no production deployment or production write.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `rollout_health_test_preservation_gate_completed`.
- Project/job: `personal-coding-platform` / `n/a`.
- Runtime state: deployed and healthy at Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`; routing policy v12.
- Verification: `ddev platform-test` passed Router 76, Runtime 289 and ddev-executor 34 tests after the corrected tests were baked into rebuilt images.
- DEC-025C preservation: identity, blocked status, result and counters unchanged; pending recovery action `abXzvyU2pvALZ5YpovNveDcr` remains unexpired and never mutated.
- Validation correction: control actions are stored in `cp_control_actions`; the plan orchestration view does not expose those rows.
- Parent rollout validation: `#162`; initiative: `#146`.
- Next stage: trust-boundary presence check, record Phase-E rollout continuity event, then local `example-drupal` fixture readiness check before creating any validation job.
- Human attention: no local rebuild/restart is currently required.
- Production deployment: not performed.
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

Authoritative preserved state before and after rollout:

- status: `blocked`;
- reason: `reassessment_stopped` / `repair budget exhausted` / `hard_budget_guard`;
- model calls `21 / 22`;
- tool calls `65 / 160`;
- test runs `14 / 14`;
- wall time `93.168 / 110` minutes;
- repair iterations `4 / 4`.

Latest recorded recovery action:

- action id `abXzvyU2pvALZ5YpovNveDcr`;
- `budget_extend` for `max_repair_iterations +1`;
- status `pending` and unexpired after rollout;
- result `null`;
- `created_at == updated_at`, so rollout did not mutate the action.

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
- Potentially failing Human Owner validation blocks must isolate non-zero/`exit` behavior in a subshell or standalone script so the parent Ubuntu/WSL shell survives controlled gate failure.

## Immediate next safe actions

Platform:

1. complete #173 as a mutable continuity update only; no rollout source changes and no rebuild;
2. verify deployed trust/secret presence boundaries without printing credential values;
3. record the Phase-E `rollout` continuity event through authenticated Runtime API;
4. inspect local `example-drupal` fixture existence, cleanliness, base branch/remote and DDEV verification readiness;
5. if fixture readiness passes, create one bounded routine WorkOrder with a small deterministic non-empty diff and allow the system to run through verification, review, PR/CI and constrained PM merge without manual merge;
6. capture telemetry, Human attention, PM merge audit and continuity evidence and post it to #162 and #146;
7. keep #146 open until operational evidence demonstrates the intended low-touch behavior.

DEC-025C:

- the recorded `max_repair_iterations +1` action remains the normal recovery path only if the Human Owner chooses to continue C1 under its preserved state;
- newer behavior must not be backported by manual state manipulation.
