# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. Durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-16

## How to resume in a new chat or agent session

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/project/README.md`;
3. this file;
4. topical documents referenced by the active work, especially `efficiency-model.md` and `service-secret-upgrades.md`;
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
- Operator shell-safety follow-up #165 completed through PR #166 / merge `d4109c77244b3e53cb751af085c71204971cd805`.
- Host-secret test-harness follow-up #167 completed through PR #168 / merge `7c7ff717ef9f38c4d5a6ed8559a1a99636e5bd99`.
- Runtime local/container test-portability follow-up #169 completed through PR #170 / merge `fcc92eff906d89d3a6eb10ddf3925d8e0bdb93f9`.
- Validation-procedure correction #171 completed through PR #172 / merge `45291e41aa797d71ecf8f82a9a2aedab8d46ecbe`.
- Rollout/preservation continuity #173 completed through PR #174 / merge `18965e545ae8d850b25a4ef8642d7d1ab735b9d2`.
- `chonhac` still has `autonomy.allow_auto_merge_low_risk: false`; do not change it merely to exercise auto-merge.
- PR #139 / Telegram terminal gateway remains approved but lower priority than #162 operational validation.

## Operational validation / issue #162

Target proof:

`WorkOrder -> implementation -> targeted/focused verification -> final deterministic verification -> proportional review -> PR/CI -> constrained PM merge -> telemetry/continuity`

with zero avoidable Human Owner intervention on one eligible routine fixture.

### Rollout health/test/preservation gate completed

The Human Owner completed the safety-gated rollout and second rebuild. Final deployed identity/health evidence:

- Antigravity host bridge: healthy, version `1.10`, no active runs, safety settings intact;
- Router: healthy, version `1.0.21`, routing policy v12;
- Coding Runtime: healthy, version `1.0.44`, Router/executor public health `ok`;
- ddev-executor: healthy, version `1.0.15`, `active_jobs: 0`, GitHub delivery configured;
- n8n: healthy.

`ddev platform-test` passed completely after corrected tests were rebuilt into Runtime:

- Router: `76 passed`;
- Runtime: `289 passed`;
- ddev-executor: `34 passed`.

The preserved `chonhac` DEC-025C state survived rollout unchanged, including counters and recovery action. A direct read-only `cp_control_actions` query confirmed action `abXzvyU2pvALZ5YpovNveDcr` remains `pending`, unexpired, result `null`, `created_at == updated_at`, payload `max_repair_iterations +1`.

The rollout health/test/DEC-025C preservation acceptance is complete. Do not repeat that rebuild sequence unless later source or local service configuration actually requires it.

### Active blocker #175: deployed internal credential missing

The next #162 trust-boundary check exposed a real existing-install upgrade gap:

- fresh active-work gate passed: Antigravity `active_runs=0`, ddev-executor `active_jobs=0`, and Runtime had no in-flight jobs;
- the deployed `coding-runtime` container did **not** expose `PLATFORM_INTERNAL_TOKEN`;
- the check stopped before recording the Phase-E rollout continuity event or inspecting `example-drupal`.

This matters because `DdevExecutorClient` reads `PLATFORM_INTERNAL_TOKEN` and uses it for privileged Runtime -> ddev-executor requests, while ddev-executor rejects privileged calls when that token is missing. Public executor `/health` is intentionally unauthenticated, so Runtime/executor health can remain green even when this privileged path is unusable.

Source already contains the canonical migration helper `scripts/scope-service-secrets.sh`. It intentionally shares `PLATFORM_INTERNAL_TOKEN` only between `.env.coding-runtime.local` and `.env.ddev-executor.local`, preserves existing real values, refuses conflicts, and removes platform credentials from global `.ddev/.env`.

Root cause: one-time `scripts/bootstrap.sh` runs this migration, but an existing installation upgraded by fast-forward + restart can miss a newly introduced service credential unless the migration helper is rerun before the restart that should consume it.

Issue #175 is the bounded follow-up. Its implementation adds a non-secret deployed credential-boundary status guard and documents the migrate-before-restart upgrade order. Do not bypass #175 by manually copying token values between files or editing container/job state.

### Trust boundary and fixture configuration

Source configuration preserves the intended authority boundary:

- coding-runtime may receive Runtime/Router/internal/provider credentials but must not receive `GITHUB_DELIVERY_TOKEN` or Telegram bot credentials;
- ddev-executor is the only service intended to receive `GITHUB_DELIVERY_TOKEN` and Docker socket access; it also shares `PLATFORM_INTERNAL_TOKEN` with Runtime;
- n8n receives Runtime/control-plane/Telegram credentials but no GitHub delivery/internal executor credential;
- Runtime reaches merge authority only through constrained ddev-executor endpoints;
- Developer subprocesses sanitize internal/control-plane credentials and Runtime is hardened non-dumpable on Linux.

`config/projects.yml` registers `example-drupal` with `autonomy.allow_auto_merge_low_risk: true`, production deploy disabled, base branch `develop`, and deterministic verification: preflight (`ddev start -y`, `ddev drush cr`), PHPCS, PHPStan, PHPUnit, cleanup. `chonhac` remains ineligible for the auto-merge proof.

Local fixture readiness has not been checked yet because the trust-boundary gate stopped first.

### Remaining #162 gates before the routine WorkOrder

1. Complete #175 and merge its status/documentation guard.
2. Human Owner fast-forwards local platform source, then runs a fresh read-only no-active-work gate.
3. Only after that gate passes, run `./scripts/scope-service-secrets.sh`; do not print credential values and do not manually copy secrets.
4. Restart/recreate DDEV services so the updated service-local env is loaded. A no-cache image rebuild is not required merely for the secret-file migration or host-only #175 guard unless some later service-image source changes.
5. Require `ddev platform-status` credential-boundary `ok=true` and `./scripts/service-secret-status.sh --strict` exit code 0.
6. Record the Phase-E `rollout` continuity event through authenticated Runtime API.
7. Confirm local `example-drupal` exists, is clean, `develop` matches the usable GitHub remote, and its configured DDEV verification passes.
8. Run one small non-security/non-architecture/non-dependency/non-migration/non-production WorkOrder with a deterministic non-empty diff and no manual merge.
9. Capture telemetry/continuity/PM-merge audit evidence and post it to #162 and #146.

No production deployment or production write.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `rollout_trust_boundary_blocked_by_missing_internal_token`.
- Project/job: `personal-coding-platform` / `n/a`.
- Rollout health/tests/preservation: completed at Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`; Router 76, Runtime 289, executor 34 tests passed; DEC-025C preserved exactly.
- Latest gate: no active work, but deployed coding-runtime lacked `PLATFORM_INTERNAL_TOKEN`.
- Active bounded follow-up: `#175`; parent rollout validation: `#162`; initiative: `#146`.
- Root cause class: existing-install service-secret migration was not rerun before rebuild; public health did not exercise privileged Runtime -> executor authentication.
- Canonical remediation: merge #175 guard/docs, fresh active-work gate, run `scripts/scope-service-secrets.sh`, restart services to load env, require strict credential-boundary pass.
- Phase-E rollout event: not recorded yet.
- Routine fixture job: not created yet.
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

C2/C3 remain gated behind C1. Do not manually mutate DB/job state, reset counters, replace the job, or simulate newer semantics inside this preserved job.

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

1. complete #175 through reviewed CI/PR;
2. Human Owner fast-forwards local `main` and runs a fresh read-only active-work gate;
3. after that gate passes, run the canonical service-secret migration and restart services to consume the updated env;
4. require strict credential-boundary pass without printing secret values;
5. record Phase-E rollout continuity event;
6. verify `example-drupal` local repository and deterministic baseline;
7. create one bounded routine validation WorkOrder and let verification/review/PR/CI/constrained PM merge proceed without manual merge;
8. capture telemetry, Human attention, PM merge audit and continuity evidence in #162 and #146.

DEC-025C:

- the recorded `max_repair_iterations +1` action remains the normal recovery path only if the Human Owner chooses to continue C1 under its preserved state;
- newer behavior must not be backported by manual state manipulation.
