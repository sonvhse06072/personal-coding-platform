# Đối chiếu phản biện Managed Agents và bài học vận hành PCP

- Ngày: 2026-10-30.
- Project: personal-coding-platform; tier T3; authority: evidence_history.
- Trạng thái: phân tích PM được Owner đồng ý lưu; không phải amendment kiến trúc, policy hoặc quyền thực thi.
- Source đã đối chiếu: N `85e415f1f53c8129056e2f04fb99a9b964b89609`.
- Liên quan: #835, #843, PR842/844/845; T1 hiện hành: [current-state](../current-state.md).
- Nguồn định hướng: [business strategy](../business-strategy.md), [roadmap](../roadmap.md), [constitution](../constitution.md), [operating model](../operating-model.md).
- Phân loại incident-learning: platform_operational_lesson; các thay đổi executable bên dưới vẫn là đề xuất chưa triển khai.

## Phạm vi và độ tin cậy

Owner cung cấp phản biện của Claude về Managed Agents/Outcomes và PCP. PM đối chiếu code tại N, tài liệu và báo cáo C843. Không suy từ metadata hoặc tài liệu mục tiêu rằng một capability đã được triển khai. PM không có truy cập trực tiếp WSL/DB của Owner; PHYSICAL/LIVE là bằng chứng operator báo cáo.

Hai nguồn Anthropic được nêu:
- https://www.anthropic.com/research/managed-agents
- https://platform.claude.com/docs/en/managed-agents/define-outcomes.md

Trong lần đối chiếu này, truy xuất web không thành công và HTTP fallback trả403. Mô tả session/harness/sandbox, grader/rubric và trạng thái phát hành của Anthropic chưa được PM xác minh độc lập. Không sử dụng bài bên thứ ba để khẳng định PCP chặt hơn hoặc tốt hơn Anthropic.

## Kết luận theo bằng chứng

| Chủ đề | Kết quả đối chiếu | Hệ quả |
| --- | --- | --- |
| Job và worker | Job/receipt/lease/counters bền không đồng nghĩa phải giữ container. PCP đã thay worker nhưng giữ job | Giữ same-job identity; đánh giá riêng khả năng thay workspace |
| Event log | storage.py có cp_job_events, append_event và events_after | Không nói PCP hoàn toàn thiếu log; log quan sát chưa chứng minh replay/reconstruction an toàn |
| Candidate sau invocation | worker loop lưu invocation_returned và usage trước; diff/verified_tree được lưu muộn hơn sau verification | Có khoảng trống phục hồi khi workspace mất trước durable candidate checkpoint |
| Rubric | WorkOrder có AcceptanceCriterion(id,description) và tiêu chí ID duy nhất | Schema chưa tự chứng minh mapping tiêu chí -> check -> bằng chứng/kết quả ở ordinary lane |
| Readiness/errors | Đã có readiness tổng hợp blockers và nhiều mã lỗi; một số lỗi cấu hình còn gộp nguyên nhân | Mở rộng mã nguyên nhân có ích, không xây hệ chẩn đoán song song |
| Authority | require_fresh kiểm bytes/digest/expiry; các vai trò dùng chung tài khoản GitHub | Integrity/custody khác với chứng minh chữ ký Owner; không tuyên bố phân tách danh tính bằng mật mã |
| Giá trị | Self-host/đa model là lựa chọn và khả năng; chưa chứng minh hiệu suất | Đo accepted outcomes và công Owner/operator thay vì số PR/tests |

Code nguồn tại N:
- [storage](../../../services/runtime/app/storage.py)
- [ordinary worker loop](../../../services/runtime/app/pcp_local_worker_loop.py)
- [recovery](../../../services/runtime/app/pcp_local_recovery.py)
- [readiness](../../../services/runtime/app/pcp_local_readiness.py)
- [WorkOrder schema](../../../services/runtime/app/work_order.py)

## Điều tiếp thu và giới hạn thiết kế

