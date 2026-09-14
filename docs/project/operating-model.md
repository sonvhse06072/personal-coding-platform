# Operating Model

Status: approved target operating model. Some artifacts and PM behaviors described here are not yet implemented in Runtime; see `roadmap.md`.

## 1. Team model

The platform models a small development team through logical roles rather than dedicated services.

Primary roles:

- Human Owner
- Product Manager (PM)
- Router / Staffing Policy
- Runtime Orchestrator
- Developer / Specialist
- Independent Reviewer
- n8n Integration Layer

The model/provider assigned to a role is an implementation detail chosen by Router. Roles must not be named after providers or models.

## 2. Human Owner

The Human Owner collaborates with PM during project inception to define the complete project frame:

- goals and non-goals;
- product scope and requirements;
- source-of-truth documents;
- architecture constraints;
- major dependency choices;
- quality/security expectations;
- roadmap frame;
- resource/budget policy.

After baseline approval, the Human Owner should not need to supervise routine engineering execution or routine PR merges.

Human participation is required for:

- initial Project Plan approval;
- scope changes;
- architecture-invariant changes;
- major new dependency/framework/service choices;
- security/authentication/authorization/trust-boundary changes;
- destructive data changes;
- production writes or deployment;
- material budget expansion;
- high-authority governance amendments;
- ambiguities that cannot be resolved from approved source of truth.

Routine PR review and merge inside the approved project frame is delegated to PM after required verification/review/CI gates pass. A merge must stop for Human Owner input whenever the PR introduces or depends on one of the decision boundaries above.

## 3. Product Manager

PM is the project-reasoning and execution-governance role.

### Inputs

PM may receive:

- a ticket/request from the Human Owner;
- the approved Project Plan and relevant source-of-truth sections;
- Developer WorkReports;
- ReviewReports;
- deterministic verification results;
- CI/delivery outcomes;
- Runtime/provider/budget evidence.

### Responsibilities

PM must:

1. check the request against project scope and constraints;
2. identify relevant requirements, architecture constraints, dependencies, and risk;
3. decompose approved work into bounded WorkOrders;
4. maintain dependency ordering and the mutable Execution Plan;
5. request staffing from Router rather than hard-code a preferred model;
6. interpret meaningful reports/evidence and choose the next action;
7. keep work aligned with the approved Project Plan;
8. create a ChangeProposal instead of silently changing project intent;
9. produce a TaskOutcome after meaningful completion/failure;
10. select the next approved in-scope task when appropriate;
11. perform the final engineering review of PR evidence before merge;
12. merge eligible PRs when all required gates pass and no Human Owner decision trigger remains unresolved.

### PM autonomy

PM may autonomously:

- split/reorder in-scope work;
- reassign a failed WorkOrder;
- request bounded repair or additional review;
- change execution tactics;
- update Execution Plan state;
- record discovered follow-up work;
- defer an in-scope task because of dependency or budget evidence;
- review and merge an in-scope PR after deterministic checks, required independent review, and CI are green;
- continue to the next dependency-satisfied in-scope task after the merge gate clears.

PM may not autonomously:

- expand product scope;
- rewrite non-goals;
- alter approved architecture constraints;
- add a major framework/service/dependency;
- weaken security boundaries;
- approve destructive/production operations outside existing policy;
- materially expand budget;
- merge a PR whose content or unresolved finding requires a Human Owner decision.

## 4. Router / Staffing Policy

Router answers **who/how expensive/how strong**, not **what/why**.

Inputs include:

- WorkOrder role and task class;
- repository/task complexity signals;
- risk/profile;
- privacy constraints;
- provider/model availability and health;
- budget/resource envelope;
- eventually historical performance telemetry.

Outputs include:

- selected logical execution profile;
- model/provider/adapter for the requested role;
- bounded execution budget;
- optional planner/evaluator staffing;
- deterministic human-decision triggers.

Router must not modify product scope or project state.

## 5. Runtime Orchestrator

Runtime answers **execute safely and durably**.

Responsibilities:

- persist job/work state;
- pin source commit;
- request isolated workspace creation;
- invoke selected agent roles with bounded context;
- track model/tool/token/time/resource usage;
- enforce anti-loop and hard budgets;
- run deterministic verification;
- perform bounded retries/failover/escalation;
- pause for human decisions when required;
- checkpoint/recover interrupted work;
- coordinate bounded GitHub delivery and CI repair;
- support the PM-controlled merge gate without giving developer agents merge authority.

Runtime should handle routine test/lint/repair mechanics without invoking PM for every iteration.

## 6. Developer / Specialist role

A Developer receives a WorkOrder/Task Contract rather than an unconstrained natural-language request.

Expected WorkOrder fields include:

```yaml
id: T-123
objective: concise bounded objective
source_of_truth:
  project_revision: ...
  requirements: [...]
  architecture: [...]
in_scope: [...]
out_of_scope: [...]
acceptance_criteria: [...]
constraints: [...]
verification: [...]
role: backend_developer
budget_profile: standard
```

Developer responsibilities:

- read relevant source and tests before modifying code;
- stay inside the Task Contract;
- use existing project patterns where practical;
- implement the smallest sufficient change;
- add/adjust relevant tests;
- report assumptions, risks, deviations, and unresolved items;
- never broaden scope because a different solution seems more interesting.

A developer must not merge, deploy, change project governance, or bypass trust boundaries.

## 7. Developer WorkReport

A meaningful developer attempt ends with structured evidence, not only raw stdout.

Target shape:

```yaml
work_order: T-123
status: completed | blocked | failed
summary: ...
criteria:
  AC1: passed
  AC2: passed
changed_components: [...]
tests_added: [...]
tests_passed: [...]
assumptions: [...]
risks: [...]
deviations: []
unresolved: []
recommendation: ready_for_review
```

For blocked work, the report should include root cause, evidence, attempted approaches, and recommended next action.

Raw execution logs remain available for diagnostics but should not be the primary PM context.

## 8. Deterministic verification

Deterministic verification is independent of the developer's claims.

It should run the checked-in project phases appropriate to the WorkOrder/profile. The system may later add a cheap pre-edit baseline check and narrower intermediate checks, but final acceptance must remain deterministic and reproducible.

Model review does not replace deterministic tests/static analysis.

## 9. Independent Reviewer

Reviewer is a logically independent role whose purpose is to challenge developer assumptions and verify alignment.

The reviewer assesses three layers:

1. implementation correctness;
2. Task Contract / acceptance-criteria compliance;
3. Project Constitution / architecture alignment.

Target ReviewReport:

```yaml
work_order: T-123
verdict: pass | fail | needs_human_decision
findings:
  - severity: ...
    category: correctness | regression | security | scope | architecture | tests
    evidence: ...
    action: ...
project_alignment: pass
```

### Diversity policy

Where practical, reviewer should use a different model/provider from the implementing developer.

Risk proportionality:

- routine: lightweight alternate-model review when economical;
- standard: independent Task Contract + diff review;
- complex: strong independent reviewer;
- critical/security/architecture: different-model/provider review required if eligible capacity exists.

Do not recursively review reviewers by default.

## 10. PM TaskOutcome

At a meaningful checkpoint, PM consumes WorkReport + deterministic checks + ReviewReport + CI evidence and writes a compact outcome.

Target shape:

```yaml
task: T-123
outcome: accepted | repair | reassign | replan | blocked | human_decision
project_effect: [...]
new_information: [...]
discovered_work:
  - description: ...
    relation: within_scope | outside_scope
plan_changes: [...]
next_task: T-124
```

If a next task is already inside the approved Project Plan, PM may schedule it automatically subject to budget/dependency rules. When the accepted task is represented by a PR, PM may merge it after the required merge gates pass and then advance the dependency graph.

Outside-scope discovered work is recorded but not silently added to the roadmap.

## 11. ChangeProposal

A ChangeProposal is the only normal path for an agent to request modification of the approved project frame.

Target shape:

```yaml
id: CP-12
trigger: ...
current_constraint: ...
proposed_change: ...
impact:
  scope: ...
  architecture: ...
  security: ...
  budget: ...
  migration: ...
alternatives: [...]
recommendation: ...
requires_human_decision: true
```

Human approval leads to a source-of-truth revision through Git/PR; rejection leaves the baseline unchanged. After explicit Human Owner approval, PM may merge the amendment PR once all remaining gates pass.

## 12. n8n Integration Layer

n8n remains thin and may provide:

- ticket/event intake;
- status/notification delivery;
- human-decision notifications;
- scheduled PM summaries;
- future integrations such as email/Slack/GitHub events.

n8n must not own:

- PM reasoning;
- project source of truth;
- model selection;
- coding logic;
- Docker/GitHub delivery capabilities;
- durable engineering job state.

## 13. Delivery and merge

The expected delivery policy is:

```text
WorkOrder accepted locally
  -> commit
  -> ai/* branch
  -> pull request
  -> CI
  -> bounded repair if needed
  -> required independent review when applicable
  -> PM final engineering review
     -> merge when in scope and all gates pass
     -> human decision when a protected decision boundary is implicated
```

A PR merge is not a production deployment. Force push remains forbidden. Blind or gate-bypassing auto-merge remains forbidden; PM-controlled autonomous merge is the approved routine path.

## 14. Concurrency and budget

Default active engineering concurrency is one.

PM may request parallel WorkOrders only when:

- dependencies are independent;
- workspace/merge conflict risk is acceptably low;
- budget/quota permits;
- there is a meaningful wall-time benefit.

The team resource envelope includes more than USD: model calls, subscription quota/scarcity, token usage, wall time, repair count, and provider reliability are all legitimate budget signals.

## 15. Practical checkpoint rule

PM is invoked at meaningful checkpoints, not every mechanical event.

PM should normally run when:

- a new ticket arrives;
- an initial plan/decomposition is needed;
- a developer completes meaningful work;
- review fails after bounded routine repair;
- a decision boundary or scope conflict is discovered;
- a task completes and the next action must be selected;
- a PR has passed its required gates and is ready for PM merge review.

A first lint failure, test typo, or ordinary bounded retry remains Runtime/Developer responsibility.
