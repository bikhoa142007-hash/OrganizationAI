# 03 · Ma trận quyền, người duyệt và hạn mức

Bộ BA v2.1; cập nhật runtime Sprint 1 ngày 22/09/2026 theo yêu cầu audit RBAC.
Đây là ma trận quyền canonical cho HTTP demo. Căn cứ: AGENTS.md,
`docs/scope-phase-1.md`, `docs/sprint-1-deliverables.md` và decision contract.
Không phải xác nhận policy sản xuất đã được PO phê duyệt. Đường dẫn `role1`
được giữ để bảo toàn liên kết/provenance của gói BA.

## 1. Vai trò ứng dụng và trách nhiệm đội dự án

- MAKER: tạo, sửa và gửi kế hoạch của mình.
- CHECKER: người duyệt cuối cùng, chỉ với hồ sơ được giao và không do mình lập.
- ADMIN: actor quản trị demo, hiện chỉ xem cấu hình và chạy Verify; không có quyền đọc mọi hồ sơ.
- EVALUATOR: danh tính nội bộ đã đăng ký; không đăng nhập bằng X-Demo-Actor.
- DEMO-DUAL-01 có MAKER + CHECKER; vẫn cấm tự duyệt và không tự có assignment.

BA và Frontend Developer là trách nhiệm đội dự án, không phải runtime roles.
Checker đồng thời là Approver ở mô hình một cấp. Không có role Approver riêng,
read-only Auditor/Judge riêng, hoặc quyền actor-management trong Sprint 1.
Judge Demo Mode là nhãn môi trường, không phải một role có toàn quyền.

## 2. Ma trận quyền backend và UI

| Hành động / màn hình | Maker | Checker | Admin | Evaluator nội bộ |
|---|---|---|---|---|
| Landing, danh sách | Có; chỉ hồ sơ của mình | Có; chỉ hồ sơ được giao | Có; danh sách rỗng nếu không có quyền bổ sung | Không có UI |
| Chi tiết, ảnh riêng tư, lịch sử, observation | Hồ sơ của mình | Hồ sơ được giao | Không mặc định | Theo nhiệm vụ pipeline |
| Hồ sơ mới / tạo draft | Có | Chỉ nếu có thêm MAKER | Không | Không |
| Sửa draft / attachment | Của mình, DRAFT hoặc REJECTED | Không sửa hồ sơ người khác | Không | Không |
| Submit / resubmit | Của mình; dữ liệu hợp lệ | Không thay Maker | Không | Không |
| Review Queue / xem để quyết định | Không, trừ CHECKER được giao hồ sơ khác | Được giao, PENDING_APPROVAL + HUMAN_REVIEW_REQUIRED | Không | Không |
| Approve / reject | Không tự duyệt, kể cả có CHECKER | Được giao, khác Maker, round ACTIVE, đã có routing | Không | Không có quyết định người dùng |
| Escalate | Không có lệnh riêng | Xem câu hỏi escalation; từ chối có lý do để yêu cầu sửa | Không có lệnh riêng | Engine tạo routing và câu hỏi |
| Chạy/tiếp tục evaluation chưa commit | Hồ sơ của mình | Hồ sơ được giao | Không | Chạy bằng danh tính evaluator |
| Policy (chỉ đọc) | Có | Có | Có | Áp dụng snapshot |
| Sửa policy / limit | Không có API | Không có API | Chưa triển khai UI/API; cấu hình server | Không tự sửa |
| Audit | Theo quyền đọc hồ sơ | Theo quyền đọc hồ sơ | Không toàn cục | Append sự kiện hợp lệ |
| Verify | Chạy fixture tổng hợp riêng | Như Maker | Như Maker | Không endpoint demo |
| Actor management / đổi assignment sau submit | Không | Không | Chưa triển khai | Không |
| Sửa final decision / audit / version cũ | Không | Không | Không | Không |

Vai trò kép là hợp quyền theo từng hành động; quy tắc ownership, assignment và
cấm tự duyệt luôn ưu tiên. Checker đọc được draft được giao nhưng không thể quyết
định cho tới khi submit và pipeline đã route Human Review. Hidden controls chỉ hỗ
trợ sử dụng; API/workflow độc lập kiểm tra quyền.

## 3. Danh mục actor và assignment demo

