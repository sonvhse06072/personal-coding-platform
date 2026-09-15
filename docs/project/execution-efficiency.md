# Personal-Budget Execution Efficiency

Status: Human Owner-approved target policy and implementation plan. Approved 2026-09-15. Implementation is incremental; code/tests remain authoritative for current executable behavior.

Parent initiative: GitHub issue #140.

## 1. Objective

Optimize PCP for the highest practical engineering throughput and quality that remains appropriate for a single-person resource envelope.

The platform should behave like a small engineering team without paying the cost of an always-on agent swarm. Routine healthy work should normally move from WorkOrder to verified/merged outcome without Human Owner intervention.

The primary efficiency objective is not to minimize every individual model call or test run. It is to minimize total cost per useful completed outcome while preserving correctness, trust boundaries, and Human Owner control over protected decisions.

## 2. Core operating principles

1. **Human attention is a scarce resource.** Routine tasks target zero avoidable Human Owner interventions.
2. **Task budgets are estimates before they are circuit breakers.** Healthy execution may use bounded automatic headroom without an owner click.
3. **Provider quota is separate from task budget.** A real external quota exhaustion may require reroute/block; merely exceeding a task estimate should not.
4. **Deterministic correctness remains mandatory.** Efficiency must not weaken required final verification or CI gates.
5. **Use the cheapest sufficient intelligence.** Strong/scarce models are reserved for work where they materially improve success, review quality, or recovery.
6. **Collaboration is selective, not ambient.** Add a second agent when expected value justifies the cost; do not create default multi-agent chatter.
7. **Context is evidence, not transcript.** Roles receive compact, task-specific evidence packs and retrieve more context just in time when needed.
8. **Retry accounting must describe reality.** Provider/infra/delivery retries are not engineering repair iterations.
9. **Telemetry calibrates policy, but small samples do not justify false precision.**
10. **Trust boundaries remain unchanged.** Developer agents stay isolated and unprivileged; PM/Runtime/ddev-executor authority boundaries remain intact.

## 3. Target happy path

```text
Ticket
  -> PM triage
     -> scope/risk/decision-boundary check
     -> effort/resource-shape estimate
     -> verification shape
     -> expected collaboration/review level
  -> Router
     -> role staffing
     -> provider/quota-aware selection
     -> task-specific estimated budget
     -> elastic working envelope
     -> emergency hard ceilings
  -> Primary Developer
     -> targeted implementation checks
     -> optional bounded specialist consultation
     -> healthy autonomous repair loop
  -> full deterministic verification
  -> risk-proportionate independent review
     -> at most bounded developer/reviewer dialogue
  -> PM outcome
  -> PR + CI
  -> PM merge when eligible
  -> telemetry + continuity update
```

Human Owner should normally enter only for protected product/architecture/security/production/destructive decisions, true external resource exhaustion without safe fallback, emergency budget ceilings, unresolved material disagreement, or abnormal/runaway execution.

## 4. Adaptive task budgeting

### 4.1 Three budget layers

Each WorkOrder should move toward three budget concepts:

```yaml
budget:
  estimate:             # planning/forecast value; not a routine stop
  working_envelope:     # autonomous healthy-progress headroom
  emergency_hard_ceiling: # fail-closed circuit breaker
```

The Router may derive these from profile defaults plus WorkOrder/repository/verification characteristics. Profile values remain useful priors/floors, but must not remain the only source of task budget.

### 4.2 WorkOrder effort/resource shape

PM/WorkOrder should describe resource shape without pretending to know exact runtime:

```yaml
effort:
  implementation: low | medium | high
  verification: low | medium | high
  uncertainty: low | medium | high
expected:
  implementation_turns: ...
  repair_turns: ...
  verification_cycles: ...
  consultations: ...
  review_rounds: ...
```

Router combines that with observed complexity dimensions such as scope, dependency depth, ambiguity, architecture impact, verification difficulty, risk, context requirement, novelty and reasoning requirement.

### 4.3 Healthy automatic headroom

Exceeding an estimate or soft working target does not by itself justify blocking.

Runtime may continue automatically inside the approved working envelope when:

- progress markers show real movement;
- failure fingerprints are not repeating beyond policy;
- the diff is not oscillating;
- scope is not unexpectedly expanding;
- verification is progressing;
- no Human Owner decision boundary exists;
- provider/model health and quota remain acceptable;
- no emergency resource/cost ceiling is reached.

