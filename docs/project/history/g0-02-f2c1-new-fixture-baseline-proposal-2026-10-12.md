# G0-02 / F2d-04C-1 — Fixture mới và đề xuất ProjectBaseline kế nhiệm

**Loại:** Tier-3 exact-source acceptance / ChangeProposal. **Ngày:** 2026-10-12 (ICT). **Canonical:** [PCP #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595).

**Trạng thái:** F2-C1 **FIXTURE SOURCE + HOSTED CI ACCEPTED**. Candidate ProjectBaseline **DRAFT / `active_revision: null`**, chưa được Human Owner phê duyệt; F2 Runtime vẫn PARKED, G0 HOLD/NOT GO, G1 #596 chưa mở.

## 1. Bằng chứng GitHub thực tế

- Owner đã khởi tạo repository **Private** mới [`sonvhse06072/pcp-g0-fullpath-fixture`](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture); GitHub connector xác nhận `private=true` và quyền push/admin, repository ban đầu README-only `main@eef96cf029e205eb6f1883622499e3ffce286635`.
- Engineering PM tạo [PR #1](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/pull/1), một module **hoàn toàn mới** `pcp_f2_fixture` với service `WindowOverlapDetector`, không sao chép `EventLabelNormalizer` hoặc mã nghiệp vụ của G0D-T01. Baseline hiện xử lý giao nhau nửa-khoảng [start,end) **cùng ngày**; hỗ trợ qua nửa đêm thuộc *task sau*.
- PHP/Drupal toolchain vẫn là Drupal 11, PHP 8.4, MariaDB 10.11. **Chỉ dùng lại dependency manifest và Composer lock của bên thứ ba** (G0 fixture trước đó đã hosted-tested), để tiết kiệm thời gian giải quyết dependency; *không dùng lại source task, seed hoặc PR lịch sử*. Workflow `validation` riêng được pin `checkout@v7` + `setup-php@2.40.0`, `ubuntu-24.04`, `permissions: contents: read`, `persist-credentials:false`, không self-hosted PR/secret/deploy.
- [Exact-HEAD GitHub-hosted run #38277967715](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/actions/runs/38277967715): event `pull_request`, attempt 1, head `7b11b42755b5821349ff5e6453a79492e1d6d5e2`, `fixture-validation` **SUCCESS**: `composer validate --strict`, locked `composer install`, PHP syntax, Drupal PHPCS, Unit **4 tests / 7 assertions**, real Drupal Kernel **1 test / 3 assertions**. Một deprecation upstream ở Kernel, không có test failure. Engineering PM exact-head COMMENT review `5493581164`, không có blocking findings.
- PR #1 **MERGED** thành `main@e59e6a2119c96a2dddb5b32f68ba178e0ac61140`. Nhánh **`benchmark/fullpath` được tạo từ chính merge SHA đó** và được re-fetch xác nhận đúng cùng SHA; seed này là **bất biến theo quy trình**, không được tự fast-forward hay reset. Hai nhánh `benchmark/pcp` và `benchmark/direct` thuộc repository **G0 cũ** vẫn giữ `39ef13c25b24c4a1b43a720ae53419f479996ed2`.
- New independent [issue F2-T01 #2](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/issues/2) có [acceptance source](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/blob/benchmark/fullpath/docs/F2-T01.md): mở rộng hỗ trợ half-open interval qua nửa đêm, chỉ ba file ứng dụng/Unit/Kernel trong scope; `HOLD`, **chưa dispatch** Codex/PCP/model và chưa bắt đầu tính số mẫu benchmark.

Đây là *fixture/CI source acceptance*, **không phải successful normal PCP end-to-end job** hoặc phép đo performance. Không suy ra p50/p90/ROI.

## 2. Draft successor ProjectBaseline — NOT ACTIVATED

`ProjectBaseline` runtime schema trong `services/runtime/app/baseline.py` yêu cầu `source_commit`, `status`, `authority`, đủ tám nhóm `references`. Đây là YAML **đề xuất**, **chỉ** lưu trong T3 để review; **chưa ghi vào** `config/fullpath-candidate/project-baselines.yml`, vì đó là thay đổi quyền ProjectBaseline `human_owner_protected`. Khi Owner phê duyệt đúng source commit và phạm vi, lập PR riêng có doc authority review để tạo revision; `active_revision` vẫn null cho đến khi có quyết định activation riêng.

```yaml
version: 1
projects:
  pcp-g0-fullpath-fixture:
    active_revision: null
    revisions:
      f2-c1-window-2026-10-12:
        status: draft
        source_commit: e59e6a2119c96a2dddb5b32f68ba178e0ac61140
        authority:
          - path: README.md
            authority: human_owner_protected
          - path: docs/F2-T01.md
            authority: human_owner_protected
          - path: .github/workflows/validation.yml
            authority: human_owner_protected
          - path: composer.json
            authority: human_owner_protected
          - path: composer.lock
            authority: human_owner_protected
          - path: web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php
            authority: mutable_execution
          - path: web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php
            authority: mutable_execution
          - path: web/modules/custom/pcp_f2_fixture/tests/src/Kernel/WindowOverlapServiceTest.php
            authority: mutable_execution
        references:
          goals: [{path: README.md}]
          non_goals: [{path: README.md}]
          requirements: [{path: docs/F2-T01.md}]
          architecture_constraints: [{path: README.md}]
          quality_policy:
            - {path: README.md}
            - {path: .github/workflows/validation.yml}
          security_policy:
            - {path: README.md}
            - {path: .github/workflows/validation.yml}
          budget_policy: [{path: docs/F2-T01.md}]
          roadmap_frame: [{path: docs/F2-T01.md}]
```

Lưu ý: `budget_policy` trong bản dự thảo hiện chỉ cho phép task fixture không phát sinh provider; **ngân sách một model job, quota/cost ceiling và chi phí tương đương hai nhánh cần định lượng & Owner chốt trước F2d-04C-3**. Không dùng trạng thái `draft` làm chứng cứ Runtime được `resolve_project_baseline`.

## 3. Gate còn lại (không gộp thành rollout)

1. **C1 protected source authority:** Owner phê duyệt chính xác proposal/revision + phạm vi eight-reference/authority metadata trước khi chạm file config baseline hoặc chuyển `approved`; không suy ra từ PR merge hay lời khen test xanh. `config/fullpath-candidate/projects.yml` vẫn `allow_commit/push/create_pr=false`.
2. **C2 protected infrastructure:** xác minh image OCI digest, UID/GID/mount/single writer, pre/post PostgreSQL schema/roles/25 tables indexes/grants, egress GitHub/provider, privileged token chỉ Executor, chặn host-global cancel/replay. F2 name-noncollision từ Owner WSL trước đó là snapshot, cần recheck ngay trước mutation, rollback chỉ tài nguyên F2 mới.
3. **C3 protected first flight:** một job direct-intake F2 mới, model/quota/time budget đã duyệt, exact CI + PM review, ghi thất bại/repair thật; khác với Planner→WorkOrder full PCP benchmark. Không khởi chạy khi C1/C2 chưa complete.

Không tạo dịch vụ/runner/orchestrator mới, không đọc/ghi Chợ Nhạc hoặc legacy PCP, không đụng fixture G0 cũ, không gọi model/Docker/DB. [#665](https://github.com/sonvhse06072/personal-coding-platform/issues/665) persistent CI runner isolation vẫn OPEN.
