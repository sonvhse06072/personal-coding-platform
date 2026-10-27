# Roadmap

Status: approved implementation order for the next phase of the Personal Coding Platform.

This roadmap is a planning artifact beneath the Project Constitution. PM may reorder or split in-scope implementation work when evidence requires it, but may not change project intent or architecture invariants without human approval.

## Guiding principle

Build the smallest layer that enables the next layer safely. Do not add swarm infrastructure, dashboards, or model orchestration complexity before the underlying team contracts and source-of-truth rules are durable.

## PCP Local execution priority — GH-815, 2026-10-27

Owner SOURCE decisions [V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6438475541),
[V2](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6438904126)
and [V3](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6440446016)
prioritize one useful local Codex WorkOrder on Ubuntu WSL2 + Docker Desktop +
DDEV using existing Runtime/Router/Executor/PostgreSQL. This is the immediate
sequence within the approved efficiency direction:

1. PR-A: local risk/delegation policy, isolated PCP-only bootstrap, default-OFF
   service configuration, draft registration and inactive baseline; 13 exact
   approved paths, fake/static checks and actual hosted four-suite CI.
2. PR-B after accepted PR-A: authentic readers and dedicated admitted
   execution/delivery using the existing durable receipt/job mechanisms. Preserve
   source/lease/credential/budget/CI boundaries; no generic legacy-worker bypass.
3. After both source reviews and postmerge CI, obtain one bounded physical pilot
   delegation, prepare fresh local images/instance, verify actual health and
   credential isolation, then run one fresh approved PCP-only issue through
   Codex, tests, Draft PR, exact-head CI and independent PM outcome.
4. Measure accepted work, quota/time and Owner interventions; prove the next
   in-scope WorkOrder proceeds without per-task WSL intervention before expansion.

External OCI signing/producer/GHCR research is no longer a prerequisite for
this local development path. Do not dispatch the old image workflow as part of
PR-A. Legacy compatibility is no longer required; retain historical artifacts
only where useful, and do not force current configuration to reproduce obsolete
fixtures. Physical deletion is separate. #795 installation remains unperformed;
#752 is PARKED, #595 is HOLD, and Chợ Nhạc is no-touch. SOURCE policy and tests
are not live deployment or benchmark evidence. Constitution and architecture
invariants, immutable baselines, CI/review and protected decisions still govern.

## Current product/engineering priority overlay — 2026-10-09 (Owner-approved direction)

**Áp dụng thay thế các đoạn ưu tiên cũ trong tài liệu này**, không thay đổi lịch sử phase, các ProjectBaseline đã phê duyệt hoặc trạng thái job đang chạy. Product North Star là [business-strategy.md](business-strategy.md); kiến trúc đích là [architecture.md](architecture.md). Đây là **phê duyệt định hướng và thứ tự đầu tư**, không phải lệnh dispatch WorkOrder hoặc thay đổi quyền Runtime.

**Phương án được chọn:** Incremental refactor PCP hiện hữu; giữ Router, Model Registry, ProjectBaseline, Runtime state/checkpoints, DDEV Executor, CI/GitHub delivery, Context Composer, Guardian và các trust boundary; ưu tiên sửa vòng đời work thật và lớp kiểm soát gây overhead trước khi xây capability bổ sung. Không big-bang rewrite và không tạo nền tảng song song.

| Giai đoạn | Effort dự kiến (ngày công) | Kết quả/boundary nghiệm thu |
| --- | ---: | --- |
| **G0 — Audit & direct-Codex benchmark** | 5–10 | Đo end-to-end parity trên các task so sánh được; phân loại overhead do permission, DDEV/preview, PM/verification, recovery, context, model; xác định module cần sửa; không xâm phạm Chợ Nhạc live lease |
| **G1 — Fast Development Path** | 24–44 | Chế độ project-scoped trusted dev cho Codex/Antigravity; developer có vòng code → build/DDEV → truy cập preview URL/Playwright → repair trong cùng job; fast path cho ticket đơn giản; linh hoạt sửa kỹ thuật thuộc acceptance criteria; final CI và protected gates còn nguyên |
| **G2 — Reliable Autonomy** | 33–65 | Tự chạy chuỗi WorkOrder đã duyệt; self-healing cho lớp lỗi được kiểm chứng, same-job preservation; Doc Governance + role-specific Runtime context packs; resource/attention telemetry và Router calibration dựa trên accepted outcome |
| **G3 — Adaptive Capability** | 23–44 | Theo dõi provider/CLI/model/effort, verify/canary/update qua PR và rollout an toàn; rule/tool/skill selection, nguồn provenance, feedback về độ hiệu quả; tích hợp/benchmark hồi quy cho các luồng trên |

