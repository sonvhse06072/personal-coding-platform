# Chợ Nhạc — Review chuẩn bị successor intake sau #466

Status: PM execution preparation / evidence. Không phải ProjectBaseline mới,
không cấp quyền release, không đưa file này vào WorkOrder.source_references.

## Nguồn đã đối chiếu

- PCP main tại lần đọc: `e7fb6d364f109a2ddee979d3a040367b03d87f73`.
- Chợ Nhạc main / approved r3 source:
  `aa8e68dd9aea6740de446151eb97615931de9b40`.
- Live #48/#49/#56/#57/#58/#50/#59 và #63 supervised replan contract;
  comments successor liên quan của #48/#49/#50 và các cập nhật replan #63.
- Chợ Nhạc AGENTS/PROJECT-CONTEXT; docs/27 phần DEC-031/032/033, đặc biệt
  section 17 phân công provenance/analytics; docs/26 safety/manifest/actor.
- PCP IntakeRequest/PM/WorkOrder schema và rollout evidence do owner cung cấp.
- Exact IDs, tuyến tính hóa dependencies, risk flags, budgets, concrete routes
  và reserved fixture identities đã được owner chốt trong handoff.

Đây là review contract, không phải bằng chứng bảy phần đã implement hoặc fixture
đã tồn tại. Chi tiết API/data/access/design được developer/planner đọc từ đúng
baseline references; không tự điền một thiết kế mới khi protected sources xung đột.

## 1. Rollout acceptance

Owner output v3 PASS không có observed_at. Không gán giờ chạy dựa trên timestamp
của lease. Trong lần chạy đó Runtime 1.0.106 healthy; executor 1.0.31/0 active;
active engineering count 0; historical GET trả 200 với 7 template routes; strict
WorkOrder/PM proposal validation trong process vẫn reject template replay.
Digest v3 `7d49d87afd3c165eff72bf3f97e3f36f9465465bd992879546db4e3a2b376f32`
không đổi trước/sau. Lease generation 9 vẫn thuộc blocked historical job
`c02defa348fc5b19a0bd021e2697571e`, preview absent; Chợ Nhạc branch/head sạch
và không thay đổi. Ba rejected plans vẫn generation-1 held, 7 pending, no jobs.

Acceptance evidence được ghi vào PCP #466 comment `5981132981`.
Không cần lặp build/restart/probe #466; quota chưa có snapshot mới trong output.

## 2. Một lỗi tham chiếu đã sửa

