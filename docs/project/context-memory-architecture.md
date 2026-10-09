# PCP Context and Memory Architecture

Status: implemented through #314 and #317. PCP uses a Git-backed tiered memory model with a repository-local deterministic Context Composer. Vector/hybrid RAG remains intentionally deferred unless future PCP-specific evaluation shows a material retrieval gap.

## 1. Objective

PCP needs durable project memory without turning every agent prompt into a replay of the entire project history.

The design separates information by authority, freshness and retrieval cost so an agent can answer three different questions correctly:

1. What must never be forgotten?
2. What is true now?
3. What historical or detailed evidence is relevant to this task?

Git remains the canonical human-auditable store for durable project knowledge. Runtime/PostgreSQL may later hold structured indexes/materialized state, but may not silently override repository governance.

## 2. Memory tiers

### T0 — Pinned governance / procedural memory

Always available to a role when relevant to its authority boundary.

Examples:

- repository-root `AGENTS.md`;
- `constitution.md`;
- authority hierarchy;
- trust/security boundaries;
- Human Owner decision boundaries;
- source-safety and merge/deploy invariants.

T0 must not depend on semantic retrieval. A critical rule is not optional merely because a retriever did not rank it highly.

### T1 — Active working state

A compact replace-in-place snapshot of what is operationally current.

Canonical human-readable artifact:

- `current-state.md`.

Typical contents:

- current platform/service identities;
- active projects and accepted local state;
- open issues/PRs that affect next work;
- active WorkOrders/jobs/leases when known;
- blockers;
- operational gates;
- immediate next safe actions.

T1 is not a chronological log. Completed work leaves T1 once its durable lesson/reference is recorded in T2/T3 or is otherwise recoverable from Git/issue/PR history.

Target: comfortably below ~15 KB and preferably below ~250 lines unless genuine active work requires more.

### T2 — Durable semantic / topical knowledge

Stable reusable knowledge that explains how PCP is designed or operated.

Examples:

- `architecture.md`;
- `operating-model.md`;
- `efficiency-model.md`;
- `provider-policy.md`;
- topical runbooks such as Telegram terminal operations or secret upgrades.

T2 is retrieved just in time by topic, role and task. It is not copied wholesale into every prompt.

### T3 — Episodic history

Compact records of completed incidents, rollouts, migrations and lessons.

Canonical Phase-1 index:

- `history/episodes.md`.

An episode records outcome, durable lesson and authoritative references, not raw logs.

Detailed chronology remains available through Git history, issues, PRs, Runtime durable records and CI.

### T4 — Raw evidence

High-volume or diagnostic evidence fetched only when required.

Examples:

- CI/job logs;
- full WorkReports/ReviewReports;
- raw agent transcripts;
- complete patches;
- Docker/resource inventories;
- detailed diagnostic command output.

T4 must not be default prompt context.

## 3. Authority and freshness

Retrieval relevance never overrides source authority.

When sources conflict, use the existing authority rules from `constitution.md` and `AGENTS.md`. In addition:

1. executable code/tests are authoritative for current executable behavior;
2. T0/T2 repository policy defines approved governance/architecture;
3. T1 defines the current mutable handoff snapshot but cannot override T0/T2;
4. live Runtime/GitHub state must be checked for time-sensitive execution facts;
5. T3 is historical evidence and must not override a current T1/live fact;
6. T4 is supporting evidence and must be interpreted in the state/time context in which it was produced.
7. for PCP-managed external projects, the pinned approved ProjectBaseline revision/source commit is the authority boundary for project-frame documents; a newer repository HEAD may provide live implementation evidence but does not automatically advance approved authority;
8. machine-readable baseline authority classes constrain interpretation: `mutable_execution` and `evidence_history` cannot override `human_owner_protected` or valid `delegated_design_owner` authority.

A historical item that is semantically similar to a query is still historical. A newer file revision is likewise not higher authority merely because it is newer.

## 4. Memory lifecycle

Material events should update memory by replacement/consolidation, not accumulation.

### Current-state transition

After a meaningful change:

- replace stale T1 values;
- remove completed initiative chronology from T1;
- keep only the current blocker/gate/next action;
- add or update a compact T3 episode when the completed event has reusable lessons.

### Durable decision

A decision that changes architecture, governance, security, scope or material policy belongs in the relevant T0/T2 document through normal reviewed change control.

### Incident-learning promotion

Live failures do not automatically become durable memory.

A deterministic incident-learning candidate may be created when durable evidence
shows recurrence, anomalous retry volume, operator recovery, a platform defect,
a reusable collaboration/PM handoff constraint, or a capability/verification
gap with avoidable resource cost. Ordinary first failures should remain
Runtime/Developer-local and should not invoke PM merely to create memory.

At a stable checkpoint or TaskOutcome, PM classifies the candidate using the
operating model and promotes only reusable conclusions:

