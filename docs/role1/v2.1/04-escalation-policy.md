# 04 · Chuyển duyệt thủ công và câu hỏi cho Checker

> **Sửa v2.1:** GT-007/008/009 và VERIFY-A04 giữ FACT_UNCERTAIN; thêm dữ kiện có cấu trúc trong input.fact_verification. Đây là **extension fixture đề xuất**, chưa xác minh schema WP1/WP2 thực tế. Không tự coi thêm field vào JSON là engine đã hỗ trợ. Xem [hướng dẫn mapping](19-wp1-wp2-mapping-and-regression.md) trước khi import.

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Scope UC_MKT_11, BR-AI-05/10/13, BR-BUD; Sprint §§3–4, 13; taxonomy kế thừa bộ Role 1 cũ.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Ý nghĩa trong Sprint 1

Escalation là chuyển hồ sơ chưa thể tự duyệt sang **Checker đang được giao**, không phải thêm tầng phê duyệt. Business status vẫn PENDING_APPROVAL; round vẫn ACTIVE. Administrator có thể nhận cảnh báo kỹ thuật nếu chức năng thông báo đã triển khai, không trở thành người quyết định thứ hai.

Ba category `FACT_UNCERTAIN`, `POLICY_OUT_OF_SCOPE`, `AUTHORITY_EXCEEDED` kế thừa bộ Role 1 trước, không được nêu như enum bắt buộc trong hai nguồn mới. Giữ làm metadata giải thích, tuyệt đối không ép mọi lý do vào một category sai nghĩa.

## 2. Taxonomy và reason code đề xuất

| Category | Điều kiện | reason_code ví dụ | Người xử lý |
|---|---|---|---|
| FACT_UNCERTAIN | Fact không đủ tin cậy, bằng chứng mâu thuẫn | VLM_LOW_CONFIDENCE, OCR_FORM_CONFLICT, KPI_EVIDENCE_CONFLICT | Checker |
| POLICY_OUT_OF_SCOPE | Chưa có rule/phạm vi/cấu hình đủ để áp dụng | POLICY_SCOPE_MISSING, BUDGET_LIMIT_MISSING, CURRENCY_UNSUPPORTED | Checker; Admin hỗ trợ cấu hình |
| AUTHORITY_EXCEEDED | Fact và limit rõ, số tiền vượt phạm vi auto | BUDGET_LIMIT_EXCEEDED | Checker; không tự chuyển Manager |
| null | Lý do không thuộc ba nhóm trên | SCORE_NOT_ABOVE_THRESHOLD, HARD_VIOLATION, AUTO_DISABLED, RECOMMENDATION_MODE | Checker |
| null | Sự cố kỹ thuật, không kết luận fact của hồ sơ sai | AGENT_TIMEOUT, INVALID_AGENT_OUTPUT, MODEL_VERSION_MISSING | Checker; Admin/đội kỹ thuật xem lỗi |

`null` không có nghĩa không có lý do: `reason_codes[]` và giải thích phải có. Nếu dự án muốn category thứ tư/fifth, cần chốt taxonomy, không tự đổi enum trong backend/UI.

## 3. Nhiều lý do cùng lúc

Lưu toàn bộ reason/evidence. `[ĐỀ XUẤT]` chọn primary category FACT_UNCERTAIN → POLICY_OUT_OF_SCOPE → AUTHORITY_EXCEEDED vì không thể chắc về hạn mức khi fact còn mâu thuẫn; giữ secondary categories. Không xóa cảnh báo hard violation chỉ vì OCR cũng thấp. Lỗi kỹ thuật được gắn error code riêng. Không dùng primary category để bỏ qua các gate khác.

## 4. Câu hỏi có thể hành động

