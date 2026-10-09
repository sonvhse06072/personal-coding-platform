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

Authenticated `POST /v1/intake` is the canonical new Human/Chat PM ticket
handoff. Its pure versioned classifier defaults to planning when explicit
bounded-direct intent or structured evidence is missing. Complete low-materiality
evidence and no protected/dependency/multi-unit trigger permit one normal direct
job. Exact policy thresholds and required evidence are in
`operating-model.md` under canonical new-ticket intake. File count alone cannot
classify a ticket as large. Intake requires and pins an approved ProjectBaseline.
Provider/model selection remains Router staffing, never intake-policy authority.

The planning branch reuses `PMPlanner -> ExecutionPlan -> PlanOrchestrator ->
WorkOrders`, including the same registration/tick path as `/v1/plans`. Structured
semantic/repo hints accompany the ticket into PM triage. Materially non-trivial
intake sets the backward-compatible `decomposition_required` constraint: an
in-scope result with no decision boundaries needs at least two coherent,
independently verifiable WorkOrders before becoming ready. Violations persist a
failed planning result with no executable plan. Out-of-scope/human-decision/
ambiguous plans need no artificial work. Default `/v1/plans` and externally
supplied PM-bridge plans keep their existing single-WorkOrder behavior.

Direct intake uses the existing engine and creates no ExecutionPlan. A private
engine keyword includes compact `canonical_intake` decision evidence in the
same initial INSERT as the job, before it is visible to enqueue/startup. It
preserves task signals, repo hints, capacity state and the approved baseline.
`auto_run=false` skips direct enqueue. Planning retains existing automatic
orchestration. Explicit/manual `POST /v1/jobs`, its helper and legacy `/run`
recovery are unchanged; existing durable jobs/plans are not migrated or
reinterpreted. This intake adds no Human Owner continuation gate, parallel
WorkOrders, developer credentials, merge or production authority.

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

ExecutionPlans have a caller-owned `execution_mode` of `autonomous` or
`supervised`; omitted legacy fields resolve to `autonomous`. The planning model
proposal does not contain this policy field. Canonical intake carries the caller
selection into planning, and rejects a supervised request when deterministic
classification selects direct execution instead of silently changing the
classification. Autonomous scheduling remains unchanged.

For a supervised plan, the existing orchestrator creates a `supervised_hold`
only between WorkOrders: after an active WorkOrder has an exact durable
`completed` or `merged` checkpoint, no child is running, awaiting merge,
waiting for an operator, blocked or repair-reopened, and at least one pending
WorkOrder is dependency-ready. The first WorkOrder starts normally and a fully
completed plan does not hold. The existing `cp_plan_orchestrations` row owns the
gate; there is no additional scheduler or WorkOrder state machine.

Each hold persists a monotonic generation, exact checkpoint ID/key/WorkOrder,
the sorted complete ready set, state `held` or `released`, and a bounded
`plan:continue:` SHA-256 key over canonical JSON containing plan ID, generation,
checkpoint ID/key and the sorted ready set. Authenticated
`POST /v1/plans/{plan_id}/continue` locks that row, recomputes and validates the
whole identity, and atomically changes only the gate to `released`. It then uses
the normal tick and launch path. An exact retry of the current released identity
is a read-only idempotent success that returns without invoking the orchestrator
tick, even after its child runs, waits for an operator or merge, blocks, or
completes; stale or mismatched generations fail closed. A released generation remains released
while ordinary launch constraints such as a direct-project lease are busy, so a
later tick may launch without another continuation. A later terminal checkpoint
and ready-set identity creates the next generation. With no next job created
before release, ordinary job `/run` cannot bypass the gate.

Supervised continuation never supplies Human Owner authorization or changes
decision boundaries, operator `waiting_human`, merge, dependency, concurrency,
lease, Runtime job identity, budget, routing, verification or delivery policy.
Protected decisions and child gates retain precedence. Runtime progress and the
Dashboard project the same durable supervision identity, and the single managed
parent progress comment renders its current held or released state.

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
#367 adds canonical intake; #368 adds parent-ticket publication below.
#369 adds the detailed blocked evidence projection below; #370 adds the
plan-level supervised projection and exact continuation gate above.

