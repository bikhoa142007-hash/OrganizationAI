# 08 · Nhãn kỳ vọng Verify và quy tắc so sánh

> **Sửa v2.1:** GT-007/008/009 và VERIFY-A04 giữ FACT_UNCERTAIN; thêm dữ kiện có cấu trúc trong input.fact_verification. Đây là **extension fixture đề xuất**, chưa xác minh schema WP1/WP2 thực tế. Không tự coi thêm field vào JSON là engine đã hỗ trợ. Xem [hướng dẫn mapping](19-wp1-wp2-mapping-and-regression.md) trước khi import.

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** BR-AI/BR-BUD và Sprint §4; nhãn tổng hợp do bộ tài liệu v2 định nghĩa, chưa sign-off.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Bảng expected đã khóa cho profile demo v2

| Case | Route | Business status | Final source | Category | Actual |
|---|---|---|---|---|---|
| VERIFY-A01 | AUTO_APPROVED | APPROVED | AI_AUTO_APPROVAL | null | NOT_RUN |
| VERIFY-A02 | AUTO_APPROVED | APPROVED | AI_AUTO_APPROVAL | null | NOT_RUN |
| VERIFY-A03 | AUTO_APPROVED | APPROVED | AI_AUTO_APPROVAL | null | NOT_RUN |
| VERIFY-A04 | HUMAN_REVIEW_REQUIRED | PENDING_APPROVAL | null | FACT_UNCERTAIN | NOT_RUN |
| VERIFY-A05 | HUMAN_REVIEW_REQUIRED | PENDING_APPROVAL | null | AUTHORITY_EXCEEDED | NOT_RUN |

**Phân bổ dự kiến:** 3 auto, 2 human. Đây là nội dung expected, không phải “đã chạy đạt 3 auto/2 human”. Kết quả từng trường đầy đủ tại [verify-expected-results.json](../../../tests/fixtures/ba/v2.1/verify-expected-results.json).

## 2. Giải thích từng ca

- A01: score 84, VLM .96, Media .94, Strategy .91, budget 50m≤100m, không lỗi/violation/conflict → đủ gate.
- A02: budget=100m đúng L, score 82.5 → gate dùng ≤, không dùng <.
- A03: score 70.1>70, các gate khác đạt → đủ gate. Test điểm đúng 70 nằm ở ST-07, không thay A03 bằng điểm 70.
- A04: kế thừa chính xác expected của GT-007 v2.1. Form 50m chưa được đối chiếu với hai phương án ảnh 120m/180m. fact_verification mô tả conflict, field, sources và verified_value null; category FACT_UNCERTAIN, outcome HUMAN_REVIEW_REQUIRED. Media result/confidence giữ nguyên và không còn là căn cứ phân loại duy nhất.
- A05: budget L+1, các output còn lại đủ → human/AUTHORITY_EXCEEDED với BUDGET_LIMIT_EXCEEDED. Assignment giữ DEMO-CHECKER-01; không chuyển Manager tự động.

## 3. So sánh nhiều lớp

**Route:** `AUTO_APPROVED` khác `APPROVED`; giá trị đầu là hành động engine, giá trị sau là trạng thái nghiệp vụ sau commit. **Human:** `HUMAN_REVIEW_REQUIRED` không phải final decision. **Source:** System auto có AI_AUTO_APPROVAL; Checker chỉ có source CHECKER sau khi người đó thực sự quyết định.

Nếu repo có enum khác, adapter mapping phải được ghi và review trước, không gọi mismatch là pass mà không giải thích. Snapshot policy/threshold không bị thay theo expected. Nếu field optional không thuộc contract đã chốt, không dùng nó để chặn test Must vô lý.

## 4. Quản trị expected

Role 1 giữ nhãn; thay đổi cần version + lý do + nguồn + ca ảnh hưởng. Đội triển khai không đổi nhãn để khớp bug. Nếu phát hiện expected sai nguồn thì Role 1 sửa có changelog rồi rerun; không cố giữ expected sai. File JSON `actual:null`, `execution_status:NOT_RUN` chỉ được dùng làm trạng thái khởi đầu; report thực thi lưu nơi khác.
