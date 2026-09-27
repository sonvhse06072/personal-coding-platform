# Personal-Scale Efficiency Model

Status: Human Owner-approved target policy and implementation direction. Approved 2026-09-15; healthy-progress non-blocking invariant reaffirmed and elevated 2026-09-17. Most behaviors in this document are not implemented yet; issues #146-#151 and follow-up work track delivery.

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

Human Owner attention is intentionally reserved for material decisions and true exceptional conditions. A routine execution must not stop merely because a heuristic estimate, profile-default counter, or static task limit was reached while the job is still making healthy progress inside the approved personal resource envelope.

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
- `wall time reached -> approve +20 min` when no loop/anomaly/resource problem exists;
- `input tokens reached profile default -> approve +1M` while the same WorkOrder is still making meaningful progress and no independent risk condition exists.

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

The emergency ceiling is a deterministic circuit breaker for abnormal execution or real material resource risk. It exists to protect against runaway loops, repeated no-progress behavior, implementation defects, unexpected scope/resource growth, or a task whose real resource shape materially exceeds the approved personal/project envelope.

A static numerical ceiling is not, by itself, a sufficient reason to classify a healthy task as abnormal. If a healthy job reaches a profile/default counter with no independent anomaly, protected decision, provider exhaustion, or material resource-risk signal, the platform should treat the limit as a working-envelope/calibration problem and continue through bounded autonomous headroom rather than creating a Human Owner continuation gate.

Durable counters are never reset when headroom is extended.

### 4.4 Mandatory healthy-progress non-blocking invariant

This is a required design and acceptance rule for all Router, Runtime, reassessment, recovery, budget, and Human Attention work:

- A job making meaningful progress must not be blocked solely because it reached a static model-call, token, tool-call, test-run, wall-time, repair, iteration, profile, or similar counter.
- Changed-file count follows the same principle on effective adaptive WorkOrders: the WorkOrder value is a working target, not proof of scope drift. Bounded headroom may continue while actual changed paths stay outside protected decision families and the emergency scope ceiling is not exceeded. Legacy-hard WorkOrders keep their strict file-count ceiling.
- Scope authority is path/contract-aware rather than count-only: governance/scope-frame, dependency, security/auth, migration/destructive-data and production-sensitive paths remain independent fail-closed decision signals regardless of changed-file count.
- A hard stop must cite an independent stop justification beyond counter exhaustion: repeated failure/no progress, solution oscillation, unexpected scope growth, runaway or abnormal resource growth, authoritative provider exhaustion without eligible fallback, a protected decision boundary, or a genuinely material expansion of the approved personal/project resource envelope.
- Healthy continuation inside the approved resource envelope should occur automatically on the same durable job/workspace with non-decreasing counters and auditable headroom changes.
- A Human Owner `continue`, `+N`, or budget-extension click whose only purpose is to compensate for an underestimated healthy task is an avoidable platform defect, not an acceptable steady-state control flow.
- Hard ceilings must be calibrated high enough and/or coupled to behavioral anomaly evidence so routine progressing tasks do not encounter them as ordinary workflow checkpoints.
- Existing compatibility/recovery controls may remain temporarily while migrating old persisted jobs, but they must not be mistaken for the target behavior when the underlying task is healthy.

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
- verification difficulty/shape;
- security/risk;
- context requirement;
- novelty;
- reasoning requirement;
- availability of existing tests/patterns;
- task class and requested logical role;
- later, observed historical performance for comparable tasks.

## 6. Healthy-progress automatic headroom

When a working estimate/envelope or profile/default counter is reached, Runtime must evaluate execution health before deciding whether to continue.

Healthy progress means, at minimum:

- progress markers are changing meaningfully;
- the same failure fingerprint is not repeating beyond policy;
- the diff/solution is not oscillating;
- scope is not expanding unexpectedly;
- no protected decision boundary has been discovered;
- provider/resource state remains eligible;
- cost/quota policy still permits continuation;
- there is no independent evidence of runaway/abnormal resource growth or a genuinely material resource-envelope expansion.

If healthy, Runtime should grant bounded automatic headroom to the same job/workspace and persist an auditable event describing the dimension, previous working limit, new working limit, current usage, reason, and applicable safety ceiling. Merely crossing a static counter is telemetry, not a Human Owner stop reason.

If unhealthy, existing circuit-break behavior applies. The block reason must identify the anomaly/material decision condition, not only the exhausted counter.