When an active WorkOrder is blocked, the progress projection derives one compact
`blocked_evidence` pack from the same repeatable-read snapshot and append-only
checkpoint store. It selects terminal `completed`/`merged` checkpoints only for
currently completed WorkOrders, the newest `blocked` checkpoint matching the
exact active WorkOrder/job identity, a 32-row checkpoint window restricted to
that same identity for the latest useful evidence, and the preceding
`completed`/`merged` checkpoint as the last known-good point. An `accepted`
checkpoint invalidated by `repair_reopened` never becomes known-good. It reports
untouched pending WorkOrders, the current branch when present, bounded
verification and reviewer/PM outcomes from the existing checkpoint whitelist,
and one advisory action from the closed
`repair`/`reroute`/`human_decision`/`replan`/`retry_delivery` vocabulary. The
exact current block reason takes precedence over retained PM outcomes. Hard
budget stops advise a human decision; GitHub CI infrastructure failures advise
delivery retry. Unrecognized free-form block
text is hash-identified rather than echoed. Raw checkpoint JSON, logs, prompts,
results and credentials are excluded. Projection reads never schedule, resume,
reroute or mutate a plan, WorkOrder, job, checkpoint or GitHub object, and store
recreation produces the same pack from PostgreSQL.

Parent-ticket progress uses a separate `cp_plan_progress_handoffs` relation,
never `cp_notification_outbox`. PlanOrchestrator stages a bounded whitelist
of durable plan/WorkOrder/checkpoint fields after engineering commits. Its
transition fingerprint includes plan identity/state/lifecycle, latest checkpoint
ID/key, ordered WorkOrder state/job identities and dependency-ready IDs; the
checkpoint-free initial shape is deterministic too. Polling timestamps, raw
detail, results, prompts, logs and provider failures are excluded. Generations
advance only when transition/body changes. One SHA-256(project_id + ':' +
issue_number) row is shared by later plans for that issue; older plans cannot
overwrite a newer plan's publication. Existing engineering/checkpoint semantics
and n8n claim/ack/release are unchanged.

For a blocked transition, the same managed comment renders the bounded
`blocked_evidence` pack: prior completed checkpoint identities/commits/PRs,
exact current block identity and safe diagnostics, untouched pending WorkOrders,
last known-good checkpoint and advisory next action. The existing 12 KiB UTF-8
body ceiling, one-comment identity, generation dedupe and publisher isolation
remain authoritative.

A persisted feature-install timestamp excludes earlier plans without a handoff.
Eligible terminal plans are also revisited, so a crash after the final engineering
commit cannot lose completion/block publication. Existing rows recover on restart.
A separate Runtime publisher claims with `FOR UPDATE SKIP LOCKED`, a 180-second
lease and an increasing attempt fence. Staging preserves an in-flight lease.
Acknowledging an older generation records its comment ID and published hash but
leaves newer desired progress pending. Only exact desired generation/body/hash
acknowledgement marks sent. Expired leases recover; failures retain known comment
identity, record only an error type and retry with a capped 300-second delay.
Publication never gates scheduling or changes engineering state.

Parent binding prefers an exact positive integer `staffing.issue_number`, then
an exact canonical `GH-N` ticket ID. Malformed supplied staffing fails closed;
prose and stored URLs never select an issue or repository. Runtime sends only
project/issue/key/body/optional known comment ID to the internal-token-authenticated
executor `/v1/github/pm-bridge/progress` endpoint. The executor resolves repository
from registered project source origin, checks the real issue (rejecting PRs),
recomputes the key and owns the `PCP:PLAN-PROGRESS` HTML marker. Final UTF-8
comment size is at most 12 KiB. It validates a known comment's exact repository,
issue and marker; only a missing/deleted ID falls back to discovery. Discovery
examines at most five 100-comment pages, fails closed on ambiguity or an incomplete
scan, and finds an uncertain prior create before attempting another. Mutations
are serialized across executor threads/processes on the existing single host.
Exact comment revalidation precedes PATCH; readback validates body/hash and
identity before success. Runtime and developer agents receive no GitHub delivery
credential. This adds no merge or deployment authority.

The current implementation may still contain manual-merge orchestration behavior from the previous governance policy. That behavior is transitional implementation state, not the approved target authority model after issue #96. Runtime/ddev-executor changes that automate the PM merge gate must preserve all existing trust boundaries and be delivered separately through normal PR/CI review.

