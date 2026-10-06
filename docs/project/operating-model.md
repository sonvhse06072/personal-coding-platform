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
- material project/personal budget expansion or justified emergency-ceiling override;
- high-authority governance amendments;
- ambiguities that cannot be resolved from approved source of truth.

Routine execution continuation inside an already-approved task working envelope is not a Human Owner decision. Static task/profile counter exhaustion by itself is also not a Human Owner decision when the WorkOrder is still making meaningful progress and no independent anomaly, protected boundary, provider-exhaustion or material-resource-risk condition exists. Routine PR review and merge inside the approved project frame is delegated to PM after required verification/review/CI gates pass. A merge must stop for Human Owner input whenever the PR introduces or depends on one of the decision boundaries above.

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
- Runtime/provider/budget evidence;
- collaboration/consultation conclusions;
- historical efficiency telemetry when meaningful.

### Responsibilities

PM must:

1. check the request against project scope and constraints;
2. identify relevant requirements, architecture constraints, dependencies, and risk;
3. decompose approved work into bounded WorkOrders;
4. record a practical effort/resource shape, verification shape, and expected collaboration/review level for each non-trivial WorkOrder;
5. maintain dependency ordering and the mutable Execution Plan;
6. request staffing from Router rather than hard-code a preferred model;
7. interpret meaningful reports/evidence and choose the next action;
8. keep work aligned with the approved Project Plan;
9. create a ChangeProposal instead of silently changing project intent;
10. produce a TaskOutcome after meaningful completion/failure;
11. select the next approved in-scope task when appropriate;
12. perform the final engineering review of PR evidence before merge;
13. merge eligible PRs when all required gates pass and no Human Owner decision trigger remains unresolved.

### PM autonomy

PM may autonomously:

- split/reorder in-scope work;
- reassign a failed WorkOrder;
- request bounded repair, specialist consultation, or additional review;
- change execution tactics;
- update Execution Plan state;
- record discovered follow-up work;
- defer an in-scope task because of dependency or resource evidence;
- use approved adaptive task-budget/headroom policy inside the existing personal/project resource envelope;
- review and merge an in-scope PR after deterministic checks, required independent review, and CI are green;
- continue to the next dependency-satisfied in-scope task after the merge gate clears.

PM may not autonomously:

- expand product scope;
- rewrite non-goals;
- alter approved architecture constraints;
- add a major framework/service/dependency;
- weaken security boundaries;
- approve destructive/production operations outside existing policy;
- materially expand the project/personal resource envelope or override a justified emergency ceiling;
- merge a PR whose content or unresolved finding requires a Human Owner decision.

### PM advisory triage

A Human Owner request is a high-authority input to PM reasoning, not an
automatic declaration that the requested implementation tactic is already the
best or approved engineering decision.

Before material execution, PM should:

1. identify the objective behind the request;
2. inspect the current source of truth and live state when they may materially
   change the answer;
3. assess scope, dependency ordering, architecture/security boundaries,
   verification implications, reversibility and resource impact;
4. distinguish the underlying problem from a proposed symptom-level fix;
5. recommend the most effective bounded path, including refining or disagreeing
   with the proposed tactic when evidence supports a better option;
6. state material uncertainty and what must be verified before relying on it;
7. execute routine, reversible, in-scope actions without creating needless
   Human Owner approval loops;
8. surface a Human Owner decision only when the remaining choice crosses an
   existing protected/material boundary.

PM should not be passively order-taking. PM should give a recommendation and
rationale when alternatives materially differ. The Human Owner retains final
authority for protected project/governance decisions and may choose a different
path after reviewing the recommendation.

### Incident-learning review

Do not invoke PM merely because the first ordinary lint/test/provider failure
occurred. Incident learning is intended to reduce repeated failures and quota
waste, not to create an additional conversation after every error.

A bounded incident-learning candidate is justified when durable evidence shows
one or more of the following:

- the same blocker or root cause recurs in one WorkOrder;
- deterministic verification retry volume becomes anomalous;
- manual operator recovery/rollout is required;
- a live project exposes a PCP platform defect;
- collaboration/PM handoff exposes a reusable execution constraint;
- a capability or verification gap causes avoidable model/tool/test spend;
- the same root cause appears across multiple tasks/projects.

