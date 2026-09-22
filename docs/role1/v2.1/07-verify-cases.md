# 07 · Năm đầu vào Verify và hướng dẫn chạy

> **Sửa v2.1:** GT-007/008/009 và VERIFY-A04 giữ FACT_UNCERTAIN; thêm dữ kiện có cấu trúc trong input.fact_verification. Đây là **extension fixture đề xuất**, chưa xác minh schema WP1/WP2 thực tế. Không tự coi thêm field vào JSON là engine đã hỗ trợ. Xem [hướng dẫn mapping](19-wp1-wp2-mapping-and-regression.md) trước khi import.

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Số lượng/ý tưởng Verify kế thừa Role 1 cũ; gate và workflow cập nhật theo Sprint.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Phạm vi Verify

Verify là bộ 5 input nhỏ để kiểm nhất quán của decision engine; hai nguồn mới không yêu cầu xây một trang Verify riêng. Có thể chạy bằng test runner/backend harness hoặc giao diện có sẵn. Không mở rộng Must Sprint chỉ để tạo dashboard Verify.

| ID | Ca nguồn | Mục đích |
|---|---|---|
| VERIFY-A01 | GT-001 | Kế hoạch thông thường đủ gate |
| VERIFY-A02 | GT-002 | Ngân sách bằng đúng L |
| VERIFY-A03 | GT-004 | Điểm 70,1 vượt ngưỡng 70 |
| VERIFY-A04 | GT-007 | Form và hai giá trị OCR không thống nhất |
| VERIFY-A05 | GT-012 | Vượt L đúng 1 VND |

## 2. Dữ liệu đầu vào

[verify-inputs.json](../../../tests/fixtures/ba/v2.1/verify-inputs.json) có 5 input đầy đủ; [base-policy.json](../../../tests/fixtures/ba/v2.1/base-policy.json) là cấu hình demo tương ứng. Actual chưa có. Input giữ loại trường của file 12/16: context + plan_snapshot + policy_snapshot + agent_outputs + conflict/error metadata + input_hash.

VERIFY-A04 form budget 50.000.000 VND, ảnh chứa 120m và 180m, confidence 0.61; đây là uncertainty sau submit, không phải thiếu required field. VERIFY-A05 budget 100.000.001 VND vượt limit 100.000.000 VND; không liên quan chức danh.

## 3. Quy trình runner cần thực hiện

1. Đọc input và expected từ hai file độc lập; không đưa expected vào request production.
2. Tạo context/user/policy/limit trong môi trường demo hoặc map sang IDs thật, ghi mapping.
3. Tại layer contract, đưa agent outputs cố định qua cơ chế test injection; không dùng UI nhập output AI trong sản phẩm thật.
4. Gọi engine/service của app; nếu test E2E thì submit thật và chọn mock provider được cấu hình rõ.
5. Lưu response/DB state/audit, so khớp route, business state, final/source, category và required reason codes.
6. Human case kiểm câu hỏi/evidence bằng rubric; auto kiểm một final decision và actor System.
7. Ghi actual/result/timing/provider/build trong report mới; không ghi đè file expected.

Không có lệnh CLI hay URL cụ thể ở đây vì chưa có repo. Đội triển khai phải cung cấp command chạy thật trong README trước UAT. Không giả định `npm test`, framework hay database chưa được khảo sát.

## 4. Pass/fail

Route/state/source/category phải đúng; required reason codes là tập con của reason thực tế nhưng reason thêm phải có căn cứ, không được chứa kết luận sai. Không bắt câu hỏi khớp nguyên văn. 5/5 là gate đề xuất, **chưa phải kết quả đã đo**. Bộ Verify tái sử dụng ca nền, không dùng để tuyên bố đánh giá tổng quát ngoài mẫu.

## Materialization VERIFY-A04 v2.1

Input lấy từ GT-007 đã sửa; chỉ đổi plan_id, code, name, round_id, run_id, correlation_id và tính lại hash phụ thuộc. Attachment ID, evidence ID, issue ID được giữ để tham chiếu cùng asset, tránh đổi một đầu mà bỏ sót đầu kia. Toàn bộ expected A04 phải bằng expected GT-007 theo deep equality. Không copy tay từng field.

Actual A04 vẫn null/NOT_RUN. JSON đã kiểm đồng bộ, chưa có kết quả engine thực tế.