Body #56 trước review ghi "EE-0-04 owns provider integration" trong đoạn
completion. Điều này không khớp #50, #59 và DEC-033/docs27 section 17.
Đã sửa đúng đoạn đó: AP-MVP-03 (#50) sở hữu provider/projection; EE-0-04 (#59)
chỉ aggregate engagement. Không đổi product scope hoặc baseline source.

PROJECT-CONTEXT tại baseline còn nhãn cũ "engagement/provenance" cho #59.
Đó là mutable snapshot cũ, không ghi đè DEC-033 hoặc sửa authority snapshot r3;
planner phải dùng section 17 của docs/27 và #63 để phân công đúng.

## 3. Ma trận bảy WorkOrder

Tất cả parent_ticket phải đúng input ticket id, role developer, budget adaptive.
Không thêm operator/cleanup/WO thứ tám; không thực hiện PILOT-01 đã merge.
Mỗi WO sau phụ thuộc đúng WO liền trước. Đây là thứ tự execution, không phải
quyền tạo module dependency ngoài architecture.

| Issue | WorkOrder ID | risk | max_profile | changed-file working target |
|---|---|---|---|---|
| #48 | AP-MVP-01-artist-profile-data-curation | high | complex | 45 |
| #49 | AP-MVP-02-artist-profile-public-experience | high | complex | 55 |
| #56 | EE-0-01-event-backend-domain-api-access | critical | critical | 90 |
| #57 | EE-0-02-public-event-discovery-detail | high | complex | 55 |
| #58 | EE-0-03-studio-event-management-participation-program | high | complex | 65 |
| #50 | AP-MVP-03-generalized-verified-performance | high | complex | 45 |
| #59 | EE-0-04-event-engagement-analytics | critical | critical | 35 |

Giá trị model_calls=8, repair=2, wall=25 trong draft là estimates theo adaptive
Router/Runtime semantics; không reset counters và không coi là hard ceilings
độc lập. Không ép model/provider hoặc sửa reserve policy.

### Risk flags đã chốt

- WO1: schema_change, security_sensitive, data_migration, media_upload_security,
  privacy, cache_invalidation.
- WO2: public_surface, public_privacy, seo, accessibility, responsive_ui.
- WO3: schema_change, security_sensitive, authorization_change, external_api,
  privacy, csrf, state_machine, postgresql, fixture_safety.
- WO4: public_surface, privacy, external_links, accessibility, responsive_ui,
  api_integration.
- WO5: frontend_actions, state_machine, privacy, accessibility, private_preview.
- WO6: module_dependency, privacy, cache_invalidation, projection_integrity,
  public_surface.
- WO7: schema_change, security_sensitive, authorization_change, external_api,
  privacy, rate_limiting, analytics_integrity, public_surface.

Frontend consumes backend authority không tự đồng nghĩa authorization_change.
Nếu scope thật cần vượt planned protected boundary thì báo DecisionBoundary;
không xóa flag/hạ risk để ép PASS.

## 4. Acceptance không được mất khi planner diễn đạt lại

### #48 — dữ liệu/media

Slug 3–40/reserved/static precedence/uniqueness/edit-before-publish/freeze và
collision-safe migration published profiles. Identity/statement, 5 themes,
professional modes (BAND chỉ mô tả). Portfolio featured/type metadata invariants,
max 1 published featured YOUTUBE, IMAGE gallery grouping. Owner image authoring
qua Drupal Media thực sự dùng được, auth/CSRF/ownership/MIME/size/dimension/alt,
no SVG/path tùy ý; serializer/cache/current-email/lifecycle/privacy giữ nguyên.
Kernel/functional/migration và backward compatibility, không chỉ text tests.

### #49 — portfolio công khai

Canonical slug/legacy UUID redirect và artist-specific SSR SEO/OG. Media-first
Hero, Story, Featured Performance, Gallery, Professional Identity; 5 themes,
hide-empty, sparse/rich/two-art-direction fixtures. No autoplay/fake ratings/
reviews/history; CTA chỉ khi then-current action hợp lệ, không dead link hoặc
reopen recruitment. Viewports 360/390/430/768/1024/1440, a11y/performance/browser,
Artist Pride/Identity/Performance/Authenticity/Booking/Mobile/Empty/Uniqueness.

### #56 — Event backend

Independent Event/Participation/Program persistence; visibility tách lifecycle/
moderation; publish/slug lock/material revision/reconfirmation; no organizer
force-confirm; owner/participant/public UUID APIs và explicit filtering.
PUBLIC discovery, UNLISTED direct-only, PRIVATE/DRAFT 404; eligible terminal
archives, terminal immutability. Program same-Event attribution/no lyrics;
external ticket metadata/link only; completion qua EventManager khoảng 24h sau
ends_at. Stable status/errors, PostgreSQL persisted/API/access/CSRF/forgery tests,
independent review theo risk. Không analytics/projection trong WO này.

### #57 — public Event

Backend PUBLIC discovery với bounded filters/pagination; detail/lineup/program/
Profile links, QR canonical URL, external provider CTA. Không reconstruct access
ở frontend; direct UNLISTED/inaccessible 404/CANCELLED/COMPLETED presentation,
no active ticket CTA terminal; responsive/accessibility/loading/error/long copy.
Instrumentation hook không trở thành analytics storage hoặc fake metrics.

### #58 — Studio

Owner draft/create/edit/preview/readiness/slug lock; seven-section editor,
material-change warning/reconfirmation, participant self-confirm/decline;
Program CRUD/keyboard reorder, ticket metadata only. Private preview không thành
public route; terminal ordinary read-only. Canonical participation surface là
`/studio/event-participations/[participation]`, không phải nested Event route.
UI không force-publish/force-confirm hoặc tự tính authority; browser actor/access
scenarios và responsive/keyboard/focus phải được kiểm chứng.

### #50 — verified performance

Profile sở hữu generic provider/registry, boot được khi Event/Marketplace absent.
Chỉ EventParticipation live provider cho pilot. Không implement Marketplace
Booking provider, query Booking entities hoặc completed Booking contributions.
Eligibility COMPLETED + CONFIRMED/current + public-safe facts; loại cancelled,
stale/pending/declined/removed/private/ineligible. Newest-first deterministic,
max 6, provenance dedupe, cache transitions. Selected Performances là UI change,
hide-empty và bắt buộc frontend_quality + visual_quality.

### #59 — aggregate engagement

Chỉ EVENT_PAGE_VIEW/PROGRAM_VIEW/PROFILE_CLICK; target thuộc current public
lineup. Aggregate-only, no raw IP/full UA/fingerprint/account/cross-Event audience
identity cho counting; rate-limit trước increment. 204 accepted, 429 +
EVENT_ENGAGEMENT_RATE_LIMITED, bounded 422 + EVENT_ENGAGEMENT_TARGET_INVALID;
rejected không increment. Writes active viewable PUBLIC/UNLISTED only; reads
owner/moderator, không mặc nhiên artist. Non-blocking/no retry storm; Studio
real views/clicks, không unique attendees/conversion/revenue/ticket sales.

## 5. Verification và fixture ownership

WO1/WO3: required targeted_tests + static_analysis, không visual_routes.
WO2/WO4/WO5/WO6/WO7: required targeted_tests, static_analysis,
frontend_quality, visual_quality theo đúng thứ tự. Intermediate targeted_tests
là draft choice; validator phải xác minh command có trong configured project.

| WO | Concrete visual_routes |
|---|---|
| WO2 | /ngoc-linh; /anh-thu |
| WO4 | /events; /events/demo-acoustic-tay-ho |
| WO5 | /studio/events; /studio/events/5324429f-f5a3-51fb-90b7-0a1ceb9c1b48; /studio/events/5324429f-f5a3-51fb-90b7-0a1ceb9c1b48/preview; /studio/event-participations/6ae2f8a7-fc87-54fd-937e-8bf13fa49518 |
| WO6 | /ngoc-linh |
| WO7 | /events/demo-acoustic-tay-ho; /studio/events/5324429f-f5a3-51fb-90b7-0a1ceb9c1b48 |

Reserved verification identities, không phải current-data evidence:

- Ngọc Linh -> ngoc-linh; Anh Thư -> anh-thu.
- PUBLIC active Event 5324429f-f5a3-51fb-90b7-0a1ceb9c1b48 /
  demo-acoustic-tay-ho; participation 6ae2f8a7-fc87-54fd-937e-8bf13fa49518.
- PUBLIC COMPLETED Event d46354fc-9260-5338-81fd-04bf82a3743e /
  demo-jazz-hoan-kiem; participation 293b2bec-4199-5636-8121-89548b9723c0.

WO1 authorable fixture fields; WO2 hoàn thiện sparse/rich profile preview;
WO3 bounded Event/Participation/Program fixture producers qua domain services;
WO4/5 reuse; WO6 hoàn thiện COMPLETED eligible fixture; WO7 real aggregate data.
Mỗi visual WO phải chứng minh route render với actor/session đúng, không bypass
access chỉ để chụp ảnh. Không khẳng định fixture đã sẵn trước implementation.

Một seed path `cho_nhac_demo`, local/DDEV-only, manifest-owned, persist ownership
progress/partial failure, purge dependency-safe, không fixed password, không
portable enabled-module config/staging seed/frontend-only fake backend. docs/26
không authorize triển khai lại full marketplace workflow trong pilot.

## 6. Gate của một fresh intake

Request: canonical POST /v1/intake, baseline r3/source như trên,
planning_profile complex, execution_mode supervised, bounded_direct=false.
auto_run chỉ chi phối direct jobs theo schema; ở đây phải classify planning và
được initial supervision hold, không lấy auto_run=false làm pause substitute.

Trước model call: đọc fresh local health/active work/quota và preserved state;
validate request/draft proposal bằng deployed schemas, baseline references,
risk-profile floors, graph/verification capability và serialized size. Quota
false/missing/stale không được tự sửa thành available. Router giữ quyền chọn
provider/reserve; không bỏ ngưỡng chỉ để request chạy được.

Chỉ một submission; timeout/mất response có thể đã tạo plan và tiêu quota.
Giữ attempt marker/evidence và lấy lại exact plan, không POST lại để đoán.

Kết quả ready chưa được release. Review full objective/scope/AC/constraints,
provider/fixtures và exact generation-1 held/active, 7 pending, all job_id null,
ready set chỉ AP-MVP-01. Sau PM approval mới supported exact supersession mapping
và xử lý historical lease với side effects đã review, rồi release AP-MVP-01.
Không cancel/clear lease hoặc checkout Chợ Nhạc trong bước planning.
