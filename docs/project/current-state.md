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

- PR #90 (`Recover wall-budget-bounded agent timeouts safely`) is merged; source Runtime behavior advanced to `1.0.31`.
- PR #92 (`Make Codex unattended execution fail closed`) is merged at `7d05c68dc36a481fbece98540bc4d0e6888643a2`; post-merge GitHub Actions run #187 passed. Source Runtime behavior advanced to `1.0.32`.
- PR #92 policy: Codex planner/evaluator use `read-only`, execute/repair use `workspace-write`, every Codex Runtime turn uses `approval_policy="never"`, workspace-write network is explicitly disabled, and full-access/bypass flags remain forbidden.
- PR #97 (`Delegate routine PR review and merge to PM`) is merged at `9574cc61a46cecb2ad88ae0983e7cb8eef8fbf7c`; GitHub Actions run #195 passed on exact head `6381507c112cd524d3fd71f3abbebaf69b999535` before PM merge.
- PR #97 updates the Constitution, Architecture, Operating Model, `AGENTS.md`, and continuity policy so PM may review and merge eligible in-scope PRs autonomously after all required gates pass and when no unresolved Human Owner decision trigger exists.
- PR #95 was closed unmerged as superseded; issue #93 was closed completed because its durable shell-command guidance is now included in `AGENTS.md` via PR #97.
- Local rollout now proves Router `1.0.15`, Runtime `1.0.32`, ddev-executor `1.0.14`, model registry `v7`, routing policy `v7`, n8n healthy, and all service-scoped secret boundaries healthy.
- Codex CLI `0.154.0` passed the bounded unattended policy smoke from a disposable trusted Git repository with `workspace-write`, `approval_policy="never"`, and workspace network disabled. The earlier `/app` failure was only a Git trust-location mismatch; no bypass flag was added.
- n8n control-plane sync is complete: `pcpTelegramOutbox1` and `pcpTelegramControl1` are active, Telegram configuration is complete, and the notification schedule executes successfully.
- Issue #101 / PR #102 (`Re-emit attention when owner actions change`) fixes a rollout rematerialization bug: a stable blocked WorkOrder could gain a newly valid control action while the previously sent notification retained the same dedupe key. PR #102 changes notification dedupe to include a deterministic fingerprint of the rendered action set, adds regression coverage, and advances source Runtime to `1.0.33`. Rollout remains pending until PR #102 is merged and local Runtime is rebuilt.
- Durable operator command guidance: avoid fragile nested `python3 -c '...'` quoting, prefer `.format()` or heredocs when they reduce quoting risk, verify `curl | python3` pipelines, and prefer readable multi-line commands.

## Effective PM merge governance

Human Owner decision adopted on 2026-09-14 through issue #96 / PR #97:

- PM may review and merge routine PRs autonomously when the change stays inside the already-approved project frame.
- PR, deterministic verification, required independent review, and green CI remain mandatory gates.
- PM must inspect the WorkOrder/Task Contract, WorkReport, verification evidence, review findings, CI state, unresolved risks, and human-decision triggers before merge.
- Developer agents still cannot merge and must not receive GitHub merge credentials.
- Force push remains forbidden.
- Production deployment is separate from PR merge and remains under existing Human Owner decision policy.
- Human Owner approval is still required for important protected decisions: scope/non-goal changes, architecture invariants, major dependencies/services, authentication/authorization/security/trust boundaries, destructive data changes, production policy/actions, high-authority governance amendments, and material budget expansion.
- If a PR introduces or depends on one of those decisions, PM must pause for explicit Human Owner approval. After approval and remaining green gates, PM may complete the merge.

Runtime currently still has manual-merge orchestration behavior from the previous policy. Issue #98 (`Implement constrained PM-controlled PR merge in Runtime`) tracks executable alignment. The future implementation must keep merge capability behind Runtime -> constrained `ddev-executor`, validate exact PR/head/project/WorkOrder/CI/review/human-decision state, preserve developer-agent credential isolation, and fail closed on stale/replayed/unauthorized merge requests.

## DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- C1 still must satisfy two evaluator findings before normal delivery completion:
  1. derive/verify deployed release identity from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. provide deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks required by AC6.
- Bounded recoveries already approved on the same job without resetting usage:
  - `max_model_calls`: `14 -> 18`;
  - `max_repair_iterations`: `2 -> 3`;
  - `max_iterations`: `8 -> 10`.
- Last pre-timeout live counters included model calls `14/18`, tool calls `36/160`, test runs `6/14`, wall time about `63.515/70`, and repair iterations `2/3`.
- C1 is still the same terminal `failed` job from the Runtime `1.0.30` wall-budget timeout bug. Runtime `1.0.32` compatibility matching recognizes this exact legacy timeout as a bounded wall-time recovery candidate.
- Orchestration reconciliation correctly keeps C1 WorkOrder `blocked`, but the already-sent blocked notification prevented the newly valid `max_wall_time_minutes +20` action from being delivered because the old notification dedupe key did not include the available action set. This is issue #101 / PR #102.
- Do not manually change DB state, create a replacement C1 job, call generic `/v1/jobs/{job_id}/run`, or manually claim notification leases to bypass orchestration controls.
- C2/C3 remain gated until C1 satisfies both evaluator findings and clears its delivery/merge gate under the effective governance policy.

## Next safe sequence

1. Finish PR #102: exact-head CI/review, PM merge if all routine gates remain green and no Human Owner decision trigger appears.
2. Pull merged `main`. Because C1 is terminal `failed` and no jobs are active, rebuild only `coding-runtime` to activate Runtime `1.0.33`; verify platform health and version afterward.
3. Trigger orchestration reconciliation. The same blocked C1 state should emit one fresh notification because the rendered action-set fingerprint is now part of dedupe.
4. Confirm Telegram receives the C1 owner notification with the exact bounded `max_wall_time_minutes +20` action. Execute only that official live-revalidated control action.
5. Confirm the same job/workspace/source commit/diff/progress/counters are preserved and monitor C1 through verification/evaluation/delivery.
6. Any later budget extension must come from a fresh live blocker/action only.
7. Issue #98 remains follow-up platform work to align Runtime/ddev-executor merge behavior with the new PM merge-governance policy; it must not block the current Codex timeout recovery unless the current C1 delivery gate reaches a merge state that requires the new capability.

## Global operational gates

- Do not commit implementation work directly to `main`; use issue -> `ai/*` branch -> tests/CI -> PR.
- Never force push.
- Developer agents never merge.
- PM may merge only after required gates pass and only when no unresolved Human Owner decision trigger exists.
- Human Owner remains final authority over important protected decisions listed in the Constitution.
- Do not restart Runtime/DDEV while a job is in flight. Terminal `failed`/stable blocked states may be restarted when needed for an approved rollout.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.
- Developer agents remain inside the approved isolated workspace/sandbox boundary; avoiding human approval prompts is not permission to grant host-level full access.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
