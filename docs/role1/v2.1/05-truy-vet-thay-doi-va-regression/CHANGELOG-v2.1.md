# 19 · Mapping WP1/WP2 và nghiệm thu sửa lỗi

## Trạng thái

- Semantic fixture: đã sửa theo A.
- Artifact validation: xem validation-report.md.
- Contract WP1/WP2 thật: **NOT_VERIFIED**.
- Actual engine regression: **NOT_RUN**.

Runtime catalog giữ nguyên AUTO_APPROVED/HUMAN_REVIEW_REQUIRED. Categories là metadata, không phải outcomes.

## Cần lấy từ repo

1. DTO/JSON Schema WP1/WP2: field, enum, additionalProperties.
2. Code map VLM/media/evidence sang deterministic input.
3. Predicate factual uncertainty và thứ tự phân loại.
4. Runtime reason/rule codes.
5. Normalized input/output thực của GT-007 đang lỗi.
6. Command/endpoint để tái hiện regression.

Target pointers trong mapping-status để null vì chưa có căn cứ. Không dùng schema proposal làm bằng chứng WP đã hỗ trợ.

## Quy trình tích hợp

1. Chụp raw fixture, input sau adapter và actual output.
2. Đọc uncertainty predicate thật; map các issue vào đúng field/enum đã có.
3. Xác minh source values/evidence refs/unresolved status còn nguyên sau mapping.
4. Nếu unknown fields bị bỏ hoặc thiếu khả năng diễn tả conflict, fail bước tích hợp rõ ràng. Không gửi chỉ MEDIA_PASS rồi coi đủ.
5. Nếu contract đã có field phù hợp, chỉnh mapping tối thiểu. Nếu contract không biểu diễn được nghiệp vụ, mở change có owner; không đổi threshold/outcome để né lỗi.
6. Gọi engine thật: so route/category, factual reasons/evidence, final/source null, business PENDING.
7. Chạy controls để tránh biến mọi human thành FACT_UNCERTAIN.
8. Ghi actual vào report mới; không ghi đè expected.

## Ma trận regression

| Ca | Input sau normalization | Kỳ vọng |
|---|---|---|
| GT-007 | 50m/120m/180m chưa chọn authoritative | Human + FACT_UNCERTAIN |
| GT-008 | 1200/12000 chưa resolved dù OCR .90 | Human + FACT_UNCERTAIN |
| GT-009 | Partial OCR, chưa xác minh text, .72 | Human + FACT_UNCERTAIN |
| VERIFY-A04 | Semantics bằng GT-007 sau identity normalization | Cùng expected |
| GT-001/002/004 | Gate đủ theo fixture gốc | AUTO_APPROVED |
| GT-010/011 | Policy-scope fixture riêng | Human + POLICY_OUT_OF_SCOPE |
| GT-012/013 | Budget-limit fixture riêng | Human + AUTHORITY_EXCEEDED |
| GT-014/015 | Hard-violation fixture riêng | Human, không thêm rejection outcome |

MEDIA_PASS cùng unresolved facts vẫn phải ra FACT_UNCERTAIN theo nghiệp vụ. Đây là acceptance, không khẳng định implementation đã hỗ trợ.

## Bằng chứng chạy app

Lưu build/commit, command/endpoint, WP schema version/hash, runtime policy version, request hash, normalized input, output, assertion, evidence, ngày giờ và tester. PASS chỉ khi engine thực đã chạy, không phải validator tự trả oracle.

## Kiểm tra artifact

~~~text
python tools/validate_package.py
~~~

Validator chỉ đọc gói, không gọi engine hay model. Nó kiểm file hashes, source quotes/pointers, conflict/partial-extraction, parity A04, JSON/catalog, snapshots và mutation controls. ARTIFACT_VALIDATED khác WP_COMPATIBLE và ENGINE_REGRESSION_PASSED.
