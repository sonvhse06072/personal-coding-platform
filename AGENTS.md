# Agent Instructions

This repository is the source of truth for the Personal Coding Platform. Coding agents must treat the checked-in project documents and implementation as authoritative; chat history, prior agent output, and remembered context are secondary.

## Required reading order

Before proposing or implementing a non-trivial change, read:

1. `docs/project/constitution.md`
2. `docs/project/architecture.md`
3. `docs/project/operating-model.md`
4. `docs/project/roadmap.md`
5. the relevant implementation, tests, and configuration

For operational setup and current commands, also read `README.md`.

## Authority order

When sources conflict, use this order:

1. Project Constitution and explicitly approved amendments
2. Approved architecture decisions and architecture invariants
3. Product/project requirements and approved roadmap
4. Operating model, quality gates, security policy, and budget policy
5. WorkOrder / Task Contract for the current task
6. Current implementation and tests
7. Developer/reviewer reports and other runtime evidence

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
- Agent changes go through an `ai/*` branch and pull request. No force push, no automatic merge, and no production deployment.
- Deterministic verification is authoritative for executable checks; model review supplements it rather than replacing it.
- Important product, architecture, security, destructive-data, production, major-dependency, and material budget decisions require human approval.
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
- Never merge automatically. The human owner performs the final merge.

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
