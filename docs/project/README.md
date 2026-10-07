# Project Source of Truth

This directory contains the authoritative project-level guidance for the Personal Coding Platform.

These documents are intentionally stored in the repository so ChatGPT, Codex, and future platform agents can recover project intent and current execution context from source control without depending on chat history.

## Documents

- `constitution.md` — project purpose, authority hierarchy, non-negotiable invariants, human decision boundaries, and change-control rules.
- `business-strategy.md` — PCP product/business identity, internal investment thesis, north-star metrics, dogfood-to-roadmap rules, portfolio priorities, maturity stages, and the business-value gate for new platform work.
- `architecture.md` — current system architecture and the approved target architecture for the small-agent-team model.
- `operating-model.md` — responsibilities and communication contracts for Human Owner, Product Manager, Router, Runtime, Developer, Reviewer, and n8n.
- `provider-policy.md` — provider/model resource tiers, Router authority, privacy/failover rules, and the approved OpenRouter opportunistic free-tier policy.
- `roadmap.md` — implementation sequence, current priorities, and explicitly deferred work.
- `efficiency-model.md` — Human Owner-approved personal-scale efficiency policy: task-specific adaptive budgets, Human-attention minimization, layered verification, bounded inter-agent collaboration, risk-proportionate review, compact evidence packs, telemetry calibration, and continuity automation.
- `telegram-terminal-operations.md` — approved target design and operator convention for a separate owner-only Telegram terminal operations gateway, including read-only sandbox/broker boundaries and the rule that Telegram-ready diagnostic blocks are emitted only when explicitly requested.
- `service-secret-upgrades.md` — existing-install upgrade procedure for service-scoped credentials, including the required migrate-before-rebuild order and non-secret deployed boundary checks.
- `current-state.md` — Tier-1 mutable working-state snapshot: current active work, last accepted local state, blockers, next safe actions and operational gates. It is replace-in-place state, not a chronological log.
- `context-memory-architecture.md` — Human Owner-approved Tier-0 through Tier-4 context/memory model, authority/freshness rules and future deterministic Context Composer contract.
- `history/episodes.md` — compact Tier-3 index of completed incidents/rollouts and reusable lessons with issue/PR/commit references; detailed chronology remains in Git/GitHub/Runtime history.
- additional topical policy documents may be added as approved decisions require them; T1 should point a new session to the relevant T2/T3 sources rather than copying their full contents.

## Resume workflow for a new chat or agent

When starting without prior conversation context:

1. read repository-root `AGENTS.md` and this index;
2. read the compact Tier-1 `current-state.md`;
3. retrieve only the Tier-2 topical documents and Tier-3 episodes relevant to the active task;
4. inspect live GitHub/Runtime/source state for time-sensitive facts such as current issue/PR, branch/HEAD, job/lease and service health;
5. inspect implementation/tests/diff before changing code;
6. fetch Tier-4 raw logs/transcripts/full evidence only when diagnostics or audit require them.

Do not load every project document merely because it exists. The default context should be T0 governance + compact T1 working state + task-relevant T2/T3 material.

The intended user workflow remains that the Human Owner can say "read the project docs and continue", but the system should recover safe context through bounded tiered retrieval rather than replaying the whole historical corpus.

## Authority

If two sources disagree, follow the authority order defined in `constitution.md` and summarized in the repository-root `AGENTS.md`.

The documents distinguish between:

- **Current implementation** — behavior already present on `main`.
- **Approved target** — behavior we have agreed to build but that may not yet exist.
- **Current execution state** — mutable work-in-progress recorded in `current-state.md`; it does not override architecture/policy authority.

Agents must not treat an approved target as already implemented. The code and tests remain the source of truth for current executable behavior.

## Mandatory continuity updates

Every material decision, implementation-state change, blocker, rollout choice, or handoff must be reflected in repository docs before the work is considered safely complete/handed off, regardless of whether ChatGPT, Codex, or the platform executed the work.

Use the memory tiers defined in `context-memory-architecture.md`:

- **durable decision / T0-T2:** update the relevant governed topical source-of-truth document;
- **mutable execution state / T1:** replace stale values in `current-state.md`;
- **completed reusable lesson / T3:** add or update a compact episodic reference when the event has future diagnostic/retrieval value;
- **raw evidence / T4:** leave logs/transcripts/full diagnostic output at their native audit source unless a bounded reference is needed.

Handoff prompts to implementation agents must include the appropriate documentation/continuity update in the Definition of Done.

Keep `current-state.md` compact and current. Completed chronology must leave T1; Git/GitHub/Runtime history provides the detailed audit trail.

Routine execution work may update lower-level plans and reports, but changes to project goals, non-goals, architecture invariants, major dependencies, security boundaries, production policy, or material budget policy require a human-approved ChangeProposal and a reviewed PR.
