# PCP Business and Product Strategy

Status: Owner-approved product direction updated 2026-10-09; implementation/rollout status remains governed by live Runtime/GitHub evidence. Historical synthesis below remains supporting context, not an active roadmap override.

This document does **not** create a new commercialization mandate, weaken any Constitution boundary, or expand PCP into a multi-tenant product. It makes the existing business/product logic explicit so future PCP work can be prioritized by user value instead of by technical novelty or whichever managed-project blocker happened most recently.

## 1. Product identity

PCP is a **personal engineering operating system for one Human Owner**.

Its job is to turn approved project intent into reliable, bounded engineering outcomes by coordinating Product Manager reasoning, model/provider staffing, developer execution, deterministic verification, independent review, GitHub delivery and safe recovery.

PCP is not currently a SaaS business. It has one primary customer: the Human Owner. Managed projects such as Chợ Nhạc are consumers and dogfood environments for PCP capabilities, not separate customers that automatically define the PCP roadmap.

The current economic case is internal leverage:

> increase accepted engineering outcomes while reducing avoidable Human Owner attention, repetitive operator work, wasted model/provider capacity and recurring platform failure.

External users, pricing, multi-tenancy, enterprise administration, public hosting and commercial support are outside the current product frame. Any future commercialization requires a separate Human Owner decision and a new product/business baseline.

### Định hướng sản phẩm được Owner chấp thuận — 2026-10-09

**North Star:** Từ nghiệp vụ, tài liệu và phạm vi đã được Owner phê duyệt, PCP tự phát triển các thay đổi phần mềm tuần tự đến trạng thái được nghiệm thu; lựa chọn tài nguyên AI phù hợp, duy trì kiến thức chính xác, và ưu tiên tự chẩn đoán/phục hồi lỗi thường gặp. Chỉ yêu cầu Owner khi phát sinh quyết định thuộc quyền bảo vệ hoặc không còn phương án tiếp tục an toàn.

**Bốn năng lực cốt lõi (định hướng, không mặc nhiên đã triển khai đầy đủ):**

1. **Autonomous Development:** ChatGPT/Owner chốt nghiệp vụ và tài liệu; PM local lập/duy trì ExecutionPlan, WorkOrder và dependency; Runtime điều phối code → kiểm thử → review → PR/CI → PM merge đủ điều kiện → WorkOrder tiếp theo.
2. **Resource Optimization:** PM phân tích độ phức tạp; Router lựa chọn provider, model, reasoning effort, review strategy và ngân sách theo chi phí **mỗi kết quả được nghiệm thu**, tính cả lượt phân tích, retry, test, quota và Human Attention. Không tối ưu riêng giá token.
3. **Bounded Self-Healing:** Phân loại failure; tự chẩn đoán, sửa và phục hồi cùng durable job khi có bằng chứng/đường phục hồi được cho phép, bảo toàn diff, lease, counters và ProjectBaseline. Không coi lỗi lặp không tiến triển là lý do retry vô hạn; không hứa tự sửa mọi lỗi hệ thống.
4. **Documentation & Context Governance:** Chuẩn hóa tài liệu theo quyền hạn, freshness và T0–T4; ngăn drift khỏi business/architecture được duyệt; tạo context pack theo role/task, đo omission, stale retrieval, token bloat và cải thiện có kiểm chứng.

**Các năng lực hỗ trợ**, không xây thành dịch vụ/agent độc lập nếu có thể mở rộng cấu phần hiện tại:

- **Trusted Project Development:** Developer có quyền đủ rộng **trong môi trường phát triển được ủy quyền**, chạy build/DDEV/browser/preview, sửa scope kỹ thuật phục vụ acceptance criteria; không nhận quyền đổi business, privileged PCP, secrets, production, destructive data hoặc tự merge.
- **Rule / Tool / Skill Management:** Nhận diện kỹ năng và công cụ cần cho WorkOrder; chọn skill theo nhu cầu, ưu tiên nguồn uy tín và kiểm chứng trước khi đưa vào project; học từ hiệu quả thực tế, không tích trữ skill hoặc context mặc định.
- **Provider Intelligence:** Theo dõi release/model/effort/quota/deprecation, xác minh khả năng dùng theo provider/adapter/tài khoản, đánh giá chi phí/lợi ích, cập nhật bằng PR/version/CI và rollout an toàn khi đủ quyền; không chạy theo bản mới nhất một cách mù quáng.

**Năng lực thứ năm của tầm nhìn — Future/Deferred:** Chủ động phân tích một repository chưa có tài liệu, reverse-engineer code, hỏi Owner để làm rõ nghiệp vụ và đề xuất ProjectBaseline. **Không triển khai hoặc kích hoạt onboarding tự động ở giai đoạn hiện tại**; cần quyết định Owner riêng sau khi bốn năng lực chính ổn định.

