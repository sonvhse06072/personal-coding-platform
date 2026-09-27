# Project Constitution

Status: approved project baseline for continued development.

This document defines the highest-authority project rules for the Personal Coding Platform. It is intentionally conservative: execution plans may evolve frequently, but the project frame does not change silently.

## 1. Project purpose

Build a personal, budget-conscious coding automation platform that models a small software-development team using multiple AI agents and deterministic tooling.

The human owner collaborates with a Product Manager agent at project inception to establish the complete project scope, source of truth, architecture constraints, roadmap frame, quality expectations, and budget policy. After that baseline is approved, the PM is responsible for executing within it.

The system should reduce the amount of routine supervision required from the human owner while keeping the human in control of important product, architecture, security, production, destructive-data, dependency, governance, and material budget decisions.

## 2. Project goals

- Model a small development team through logical agent roles such as Product Manager, developer, reviewer, debugger, tester, and specialist.
- Let the PM transform approved project scope into bounded WorkOrders and choose the next action based on evidence from developers, reviewers, deterministic checks, and CI.
- Route each role to an appropriate model/provider based on capability, risk, availability, historical performance, and resource cost.
- Use cross-model review so important work is not locked into a single model's assumptions or reasoning style.
- Keep deterministic checks, Git, CI, bounded retries, budgets, checkpoints, and explicit trust boundaries as hard controls around model behavior.
- Keep operating cost practical for one person. Strong or scarce models should be used where they create meaningful value, not by default.
- Minimize avoidable Human Owner intervention in routine healthy execution; human attention is itself a scarce project resource.
- Preserve healthy-progress autonomy: routine work that is demonstrably progressing must not be converted into a Human Owner continuation gate merely because a static task counter or profile default was reached.
- Preserve a repository-resident source of truth so any capable agent can resume project work from source control alone.

## 3. Non-goals

The platform is not intended to become:

- a general multi-tenant SaaS platform;
- an enterprise workflow engine;
- an always-parallel autonomous agent swarm;
- a replacement for human ownership of project direction;
- a system that blindly merges code without PM review and required gates, or deploys to production without human control;
- a reason to add infrastructure or abstraction that does not improve reliability, efficiency, security, or governance.

## 4. Authority hierarchy

When artifacts conflict, use this order:

1. This Project Constitution and human-approved amendments.
2. Human-approved architecture decisions and architecture invariants.
3. Approved project requirements, roadmap frame, and product scope.
4. Operating model, quality gates, security policy, and budget policy.
5. The current WorkOrder / Task Contract.
6. Current code, tests, and checked-in configuration for executable behavior.
7. Developer WorkReports, ReviewReports, PM summaries, telemetry, and other runtime evidence.

A lower-authority artifact may clarify a higher-authority artifact but must not silently redefine it.

### Approved baseline immutability

For a PCP-managed project, the approved ProjectBaseline revision is an immutable authority snapshot identified by an exact source commit. A newer repository `HEAD` does not by itself amend the approved project frame.

Advancing protected project authority requires a reviewed successor baseline revision. An already-approved revision must not be rewritten in place to point at newer source material or to change the authority class of protected documents. The previous revision remains auditable.

ProjectBaseline metadata may classify source paths by authority. Changes classified as `human_owner_protected` require explicit Human Owner approval before PM merge. Delegated authority such as day-to-day design ownership remains valid only inside its approved delegation and does not extend into product scope, business rules, architecture, security, governance, production, destructive-data, or material-budget authority.

Mutable execution state and historical evidence may describe newer repository state, but neither can silently promote that state into approved project-frame authority.

## 5. Human Owner authority

The human owner has final authority over:

- initial project baseline and major roadmap direction;
- project goals, scope, and non-goals;
- architecture direction and architecture invariants;
- major dependencies, frameworks, and platform services;
- authentication, authorization, secret-handling, and other security-boundary changes;
- destructive migrations or data-loss risks;
- production writes and production deployment;
- material budget/quota changes;
- amendments to this Constitution or other high-authority source-of-truth documents.

Routine pull-request review and merge inside the already-approved project frame is delegated to the Product Manager after required verification gates pass. The system must surface Human Owner decision boundaries rather than silently resolving them.

