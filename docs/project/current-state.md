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
- PR #92 (`Make Codex unattended execution fail closed`) is merged at `7d05c68dc36a481fbece98540bc4d0e6888643a2`; post-merge GitHub Actions run #187 passed. Source Runtime behavior is `1.0.32`.
- PR #92 policy: Codex planner/evaluator use `read-only`, execute/repair use `workspace-write`, every Codex Runtime turn uses `approval_policy="never"`, workspace-write network is explicitly disabled, and full-access/bypass flags remain forbidden.
- The last proven deployed platform before the current rollout work was Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`, OpenCode adapter available, n8n healthy, and OpenRouter secret scoped only to Runtime.
- During rollout smoke testing, invoking Codex from `/app` failed before the prompt because `/app` is not a trusted Git repository. The next bounded smoke must use a temporary Git repository or a real isolated job workspace; do not add `--skip-git-repo-check` merely to hide the mismatch.
- Operator command guidance is now intended to be durable: avoid fragile nested `python3 -c '...'` quoting, prefer `.format()` or heredocs when they reduce quoting risk, verify `curl | python3` pipelines, and prefer readable multi-line commands.

## Active governance amendment — issue #96 / PR #97

Human Owner decision on 2026-09-14:

- PM may review and merge routine PRs autonomously when the change stays inside the already-approved project frame.
- PR, deterministic verification, required independent review, and green CI remain mandatory gates.
- PM must inspect the WorkOrder/Task Contract, WorkReport, verification evidence, review findings, CI state, unresolved risks, and human-decision triggers before merge.
- Developer agents still cannot merge and must not receive GitHub merge credentials.
- Force push remains forbidden.
- Production deployment is separate from PR merge and remains under existing Human Owner decision policy.
- Human Owner approval is still required for important protected decisions: scope/non-goal changes, architecture invariants, major dependencies/services, authentication/authorization/security/trust boundaries, destructive data changes, production policy/actions, high-authority governance amendments, and material budget expansion.
- If a PR introduces or depends on one of those decisions, PM must pause for explicit Human Owner approval. After approval and remaining green gates, PM may complete the merge.

Implementation artifacts:

- Issue #96: `Allow PM-reviewed autonomous PR merge within approved scope`.
- Branch: `ai/pm-autonomous-merge-policy-96`.
- PR #97: `Delegate routine PR review and merge to PM`.
- PR #97 updates `constitution.md`, `architecture.md`, `operating-model.md`, `AGENTS.md`, and this continuity file.
- Issue #96 records explicit transitional Human Owner authorization for PM to merge PR #97 itself after CI/review gates pass, because this PR enacts the new merge-governance rule.
- Runtime currently still has manual-merge orchestration behavior from the previous policy. Treat that as transitional implementation state. A separate implementation PR is required to add constrained PM-controlled merge through Runtime/ddev-executor; do not broaden developer-agent privileges.
- PR #95 (`Document safer operator shell command patterns`) is superseded by PR #97 because the durable shell-command guidance is included in `AGENTS.md` here. Close #95 after #97 is merged rather than merging duplicate/stale continuity changes.

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
- C1 remains terminal `failed` from the Runtime `1.0.30` wall-budget timeout bug until Runtime `1.0.32` rollout/smoke verification is complete and the official compatibility control action reopens the exact same job.
- Do not manually change DB state, create a replacement C1 job, or call generic `/v1/jobs/{job_id}/run` to bypass orchestration controls.
- C2/C3 remain gated until C1 satisfies both evaluator findings and clears its delivery/merge gate under the effective governance policy.

## Next safe sequence

1. Let PR #97 CI complete; PM reviews the exact diff and CI evidence.
2. Because the Human Owner explicitly approved this governance amendment in issue #96, PM may merge PR #97 when green without an additional human merge step.
3. Close superseded PR #95 after #97 is merged.
4. Resume Runtime `1.0.32` rollout validation: confirm platform health, installed Codex CLI version, and run the bounded non-mutating Codex smoke inside a trusted temporary Git repo or actual isolated workspace.
5. Trigger orchestration reconciliation and inspect the live control action for the same C1 job. Expected only if the compatibility matcher validates the persisted legacy state: `max_wall_time_minutes +20`.
6. Execute recovery only through the official live-revalidated control action. Preserve the same job/workspace/source commit/diff/progress/counters.
7. Continue C1 through verification/evaluation/delivery.
8. Separately implement constrained PM-controlled merge support in Runtime/ddev-executor so executable behavior matches the new approved policy; preserve developer-agent credential isolation and fail closed on unresolved Human Owner decision triggers.

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