Candidate detection should be deterministic from Runtime/GitHub evidence where
possible and should not itself require a model call.

At a stable checkpoint or TaskOutcome, PM classifies a candidate as:

- `ephemeral_task_failure`;
- `project_runbook_lesson`;
- `platform_operational_lesson`;
- `verification_contract_change`;
- `platform_defect`;
- `governance_change_proposal`.

PM records the root cause, avoidable impact, existing rule coverage, preferred
prevention mechanism and the smallest authoritative destination for the lesson.
Executable prevention (code/config/preflight/circuit-breaker/regression test)
is preferred over prose when the recurrence can be mechanically prevented.
Promotion into repository memory follows
`context-memory-architecture.md`; raw chronology stays in GitHub/Runtime
evidence.

### Human-operated ChatGPT PM model convention

This subsection applies only when the Human Owner is manually using ChatGPT as
the Product Manager/operator outside Runtime/Router staffing. It does **not**
change Router authority, PCP model registry, provider policy, WorkOrder role
identity, or the architectural rule that a logical role is not a model name.
The role remains Product Manager; the settings below are operator-side ChatGPT
configuration choices.

Use the following operating defaults:

- routine PM checks such as CI/status inspection, short log triage and narrow
  operational verification may use GPT-5.6 Sol with **High** reasoning;
- substantive PM work defaults to GPT-5.6 Sol with **Extra High** reasoning,
  including planning, root-cause analysis, bounded patch review, governance
  checks and rollout decisions;
- GPT-6 Pro is reserved for unusually difficult or high-blast-radius PM
  reasoning where additional model capability is materially useful.

Typical triggers for a GPT-6 Pro recommendation include:

- architecture or state-machine changes spanning multiple services/lifecycle
  transitions;
- concurrency, race-condition or finalizer/lease correctness;
- durable-state migration, checkpoint/recovery/resume semantics;
- security, trust-boundary or authority-boundary changes;
- high-blast-radius governance/resource-policy changes;
- final PM review of an unusually complex hotfix or patch where several
  independent invariants interact.

Before beginning substantive work for which GPT-6 Pro is recommended, PM should
tell the Human Owner explicitly so the Human Owner can select the model in the
ChatGPT UI. Use a concise form such as:

```text
Model recommendation: GPT-6 Pro — <bounded reason>.
```

Do not recommend GPT-6 Pro for routine work merely because it is available.
Model scarcity/usage, latency and Human Owner attention remain legitimate
resource considerations.

The labels **High**, **Extra High**, and the named ChatGPT models in this
subsection are external operator-product settings, not PCP Router reasoning
effort values or architecture invariants. They may change as the ChatGPT
product changes. Revalidate material capability/availability claims when they
matter, and update this convention rather than hard-coding a commercial plan or
ChatGPT UI setting into Runtime/Router policy.

A longer ChatGPT conversation is not a substitute for repository continuity.
PM must continue to treat the checked-in project docs plus current executable
evidence as authoritative over chat history. When a PM chat is restarted or its
active context is insufficient, recover through the repository reading order
and live state checks defined in `AGENTS.md` and `docs/project/README.md`.

## 4. Router / Staffing Policy

Router answers **who/how expensive/how strong**, not **what/why**.

Inputs include:

- WorkOrder role and task class;
- PM effort/resource-shape estimate;
- repository/task complexity signals;
- verification difficulty/shape;
- risk/profile;
- privacy constraints;
- provider/model availability and health;
- authoritative quota/resource state;
- personal/project resource envelope;
- eventually historical performance telemetry.

Outputs include:

- selected logical execution profile;
- model/provider/adapter for the requested role;
- task-specific budget estimate;
- approved elastic working envelope and justified emergency circuit-break ceilings where supported;
- optional planner/evaluator/consultant staffing;
- deterministic human-decision triggers tied to protected/material/anomalous conditions.

Explicit reasoning effort is constrained by both the selected model's registry
capability list and the route's policy ceiling. A global effort order is only an
ordering aid and cannot make an unsupported value eligible. The current
automatic profiles continue to request and cap effort at `low`, `medium`, or
`high`; higher registered Codex capabilities do not make Astra routine/default
staffing or expand Product Manager eligibility.