Automatic headroom must preserve consumed counters and produce durable telemetry/audit evidence. It must not reset usage.

### 4.4 Circuit breakers

Hard interruption is appropriate for conditions such as:

- repeated failure beyond policy;
- no-progress iterations;
- diff/solution oscillation;
- unexpected scope growth;
- real provider/model exhaustion without safe fallback;
- emergency task/personal-budget ceiling;
- protected decision boundary;
- unresolved high-impact disagreement;
- other deterministic safety failures.

A sequence such as `repair 4/4 -> owner approves +1 -> test 14/14 -> owner approves +2` is considered an avoidable workflow interruption when the task is otherwise healthy.

## 5. Personal resource envelope

Task budgets sit inside a broader personal resource envelope.

The resource envelope may include:

- provider weekly/daily quota and reset windows;
- scarce subscription capacity;
- paid cost;
- wall time;
- total model calls/tokens;
- Human Owner attention;
- provider reliability/latency.

Router/PM should optimize allocation across tasks, not merely stop each task at low local thresholds.

Material expansion of the approved personal/project resource envelope remains a Human Owner decision.

## 6. Human Attention Budget

Human attention is an explicit efficiency metric.

Target routine-task metric:

```text
avoidable_human_interventions_per_task = 0
```

Useful telemetry includes:

- owner interventions per task;
- avoidable budget-extension blocks;
- time waiting for owner;
- intervention reason/category;
- decision-boundary versus operational-continuation distinction.

Telegram notifications that merely request continuation of healthy routine execution should become exceptional rather than normal.

## 7. Layered verification

Verification should be staged by value/cost while preserving final deterministic acceptance.

Target tiers:

1. **cheap/targeted checks** during implementation or a narrow repair;
2. **focused affected tests/static checks** when the patch stabilizes;
3. **full deterministic verification** at meaningful acceptance/delivery checkpoints.

Full verification remains mandatory where the WorkOrder/project policy requires it. Layering only reduces redundant full-suite execution during intermediate repair loops.

Verification evidence is durable and must identify which tier ran and why.

## 8. Failure-budget separation

Runtime/telemetry should distinguish at least:

- engineering repair;
- provider recovery/failover;
- infrastructure retry;
- verification retry;
- delivery/CI retry.

A provider timeout, quota reroute, dashboard failure, or delivery-infrastructure retry must not silently consume the same budget/telemetry category as an engineering code repair.

This separation improves both runtime policy and later calibration.

## 9. Bounded inter-agent collaboration

### 9.1 Collaboration objective

Agents may consult one another to improve implementation, debugging, test strategy, review quality, or uncertainty resolution, but collaboration must be purposeful and bounded.

### 9.2 Writer model

Default collaboration model:

```text
Primary Developer -> workspace write capability
Consultant/Tester/Debugger/Specialist/Reviewer -> read-only evidence/workspace view
```

Only one primary writer acts on a WorkOrder workspace at a time unless a future explicitly approved architecture change proves multi-writer execution is safe and worthwhile.

### 9.3 CollaborationThread

Target durable artifact:

```yaml
thread_id: CT-...
work_order: ...
topic: ...
initiator_role: ...
participant_role: ...
question: ...
evidence_refs: [...]
response:
  recommendation: ...
  risks: [...]
  suggested_tests: [...]
status: open | resolved | escalated
rounds: ...
```

Store compact conclusions/evidence, not unbounded conversational transcripts.

### 9.4 Collaboration triggers

Consultation is justified by signals such as:

- high uncertainty;
- difficult verification strategy;
- cross-component behavior;
- unknown project pattern;
- repeated failed approach;
- reviewer finding;
- security-sensitive logic;
- low confidence where a second opinion is cheaper than another blind repair.

### 9.5 Anti-meeting policy

Default constraints:

- concrete question required;
- evidence references required;
- small maximum number of rounds;
- small maximum number of simultaneous threads;
- duplicate-question guard;
- recursive consultation disabled by default;
- consultants do not independently spawn consultant chains.

The target is selective pair programming/review dialogue, not an agent meeting or swarm.

## 10. Reviewer/developer dialogue

Review may use a bounded dialogue:

```text
Developer result
  -> Reviewer finding
  -> Developer response/repair
  -> Reviewer re-check
```

Default review dialogue should stop after a small number of rounds. Persistent disagreement is summarized to PM with evidence rather than debated indefinitely.

PM may then accept, repair, reassign, request another specialist opinion, or escalate to a Human Owner decision when the disagreement touches a protected/material boundary.

## 11. Risk-proportionate review

Review strength should be chosen by expected value and risk.

Indicative policy:

- routine with strong deterministic checks: no or very lightweight model review where policy permits;
- standard: lightweight independent diff/Task Contract review;
- complex: strong independent reviewer;
- critical/security/architecture: different-model/provider review required where eligible capacity exists.

Telemetry should measure useful findings, findings that changed code/decision, resource cost and no-value/false-positive rate. Review policy should be calibrated from evidence, not tradition.

## 12. Role-specific Evidence Packs

Each role should receive the smallest context package sufficient for its decision.

Examples:

Developer repair:

```text
WorkOrder + current diff + failing check + relevant finding + relevant files + compact prior-attempt summary
```

Reviewer:

```text
Task Contract + relevant changed files/diff + deterministic verification summary + WorkReport + relevant source-of-truth refs
```

Consultant:

```text
specific question + evidence + relevant source slice + constraints
```

PM:

```text
structured WorkReport + verification + ReviewReport + CI/delivery + budget/provider/decision evidence
```

Raw logs/transcripts remain available for diagnostics but are not default role context. Just-in-time retrieval is preferred over large prompt stuffing.

## 13. WorkOrder sizing

PM should avoid both oversized and excessively fragmented WorkOrders.

Sizing considerations include implementation complexity, verification difficulty, context size, dependency boundaries, reviewability and expected coordination overhead.

A WorkOrder estimate is a resource-shape forecast, not a commitment to an exact number of minutes/calls.

## 14. Telemetry and calibration

Collect evidence including:

- role/task class;
- model/provider;
- task estimate versus actual resource use;
- first-pass success;
- engineering repair count;
- provider/infra/verification/delivery retry counts;
- verification cycles;
- reviewer findings/useful findings;
- CI result;
- wall time;
- token/model/tool use;
- provider quota pressure/failures;
- Human Attention metrics;
- final TaskOutcome.

Calibration should begin with transparent heuristics and only adjust by project/task/role after meaningful sample sizes exist.

## 15. Continuity/state maintenance

Project continuity must remain compact and current.

After material merge, rollout, terminal job transition or governance decision, the platform/PM should increasingly produce the required continuity update automatically or as a required delivery artifact.

`current-state.md` should replace stale operational state rather than append raw history. Git history remains the chronology/audit trail.

## 16. PM merge integration

The constrained PM-controlled merge path tracked by issue #98 remains an important dependency for the no-human-touch happy path.

Completion of engineering work should not require a routine Human Owner merge click when all approved PM merge gates are satisfied.

## 17. Implementation sequence

The approved implementation sequence under parent issue #140 is:

1. **Source-of-truth amendment** — this policy plus required Constitution/Operating Model/Roadmap/current-state references.
2. **#141 Adaptive task budgeting and Human Attention Budget.**
3. **#142 Layered verification and failure-budget separation.**
4. **#143 Bounded inter-agent collaboration and review dialogue.**
5. **#144 Risk-proportionate review and role-specific Evidence Packs.**
6. **#145 Telemetry calibration and automatic continuity maintenance.**
7. **#98 Constrained PM-controlled PR merge** — may proceed in parallel where dependencies permit, but must be integrated before claiming the full routine zero-human-touch happy path.

Telegram terminal operations remain useful but are a convenience layer and are lower priority than the execution-efficiency work above.

## 18. Success measures

The initiative should trend toward:

- routine healthy tasks completing with zero avoidable Human Owner intervention;
- fewer full verification runs per successful repair cycle;
- lower model/context cost per accepted outcome;
- fewer provider/infra events misclassified as engineering repair;
- higher useful-finding rate per reviewer call;
- bounded collaboration that reduces failed repair cycles rather than inflating them;
- better estimate-versus-actual accuracy over time;
- no regression in deterministic verification, CI, trust boundaries, PM governance, or production controls.

A feature that adds model calls, services, coordination steps or infrastructure without improving one of these outcomes should be deferred or removed.
