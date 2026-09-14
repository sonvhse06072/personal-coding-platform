# Architecture

Status: approved architecture direction. This document deliberately separates what exists on `main` from what is approved but not yet implemented.

## 1. Architectural objective

The platform models a small software-development team while keeping model behavior inside deterministic, reviewable trust boundaries.

The target separation of responsibility is:

```text
Human Owner
    |
    v
Product Manager role
    |  project reasoning / scope governance / WorkOrders
    v
Router / Staffing Policy
    |  model + role + budget choice
    v
Runtime Orchestrator
    |  bounded execution / state / checkpoints
    v
Developer or Specialist role
    |
    v
Deterministic Verification
    |
    v
Independent Reviewer role
    |
    v
Product Manager synthesis
    |
    +--> repair / reassign / replan within approved scope
    +--> ChangeProposal -> Human Owner when project frame must change
    +--> delivery -> GitHub CI -> PM review/merge when no human-decision trigger exists
```

PM, developer, reviewer, debugger, tester, and other specialists are logical roles. They are not separate infrastructure services unless future evidence demonstrates a concrete need.

## 2. Current implementation

The current system already provides the execution infrastructure on which the target team model will be built.

### DDEV-managed platform

DDEV owns the local platform lifecycle and composes the following services:

- `router`
- `coding-runtime`
- `ddev-executor`
- `n8n`
- PostgreSQL via DDEV `db`
- a constrained Antigravity host bridge running on WSL rather than inside the coding container

### Router

Current Router responsibilities:

- deterministic repository/task complexity dimensions;
- profile selection (`fast`, `standard`, `complex`, `critical`);
- model/provider selection by role, capability metadata, availability, cost class, privacy, and health state;
- hard execution budgets and anti-loop policy;
- deterministic human-decision triggers;
- bounded escalation/failover decisions.

The Router does **not** own product direction. Its target role is staffing/resource policy.

Current model-scoring constants are heuristic. They may later be replaced or calibrated with real project telemetry; do not interpret current scores as statistically precise success probabilities.

### Coding Runtime

Current Runtime responsibilities:

- durable job persistence in PostgreSQL;
- job lifecycle and checkpoint/recovery behavior;
- deterministic repository analysis;
- isolated workspace creation through `ddev-executor`;
- planner/executor/evaluator adapter calls according to Router strategy;
- bounded repair, failover, escalation, cancellation, and human-decision pauses;
- deterministic DDEV verification;
- commit creation after acceptance;
- bounded branch/PR/CI delivery and CI-failure repair loops.

Runtime is an engineering-operations orchestrator. It does not own project/product direction.

The current implementation may still contain manual-merge orchestration behavior from the previous governance policy. That behavior is transitional implementation state, not the approved target authority model after issue #96. Runtime/ddev-executor changes that automate the PM merge gate must preserve all existing trust boundaries and be delivered separately through normal PR/CI review.

### Isolated workspaces

Each coding job uses a self-contained clone pinned to the source commit and an `ai/*` branch. The agent workspace has no Git remote. This is deliberate: agents may modify workspace files but cannot independently publish to the source repository.

### ddev-executor

`ddev-executor` is the privileged boundary. It is the only platform service intended to have the Docker socket, target source-repository visibility needed for workspace creation, and GitHub delivery credentials/capabilities.

It accepts registered project IDs and bounded operations rather than arbitrary remote command execution. It validates workspace identity, branch namespace, source ancestry, expected commits, and project autonomy policy before publishing.

PM-controlled merge capability, when implemented, must remain behind a constrained Runtime/ddev-executor operation that validates the exact PR/head, CI/review state, project/WorkOrder identity, and absence of unresolved human-decision triggers. Developer-agent subprocesses must never receive GitHub merge credentials or direct merge capability.

### Agent adapters

Current coding adapters include Codex CLI, OpenCode and the Antigravity host adapter. Provider/model choice is separate from the logical role being performed.

The architecture requires developer-agent subprocesses to receive only the process environment and provider credential needed for that specific call. They must not receive internal platform credentials or unrelated provider keys.

Codex CLI is an unattended Runtime worker, so its approval behavior must be explicit rather than inherited from mounted user configuration. Planner/evaluator turns use `read-only`; execute/repair turns use `workspace-write`; all Codex turns use approval policy `never`, and workspace-write network access is explicitly disabled. A command that requires permission outside the selected sandbox must fail closed rather than wait for interactive approval. `danger-full-access` and approval/sandbox bypass flags are outside the approved developer-agent trust boundary.

### Antigravity host bridge

Antigravity remains on the WSL host so its OS keyring credentials do not enter Docker. Runtime talks to a constrained bearer-authenticated bridge that accepts only bounded workspace runs/cancellation.

### n8n

n8n is currently a thin control plane for:

- authenticated job intake;
- job status access;
- human-decision forwarding.

It proxies Runtime operations and is intentionally forbidden from owning model routing, coding logic, project state, Docker access, GitHub delivery, or PM reasoning.

### GitHub delivery

Approved delivery flow is:

```text
local deterministic verification
  -> bounded commit
  -> non-force ai/* branch publish
  -> create/update PR
  -> monitor GitHub CI
     -> failure: bounded repair on same branch/PR
     -> delivery infrastructure failure: durable checkpoint/resume
     -> success: PM consumes WorkOrder + WorkReport + required ReviewReport + CI evidence
         -> in scope, all gates green, no human-decision trigger: PM merge
         -> protected decision boundary: pause for Human Owner decision, then PM may merge after approval
```

