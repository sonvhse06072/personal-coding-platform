# Roadmap

Status: approved implementation order for the next phase of the Personal Coding Platform.

This roadmap is a planning artifact beneath the Project Constitution. PM may reorder or split in-scope implementation work when evidence requires it, but may not change project intent or architecture invariants without human approval.

## Guiding principle

Build the smallest layer that enables the next layer safely. Do not add swarm infrastructure, dashboards, or model orchestration complexity before the underlying team contracts and source-of-truth rules are durable.

## Phase 0 — Trust-boundary hardening

Goal: developer workers must be safe enough to become a reusable primitive for later PM-driven orchestration.

Status:

- Runtime API auth fail-closed: complete.
- Router API auth fail-closed: complete.
- ddev-executor auth fail-closed: complete.
- n8n service-scoped secret boundary: complete.
- Antigravity bridge secret/process boundary: complete.
- developer-agent child credential isolation: implementation in PR #33 at the time this roadmap was written; must be merged only after CI and live verification.

Exit criteria:

- coding agents cannot inherit platform-internal credentials or unrelated provider keys;
- Runtime/Router/Executor/bridge boundaries fail closed;
- no regression in Codex/OpenCode/Antigravity execution paths.

## Phase 1 — Repository Source of Truth

Goal: ChatGPT, Codex, and future agents can recover project intent and architecture from Git without relying on chat history.

Deliverables:

- root `AGENTS.md`;
- Project Constitution;
- current/target architecture document;
- agent-team operating model;
- roadmap and documentation index;
- README pointer to these documents.

Exit criteria:

- authority order is explicit;
- implemented behavior is clearly separated from approved target behavior;
- PM autonomy and human-decision boundaries are documented;
- future agents know what to read before changing code.

## Phase 2 — Project Baseline / Constitution schema

Goal: make project-level source of truth a first-class, versioned runtime concept rather than only prose documents.

Expected work:

- define ProjectBaseline/ProjectRevision schema;
- reference checked-in project documentation rather than copying large documents into prompts;
- identify required baseline fields: goals, non-goals, requirements, architecture constraints, quality/security policy, budget policy, roadmap frame;
- persist the revision used by each WorkOrder/job;
- validate that requested work references a known approved baseline.

Constraints:

- do not build PM reasoning yet;
- do not create a vector database unless real retrieval evidence justifies it;
- prefer repository paths/sections and just-in-time retrieval.

Exit criteria:

- every future WorkOrder can name the exact project revision it is governed by.

## Phase 3 — WorkOrder / Task Contract

Goal: replace unconstrained developer prompts with bounded, structured engineering contracts.

Expected fields:

- ID and parent initiative/ticket;
- objective;
- source-of-truth revision and relevant references;
- in-scope / out-of-scope;
- acceptance criteria;
- constraints;
- requested logical role;
- deterministic verification requirements;
- risk/profile/budget envelope;
- dependency metadata.

Expected work:

- schema and validation;
- prompt construction from Task Contract;
- persistence/checkpoint integration;
- tests preventing scope/contract loss across repair/resume.

Exit criteria:

- developer agents receive a stable contract whose meaning survives retries, model failover, CI repair, and process restart.

## Phase 4 — Product Manager role: planning and triage

Goal: add PM as a project-reasoning layer above Router/Runtime.

First PM capability should be intentionally narrow:

1. read the approved ProjectBaseline;
2. assess whether a ticket is inside scope;
3. decompose approved work into WorkOrders;
4. identify dependencies, risks, acceptance criteria, and human-decision boundaries;
5. produce/update a mutable ExecutionPlan.

PM must not directly edit code or select a hard-coded model. It requests a logical role/profile; Router performs staffing.

Human gate:

- initial or materially changed Project Plan requires human approval;
- routine in-scope decomposition does not.

Exit criteria:

- one human ticket can become an approved, dependency-aware list of bounded WorkOrders without changing project scope.

## Phase 5 — Developer WorkReport

Goal: make agent-to-PM communication structured and compact.

Expected work:

- WorkReport schema;
- structured result extraction/adaptation from coding agents;
- criteria mapping;
- changed-component/test/risk/assumption/deviation fields;
- blocked/failure report with root cause/evidence/recommendation;
- retain raw logs separately for diagnostics.

Exit criteria:

- PM does not need full raw agent transcripts for routine task decisions.

## Phase 6 — Independent cross-model Reviewer

Goal: challenge developer assumptions and project alignment using a different reasoning path while controlling budget.

Expected work:

- ReviewReport schema;
- reviewer prompt/context package based on Task Contract, relevant diff/files, deterministic verification, WorkReport, and source-of-truth references;
- Router support for reviewer staffing/diversity policy;
- risk-proportionate review requirements;
- critical/security/architecture different-model/provider rule where eligible capacity exists.

Efficiency rule:

- do not embed the maximum full diff by default;
- provide compact evidence and allow reviewer to retrieve additional workspace context just in time.

Exit criteria:

- accepted work has deterministic evidence plus the configured independent-review evidence without unbounded extra model calls.

## Phase 7 — PM post-task synthesis and feedback loop

Goal: make PM choose the next meaningful action from structured evidence.

Inputs:

- WorkOrder;
- WorkReport;
- deterministic verification;
- ReviewReport;
- CI/delivery evidence;
- remaining budget/provider state.

Outputs:

- TaskOutcome: accept, bounded repair, reassign, replan, block, human decision;
- project/execution-plan effects;
- discovered work classified as inside/outside scope;
- next in-scope WorkOrder when appropriate.

PM should not be invoked for every mechanical repair attempt.

Exit criteria:

- after a task finishes or reaches a meaningful failure state, the system can select the next approved action without human intervention unless a decision boundary is reached.

## Phase 8 — ChangeProposal / source-of-truth amendment flow

Goal: make project-frame changes explicit and human-controlled.

Expected work:

- ChangeProposal schema;
- impact analysis fields;
- waiting-human state integration;
- approved/rejected decision record;
- mechanism to require a source-of-truth Git revision before new work uses the amended baseline.

Exit criteria:

- PM can identify that the current project frame must change, but cannot silently make that change.

## Phase 9 — Telemetry-driven staffing and budget calibration

Goal: replace heuristic model-success assumptions with evidence from the user's own projects.

Collect first:

- role/task class;
- model/provider;
- first-pass success;
- repair count;
- CI pass rate;
- reviewer finding rate;
- wall time;
- token/resource use;
- provider failure/quota pressure;
- task outcome.

Then calibrate Router decisions by project/task/role where sample size is meaningful.

Do not prematurely add statistical complexity from very small samples.

Exit criteria:

- model staffing decisions can cite observed project performance rather than only hand-authored capability/base-success values.

## Phase 10 — Efficiency improvements driven by evidence

Candidates, only after telemetry demonstrates value:

- cheap pre-edit baseline tests;
- narrower intermediate verification before final full checks;
- lightweight structural repo map;
- smarter context compaction;
- provider/quota resource weights beyond USD;
- carefully bounded parallel WorkOrders.

These are optimizations, not prerequisites for the PM/team model.

## Deferred until demonstrated need

Do not build these merely because multi-agent systems often include them:

- always-on parallel agent swarm;
- Best-of-N implementation generation for routine work;
- recursive reviewer-of-reviewer loops;
- automatic PR merge;
- production deployment by agents;
- large vector/RAG infrastructure for code retrieval;
- separate containers/services for PM, developer, QA, architect, and reviewer roles;
- complex provider quota dashboards before enough telemetry exists;
- additional model gateways/services with no active use case.

## Current development workflow while building the platform

Until the internal PM/team loop is complete, dogfood the target model manually:

```text
Human Owner
  -> ChatGPT High: architecture / WorkOrder / review
  -> Codex or bounded implementation agent: implementation / tests / repair
  -> ChatGPT High or alternate model: independent review
  -> GitHub CI
  -> Human Owner: merge
```

For very small, obvious patches, direct implementation may be acceptable, but non-trivial subsystem work should follow the WorkOrder/review pattern.