Profile budgets are priors and safety defaults, not necessarily the final task estimate and not sufficient Human Owner stop reasons by themselves. Provider quota is resource state and must not be conflated with task estimate/profile-counter exhaustion.

Router must not modify product scope or project state.

## 5. Runtime Orchestrator

Runtime answers **execute safely and durably**.

Responsibilities:

- persist job/work state;
- pin source commit;
- request isolated workspace creation;
- invoke selected agent roles with bounded role-specific context/evidence;
- track model/tool/token/time/resource usage and Human Attention events;
- preserve consumed counters across retry/recovery/headroom changes;
- permit bounded automatic healthy-progress headroom inside approved policy;
- treat static task/profile counter exhaustion as telemetry/reassessment input rather than an automatic Human Owner gate;
- enforce anti-loop/circuit-break signals and emergency ceilings only when an independent anomaly/material-risk condition justifies stopping;
- run layered deterministic verification while preserving mandatory final acceptance verification;
- distinguish engineering repair from provider recovery, infrastructure retry, verification retry and delivery retry;
- perform bounded retries/failover/escalation;
- coordinate bounded consultant/reviewer dialogue where configured;
- pause for Human Owner decisions only when required by protected decisions, genuine material resource risk, authoritative provider exhaustion without eligible fallback, or abnormal execution;
- checkpoint/recover interrupted work;
- coordinate bounded GitHub delivery and CI repair;
- support the PM-controlled merge gate without giving developer agents merge authority.

Runtime should handle routine test/lint/repair mechanics, healthy continuation, mechanical static-counter headroom, and non-material resource growth without invoking PM or Human Owner for every iteration. Semantic working-envelope crossings that can indicate a change in implementation shape—such as changed-file scope growth—are PM reassessment checkpoints, not automatic Human Owner gates. A routine owner `continue`/budget-extension action whose only reason is an underestimated but healthy task remains a platform defect, not the target operating model.

### Runtime coding-CLI toolchain pinning

Subscription-backed coding CLIs that execute inside PCP Runtime are part of the
reproducible execution environment, not an ambient host dependency. Their normal
build contract must use checked-in concrete versions rather than floating
`latest` tags. A host CLI upgrade does not upgrade the Runtime image.

For Codex specifically:

- `config/tool-versions.env` is the authoritative normal-build pin;
- `scripts/pcp-build-images.sh` passes that exact version into the Runtime image;
- `platform-status` exposes the running Codex version against the pin;
- `platform-test` fails closed when the running Runtime Codex binary does not
  match the checked-in pin.

An explicit `CODEX_VERSION` override may be used for bounded local diagnosis,
but it is not accepted release evidence until the checked-in pin is updated,
tests pass, and the resulting Runtime image reports the same version. This
prevents Docker/BuildKit caching of a literal `@latest` install step from
silently leaving Runtime on an older Codex binary.

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
effort:
  implementation: medium
  verification: high
  uncertainty: medium
expected:
  repair_turns: 2
  consultations: 0
  review_rounds: 1
