# Personal-Scale Efficiency Model

Status: Human Owner-approved target policy and implementation direction. Approved 2026-09-15. Most behaviors in this document are not implemented yet; issues #146-#151 track delivery.

This document defines how the Personal Coding Platform should maximize useful engineering throughput and quality while keeping model/provider/resource consumption appropriate for one person. It complements `architecture.md`, `operating-model.md`, `provider-policy.md`, and `roadmap.md` without weakening any existing trust, security, production, or governance boundary.

## 1. North-star outcome

A healthy routine ticket should normally move through:

```text
Ticket
  -> PM triage / WorkOrder
  -> Router staffing + task resource estimate
  -> primary developer
  -> targeted/focused verification during iteration
  -> final deterministic verification
  -> risk-proportionate review
  -> PM outcome
  -> PR / CI
  -> PM merge when eligible
```

without Human Owner intervention.

Human Owner attention is intentionally reserved for material decisions and true exceptional conditions. A routine execution must not stop merely because a heuristic estimate or profile-default counter was reached while the job is still making healthy progress inside the approved personal resource envelope.

## 2. Efficiency objective

The platform is not trying to maximize the number of agents, conversations, model calls, test runs, or parallel tasks. It is trying to maximize useful accepted work per unit of:

- provider/model quota;
- model calls and tokens;
- tool calls;
- verification runs;
- wall time;
- monetary cost;
- Human Owner attention.

Additional roles or model calls are justified only when their expected value exceeds their resource cost.

## 3. Human attention is a first-class resource

Human Owner attention is one of the platform's scarcest resources.

Routine targets:

```text
human_interventions_per_task -> 0
avoidable_blocks_per_task -> 0
time_waiting_for_owner on routine execution -> 0
```

Examples of undesirable routine interruptions:

- `repair 4/4 -> approve +1` while the repair loop is making useful progress;
- `tests 14/14 -> approve +2` when required verification still has a healthy path forward;
- `wall time reached -> approve +20 min` when no loop/anomaly/resource problem exists.

These events should be treated as workflow inefficiency and measured separately from legitimate Human Owner decisions.

Human Owner intervention remains required for protected boundaries already defined by the Constitution and operating model, including scope/non-goal changes, architecture invariants, major services/dependencies, security/auth/trust boundaries, destructive data changes, production actions/policy, high-authority governance changes, and material expansion of the approved personal resource envelope.

## 4. Budget semantics: estimate, working envelope, emergency ceiling

Execution budget is not one number with one meaning.

The target model has three layers per relevant resource dimension:

### 4.1 Estimated usage

The estimate is what PM/Router expects the WorkOrder to need. It is used for planning, staffing, quota allocation, telemetry, and anomaly comparison.

Reaching the estimate is **not** a stop condition.

### 4.2 Autonomous working envelope

The working envelope provides normal headroom above the estimate. Runtime may consume or extend this headroom autonomously while execution remains healthy and total personal-resource policy allows it.

Crossing an estimate or working target should create telemetry/activity, not Human Owner attention by itself.

### 4.3 Emergency hard ceiling

The emergency ceiling is a deterministic circuit breaker. It protects against runaway execution, unexpected resource consumption, implementation bugs, or a task whose real shape materially exceeds the approved envelope.

Reaching an emergency ceiling may block and require PM/Human Owner action according to the existing authority model.

Durable counters are never reset when headroom is extended.

## 5. Task-specific effort/resource estimation

Profile (`fast`, `standard`, `complex`, `critical`) remains useful for broad staffing/risk behavior, but profile-fixed counters must not be the sole resource estimate.

Each WorkOrder should carry an effort/resource shape such as:

```yaml
effort:
  implementation: medium
  verification: high
  uncertainty: medium
  collaboration: low
expected:
  implementation_turns: 2
  repair_turns: 3
  verification_cycles: 6
  consultations: 0
```

These are estimates, not promises or false-precision project-management hours.

