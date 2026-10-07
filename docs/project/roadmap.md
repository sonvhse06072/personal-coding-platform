# Roadmap

Status: approved implementation order for the next phase of the Personal Coding Platform.

This roadmap is a planning artifact beneath the Project Constitution. PM may reorder or split in-scope implementation work when evidence requires it, but may not change project intent or architecture invariants without human approval.

## Guiding principle

Build the smallest layer that enables the next layer safely. Do not add swarm infrastructure, dashboards, or model orchestration complexity before the underlying team contracts and source-of-truth rules are durable.

## Current business/product priority overlay — 2026-10-07

The current business/product strategy is `business-strategy.md`. PCP has moved from broad foundational capability construction into a **consolidation and reliability** stage.

The practical roadmap is therefore narrower than the historical phase list below:

1. **Protect the live end-to-end loop.** Existing PM planning/orchestration, bounded execution, deterministic verification, independent review, GitHub delivery, PM merge, remote PM control and Guardian paths should become predictable before adjacent capability expansion.
2. **Finish existing evidence-backed backlog before new scope.** The only ordinary open PCP engineering issue is #493 (DDEV cold/bootstrap reliability). #512 remains a parent acceptance frame for natural remote-control evidence, not permission for broad new implementation. #524 is a persistent Guardian operations/audit channel, not product backlog.
3. **Treat managed-project dogfood as evidence.** Chợ Nhạc and other managed projects may expose real PCP defects, but an application bug or contract miss stays in the application repo. Open PCP work only for a reusable platform defect/capability gap, recurring owner-cost pattern or broken approved PCP invariant.
4. **Prefer repair/reconciliation over issue multiplication.** If an existing PCP capability is defective, repair that capability/issue before creating a neighboring abstraction or replacement workflow.
5. **Measure before optimizing.** Staffing, budget and review calibration should use meaningful task-outcome samples. Do not add statistical/dashboard complexity merely because telemetry fields exist.
6. **Defer convenience-only expansion.** New remote controls, dashboards, agent roles, parallelism or operator surfaces require a demonstrated reduction in Human Owner attention, recurring failure, resource waste, quality risk or a real blocker to an approved project workflow.

Current evidence:

- RCTL-MVP #513 is completed after live standalone exact-head merge and exact supervised continuation proof.
- Runtime 1.0.130 is live on PCP main `62a89ff59669e68dd73533af7c6851f91c5b44dc`.
- #512 remains open only for natural parent-level evidence such as post-rollout GitHub `direct_intake` and a real control-plane-unavailable Guardian case; do not create synthetic work solely to close those acceptance boundaries.
- #524 intentionally stays open for Guardian command/audit history.

The older phases remain useful architecture/history context. They must not be interpreted as a requirement to continue building every previously imagined layer after the business problem has already been solved by a smaller path.

## Current priority overlay — personal-budget execution efficiency

Human Owner approved initiative #146 on 2026-09-15. The authoritative policy is `efficiency-model.md`.

This initiative takes priority over convenience-only work such as the Telegram terminal gateway because it directly improves autonomous throughput, model/test efficiency, and Human Owner attention.

Implementation order:

1. source-of-truth amendment for the approved execution-efficiency policy;
2. #147 Adaptive task budgeting and Human-attention circuit breakers;
3. #148 Layered verification and failure-budget separation;
4. #149 Bounded inter-agent collaboration and review dialogue;
5. #150 Risk-proportionate review and role-specific evidence packs;
6. #151 Telemetry calibration, Human-attention metrics, and continuity automation, including the Human Owner-approved #406 bounded incident-learning/advisory-triage direction. Implement #406 as an extension of TaskOutcome/continuity/memory promotion rather than a separate always-on retrospective agent;
7. #98 Constrained PM-controlled PR merge may proceed where dependencies permit, but must be complete before PCP can claim a routine zero-human-touch happy path.

Guiding constraints for the initiative:

- routine healthy tasks should target zero avoidable Human Owner interventions;
- task estimates are planning/resource signals, while emergency ceilings/circuit breakers protect against abnormal execution and material resource risk;
- provider quota is separate from task estimate exhaustion;
- full required deterministic verification/CI remain mandatory;
- inter-agent collaboration is selective, bounded, and single-writer by default;
- no always-on swarm or recursive agent meeting;
- strong/scarce models and heavy review are risk/value proportional;
- telemetry improves heuristics only after meaningful evidence exists;
- incident learning must prefer deterministic detection and executable prevention,
  must not invoke PM for each ordinary first failure, and must preserve the
  T0/T1/T2/T3/T4 memory lifecycle rather than creating an append-only log.

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
- repair count by category;
- verification cycles;
- CI pass rate;
- reviewer finding/useful-finding rate;
- wall time;
- token/resource use;
- provider failure/quota pressure;
- Human Attention metrics;
- task outcome.

