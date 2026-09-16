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
- `chonhac` still has `autonomy.allow_auto_merge_low_risk: false`; do not change it merely to exercise auto-merge.
- PR #139 / Telegram terminal gateway remains approved but lower priority than #162 operational validation.

## Operational validation / issue #162

Target proof:

`WorkOrder -> implementation -> targeted/focused verification -> final deterministic verification -> proportional review -> PR/CI -> constrained PM merge -> telemetry/continuity`

with zero avoidable Human Owner intervention on one eligible routine fixture.

### Pre-rollout gate completed

The Human Owner completed the read-only pre-rollout gate on local `main` at `d4109c77244b3e53cb751af085c71204971cd805`:

- authenticated Runtime job list contained only stable `blocked`, `completed`, or `failed` jobs;
- `ACTIVE_JOB_GATE=PASS`;
- preserved DEC-025C job `eec59b13651c54559c10ce204380a68e` remained `blocked` with WorkOrder `DEC-025C-1-recovery-tooling-r2`;
- `DEC025C_GATE=PASS`;
- ddev-executor reported `active_jobs: 0`;
- Antigravity bridge reported `active_runs: 0`, `safe_settings: true`, and no safety mismatches.

### Local rebuild completed and source identity proven

The Human Owner ran `ddev restart --no-cache` only after the active-job gate passed. DDEV rebuilt the custom project images and restarted the platform successfully.

Post-rebuild health evidence:

- Antigravity host bridge: healthy, version `1.10`, no active runs, safety settings intact;
- Router: healthy, version `1.0.21`, routing policy v12;
- Coding Runtime: healthy, version `1.0.44`, Router/executor health `ok`;
- ddev-executor: healthy, version `1.0.15`, `active_jobs: 0`, GitHub delivery configured;
- n8n: healthy.

All three explicit deployed-version gates passed. This proves the new Runtime/Router/ddev-executor source is deployed.

### Resolved harness blocker #167 and current test-portability blocker #169

#167 / PR #168 fixed the first post-rollout `platform-test` failure by loading the host-scoped Antigravity bridge token through `scripts/with-host-secrets.sh`. After the Human Owner fast-forwarded local `main` to `7c7ff717ef9f38c4d5a6ed8559a1a99636e5bd99`, the service suites ran.

Observed local evidence on that rerun:

- platform health still passed at Antigravity `1.10`, Router `1.0.21`, Runtime `1.0.44`, ddev-executor `1.0.15`, n8n healthy;
- Router suite: `76 passed`;
- Runtime suite: `288 passed, 2 failed`.

The two failures are deterministic test-layer defects rather than deployed service-health failures:

1. `services/runtime/tests/test_quota_policy_doc.py` assumes a full repository checkout and walks `parents[3]` to repo-level `docs/`. The Runtime production image intentionally copies only `/app/app` and `/app/tests`, so repo documentation does not exist inside that service image. Provider-quota documentation coverage belongs in root structure tests instead.
2. `services/runtime/tests/test_router_staffing_client.py` assumes the outbound staffing JSON is exactly the caller payload. `RouterClient.staff()` intentionally applies `quota_coordinator.enrich(payload)` before POST. Clean CI quota state can make the stale assertion pass accidentally; durable local quota telemetry exposes the mismatch. The unit test must mock enrichment deterministically and assert the enriched payload without mutating caller input.

Bounded follow-up #169 moves the repo-documentation assertion to root structure tests and makes staffing-client quota enrichment deterministic. It does not change Runtime/Router/executor behavior or weaken credential boundaries.

Until #169 merges and the Human Owner reruns the post-rollout checks:

- #162 rollout acceptance remains incomplete;
- do not start the routine fixture WorkOrder yet;
- do not record the Phase-E `rollout` continuity event yet;
- post-rebuild DEC-025C full result/counter/recovery-action comparison remains required because the safety block stopped at `platform-test`.

### Remaining #162 safety gates

- preserve the existing `chonhac` DEC-025C job/workspace/counters and pending recovery action exactly;
- do not resume, replace, reset or migrate DEC-025C as part of rollout validation;
- after #169 merges, fast-forward local `main`, rerun `ddev platform-test`, then capture the preserved DEC-025C job result and orchestration state and compare identity/status/counters/recovery action with the pre-rollout state;
- because #169 changes only tests/documentation, no service rebuild should be required merely to consume the corrected tests; if executable evidence contradicts this, stop and reassess rather than bypassing it;
- only after post-rollout test and DEC-025C preservation gates pass, verify trust/secret boundaries and record the Phase-E `rollout` continuity event;
- use a clean registered fixture with `allow_auto_merge_low_risk: true`; prefer `example-drupal`, otherwise use `default` only if its verification contract is sufficient;
- never fall back to `chonhac` for the auto-merge proof;
- no production deployment or production write.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `rollout_validation_blocked_by_runtime_test_portability`.
- Project/job: `personal-coding-platform` / `n/a`.
- Runtime state: deployed and healthy at Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`; outcome: `awaiting_issue_169_fix_and_post_rollout_retest`.
- Active issue: `#169`; parent rollout validation: `#162`; initiative: `#146`.
- Safety evidence: pre-rollout active-job gate passed; rebuild occurred only after the gate; post-rebuild health remains green and executor/bridge active counts remain zero.
- Resolved blocker: #167 fixed host-scoped Antigravity secret loading in `platform-test`.
- Current blocker: one repo-documentation test is incorrectly located inside Runtime service tests, and one staffing-client test is nondeterministic with respect to local durable quota telemetry.
- Human attention: no additional local action required while #169 is in repository PR/CI flow.
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

Authoritative pre-rollout preserved state:

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
- last recorded status pending/valid.

C2/C3 remain gated behind C1. Do not manually mutate DB/job state, reset counters, replace the job, or simulate newer adaptive/layered/collaboration/review/telemetry/PM-merge semantics inside this preserved job.

The post-rebuild preservation comparison has not yet completed; perform it only after #169 allows `platform-test` to pass.

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

1. complete #169 through exact-head CI/review/merge; keep the change limited to test portability and continuity documentation;
2. Human Owner fast-forwards local `main` after #169 merges; no service restart/rebuild merely for this tests/docs-only follow-up;
3. rerun `ddev platform-test` and require all Router/Runtime/ddev-executor tests to pass;
4. capture `GET /v1/jobs/eec59b13651c54559c10ce204380a68e` plus `/v1/plans/pm-gh-5650852312/orchestration` and verify DEC-025C identity/status/result/counters/recovery action remain unchanged after rebuild;
5. verify coding-agent secret/trust boundaries and then record the Phase-E `rollout` continuity event;
6. inspect `config/projects.yml` plus local fixture availability and verification contract; prefer `example-drupal` for the routine end-to-end task;
7. run one bounded routine fixture ticket end-to-end without manual merge and capture telemetry/continuity evidence;
8. keep #146 open until operational evidence demonstrates the intended low-touch behavior.

DEC-025C:

- the recorded `max_repair_iterations +1` action remains the normal recovery path only if the Human Owner chooses to continue C1 under its preserved state;
- newer behavior must not be backported by manual state manipulation.