1. **Phục hồi cùng job, workspace thay được:** cân nhắc checkpoint candidate ngay sau invocation qua cơ chế hiện hữu. Patch đơn thuần chưa đủ: cần source identity, file mới/xóa, modes, binary, counters và trạng thái side effects. Workspace dựng lại không tự thừa hưởng verified status. Cần crash/rebuild tests và phép đo lợi ích trước khi mở rộng; không mặc định rewrite sang event sourcing.
2. **Guard theo bản chất:** credential/socket/escape/authorization tiếp tục fail-closed. Hợp đồng Git/CLI cần producer control và compatibility probes trên image thật. Git config và .codex có thể đổi hành vi thực thi, không phải metadata vô hại để bỏ qua. Metadata quan sát chỉ nên làm gate khi có lý do và kiểm chứng.
3. **Rubric nhỏ, tái sử dụng:** mục tiêu criterion ID -> command/check/review question -> result -> evidence -> assessor. Dùng cấu trúc hiện có trước; chưa thêm grader service. Deterministic test cũng có thể thiếu coverage hoặc kiểm sai yêu cầu; CI PASS không thay thế nghiệm thu.
4. **Authority có chữ ký:** chỉ hữu ích nếu private signing key ngoài quyền PM/operator, với scope/expiry/replay/revocation đúng. Nếu agent đọc được khóa, chữ ký không tạo ranh giới độc lập. Đây là đề xuất protected security cần thiết kế/review riêng, chưa phải điều kiện chặn closeout C.
5. **Hai mức độ chặt:** phân biệt platform/security repair và task routine, nhưng cả hai giữ chất lượng và trust boundary. Giới hạn số chỉ là estimate/headroom trừ circuit breaker/resource risk có căn cứ; không tái tạo owner-click gate do counter.
6. **Hiệu chuẩn review:** chưa có tỷ lệ false acceptance/rejection đã đo. Trước hết ghi phát hiện review, sửa đổi được xác nhận, escaped defect và nguồn ground truth; bất đồng giữa hai model không tự là nhãn đúng/sai.

## C843 thay đổi đánh giá như thế nào

Bằng chứng ordinary C đã đạt admission -> verification17+17 -> Draft844 -> exact-head CI, một model invocation, không recovery/replay; operator báo cáo0 yêu cầu tương tác Owner. Tuy nhiên chuẩn bị/giám sát operator vẫn đáng kể; Owner active minutes Unknown. Tại mốc ghi này finalization chưa xảy ra.

Không đồng nhất0 Owner prompts với0 operator work hoặc unattended success. Ghi riêng setup, runtime, review/CI waiting, Owner active effort, operator effort và recovery assistance. Missing data là Unknown. C là repeatability-only, không phải Drupal benchmark; #595 vẫn HOLD.

## Thứ tự đầu tư được PM khuyến nghị

Hoàn tất C với authority hiện hữu; sau đó ưu tiên task hữu ích trên fixture Drupal và phép so sánh Codex trực tiếp được chuẩn bị đúng protocol. Không tạo scope thực thi benchmark chỉ bằng tài liệu này.

Áp dụng bảng nghiệm thu theo tiêu chí và đo công operator bằng tooling hiện hữu. Chỉ mở candidate durability/workspace recovery hoặc guard repair khi có failure mode cụ thể, contract test và lợi ích đo được. Không triển khai đồng thời tất cả đề xuất Claude, không thêm swarm/service/hạ tầng chỉ vì tính năng hấp dẫn. Giữ incremental refactor và stop/go của roadmap; không đưa ETA/percent completion thiếu bằng chứng.

## Bài học PM: hash review C843

[Receipt6527787547](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6527787547) ghi finalization bị chặn trước mutation vì review5715171332 dùng hash sai. PM đã tái hiện độc lập trên Git repository tạm chỉ chứa ba file base/head lấy từ GitHub:

- Runtime convention: stripped `git diff <base> --binary`:5378 bytes, SHA256 `e7129de0abd18887749302f8b0f47d7f4a7990f38b12e043fccf364626a431e5`.
- Thêm `--full-index`:5576 bytes, SHA256 `ae80bf174bd41bbe115a49467c3cf405db9b9292fc564817da1a4e1996b2f9e5`.

Lỗi do PM tự đổi representation thành full blob IDs khi dựng hash, không phải task drift. Không sửa durable proof để hợp review; review phải sửa cho đúng producer convention. Guard đã ngăn một binding không khớp, nhưng công chờ/sửa là overhead PM cần tính vào phép đo.

Phòng ngừa đề xuất: lấy binding từ durable output và xác minh bằng đúng accepted producer/helper; không hash lại giao diện diff hoặc tự chọn abbreviation. Nếu chuẩn hóa serialization trong tương lai, phải version/migrate qua review và không đổi proof lịch sử. Chưa triển khai helper mới trong tài liệu này.

## Giới hạn và continuity

Tài liệu là record phân tích, không cấp authority, không đổi approved baseline, không chứng minh khả năng disaster recovery/benchmark/VPN. Trạng thái live và review thay thế phải đọc từ T1 và GitHub receipt mới nhất. Raw logs/manifests/backups giữ ở nguồn T4, không chép vào đây.