budget_profile: standard
```

Developer responsibilities:

- read relevant source and tests before modifying code;
- stay inside the Task Contract;
- use existing project patterns where practical;
- implement the smallest sufficient change;
- add/adjust relevant tests;
- use targeted checks during iteration where appropriate;
- request a purpose-specific consultation when uncertainty/risk justifies the cost rather than blindly repeating a failed approach;
- report assumptions, risks, deviations, and unresolved items;
- never broaden scope because a different solution seems more interesting.

The Primary Developer is the default sole workspace writer. Consultants/testers/debuggers/specialists/reviewers are read-only unless a separately approved capability says otherwise.

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
consultations: [...]
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

Verification should be layered:

1. cheap/targeted checks during implementation or narrow repair;
2. focused affected tests/static checks as the patch stabilizes;
3. full checked-in deterministic verification at required acceptance/delivery checkpoints.

Layering is an efficiency mechanism, not a way to weaken final acceptance. Model review does not replace deterministic tests/static analysis.

For user-facing frontend WorkOrders, an approved project may expose a final
`visual_quality` phase after `frontend_quality`. The WorkOrder must declare
bounded local `visual_routes`; Runtime owns preview lifecycle and writes the
ephemeral evidence request outside the tracked worktree. The project collector
may capture bounded screenshots plus deterministic browser evidence such as HTTP
status, console/page errors, failed request paths, DOM landmarks and horizontal
overflow.

Screenshot capture alone is not pixel-level review. Evidence records whether an
image was actually consumed by a multimodal reviewer. When
`image_reviewed=false`, evaluators may use deterministic browser/DOM/network
evidence but must not claim color, spacing, typography, aesthetic or composition
findings from the screenshot. Preview/evidence failure is a normal enforcing
verification failure and returns to the same developer repair loop.

When a selected model-agent invocation cannot provide a verification surface
that a project-owned Runtime/DDEV phase requires, Runtime may tell that agent not
to retry the impossible in-agent check and to continue supported deterministic
work. The context is derived from explicit adapter and phase capabilities, not
framework or command-name heuristics. Skipping that attempt is never pass
evidence: required Runtime/DDEV results remain the final gate, evaluator findings
remain evidence-driven, and listener-capable adapters remain unrestricted.
Developer guidance may name project-owned phases conditionally before a diff
exists. Evaluator guidance may name only phases that the completed Runtime
verification result identifies as required for final acceptance; configured but
inapplicable phases do not become review requirements.

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

- routine with strong deterministic checks: no or very lightweight model review where policy permits;
- standard: lightweight independent Task Contract + diff review;
- complex: strong independent reviewer;
- critical/security/architecture: different-model/provider review required if eligible capacity exists.

Reviewer/developer dialogue may use a small bounded number of finding -> response/repair -> re-check rounds. Persistent disagreement is summarized to PM rather than debated recursively.

Do not recursively review reviewers by default.

## 10. PM TaskOutcome

At a meaningful checkpoint, PM consumes WorkReport + deterministic checks + required ReviewReport + CI evidence and writes a compact outcome.

Target shape:

```yaml
task: T-123
outcome: accepted | repair | reassign | replan | blocked | human_decision
project_effect: [...]
new_information: [...]
discovered_work:
  - description: ...
    relation: within_scope | outside_scope
incident_learning:
  candidates: [...]
  promoted: [...]
