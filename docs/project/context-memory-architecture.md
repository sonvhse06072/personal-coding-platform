# PCP Context and Memory Architecture

Status: Human Owner-approved architecture direction under #313. Phase 1 is documentation/continuity only; no vector database, embedding service, memory daemon or Runtime retrieval API is implied by this document.

## 1. Objective

PCP needs durable project memory without turning every agent prompt into a replay of the entire project history.

The design separates information by authority, freshness and retrieval cost so an agent can answer three different questions correctly:

1. What must never be forgotten?
2. What is true now?
3. What historical or detailed evidence is relevant to this task?

Git remains the canonical human-auditable store for durable project knowledge. Runtime/PostgreSQL may later hold structured indexes/materialized state, but may not silently override repository governance.

## 2. Memory tiers

### T0 — Pinned governance / procedural memory

Always available to a role when relevant to its authority boundary.

Examples:

- repository-root `AGENTS.md`;
- `constitution.md`;
- authority hierarchy;
- trust/security boundaries;
- Human Owner decision boundaries;
- source-safety and merge/deploy invariants.

T0 must not depend on semantic retrieval. A critical rule is not optional merely because a retriever did not rank it highly.

### T1 — Active working state

A compact replace-in-place snapshot of what is operationally current.

Canonical human-readable artifact:

- `current-state.md`.

Typical contents:

- current platform/service identities;
- active projects and accepted local state;
- open issues/PRs that affect next work;
- active WorkOrders/jobs/leases when known;
- blockers;
- operational gates;
- immediate next safe actions.

T1 is not a chronological log. Completed work leaves T1 once its durable lesson/reference is recorded in T2/T3 or is otherwise recoverable from Git/issue/PR history.

Target: comfortably below ~15 KB and preferably below ~250 lines unless genuine active work requires more.

### T2 — Durable semantic / topical knowledge

Stable reusable knowledge that explains how PCP is designed or operated.

Examples:

- `architecture.md`;
- `operating-model.md`;
- `efficiency-model.md`;
- `provider-policy.md`;
- topical runbooks such as Telegram terminal operations or secret upgrades.

T2 is retrieved just in time by topic, role and task. It is not copied wholesale into every prompt.

### T3 — Episodic history

Compact records of completed incidents, rollouts, migrations and lessons.

Canonical Phase-1 index:

- `history/episodes.md`.

An episode records outcome, durable lesson and authoritative references, not raw logs.

Detailed chronology remains available through Git history, issues, PRs, Runtime durable records and CI.

### T4 — Raw evidence

High-volume or diagnostic evidence fetched only when required.

Examples:

- CI/job logs;
- full WorkReports/ReviewReports;
- raw agent transcripts;
- complete patches;
- Docker/resource inventories;
- detailed diagnostic command output.

T4 must not be default prompt context.

## 3. Authority and freshness

Retrieval relevance never overrides source authority.

When sources conflict, use the existing authority rules from `constitution.md` and `AGENTS.md`. In addition:

1. executable code/tests are authoritative for current executable behavior;
2. T0/T2 repository policy defines approved governance/architecture;
3. T1 defines the current mutable handoff snapshot but cannot override T0/T2;
4. live Runtime/GitHub state must be checked for time-sensitive execution facts;
5. T3 is historical evidence and must not override a current T1/live fact;
6. T4 is supporting evidence and must be interpreted in the state/time context in which it was produced.

A historical item that is semantically similar to a query is still historical.

## 4. Memory lifecycle

Material events should update memory by replacement/consolidation, not accumulation.

### Current-state transition

After a meaningful change:

- replace stale T1 values;
- remove completed initiative chronology from T1;
- keep only the current blocker/gate/next action;
- add or update a compact T3 episode when the completed event has reusable lessons.

### Durable decision

A decision that changes architecture, governance, security, scope or material policy belongs in the relevant T0/T2 document through normal reviewed change control.

### Raw evidence

