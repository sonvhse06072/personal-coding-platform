# Project Source of Truth

This directory contains the authoritative project-level guidance for the Personal Coding Platform.

These documents are intentionally stored in the repository so ChatGPT, Codex, and future platform agents can recover project intent from source control without depending on chat history.

## Documents

- `constitution.md` — project purpose, authority hierarchy, non-negotiable invariants, human decision boundaries, and change-control rules.
- `architecture.md` — current system architecture and the approved target architecture for the small-agent-team model.
- `operating-model.md` — responsibilities and communication contracts for Human Owner, Product Manager, Router, Runtime, Developer, Reviewer, and n8n.
- `roadmap.md` — implementation sequence, current priorities, and explicitly deferred work.

## Authority

If two sources disagree, follow the authority order defined in `constitution.md` and summarized in the repository-root `AGENTS.md`.

The documents distinguish between:

- **Current implementation** — behavior already present on `main`.
- **Approved target** — behavior we have agreed to build but that may not yet exist.

Agents must not treat an approved target as already implemented. The code and tests remain the source of truth for current executable behavior.

## Updating this source of truth

Routine execution work may update lower-level plans and reports, but changes to project goals, non-goals, architecture invariants, major dependencies, security boundaries, production policy, or material budget policy require a human-approved ChangeProposal and a reviewed PR.