### Isolated workspaces

Each coding job uses a self-contained clone pinned to the source commit and an `ai/*` branch. The agent workspace has no Git remote. This is deliberate: agents may modify workspace files but cannot independently publish to the source repository.

### ddev-executor

`ddev-executor` is the privileged boundary. It is the only platform service intended to have the Docker socket, target source-repository visibility needed for workspace creation, and GitHub delivery credentials/capabilities.

It accepts registered project IDs and bounded operations rather than arbitrary remote command execution. It validates workspace identity, branch namespace, source ancestry, expected commits, and project autonomy policy before publishing.

PM-controlled merge capability, when implemented, must remain behind a constrained Runtime/ddev-executor operation that validates the exact PR/head, CI/review state, project/WorkOrder identity, and absence of unresolved human-decision triggers. Developer-agent subprocesses must never receive GitHub merge credentials or direct merge capability.

### Agent adapters

Current coding adapters include Codex CLI, OpenCode and the Antigravity host adapter. Provider/model choice is separate from the logical role being performed.

Reasoning effort is a per-PCP-model capability, not an adapter-wide or
provider-wide assumption. The model registry supplies each model's ordered
allowed values. Router may assign or escalate only within that list and the
route's unchanged policy ceiling; the canonical ordering is used only to find
the next allowed value. Runtime revalidates the durable PCP model id, adapter,
upstream model and explicit effort against its mounted registry before every
agent invocation and before model-attempt accounting. `xhigh` and `max` are
currently representable Codex capabilities, not automatic routing policy;
normal profile ceilings remain at or below `high`, and Astra remains limited
to its existing manual `frontier_escalation` role.

The architecture requires developer-agent subprocesses to receive only the process environment and provider credential needed for that specific call. They must not receive internal platform credentials or unrelated provider keys.

Codex CLI is an unattended Runtime worker, so its approval behavior must be explicit rather than inherited from mounted user configuration. Planner/evaluator turns use `read-only`; execute/repair turns use `workspace-write`; all Codex turns use approval policy `never`, and workspace-write network access is explicitly disabled. A command that requires permission outside the selected sandbox must fail closed rather than wait for interactive approval. `danger-full-access` and approval/sandbox bypass flags are outside the approved developer-agent trust boundary.

Agent adapters expose invocation capabilities independently of provider identity;
the default remains local-listener capable unless an adapter explicitly declares
otherwise for a mode. Project DDEV verification phases may declare required
capabilities. Runtime gives the selected developer/evaluator only bounded phase
names when an adapter cannot supply a required surface. Developer context treats
configured phase metadata as forward-looking and conditional. Evaluator context
intersects that metadata with phases already marked required in the authoritative
Runtime verification result; it does not recompute applicability. This model
context does not skip, satisfy or reinterpret the phase: final Runtime/
ddev-executor evidence remains authoritative, while capable adapters receive no
restrictive instruction.

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

### Refactor target 2026-10-09: one efficient autonomous execution path

**Status:** Owner-approved architectural **direction**, not a statement that all components exist or that security/credential/merge invariants have been amended. The canonical product outcomes are in [business-strategy.md](business-strategy.md), the implementation priorities in [roadmap.md](roadmap.md), and day-to-day authority in [operating-model.md](operating-model.md).

~~~text
Owner + ChatGPT: approve business, architecture, ProjectBaseline
  -> GitHub approved Source of Truth + scoped issue/contract
  -> PCP PM: deterministic direct-intake OR planning/dependencies
  -> Context Composer: pinned authority + minimal role/task context
  -> Router: model/effort/quota + appropriate review/tool/skill
  -> ONE trusted project-scoped developer writer
       edit -> local build/DDEV -> browse configured dev URL -> test -> repair
  -> required deterministic verification -> risk-aware review -> PR/exact CI
  -> PM final outcome + eligible merge -> next approved WorkOrder
          |
          + failure classifier -> safe self-healing/reassess/owner decision
          + TaskOutcome -> context/provider/skill efficiency feedback
~~~

No separate PM, reviewer, recovery daemon or provider-watcher service is required merely to represent a logical responsibility. Extend existing Runtime/Router/Executor/Guardian boundaries first; any new bridge or service must pass the economic and trust-boundary gates.

