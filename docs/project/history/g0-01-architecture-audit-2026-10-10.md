# G0-01 — PCP architecture & critical-path evidence audit (2026-10-10)

**Phân loại:** T3 / `evidence_history`. **Workstream:** [#594](https://github.com/sonvhse06072/personal-coding-platform/issues/594), thuộc [#593](https://github.com/sonvhse06072/personal-coding-platform/issues/593). Đây là **báo cáo thực trạng và phương án cần đánh giá**, không sửa Constitution, architecture authority, ProjectBaseline hoặc cấp thêm quyền runtime.

**Trạng thái evidence:** source inventory và deployed health **đã đối chiếu**; direct Chợ Nhạc historical PCP job **đã truy vấn từ Runtime**; project lease table / current direct writer vẫn cần xác minh độc lập trước bất kỳ shared-workspace write; **live shared worktree của Chợ Nhạc đang dirty trên nhánh Codex**; chưa có cohort benchmark hợp lệ. Không đánh đồng `service OK` với `zero writer`.

## 1. Provenance — không nhập nhằng source, deployed, historical

| Loại | Nguồn/identity | Điều đã chứng minh | Giới hạn |
| --- | --- | --- | --- |
| GitHub authoritative implementation | PCP `main@aae9da0f4164b496f4fbb153d8e2fa4083d6fa08` | 17 commit sau `d53fbb0`, chỉ đổi 8 file `docs/project/*.md`, `scripts/context_memory.py`, `tests/test_context_memory.py`; Router/Runtime/Executor/Guardian/adapters không đổi trong khoảng này ([compare](https://github.com/sonvhse06072/personal-coding-platform/compare/d53fbb07524bb3ca13324e2ed7edac1513367072...aae9da0f4164b496f4fbb153d8e2fa4083d6fa08)) | Không đồng nghĩa với deployed HEAD |
| Guardian fresh read-only | [status 6093920625](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625) ngày 2026-10-10 | Runtime `1.0.141`, Router `1.0.31`, DDEV Executor `1.0.35`, Antigravity `1.13`, n8n, credential boundary reachable/OK; Runtime engineering=0, Executor jobs=0, Antigravity runs=0 **ở thời điểm snapshot** | Không xác nhận mọi project lease đã release; không phải standing rollout permission |
| Local PCP git qua Guardian | Cùng snapshot | local `main` clean, HEAD `d53fbb07524bb3ca13324e2ed7edac1513367072`; cached origin tương ứng | Local main đi sau GitHub 17 commit; phần diff chỉ docs/context script/tests, chưa sync |
| Owner local DDEV read-only | `ddev describe`, `docker ps -a` 2026-10-10 | PCP web/db/coding-runtime/router/executor/n8n container Up; DDEV `v1.25.4`; web PHP 8.4, Node 24; Chợ Nhạc frontend/backend/database/test containers cũng Up | Docker process Up **không** chứng minh API health, DB lease hay Codex writer idle; xhgui optional stopped không phải lỗi |
| GH-89 durable job **vs live shared worktree** | [2026-10-10 Runtime diagnostic 6093934986](https://github.com/sonvhse06072/chonhac/issues/89#issuecomment-6093934986) | Persisted PCP job `08ae925693b85379b11a54e4dc26121e` vẫn `blocked`; plan `pm-gh-6064614742` checkpoint 187, original source `a9c60bf667c48afbbc0d5c96f85b6a834e37265a` và recorded job branch `ai/08ae925693b8`. **Current direct worktree khác hẳn:** `codex/132-stage-b-editorial-repair`, dirty, HEAD `b133355926098682a2ef88a72adba46cb3d8c0d0`, observed origin/main `436fccf95a677e6c7e7f24d948e53a2f79ee65cc`; Runtime active engineering=0 | Bằng chứng ghi rõ Codex-direct đã tiến triển độc lập, nhưng không chứng minh lease table của PCP đã release hoặc Codex không còn đang viết. **Không được checkout/reset/tiếp quản shared worktree; cần xác minh lease bằng cơ chế riêng.** |

**Durable identity mismatch is expected after Codex-direct handoff, not proof of lease release:** persisted GH-89 job retains its original `ai/08ae...` reference, while DDEV Executor currently observes a dirty Codex branch. Do not operate either writer from this audit; preserve Codex branch state, original PCP durable job and both records separately.

**Runtime incident:** [status 6093879505](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093879505) trước đó ghi Runtime timeout và active-count unavailable, nhưng [6093920625](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625) sau phục hồi có healthy/zero-active. Ghi nhận như hai mốc thời điểm, không che incident, không tự gán nguyên nhân cho việc host boot.

## 2. Component ownership / reuse decision

| Subsystem (source anchors on `main`) | Đã có | Gap cần đo hoặc bổ sung | Workstream |
| --- | --- | --- | --- |
| Runtime/PM `pm_planning.py`, `plan_orchestrator.py`, `pm_merge.py` | Durable plans, WorkOrders, dependencies, checkpoint, gated merge | Shorten simple-task critical path và reconcile next-ready; đo PM/reviewer overhead | #595, #599, #600 |
| Router `services/router/app/engine_*.py`, `config/models.yml` | Model/quota/reasoning/budget policy | Outcome-based calibration, provider discovery/probe | #605–#607 |
| Codex `services/runtime/app/adapters/codex.py`, Runtime Dockerfile | Non-interactive streaming Codex execute/repair | Sandbox `workspace-write`, local network off; Runtime image thiếu PHP/DDEV | #596–#597 |
| Antigravity `developer_permissions.py` + host bridge | `trusted_local` đúng exact direct project, adapter `antigravity_host` | Không tự cấp `trusted_local` cho Codex; quyền kỹ thuật/trust cần proposal | #596 |
| Executor + preview `services/ddev-executor/app/`, `preview.py`, `visual_evidence.py` | DDEV targeted/frontend/visual checks, preview lease guard, image 1.0.35 observed | Developer-in-turn dev commands và browser/screenshot/console loop chưa chứng minh | #597–#598 |
| Verification/review `engine_verification.py`, `review.py`, CI workflows | Final deterministic phases, source/diff/head proof, mandatory CI | Failure attribution, redundant verifier rounds và review cost | #595, #599, #601 |
| PM Bridge / Guardian `pm_bridge.py`, `pm_diagnostics.py`, `scripts/pcp_guardian.py` | Author-bound controls, read-only diagnostics, out-of-band status, safe rollout gating | Natural outage recovery + same-job repair class; fail closed khi active count unavailable | #512, #601–#602 |
| Docs/context `scripts/context_memory.py`, context eval, T0–T4 | Standalone deterministic retrieval and protected doc authority | Runtime role context packs và drift/write pipeline chưa end-to-end | #603–#604 |
| Skill/capability `config/models.yml`, project skills, quota tools | Explicit registry, project-local skills | Discovery + safe selective loading + effectiveness outcome | #606–#609 |

Do not reimplement shipped foundations (#317, #426/#427, #562, #563, #571); the original request issues #586/#587/#589/#590 are archived duplicates. #493 now version-observed but lacks natural cold-start acceptance; #512 natural remote acceptance still open; #524 is operations audit, not an engineering task; #588 stays future/deferred.

## 3. Current critical paths (hypotheses pending measurements)

**Small approved routine task:**

```text
PCP: approved task -> intake/classifier -> Router -> Runtime job/lease
   -> Codex/Antigravity edit -> separate deterministic verification
   -> conditional PM reassessment/repair/evaluator -> PR
   -> exact-head CI -> PM review/eligible merge

Codex-direct: approved task -> direct WSL workspace edit + local test
   -> required final verification -> PR -> exact-head CI -> PM review/merge
```

**Frontend multi-layer task:**

```text
PCP: approved UI scope -> planning/WorkOrders -> developer turn
   -> Runner frontend_quality/visual_quality -> failure or no-preview
   -> repair/reroute -> external visual evidence -> PR/CI/review
Direct: approved UI scope -> edit -> local DDEV/Next live URL
   -> browser DOM/console/screenshots -> same-turn repair
   -> full tests + visual evidence -> PR/CI/review
```

These are architectural control flows, **not measured timing traces**. Verification and PR gates are preserved in both comparators. No artificial Chợ Nhạc task may be launched for G0 benchmarking.

## 4. Ten bottlenecks — ranked by expected leverage, NOT measured ROI

| Priority | Observed source/incident signal | Expected effect, certainty | Validate in #595 / mitigation owner |
| --- | --- | --- | --- |
| 1 | Codex adapter pins `sandbox_workspace_write.network_access=false`; `local_listener=false`, `php_runtime=false`; Runtime Dockerfile no PHP | **High, source-confirmed capability gap**; cost impact unmeasured | #596/#597: same job PHP/DDEV build/test |
| 2 | Preview/visual verification services exist separately; developer browser-in-turn not demonstrated | **High, architecture gap**; actual incidence unknown | #598: live edit→URL→console/screenshot→repair acceptance |
| 3 | GH-89 `frontend_quality` failure; 12 repair iterations, 51 test runs, 76.966m elapsed on preserved job | **High, historical concrete case**; not evidence all rounds unnecessary | #599/#601: classify verifier failures and stop/recovery |
| 4 | GH-89 blocked checkpoint 187 and `attention.actions=[]` despite Codex-direct PRs shipped separately | **High, concrete historical gap**; exact active lease unknown | #601: same-job recovery/retirement protocol, no DB reset |
| 5 | Historical Guardian `ddev restart` 900s timeout; #493 distinct Executor cold-bootstrap | **High incident severity**; common root cause not proven | #602 and #512; preserve separate issue semantics |
| 6 | PM planning, reassessment and review may add repeated turns for small tasks | **Medium/high hypothesis**, no comparable latency evidence | #595 benchmark, #599 fast path |
| 7 | Scope/budget heuristics may cause avoidable owner handoffs or missed supporting refactors | **Medium/high hypothesis**, impact rate unknown | #596 contract; #599 instrumentation |
| 8 | Standalone Context Composer is implemented; runtime PM/Dev/Reviewer usage not verified | **Medium; source-confirmed integration unknown** | #603/#604 role provenance and omission test |
| 9 | Provider/model/effort/CLI pins updated manually; prior model mismatch incidents | **Medium; historical incidents confirmed** | #606/#607; capability canary and cost |
| 10 | Skills exist in project repos but no proven role-specific selection/effectiveness feedback | **Medium; actual ROI unknown** | #608/#609; measured accepted outcomes |

**Observed GH-89 metrics are a single historical job, not a controlled A/B cohort.** No trustworthy PCP-vs-direct p50/p90, cached tokens, context savings, owner-wait distribution or accepted-quality equivalence can be inferred from these data alone.

## 5. ADR-G0-01 (DRAFT) — smallest trusted-dev boundary worth benchmarking

- **Option A — Existing Executor broker (first to evaluate):** allowlisted project+workspace+lease-bound DDEV/PHP/Node/browser tooling while Codex remains isolated; reuses existing privileged boundary and audit. Costs: explicit mediated tool protocol, IPC latency, challenge streaming rich browser feedback.
- **Option B — Host-constrained Codex adapter:** best experiential parity with direct WSL Codex; high risk of credential/process/socket/network leakage unless OS-enforced sandbox and exact single-writer proven. No blanket host privileges under current Constitution.
- **Option C — Dedicated scoped dev container:** reproducible PHP/Node/Playwright toolchain; extra image/startup/maintenance, still needs governed DDEV/browser access. No Docker socket to developer.

**Provisional choice:** test A before adding a service, compare with B/C on identical tests, security-negative cases and A/B accepted outcomes. This *is not approval to modify protected trust boundaries*. An explicit Owner-reviewed ChangeProposal is mandatory before implementing #596 protected changes.

**Negative acceptance:** no unrelated workspace, secrets, Docker socket/root, production URL, credentials, bypassed merge, mutated historical GH-89 lease or accidental live Chợ Nhạc writer collision. Fail closed on stale/unknown state.

## 6. Dependency/go-no-go and next evidence

```text
#591 docs prerequisite DONE -> #594 audit/evidence
  -> #595 controlled direct-vs-PCP benchmark, report + G0 decision
  -> [separate approved security/architecture ChangeProposal, G0 GO]
  -> #596 -> #597 -> #598 -> #599 [G1 exit]
  -> (#600,#601,#602,#603), #603 -> #604 -> #605 [G2 exit]
  -> (#606 -> #607), (#608 -> #609) -> #610 [G3 RC1]
```

**#594 completion gate:** source/deployed provenance and risks recorded; measurable/unknown distinctions explicit; historical direct-workspace lease verified independently or recorded as protected unresolved safety condition; 10 impact hypotheses, critical paths and alternatives documented. **#595 owns actual benchmark measurements**; do not create a circular dependency by requiring #595 p50/p90 to close #594 while forbidding #595 until #594 closes.

**#595 benchmark contract (not begun):** pick existing historical outcomes plus at least one isolated independent Drupal/domain, Next/browser and repair fixture, pin task/source/model/effort/environment/acceptance/CI; record cohorts, p50/p90 only for sufficient comparable samples, actual input/output/cached tokens if provider exposes them, model/repair/test/CI/owner attention, visual acceptance. Report insufficient evidence rather than inventing numbers.

**Do not:** restart DDEV/Runtime, sync local repo automatically, issue `resume_same_job`, modify GH-89 job/lease, execute Chợ Nhạc source edits, invent route permission, mark #493 cold-start done, enable production deploy or call this a live benchmark.

**Source map:** [PCP #594 source audit](https://github.com/sonvhse06072/personal-coding-platform/issues/594#issuecomment-6082567587); [new #594 evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/594#issuecomment-6093894337); [Guardian fresh](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625); [GH-89](https://github.com/sonvhse06072/chonhac/issues/89); authoritative T0/T2: `AGENTS.md`, `docs/project/constitution.md`, `architecture.md`, `operating-model.md`, `roadmap.md`.
