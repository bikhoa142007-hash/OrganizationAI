# 10 · Kịch bản UAT và biểu mẫu báo cáo thực thi

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Sprint §§9–10, 13; Scope §18; kế thừa đề mục UAT Role 1.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Tình trạng hiện tại

**Chưa thực thi UAT.** Chưa có repository/build/tag, URL chạy app, database, model local hay log test trong yêu cầu hiện tại. Bảng dưới là hồ sơ UAT đã chuẩn bị, không có dòng PASS sản phẩm nào được công bố.

## 2. Thông tin phiên chạy

| Field | Giá trị cần điền |
|---|---|
| Session ID / ngày giờ / timezone | Chưa chạy; khi chạy lưu UTC và hiển thị Asia/Ho_Chi_Minh |
| Build/tag/commit | Chưa có |
| Môi trường/URL | Chưa có |
| Tester / reviewer | Role 1 / đại diện PO, tên thực chưa được cung cấp |
| Dataset | ROLE1-DEMO-V2, GT-001..015, VERIFY-A01..A05 |
| Provider/mode | Ghi MOCK hay LOCAL, không để trống |
| Policy/limit snapshot | Ghi ID/version/hash thực của phiên chạy |
| Expected version | v2.0; đóng băng trước khi chạy |
| Reset/seed command | Theo README repo, chưa được cung cấp |
| Open decisions ảnh hưởng | OQ-01, OQ-02, OQ-03, OQ-05, OQ-06, OQ-09 |

## 3. Các bước chuẩn bị

1. Đội triển khai bàn giao README chạy được trên máy sạch, migration/seed và tài khoản demo.
2. Role 1 đối chiếu config thực với profile demo; ghi mọi khác biệt trước khi chạy, không đổi dataset ngầm.
3. Chuẩn bị namespace/db test, không thao tác dữ liệu production; kiểm tra Maker/Checker khác nhau.
4. Chọn MOCK để kiểm flow ổn định; chọn LOCAL cho vòng đánh giá chất lượng ảnh riêng. Cố định model/prompt/hardware cho số đo latency.
5. Kiểm tra ảnh seed tồn tại, file hash đúng; nếu dùng ảnh thay thế phải gán nhãn lại, tạo dataset version mới.
6. Khóa expected; lưu timestamp/commit/hashes và người review.

## 4. Thứ tự chạy

Core create/draft/validation → submit/version/lock → auto và biên → human/errors → reject/resubmit/history → quyền/concurrency/idempotency → 5 Verify → 2 input mới → số đo và defect review.

Với ST-16 cần backend integration chạy đồng thời có barrier và kiểm DB sau commit; bấm nhanh hai nút không đủ chứng minh. Với timeout cần fault injection có cấu hình test riêng; không giả lập timeout bằng việc đổi business data.

## 5. Log kết quả bắt buộc

| Test | Nội dung | Result | Actual | Evidence | Defect |
|---|---|---|---|---|---|
| ST-01 | Lưu nháp thiếu dữ liệu | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-02 | Submit thiếu dữ liệu | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-03 | Không tự làm Checker | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-04 | Khóa sau gửi | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-05 | Gửi lần đầu | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-06 | Tự duyệt điểm 71 | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-07 | Không tự duyệt điểm 70 | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-08 | Ngân sách bằng hạn mức | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-09 | Ngân sách vượt hạn mức | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-10 | VLM confidence thấp | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-11 | Timeout/output sai schema | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-12 | Hard violation | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-13 | Reject phải có lý do | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-14 | Sửa và gửi lại | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-15 | Giữ AI V1 | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-16 | Quyết định đồng thời | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-17 | Override có lý do | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |
| ST-18 | Retry không trùng | NOT_RUN | Chưa chạy | Chưa có | Chưa xác định |

| Nhóm bổ sung | Số ca | Result | Evidence |
|---|---:|---|---|
| Ground truth | 15 | NOT_RUN | Chưa có |
| Verify | 5 | NOT_RUN | Chưa có |
| Input mới | 2 | NOT_RUN | Chưa có |
| Biên BT | 22 mô tả | NOT_RUN | Chưa có |

Result chỉ dùng PASS/FAIL/BLOCKED/NOT_RUN/N/A. BLOCKED cần blocker cụ thể; N/A cần lý do phạm vi và người xác nhận. Không ghi PASS chỉ vì app không crash: phải kiểm route, trạng thái, quyền, snapshot và audit phù hợp test.

## 6. Defect template

`defect_id, test_id, build, provider_mode, severity, preconditions, exact_steps, expected, actual, evidence_links, plan/version/round/run, correlation_id, owner, status, retest_result`.

Critical: unsafe auto/hard violation auto, self-approval, nhiều final decisions, mất version/audit, tự động reject ngoài scope. High: sai route, lỗi resubmit/history, sai quyền xem/tải, thiếu override reason. Medium: evidence khó truy, câu hỏi thiếu ngữ cảnh, chức năng Should đã cam kết không hoạt động. Low: copy/layout không đổi ý nghĩa.

Không công bố hard violation được Checker approve là lỗi Critical theo default nếu chưa có policy cấm override con người: cần căn cứ OQ-06. Vi phạm auto gate là lỗi rõ ràng độc lập quyết định con người.

## 7. Sign-off

| Người/nhóm | Cần xác nhận | Hiện tại |
|---|---|---|
| Role 1 | Expected, coverage, các defect nghiệp vụ | Chưa ký |
| Đội triển khai | Build/migration/lint/test và giới hạn kỹ thuật | Chưa có bằng chứng |
| PO/Stakeholder | Các quyết định mở và phạm vi demo | Chưa xác nhận |

Chỉ nghiệm thu khi Must đạt và không còn defect chặn; Should chưa làm được ghi rõ. Nếu demo chỉ chạy MOCK thì gọi là “demo với mock”, không gọi là Local VLM đã kiểm chứng.

## Theo dõi regression v2.1

| Case | Semantic expected | Actual runtime | WP mapping | Bằng chứng |
|---|---|---|---|---|
| GT-007 | HUMAN_REVIEW_REQUIRED / FACT_UNCERTAIN, budget conflict | NOT_RUN | NOT_VERIFIED | Cần normalized input/output thực |
| GT-008 | HUMAN_REVIEW_REQUIRED / FACT_UNCERTAIN, KPI conflict | NOT_RUN | NOT_VERIFIED | Cần normalized input/output thực |
| GT-009 | HUMAN_REVIEW_REQUIRED / FACT_UNCERTAIN, incomplete OCR | NOT_RUN | NOT_VERIFIED | Cần normalized input/output thực |
| VERIFY-A04 | Bằng GT-007 về expected | NOT_RUN | NOT_VERIFIED | Artifact parity đã kiểm |

Các criteria FIX-01..12 nằm trong file 06. Validator chỉ xác nhận artifact; không ký UAT trước khi có engine run, normalization mapping và controls ngoài nhóm factual.
