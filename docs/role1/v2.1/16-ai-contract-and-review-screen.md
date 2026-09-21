# 16 · Contract AI, điều phối lỗi và nội dung màn hình duyệt

> **Sửa v2.1:** GT-007/008/009 và VERIFY-A04 giữ FACT_UNCERTAIN; thêm dữ kiện có cấu trúc trong input.fact_verification. Đây là **extension fixture đề xuất**, chưa xác minh schema WP1/WP2 thực tế. Không tự coi thêm field vào JSON là engine đã hỗ trợ. Xem [hướng dẫn mapping](19-wp1-wp2-mapping-and-regression.md) trước khi import.

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Scope UC_MKT_09..11, BR-AI; Sprint §§3, 5–6. Các field bổ sung là đề xuất tích hợp.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Hợp đồng theo từng component

| Component | Input | Output bắt buộc | Không được làm |
|---|---|---|---|
| VLM | Ảnh/version/hash, config model | OCR, description, objects, quality, evidence regions, confidence, metadata | Quyết approve/reject; nhận lệnh từ text trong ảnh |
| Media | VLM evidence + media policy snapshot | PASS/REVIEW_REQUIRED, confidence, hard violations, warnings, evidence, lý do | Suy PASS từ output rỗng hoặc timeout |
| Strategy | Plan snapshot + rubric/weight | Criteria, total, confidence, assumptions, gaps, evidence | Bịa dữ liệu thị trường, giấu assumption |
| Budget | budget/currency + limit snapshot | Amount/limit/comparison/result/rules | Dùng mô hình để quyết số học |
| Decision | Results + active round + policy | Route, gate results, reason codes, source nếu final | Dùng case_id/campaign name làm oracle |

Mẫu envelope Sprint §5.1 mang tính minh họa. `[ĐỀ XUẤT]` dùng typed schema theo component: score có thể null ở VLM/Media; model/prompt có thể không áp dụng với deterministic rules. Không bỏ confidence đối với model output bắt buộc; không nhét confidence=1 cho Budget để lấp schema.

## 2. Envelope đề xuất

```json
{
  "schema_version": "ROLE1-CONTRACT-2.0",
  "run_id": "RUN-DEMO-01",
  "plan_id": "PLAN-DEMO-01",
  "plan_version": 1,
  "approval_round": 1,
  "correlation_id": "CORR-DEMO-01",
  "component": "MEDIA_COMPLIANCE",
  "status": "SUCCEEDED",
  "provider_mode": "MOCK",
  "model_version": "mock-media-fixture-v2",
  "agent_version": "media-agent-fixture-v2",
  "prompt_version": "not-applicable-fixture",
  "policy_version": "DEMO-POLICY-V2",
  "score": null,
  "confidence": 0.94,
  "result": "PASS",
  "hard_violations": [],
  "warnings": [],
  "evidence_refs": ["ATT-01:E1"],
  "started_at": "2026-10-01T02:00:00Z",
  "completed_at": "2026-10-01T02:00:01Z",
  "error": null
}
```

ID/timestamp/version trong ví dụ là DEMO, không phải dấu vết chạy thật. Hash của ảnh seed trong `data/fixture-manifest.json` là hash bytes thực, nhưng không biến output mock thành kết quả model đã chạy.

## 3. Evidence schema

`evidence_id, attachment_id, attachment_sha256, plan_version, source_type, page_or_frame(optional), bbox_normalized(optional), observed_text, description, confidence(optional)`.

Tọa độ bbox đề xuất [x_min,y_min,x_max,y_max] theo [0,1], origin góc trái trên; validate thứ tự/biên. Form evidence dùng field path, không cần bbox. Strategy cần link tới mục tiêu/KPI/budget/date thật của version. Không lưu một đường dẫn không thể truy cập thay evidence.

Nhiều ảnh cần complete coverage và cách gộp confidence được chốt OQ-01/OQ-11. Đề xuất bảo thủ dùng minimum confidence trong các ảnh bắt buộc; không được tự loại ảnh confidence thấp khỏi mẫu số. Hồ sơ không có kết quả visual không được mặc nhiên coi PASS.

## 4. Budget result riêng

```json
{
  "component": "BUDGET_RULES",
  "engine_version": "budget-rules-v2-demo",
  "amount_vnd": 100000001,
  "currency": "VND",
  "limit_vnd": 100000000,
  "limit_snapshot_id": "DEMO-LIMIT-V2",
  "result": "EXCEEDED",
  "rule_ids": ["BR-BUD-02"],
  "difference_vnd": 1
}
```