Blind auto-merge, force push, developer-agent merge, and production deployment by implication are not allowed. PM-controlled autonomous merge after explicit evidence gates is approved.

## 3. Approved target architecture

The following layers are approved targets but are not all implemented yet.

### Project Source-of-Truth layer

Each managed project will have a versioned baseline established by the Human Owner and PM before autonomous execution begins. It will describe:

- project goals and non-goals;
- product scope and requirements;
- architecture constraints/invariants;
- quality/security rules;
- budget/resource policy;
- roadmap frame;
- approved architecture decisions.

The platform repository uses this `docs/project/` set as the first dogfood example.

### Product Manager layer

The PM is a reasoning role above Router/Runtime. Its responsibilities include:

- read and enforce the approved Project Plan;
- assess whether incoming work is inside scope;
- decompose in-scope requests into bounded WorkOrders;
- maintain a mutable Execution Plan and dependency ordering;
- choose the next meaningful action after developer/reviewer/CI evidence;
- request staffing from Router;
- create ChangeProposals when the approved project frame must change;
- summarize completed work and update project execution state;
- perform the final engineering review for merge eligibility;
- authorize and execute merge for in-scope PRs after all required gates pass and no human-decision trigger remains unresolved.

The PM may change execution tactics and merge routine in-scope work, but it may not change project intent or protected governance boundaries without human approval.

### Structured team artifacts

The target protocol will use durable, versioned or persisted artifacts:

- ProjectBaseline / Constitution revision
- ExecutionPlan
- WorkOrder / TaskContract
- WorkReport
- ReviewReport
- TaskOutcome
- ChangeProposal

These artifacts should be compact and structured so later roles consume relevant evidence instead of large raw transcripts.

### Role-based staffing

The system should staff logical roles such as:

- Drupal/backend developer;
- frontend developer;
- test engineer;
- debugger;
- security reviewer;
- architecture reviewer.

A role is mapped to a model/provider by Router according to capability, risk, availability, privacy, historical performance, and budget. A model name must never become the role identity.

### Cross-model review

Review diversity is a first-class target, but it must be risk-proportionate.

- Routine tasks: lightweight review using a different model/provider where cost permits.
- Standard tasks: independent diff/task-contract review.
- Complex tasks: stronger independent reviewer.
- Critical/security/architecture work: different-model review is mandatory where an eligible provider exists.
- Repeated failure or uncertain solution: PM may request an alternate-model opinion before more implementation spend.

Reviewer context should be minimal and high-signal: Task Contract, relevant changed files/diff, deterministic verification, developer report, and relevant source-of-truth sections. Reviewers should retrieve additional repository context only when needed.

### PM feedback loop

After meaningful work, the expected loop is:

```text
Developer WorkReport
+ deterministic verification
+ independent ReviewReport
+ GitHub/CI evidence when applicable
        |
        v
PM TaskOutcome
        |
        +--> accept and merge when eligible
        +--> bounded repair
        +--> reassign
        +--> replan within scope
        +--> ChangeProposal / human decision
        +--> select next in-scope WorkOrder
```

The PM should not be called for every lint/test retry. Runtime handles routine repair mechanics; PM is invoked at meaningful checkpoints, including the final merge decision.

## 4. Trust-boundary model

The intended capability flow is:

```text
Developer agent
  - isolated workspace
  - selected provider credential only when required
  - no platform-internal credentials
  - no Docker socket
  - no source repo root
  - no GitHub delivery/merge credential

Runtime
  - job/project state
  - Router/executor/bridge client credentials
  - coding adapters
  - no Docker socket
  - no unrestricted GitHub delivery privilege
  - may request constrained PM-authorized merge through ddev-executor after validating gates

Router
  - model/project policy
  - no coding workspace mutation
  - no Docker/GitHub delivery privilege

ddev-executor
  - Docker socket
  - registered source/workspace roots
  - bounded DDEV execution
  - GitHub delivery credential
  - constrained PR publish/status/merge operations only
  - internal only

n8n
  - Runtime API credential
  - control-plane ingress secrets
  - no Router/provider/executor/GitHub credentials
```

Security boundaries must fail closed. Convenience is not sufficient justification for giving a lower-trust role a higher-trust credential.

## 5. Concurrency model

Default concurrency is one active engineering WorkOrder. This is intentional for a personal, quota-conscious platform.

Parallel execution may be enabled later only when PM determines that WorkOrders are independent, merge/scope collision risk is low, and the resource envelope allows it.

## 6. State and source-of-truth principle

Stable project intent belongs in checked-in project documentation. Runtime/PostgreSQL will hold mutable execution state, reports, checkpoints, outcomes, and merge-gate evidence.

Chat history is never authoritative project state.

## 7. Architecture change rule

A change that alters service boundaries, trust boundaries, major dependencies, project authority, merge/deploy policy, or PM/Router/Runtime responsibility boundaries is an architecture change. It requires a ChangeProposal and human approval before implementation.

Once the Human Owner explicitly approves such a change, PM may carry its amendment PR through the remaining review/CI gates and merge it under the approved transition.
