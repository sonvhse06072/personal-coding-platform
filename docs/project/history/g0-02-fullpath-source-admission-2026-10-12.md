# G0-02/F1 — Full PCP source admission: fail-closed, NOT a runnable pilot

**Ngày:** 2026-10-12 (ICT). **Authority:** T3 design/implementation evidence under [PCP #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595), direct Owner source/tests approval DEC-G0-FULLPATH-SOURCE-01 plus delegated routine technical decisions. **Không** có quyền từ tài liệu này để khởi chạy Runtime, dùng provider, DDEV hoặc đụng dữ liệu lịch sử.

## Vấn đề cần giải quyết

Bài thử G0D-T01 trước đã có 1 cặp code/CI hợp lệ nhưng 0 cặp end-to-end trơn tru; nhánh PCP dùng G0FixtureExecution rút gọn, không phải Planner/Router/RuntimeEngine/Verifier/Delivery thông thường. [T3 paired outcome](g0-02-first-paired-outcome-2026-10-12.md).

Full PCP normal startup hiện có side effects mà không thể an toàn chạy trên legacy PostgreSQL: init/replay job, hủy Antigravity runs host, interrupt/reconcile leases và PlanOrchestrator.tick. Còn fixture G0D-T01 hiện thiếu DDEV-phase executor và privileged GitHub CI delivery, nên bật normal cũng không chứng minh final deterministic quality.

## Source-only F1 implementation

- **Mã nguồn:** services/runtime/app/fullpath_fixture_safety.py, main.py, engine_core.py.
- **Chế độ proposal riêng:** PCP_RUNTIME_STARTUP_MODE=g0_fullpath_candidate; đây là **candidate source-only**, không phải chức năng đã kích hoạt. Lifespan và direct RuntimeEngineCore.start đều từ chối trước Storage.init, global Antigravity cancel-all, legacy work replay, DB leases hoặc scheduler tick. HTTP trả 503 cho mọi route kể cả health, không tạo ấn tượng sẵn sàng sai.
- **Pure admission assessor:** assess_source_contract chỉ kiểm tra object nguồn YAML/env được truyền vào, không đọc secrets, không mở DB/socket, không gọi model. Cấm source/project/root trùng G0D-T01 hoặc global PCP; candidate project id pcp-g0-fullpath-fixture; độc lập DB hostname fullpath-db, database fullpath và user fullpath, Router/Executor host fullpath riêng, không host bridge, Docker socket hay GitHub token trong Runtime. Source mới phải có approved baseline và commit khác seed G0D-T01.
- **Quyền vẫn parked:** tất cả autonomy=false; ddev.enabled=false. Một cấu hình candidate khớp tất cả điều kiện danh tính **vẫn STOP** vì còn ba gate chưa có bằng chứng: hostless deterministic verifier, privileged exact-SHA CI delivery và fixture/operational ownership. Không được hiểu các khóa cấu hình là bằng chứng kỹ thuật Docker isolation.
- **Regression thực sự:** services/runtime/tests/test_g0_fullpath_source_gate.py kiểm chứng context synthetic, negative foreign project/old DB/old seed/global auth/sock, bypass HTTP/lifespan/direct engine.start, existing normal/G0 startup labels. CI của PCP chạy toàn bộ Runtime/Executor/Router/root suites.

## Lộ trình kỹ thuật tiếp theo — tái sử dụng engine hiện hữu

1. **F1b capability contract:** source-only xác định một Executor có thể chạy mandatory Drupal syntax/PHPCS/Unit+Kernel trên *fixture-owned* worktree mà không quyền Docker socket/host DDEV. Nếu không khả thi với image hiện có, document blocker & bounded separate-image capability cần có; không dùng hosted-CI success làm kết quả local DDEV.
2. **F1c accepted-state wiring:** review normal Engine verification và Github delivery để *không đánh dấu completed khi required checks chưa thực thi*, giữ Router staffing/provider/effort/model/usage provenance và một direct-intake job. Chỉ nới module/endpoint đúng synthetic fixture sau khi negative tests minh chứng không reach unrelated project. Không copy G0FixtureExecution thành orchestrator thứ hai.
3. **F2 isolated source-ready topology:** một Compose candidate mới, tên/volume/DB/workspaces/network/profiles mới; không reuse G0D-T01 runtime/DB/journals, không mount Chợ Nhạc/legacy repo, không host Docker socket, không global Codex/Antigravity secrets. Cần admission evidence từ actual image, command allowlist, privilege/mount/network và fresh empty durable state trước khi cho phép normal startup.
4. **F3 live pilot:** chỉ sau source exact-head CI/review và **separate verified operational gates**, một task synthetic fixture mới (không replay G0D-T01), hai arm matched source/model/CLI/effort/acceptance/CI/review, đo chính xác task-cycle, tools, token/owner interventions; G0 NOT GO khi thiếu chứng cứ.

**Stop policy:** nếu chỉ chạy full pipeline được bằng root Docker socket chung, bỏ deterministic verifier/CI, gọi global Antigravity cancel hoặc dựng parallel engine, lập No-Go/simplify proposal trong #595 thay vì cấp thêm model/nguồn lực.

**Không đổi:** original G0D-T01 PCP/Direct jobs, journal, 2 fixture [PR #4](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/4)/[PR #5](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/5) và 2 frozen benchmark refs. Strict Chợ Nhạc/legacy PCP no-touch.

## F1b — mandatory exact-HEAD GitHub Actions CI (source/tests, PR #657)

- Existing Runtime delivery has an optional required_ci contract; its pure verifier requires an authenticated Executor GitHub Actions validation run from the exact fixture repository, on the exact 40-hex commit, with terminal success and no effective failures or conflicting evidence. A generic combined status, unrelated workflow, CI absence (ci_none) or insufficient reconcile_existing payload is a hard DeliveryError for the new fullpath fixture.
- Scope is pinned to future project_id pcp-g0-fullpath-fixture; legacy projects and existing G0D-T01 delivery behavior remain unchanged. All model calls, container operations, PostgreSQL writes, Github delivery actions and CI network requests are synthetic/mocked in tests.
- **Không gọi đây là verifier đầy đủ:** hosted CI can ultimately authorize accepted PR only after publication. Current normal local _verify() skips checks when ddev.enabled=false; the separate hostless pre-delivery requirement and new sandbox ownership are still unproven. g0_fullpath_candidate remains non-executable and all HTTP endpoints 503. No runtime/dev-ops activation authorized by this source merge.


## F1c — CI-deferred verification and PM gate (source-only, PR #658)

Existing Runtime engineering loop now returns a **provisional** `hosted_ci_deferred` result for only future project_id `pcp-g0-fullpath-fixture`: no local PHP/DDEV test has run, so `tests_passed=false`, `test_runs=0`, `local_tests_executed=false`. This provisional `passed=true` flag is strictly for internal Router/reviewer flow, **not final deterministic acceptance**. At first persisted `completed` transition, existing `DeliveryAwareStorage` strictly requires an authorized commit, AI branch, PR/push/commit permissions and CI-deferred evidence, then rewrites durable status to `delivering`, progress required_checks_passed=false, and verification passed=false. Invalid source/rights/result gets blocked without a false terminal success.

Only a genuinely successful exact-repository/HEAD GitHub Actions validation run (PR #657 strict contract) may update hosted_ci_passed=true. Even then the normal delivery path records `waiting_human` with acceptance_phase `awaiting_pm_exact_head_review`, preserving local_tests_executed=false and all original usage/diff/checkpoints. There is **no** implicit PM approval or `completed` transition; a separately reviewed PM acknowledgement contract would be required before counting an accepted end-to-end result. Legacy projects/G0D-T01 pathways are unchanged. This source change calls no model, host Docker, CI provider or database and **does not activate** the non-executable fullpath candidate.

## F1d — PM review finalization requirements (2026-10-12, source-only)

Existing PMChatReviewService (pm_chat_review.py) attests GitHub reviews only for ExecutionPlan/WorkOrder jobs with a plan_id, work_order_id and checkpoint. The first fullpath pilot is **direct-intake standalone**; creating a fictitious Plan solely to use that service would invent authority and distort the benchmark.

**Decision:** Reuse the already existing privileged Executor GitHub review reader, durable Runtime Storage and authenticated PM-control boundary. Do not create a new review server or accept unauthenticated/model-authored JSON. A standalone review receipt needs explicit project id, job id, approved baseline/source commit, AI branch, exact PR/repository/head, known successful hosted validation run and GitHub review ID/author/body digest/submission time. Only a structured PASS/no-blocker exact-HEAD PM review from an allowed reviewer qualifies.

**Finalization:** Verify the review and CI are still valid and PR remains unchanged/open, with no protected Owner decision outstanding. Atomically transition *only* status waiting_human with acceptance_phase awaiting_pm_exact_head_review to completed using row lock/compare-and-swap and a durable unique review decision key. Same receipt retry returns idempotent audit only; conflicting/new-head receipt STOP. Preserve original model counts, diff, journal, timestamps and all review provenance. Merge is a separate privileged action, not inferred from review text.

**Mandatory negative tests:** missing/revoked/edited review, wrong author, cross-repo PR, stale head, baseline drift, CI failure/none, missing exact job/branch, duplicate concurrent control, mismatched protected approval or foreign project must NOT finalize or merge. Keep existing legacy PCP/Chợ Nhạc PM review logic unchanged.

**Operational status:** This is a source design contract, not a callable API/approval. Fullpath startup still intentionally refused, and a completely new fixture/DB/workspace/Router/Executor/provider namespace must first be proven. G0 remains HOLD/NOT GO; prior G0D-T01 jobs/PR bases unchanged.
