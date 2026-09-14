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

## 6. Product Manager authority

After the human owner approves the baseline, the PM may autonomously:

- decompose approved scope into WorkOrders;
- order or reorder work based on dependencies and evidence;
- split a task into smaller in-scope tasks;
- select the next task within the approved roadmap frame;
- ask the Router to staff a WorkOrder with an appropriate model/role;
- request bounded repair, re-review, reassignment, or escalation;
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
- materially expand the project budget;
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
- Independent model review supplements deterministic checks for risk-appropriate tasks.
- Bounded repair/escalation must preserve already-consumed job budgets.
- Agent-produced changes are delivered through an `ai/*` branch and pull request.
- CI green is a mandatory gate before a PR is considered ready for merge.
- The PM performs the final engineering review for in-scope work and may merge autonomously when all required gates pass and no unresolved Human Owner decision trigger exists.
- Changes requiring Human Owner approval must obtain that approval before PM merge.

## 11. Budget principles

- Budget is a team resource envelope, not only a USD value.
- Resource decisions may account for money, subscription quota, scarcity, latency, model-call count, wall time, and repair count.
- Cheap/free/subscription capacity should be preferred for routine work when expected quality is sufficient.
- Stronger or scarce models should be reserved for high-risk, high-reasoning, repeated-failure, architecture, or review work where they create meaningful value.
- Repeated failures should trigger reassessment or escalation, not unbounded retries.

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

Do the simplest thing that preserves the approved architecture and invariants. A new abstraction, service, agent role, model call, or automation must justify itself by improving at least one of:

- failure rate / correctness;
- model or tool efficiency;
- security / blast-radius control;
- governance / project alignment.

Otherwise, defer it.