Router should derive resource estimates from available signals including:

- expected file/component scope;
- dependency depth;
- ambiguity;
- architecture impact;
- verification difficulty;
- security/risk;
- context requirement;
- novelty;
- reasoning requirement;
- availability of existing tests/patterns;
- task class and requested logical role;
- later, observed historical performance for comparable tasks.

## 6. Healthy-progress automatic headroom

When a working estimate/envelope is reached, Runtime should evaluate execution health before deciding whether to continue.

Healthy progress means, at minimum:

- progress markers are changing meaningfully;
- the same failure fingerprint is not repeating beyond policy;
- the diff/solution is not oscillating;
- scope is not expanding unexpectedly;
- no protected decision boundary has been discovered;
- provider/resource state remains eligible;
- cost/quota policy still permits continuation;
- the emergency hard ceiling has not been reached.

If healthy, Runtime may grant bounded automatic headroom to the same job/workspace and persist an auditable event describing the dimension, previous working limit, new working limit, current usage, reason, and applicable emergency ceiling.

If unhealthy, existing circuit-break behavior applies.

## 7. Provider quota is not task budget

Provider quota/resource state and WorkOrder estimates are separate concepts.

```text
provider quota/resource state
  = real external capacity with reset windows and scarcity

task estimate
  = expected resource shape for this WorkOrder

emergency execution ceiling
  = safety circuit breaker
```

Authoritative provider exhaustion can exclude/reroute a resource or block when no eligible fallback exists. A task estimate being reached must not be presented as if the provider itself is exhausted.

Router should allocate scarce provider capacity across work while avoiding unnecessary interruption of a healthy task.

## 8. Anti-loop and anomaly detection are primary circuit breakers

The system should prefer behavioral evidence over arbitrary low counters when deciding that execution is unhealthy.

Primary circuit-break signals include:

- repeated failure fingerprints;
- no-progress iterations;
- diff/solution oscillation;
- unexpected scope growth;
- protected decision boundaries;
- provider/resource exhaustion without fallback;
- abnormal cost/resource growth;
- emergency hard ceiling reached.

Normal engineering activity such as one more targeted test or a productive repair turn should not itself be considered an anomaly.

## 9. Layered deterministic verification

Final acceptance remains deterministic and reproducible. Efficiency comes from changing when expensive verification runs, not weakening the final gate.

Target layers:

```text
implementation / repair
  -> cheap targeted check
  -> focused affected tests
  -> stable checkpoint
  -> required full deterministic verification
```

Examples:

- syntax/static check or directly affected unit test during a narrow repair;
- component/test-group verification after the implementation stabilizes;
- full required project suite only at final/meaningful checkpoints or when the WorkOrder contract requires it earlier.

A passing narrow check never substitutes for required final verification.

## 10. Failure and retry accounting

Resource telemetry must distinguish engineering work from infrastructure/provider recovery.

At minimum classify:

- `engineering_repair`;
- `provider_recovery`;
- `infrastructure_retry`;
- `verification_retry`;
- `delivery_retry`.

A provider timeout, quota reroute, CI observation retry, or delivery infrastructure failure must not consume an engineering-repair iteration unless actual code repair occurred.

This separation is necessary both for fair budgeting and for useful telemetry calibration.

## 11. Bounded inter-agent collaboration

The target team may collaborate, but not as an unconstrained chat swarm.

Default workspace authority:

```text
Primary Developer
  -> write-capable in the isolated job workspace

Consultant / Tester / Debugger / Specialist / Reviewer
  -> read-only evidence/workspace access by default
```

A second role receives write authority only through a separate explicitly authorized WorkOrder/execution path.

### 11.1 Consultation trigger

Consultation should be used when expected value justifies its cost, such as:

- uncertainty about an existing project pattern;
- cross-component semantics;
- difficult verification/test design;
- security-sensitive behavior;
- repeated failed approach;
- reviewer finding;
- uncertainty high enough that another viewpoint is cheaper than another blind implementation iteration.

