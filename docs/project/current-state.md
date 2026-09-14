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
- PR #102 (`Re-emit attention when owner actions change`) is merged at `bdba1a34d3f154f0e0e1e757cc7a341a188645b2`; exact-head GitHub Actions run #201 passed before PM merge. Issue #101 is resolved. Source Runtime is `1.0.33`.
- PR #102 fixes a rollout rematerialization bug: attention notification dedupe includes a deterministic fingerprint of the rendered control-action set, so a stable blocked/waiting/merge state emits one fresh owner notification when newly valid actions appear while repeated ticks with the same action set remain deduped.
- PR #106 (`Keep Telegram callback acknowledgement non-blocking`) is merged at `03cd3a918fbf1de8f4ad1eabdd844d45f2ec8e73`; exact-head GitHub Actions run #205 passed before PM merge. Issue #105 is resolved.
- PR #106 makes Telegram `answerCallbackQuery` best-effort in `pcpTelegramControl1`, so Telegram HTTP 400 acknowledgement failures cannot prevent a valid opaque Runtime control action from being attempted. Runtime remains authoritative for owner identity, stale/replayed action rejection and one-time live state revalidation.
- Local rollout proves Router `1.0.15`, Runtime `1.0.33`, ddev-executor `1.0.14`, model registry `v7`, routing policy `v7`, n8n healthy, and all service-scoped secret boundaries healthy.
- Codex CLI `0.154.0` passed the bounded unattended policy smoke from a disposable trusted Git repository with `workspace-write`, `approval_policy="never"`, and workspace network disabled. The earlier `/app` failure was only a Git trust-location mismatch; no bypass flag was added.
- Issue #109 / PR #114 (`Stream sanitized live developer transcript`) is active platform work approved by the Human Owner. It incrementally consumes Codex `--json` stdout, persists only bounded sanitized developer/tool/file/error events, adds authenticated replay + SSE under the existing read-only dashboard session, and makes the Live Developer Console the primary active-job view while preserving a separate high-level audit timeline.
- PR #114 explicitly excludes raw chain-of-thought/reasoning, prompts, credentials, unrestricted environment data and unbounded subprocess output. Observability callback/store failures are fail-open for the coding job; Runtime execution/control semantics remain authoritative and unchanged.
- Initial PR #114 CI run #209 found two compatibility regressions only; both were corrected. Exact-head run #211 passed all four CI jobs before the continuity update. A final exact-head CI run is still required after this documentation commit.
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
  - `max_iterations`: `8 -> 10`;
  - compatibility recovery: `max_wall_time_minutes +20` only when the persisted legacy timeout matches live policy.
- The Human Owner reports that the exact C1 job is currently running after recovery. Treat Runtime durable state as authoritative and re-read it before any operator action.
- While C1 remains in an active state, do not restart/rebuild Runtime, DDEV or n8n; do not roll out PR #114; do not mutate its workspace/job/database state; and do not create a replacement C1 job.
- Do not call generic `/v1/jobs/{job_id}/run`, manually claim notification leases or otherwise bypass orchestration controls.
- C2/C3 remain gated until C1 satisfies both evaluator findings and clears its delivery/merge gate under the effective governance policy.

## Live Developer Console rollout gate

1. Continue issue #109 / PR #114 entirely as repository + CI work while C1 is active. Merging the PR is allowed after all normal PM gates pass because merge alone does not restart the local Runtime.
2. Do not pull/rebuild/restart the local platform for PR #114 while C1 is active. The current running Runtime must remain undisturbed.
3. After C1 reaches a safe terminal or stably paused state, re-read platform/job status first. Only then plan the targeted Runtime rollout for the Live Developer Console.
4. After rollout, verify the read-only dashboard session, recent-event replay and SSE stream with a bounded disposable/safe coding job before relying on the console operationally.
5. Confirm that dashboard disconnect/reconnect never changes job status or execution, secrets/prompts/reasoning remain absent, and streamed events remain bounded/sanitized.
6. Issue #98 remains separate follow-up work for constrained PM-controlled PR merge behavior.

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