- executable Runtime/code/config invariant -> implementation + regression test
  is authoritative; docs may reference it but should not restate mechanics in
  multiple places;
- current operational rule -> the narrow relevant T1/T2/runbook source;
- completed reusable rationale/incident -> compact T3 episode;
- project-specific prerequisite -> project verification config/runbook;
- raw chronology/logs/transcripts -> native GitHub/Runtime/CI source only.

One WorkOrder with many related failures should normally produce one consolidated
episode, not one T3 entry per attempt. A historical episode is never sufficient
when the recurrence can be mechanically prevented.

### Raw evidence

Raw evidence remains at its native source. Do not duplicate full logs into T1/T3.

## 5. Phase-1 episodic metadata

T3 entries should carry enough structure for deterministic filtering before any future semantic retrieval.

Recommended logical shape:

```yaml
id: rollout-309
project_id: personal-coding-platform
memory_type: episodic
event_type: rollout
date: 2026-09-26
status: historical
title: Project-level Current site rollout
summary: ...
lessons:
  - ...
entities:
  issues: [309]
  prs: [310, 311, 312]
  commits: [...]
tags: [direct-workspace, preview, lease]
valid_from: 2026-09-26
valid_until: null
supersedes: []
sources:
  - github_issue: 309
```

The Markdown index may express this more compactly while preserving the same concepts.

## 6. Context Composer contract

The deterministic repository-local Context Composer is implemented by:

- `scripts/context_memory.py` — reusable composition/retrieval logic;
- `scripts/pcp-context-compose.py` — operator/development CLI;
- `scripts/pcp-context-eval.py` — deterministic evaluation runner;
- `config/context-memory-eval.json` — PCP-specific evaluation corpus.

It does not require embeddings, a vector database, a network retrieval service or a Runtime container mount.

Input shape:

```yaml
project_id: chonhac
role: reviewer
task:
  title: Review direct-preview lifecycle change
  task_type: code_review
references:
  issue: 123
  work_order: optional
budget_chars: 8000
```

Output shape:

```yaml
context_pack_version: 1
pinned:
  - tier: T0
    source: AGENTS.md
    heading: ...
    reasons: [...]
  - tier: T1
    source: docs/project/current-state.md
    reasons: [pinned_current_state, current_precedence]
retrieved:
  - tier: T2
    source: docs/project/architecture.md
    heading: ...
    score: ...
  - tier: T3
    source: docs/project/history/episodes.md
    heading: ...
    score: ...
retrieval:
  policy: deterministic-v1
  supported_memory_found: true
  current_intent: false
provenance:
  generated_from_head: ...
  sources_are_repository_relative: true
```

The composer emits bounded content, source/heading provenance, explicit truncation and an unsupported-memory result when no T2/T3 candidate is justified. Host-local paths and secret assignment values are redacted at the output boundary.

## 7. Initial retrieval policy

Before adding vectors, prefer deterministic signals:

1. exact identifiers: project, issue, PR, job, WorkOrder, decision;
2. memory tier;
3. authority;
4. current/historical status;
5. project/task/role tags;
6. heading-aware lexical search;
7. recency only after authority/status filtering.

Future ranking may combine lexical/vector similarity, but stale/superseded penalties and current-state precedence must remain explicit.

## 8. Role-specific packs

### Product Manager

Default:

- T0 authority/governance;
- full compact T1;
- relevant T2 product/architecture/operating policy;
- relevant T3 lessons;
- live GitHub/Runtime evidence for current execution;
- bounded incident-learning candidates only when a stable checkpoint/task
  outcome or a material recurrence justifies classification.

### Developer

Default:

- task contract;
- relevant source/tests;
- minimal T0 safety boundaries;
- relevant T2 implementation constraints;
- narrow prior-attempt/T3 lessons when useful.

The developer does not need the full project history.

### Reviewer

Default:

- acceptance/task contract;
- diff/changed files;
- deterministic verification;
- WorkReport;
- relevant T0/T2 risk/governance;
- only the T3 incidents relevant to the reviewed risk.

### Debugger / specialist

Default:

- failure evidence;
- narrow relevant source/config;
- related prior T3 incidents;
- T4 logs only as needed.

### Định hướng nâng cấp Doc Governance & Context Quality — 2026-10-09

