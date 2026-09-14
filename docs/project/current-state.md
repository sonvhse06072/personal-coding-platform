# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. Durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-14

## How to resume in a new chat or agent session

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/project/README.md`;
3. this file;
4. every topical project document referenced below;
5. the active GitHub issue/PR and current branch diff before editing.

Do not rely on chat history as project state. Repository docs and current executable evidence win according to the authority order in `AGENTS.md`.

## Mandatory continuity rule

Before a material task is complete or handed off, update the relevant topical document for durable decisions and update this file for mutable execution state. Handoff prompts to Codex/platform agents must require those documentation updates as part of Definition of Done.

## Current repository state

- PR #90 (`Recover wall-budget-bounded agent timeouts safely`) is merged at main commit `f698ccc5a687ecc012305c17391c5b40194cb29d`; issue #89 is closed.
- PR #90 changes Runtime source behavior from `1.0.30` to `1.0.31`: typed coding-command timeouts, wall-budget-aware recoverable blocking, and narrow compatibility recovery for the already-failed DEC-025C C1 job.
- The last proven deployed platform before that rollout remains Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`, OpenCode adapter available, n8n healthy, and OpenRouter secret scoped only to Runtime.
- OpenRouter rollout is operational with explicit upstream free model `cohere/north-mini-code:free`; stable logical PCP model ID remains `openrouter_qwen3_coder_free`.

## Active work

### 1. Codex unattended execution policy — issue #91 / PR #92

- Issue: `personal-coding-platform` #91 (`Make Codex unattended execution policy explicit`).
- Branch: `fix/codex-unattended-policy-91`.
- PR: #92 (`Make Codex unattended execution fail closed`).
- Human Owner decision: Codex must not receive full machine access merely to avoid interactive approval.
- Implemented policy on the PR branch:
  - planner/evaluator: `read-only` sandbox;
  - execute/repair: `workspace-write` sandbox;
  - every Codex Runtime turn: `approval_policy="never"`;
  - workspace-write network access: explicitly `false`;
  - `danger-full-access` and approval/sandbox bypass flags remain forbidden.
- Commands that require permission outside the selected sandbox must fail closed instead of waiting for an interactive approval that Runtime cannot answer.
- Runtime behavior/version on this branch is `1.0.32`.
- Focused adapter tests assert the non-interactive policy for execute, plan and evaluate modes and guard against full-access regression.
- `docs/project/architecture.md` records this as the approved developer-agent trust-boundary policy.
- Full GitHub CI and Human Owner manual merge are required. Do not auto-merge.

### 2. DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- C1 still must satisfy two evaluator findings before its normal PR/CI/manual-merge gate:
  1. derive/verify deployed release identity from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. provide deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks required by AC6.
- Bounded recoveries already approved on the same job without resetting usage:
  - `max_model_calls`: `14 -> 18`;
  - `max_repair_iterations`: `2 -> 3`;
  - `max_iterations`: `8 -> 10`.
- Last pre-timeout live counters included model calls `14/18`, tool calls `36/160`, test runs `6/14`, wall time about `63.515/70`, and repair iterations `2/3`.
- C1 remains terminal `failed` from the Runtime `1.0.30` wall-budget timeout bug until the merged timeout-recovery behavior is rolled out and the official compatibility control action reopens the exact same job.
- Do not manually change DB state, create a replacement C1 job, or call generic `/v1/jobs/{job_id}/run` to bypass orchestration controls.
- C2/C3 remain gated until C1 satisfies both evaluator findings and reaches its normal PR/CI/manual-merge gate.

## Next safe sequence

1. Let PR #92 run full GitHub CI. Repair only on the same branch/PR if required.
2. Human Owner manually merges PR #92 after green CI.
3. Because C1 is terminal `failed`, pull merged `main` and restart/sync only as required to activate Runtime `1.0.32`. This single rollout includes the already-merged #89 timeout recovery plus the #91 Codex policy; do not perform an unnecessary intermediate `1.0.31` rollout first.
4. Verify platform health and Runtime `1.0.32`; verify the installed Codex CLI accepts the explicit config policy with a bounded non-mutating smoke before relying on it for C1.
5. Trigger orchestration reconciliation and inspect the newly materialized live control action for the same C1 job. Expected only if the compatibility matcher validates the persisted legacy state: `max_wall_time_minutes +20`.
6. Execute recovery only through the official live-revalidated control action. Preserve the same job/workspace/source commit/diff/progress/counters.
7. Monitor C1 through verification/evaluation/delivery. Any later budget extension must be based on a fresh live blocker/action only.
8. C1 must fix both evaluator findings and reach PR/green-CI/Human-merge before C2/C3 proceed.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight. Terminal `failed`/stable blocked states may be restarted when needed for an approved rollout.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.
- Developer agents remain inside the approved isolated workspace/sandbox boundary; avoiding human approval prompts is not permission to grant host-level full access.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