### 11.2 Router staffing

The initiating role requests a logical role and objective, for example:

```yaml
consult:
  role: test_engineer
  objective: challenge the recovery verification strategy
```

Router chooses provider/model. Agents must not name a provider/model as the collaborator identity.

### 11.3 CollaborationThread

Collaboration should be stored as a compact artifact, not an unbounded transcript.

Target shape:

```yaml
thread_id: CT-104
work_order: T-123
topic: release_identity
initiator_role: backend_developer
participant_role: test_engineer
question: ...
evidence_refs: [...]
response:
  recommendation: ...
  risks: [...]
  suggested_tests: [...]
status: resolved
rounds: 1
```

Default policy:

- concrete question required;
- compact relevant evidence required;
- normally 1-2 rounds;
- bounded number of open threads;
- recursive consultant-to-consultant fanout disabled by default;
- duplicate-question loops blocked;
- unresolved disagreement becomes structured evidence for PM rather than an infinite debate.

## 12. Reviewer dialogue

Review is allowed to be a bounded engineering conversation rather than a one-shot pass/fail oracle.

Target flow:

```text
Developer
  -> deterministic evidence
  -> Reviewer finding/question
  -> Developer response or repair
  -> Reviewer re-check
  -> ReviewReport
```

Normally allow at most 1-2 review dialogue rounds before PM receives the unresolved evidence and decides repair, reassignment, alternate specialist, replan, or a protected Human Owner decision.

Do not recursively review reviewers by default.

## 13. Risk-proportionate review

Independent review spend must match risk and expected useful value.

Target policy:

- routine + strong deterministic evidence: no separate model review or lightweight alternate-model review according to policy;
- standard: bounded independent Task Contract + diff review;
- complex: stronger independent reviewer;
- critical/security/architecture: different-model/provider review required when eligible capacity exists.

Measure:

- reviewer findings per review;
- findings that changed code/tests/decision;
- review model/token/wall resource use;
- useful-finding yield by task class/risk/reviewer strategy.

Low-yield review patterns should be reduced when policy permits; high-value review remains mandatory where risk justifies it.

## 14. Role-specific evidence packs and context compaction

Roles should consume compact evidence, not repeated full transcripts.

Example developer-repair pack:

```yaml
work_order_ref: ...
current_diff_ref: ...
failing_check: ...
reviewer_finding: ...
relevant_files: [...]
prior_attempt_summary: ...
```

Example reviewer pack:

```yaml
task_contract_ref: ...
changed_files: [...]
verification_summary: ...
developer_report: ...
relevant_source_of_truth: [...]
```

The role may retrieve additional repository context just in time when the pack is insufficient.

Raw developer/model transcripts remain diagnostic evidence, not default prompt context.

## 15. Telemetry-driven calibration

Collect before optimizing statistically:

- task class and logical role;
- task estimate vs actual usage;
- model/provider;
- first-pass success;
- engineering repair count;
- provider/infra/delivery retry counts;
- targeted/focused/full verification counts;
- CI pass rate;
- reviewer useful findings;
- wall time;
- model/tool/token/resource use;
- provider failure/quota pressure;
- final TaskOutcome;
- Human Owner interventions and reason class.

Calibrate only when sample size is meaningful. Sparse data should fall back to policy defaults; do not create false precision from a handful of tasks.

## 16. Human-attention telemetry

Track at minimum:

```text
human_interventions_per_task
avoidable_blocks_per_task
time_waiting_for_owner
decision_boundary_interventions
routine_operational_interventions
```

A protected decision is not an avoidable interruption. A routine '+1 repair' caused only by an underestimated healthy task is.

## 17. Continuity automation

After material events such as:

- PR merge;
- rollout;
- job terminal/stable-blocked transition;
- material governance decision;

PM/Runtime should produce a compact continuity update that replaces stale mutable state rather than appending raw chronological history.