**Execution modes and cost:** A small already-approved task may use deterministic admission + single developer invocation rather than an additional full AI planning/evaluation loop. Complex/dependent tasks still receive PM planning and appropriate independent review. Select verification by affected paths during iteration; final configured required tests, exact-head CI and PM merge requirements remain. The complexity score and effort are planning estimates, not routine reasons to pause healthy progress.

**Trusted project developer — proposed, project-opt-in:** Keep a single writer bound to an exact registered project/workspace/lease and a per-run capability contract. Compare host-side constrained Codex, project-owned dev container and executor-brokered DDEV/Playwright as options in G0/G1; do not preselect an unsafe implementation. A developer may exercise routine local build, Drush/Composer/PHP/Node, private test fixtures, an allowlisted dev preview origin, browser evidence and related technical refactoring needed for approved acceptance criteria. A ready URL alone is **not** proof of visual review. Technical scope expansion is judged against requirements, architecture and risk, not file count alone. No blanket full host control, Docker socket/privileged credentials, unrelated filesystem access, production, destructive real data, unreviewed dependency or business changes. Direct-workspace authority must preserve existing branch/lease/dirty worktree. Widening any Constitution-level trust boundary requires a separate explicit ChangeProposal and approved implementation; this direction alone changes no Runtime permissions.

**Self-Healing as a bounded flow, not a generic resume bypass:** On significant failures, distinguish application code/test failure, platform verifier/config defect, stale executable/unsupported model-effort, provider quota/outage, local infrastructure/preview, source/lease collision and protected decision. Capture sanitized exact job/WorkOrder/source/checkpoint/diff identity and failure fingerprint. Use deterministic local recheck or bounded repair first; ask PM/Router to replan/reroute only on meaningful evidence. For a PCP code defect, prepare an isolated fix PR, validate exact-head CI, install only under existing rollout/quiescence gates, then prove the original failure changed before reopening the **same** preserved job. Do not reset counters, invent control authorization, repeat identical failing commands or create replacement jobs just to escape a block. Guardian remains the independent, finite out-of-band path for Runtime/n8n outages, never generic elevated shell. Irrecoverable or unsafe cases surface a concise Owner decision.

**Governed context:** Git/approved baseline defines durable business/architecture; Runtime stores mutable job state. Tier-0 rules are pinned, required WorkOrder constraints are non-optional, Tier-1 is current and Tier-2/3 are retrieved just in time, Tier-4 only for diagnostics. Integrate the existing deterministic Context Composer into PM/Developer/Reviewer *after measuring* role-specific coverage/provenance and token overhead. Doc-write guards must detect authority drift and stale/duplicated knowledge before merged documentation is used. See [context-memory-architecture.md](context-memory-architecture.md); standalone composer presence alone is not production integration proof.

**Provider and capability adaptability:** Discovery inputs (official release/catalog and actual authenticated CLI/app-server signals) are **candidate** metadata, not routable authority. Verify model slug, supported reasoning effort/transport, entitlement, privacy, quota and adapter version in a disposable canary; update a stable-ID versioned registry/CLI pin via reviewed PR, then safe rollout and benchmark before changing routing preferences. Likewise, select project rules/tools/skills using a project/task-specific registry; a skill is untrusted material and cannot grant permissions or rewrite approved docs. Prefer project-local skills, pinned provenance and feedback on accepted task results instead of default-loading every skill. Canonical provider policy: [provider-policy.md](provider-policy.md).

**Future only:** Autonomous Project Discovery and business interviewing for repositories without adequate documentation ([#588](https://github.com/sonvhse06072/personal-coding-platform/issues/588)) remain **deferred**. No code scanning of new repositories, draft-to-approved promotion, auto-registration or new intake mode is authorized by this roadmap.

**Migration and compatibility:** Do not reinterpret existing durable jobs, WorkOrders, checkpoints, pinned ProjectBaseline revisions, provider histories or leased direct workspaces when a new execution mode arrives. Use opt-in fixture/canary, feature-specific regression and verified source-vs-deployed state; Chợ Nhạc TECH-DEC-040 Codex-first remains authoritative for new approved work until a separate project decision changes it.


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