Tổng effort nền tạm tính **85–163 ngày công**; với dự phòng rủi ro và tích hợp, khung đầu tư đề xuất **100–200 ngày công**, kỳ vọng sơ bộ **110–170 ngày** nếu không phải thay đổi kiến trúc lớn. Đây là **ước lượng, không phải kết quả profiling, hạn chót hay quyền chi ngân sách tự động**. Effort giữa các giai đoạn đã chứa kiểm thử/tích hợp tương ứng; không cộng lại một hạng mục integration lần hai. Một ngày công là khoảng 6–7 giờ kỹ thuật hiệu quả; phí provider/CI/compute và thời gian chờ các quyết định protected được theo dõi riêng.

**Stop/go sau khoảng 30–50 ngày công đầu:** nếu trusted developer feedback loop chưa cạnh tranh được với Codex trực tiếp và owner intervention chưa giảm trên các task tương đương, phải tái đánh giá phạm vi và critical path trước khi commit G2–G3. Phân bổ effort theo từng đợt; không phê duyệt toàn bộ khung 100–200 ngày chỉ bằng roadmap này.

**Quality/value gates** (định nghĩa đo, cohort và baseline ở [efficiency-model.md](efficiency-model.md)):
- Với cùng acceptance criteria/test/review: đề xuất PCP median task-cycle ≤1,25× và p90 ≤1,5× so với Codex trực tiếp; không giảm chất lượng, không so không cùng mức nghiệm thu.
- Một chuỗi 3–5 WorkOrder routine đi từ scope được duyệt đến PR/merge và WorkOrder tiếp theo không cần paste/re-dispatch hoặc owner continuation vì counter ước lượng.
- Runtime không tự bypass protected decision; không mất job/diff/lease/counters; self-healing chỉ chạy lớp lỗi có đường kiểm chứng và không retry lặp mù.
- Giảm context/AI quota trên **accepted outcome**, bảo toàn required decision/constraint recall trong benchmark có nhãn.
- Những cải tiến về routing, tool/skill và provider đều phải được kiểm nghiệm và không được làm chậm bất hợp lý đường thực thi chính.

**Điều kiện triển khai:** G0 trước; G1 cần phê duyệt riêng cho chi tiết thay đổi protected developer trust boundary/permissions; G2–G3 chỉ khi G1 đã qua benchmark. Mỗi giai đoạn đi qua issue/WorkOrder, PR, exact-head CI, review và rollout an toàn. **Chợ Nhạc TECH-DEC-040 Codex-first + PCP-light vẫn là phương thức phát triển mới đang được áp dụng**; không khởi chạy PCP đồng thời trong cùng workspace/DB cho tới khi hoàn thành handoff/lease hợp lệ.