Automation may update mutable continuity artifacts through the normal Git authority path. It must not silently rewrite durable architecture, governance, security, scope, or product policy.

## 18. Personal-scale concurrency

Default engineering concurrency remains one active WorkOrder because the platform is personal and quota-conscious.

Parallel WorkOrders are justified only when:

- dependencies are genuinely independent;
- workspace/merge collision risk is low;
- provider/resource envelope supports it;
- expected wall-time benefit outweighs coordination/context overhead.

Inter-agent collaboration does not imply parallel write execution.

## 19. Target routine execution flow

```text
Ticket
  -> PM
     - scope/risk
     - effort/resource shape
     - verification shape
     - likely collaboration need
  -> Router
     - logical staffing
     - provider quota awareness
     - task estimate + working envelope + emergency ceiling
  -> Primary Developer
     - targeted checks
     - optional bounded consultation
     - autonomous healthy repair loop
  -> final deterministic verification
  -> risk-proportionate reviewer
     - optional bounded dialogue
  -> PM outcome
  -> PR / CI
  -> PM merge
  -> telemetry + continuity update
```

Human Owner sits beside this flow, not in the middle of routine execution.

## 20. Implementation sequence

Umbrella: issue #146.

Priority order:

1. **#147 — Adaptive execution budgets + Human-attention circuit breakers.** Remove avoidable routine budget-block approvals while preserving emergency ceilings and compatibility.
2. **#148 — Layered verification + failure-budget separation.** Reduce unnecessary full-suite runs and make repair telemetry accurate.
3. **#149 — Bounded inter-agent collaboration + review dialogue.** Add read-only consultants and bounded role-to-role collaboration after budget semantics can absorb normal teamwork.
4. **#150 — Risk-proportionate review + role-specific evidence packs.** Spend review/context where useful.
5. **#151 — Telemetry calibration + Human-attention metrics + continuity automation.** Learn from real project data and prevent state-document drift.
6. **#98 — Constrained PM-controlled merge path.** Complete executable alignment so routine eligible PRs have no leftover manual merge checkpoint.
7. Telegram terminal convenience work remains lower priority than the execution-efficiency initiative unless an operational need changes that priority.

PM may split these issues further when implementation evidence shows a smaller safe delivery boundary.

## 21. Backward compatibility and rollout

- Existing persisted jobs/routes must remain readable and resumable.
- Existing explicit owner budget-extension records remain valid audit history.
- No implementation may reset durable usage counters or replace a job merely to adopt new budget semantics.
- During transition, old profile-fixed budgets may be interpreted as legacy working/emergency values only through an explicit compatibility rule tested against persisted state.
- Router/Runtime rollout must respect the active-job safety gate: no restart/rebuild while a job is active.
- Rollout verification must prove same-job/workspace/counter preservation for any pre-existing blocked job.

## 22. Non-goals

Do not optimize by adding complexity with no demonstrated return. Specifically, this initiative does not authorize:

- an always-on agent swarm;
- Best-of-N routine implementation generation;
- multiple concurrent writers in one workspace;
- recursive consultant chains;
- recursive reviewer-of-reviewer loops;
- blanket maximum-strength review for every task;
- production deployment by agents;
- weakened security/trust boundaries;
- arbitrary expansion of the personal resource envelope;
- large retrieval/vector infrastructure without evidence it is needed.

## 23. Success criteria

The initiative succeeds when evidence shows that, without weakening final quality/security gates:

- routine Human Owner interventions approach zero;
- avoidable budget blocks approach zero;
- accepted tasks use fewer unnecessary model calls/full-suite runs;
- wall-clock time from accepted ticket to merged PR improves;
- provider quota is used deliberately rather than through arbitrary per-task counter stops;
- reviewer useful-finding yield is maintained or improved while low-value review spend decreases;
- collaboration improves difficult-task outcomes without creating conversation loops;
- final deterministic verification and protected Human Owner decision boundaries remain intact.
