# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. Durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-15

## How to resume in a new chat or agent session

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/project/README.md`;
3. this file;
4. every topical project document referenced below;
5. the active GitHub issue/PR and current branch diff before editing.

Do not rely on chat history as project state. Repository docs and current executable evidence win according to the authority order in `AGENTS.md`.

## Mandatory continuity rule

Before a material task is complete or handed off, update the relevant topical document for durable decisions and update this file for mutable execution state. Handoff prompts to implementation agents must require those documentation updates as part of Definition of Done.

Keep this file compact and current. Replace stale operational state rather than appending chronology; Git history is the audit trail.

## Current platform baseline

Key merged platform work now in `main` includes:

- PM routine PR merge governance: PR #97 / merge `9574cc61a46cecb2ad88ae0983e7cb8eef8fbf7c`.
- Runtime attention-action fingerprinting: PR #102 / merge `bdba1a34d3f154f0e0e1e757cc7a341a188645b2`.
- Telegram callback acknowledgement hardening: PR #106 / merge `03cd3a918fbf1de8f4ad1eabdd844d45f2ec8e73`.
- Live Developer Activity across providers: PR #114 and PR #118.
- Provider/model quota-aware routing policy: PR #126; Router source release `1.0.16`, model registry/routing policy `v8`.
- Proactive provider quota telemetry: PR #129, followed by Antigravity proactive refresh PR #131 and safety/worktree fixes #133/#135.
- Antigravity host bridge source release `1.10`; proactive quota probing preserves required safety settings.
- Multi-budget provider recovery: PR #137 / merge `1c2d7a4d8299a44cb045dfb7d3c5f204b270e8ea`; Runtime source release `1.0.38`.
- Telegram terminal operations design: PR #139 / merge `9683250a7669b47e9d81f6df648bb769ca5e3893`; approved target only, not implemented.

Current important executable/governance gap:

- issue #98 still tracks constrained PM-controlled PR merge in Runtime/ddev-executor. Governance allows PM routine merge, but executable orchestration must still be aligned before claiming the full zero-human-touch happy path.

## Initiative #140 — personal-budget execution efficiency

Human Owner approved the full initiative on 2026-09-15.

Authoritative policy document: `docs/project/execution-efficiency.md`.

Parent issue: #140 `Optimize PCP for personal-budget autonomous team execution`.

Implementation workstreams:

1. #141 — Adaptive task budgeting and Human Attention Budget.
2. #142 — Layered verification and failure-budget separation.
3. #143 — Bounded inter-agent collaboration and review dialogue.
4. #144 — Risk-proportionate review and role-specific Evidence Packs.
5. #145 — Telemetry calibration and automatic continuity maintenance.
6. #98 — constrained PM-controlled merge, integrated into the autonomous happy path.

Current source-of-truth amendment branch: `ai/personal-budget-efficiency-140`.

Policy summary:

- healthy routine tasks should target zero avoidable Human Owner interventions;
- fixed profile budgets become priors/estimates rather than routine stop points;
- task execution moves toward estimate -> elastic working envelope -> emergency hard ceiling;
- anti-loop/no-progress/oscillation/scope-growth signals are the primary circuit breakers;
- provider quota/resource state remains separate from task estimates;
- layered verification reduces redundant full-suite runs but required final deterministic verification/CI remain mandatory;
- provider/infra/verification/delivery retries must not be miscounted as engineering repair;
- inter-agent consultation is selective, bounded, role-based and single-writer by default;
- review strength/context are risk/value proportional;
- Human Attention is an explicit efficiency resource/metric;
- convenience work such as the Telegram terminal gateway is lower priority than these execution-efficiency changes.

## DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- Branch: `ai/eec59b13651c`.
- Workspace identity remains the same job/workspace throughout recovery.
- A multi-budget recovery action already executed successfully on the same job, extending wall time `90 -> 110` and iterations `12 -> 14`, after which C1 progressed through verification into reassessment.
- Current durable C1 state is blocked at reassessment with reason `reassessment_stopped`; reassessment reason is `repair budget exhausted` with `hard_budget_guard`.
- Current observed counters at that block: model calls `21/22`, tool calls `65/160`, test runs `14/14`, wall time `93.168/110`, repair iterations `4/4`.
- Fresh current recovery action is `budget_extend` for `max_repair_iterations +1`; do not use older provider-era actions even if stale rows remain stored.
- This C1 behavior is one of the direct evidence inputs for initiative #140: the execution was still making meaningful progress but repeatedly encountered profile/task ceilings that required Human Owner continuation.
- C2/C3 remain gated until C1 satisfies C1 Definition of Done and clears delivery/merge gates.

Do not manually mutate C1 database/job state, replace the job, reset counters, or call generic `/v1/jobs/{job_id}/run`. Use only current official orchestrator/control actions.

## Provider quota/resource state

Quota telemetry is an independent fail-open resource signal and does not consume WorkOrder model/tool/test counters.

Recent verified Antigravity buckets from the safe Bridge 1.10 path showed:

- Gemini weekly bucket exhausted at the observed snapshot;
- Claude/GPT weekly bucket available with full observed headroom at that snapshot.

Codex quota telemetry is collected through the supported app-server rate-limit interface. Router should treat fresh authoritative exhaustion as unavailable and non-exhausted pressure as a routing resource signal; stale/unknown telemetry must not fabricate values.

## PM merge governance

Effective policy from issue #96 / PR #97:

- PM may review and merge routine in-scope PRs when deterministic verification, required independent review and CI gates pass and no Human Owner decision trigger remains.
- Developer agents never merge and never receive GitHub merge credentials.
- Force push remains forbidden.
- Production deployment is separate and remains Human Owner-controlled under existing policy.
- Human Owner approval remains required for scope/non-goal changes, architecture invariants, major dependencies/services, authentication/authorization/security/trust boundaries, destructive data changes, production policy/actions, high-authority governance amendments and material project/personal budget expansion.
- Issue #98 is the executable implementation gap for this policy.

## Telegram terminal operations target

Authoritative document: `docs/project/telegram-terminal-operations.md`.

Approved convention remains:

- normal ChatGPT read-only diagnostics use ordinary terminal-safe blocks by default;
- Telegram-ready formatting is emitted only when Human Owner explicitly requests it;
- planned terminal bot is separate from the PCP governance/notification bot;
- `/run-ro` must be capability-restricted rather than regex-classified;
- `/run-op` is later bounded named operations with confirmation;
- generic `/run-admin` remains disabled by default.

Implementation is intentionally lower priority than initiative #140.

## Global operational gates

- Do not commit implementation work directly to `main`; use issue -> `ai/*` branch -> tests/CI -> PR.
- Never force push.
- Developer agents never merge.
- PM may merge only after required gates pass and only when no unresolved Human Owner decision trigger exists.
- Human Owner remains final authority over protected decisions listed in the Constitution.
- Do not restart Runtime/DDEV/n8n while an engineering job is active. Stable blocked/terminal states may be used for approved targeted rollout when required.
- Runtime durable state is authoritative; never mutate job/database state manually to bypass the state machine.
- Provider/control-plane credentials remain service-scoped and must never be committed to docs or sent intentionally to model prompts.
- Developer agents remain inside isolated workspace/sandbox boundaries; autonomy is not permission for host-level full access.
- Routine healthy execution inside an approved task working envelope should increasingly continue autonomously as #141–#145 are implemented; until then, current executable hard-budget behavior still applies.

## Updating this file

After material merge, rollout, terminal job transition, or governance decision, replace stale state here with the smallest current snapshot a future session needs. Issue #145 will make this maintenance increasingly automatic.
