# Role 1 Sprint 1 v2.1 — sửa factual uncertainty

**Bản cập nhật từ ZIP người dùng cung cấp.** GT-007/008/009 và VERIFY-A04 giữ FACT_UNCERTAIN; bổ sung fact evidence có cấu trúc, field cụ thể, source values, unresolved status, rationale và rule/policy references.

## Đọc trước

1. [Changelog đầy đủ từng field](CHANGELOG-v2.1.md).
2. [Kết luận nghiệp vụ A/B](18-fact-uncertainty-correction.md).
3. [Mapping WP1/WP2 và regression](19-wp1-wp2-mapping-and-regression.md).
4. [Báo cáo kiểm artifact](validation-report.md).

**Chưa xác minh contract WP1/WP2 hoặc chạy engine thật.** Field input.fact_verification là extension fixture đề xuất; không bảo đảm app hiện tại tự đọc nó. Mapping/status được ghi rõ, không tạo schema giả rồi gọi là contract WP đã duyệt.

## Dataset hiện hành

- [15 GT](../../../tests/fixtures/role1/v2.1/ground-truth-cases.json), [5 Verify inputs](../../../tests/fixtures/role1/v2.1/verify-inputs.json), [Verify expected](../../../tests/fixtures/role1/v2.1/verify-expected-results.json).
- VERIFY-A04 được materialize từ GT-007; expected đồng nhất hoàn toàn.
- Runtime outcomes chỉ AUTO_APPROVED và HUMAN_REVIEW_REQUIRED. Không thêm deterministic rejection.
- Scores, confidence, limit, base policy và ảnh giữ nguyên; GT-009 sửa mock OCR thành partial response rõ ràng.
- [Diff machine-readable](../archive/v2.1/data/changes-v2.1.json); [schema proposal](../../../tests/fixtures/role1/v2.1/fact-verification.schema.json); [mapping status](../archive/v2.1/data/wp1-wp2-mapping-status.json).

## Tài liệu nghiệp vụ

- [01-scope-and-process.md](01-scope-and-process.md)
- [02-marketing-approval-policy.md](02-marketing-approval-policy.md)
- [03-authority-matrix.md](03-authority-matrix.md)
- [04-escalation-policy.md](04-escalation-policy.md)
- [05-ground-truth-cases.md](05-ground-truth-cases.md)
- [06-test-case-catalog.md](06-test-case-catalog.md)
- [07-verify-cases.md](07-verify-cases.md)
- [08-verify-expected-results.md](08-verify-expected-results.md)
- [09-measurement-plan.md](09-measurement-plan.md)
- [10-uat-report.md](10-uat-report.md)
- [11-submission-content.md](11-submission-content.md)
- [12-domain-data-dictionary.md](12-domain-data-dictionary.md)
- [13-source-traceability.md](13-source-traceability.md)
- [14-sprint-backlog-and-handoff.md](14-sprint-backlog-and-handoff.md)
- [15-open-decisions-and-change-log.md](15-open-decisions-and-change-log.md)
- [16-ai-contract-and-review-screen.md](16-ai-contract-and-review-screen.md)
- [17-demo-data-and-seed-guide.md](17-demo-data-and-seed-guide.md)
- [18-fact-uncertainty-correction.md](18-fact-uncertainty-correction.md)
- [19-wp1-wp2-mapping-and-regression.md](19-wp1-wp2-mapping-and-regression.md)

## Kiểm tra độc lập

Chạy python tools/validate_package.py trong môi trường Python 3. Validator chỉ đọc gói và in kết quả; không sửa app hoặc chạy model. Có kiểm ngược diff về baseline, hashes, source pointers/quotes, candidate normalization, incomplete OCR, parity A04 và negative mutation controls.

Nguồn Scope/Sprint giữ nguyên trong sources/. PDF đầu vào giữ bytes trong legacy/ và chỉ là tham khảo lịch sử, không đại diện sửa v2.1.