**Định hướng đầu tư:** Refactor có chọn lọc PCP hiện hữu thay vì viết lại toàn bộ. Thực thi theo giai đoạn có benchmark/stop-go; không mở thêm hạ tầng, role hoặc recovery protocol chỉ vì tính năng có vẻ hữu ích. Chợ Nhạc đang theo TECH-DEC-040 (Codex-first + PCP-light) cho công việc mới; PCP không được tự thu hồi quyền điều phối, chiếm workspace hoặc vượt qua lease/job hiện hữu chỉ vì roadmap mới.

Nguồn yêu cầu: [#587](https://github.com/sonvhse06072/personal-coding-platform/issues/587), [#588](https://github.com/sonvhse06072/personal-coding-platform/issues/588), [#589](https://github.com/sonvhse06072/personal-coding-platform/issues/589), [#590](https://github.com/sonvhse06072/personal-coding-platform/issues/590), [#591](https://github.com/sonvhse06072/personal-coding-platform/issues/591). Chi tiết kiến trúc đích thuộc **architecture.md**, quyền/quy trình thuộc **operating-model.md**, đo hiệu suất thuộc **efficiency-model.md**, thứ tự/effort thuộc **roadmap.md**.

**Giới hạn ủy quyền:** Việc Owner đồng ý định hướng và tài liệu **không** tự động sửa Constitution, project baseline đã được duyệt, mô hình bảo mật, quyền developer đang triển khai, CI/merge/deploy gate hoặc ngân sách. Mọi thay đổi thuộc thẩm quyền được bảo vệ phải có ChangeProposal, phê duyệt đúng phạm vi, PR và kiểm chứng riêng.

## 2. Primary user and jobs-to-be-done

The primary user is a technically capable Human Owner who already knows how to develop software, operate Git/DDEV and review implementation, but does not want to spend scarce attention on routine coordination and recovery.

PCP should help the owner:

- convert an approved product request into bounded WorkOrders;
- let routine implementation proceed without constant supervision;
- preserve exact project scope and architecture constraints across model turns and failures;
- choose models/providers according to task value, capability and resource state rather than habit;
- obtain deterministic verification and independent review before merge;
- review and merge routine in-scope work remotely;
- diagnose and recover the same durable job when execution blocks;
- avoid reopening WSL/DDEV for ordinary control-plane actions;
- resume project work from repository/runtime state instead of reconstructing context from chat history;
- reuse platform improvements across multiple personal projects.

The desired Human Owner role is therefore **decision maker and product owner**, not full-time job scheduler, retry operator or transcript reader.

## 3. Problem PCP is solving

Without PCP, personal AI-assisted development tends to fragment across chat sessions, CLIs, provider accounts, local shells, CI runs and ad-hoc recovery steps. The recurring costs are not only model tokens or subscription fees. They include:

- repeated explanation of project context;
- manual decomposition and task routing;
- hidden drift from approved scope;
- repeated test/retry loops;
- inconsistent review quality;
- duplicated local commands;
- fragile handoff between models/tools;
- owner attention spent on mechanical continuation;
- inability to operate or diagnose a home development environment remotely;
- fixes that solve one incident but do not become reusable platform behavior.

PCP exists when it can reduce those costs **without** trading away deterministic verification, security boundaries, source-of-truth discipline or Human Owner authority over protected decisions.

## 4. Value proposition

PCP should create value in five ways.

### 4.1 Owner leverage

Routine tickets should move from approved intent to reviewed/verified PR with little or no avoidable owner intervention.

A platform improvement is valuable when it removes repeated Human Owner work while retaining an auditable decision boundary.

### 4.2 Engineering quality

Models provide flexible reasoning, but executable truth remains anchored by:

- bounded WorkOrders;
- deterministic tests/static analysis;
- risk-proportionate independent review;
- exact-head CI;
- Git/PR identity;
- durable checkpoints and failure evidence.

PCP should improve throughput only when final quality/security gates remain intact.

### 4.3 Resource efficiency

The platform should spend model/provider quota, tokens, tests, wall time and stronger-model capacity where they have expected value.

More agents, more model calls, more tests or more parallelism are not business outcomes. Accepted work per unit of resource is.

### 4.4 Operational continuity

A job or plan should survive normal failures without forcing the owner to reconstruct state or create replacement work.

Remote GitHub PM controls and the Guardian are valuable because they reduce dependence on physical access to the development workstation, while still failing closed when local state cannot be proven safe.

### 4.5 Reuse across projects

PCP investment compounds only when a capability is reusable.

A fix that benefits one managed project may still be correct, but it belongs in that project unless the evidence demonstrates a generic PCP defect, missing platform capability, repeated owner-cost pattern or reusable governance/verification need.

## 5. Business north star

The north-star business outcome is:

> **useful accepted engineering work per unit of Human Owner attention and total personal resource consumption.**

The platform should not optimize one metric in isolation. For example, lowering model cost is not success if it increases owner intervention or escaped defects; reducing cycle time is not success if it weakens review or CI gates.

Directional primary metrics:

- Human Owner interventions per accepted task;
- manual WSL/local-operator actions per routine task;
- elapsed time from accepted ticket to merged PR;
- avoidable blocker events per task;
- repeated blocker/root-cause recurrence;
- model/tool/test usage per accepted task;
- provider quota pressure attributable to retries/no-progress work;
- useful reviewer finding rate;
- percentage of routine control actions handled remotely without local shell interaction;
- first-pass or low-repair completion rate for appropriately bounded WorkOrders.

Guardrail metrics:

- unresolved protected decisions bypassed: 0;
- force/reset/state-rewrite recovery used to bypass governance: 0;
- replacement jobs created only to escape a blocker: 0;
- production/deployment actions performed without explicit authority: 0;
- security/trust-boundary credential leakage: 0;
- required deterministic verification or exact-head CI skipped: 0.

Metrics should be interpreted over meaningful samples. PCP should not add statistical or dashboard complexity before the collected evidence can change a decision.

## 6. Economic model

PCP is currently an internal productivity investment, not a revenue product.

Its relevant cost base includes:

- model subscriptions and provider quota;
- metered API spend where applicable;
- test and CI time;
- local compute/storage/Docker/DDEV overhead;
- maintenance burden of PCP itself;
- Human Owner attention;
- failure/recovery time;
- complexity debt introduced by additional services or abstractions.

Many provider costs are fixed or semi-fixed subscription capacity. Therefore PCP should not minimize every model call blindly. It should optimize **marginal useful output** from available capacity while reserving scarce/strong models for work where they materially improve outcome probability.

A new PCP capability is economically justified when credible evidence shows that it will do one or more of the following:

1. remove recurring owner intervention;
2. prevent or shorten a recurring blocker/failure class;
3. reduce material model/tool/test waste;
4. improve accepted-work quality or reduce escape risk;
5. make an existing approved project workflow safely executable;
6. strengthen a trust/governance boundary required for greater autonomy;
7. create reusable leverage across more than one task or project class.

Technical novelty, dashboard completeness, agent count or architectural elegance are insufficient reasons on their own.

## 7. Product investment rules

### 7.1 Reliability before capability expansion

Once an end-to-end capability exists, recurring defects in that path take priority over adjacent feature expansion.

The current product stage is consolidation/reliability rather than broad capability construction. PCP already has PM planning/orchestration, bounded execution, verification/review, GitHub delivery, constrained PM merge, remote PM controls and a Guardian path. The near-term business return comes from making these paths boring, predictable and low-touch.

### 7.2 Dogfood is evidence, not roadmap authority

Managed-project incidents are valuable natural tests, but they do not automatically create PCP scope.

When a managed project blocks:

1. determine whether the problem belongs to the project or the platform;
2. fix application-specific requirements/contracts/tests in the project;
3. create PCP work only when evidence shows a generic platform defect, missing reusable capability, recurring operator burden or broken approved platform invariant;
4. prefer repairing the existing PCP issue/capability over opening a new adjacent issue;
5. do not keep expanding PCP merely because one dogfood ticket discovers another project-specific problem.

A successful natural acceptance case should close or reconcile PCP scope rather than become a default source of new platform work.

### 7.3 Smallest reusable layer

Prefer the smallest change that makes the next real workflow reliable.

Do not add:

- general-purpose remote shell;
- always-on agent swarms;
- speculative multi-project orchestration;
- extra dashboards that do not change decisions;
- provider abstractions without an actual staffing/reliability need;
- duplicate state stores;
- convenience automation whose maintenance cost exceeds the owner time it saves.

### 7.4 Preserve optionality

Provider/model assignments should remain replaceable. Project source of truth should remain repository-resident. Runtime state should remain auditable. Managed projects should not become coupled to one model or to PCP-internal implementation details.

This preserves the owner's ability to change providers, projects and tactics without rebuilding the entire operating system.

## 8. Current portfolio priority

As of 2026-10-07, the PCP GitHub engineering backlog is intentionally small.

- **#493 — DDEV cold/bootstrap hardening:** real independent reliability/resource issue. It remains legitimate engineering work because cold bootstrap behavior can block execution and waste local infrastructure time.
- **#512 — Remote PM control plane + Guardian:** parent acceptance remains open for natural evidence, not broad new source implementation. Missing natural proofs should not justify synthetic jobs or destructive outage tests.
- **#524 — Guardian control/audit:** intentionally persistent operational channel, not product backlog.

RCTL-MVP #513 is completed. Runtime 1.0.131 is live on PCP main `6db414df30040cacc9fd922283eb21e06ba576b8`. The remote standalone-merge/supervised-continuation path is live-proven, and #555 additionally live-proved bounded GitHub same-job recovery from an exact `collaboration_pm_handoff` without reroute, provider reset, replacement job or counter reset.

Therefore the default PCP roadmap posture is:

1. finish/reconcile existing issues before opening new scope;
2. let active managed-project work supply natural acceptance evidence;
3. fix generic defects discovered by dogfood, but keep application work in the application repo;
4. collect enough real execution evidence to calibrate staffing/budgets;
5. add new convenience or autonomy capabilities only after the current loop is demonstrably reliable.

## 9. Product maturity stages

### Stage A — Safe execution primitive

Capabilities: constrained workspaces, routing, deterministic checks, bounded delivery, trust boundaries.

Business question: can AI coding work be executed safely enough to reuse?

Status: substantially achieved.

### Stage B — Managed personal engineering team

Capabilities: ProjectBaseline, WorkOrders, PM planning, developer/reviewer roles, supervised orchestration, PM merge.

Business question: can the owner delegate routine engineering rather than operate every step?

Status: achieved sufficiently for live dogfood; reliability remains the focus.

### Stage C — Low-touch remote personal engineering

Capabilities: GitHub PM controls, same-job recovery, remote merge/continue, Guardian rollout/diagnostics.

Business question: can the owner manage projects from ChatGPT/GitHub without routine WSL access?

Status: core loop proven; a small number of parent #512 natural acceptance boundaries remain.

### Stage D — Evidence-calibrated personal platform

Capabilities: project/task outcome telemetry that materially improves staffing, budgets and review allocation.

Business question: does PCP measurably produce more accepted work with less owner attention/resource waste over time?

Status: next maturity objective after reliability and sufficient sample size.

### Stage E — Optional external product

External users, hosting, billing, multi-tenancy and support.

Status: **not approved / not planned**. Entering this stage requires a separate Human Owner product and business decision.

## 10. Prioritization test for new PCP work

Before opening or starting a material PCP issue, PM should answer:

- What owner/business problem does this solve?
- Is the problem generic to PCP or specific to one managed project?
- What evidence shows recurrence, cost, risk or blocked value?
- Can an existing issue/capability be repaired instead?
- What owner attention, resource waste, quality risk or workflow limitation will improve?
- Is the expected benefit reusable?
- Does the change add ongoing maintenance or trust-boundary cost?
- Can the same value be obtained with a smaller change?
- What metric or observable outcome would show that the change worked?

If these questions do not establish a meaningful expected return, defer the work.

## 11. Business risks

### Platform-building becomes the product

Risk: every dogfood incident opens another PCP feature and managed-project delivery slows indefinitely.

Mitigation: dogfood rule, existing-issue reconciliation, smallest reusable layer, explicit business-value gate.

### Automation increases owner burden

Risk: complicated gates, counters or dashboards generate more intervention than manual work.

Mitigation: Human Attention remains a first-class resource; healthy-progress execution should be non-blocking.

### Provider spend grows without accepted output

Risk: retries, model escalation or review loops consume quota without material progress.

Mitigation: anti-loop signals, deterministic failure evidence, bounded collaboration, risk-proportionate review and telemetry calibration.

### Reliability debt grows with capability count

Risk: each new service/action increases maintenance and recovery surface.

Mitigation: reliability-first roadmap, finite control enums, no general remote shell, no speculative services.

### PCP becomes coupled to one managed project

Risk: Chợ Nhạc-specific assumptions leak into generic Runtime/Router behavior.

Mitigation: project-specific logic stays in project source/config/WorkOrders; PCP changes require generic platform evidence.

## 12. Review cadence

Business/product strategy should be revisited when one of these occurs:

- a major new PCP capability is proposed;
- a recurring managed-project incident reveals a generic platform cost;
- owner-intervention/resource telemetry shows a material bottleneck;
- provider economics/capabilities materially change;
- the owner considers external commercialization;
- the current roadmap has no remaining evidence-backed engineering work.

Routine implementation findings do not require rewriting this strategy. Update the mutable roadmap/current-state first; amend this document only when the underlying product/investment logic changes.
