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
- a separate durable orchestration lifecycle for explicitly superseded
  WorkOrders, preserving the underlying engineering job/result while removing
  only scheduling, automatic recovery and owner-attention eligibility.

Runtime is an engineering-operations orchestrator. It does not own project/product direction.

After successful base verification, project-owned path-scoped
`ddev.auto_required_phases` apply to both legacy jobs without a WorkOrder and
WorkOrder-backed jobs. Matching phases supplement WorkOrder-required phases
in deterministic order; phases already present in that verification result are
not rerun. Missing configured commands, completed phases without executed-command
evidence, or a failed required phase fail final verification.
Executed additional phases carry final/required evidence and command counts;
the existing verification-attempt and review-repair churn accounting remain intact.

Supersession is never inferred from ticket identity, WorkOrder naming, source
commit, timestamps, later PR success or PM prose. Runtime accepts it only
through the exact-identity supersession operation. A superseded WorkOrder and
its job remain queryable and retain their historical state, result, counters
and workspace references; pending owner attention becomes non-actionable while
sent/executed audit history remains unchanged.

WorkOrder checkpoint history is stored separately from mutable lifecycle
`cp_plan_work_orders.detail` in append-only `cp_plan_work_order_checkpoints`.
Each row has a database-ordered ID, unique caller-supplied transition key,
exact plan/WorkOrder foreign key, kind/state, optional job ID, bounded evidence
and a store-owned creation timestamp. Exact key/content retries return the
original row; conflicting reuse fails closed without updating it. Identity
strings are bounded (key: 500 characters; other fields: 200), and compact JSON
evidence is limited to 16 KiB serialized UTF-8. Evidence contains summaries and
identities, never raw transcripts, logs, prompts, Runtime results or file contents.
Schema installation uses the existing orchestrator `ensure()` startup path;
checkpoint append/read operations do not run migrations. There is no checkpoint
update/delete API. Supersession and later lifecycle changes preserve history.

Lifecycle transitions emit `started`, `waiting_human`, `accepted`, `completed`,
`merged`, `blocked` and `repair_reopened` checkpoints. The store locks the exact
plan/WorkOrder, checks the expected source state/job/PR/persisted version, and
commits the WorkOrder mutation, attention retirement and checkpoint together.
Checkpoint conflicts or failures roll back the entire transition. Retries
validate the existing immutable row without replaying a historical mutation.
Keys hash durable plan/WorkOrder/job identity plus decision, delivery, merge or
repair identity and persisted source versions as applicable; no polling clock
or random identity is used. Evidence is a strict whitelist of bounded identities,
outcomes and counters. Dependency state and next-ready IDs use the existing
ExecutionPlan graph with the target transition applied inside the transaction.
`accepted` does not unlock dependencies; confirmed merge completion and its
`merged` checkpoint commit atomically before a dependent can launch. Job start
is checkpointed after deterministic job creation and before enqueue. An internal
plan/WorkOrder/deterministic-job reservation is stored atomically with the queued
job; startup skips `held` reservations. Exact active running WorkOrder + durable
`started` proof releases it to `ready` before enqueue. Reconciliation completes
only held/ready pre-execution launches; queue dedupe and a locked execution claim
prevent duplicate launch. The claim marks the reservation `launched` and enters
the existing `routing` state before workspace side effects, so an in-flight
restart still requires explicit resume. Standalone queued startup is unchanged.
The reservation is a private engine keyword, not public job-intake policy. Existing
manual/PM merge authority, recovery and default concurrency of one are unchanged.

Authenticated `GET /v1/plans/{plan_id}/progress` projects a consistent read-only
database snapshot of orchestration state, the ExecutionPlan dependency graph
and checkpoints. It reports plan/project/ticket identity, state/lifecycle,
active-only completed/total counts, the current running/awaiting-merge/waiting-human
WorkOrder, a compact blocked WorkOrder/job identity, dependency-ready pending
WorkOrders in sequence order and the latest checkpoint by database ID. Only
active completed dependencies unlock `next`; this list expresses dependency
readiness, not permission to launch past other orchestration gates. The latest
checkpoint includes preserved superseded history for that plan. Raw lifecycle
detail and job results are not exposed. The existing `/orchestration` contract
is unchanged. #365 supplies persistence/projection and #366 lifecycle emission;
#367–#370 intake/publication/blocked-pack/supervised
continuation remain unimplemented by this change.

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

