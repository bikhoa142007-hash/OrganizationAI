# 02 · Chính sách đánh giá và tự động phê duyệt

> **Sửa v2.1:** GT-007/008/009 và VERIFY-A04 giữ FACT_UNCERTAIN; thêm dữ kiện có cấu trúc trong input.fact_verification. Đây là **extension fixture đề xuất**, chưa xác minh schema WP1/WP2 thực tế. Không tự coi thêm field vào JSON là engine đã hỗ trợ. Xem [hướng dẫn mapping](19-wp1-wp2-mapping-and-regression.md) trước khi import.

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Scope §9, BR-AI-01..16, BR-BUD-01..06, §§12.3–12.4; Sprint §§4–5, 9, 12.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Tình trạng chính sách

Scope phiên bản 1.1 tự ghi “Baseline cập nhật theo kiến trúc AI, chờ PO/Stakeholder xác nhận”. Bộ này bám baseline đó, không gắn nhãn đã phê duyệt sản xuất. Ngưỡng 70/0,85/0,80 có trong nguồn; hạn mức tiền cụ thể, content guideline, thời gian timeout và retry chưa được chốt trong nguồn.

## 2. Validation trước khi tạo vòng duyệt

| Trường | Lưu nháp | Gửi duyệt | Cách xử lý |
|---|---|---|---|
| name | Có thể thiếu | Bắt buộc | Trim; không chỉ khoảng trắng |
| maker_id, department_id | Hệ thống lấy | Phải xác định | Không tin actor gửi từ frontend |
| checker_id | Có thể chưa chọn | Bắt buộc | Active, account active, có quyền, khác Maker |
| objective, summary | Có thể thiếu | Bắt buộc | Nội dung không rỗng sau trim |
| start_date, end_date | Có thể thiếu | Bắt buộc | start ≤ end; không tự thêm quy tắc ngày phải ở tương lai |
| budget_vnd | Có thể thiếu | Bắt buộc | Số không âm; 0 hợp lệ, không nhầm với null |
| attachments | Có thể chưa có | Ít nhất 1 | Sprint ưu tiên ảnh hợp lệ, upload hoàn tất |
| target_audience | Tùy chọn | Tùy chọn | Thiếu có thể giảm chất lượng đánh giá, không chặn submit |
| channels | Tùy chọn | Tùy chọn | Không tự tạo danh mục bắt buộc từ ví dụ demo |
| kpi_expected | Tùy chọn | Tùy chọn | Không ép bắt buộc metric/target/deadline như bộ cũ |
| notes | Tùy chọn | Tùy chọn | Không thay lý do từ chối |

Không thêm trường `strategy_content` bắt buộc vì nguồn không có. Strategy sử dụng objective, summary và trường liên quan. Thiếu optional không tự động đồng nghĩa REVIEW: agent cần giải thích ảnh hưởng lên score/confidence/critical gaps.

Validation không qua → vẫn trạng thái trước submit, không tạo round/run. Đây là lỗi gửi form, không phải từ chối nghiệp vụ và không tính vào escalation recall của các hồ sơ đã gửi hợp lệ.

## 3. Media và bằng chứng

Local VLM chỉ cung cấp fact quan sát, OCR, vùng ảnh và confidence. Media Compliance trả đúng hai outcome `PASS` hoặc `REVIEW_REQUIRED`; lỗi execution được lưu riêng, không dùng outcome FAIL.

PASS cần kết quả hợp lệ, evidence truy ngược đúng attachment/hash/version, policy xác định và không có hard violation/conflict chưa xử lý. `PASS` của media riêng lẻ không đủ để auto-approve.

Các ví dụ “claim tuyệt đối”, “thông tin riêng tư trong creative”, “ngành chưa có guideline” là `[DEMO]` để xây fixture. Hai nguồn không cung cấp luật quảng cáo/brand guideline đầy đủ; không khẳng định một cụm từ hay ngành cụ thể luôn vi phạm pháp luật. Khi chưa có chính sách đã duyệt: đưa human, không tự kết luận hợp lệ hoặc tự reject.