**Không triển khai trong roadmap hiện tại:** [#588 — Autonomous Project Discovery/Business Onboarding](https://github.com/sonvhse06072/personal-coding-platform/issues/588), mô hình SaaS, agent swarm/parallelism mặc định, full-access developer trên máy host, generic remote shell, tự deploy production. Năng lực khám phá dự án mới chỉ được cân nhắc sau khi G0–G3 đạt kết quả và Owner kích hoạt riêng.

**Các issue nguồn:** #590 (trusted dev/parity), #586 (orchestrated same-job recovery), #493 (DDEV infra), #512 (remote control), #587 (doc/context), #589 (provider), #146 (efficiency), #591 (Owner-approved docs reconciliation); #588 là **deferred**. Issues đã hoàn tất (#313/#317/#426/#478/#491/#563/#571) là tài sản nền, không tự mở lại.

Các phase chi tiết bên dưới ghi lại kiến trúc, chương trình và mốc lịch sử đã được duyệt trước đây. Nếu chúng mô tả một thứ tự thực hiện khác, **overlay hiện tại là kế hoạch tác nghiệp**, trong khi Constitution/architecture/ProjectBaseline và protected decisions vẫn giữ thứ bậc authority cao hơn.

## Current priority overlay — personal-budget execution efficiency

_Ghi chú: phần dưới là lịch sử chương trình #146; thứ tự đầu tư thực tế từ 2026-10-09 theo overlay mới phía trên. Không diễn giải số phiên bản/rollout lịch sử thành live hiện tại._

Human Owner approved initiative #146 on 2026-09-15. The authoritative policy is `efficiency-model.md`.

This initiative takes priority over convenience-only work such as the Telegram terminal gateway because it directly improves autonomous throughput, model/test efficiency, and Human Owner attention.

Implementation order:

1. source-of-truth amendment for the approved execution-efficiency policy;
2. #147 Adaptive task budgeting and Human-attention circuit breakers;
3. #148 Layered verification and failure-budget separation;
4. #149 Bounded inter-agent collaboration and review dialogue;
5. #150 Risk-proportionate review and role-specific evidence packs;
6. #151 Telemetry calibration, Human-attention metrics, and continuity automation, including the Human Owner-approved #406 bounded incident-learning/advisory-triage direction. Implement #406 as an extension of TaskOutcome/continuity/memory promotion rather than a separate always-on retrospective agent;
7. #98 Constrained PM-controlled PR merge may proceed where dependencies permit, but must be complete before PCP can claim a routine zero-human-touch happy path.

Guiding constraints for the initiative:

- routine healthy tasks should target zero avoidable Human Owner interventions;
- task estimates are planning/resource signals, while emergency ceilings/circuit breakers protect against abnormal execution and material resource risk;
- provider quota is separate from task estimate exhaustion;
- full required deterministic verification/CI remain mandatory;
- inter-agent collaboration is selective, bounded, and single-writer by default;
- no always-on swarm or recursive agent meeting;
- strong/scarce models and heavy review are risk/value proportional;
- telemetry improves heuristics only after meaningful evidence exists;
- incident learning must prefer deterministic detection and executable prevention,
  must not invoke PM for each ordinary first failure, and must preserve the
  T0/T1/T2/T3/T4 memory lifecycle rather than creating an append-only log.

## Phase 0 — Trust-boundary hardening

Goal: developer workers must be safe enough to become a reusable primitive for later PM-driven orchestration.

Status:

- Runtime API auth fail-closed: complete.
- Router API auth fail-closed: complete.
- ddev-executor auth fail-closed: complete.
- n8n service-scoped secret boundary: complete.
- Antigravity bridge secret/process boundary: complete.
- developer-agent child credential isolation: implementation in PR #33 at the time this roadmap was written; must be merged only after CI and live verification.

Exit criteria:

- coding agents cannot inherit platform-internal credentials or unrelated provider keys;
- Runtime/Router/Executor/bridge boundaries fail closed;
- no regression in Codex/OpenCode/Antigravity execution paths.

## Phase 1 — Repository Source of Truth

Goal: ChatGPT, Codex, and future agents can recover project intent and architecture from Git without relying on chat history.

Deliverables:

- root `AGENTS.md`;
- Project Constitution;
- current/target architecture document;
- agent-team operating model;
- roadmap and documentation index;
- README pointer to these documents.

Exit criteria:

- authority order is explicit;
- implemented behavior is clearly separated from approved target behavior;
- PM autonomy and human-decision boundaries are documented;
- future agents know what to read before changing code.

## Phase 2 — Project Baseline / Constitution schema

Goal: make project-level source of truth a first-class, versioned runtime concept rather than only prose documents.

Expected work:

- define ProjectBaseline/ProjectRevision schema;
- reference checked-in project documentation rather than copying large documents into prompts;
- identify required baseline fields: goals, non-goals, requirements, architecture constraints, quality/security policy, budget policy, roadmap frame;
- persist the revision used by each WorkOrder/job;
- validate that requested work references a known approved baseline.

Constraints:

- do not build PM reasoning yet;
- do not create a vector database unless real retrieval evidence justifies it;
- prefer repository paths/sections and just-in-time retrieval.

Exit criteria:

- every future WorkOrder can name the exact project revision it is governed by.

## Phase 3 — WorkOrder / Task Contract

Goal: replace unconstrained developer prompts with bounded, structured engineering contracts.

Expected fields:

- ID and parent initiative/ticket;
- objective;
- source-of-truth revision and relevant references;
- in-scope / out-of-scope;
- acceptance criteria;
- constraints;
- requested logical role;
- deterministic verification requirements;
- risk/profile/budget envelope;
- dependency metadata.

Expected work:

- schema and validation;
- prompt construction from Task Contract;
- persistence/checkpoint integration;
- tests preventing scope/contract loss across repair/resume.

Exit criteria:

- developer agents receive a stable contract whose meaning survives retries, model failover, CI repair, and process restart.

## Phase 4 — Product Manager role: planning and triage

Goal: add PM as a project-reasoning layer above Router/Runtime.

First PM capability should be intentionally narrow:

1. read the approved ProjectBaseline;
2. assess whether a ticket is inside scope;
3. decompose approved work into WorkOrders;
4. identify dependencies, risks, acceptance criteria, and human-decision boundaries;
5. produce/update a mutable ExecutionPlan.

PM must not directly edit code or select a hard-coded model. It requests a logical role/profile; Router performs staffing.

Human gate:

- initial or materially changed Project Plan requires human approval;
- routine in-scope decomposition does not.

Exit criteria:

- one human ticket can become an approved, dependency-aware list of bounded WorkOrders without changing project scope.

## Phase 5 — Developer WorkReport

Goal: make agent-to-PM communication structured and compact.

Expected work:

- WorkReport schema;
- structured result extraction/adaptation from coding agents;
- criteria mapping;
- changed-component/test/risk/assumption/deviation fields;
- blocked/failure report with root cause/evidence/recommendation;
- retain raw logs separately for diagnostics.

Exit criteria:

- PM does not need full raw agent transcripts for routine task decisions.

## Phase 6 — Independent cross-model Reviewer

Goal: challenge developer assumptions and project alignment using a different reasoning path while controlling budget.

Expected work:

- ReviewReport schema;
- reviewer prompt/context package based on Task Contract, relevant diff/files, deterministic verification, WorkReport, and source-of-truth references;
- Router support for reviewer staffing/diversity policy;
- risk-proportionate review requirements;
- critical/security/architecture different-model/provider rule where eligible capacity exists.

Efficiency rule:

- do not embed the maximum full diff by default;
- provide compact evidence and allow reviewer to retrieve additional workspace context just in time.

Exit criteria:

- accepted work has deterministic evidence plus the configured independent-review evidence without unbounded extra model calls.

## Phase 7 — PM post-task synthesis and feedback loop

Goal: make PM choose the next meaningful action from structured evidence.

Inputs:

- WorkOrder;
- WorkReport;
- deterministic verification;
- ReviewReport;
- CI/delivery evidence;
- remaining budget/provider state.

Outputs:

- TaskOutcome: accept, bounded repair, reassign, replan, block, human decision;
- project/execution-plan effects;
- discovered work classified as inside/outside scope;
- next in-scope WorkOrder when appropriate.

PM should not be invoked for every mechanical repair attempt.

Exit criteria:

- after a task finishes or reaches a meaningful failure state, the system can select the next approved action without human intervention unless a decision boundary is reached.

## Phase 8 — ChangeProposal / source-of-truth amendment flow

Goal: make project-frame changes explicit and human-controlled.

Expected work:

- ChangeProposal schema;
- impact analysis fields;
- waiting-human state integration;
- approved/rejected decision record;
- mechanism to require a source-of-truth Git revision before new work uses the amended baseline.

Exit criteria:

- PM can identify that the current project frame must change, but cannot silently make that change.

## Phase 9 — Telemetry-driven staffing and budget calibration

Goal: replace heuristic model-success assumptions with evidence from the user's own projects.

Collect first:

- role/task class;
- model/provider;
- first-pass success;
- repair count by category;
- verification cycles;
- CI pass rate;
- reviewer finding/useful-finding rate;
- wall time;
- token/resource use;
- provider failure/quota pressure;
- Human Attention metrics;
- task outcome.

Then calibrate Router decisions by project/task/role where sample size is meaningful.

Do not prematurely add statistical complexity from very small samples.

Exit criteria:

- model staffing and effort/budget decisions can cite observed project performance rather than only hand-authored capability/base-success values.

## Phase 10 — Efficiency improvements driven by evidence

The following items are pulled forward under initiative #146 rather than deferred until late optimization:

- task-specific estimated/elastic budgets;
- Human Attention metrics;
- cheap/targeted intermediate verification before final full checks;
- separated retry/failure accounting;
- bounded specialist consultation/review dialogue;
- smarter evidence/context compaction;
- provider/quota resource weights beyond USD.

Candidates that remain evidence-dependent:

- lightweight structural repo map;
- carefully bounded parallel WorkOrders.

## Phase 11 — Owner-only Telegram terminal operations gateway

Goal: allow the Human Owner to run local diagnostics from Telegram without turning Telegram into an unrestricted remote shell or weakening PCP trust boundaries.

The authoritative design is `telegram-terminal-operations.md`.

This remains approved but is lower priority than the execution-efficiency initiative because it is primarily an operator convenience layer.

Implementation order:

1. separate Telegram bot/token and owner/private-chat authentication;
2. WSL long-polling daemon/service lifecycle;
3. `/run-ro` arbitrary diagnostic scripts inside a capability-restricted read-only sandbox;
4. timeout/output/audit controls and secret-free execution environment;
5. PCP read-only broker for jobs/plans/actions/events/quota/logs and optional SELECT-only database principal;
6. optional Telegram-ready block metadata/hash/TTL ergonomics;
7. only after the read-only path is stable, `/run-op` named bounded mutations with explicit confirmation and fresh state revalidation;
8. keep generic `/run-admin` disabled unless a later concrete need passes a separate security/architecture decision.

Critical constraints:

- security must be enforced by OS/container/database capability boundaries, not shell-text regex allow/deny parsing;
- diagnostic scripts receive no Runtime/provider/GitHub/Docker/SSH secrets;
- repository/workspace/log sources are read-only and `/tmp` is the only normal writable scratch area;
- no Docker socket, sudo/root, arbitrary SSH, source-repository writes, database mutation or production authority in `/run-ro`;
- `/run-op` uses named official Runtime/service operations rather than a generic elevated shell;
- existing Runtime durable state, stale-action validation, active-job rollout gates, PM governance and production boundaries remain authoritative;
- ordinary ChatGPT read-only blocks remain ordinary terminal-safe blocks; Telegram-specific formatting is emitted only when the Human Owner explicitly asks for a Telegram-ready block.

Exit criteria:

- the Human Owner can paste a Telegram-ready multi-line diagnostic block and receive bounded output from the local machine while mutation authority and secrets remain unavailable to the diagnostic process;
- common PCP inspection no longer requires exposing mutable Runtime/database credentials to the Telegram-run script;
- any enabled operational mutation preserves the same state-machine and owner-confirmation guarantees as local execution.

## Deferred until demonstrated need

Do not build these merely because multi-agent systems often include them:

- always-on parallel agent swarm;
- Best-of-N implementation generation for routine work;
- recursive reviewer-of-reviewer loops;
- production deployment by agents;
- large vector/RAG infrastructure for code retrieval;
- separate containers/services for PM, developer, QA, architect, and reviewer roles;
- complex dashboards with no demonstrated decision value;
- additional model gateways/services with no active use case.

PM-controlled autonomous merge is no longer a deferred concept; issue #98 tracks its constrained implementation under already-approved governance.

## Current development workflow while building the platform

Until the internal PM/team loop is complete, dogfood the target model manually:

```text
Human Owner
  -> ChatGPT High: architecture / WorkOrder / review
  -> Codex or bounded implementation agent: implementation / tests / repair
  -> ChatGPT High or alternate model: independent review
  -> GitHub CI
  -> PM merge where executable support exists; otherwise follow the current constrained implementation state
```

For very small, obvious patches, direct implementation may be acceptable, but non-trivial subsystem work should follow the WorkOrder/review pattern.
