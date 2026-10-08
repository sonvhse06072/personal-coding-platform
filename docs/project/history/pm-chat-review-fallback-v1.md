# PCP #562 — PM trong ChatGPT làm reviewer dự phòng (v1)

## Mục đích và ranh giới tin cậy

Khi không còn reviewer tự động hợp lệ, Owner có thể ủy quyền PM trong
đoạn chat hiện tại kiểm tra **exact PR diff/head** và ghi nhận review kỹ
thuật trên GitHub. Cơ chế nhận kết quả có tên riêng:
\`pm_chat_manual_review\`.

**Không được gọi cơ chế này là review độc lập khác provider hoặc reviewer
cùng provider có năng lực cao hơn.** Đây là đường review do Owner ủy quyền,
xác thực bằng GitHub identity, có bằng chứng và gate độc lập. GitHub review
COMMENTED từ cùng tài khoản tạo PR không được ngụy tạo thành GitHub APPROVE
của người khác. PM vẫn phải đánh giá cẩn trọng, không được suy ra PASS chỉ từ CI.

Áp dụng có chủ đích cho dự án \`chonhac\` trong
\`config/pm-bridge.yml\`, với \`pm_chat_review.enabled: true\` và
\`owner_author\` thuộc \`allowed_authors\`. Không có cấu hình → fail closed.

## Điều kiện trước khi ghi nhận review

1. Durable parent plan đang \`blocked\` đúng WorkOrder, job, PR, checkpoint
   và lý do \`pm_merge_ineligible:required_review_independence_not_satisfied\`.
   Không thay đổi job/workspace/counters hoặc checkpoint cũ.
2. Đọc lại source/head committed diff qua \`accepted_diff()\`; kiểm SHA-256
   đúng accepted diff trong Runtime. GitHub PR phải open/đúng head/base,
   CI exact-head phải green, và **không có merge gate khác** bị vi phạm.
3. Router được gọi **chỉ để staffing/probe**, không invoke model. Phải
   xác nhận \`no_eligible_cross_provider_now\` hoặc không có reviewer
   khác-provider đã đăng ký. Mọi \`staffing_unverifiable\`, lỗi network/auth,
   hoặc có model khác provider hợp lệ đều phải dừng. Nếu registry có
   *bất kỳ* cùng-provider reviewer tier cao hơn writer, v1 cũng fail closed
   (không khẳng định quota của họ là cạn chỉ từ registration).
4. PM Bridge control chỉ được gửi từ GitHub author ủy quyền, trên issue
   gốc của plan. Payload cần đúng exact plan/WO/job/source/head/branch/PR/
   checkpoint, không sử dụng lại control cũ.
5. Runtime gọi **DDEV Executor** bằng token nội bộ để lấy **GitHub PR review
   theo ID**, không tin review text do control tự khai. Review phải có
   \`state=COMMENTED\`, \`commit_id=expected_head\`, \`author=owner_author\`,
   đúng repository/PR/review ID và canonical GitHub URL.
6. Review body phải là marker \`<!-- coding-platform:pm-chat-review:v1 -->\`
   rồi đến **một** JSON hợp lệ, với \`schema_version=1\`, đầy đủ exact
   identity, \`verdict\`, \`summary\` có nội dung và \`findings\`. PASS
   chỉ có thể đi cùng mảng blocking findings rỗng.

## Hai control độc lập

Control được đưa vào comment issue gốc; PM Bridge tiếp nhận theo
\`<!-- coding-platform:pm-control:v1 -->\`, sau đó Guardian dùng
\`pm_bridge_poll_project_once\` để dispatch.

### 1. record_pm_chat_review

Ví dụ (phải thay ID bằng giá trị live, không copy mù):

\`\`\`json
{
  "schema_version": 1,
  "project_id": "chonhac",
  "action": "record_pm_chat_review",
  "plan_id": "<exact-plan-id>",
  "work_order_id": "<exact-workorder-id>",
  "job_id": "<exact-child-job-id>",
  "source_commit": "<40-hex-sha>",
  "expected_head": "<40-hex-sha>",
  "branch": "<exact-ai-branch>",
  "pr_number": 85,
  "checkpoint_id": 182,
  "checkpoint_key": "<exact-durable-checkpoint-key>",
  "review_id": 123456
}
\`\`\`

Control thực hiện preflight, fetch GitHub review, xác thực và ghi
\`cp_pm_chat_review_attestations\` append-only. Payload attestation lưu
diff hash, review-body SHA-256, author, canonical URL, verdict,
capacity result, control ID/body hash. **Chỉ ghi nhận, không merge.**
Thay đổi cùng khóa nhưng khác bằng chứng bị từ chối; không cho replay để
đổi review hoặc override failed proof.

### 2. release_pm_chat_review

Control thứ hai giữ **y nguyên** exact identity, thay action thành
\`release_pm_chat_review\`, bỏ \`review_id\` và thêm \`attestation_id\`
được Runtime tạo ở bước 1.

Runtime tiếp tục kiểm tra diff/head/CI, capacity, attestation nội bộ và
**đọc lại review trên GitHub để so body hash**. Với PASS hợp lệ và toàn bộ
merge gate gốc không còn blocker, checkpoint mới được chuyển thành
\`pm_chat_review_released → awaiting_merge\`. Không biến review thành
\`LateReviewProof\` hoặc sửa \`review_policy.independence_satisfied\`.

Sau đó, PM merge orchestrator đọc lại review/head/CI và đánh giá
\`PMChatReviewProof\` **cùng các gate cũ**: protected decisions, owner
permission, CI, verified PR head/source/branch/base, merge audit, replay,
merge uncertainty. Merge chỉ do PCP → DDEV Executor thực hiện sau audit.
Human Owner-protected gate vẫn phải được giải quyết bằng luồng Owner thật,
không dùng review fallback để bỏ qua.

## Trường hợp phải dừng

- Sai author, review chỉ APPROVED/DISMISSED/PENDING, body trống/edited,
  marker/schema/verdict/finding không hợp lệ.
- Khác project/plan/WO/PR/source/head/diff/checkpoint hoặc review đã
  được tái sử dụng.
- Có reviewer tự động đủ điều kiện hoặc Router staffing/credential
  không xác thực được.
- Human Owner-protected signal chưa được phê duyệt.
- GitHub review/CI/gate thay đổi sau khi attestation, hoặc merge audit
  cho thấy đã thử merge.

Tuyệt đối không tự tạo replacement job, reset counters, sửa trực tiếp
DB orchestration, giả mạo cross-provider independence hay gọi model
lặp lại khi chỉ thiếu reviewer.

## Giới hạn xác thực

GitHub author được xác thực qua PM Bridge và DDEV Executor. Đây là **bằng chứng
ủy quyền cấp tài khoản GitHub**, không phải chữ ký có thể chứng minh người
đang sử dụng ChatGPT khác với chủ tài khoản. Vì vậy phải giữ riêng trường
\`pm_chat_manual_review\`, lưu source/provenance, và không dùng GitHub review
COMMENTED làm bằng chứng độc lập nhà cung cấp. Việc Owner phê duyệt chính
sách trong cuộc trò chuyện phải được phản ánh bằng thay đổi cấu hình được
review/CI/merge và rollout qua Guardian.

## Live acceptance cho Chợ Nhạc GH-63 Step 7

- Exact plan: \`pm-b0748be27f8446a0813c2d1fe7d697fd\`;
  WorkOrder: \`EE-0-04-event-engagement-analytics\`;
  durable job: \`057f6acff17b501eae3a673cbb6bbe36\`.
- Chỉ sử dụng PR #85 nếu head vẫn đúng
  \`90c84d38692f781e1df91e85d253897d68458638\`, checkpoint #182
  đúng key, CI green, capacity hợp lệ.
- Technical review trước đó (review ID \`5455113475\`) là nhận xét dạng
  prose, **chưa đạt JSON protocol v1**; không tự convert hay coi nó là
  attestation. Nếu còn đúng head, PM có thể đăng một review COMMENTED
  mới với marker/JSON v1, rồi chạy hai control theo thứ tự.
- Không kết luận Step 7 completed chỉ từ control accepted hoặc kết quả
  record/release. Phải có GitHub merged PR, exact merge audit, dependency
  transition và plan checkpoint được đối chiếu.