## 4. Chấm khả thi

| criterion_id [đề xuất tên kỹ thuật] | Tiêu chí nguồn | Trọng số |
|---|---|---:|
| objective | Mục tiêu rõ và đo được | 15 |
| audience | Phù hợp đối tượng | 15 |
| channel | Phù hợp kênh | 15 |
| timeline | Khả thi thời gian | 15 |
| kpi | Chất lượng KPI/kết quả | 15 |
| budget_efficiency | Hiệu quả ngân sách | 15 |
| risk_control | Rủi ro và kiểm soát | 10 |

`total_score = Σ(criterion_score × weight) / 100`, từng score trong [0,100], tổng weight = 100. `[ĐỀ XUẤT]` tính Decimal, so sánh giá trị chưa làm tròn; chỉ làm tròn khi hiển thị. `70` không qua, `70.1` qua điều kiện điểm. Confidence [0,1] không phải điểm khả thi [0,100] và không được mô tả là xác suất thành công kinh doanh đã hiệu chuẩn.

Rubric đề xuất: 0 = không có bằng chứng/không đánh giá được; 25 = rất thiếu; 50 = có nội dung nhưng thiếu chứng cứ quan trọng; 75 = hợp lý, có căn cứ, còn khoảng trống nhỏ; 100 = đầy đủ, nhất quán với rubric. Đây không phải phương pháp đã hiệu chuẩn; cần Role 1/PO chấm mẫu cùng nhau. Với thiếu chứng cứ phải ghi assumption/gap thay vì dựng số liệu thị trường.

`critical_gaps` bắt buộc có trong output. `[ĐỀ XUẤT]` gap trọng yếu chưa xử lý được coi là unresolved conflict/gap chặn auto; nguồn chưa quy định mapping máy đọc được, cần OQ-09.

## 5. Ngân sách

- Dùng `budget_vnd` của version và applicable limit còn hiệu lực của round; so sánh `budget <= limit` bằng rule xác định.
- Bằng hạn mức đạt; lớn hơn 1 VND không đạt. Không có cấu hình, trùng cấu hình chưa phân giải, currency khác VND → human.
- Không tự đổi tiền, không tổng hợp chi tiêu thực tế, không trừ budget ledger kế toán trong Sprint.
- “Phần còn lại” nếu hiển thị là `limit - budget` của phép so sánh này, không phải số dư ngân sách doanh nghiệp.
- Chỉ một limit demo L = 100.000.000 VND trong seed v2. Đây là giá trị thử biên, không phải hạn mức đã được công ty phê duyệt. Không còn cap 100m/Lead 300m/Manager 1b song song.

## 6. Gate quyết định

| Gate | Điều kiện auto | Nếu không đạt | Nguồn |
|---|---|---|---|
| CTX | PENDING_APPROVAL, đúng version/round, round ACTIVE, chưa final decision | Nếu stale/đã quyết định: bỏ kết quả cũ, ghi audit; không mở lại hồ sơ | BR-AI-11, Sprint §4 |
| POLICY | Có snapshot hợp lệ, auto enabled, mode cho phép auto | Human nếu round vẫn active | Scope §12.3, BR-AI-14 |
| OUTPUT | Đủ output hợp lệ, evidence/model version, không lỗi/timeout | Human; giữ failure metadata | BR-AI-03/10 |
| MEDIA | PASS, hard_violation_count = 0 | Human | BR-AI-05/08 |
| VLM | vlm_confidence ≥ 0.85 | Human | BR-AI-09, Sprint §9/§12 |
| MEDIA_CONF | media_confidence ≥ 0.85 | Human trong profile v2 đề xuất | Sprint §4; khác với Scope, OQ-01 |
| SCORE | total_score > 70 | Human | BR-AI-07 |
| STRATEGY_CONF | strategy_confidence ≥ 0.80 | Human | BR-AI-09 |
| BUDGET | VND, limit xác định, budget ≤ limit | Human | BR-BUD-01..06 |
| CONFLICT | unresolved_conflict_count = 0 | Human | Sprint §4 |

