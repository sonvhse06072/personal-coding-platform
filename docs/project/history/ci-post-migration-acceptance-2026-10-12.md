# PCP CI — đối chiếu nghiệm thu hậu #666–#668 (2026-10-12)

**Authority:** Bằng chứng T3, thuộc [issue CI #665](https://github.com/sonvhse06072/personal-coding-platform/issues/665) và handoff [G0/F2 #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595). Chỉ kiểm tra GitHub source, workflow/CI/job logs. Không kiểm tra host WSL/Docker/Runtime, không thay đổi protected policy hoặc cho phép F2 khởi động.

## Reconcile và kiểm thử thật

- `main@cd9177572f7c81c2046835ac7aa52b66a7ab9a60` sau ba PR đã merge: [#666](https://github.com/sonvhse06072/personal-coding-platform/pull/666), [#667](https://github.com/sonvhse06072/personal-coding-platform/pull/667), [#668](https://github.com/sonvhse06072/personal-coding-platform/pull/668). Không PR PCP nào còn mở tại thời điểm audit. Đây là snapshot; không phải chứng thực ref vĩnh viễn.
- [#667 / CI 38228350120](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38228350120): 4/4 SUCCESS, ba service jobs thực sự in `PCP CI scope: docs_only`, bước setup-python/pip/service-pytest SKIPPED, không phải bài kiểm tra đã chạy. Root document authority PASS và **661 root tests PASS** trên `ubuntu-24.04`.
- [#668 / CI 38231355654](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38231355654): 4/4 SUCCESS, `scope: full`, chạy đủ 1546 Runtime tests (88 skipped), 273 Executor, 127 Router, 662 root tests trên GitHub-hosted. Hai checker được load từ base SHA trusted `main`; PR không còn tự quyết định scope bằng checker đã sửa trong cùng diff.
- [main / CI 38231645230](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38231645230): 4/4 SUCCESS, full regression trên `SonVH`. Kiểm chứng source/CI, **không** chứng minh F2/normal Runtime đã chạy.

## Đo latency: một số run, không suy diễn chi phí

Các mốc là GitHub Actions run `created_at` → `updated_at`, lấy từ API; log spans đo gần đúng thời gian của từng job sau khi bắt đầu có log. Sai số do queue, provisioning, kết thúc run và timestamp resolution. Cohort nhỏ, source/test counts giữa run khác nhau.

| Run | Loại | Run wall-clock | Tổng spans log 4 jobs | Test body thực tế |
| --- | --- | ---: | ---: | --- |
| [38220824480](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38220824480) | Trước migration, main self-hosted | ~150 s | ~105.7 s | Runtime 28.98 s, Executor 21.99 s, Router 3.58 s, root 7.41 s |
| [38228350120](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38228350120) | PR docs-only hosted | ~28 s | ~29.7 runner-s cộng dồn | Chỉ root 10.92 s, **không chạy service tests** |
| [38231355654](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38231355654) | PR full hosted | ~60 s | ~129.6 runner-s cộng dồn | Runtime 34.70 s, Executor 24.42 s, Router 7.68 s, root 10.87 s |
| [38231645230](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38231645230) | Sau migration, main self-hosted | ~226 s | Chưa dùng làm mẫu chi phí | Runtime 38.98 s |

**Kết luận hiệu suất:** full PR latency cải thiện chủ yếu nhờ 4 máy hosted chạy song song; docs-only giảm cài dependencies và service compute. Test-body thời gian không giảm tương ứng; main vẫn tuần tự, và một main push sau migration còn chậm hơn baseline. Không có dữ liệu billing/charged minutes, failure-rate dài hạn hoặc cost attribution; không khẳng định tiết kiệm USD hay ROI. Run-time GH-hosted và self-hosted không là cùng resource metric.

## Security review — functional PASS, bảo đảm self-hosted isolation còn thiếu

**Đã xác thực trong các run quan sát:** PR jobs đều có `RUNNER_ENVIRONMENT=github-hosted` PASS và log runner image `ubuntu-24.04`; workflow mặc định giới hạn `permissions: contents: read`, checkout `persist-credentials: false`, dùng synthetic test tokens, không truyền project/provider credentials. GitHub-hosted dùng VM tạm thời, không kế thừa workspace/Codex home của `SonVH` theo cấu hình được quan sát. Không khẳng định hosted VM hoàn toàn không có Docker socket, hoặc chứng minh tuyệt đối mọi secret bên ngoài workflow.

**HIGH — PR workflow self-modification chưa bị chặn tại runner scheduler:** Theo [GitHub docs về `pull_request`](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target), bản workflow được chạy lấy từ **PR merge commit**. PR sửa chính `.github/workflows/tests.yml` có thể đổi `runs-on` hoặc xóa bước `Check disposable PR runner`. Khi repo vẫn có persistent `SonVH` nhận `[self-hosted, linux, x64]` cho main, chưa có bằng chứng rằng runner registration/group/access policy độc lập với PR ngăn một untrusted PR chọn runner này. Việc trusted-base script #668 không bảo vệ được toàn bộ YAML. [GitHub security guidance](https://docs.github.com/en/actions/reference/security/secure-use) cảnh báo rõ nguy cơ này ngay cả ở private repositories. **Đây là đường tấn công có điều kiện, không phải sự cố đã khai thác. Không được claim P0 isolation được cưỡng chế server-side.**

**Required checks:** branch metadata trả `protected: false`; endpoint protection chi tiết trả `403 Resource not accessible by integration`, rulesets `403` do plan; không thể chứng minh bốn status contexts được GitHub enforce. PR docs-only vẫn có bốn check *chạy và SUCCESS*, nhưng không đồng nghĩa checks được branch protection yêu cầu trước merge.

**Biện pháp thực sự cần lớp ngoài PR-controlled YAML:** giới hạn runner ở tầng repository/org runner access, workflow-ref restriction nếu plan cho phép và được độc lập xác minh; hoặc vô hiệu hóa/unregister persistent runner khỏi repo rồi đổi trusted main CI sang hosted/isolated runner theo quyết định Owner riêng. Không đủ nếu chỉ thêm `if`, guard step hay policy ở cùng PR workflow. Không được tự thay host runner/credential hoặc biến đổi security policy từ audit này.

## Workflow legacy — giữ theo bằng chứng

- `guardian-static.yml`: PR path-scoped, hosted Ubuntu, pinned checkout/setup-python v7, bảo vệ script/config/Guardian workflow bằng test; còn hữu ích. Không archive.
- `pcp-guardian.yml`: chạy theo Owner issue-comment trigger trên default branch, self-hosted `SonVH`, checkout v4 và `issues: write`; giữ vì là kênh điều hành đã giới hạn, nhưng quyền host và upgrade action riêng còn cần đánh giá theo protected scope. Không chạy theo PR checkout mặc định.
- `g0d01-hosted-drupal-proof.yml`: path-scoped, fork check, hosted Drupal/DDEV proof, artifact retention 7 ngày; test có thể phục vụ audit fixture/G0; checkout v4 là debt riêng, không đủ bằng chứng để xóa.
- Root/Runtime/Router/Executor tests và các kiểm thử Guardian/G0/Antigravity vẫn bảo vệ regression/source boundary; tên cũ không chứng minh đã lỗi thời.

## F2d tiếp theo và điều kiện STOP

[PCP #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595) vẫn là canonical issue. GitHub source quan sát được `deploy/fullpath/compose.source-only.yml`: bốn service profile không mặc định + `entrypoint: ["/bin/false"]`, `project-baselines.yml` chưa có active revision, `models.yml`/`routing-policy.yml` rỗng; F2 vẫn PARKED. Fixture PR #4/#5 vẫn OPEN, hai branch `benchmark/*` cùng seed `39ef13c25b24c4a1b43a720ae53419f479996ed2`.

**Chưa có bằng chứng mới** cho repo/seed/approved ProjectBaseline độc lập, DB/role/volume/9-family zero-history *live*, image digest, single-writer/UID/mount, Router/Executor GitHub privileges, provider auth/domain-egress hoặc safe normal-engine boot + rollback. Không khởi động dịch vụ, không tạo tài nguyên F2, không retry Direct, không đụng legacy/host-global Codex, Chợ Nhạc hoặc G0D-T01 journal. Operational activation chỉ theo Owner protected approval mới sau independent attestation.

**PM disposition:** CI modernization source/functional fast path PASS, nhưng isolation security **CONDITIONAL / NOT FULLY VERIFIED**; không mở rộng CI hoặc sửa protected workflow chỉ để green hình thức. G0 1 code-valid reduced pair, 0 clean end-to-end pairs, investment HOLD/NOT GO, G1 chưa mở.
