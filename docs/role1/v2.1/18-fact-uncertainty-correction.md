# 18 · Phân tích và sửa factual uncertainty — v2.1

## Kết luận nghiệp vụ

| Case | Phương án | Lý do | Expected |
|---|---|---|---|
| GT-007 | A | Form 50m, ảnh có hai phương án 120m/180m; chưa chọn số chính thức | HUMAN_REVIEW_REQUIRED / FACT_UNCERTAIN |
| GT-008 | A | Form 1.200 lượt, ảnh 12.000; OCR tin cậy vẫn không giải quyết conflict | HUMAN_REVIEW_REQUIRED / FACT_UNCERTAIN |
| GT-009 | A | Mock partial OCR chưa xác minh toàn bộ dòng thông điệp | HUMAN_REVIEW_REQUIRED / FACT_UNCERTAIN |
| VERIFY-A04 | A, kế thừa GT-007 | Materialize cùng toàn bộ fact và expected | HUMAN_REVIEW_REQUIRED / FACT_UNCERTAIN |

Không chọn B vì không có căn cứ rằng facts đã xác minh đầy đủ rồi mới thiếu policy. GT-010/011 là nhóm policy-scope riêng, được giữ nguyên.

## Những gì đã sửa

- Mô tả fact bằng field cụ thể, typed issue, source pointer, candidates, evidence ID, unresolved status và rationale.
- GT-007/008 không xóa budget/KPI form, không làm form invalid để giả uncertainty.
- GT-009 không vừa cung cấp đầy đủ OCR text vừa nói chưa đọc được: dùng partial text và is_complete=false.
- Giữ confidence, score, budget, limit, policy và media.result. Không nâng confidence/ép PASS.
- Bỏ MEDIA_REVIEW_REQUIRED/media-confidence khỏi reason bắt buộc cho phân loại factual. Factual reasons/evidence vẫn phải đủ; engine có thêm lý do gate hợp lệ thì giữ.
- Giữ FACT_UNCERTAIN, final/source null và PENDING.
- Chuẩn hóa spelling runtime route về AUTO_APPROVED/HUMAN_REVIEW_REQUIRED trên dataset, Verify và mock declarations; không thêm enum.

## R1-FIX-CONFLICT-01 — local fixture rule

Conflict cần ít nhất hai source values khác nhau sau chuẩn hóa, pointers truy được, quote có trong evidence, verified_value null và chưa có resolution. Confidence cao chỉ phản ánh việc đọc, không lựa chọn nguồn chính thức. Số chuẩn hóa phải khớp source.

## R1-FIX-INCOMPLETE-01 — local fixture rule

Incomplete extraction cần OCR thể hiện thiếu, is_complete=false, phần chưa xác minh rõ, verified_value null. Execution SUCCEEDED chỉ nghĩa provider trả response hợp lệ, không nghĩa fact verified. Đây là mock response, không phải benchmark model thật.

Tham chiếu sản phẩm: Scope BR-AI-10; Sprint §4 về unresolved conflicts và §9.10 về VLM confidence; taxonomy FACT_UNCERTAIN trong Role 1. Không giả định ID R1-FIX-* có trong runtime.

## Ngăn sửa để xanh nhưng sai nghiệp vụ

Không đổi category vì engine hiện trả khác expected. Không dùng case_id/filename/expected làm oracle trong engine. Không xóa fact findings sau MEDIA_PASS. Không chấp nhận test chỉ so nhãn category mà bỏ field/source/rationale.

## Giới hạn xác nhận

Sprint mô tả WP1/WP2 như work packages, không cung cấp schema chuẩn hóa runtime. Extension proposal và trạng thái mapping đã tách rõ; chưa thể xác nhận tên field/enum WP1/WP2 khi chưa có contract.

Xem [diff từng field](CHANGELOG-v2.1.md) và [mapping/regression](19-wp1-wp2-mapping-and-regression.md).