**Khác biệt cần xác nhận OQ-01:** Scope gọi confidence của VLM; Sprint §4 gọi media_confidence; Sprint §12 quay lại VLM. Không coi hai field đồng nghĩa. `[ĐỀ XUẤT]` profile demo v2 kiểm tra cả hai ≥0.85, lưu riêng; chưa phải chốt yêu cầu sản xuất. Các ca nền tránh trường hợp chỉ một confidence đạt; ca khác biệt có expected theo profile đề xuất và nhãn cần PO chốt.

```text
evaluate(round, outputs, snapshot):
  nếu round không còn hiện hành/ACTIVE hoặc plan không PENDING:
      bỏ kết quả trễ; không tạo decision/human queue mới
  kiểm tra dữ liệu output, policy và context
  thu tất cả lý do không đạt (không chỉ lý do đầu tiên)
  nếu Controlled Auto-Approval + auto enabled + mọi gate đều đạt:
      commit APPROVED đúng một lần, source AI_AUTO_APPROVAL
  còn lại:
      giữ PENDING_APPROVAL; route Checker; không tạo final decision
```

## 7. Chế độ và đổi cấu hình

Shadow: chạy đánh giá và giữ audit, không hiển thị khuyến nghị gây tác động Checker; vẫn cần người quyết định. Recommendation: hiển thị khuyến nghị, Checker quyết định. Controlled Auto-Approval: được tự duyệt nếu toàn bộ gate đạt. Tắt auto không tắt pipeline.

Vòng đã bắt đầu dùng snapshot, thay cấu hình áp dụng vòng mới. Nguồn diễn đạt thời điểm khóa ở submit/round và chỗ khác ở run; đề xuất thống nhất submit, xem OQ-02. Tắt auto giữa một run có vô hiệu ngay quyền commit hay không cần chốt OQ-03; không tự mô tả nút Stop/Undo là đã tồn tại.

## 8. Quyết định con người

Checker hợp lệ, đúng người được giao, khác Maker, round active và stage cho phép. Phê duyệt có thể có ghi chú; từ chối phải nhập reason không trắng; override khác khuyến nghị phải có lý do riêng hoặc mapping reason đã được thống nhất. Không sửa output AI. Hard violation luôn chặn auto nhưng không tự biến thành quyền từ chối/duyệt cấp trên; phạm vi Checker được phép bỏ qua loại vi phạm nào chưa được quy định, OQ-06.

## 9. Các rule cũ bị loại khỏi bản này

`HARD_REJECTED`, `MEDIA=FAIL`, tự tăng cấp theo chức danh, limit 300m/1b mặc định, KPI bắt buộc gửi, SLA escalation 4h/8h cố định, sửa/undo final decision. Tất cả phải có change request và phê duyệt phạm vi nếu muốn đưa trở lại.

## Bổ sung v2.1: bằng chứng fact không thay bằng nhãn media

Sự diễn giải MEDIA_PASS của adapter không tự chứng minh budget_vnd, kpi_expected hoặc nội dung OCR đã được xác minh. Với ba ca sửa, bằng chứng nghiệp vụ vẫn chưa thống nhất/đầy đủ. Giữ expected FACT_UNCERTAIN theo taxonomy hiện có.

Không thay base-policy.json, ngưỡng, trọng số, hạn mức hay policy snapshot để làm test đạt. Không nâng media confidence lên 0,99, không ép PASS khi thiếu căn cứ, không suy thiếu policy từ việc chưa đọc được chữ. Extension mới chỉ mô tả dữ kiện; tên trường/enum đi vào app phải theo WP1/WP2 thật.

Nếu app hiện chưa có cách biểu diễn evidence conflict/partial extraction, đó là khoảng trống contract cần xử lý hoặc xác nhận lại từ nguồn; không âm thầm thay expected thành POLICY_OUT_OF_SCOPE.
