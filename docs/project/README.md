# Project Source of Truth

This directory contains the authoritative project-level guidance for the Personal Coding Platform.

These documents are intentionally stored in the repository so ChatGPT, Codex, and future platform agents can recover project intent and current execution context from source control without depending on chat history.

## Documents

- `constitution.md` — project purpose, authority hierarchy, non-negotiable invariants, human decision boundaries, and change-control rules.
- `architecture.md` — current system architecture and the approved target architecture for the small-agent-team model.
- `operating-model.md` — responsibilities and communication contracts for Human Owner, Product Manager, Router, Runtime, Developer, Reviewer, and n8n.
- `provider-policy.md` — provider/model resource tiers, Router authority, privacy/failover rules, and the approved OpenRouter opportunistic free-tier policy.
- `roadmap.md` — implementation sequence, current priorities, and explicitly deferred work.
- `current-state.md` — mutable cross-chat handoff snapshot: active work, branches/issues/PRs/WorkOrders/jobs, blockers, evidence, next safe actions, and operational gates.
- additional topical policy documents may be added as approved decisions require them; `current-state.md` should point a new session to the relevant ones.

## Resume workflow for a new chat or agent

When starting without prior conversation context:

1. read repository-root `AGENTS.md`;
2. read this file;
3. read `current-state.md`;
4. read the topical documents referenced by the active work;
5. inspect the active issue/PR, current branch diff, implementation and tests before making changes.

The intended user workflow is that the Human Owner can say "read the project docs and continue" and the repository contains enough durable context to resume safely.

## Authority

If two sources disagree, follow the authority order defined in `constitution.md` and summarized in the repository-root `AGENTS.md`.

The documents distinguish between:

- **Current implementation** — behavior already present on `main`.
- **Approved target** — behavior we have agreed to build but that may not yet exist.
- **Current execution state** — mutable work-in-progress recorded in `current-state.md`; it does not override architecture/policy authority.

Agents must not treat an approved target as already implemented. The code and tests remain the source of truth for current executable behavior.

## Mandatory continuity updates

Every material decision, implementation-state change, blocker, rollout choice, or handoff must be reflected in repository docs before the work is considered safely complete/handed off, regardless of whether ChatGPT, Codex, or the platform executed the work.

Use two layers:

- **durable decision:** update the relevant topical source-of-truth document;
- **mutable execution state:** update `current-state.md` with the latest status, evidence, blocker, next safe action and owner/operational gates.

Handoff prompts to implementation agents must include documentation updates in the Definition of Done.

Keep `current-state.md` compact: replace stale state rather than appending raw conversation history. Git history provides chronology.

Routine execution work may update lower-level plans and reports, but changes to project goals, non-goals, architecture invariants, major dependencies, security boundaries, production policy, or material budget policy require a human-approved ChangeProposal and a reviewed PR.
