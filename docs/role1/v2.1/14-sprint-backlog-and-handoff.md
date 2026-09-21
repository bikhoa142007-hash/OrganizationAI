# 14 · Backlog Role 1 và bàn giao cho đội triển khai

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Sprint §§7–11; thứ tự đề mục kế thừa bộ Role 1 cũ, chưa xác minh lại phân công Role gốc.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Ranh giới trách nhiệm

Trong task này Role 1 tạo baseline nghiệp vụ, nhãn expected và tiêu chí nghiệm thu. Không chạy triển khai 72 giờ, không khẳng định đã hoàn thành WP1–WP6. Nội dung “dừng xác nhận trước triển khai” ở master prompt Sprint là hướng dẫn cho một yêu cầu triển khai riêng, không buộc dừng việc soạn tài liệu hiện tại.

Tên người/Role 2/Role 3 và ownership nguyên văn cần đối chiếu lại file phân công khi có. Các cột “đội triển khai/PO” dưới là nhóm trách nhiệm đề xuất, không phải danh sách nhân sự đã được giao chính thức.

## 2. Bàn giao theo WP

| WP | Việc Role 1 cung cấp | Việc đội triển khai làm | Điều kiện để Role 1 review |
|---|---|---|---|
| WP1 Audit repo, 0–4h | Scope Must/Should/Out, câu hỏi mở, validation | Chỉ đọc repo, báo stack/auth/DB/convention/test command/blocker | Có implementation plan và không bịa stack |
| WP2 Foundation, 4–10h | Data dictionary, seed, enums, snapshot rules | Migration/seed/contracts theo convention | Schema biểu diễn đúng 4 business states, 1 Checker |
| WP3 Core, 10–28h | ST-01..05, 13..15, ma trận quyền | CRUD/upload/submit/approve/reject/resubmit | V1/R1, khóa dữ liệu, reason, V2/history |
| WP4 AI, 28–40h | Agent contract, mock modes, threshold/evidence rules | VLM adapter, agents, rules engine, lỗi/timeout | Structured output hợp lệ, lỗi chuyển human |
| WP5 Decision/UI, 40–62h | Gate table, escalation questions, review content | Transaction auto/human, evidence UI, audit; in-app theo ưu tiên chốt | Không auto-reject; source/audit đúng; override có reason |
| WP6 Hardening, 62–72h | GT/Verify/test catalog/UAT/demo script | Integration/concurrency tests, README, reset seed | Actual evidence và defect đã xử lý |

Timeline là kế hoạch nguồn, không phải số giờ đã thực hiện trong task này. Giờ 68 đóng scope, sau đó sửa lỗi/seed/README/demo. SLA/domain admin mở rộng không đẩy vào Must chỉ vì còn trong Phase 1.

## 3. Backlog nghiệm thu nghiệp vụ

| ID | User story | Acceptance ngắn | Ưu tiên | Tài liệu |
|---|---|---|---|---|
| R1-01 | Maker lưu nháp khi chưa đủ dữ liệu | DRAFT; dữ liệu đã nhập đúng kiểu | Must | 01,02,06 |
| R1-02 | Maker gửi hồ sơ hợp lệ | Required/file/Checker, version/round/snapshot | Must | 01,02,12 |
| R1-03 | AI phân tích đúng version | Hash/evidence/metadata, output schema | Must | 12,16 |
| R1-04 | Engine quyết định xác định | >70, confidence, budget≤L và toàn bộ gate | Must | 02,05,08 |
| R1-05 | Checker hiểu vì sao cần mình | Ảnh, extraction, score, limit, reasons, history | Must | 04,16 |
| R1-06 | Checker ra quyết định | Backend quyền; reject/override reason | Must | 03,06 |
| R1-07 | Maker sửa sau từ chối | V2/R2/run mới, giữ V1 | Must | 01,06,12 |
| R1-08 | Truy vết và không quyết định trùng | Actor/source/snapshot/audit; idempotent | Must | 06,12,16 |
| R1-09 | Demo khi model local hỏng | MOCK công khai, 3 mock modes | Must | 07,11,17 |
| R1-10 | Theo dõi thời hạn/thông báo | SLA giờ; in-app nếu được chọn | Should | 01,15 |
| R1-11 | Sửa cấu hình qua màn hình | Version/effective time/snapshot giữ nguyên | Should | 02,12 |

## 4. Handoff checklist

- [ ] PO chốt OQ-01 confidence và OQ-05 recommendation/override.
- [ ] Đội triển khai ghi rõ schema, endpoint mapping, storage/hash canonicalization.
- [ ] Seed L/policy/demo accounts tách production; không copy cap theo chức danh.
- [ ] Dùng artifact dữ liệu như fixture; không hardcode route theo case ID/tên campaign.
- [ ] Xác nhận ảnh seed và mock status hiển thị công khai; model thật đánh giá riêng.
- [ ] Gửi migration/seed/build/lint/test commands thực tế; không điền lệnh giả trong README.
- [ ] Role 1 khóa expected version trước UAT; actual/evidence ghi riêng.
- [ ] Nếu thay requirement, tạo change entry có source/owner/ảnh hưởng thay vì sửa ngầm.

## 5. Định nghĩa hoàn thành hai cấp

**Bộ tài liệu:** các file đọc được, liên kết hợp lệ, traceability, dataset/expected nhất quán, vấn đề chưa chốt được gắn nhãn. **MVP Sprint:** build/lint/migration/seed/test, backend permission, version/audit, README và demo thực chạy theo DoD Sprint §10. Hoàn thành cấp tài liệu không suy ra cấp MVP.

## Theo dõi regression v2.1

Handoff gồm schema proposal, factual evidence và expected, không phải chỉ dẫn thay runtime schema tùy ý. WP owner cần map vào contract hiện có, ghi version/hash, capture normalized input và chạy FIX-01..12. Nếu unknown field bị bỏ, báo mapping chưa hoàn thành thay vì đổi expected sang POLICY_OUT_OF_SCOPE.

Kết quả kỳ vọng: bốn case FACT_UNCERTAIN có factual reasons rõ; controls GT-010/011 vẫn policy scope; GT-012/013 authority; auto cases vẫn AUTO_APPROVED. Dữ liệu expected không được engine đọc làm input quyết định.