Then calibrate Router decisions by project/task/role where sample size is meaningful.

Do not prematurely add statistical complexity from very small samples.

Exit criteria:

- model staffing and effort/budget decisions can cite observed project performance rather than only hand-authored capability/base-success values.

## Phase 10 — Efficiency improvements driven by evidence

The following items are pulled forward under initiative #146 rather than deferred until late optimization:

- task-specific estimated/elastic budgets;
- Human Attention metrics;
- cheap/targeted intermediate verification before final full checks;
- separated retry/failure accounting;
- bounded specialist consultation/review dialogue;
- smarter evidence/context compaction;
- provider/quota resource weights beyond USD.

Candidates that remain evidence-dependent:

- lightweight structural repo map;
- carefully bounded parallel WorkOrders.

## Phase 11 — Owner-only Telegram terminal operations gateway

Goal: allow the Human Owner to run local diagnostics from Telegram without turning Telegram into an unrestricted remote shell or weakening PCP trust boundaries.

The authoritative design is `telegram-terminal-operations.md`.

This remains approved but is lower priority than the execution-efficiency initiative because it is primarily an operator convenience layer.

Implementation order:

1. separate Telegram bot/token and owner/private-chat authentication;
2. WSL long-polling daemon/service lifecycle;
3. `/run-ro` arbitrary diagnostic scripts inside a capability-restricted read-only sandbox;
4. timeout/output/audit controls and secret-free execution environment;
5. PCP read-only broker for jobs/plans/actions/events/quota/logs and optional SELECT-only database principal;
6. optional Telegram-ready block metadata/hash/TTL ergonomics;
7. only after the read-only path is stable, `/run-op` named bounded mutations with explicit confirmation and fresh state revalidation;
8. keep generic `/run-admin` disabled unless a later concrete need passes a separate security/architecture decision.

Critical constraints:

- security must be enforced by OS/container/database capability boundaries, not shell-text regex allow/deny parsing;
- diagnostic scripts receive no Runtime/provider/GitHub/Docker/SSH secrets;
- repository/workspace/log sources are read-only and `/tmp` is the only normal writable scratch area;
- no Docker socket, sudo/root, arbitrary SSH, source-repository writes, database mutation or production authority in `/run-ro`;
- `/run-op` uses named official Runtime/service operations rather than a generic elevated shell;
- existing Runtime durable state, stale-action validation, active-job rollout gates, PM governance and production boundaries remain authoritative;
- ordinary ChatGPT read-only blocks remain ordinary terminal-safe blocks; Telegram-specific formatting is emitted only when the Human Owner explicitly asks for a Telegram-ready block.

Exit criteria:

- the Human Owner can paste a Telegram-ready multi-line diagnostic block and receive bounded output from the local machine while mutation authority and secrets remain unavailable to the diagnostic process;
- common PCP inspection no longer requires exposing mutable Runtime/database credentials to the Telegram-run script;
- any enabled operational mutation preserves the same state-machine and owner-confirmation guarantees as local execution.

## Deferred until demonstrated need

Do not build these merely because multi-agent systems often include them:

- always-on parallel agent swarm;
- Best-of-N implementation generation for routine work;
- recursive reviewer-of-reviewer loops;
- production deployment by agents;
- large vector/RAG infrastructure for code retrieval;
- separate containers/services for PM, developer, QA, architect, and reviewer roles;
- complex dashboards with no demonstrated decision value;
- additional model gateways/services with no active use case.

PM-controlled autonomous merge is no longer a deferred concept; issue #98 tracks its constrained implementation under already-approved governance.

## Current development workflow while building the platform

Until the internal PM/team loop is complete, dogfood the target model manually:

```text
Human Owner
  -> ChatGPT High: architecture / WorkOrder / review
  -> Codex or bounded implementation agent: implementation / tests / repair
  -> ChatGPT High or alternate model: independent review
  -> GitHub CI
  -> PM merge where executable support exists; otherwise follow the current constrained implementation state
```

For very small, obvious patches, direct implementation may be acceptable, but non-trivial subsystem work should follow the WorkOrder/review pattern.