| Tình huống | Câu hỏi/đề nghị hiển thị |
|---|---|
| Form 50m, OCR 120m hoặc 180m, confidence 0.61 | “Form ghi 50.000.000 VND; ảnh A vùng E1 đọc được 120.000.000 hoặc 180.000.000 VND (0,61). Vui lòng đối chiếu ảnh gốc và xác nhận ngân sách được thẩm định. Nếu nội dung phải sửa, hãy từ chối kèm lý do để Maker gửi phiên bản mới.” |
| KPI xung đột | “Mục tiêu trong form là 1.200 lượt đăng ký, ảnh A ghi 12.000. Đâu là căn cứ cho quyết định tại vòng này? Nêu bằng chứng hoặc từ chối để Maker cập nhật.” |
| Chưa có policy ngành/kênh | “Chưa tìm thấy policy có hiệu lực bao phủ phạm vi X. Vui lòng xác định chính sách/căn cứ xử lý; không tự duyệt trong lúc chưa xác định.” |
| Budget 100.000.001 với L 100.000.000 | “Ngân sách vượt hạn mức tự động 1 VND của DEMO-LIMIT-V2. Vui lòng xem xét thủ công theo quyền được giao và ghi lý do nếu ghi đè khuyến nghị.” |
| Hard violation | “Policy demo đánh dấu vi phạm HV-DEMO-01 tại E1. Vui lòng kiểm tra ảnh gốc, rule và căn cứ trước khi approve/reject. Đây chưa phải quyết định từ chối.” |
| Timeout | “VLM chưa trả kết quả hợp lệ trong thời gian cấu hình. Hãy thẩm định ảnh gốc; run/correlation và lỗi được đính kèm. Không diễn giải timeout thành nội dung vi phạm.” |
| Score 70 | “Điểm 70 không vượt ngưỡng 70. Hãy xem điểm từng tiêu chí và khoảng trống trước khi quyết định.” |

Không thêm action “Yêu cầu chỉnh sửa”. Câu hỏi hỗ trợ thẩm định; trả lời không trực tiếp sửa snapshot. Maker chỉ sửa sau REJECTED và resubmit. Internal note nếu có là trao đổi, không phải quyết định, không thay reason.

## 5. Payload giao diện đề xuất

```json
{
  "route": "HUMAN_REVIEW_REQUIRED",
  "business_status": "PENDING_APPROVAL",
  "final_decision": null,
  "primary_category": "AUTHORITY_EXCEEDED",
  "reason_codes": ["BUDGET_LIMIT_EXCEEDED"],
  "assigned_checker_id": "DEMO-CHECKER-01",
  "evidence_refs": ["BUDGET-SNAPSHOT-DEMO-01"],
  "question": {
    "text": "Ngân sách 100.000.001 VND vượt hạn mức tự động 100.000.000 VND. Vui lòng thẩm định theo quyền được giao.",
    "answer_type": "REVIEW_COMMENT"
  },
  "priority": null,
  "sla_deadline": null
}
```

Đây là ví dụ rút gọn; production cần plan/version/round/run/correlation ID. Không có SLA 4h/8h mặc định trong nguồn. Priority/null chỉ là gợi ý schema; nếu dùng priority cần rule cụ thể. Không biến cảnh báo thành cam kết thời gian chưa được phê duyệt.

## 6. Chất lượng output

Có reason cụ thể + giá trị/ngưỡng + nguồn evidence + việc cần kiểm tra + người được giao. Không dùng câu “AI không chắc, hãy xem xét” làm toàn bộ giải thích. Dùng tiếng Việt cho UI, mã kỹ thuật trong API/audit. Không đặt nút chấp thuận trên thông báo thiếu kiểm tra quyền phía backend.

## 7. Điều kiện kết thúc route

Chỉ final decision của Checker hoặc System hợp lệ mới đóng round; mở màn hình/đọc thông báo/nhập ghi chú không đóng. Callback AI đến sau final decision chỉ thêm log kết quả trễ theo thiết kế, không chuyển trạng thái trở lại. Không auto-reject khi quá SLA hoặc hết timeout.

## Bổ sung v2.1: phân biệt A và B

| Tình huống | Kết luận nghiệp vụ |
|---|---|
| Fact có nhiều giá trị chưa có authoritative resolution | A: FACT_UNCERTAIN; lưu tất cả candidates và source |
| Extractor chưa xác minh đủ chuỗi cần đánh giá | A: FACT_UNCERTAIN; ghi phần đọc được và phần chưa biết |
| Fact đã được xác minh nhưng mapping policy thật sự thiếu | B: POLICY_OUT_OF_SCOPE; không gọi là uncertainty fact |
| Media result chung chung REVIEW_REQUIRED hoặc MEDIA_PASS | Chưa đủ để chọn A/B; cần fact evidence và trạng thái scope |

GT-007/008/009 là A, VERIFY-A04 kế thừa GT-007. GT-010/011 tiếp tục là B theo fixture cũ, không thay input/expected của hai ca đó. Mã R1-FIX-* là tham chiếu fixture, không phải ID policy runtime hiện có.