| ID tổng hợp | Quyền | Phạm vi |
|---|---|---|
| DEMO-MAKER-01 | MAKER | Kế hoạch của mình |
| DEMO-CHECKER-01 | CHECKER | Assignment DEMO-DEPT-01 |
| DEMO-ADMIN-01 | ADMIN | Policy chỉ đọc và Verify; không tự có quyền hồ sơ |
| DEMO-DUAL-01 | MAKER, CHECKER | Tạo hồ sơ; queue rỗng khi chưa được giao |
| DEMO-EVALUATOR-01 | EVALUATOR | Chỉ nội bộ, bị HTTP demo-auth từ chối |

`src/backend/demo.py` sở hữu danh mục và assignment: DEMO-DEPT-01 →
DEMO-CHECKER-01, tiền tệ VND. Bộ phận hợp lệ là danh mục nhập liệu, không đồng nhất
với phạm vi hạn mức auto-approval. Giới hạn 100.000.000 VND là dữ liệu tổng hợp.
Không cho client đặt maker_id, role, status, decision actor hoặc audit metadata. Draft có Checker phải có cặp phòng ban/Checker hợp lệ; draft rỗng có thể bỏ cả hai. Quyền đọc áp dụng toàn hồ sơ, gồm lịch sử; demo không hỗ trợ đổi Checker.

## 4. Chuyển trạng thái

| Từ | Hành động / điều kiện | Đến |
|---|---|---|
| Chưa có | Maker lưu draft, có thể thiếu nội dung | DRAFT |
| DRAFT hoặc REJECTED | Owner submit hợp lệ, ảnh hợp lệ, Checker khác Maker | PENDING_APPROVAL / AI_PENDING / ACTIVE; version và round tiếp theo |
| AI_PENDING | Pipeline trả evidence; engine áp dụng snapshot | HUMAN_REVIEW_REQUIRED, vẫn PENDING_APPROVAL / ACTIVE |
| AI_PENDING | Chỉ khi snapshot bật auto và mọi gate đạt | APPROVED / AI_AUTO_APPROVED / CLOSED |
| HUMAN_REVIEW_REQUIRED | Assigned Checker approve | APPROVED / CLOSED |
| HUMAN_REVIEW_REQUIRED | Assigned Checker reject với lý do | REJECTED / CLOSED |
| APPROVED | Sửa / submit / quyết định mới | 409; không mở lại |

REJECTED cho phép sửa bản làm việc và tạo V2/Round 2; quyết định, version và
kết quả cũ không đổi. Cùng actor/key/input replay kết quả; key tái dùng với input
khác hoặc quyết định mới trên round đóng trả 409. Transaction và unique final slot
chặn quyết định trùng. Audit lưu actor, timestamp, old/new state, reason, hashes.

## 5. AI recommendation và quyết định cuối

Policy HTTP `DEMO-HTTP-2` tắt auto-approval. Mock PASS chỉ là evidence/khuyến nghị;
plan mới chờ Checker. Seed `DEMO-SEED-AUTO` riêng dùng `DEMO-HTTP-AUTO-1` bật auto
để minh họa chức năng Must Sprint 1. Mọi gate trong decision contract vẫn bắt buộc:
media PASS/confidence ≥ .85, score > 70/confidence ≥ .80, ngân sách trong hạn mức,
không hard violation/conflict/error, policy enabled và pending/active.

Không có AI auto-reject. Khi auto tắt, POLICY_ENABLED thất bại và category có thể
là POLICY_OUT_OF_SCOPE dù evidence đồng thời có factual uncertainty; xem toàn bộ
rule_checks và evidence, không suy luận mọi vấn đề từ primary category.

Reject cần lý do; quyết định trái recommendation cần override_reason. Verify dùng
DB in-memory riêng và fixture versioned, không có khả năng đóng live approval round.

## 6. HTTP và giới hạn demo

401: actor thiếu/không biết/nội bộ evaluator hoặc không ở APP_ENV=demo.
403: actor đã xác thực nhưng thiếu role, ownership, assignment hoặc tự duyệt.
404: đối tượng không tồn tại. 409: stale revision/policy hoặc transition không hợp lệ.
422: sai schema, protected field, nội dung/date/budget/Checker không hợp lệ.

Chọn actor trong header mô phỏng người dùng; ai truy cập demo cũng có thể chọn
actor khác. Đây không phải identity provider hay ranh giới bảo mật giữa người thật.
Không có quản lý tài khoản, thay Checker, policy editor hoặc global audit UI.
Production auth bị fail closed. Không thay CORS HTTPS, URL deployment hay storage.
