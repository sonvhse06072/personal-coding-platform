# Agent Instructions

This repository is the source of truth for the Personal Coding Platform. Coding agents must treat the checked-in project documents and implementation as authoritative; chat history, prior agent output, and remembered context are secondary.

## Required reading order

Before proposing or implementing a non-trivial change, read:

1. `docs/project/constitution.md`
2. `docs/project/architecture.md`
3. `docs/project/operating-model.md`
4. `docs/project/roadmap.md`
5. `docs/project/current-state.md`
6. every topical project document referenced by the active work
7. the relevant implementation, tests, configuration, active issue/PR and current branch diff

For operational setup and current commands, also read `README.md`.

A new chat or agent session must not require the previous conversation to resume work safely. If the Human Owner asks to "read the project docs and continue", the repository source of truth plus current executable evidence must be sufficient to reconstruct the active context.

## Authority order

When sources conflict, use this order:

1. Project Constitution and explicitly approved amendments
2. Approved architecture decisions and architecture invariants
3. Product/project requirements and approved roadmap
4. Operating model, quality gates, security policy, and budget policy
5. WorkOrder / Task Contract for the current task
6. Current implementation and tests
7. Developer/reviewer reports and other runtime evidence

`docs/project/current-state.md` is a continuity/handoff index, not permission to override a higher-authority source. It records the latest mutable execution state and points to the authoritative topical documents and evidence.

Lower-authority artifacts must not silently redefine higher-authority artifacts. If a requested change conflicts with a higher-authority source, stop at the decision boundary and produce a change proposal instead of implementing the conflict.

## Core invariants

- The platform is a personal, budget-conscious system that models a small software-development team using logical agent roles.
- The human owner and Product Manager establish project scope and the initial plan. After baseline approval, the PM executes within that frame; it does not invent new product scope.
- PM, developer, reviewer, and specialist are logical roles, not dedicated infrastructure services.
- The Router is a deterministic staffing/budget policy engine. It does not own product direction.
- Runtime owns job state, bounded execution, checkpoints, retries, verification, and delivery. It does not own product direction.
- n8n remains a thin integration/control-plane layer. It must not contain coding intelligence, routing policy, project state, or model-selection logic.
- Coding agents work only in isolated job workspaces and must not possess Runtime, Router, executor, GitHub-delivery, or unrelated provider credentials.
- Only `ddev-executor` may hold Docker-socket/source-repository/GitHub-delivery capabilities required for bounded delivery.
- Agent changes go through an `ai/*` branch and pull request. Force push and production deployment remain forbidden.
- PM may review and merge a PR autonomously only when the work is inside the approved project frame, all required deterministic/review/CI gates pass, and no unresolved Human Owner decision trigger exists.
- Developer agents must never merge.
- Deterministic verification is authoritative for executable checks; model review supplements it rather than replacing it.
- Important product, architecture, security, destructive-data, production, major-dependency, governance, and material budget decisions require human approval.
- Default execution concurrency is one. Parallel agent work is an explicit optimization only for independent WorkOrders.

## Change discipline

- Prefer one bounded issue/WorkOrder and one PR at a time.
- Read existing code and tests before editing.
- Keep changes minimal and do not refactor unrelated code.
- Do not weaken a trust boundary to make an agent/tool easier to run.
- Do not add infrastructure, agents, services, frameworks, or model calls without a demonstrated project need.
- New automation should reduce failure rate, reduce model/tool time, or strengthen a security/governance boundary.
- Preserve budget limits and anti-loop behavior; escalation must not reset consumed job budget.
- A CI-green PR is a mandatory gate before a task is considered ready for merge.
- Before merge, PM must review the WorkOrder/Task Contract, developer evidence, deterministic verification, independent review when required, CI state, unresolved risks, and any Human Owner decision triggers.
- PM must not merge while a required human decision is unresolved. Once the Human Owner explicitly approves such a decision, PM may complete the merge after the remaining gates pass.

## Operator command authoring

- Avoid `python3 -c '...'` when the embedded Python code itself needs single-quoted expressions that can collide with the shell delimiter.
- Prefer `.format()` or a heredoc when either approach reduces nested shell/Python quoting risk.
- For `curl | python3` pipelines, verify both the shell quoting and the Python quoting before presenting the command.
- Prefer readable multi-line commands over fragile one-liners when a command is moderately complex.
- Treat the Human Owner's interactive Ubuntu/WSL shell as persistent operator state. Do not provide a pasted command block that can intentionally return non-zero or call `exit` while `set -e`/`set -euo pipefail` is active in the parent interactive shell if that could terminate the shell/session.
- Any operator validation block that may intentionally fail, use `exit N`, or stop on a failed gate must run inside an explicit subshell `( ... )` or a standalone script/process. Non-zero status must terminate only that isolated process, never the Human Owner's parent shell.
- When using a subshell, capture/report the subshell return code after `)` when useful so the Human Owner can distinguish `PASS`, a controlled gate failure, and an unexpected command failure without losing the terminal session.
- For rollout/restart/deploy gates, default to a fail-closed subshell pattern: perform read-only checks first, print a clear stop reason, return non-zero from the subshell, and do not place the mutating restart/rebuild command in the same block unless all prerequisites have already passed.

## Mandatory documentation continuity

Every material decision or state transition must be reflected in repository documentation before the work is considered complete or safely handed off, whether the work was performed by ChatGPT, Codex, or the platform itself.

Update the relevant topical source-of-truth document when a durable decision changes. Update `docs/project/current-state.md` whenever active execution context changes materially, including issue/branch/PR/WorkOrder/job state, completed work, blockers, verification evidence, next safe action, or rollout/merge/restart/deploy gates.

Do not append an unbounded chat transcript to project docs. Keep the current-state document compact and replace stale state; Git history is the audit trail.

When delegating implementation to Codex/platform agents, the handoff prompt must require documentation updates as an explicit Definition-of-Done item.

## Planned team artifacts

The target operating model uses versioned, structured artifacts:

- Project Constitution / approved project baseline
- Execution Plan
- WorkOrder / Task Contract
- Developer WorkReport
- independent ReviewReport
- PM TaskOutcome / next-action decision
- ChangeProposal for any requested change to the approved project frame

Until these are implemented in Runtime, use the documents in `docs/project/` and GitHub issue/PR descriptions as their human-readable equivalents.