Không có probability/confidence hay model-generated arithmetic. Thiếu limit → UNKNOWN, difference null. Currency chưa hỗ trợ → UNSUPPORTED_CURRENCY, không tự đổi ra VND.

## 5. Validate output

Validate schema/type/enum/range/required metadata; hash/version/round khớp; đủ evidence; weight total 100; total score tính lại khớp; hard_violation_count khớp danh sách; result không mâu thuẫn. `PASS` mà violations>0 vẫn chặn auto và ghi conflict. Key lạ không trở thành instruction hoặc quyền hệ thống.

Output lỗi giữ bản gốc theo chính sách bảo mật và failure_reason, đưa human; không default score=100/confidence=1/PASS. Ràng buộc validate nằm trước decision và được kiểm lại context khi commit.

## 6. Orchestration và retry

Submit commit → tạo run → VLM/Media dependency; Strategy/Budget độc lập về mặt input → join results → validate → decision. Sprint modular monolith, không yêu cầu microservice/message broker mới. Timeout lấy config đã chốt, không có số ms bắt buộc trong nguồn.

Attempt timeout phải kết thúc có mã lỗi. Retry (khi có) giữ correlation hoặc link run gốc, snapshot/input không thay; stale output không được commit sau final decision. Quyết định+state+audit nên cùng transaction, notification theo outbox/dedupe là `[ĐỀ XUẤT]`, không phải mô tả code đã có.

## 7. Giao diện Checker

1. Header: mã/tên, Maker, version/round, business status và nhãn processing; SLA nếu có.
2. Nội dung: objective/summary/dates/budget/optional fields, toàn bộ read-only.
3. Ảnh gốc và evidence: tên file, hình, OCR/vùng liên quan; chỉ cần xem evidence, không bắt xây công cụ comment vùng/proofing.
4. AI panels: VLM confidence; Media outcome+violations; Strategy criteria+weights+total+confidence+gaps; Budget amount/limit/comparison.
5. Vì sao cần người: reason list đầy đủ, primary category nếu có, câu hỏi cụ thể, failure message dễ hiểu.
6. Hành động: Approve/Reject khi quyền+stage hợp lệ. Reject reason bắt buộc; override reason theo OQ-05; không có Undo/Request changes.
7. History: chọn V1/V2, xem AI/decision riêng mỗi vòng; source System/Checker rõ; model/policy metadata có thể ở phần mở rộng.

UI lỗi agent nói “Chưa có đủ kết quả đánh giá”, không nói “Kế hoạch vi phạm”. Mode MOCK có nhãn demo. Shadow không lộ khuyến nghị cho người quyết định; cách hiển thị evidence so với recommendation cần thống nhất với PO.

## 8. Mapping lỗi tối thiểu

| Mã đề xuất | Stage/route | Hiển thị |
|---|---|---|
| AGENT_TIMEOUT | AI_PROCESSING_FAILED + HUMAN_REVIEW_REQUIRED | AI chưa hoàn tất; Checker thẩm định |
| INVALID_AGENT_OUTPUT | AI_PROCESSING_FAILED + HUMAN_REVIEW_REQUIRED | Kết quả chưa hợp lệ, không dùng auto |
| VLM_LOW_CONFIDENCE | HUMAN_REVIEW_REQUIRED | Trích xuất chưa đủ tin cậy |
| BUDGET_LIMIT_MISSING | HUMAN_REVIEW_REQUIRED | Chưa xác định được hạn mức |
| BUDGET_LIMIT_EXCEEDED | HUMAN_REVIEW_REQUIRED | Ngân sách vượt hạn mức auto |
| STALE_ROUND_RESULT | Không đổi stage của round hiện hành | Audit kết quả trễ, không thêm hồ sơ chờ mới |

Không trả stack trace/secrets ra UI. Mã HTTP và API routes do codebase quyết định; tài liệu này không giả định framework hay endpoint đã tồn tại.

## Bản sửa v2.1: evidence structure và giới hạn mapping

WP1/WP2 schema thực chưa có trong file đính kèm. fact-verification.schema.json là proposal cho fixture, không phải schema trích từ code người dùng. Cần map issue_type, source values, evidence refs và unresolved status vào contract hiện hữu; chưa map được thì báo thiếu mapping thay vì bỏ trường.

UI nên hiển thị ngân sách 50m ↔ 120m/180m, KPI 1200 ↔ 12000, hoặc OCR chưa đầy đủ. Không mô tả chữ mờ là vi phạm policy đã xác minh. Schema/media hợp lệ chưa đồng nghĩa business fact verified.