Routine execution continuation inside an already-approved task working envelope is not a material budget decision and should not require Human Owner approval when execution remains healthy and no protected decision boundary is implicated.

## 6. Product Manager authority

After the human owner approves the baseline, the PM may autonomously:

- decompose approved scope into WorkOrders;
- order or reorder work based on dependencies and evidence;
- split a task into smaller in-scope tasks;
- select the next task within the approved roadmap frame;
- ask the Router to staff a WorkOrder with an appropriate model/role;
- request bounded repair, re-review, reassignment, escalation, or specialist consultation;
- update the mutable Execution Plan;
- record newly discovered work that is inside or outside the approved scope;
- review pull requests using the WorkOrder, WorkReport, deterministic verification, independent review when required, and CI evidence;
- merge a PR autonomously when it remains inside the approved project frame, all required gates are green, and no unresolved Human Owner decision trigger exists.

The PM may not autonomously:

- invent new product scope;
- redefine a non-goal;
- change an architecture invariant;
- add a major dependency or infrastructure service without approval;
- weaken a security or trust boundary;
- authorize destructive or production operations outside existing approved policy;
- materially expand the project/personal resource envelope;
- approve or merge a change that itself requires Human Owner approval until that approval has been explicitly obtained.

When such a change appears necessary, the PM must create a ChangeProposal for human approval.

## 7. Project Plan versus Execution Plan

The **Project Plan** is the human-approved, versioned frame containing project scope, requirements, architecture constraints, quality rules, budget policy, and roadmap direction. It is immutable-ish and changes through reviewed amendments.

The **Execution Plan** is PM-owned and mutable. It contains current WorkOrders, dependency ordering, current focus, next candidates, and bounded replanning decisions that remain inside the Project Plan.

Agents must not confuse these two levels.

## 8. Agent-role principles

- Roles are logical responsibilities, not dedicated containers or long-running services.
- A model/provider is staffing for a role, not the identity of the role itself.
- The same model may perform different roles at different times, subject to review-diversity policy.
- Critical work should receive an independent review from a different model/provider where practical.
- Cross-model review must be risk-proportionate; routine work must not become an expensive swarm by default.
- Bounded inter-agent consultation is allowed when expected value justifies the resource cost; collaboration must not become unrestricted recursive agent chatter.
- For a WorkOrder workspace, the default writer is one Primary Developer. Consultants, testers, debuggers, specialists, and reviewers are read-only unless a separately approved execution design explicitly grants a narrower capability.
- Default execution concurrency is one. Parallel execution is allowed only for demonstrably independent WorkOrders and when budget permits.

## 9. Trust and security invariants

- Developer agents operate only inside isolated job workspaces.
- Developer agents must not possess Runtime, Router, executor, GitHub-delivery, Antigravity-bridge, or unrelated provider credentials.
- Runtime must not receive the Docker socket or unrestricted source-repository privilege.
- Only the constrained `ddev-executor` service may hold the Docker/source/GitHub-delivery capabilities required for bounded verification and delivery.
- n8n remains a thin external integration/control-plane layer and must not own coding intelligence, model routing, product state, or privileged execution.
- Authentication and secret boundaries fail closed when required credentials are absent or placeholders.
- No force push is permitted. Developer agents cannot merge. PM-reviewed autonomous merge is allowed only after required gates pass and only when no Human Owner decision boundary is implicated.
- Production deployment remains separately controlled and cannot be implied by a PR merge.

## 10. Verification and delivery invariants

- Model output is never the sole definition of correctness.
- Deterministic verification must run against checked-in project commands and policies.
- Verification may be layered so targeted/affected checks run during implementation and repair, but required full deterministic verification must still pass before acceptance/delivery.
- Independent model review supplements deterministic checks for risk-appropriate tasks and must be stronger where risk justifies the added resource cost.
- Bounded repair/escalation must preserve already-consumed job budgets/counters.
- Agent-produced changes are delivered through an `ai/*` branch and pull request.
- CI green is a mandatory gate before a PR is considered ready for merge.
- The PM performs the final engineering review for in-scope work and may merge autonomously when all required gates pass and no unresolved Human Owner decision trigger exists.
- Changes requiring Human Owner approval must obtain that approval before PM merge.