**Status:** Owner-approved mục tiêu [#587](https://github.com/sonvhse06072/personal-coding-platform/issues/587), **không** phải bằng chứng Runtime hiện đã dùng Context Composer. Hiện Composer trong scripts/context_memory.py và benchmark trong scripts/pcp-context-eval.py là công cụ deterministic độc lập; đường PM/Developer/Reviewer đã có WorkOrder/baseline/evidence packs riêng. Mọi tích hợp phải xác minh và đo thực tế trước khi claim giảm token.

**Doc-write lifecycle:** Khi PM local hoặc developer soạn/sửa doc, phân loại **project + tier + authority class + approved source commit + decision ID + supersession + canonical destination**. Check tự động nguồn/đường dẫn sai, T1 chứa history phình to, tài liệu trùng lặp, stale link, lower-authority text tự xưng approved, protected-path diff không có approval. AI chỉ phân tích mâu thuẫn ngữ nghĩa có rủi ro và phải trích dẫn claim/nguồn chứng minh, không tự sửa approved business/architecture. Thay đổi routine mutable/delegated được thực hiện qua PR/CI trong phạm vi cho phép; protected cần Owner-approved ChangeProposal và successor baseline nếu thay đổi authority. History/audit không bị xóa để giảm context.

**Read lifecycle:** Runtime phải dùng role/task-specific context pack đúng **pinned approved ProjectBaseline**, kiểm tra source/revision/heading, current-vs-historical status, omitting/truncation markers và budget. Tier-0/protected constraints/WorkOrder acceptance criteria **không bị clip để đủ ngân sách**; thiếu evidence quan trọng thì bounded retrieval tiếp hoặc dừng với lý do cannot-prove, không bịa. T2/T3 chỉ đọc khi cần, T4 là diagnostic. Không cho PCP và dự án được quản lý vô tình dùng chéo authority; không mặc định đọc toàn bộ docs hoặc tất cả skills.

**Feedback và tự điều chỉnh (bounded):** Ở doc PR, TaskOutcome hoặc sau các lỗi context lặp có bằng chứng, tạo ContextHealthReport: nguồn/mục yêu cầu bị bỏ sót, stale/duplicate source, context tokens/size, prompt caching, reader role, test/repair waste, outcome. Trước khi sửa retrieval, phân loại đúng nguyên nhân thành missing docs, stale docs, retrieval miss/truncation, reasoning failure dù đã đủ context, hay task specification ambiguity. Ưu tiên thay metadata/heading/dedup/role pack/chunk/budget hơn thêm embedding service. Chỉ tự apply các thay đổi không đụng protected authority sau offline benchmark + regression/CI; protected policy vẫn cần Owner approval.

**Benchmark có kiểm chứng:** Tập case tiếng Việt/Anh với decision refs, current/stale, multiple file, source conflict, approved architectural constraints và context window dài; đo **selected content recall** (không chỉ đúng heading), wrong authority/historical false positive, latency, actual token usage, downstream rework/quality và chi phí chạy bộ đánh giá. Mục tiêu 100% required-evidence recall **trên fixture có nhãn** và 0 authority violations; không tuyên bố đảm bảo 100% trên mọi task ngoài đời. Vector/hybrid RAG chỉ có cửa khi có retrieval miss thực tế, benchmark uplift đủ lớn và tổng chi phí thấp hơn đường deterministic.

**Interface với Capability Manager:** Metadata rules/tools/skills được chọn từ project/task/role; skill text là hướng dẫn không có quyền nâng authority. Tự phát hiện skill phù hợp phải kiểm nguồn, version, license, scripts trước khi thêm project qua PR; chỉ load skill được chọn thay vì toàn bộ. Tác động lợi ích được đánh giá theo accepted outcome, không theo số lượng skill được cài. Autonomous new-project discovery/business interviewing [#588](https://github.com/sonvhse06072/personal-coding-platform/issues/588) **Future/Deferred** và không nằm trong vòng đời hiện tại.

## 9. RAG decision gate

PCP must not add a vector database merely because RAG is common in agent systems.

#317 established the deterministic baseline and evaluation gate. Exact-head CI #637 accepted:

- required evidence target recall = 1.0 on the current fixture;
- stale Tier-3 false-positive rate for current-state cases = 0.0;
- authority-conflict failure rate = 0.0;
- unsupported-memory abstention accuracy = 1.0;
- mean composed context remains below 50% of the read-all-docs character baseline;
- role-specific T0/T1 selection, exact historical references, budget limits, provenance and output redaction are regression-tested.

Therefore PCP does **not** currently have evidence that justifies vector/embedding infrastructure.

Re-open vector/hybrid evaluation only when at least one measurable trigger appears:

- the deterministic evaluation loses required evidence recall;
- semantically relevant material is repeatedly missed despite correct metadata/heading structure;
- stale/historical ranking errors recur;
- corpus growth makes deterministic retrieval materially too large or slow;
- a new benchmark demonstrates that vector/hybrid retrieval improves PCP-specific correctness/relevance enough to justify its operational cost.

Any future experiment should compare the deterministic baseline against vector and hybrid retrieval while retaining explicit authority, freshness, supersession and provenance controls.

## 10. Safety and non-goals

The implemented architecture does not:

- change Runtime execution semantics;
- add a vector DB;
- add an embedding provider;
- create an autonomous consolidation daemon;
- let retrieved memory override governance;
- delete Git/issue/PR/Runtime audit history;
- weaken source, secret, merge, deployment or Human Owner boundaries.

The simplest architecture that preserves correctness and reduces context pressure should be preferred.