Raw evidence remains at its native source. Do not duplicate full logs into T1/T3.

## 5. Phase-1 episodic metadata

T3 entries should carry enough structure for deterministic filtering before any future semantic retrieval.

Recommended logical shape:

```yaml
id: rollout-309
project_id: personal-coding-platform
memory_type: episodic
event_type: rollout
date: 2026-09-26
status: historical
title: Project-level Current site rollout
summary: ...
lessons:
  - ...
entities:
  issues: [309]
  prs: [310, 311, 312]
  commits: [...]
tags: [direct-workspace, preview, lease]
valid_from: 2026-09-26
valid_until: null
supersedes: []
sources:
  - github_issue: 309
```

The Markdown index may express this more compactly while preserving the same concepts.

## 6. Future Context Composer contract

Issue #313 Phase 2 may add a deterministic Context Composer. Its initial design must not require embeddings.

Proposed input:

```yaml
project_id: chonhac
role: reviewer
task:
  title: Review direct-preview lifecycle change
  task_type: code_review
references:
  issue: 123
  work_order: optional
token_budget: 8000
```

Proposed output:

```yaml
context_pack_version: 1
pinned:
  - tier: T0
    source: AGENTS.md
  - tier: T1
    source: docs/project/current-state.md
retrieved:
  - tier: T2
    source: docs/project/architecture.md
    sections: [...]
  - tier: T3
    source: docs/project/history/episodes.md
    entries: [...]
evidence_refs:
  - tier: T4
    source: ...
provenance:
  generated_from_main: ...
  query: ...
  retrieval_policy: deterministic-v1
```

The composer must emit source/provenance references and keep a bounded token budget.

## 7. Initial retrieval policy

Before adding vectors, prefer deterministic signals:

1. exact identifiers: project, issue, PR, job, WorkOrder, decision;
2. memory tier;
3. authority;
4. current/historical status;
5. project/task/role tags;
6. heading-aware lexical search;
7. recency only after authority/status filtering.

Future ranking may combine lexical/vector similarity, but stale/superseded penalties and current-state precedence must remain explicit.

## 8. Role-specific packs

### Product Manager

Default:

- T0 authority/governance;
- full compact T1;
- relevant T2 product/architecture/operating policy;
- relevant T3 lessons;
- live GitHub/Runtime evidence for current execution.

### Developer

Default:

- task contract;
- relevant source/tests;
- minimal T0 safety boundaries;
- relevant T2 implementation constraints;
- narrow prior-attempt/T3 lessons when useful.

The developer does not need the full project history.

### Reviewer

Default:

- acceptance/task contract;
- diff/changed files;
- deterministic verification;
- WorkReport;
- relevant T0/T2 risk/governance;
- only the T3 incidents relevant to the reviewed risk.

### Debugger / specialist

Default:

- failure evidence;
- narrow relevant source/config;
- related prior T3 incidents;
- T4 logs only as needed.

## 9. RAG decision gate

PCP must not add a vector database merely because RAG is common in agent systems.

Under #313, a later evaluation set should compare:

- read-all-docs baseline;
- T0/T1 + metadata/lexical retrieval;
- vector retrieval;
- hybrid lexical/vector retrieval.

Measure at least:

- answer correctness;
- current-vs-historical error rate;
- authority-conflict error rate;
- retrieval recall for required evidence;
- abstention when evidence is absent;
- prompt tokens;
- latency/model/tool cost.

Embeddings/vector infrastructure are justified only if they materially improve PCP-specific retrieval after metadata/authority controls are applied.

## 10. Safety and non-goals

Phase 1 does not:

- change Runtime execution semantics;
- add a vector DB;
- add an embedding provider;
- create an autonomous consolidation daemon;
- let retrieved memory override governance;
- delete Git/issue/PR/Runtime audit history;
- weaken source, secret, merge, deployment or Human Owner boundaries.

The simplest architecture that preserves correctness and reduces context pressure should be preferred.