## 11. Budget principles

- Budget is a team/personal resource envelope, not only a USD value.
- Resource decisions may account for money, subscription quota, scarcity, latency, model-call/token usage, wall time, verification cost, repair work, provider reliability, and Human Owner attention.
- Task budget should distinguish **estimate**, **elastic working envelope**, and **emergency hard ceiling** semantics where implementation supports it.
- A task estimate is primarily a planning/resource-allocation forecast; merely reaching the estimate should not interrupt healthy execution.
- Runtime may autonomously use bounded headroom inside the approved working envelope when progress remains healthy, consumed usage is preserved, no protected decision is implicated, provider/quota state is acceptable, and no circuit-break condition exists.
- **Healthy-progress non-blocking is a mandatory platform invariant.** A job that is making meaningful progress must not be blocked solely because it reached a static profile/default limit for model calls, input/output tokens, tool calls, test runs, wall time, repair iterations, iterations, or a similar task counter.
- A static counter crossing by itself is not a sufficient Human Owner decision trigger. A hard stop must have an independent reason such as repeated failure/no progress, solution oscillation, unexpected scope growth, runaway or abnormal resource growth, authoritative provider exhaustion without an eligible fallback, a protected decision boundary, or a genuinely material expansion of the approved project/personal resource envelope.
- Emergency hard ceilings are safety/circuit-break controls for abnormal execution or real material resource risk. They must be calibrated and implemented so healthy routine work does not repeatedly hit them as ordinary continuation checkpoints.
- When a healthy task approaches or crosses a working/default limit inside the already-approved personal resource envelope, Router/Runtime must prefer bounded autonomous continuation/headroom on the same durable job/workspace/counters. If the implementation instead requires an owner click merely to continue otherwise healthy work, that is an avoidable workflow defect to be corrected rather than an acceptable steady-state design.
- Human Owner continuation actions are reserved for true exceptional conditions or protected/material decisions; they must not compensate for arbitrary low counters or profile defaults.
- Provider quota/resource state is separate from task execution estimates. Authoritative provider exhaustion may block/reroute work; estimate exhaustion alone is not equivalent to provider quota exhaustion.
- Cheap/free/subscription capacity should be preferred for routine work when expected quality is sufficient.
- Stronger or scarce models should be reserved for high-risk, high-reasoning, repeated-failure, architecture, specialist consultation, or review work where they create meaningful value.
- Repeated failures, no progress, solution oscillation, unexpected scope growth, or other abnormal execution signals should trigger reassessment/escalation/circuit breaking rather than unbounded retries.
- Material expansion of the approved project/personal resource envelope or override of a justified emergency ceiling requires Human Owner approval.
- Consumed counters are durable audit evidence and must never be reset to create artificial headroom.
- Human attention should be measured as a scarce resource; routine healthy tasks should target zero avoidable owner interventions.
- All future Router/Runtime budget, recovery, reassessment, and Human Attention work must be reviewed against this healthy-progress non-blocking invariant as a required acceptance criterion.
- The detailed Human Owner-approved execution-efficiency policy is `docs/project/efficiency-model.md`.

## 12. Change control

Any proposed change to project goals, scope, non-goals, architecture invariants, major dependency choices, security policy, production policy, destructive-data policy, merge-governance policy, or material budget policy requires a ChangeProposal containing:

- the current constraint;
- the proposed change;
- rationale and evidence;
- impact on scope, architecture, security, budget, migration, and roadmap;
- alternatives considered;
- a recommendation;
- explicit human approval/rejection.

Once approved, the affected source-of-truth document must be versioned through Git in a reviewed PR. After explicit Human Owner approval of the high-authority change, the PM may merge that amendment PR once CI and required review gates pass.

## 13. Practicality rule

Do the simplest thing that preserves the approved architecture and invariants. A new abstraction, service, agent role, model call, consultation, review round, or automation must justify itself by improving at least one of:

- failure rate / correctness;
- model, tool, verification, or context efficiency;
- Human Owner attention / autonomous throughput;
- security / blast-radius control;
- governance / project alignment.

Otherwise, defer it.