plan_changes: [...]
next_task: T-124
```

If a next task is already inside the approved Project Plan, PM may schedule it automatically subject to budget/dependency rules. When the accepted task is represented by a PR, PM may merge it after the required merge gates pass and then advance the dependency graph.

Outside-scope discovered work is recorded but not silently added to the roadmap.

`incident_learning` is optional for ordinary tasks. When present, it contains
only bounded candidate/classification references and compact promoted lessons;
it does not embed raw logs or trigger recursive retrospective agents. A reusable
lesson should be promoted once at a meaningful checkpoint rather than repeated
after every failed attempt.

Runtime implements the candidate side deterministically. Ordinary first
lint/test/provider failures produce no candidate. Repeated failure fingerprints,
verification-retry anomalies, material repair/routing churn, source-advance
recovery, or explicit platform/state-machine blockers may create one stable
candidate per job/WorkOrder incident window. The candidate carries only compact
signal/counter/evidence references and no raw logs. PM classification remains a
checkpoint responsibility; candidate generation itself performs no model call.

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

The team resource envelope includes more than USD: model calls, subscription quota/scarcity, token usage, wall time, verification/repair cost, provider reliability, and Human Owner attention are all legitimate budget signals.

Mandatory budget rule: healthy-progress work continues autonomously inside the approved envelope. Static task/profile counter exhaustion alone must not create a Human Owner checkpoint; hard blocking requires independent anomaly/protected/provider/material-risk evidence.

The detailed adaptive-budget, collaboration, review-efficiency, evidence-pack and telemetry policy is `efficiency-model.md`.

## 15. Practical checkpoint rule

PM is invoked at meaningful checkpoints, not every mechanical event.

### Canonical new-ticket intake (#367)

Authenticated `POST /v1/intake` is the canonical Human/Chat PM handoff for new
tickets. It requires a registered project and approved ProjectBaseline; an
omitted revision resolves and pins the active approved revision. Missing or
unapproved baselines fail before creating a job or plan. Explicit/manual bounded
`POST /v1/jobs`, `scripts/create-job.sh`, and `/v1/jobs/{id}/run` remain available
with their existing contracts. Existing jobs/plans are not reclassified.

The typed request carries `project_id`, `ticket` (existing PMTicket id/title/
description), optional `baseline_revision`, `bounded_direct` (default false),
caller-owned `execution_mode` (`autonomous` by default or `supervised`),
existing `SemanticSignals` as `semantic`, existing `RepoHints` as `repo_hints`,
`planning_profile` (standard/complex), typed PM `provider_state`, and `auto_run`
(default true). No command, workspace path/mode, credential, merge/production
authority or model-selection field is accepted. Unrecognized top-level or signal
fields are rejected. Provider state is capacity evidence for existing execution
paths and never intake-policy authority. Canonical intake has no `dry_run`:
planning retains the existing read-only PM call and normal orchestration path.
If supervised mode is requested but policy classifies the intake as direct,
intake fails validation; it does not force planning or ignore the mode.

Policy version `1` defaults to planning unless `bounded_direct=true`, all seven
semantic values were explicitly supplied, and all required hints are known.
Required hints are positive `estimated_files` and `affected_components`,
`dependency_depth`, `tests_available`, `existing_pattern`, `historical_churn`,
and explicit values for all seven boundary booleans below. Defaults, omissions,
null hints and zero file/component estimates cannot prove small scope.

Hard planning triggers are any true `schema_change`, `security_sensitive`,
`authentication_change`, `authorization_change`, `external_api`,
`production_write`, or `destructive_migration`; `dependency_depth > 0`; or
`affected_components >= 3` (multi-unit shape).

Otherwise two or more independent material signals require planning:

| Material signal | Inclusive threshold |
| --- | --- |
| ambiguity, architecture_impact, verification_difficulty, risk, novelty | 50 each |
| context_requirement, reasoning_requirement | 70 each |
| affected_components | 2 |
| historical_churn | 50 |
| estimated_files | 10 |
| verification_shape | tests_available=false OR existing_pattern=false; counts once |

File count alone never makes a ticket materially large or forces decomposition.
The pure classifier reads structured signals only, makes no external call, and
returns policy version, mode, reason codes and material-signal names. Insufficient
evidence or absent direct intent routes to planning without itself claiming the
ticket is large. Hard triggers or two material signals set
`decomposition_required=true` on the existing PMPlanner request. An in-scope
proposal with no decision boundaries must then have at least two coherent,
independently verifiable WorkOrders before becoming ready. Invalid single-unit
output fails planning and cannot launch. Out-of-scope/ambiguous/human-decision
results need no artificial WorkOrders. Ordinary `/v1/plans` defaults this flag
to false and still accepts a valid single-WorkOrder plan.

Direct intake creates one normal job with ticket title/description, semantic
signals, repo hints, provider state and the pinned baseline. The compact internal
`canonical_intake` decision is committed with the initial job row before enqueue;
it contains no ticket prose, prompts or raw request body. `auto_run=false` creates
the direct job without enqueue. Planning calls the same PMPlanner and
PlanOrchestrator registration/tick path as `/v1/plans`; `auto_run` controls only
direct-job enqueue, not plan scheduling. Planning may launch dependency-ready
WorkOrders under the existing concurrency-one gates, but creates no standalone
direct job. Responses contain bounded decision evidence and either `job` or
`plan` identity/status, plus baseline revision, without staffing internals.

### Meaningful PM checkpoints

For an eligible ExecutionPlan with a structured parent GitHub issue identity,
#368 maintains one compact managed progress comment for the Human-operated PM.
Initial decomposition, started, accepted/awaiting-merge, merged/completed,
blocked, waiting-human, repair-reopened and final completion update the same
handoff. Durable state determines transitions; polling alone produces no update.
Later plans for the same project/issue reuse the comment. Pre-install plans are
not automatically enrolled. Publication retries independently of engineering;
GitHub outages cannot roll back a checkpoint or change dependency readiness.
For a blocked plan, the read model and comment include prior completed durable
checkpoints, exact current WorkOrder/job/branch, bounded whitelisted verification
and reviewer/PM outcome, untouched pending WorkOrders, the last known-good
checkpoint and an advisory closed-vocabulary next action. Reading this evidence
cannot authorize or perform recovery.

For a supervised ExecutionPlan, the first WorkOrder launches through the normal
path. After each later dependency-unlocking `completed` or `merged` checkpoint,
the plan holds before any ready successor job or operator gate is created. Chat
PM reviews the durable checkpoint and uses the authenticated continuation API
with the exact generation, continuation key, checkpoint ID/key and sorted ready
set. The release is durable and idempotent; an exact retry of an already released
generation returns without invoking a scheduling tick. Normal scheduling keeps
retrying a released generation if a lease or other infrastructure condition delays launch.
The same managed parent comment and Dashboard show the held/released identity.
This checkpoint does not authorize a Human Owner decision, merge, production
write, destructive change or existing operator action. Those gates keep their
existing authority and must be resolved separately.

PM should normally run when:

- a new ticket arrives;
- an initial plan/decomposition is needed;
- a developer completes meaningful work;
- a semantic working envelope is exceeded in a way that may reflect implementation/scope shape rather than mere resource consumption;
- review fails after bounded routine repair/dialogue;
- a decision boundary or scope conflict is discovered;
- a task completes and the next action must be selected;
- a PR has passed its required gates and is ready for PM merge review.

A first lint failure, test typo, ordinary bounded retry, healthy mechanical budget headroom, or non-material provider recovery remains Runtime/Developer responsibility. A semantic working-target crossing such as changed-file scope growth should invoke PM with a bounded evidence pack. PM may approve the exact diff, request a developer explanation/repair, or surface a Human Owner decision only when PM authority is insufficient.

A removable implementation choice that violates the approved WorkOrder or an explicit out-of-scope rule is ordinarily resolved by PM through bounded developer dialogue or repair/revert. The existence of a protected-path or dependency signal does not by itself require Human Owner attention. PM should escalate only when evidence shows the protected/material change is genuinely necessary and the objective cannot be met by an in-scope repair. If Human Owner rejects a PM-raised boundary, the same job should return to bounded repair inside the current baseline rather than treating rejection as a terminal project stop.
Protected execution signals discovered from the current diff must be semantically reviewed by PM before generic Router reassessment may surface a Human decision. If deterministic verification is still failing, ordinary bounded repair gets the first turn and protected flags remain durable for the next successful verification. Router must not use a protected path/dependency flag to bypass the PM repair-first gate.

## 16. Human Owner diagnostic-block convention

Normal ChatGPT/operator collaboration continues to use ordinary terminal-safe read-only blocks. The existence of the planned Telegram terminal operations gateway does not change the default response format.

Only when the Human Owner explicitly asks for a read-only block that is ready to send through Telegram should ChatGPT emit the Telegram-specific metadata/format described in `telegram-terminal-operations.md`.

This convention exists so local terminal work remains simple while Telegram execution remains an opt-in transport with a distinct security boundary.

The detailed approved target design for `/run-ro`, the read-only broker, optional `/run-op`, sandbox/database/secret boundaries, Telegram-ready metadata, WSL lifecycle and implementation phases is authoritative in `telegram-terminal-operations.md`.

## 17. Bounded collaboration protocol

A developer may request a specialist/tester/debugger/reviewer consultation through Router using a logical role and a concrete objective. The request must include a bounded evidence package and must not name a provider/model as the role identity.

Default consultation properties:

- concrete question required;
- relevant evidence/source references required;
- consultant read-only;
- small round limit;
- duplicate-question guard;
- recursive consultation disabled by default;
- compact conclusion/recommendation persisted as a CollaborationThread artifact target rather than an unbounded transcript.

The detailed policy and implementation order are authoritative in `efficiency-model.md` and parent initiative #146.

## PM-controlled merge authority

For projects with `autonomy.allow_pm_merge=true`, PM may merge an exact
delivered PR after deterministic verification, required independent review and
exact-head CI all pass, provided no unresolved protected decision remains.

Risk level alone is not a Human Owner merge decision. `high` and `critical`
risk continue to raise execution/profile/verification rigor, but owner merge is
required only when durable protected-decision evidence or another explicit
merge blocker remains.

Production deployment is separate authority and is never implied by PM merge.