A PM finding discovered after delivery but before merge uses a dedicated
same-job review-repair transition, not ordinary run/resume. Runtime must first
ask `ddev-executor` to verify the exact open, unmerged PR identity, repository,
job branch, base branch, and expected delivered head. Once accepted, the
durable pending repair takes precedence over delivery reconciliation and sends
the unchanged job/WorkOrder/baseline/workspace back through normal engineering
and review gates. A successful repair publishes a new commit to the same branch
and PR and observes CI only for that new exact head; the transition grants no
merge or deployment authority.

Each active delivered-PR review repair also owns a durable churn epoch bound to
its exact request id. The epoch snapshots cumulative repair and verification
counters without resetting them and applies policy-defined anomaly limits before
another developer-model or deterministic-verification cycle. A pre-feature
pending request receives one persisted baseline on its first resumed run, so
historical work is not charged to the new epoch. Hitting the bound enters the
existing Human Owner decision flow with bounded evidence. Approval authorizes
one new generation and counter baseline for that same request; ordinary resume,
reroute, provider recovery and Runtime restart cannot re-arm it. Successful
same-PR delivery archives and clears the epoch before a future unrelated repair.

Legacy migration requires the epoch key to be genuinely absent and no churn
gate, pending churn decision, or initialization/history evidence for that request.
Explicit null, malformed metadata and inconsistent gate identities stop execution
with bounded integrity evidence while preserving the original checkpoint. A
persisted gate remains effective for its exact request/generation even if a stale
progress snapshot falls below the counters that tripped it. Only exact-key Human
authorization opens the next window; successful verified delivery retains its
existing archive path, including cleanup of the request initialization marker.

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

### Owner-only Telegram terminal operations gateway

A separate owner-only Telegram terminal operations gateway is an approved target convenience layer and is **not implemented yet**. Its authoritative detailed design is `telegram-terminal-operations.md`.

The gateway is distinct from the existing PCP Telegram governance/notification bot and must use a separate bot/token and trust boundary.

Target capability split:

```text
Human Owner Telegram private chat
  -> separate Terminal Bot
     -> /run-ro: arbitrary diagnostic logic inside a capability-restricted read-only runner
        -> PCP read-only broker / SELECT-only observer paths
     -> /run-op: named bounded operations with explicit confirmation and fresh state revalidation
     -> /run-admin: disabled by default
```

The read-only runner must not receive source/workspace write access, Runtime/provider/GitHub credentials, Docker socket, SSH agent, root/sudo capability or database mutation authority. Repository/workspace/log views are read-only and scratch writes are confined to a bounded temporary area.

Security must be enforced by OS/container/database permissions and brokered capabilities, not by regex or shell-text classification. A diagnostic script may be syntactically arbitrary while remaining unable to mutate protected state.

The read-only broker exists so common PCP diagnostics can inspect jobs, plans, actions, events, quota and bounded logs without exporting mutable Runtime/database credentials into the diagnostic process.

`/run-op`, if implemented, maps only to approved named operations through official Runtime/service interfaces. It must not become a generic elevated shell and must preserve active-job rollout gates, stale/replay checks, current project/WorkOrder identity and production decision boundaries.

This target does not change the normal ChatGPT/operator interaction convention: ordinary read-only blocks remain ordinary terminal-safe blocks. Telegram-specific metadata/format is emitted only when the Human Owner explicitly requests a Telegram-ready block.

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

Telegram terminal /run-ro target
  - owner/private-chat authenticated ingress
  - arbitrary diagnostic logic inside read-only capability sandbox
  - repository/workspace/log views read-only
  - brokered PCP inspection only
  - no Runtime/provider/GitHub/SSH secrets
  - no Docker socket
  - no database mutation
  - no source/workspace mutation
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