If the platform repeatedly needs Human Owner continuation for otherwise healthy work, the relevant limit/policy is considered miscalibrated and should become implementation follow-up work.

## 7. Provider quota is not task budget

Provider quota/resource state and WorkOrder estimates are separate concepts.

```text
provider quota/resource state
  = real external capacity with reset windows and scarcity

task estimate
  = expected resource shape for this WorkOrder

emergency execution ceiling
  = safety circuit breaker for abnormal/material-risk execution
```

Authoritative provider exhaustion can exclude/reroute a resource or block when no eligible fallback exists. A task estimate or profile counter being reached must not be presented as if the provider itself is exhausted.

Router should allocate scarce provider capacity across work while avoiding unnecessary interruption of a healthy task.

## 8. Anti-loop and anomaly detection are primary circuit breakers

The system must prefer behavioral evidence over arbitrary low counters when deciding that execution is unhealthy.

Primary circuit-break signals include:

- repeated failure fingerprints;
- no-progress iterations;
- diff/solution oscillation;
- unexpected scope growth;
- protected decision boundaries;
- provider/resource exhaustion without fallback;
- abnormal cost/resource growth;
- emergency-limit usage accompanied by independent evidence that continuation would be abnormal or materially exceed the approved envelope.

Normal engineering activity such as one more targeted test, a productive repair turn, or higher-than-estimated token use while progress remains meaningful should not itself be considered an anomaly.

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

A protected decision is not an avoidable interruption. A routine continuation action caused only by an underestimated but healthy task is avoidable and should be classified as a platform efficiency defect.

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
     - task estimate + working envelope + anomaly/material-risk circuit breaker
  -> Primary Developer
     - targeted checks
     - optional bounded consultation
     - autonomous healthy repair loop
     - automatic healthy-progress headroom when needed
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

1. **#147 — Adaptive execution budgets + Human-attention circuit breakers.** Remove avoidable routine budget-block approvals while preserving justified emergency ceilings and compatibility.
2. **#148 — Layered verification + failure-budget separation.** Reduce unnecessary full-suite runs and make repair telemetry accurate.
3. **#149 — Bounded inter-agent collaboration + review dialogue.** Add read-only consultants and bounded role-to-role collaboration after budget semantics can absorb normal teamwork.
4. **#150 — Risk-proportionate review + role-specific evidence packs.** Spend review/context where useful.
5. **#151 — Telemetry calibration + Human-attention metrics + continuity automation.** Learn from real project data and prevent state-document drift.
6. **#98 — Constrained PM-controlled merge path.** Complete executable alignment so routine eligible PRs have no leftover manual merge checkpoint.
7. Any discovered static-counter continuation gate affecting healthy work takes priority as a bounded follow-up under this policy.
8. Telegram terminal convenience work remains lower priority than the execution-efficiency initiative unless an operational need changes that priority.

PM may split these issues further when implementation evidence shows a smaller safe delivery boundary.

## 21. Backward compatibility and rollout

- Existing persisted jobs/routes must remain readable and resumable.
- Existing explicit owner budget-extension records remain valid audit history.
- No implementation may reset durable usage counters or replace a job merely to adopt new budget semantics.
- During transition, old profile-fixed budgets may be interpreted as legacy working/emergency values only through an explicit compatibility rule tested against persisted state.
- Compatibility controls that still require owner continuation for healthy work are temporary migration mechanisms and must have a follow-up path to the mandatory non-blocking invariant.
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
- silent counter resets or unbounded continuation;
- large retrieval/vector infrastructure without evidence it is needed.

## 23. Success criteria

The initiative succeeds when evidence shows that, without weakening final quality/security gates:

- routine Human Owner interventions approach zero;
- avoidable budget blocks approach zero;
- no healthy-progress task requires owner continuation solely because a static task/profile counter was reached;
- hard stops can identify a real anomaly, protected decision, provider exhaustion, or material resource-risk reason beyond mere counter exhaustion;
- accepted tasks use fewer unnecessary model calls/full-suite runs;
- wall-clock time from accepted ticket to merged PR improves;
- provider quota is used deliberately rather than through arbitrary per-task counter stops;
- reviewer useful-finding yield is maintained or improved while low-value review spend decreases;
- collaboration improves difficult-task outcomes without creating conversation loops;
- final deterministic verification and protected Human Owner decision boundaries remain intact.
