# 05 · Bộ 15 ca dữ liệu nền và nhãn kỳ vọng

> **Sửa v2.1:** GT-007/008/009 và VERIFY-A04 giữ FACT_UNCERTAIN; thêm dữ kiện có cấu trúc trong input.fact_verification. Đây là **extension fixture đề xuất**, chưa xác minh schema WP1/WP2 thực tế. Không tự coi thêm field vào JSON là engine đã hỗ trợ. Xem [hướng dẫn mapping](19-wp1-wp2-mapping-and-regression.md) trước khi import.

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Gate theo Scope/Sprint; số lượng và phân nhóm kế thừa gói Role 1 cũ. Toàn bộ dữ liệu là tổng hợp.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Giới hạn nhãn “ground truth”

Đây là **oracle nghiệp vụ ở layer contract**: với output agent đã đặt trước, engine phải cho route đúng. Đây không phải nhãn khách quan về hiệu quả một chiến dịch, bộ ảnh đánh giá Local VLM hay kết quả AI đã chạy. Tên ground truth được giữ theo đề mục cũ; chưa có PO sign-off. Có 6 ca auto, 9 ca human (3 fact, 2 policy, 2 authority, 2 hard-violation có category null).

Các case đều đủ dữ liệu submit. GT-007 có budget form hợp lệ 50m; vấn đề là OCR và form xung đột, không dùng budget null rồi cho qua validation như v1. GT-014/015 chuyển human, không HARD_REJECTED. GT-013 chỉ vượt cùng L demo, không tạo quyền Manager hay cấp cao hơn.

## 2. Fixture chung, áp dụng cho mọi ca nếu không ghi khác

Maker DEMO-MAKER-01; Checker DEMO-CHECKER-01 active, khác Maker; department DEMO-DEPT-01; PENDING_APPROVAL; Round 1 ACTIVE; version 1; chưa final decision; mode Controlled Auto-Approval enabled; policy/limit còn hiệu lực tại thời điểm submit giả lập 2026-10-01T02:00:00Z.

Ngày kế hoạch 2026-10-02 đến 2026-10-30; objective/summary đầy đủ; audience/channels/KPI optional được điền để demo có ngữ cảnh; có một PNG fixture upload hoàn tất. Agent metadata/evidence đầy đủ, không lỗi trừ biến thể được chỉ rõ. Điểm 7 tiêu chí trong fixture bằng nhau để tổng đúng score đặt trước; không phải chấm chất lượng nội dung thật.

File JSON chứa **đầy đủ input của từng ca**, không chỉ patch; dùng để import vào harness sau khi map schema dự án. Hình PNG được tạo bằng chữ tổng hợp có nhãn demo; confidence/output là giá trị test, không suy ra từ việc đã chạy model trên PNG.

## 3. Danh mục chi tiết

### GT-001 · Kế hoạch thông thường đủ gate

**Nhóm:** ROUTINE · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 50,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 84 / 0.91 |
| VLM / Media confidence | 0.96 / 0.94 |
| Media / hard violations / conflicts | PASS / 0 / 0 |
| Ảnh | [creative-pass.png](../../../tests/fixtures/ba/v2.1/images/creative-pass.png) |
| Route | AUTO_APPROVED |
| Business / processing | APPROVED / AI_AUTO_APPROVED |
| Final decision / source | APPROVED / AI_AUTO_APPROVAL |
| Category | null — xem reason code |
| Reason bắt buộc | Không có blocker; phải lưu mọi gate đạt |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-001 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Mọi điều kiện đủ; ghi actor System, policy version và gate summary. Không cần câu hỏi Checker để hoàn tất quyết định tự động.

**Kiểm thêm:** Không nhân đôi quyết định khi cùng kết quả được gửi lại; không giả danh Checker.

### GT-002 · Ngân sách bằng đúng L

**Nhóm:** ROUTINE · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 100,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 82.5 / 0.86 |
| VLM / Media confidence | 0.93 / 0.93 |
| Media / hard violations / conflicts | PASS / 0 / 0 |
| Ảnh | [creative-pass.png](../../../tests/fixtures/ba/v2.1/images/creative-pass.png) |
| Route | AUTO_APPROVED |
| Business / processing | APPROVED / AI_AUTO_APPROVED |
| Final decision / source | APPROVED / AI_AUTO_APPROVAL |
| Category | null — xem reason code |
| Reason bắt buộc | Không có blocker; phải lưu mọi gate đạt |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-002 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Mọi điều kiện đủ; ghi actor System, policy version và gate summary. Không cần câu hỏi Checker để hoàn tất quyết định tự động.

**Kiểm thêm:** Không nhân đôi quyết định khi cùng kết quả được gửi lại; không giả danh Checker.

### GT-003 · Confidence bằng đúng các ngưỡng

**Nhóm:** ROUTINE · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 75,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 78 / 0.8 |
| VLM / Media confidence | 0.85 / 0.85 |
| Media / hard violations / conflicts | PASS / 0 / 0 |
| Ảnh | [creative-pass.png](../../../tests/fixtures/ba/v2.1/images/creative-pass.png) |
| Route | AUTO_APPROVED |
| Business / processing | APPROVED / AI_AUTO_APPROVED |
| Final decision / source | APPROVED / AI_AUTO_APPROVAL |
| Category | null — xem reason code |
| Reason bắt buộc | Không có blocker; phải lưu mọi gate đạt |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-003 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Mọi điều kiện đủ; ghi actor System, policy version và gate summary. Không cần câu hỏi Checker để hoàn tất quyết định tự động.

**Kiểm thêm:** Không nhân đôi quyết định khi cùng kết quả được gửi lại; không giả danh Checker.

### GT-004 · Điểm 70,1 vượt ngưỡng 70

**Nhóm:** ROUTINE · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 90,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 70.1 / 0.81 |
| VLM / Media confidence | 0.89 / 0.9 |
| Media / hard violations / conflicts | PASS / 0 / 0 |
| Ảnh | [creative-pass.png](../../../tests/fixtures/ba/v2.1/images/creative-pass.png) |
| Route | AUTO_APPROVED |
| Business / processing | APPROVED / AI_AUTO_APPROVED |
| Final decision / source | APPROVED / AI_AUTO_APPROVAL |
| Category | null — xem reason code |
| Reason bắt buộc | Không có blocker; phải lưu mọi gate đạt |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-004 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Mọi điều kiện đủ; ghi actor System, policy version và gate summary. Không cần câu hỏi Checker để hoàn tất quyết định tự động.

**Kiểm thêm:** Không nhân đôi quyết định khi cùng kết quả được gửi lại; không giả danh Checker.

### GT-005 · Kế hoạch webinar demo đủ gate

**Nhóm:** ROUTINE · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 60,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 88 / 0.9 |
| VLM / Media confidence | 0.95 / 0.95 |
| Media / hard violations / conflicts | PASS / 0 / 0 |
| Ảnh | [creative-pass.png](../../../tests/fixtures/ba/v2.1/images/creative-pass.png) |
| Route | AUTO_APPROVED |
| Business / processing | APPROVED / AI_AUTO_APPROVED |
| Final decision / source | APPROVED / AI_AUTO_APPROVAL |
| Category | null — xem reason code |
| Reason bắt buộc | Không có blocker; phải lưu mọi gate đạt |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-005 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Mọi điều kiện đủ; ghi actor System, policy version và gate summary. Không cần câu hỏi Checker để hoàn tất quyết định tự động.

**Kiểm thêm:** Không nhân đôi quyết định khi cùng kết quả được gửi lại; không giả danh Checker.

### GT-006 · Ngân sách bằng 0 vẫn hợp lệ

**Nhóm:** ROUTINE · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 0 / 100,000,000 VND |
| Score / Strategy confidence | 76 / 0.83 |
| VLM / Media confidence | 0.97 / 0.95 |
| Media / hard violations / conflicts | PASS / 0 / 0 |
| Ảnh | [creative-pass.png](../../../tests/fixtures/ba/v2.1/images/creative-pass.png) |
| Route | AUTO_APPROVED |
| Business / processing | APPROVED / AI_AUTO_APPROVED |
| Final decision / source | APPROVED / AI_AUTO_APPROVAL |
| Category | null — xem reason code |
| Reason bắt buộc | Không có blocker; phải lưu mọi gate đạt |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-006 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Mọi điều kiện đủ; ghi actor System, policy version và gate summary. Không cần câu hỏi Checker để hoàn tất quyết định tự động.

**Kiểm thêm:** Không nhân đôi quyết định khi cùng kết quả được gửi lại; không giả danh Checker.

### GT-007 · Form và hai giá trị OCR không thống nhất

**Kết luận nghiệp vụ: chọn A — giữ FACT_UNCERTAIN.** Runtime outcome HUMAN_REVIEW_REQUIRED; business state PENDING_APPROVAL; final decision/source null. Actual NOT_RUN.

| Nội dung | Dữ liệu sửa v2.1 |
|---|---|
| Field cần xác minh | budget_vnd tại /plan_snapshot/budget_vnd |
| Tính chất vấn đề | CONFLICTING_VALUES, trạng thái UNRESOLVED |
| Giá trị được xác minh | null trong issue; không xóa field bắt buộc trong form |
| Nguồn | E-GT-007; có source pointers trong JSON |
| Media result / confidence | REVIEW_REQUIRED / 0.82 — giữ nguyên, không dùng riêng nó để suy category |
| VLM confidence | 0.61 — không nâng/hạ để ép test |
| Policy scope covered | true — giữ nguyên |
| Rule fixture | R1-FIX-CONFLICT-01 (local reference, chưa xác minh mã runtime) |
| Hash bổ sung | evaluation_fixture_hash bao phủ cả output/evidence; input_hash giữ định nghĩa plan+policy |
| Runtime verification | Chưa có engine/WP1/WP2; chưa chạy regression ứng dụng |

**Rationale:** Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR.

**Câu hỏi:** Form ghi 50.000.000 VND, ảnh nêu phương án A 120.000.000 và B 180.000.000 VND. Hãy đối chiếu E-GT-007 và xác định ngân sách chính thức. Nếu cần sửa hồ sơ, từ chối có lý do để Maker gửi phiên bản mới.

**Evidence chuẩn hóa đầy đủ:**

~~~json
{
  "schema_version": "role1.fact-verification/1.0-proposed",
  "verification_status": "UNCERTAIN",
  "assertion_origin": "SYNTHETIC_FIXTURE",
  "issues": [
    {
      "issue_id": "ISSUE-GT-007-01",
      "field": "budget_vnd",
      "affected_input_pointer": "/plan_snapshot/budget_vnd",
      "issue_type": "CONFLICTING_VALUES",
      "status": "UNRESOLVED",
      "verified_value": null,
      "sources": [
        {
          "kind": "PLAN_FIELD",
          "pointer": "/plan_snapshot/budget_vnd",
          "observed_value": 50000000,
          "normalized_value": 50000000,
          "evidence_ref": null
        },
        {
          "kind": "VLM_EVIDENCE",
          "pointer": "/agent_outputs/vlm/evidence/0/observed_text",
          "observed_value": "Phương án A: 120.000.000 VND",
          "normalized_value": 120000000,
          "evidence_ref": "E-GT-007"
        },
        {
          "kind": "VLM_EVIDENCE",
          "pointer": "/agent_outputs/vlm/evidence/0/observed_text",
          "observed_value": "Phương án B: 180.000.000 VND",
          "normalized_value": 180000000,
          "evidence_ref": "E-GT-007"
        }
      ],
      "evidence_refs": [
        "E-GT-007"
      ],
      "rationale": "Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR.",
      "fixture_rule_ref": "R1-FIX-CONFLICT-01"
    }
  ]
}
~~~

**Reason/gate:** VLM_LOW_CONFIDENCE, UNRESOLVED_CONFLICT là các tên kế thừa fixture, cần map mã thực của engine. Không còn bắt buộc MEDIA_REVIEW_REQUIRED như bằng chứng cho factual uncertainty. explanation_requirements buộc nêu field, conflict/thiếu trích xuất, evidence và unresolved status; không chỉ kiểm category hoặc câu chữ chung.

**Cách chạy:** dùng JSON đầy đủ tại [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json). Validate fixture → xác nhận WP mapping → capture input sau adapter → gọi engine thật → kiểm route/category/reason/evidence và state/audit. Không nạp expected vào engine.

### GT-008 · KPI form và ảnh mâu thuẫn

**Kết luận nghiệp vụ: chọn A — giữ FACT_UNCERTAIN.** Runtime outcome HUMAN_REVIEW_REQUIRED; business state PENDING_APPROVAL; final decision/source null. Actual NOT_RUN.

| Nội dung | Dữ liệu sửa v2.1 |
|---|---|
| Field cần xác minh | kpi_expected tại /plan_snapshot/kpi_expected |
| Tính chất vấn đề | CONFLICTING_VALUES, trạng thái UNRESOLVED |
| Giá trị được xác minh | null trong issue; không xóa field bắt buộc trong form |
| Nguồn | E-GT-008; có source pointers trong JSON |
| Media result / confidence | REVIEW_REQUIRED / 0.9 — giữ nguyên, không dùng riêng nó để suy category |
| VLM confidence | 0.9 — không nâng/hạ để ép test |
| Policy scope covered | true — giữ nguyên |
| Rule fixture | R1-FIX-CONFLICT-01 (local reference, chưa xác minh mã runtime) |
| Hash bổ sung | evaluation_fixture_hash bao phủ cả output/evidence; input_hash giữ định nghĩa plan+policy |
| Runtime verification | Chưa có engine/WP1/WP2; chưa chạy regression ứng dụng |

**Rationale:** Form/KPI nêu 1.200 lượt đăng ký, trong khi dòng KPI chính trên ảnh nêu 12.000 lượt đăng ký. Confidence OCR 0,90 không giải quyết được xung đột liên nguồn. Chưa xác định target chính thức; không đổi score/confidence để ép case.

**Câu hỏi:** Form ghi 1.200 lượt đăng ký, dòng KPI trên ảnh E-GT-008 ghi 12.000. Hãy xác định target được thẩm định và căn cứ. Nếu nội dung phải sửa, từ chối để Maker gửi phiên bản mới.

**Evidence chuẩn hóa đầy đủ:**

~~~json
{
  "schema_version": "role1.fact-verification/1.0-proposed",
  "verification_status": "UNCERTAIN",
  "assertion_origin": "SYNTHETIC_FIXTURE",
  "issues": [
    {
      "issue_id": "ISSUE-GT-008-01",
      "field": "kpi_expected",
      "affected_input_pointer": "/plan_snapshot/kpi_expected",
      "issue_type": "CONFLICTING_VALUES",
      "status": "UNRESOLVED",
      "verified_value": null,
      "sources": [
        {
          "kind": "PLAN_FIELD",
          "pointer": "/plan_snapshot/kpi_expected",
          "observed_value": "1.200 lượt đăng ký trước 2026-10-30",
          "normalized_value": 1200,
          "evidence_ref": null
        },
        {
          "kind": "VLM_EVIDENCE",
          "pointer": "/agent_outputs/vlm/evidence/0/observed_text",
          "observed_value": "Mục tiêu: 12.000 lượt đăng ký",
          "normalized_value": 12000,
          "evidence_ref": "E-GT-008"
        }
      ],
      "evidence_refs": [
        "E-GT-008"
      ],
      "rationale": "Form/KPI nêu 1.200 lượt đăng ký, trong khi dòng KPI chính trên ảnh nêu 12.000 lượt đăng ký. Confidence OCR 0,90 không giải quyết được xung đột liên nguồn. Chưa xác định target chính thức; không đổi score/confidence để ép case.",
      "fixture_rule_ref": "R1-FIX-CONFLICT-01"
    }
  ]
}
~~~

**Reason/gate:** UNRESOLVED_CONFLICT là các tên kế thừa fixture, cần map mã thực của engine. Không còn bắt buộc MEDIA_REVIEW_REQUIRED như bằng chứng cho factual uncertainty. explanation_requirements buộc nêu field, conflict/thiếu trích xuất, evidence và unresolved status; không chỉ kiểm category hoặc câu chữ chung.

**Cách chạy:** dùng JSON đầy đủ tại [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json). Validate fixture → xác nhận WP mapping → capture input sau adapter → gọi engine thật → kiểm route/category/reason/evidence và state/audit. Không nạp expected vào engine.

### GT-009 · Ảnh chất lượng thấp, cần người đọc lại

**Kết luận nghiệp vụ: chọn A — giữ FACT_UNCERTAIN.** Runtime outcome HUMAN_REVIEW_REQUIRED; business state PENDING_APPROVAL; final decision/source null. Actual NOT_RUN.

| Nội dung | Dữ liệu sửa v2.1 |
|---|---|
| Field cần xác minh | creative_text tại /agent_outputs/vlm/evidence/0/observed_text |
| Tính chất vấn đề | INCOMPLETE_EXTRACTION, trạng thái UNRESOLVED |
| Giá trị được xác minh | null trong issue; không xóa field bắt buộc trong form |
| Nguồn | E-GT-009; có source pointers trong JSON |
| Media result / confidence | REVIEW_REQUIRED / 0.88 — giữ nguyên, không dùng riêng nó để suy category |
| VLM confidence | 0.72 — không nâng/hạ để ép test |
| Policy scope covered | true — giữ nguyên |
| Rule fixture | R1-FIX-INCOMPLETE-01 (local reference, chưa xác minh mã runtime) |
| Hash bổ sung | evaluation_fixture_hash bao phủ cả output/evidence; input_hash giữ định nghĩa plan+policy |
| Runtime verification | Chưa có engine/WP1/WP2; chưa chạy regression ứng dụng |

**Rationale:** Mock OCR chỉ trả phần đầu 'Thông điệp'; phần còn lại của dòng chưa được xác minh. Case mô phỏng trích xuất không đầy đủ, không khẳng định một model thật đã chạy hoặc ảnh chứa claim/disclaimer vi phạm. creative_text chưa đủ bằng chứng nên cần human review.

**Câu hỏi:** Kết quả OCR E-GT-009 chỉ xác minh phần đầu 'Thông điệp', chưa xác minh phần còn lại (confidence 0,72). Hãy đọc ảnh gốc hoặc yêu cầu Maker gửi ảnh/phiên bản đủ rõ qua luồng từ chối và gửi lại.

**Evidence chuẩn hóa đầy đủ:**

~~~json
{
  "schema_version": "role1.fact-verification/1.0-proposed",
  "verification_status": "UNCERTAIN",
  "assertion_origin": "SYNTHETIC_FIXTURE",
  "issues": [
    {
      "issue_id": "ISSUE-GT-009-01",
      "field": "creative_text",
      "affected_input_pointer": "/agent_outputs/vlm/evidence/0/observed_text",
      "issue_type": "INCOMPLETE_EXTRACTION",
      "status": "UNRESOLVED",
      "verified_value": null,
      "sources": [
        {
          "kind": "VLM_EVIDENCE",
          "pointer": "/agent_outputs/vlm/evidence/0/observed_text",
          "observed_value": "Thông điệp [phần còn lại chưa xác minh]",
          "normalized_value": null,
          "evidence_ref": "E-GT-009"
        }
      ],
      "evidence_refs": [
        "E-GT-009"
      ],
      "rationale": "Mock OCR chỉ trả phần đầu 'Thông điệp'; phần còn lại của dòng chưa được xác minh. Case mô phỏng trích xuất không đầy đủ, không khẳng định một model thật đã chạy hoặc ảnh chứa claim/disclaimer vi phạm. creative_text chưa đủ bằng chứng nên cần human review.",
      "fixture_rule_ref": "R1-FIX-INCOMPLETE-01"
    }
  ]
}
~~~

**Reason/gate:** VLM_LOW_CONFIDENCE là các tên kế thừa fixture, cần map mã thực của engine. Không còn bắt buộc MEDIA_REVIEW_REQUIRED như bằng chứng cho factual uncertainty. explanation_requirements buộc nêu field, conflict/thiếu trích xuất, evidence và unresolved status; không chỉ kiểm category hoặc câu chữ chung.

**Cách chạy:** dùng JSON đầy đủ tại [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json). Validate fixture → xác nhận WP mapping → capture input sau adapter → gọi engine thật → kiểm route/category/reason/evidence và state/audit. Không nạp expected vào engine.

### GT-010 · Chưa có policy cho phạm vi nội dung

**Nhóm:** POLICY_OUT_OF_SCOPE · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 80,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 83 / 0.88 |
| VLM / Media confidence | 0.94 / 0.94 |
| Media / hard violations / conflicts | REVIEW_REQUIRED / 0 / 0 |
| Ảnh | [scope-missing.png](../../../tests/fixtures/ba/v2.1/images/scope-missing.png) |
| Route | HUMAN_REVIEW_REQUIRED |
| Business / processing | PENDING_APPROVAL / HUMAN_REVIEW_REQUIRED |
| Final decision / source | null / null |
| Category | POLICY_OUT_OF_SCOPE |
| Reason bắt buộc | MEDIA_REVIEW_REQUIRED, POLICY_SCOPE_MISSING |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-010 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Chưa có content policy cho DEMO-SPECIAL-DOMAIN. Vui lòng xác định chính sách/căn cứ xử lý, không tự duyệt khi thiếu mapping.

**Kiểm thêm:** Không được tạo final decision hoặc chuyển REJECTED tại bước engine; Checker vẫn là người được giao.

### GT-011 · Kênh thử nghiệm chưa mapping content policy

**Nhóm:** POLICY_OUT_OF_SCOPE · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 70,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 77 / 0.84 |
| VLM / Media confidence | 0.92 / 0.92 |
| Media / hard violations / conflicts | REVIEW_REQUIRED / 0 / 0 |
| Ảnh | [scope-missing.png](../../../tests/fixtures/ba/v2.1/images/scope-missing.png) |
| Route | HUMAN_REVIEW_REQUIRED |
| Business / processing | PENDING_APPROVAL / HUMAN_REVIEW_REQUIRED |
| Final decision / source | null / null |
| Category | POLICY_OUT_OF_SCOPE |
| Reason bắt buộc | MEDIA_REVIEW_REQUIRED, POLICY_SCOPE_MISSING |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-011 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Chưa có content policy cho NewLiveChannel. Vui lòng xác định căn cứ áp dụng và thẩm định thủ công.

**Kiểm thêm:** Không được tạo final decision hoặc chuyển REJECTED tại bước engine; Checker vẫn là người được giao.

### GT-012 · Vượt L đúng 1 VND

**Nhóm:** AUTHORITY_EXCEEDED · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 100,000,001 / 100,000,000 VND |
| Score / Strategy confidence | 86 / 0.9 |
| VLM / Media confidence | 0.96 / 0.96 |
| Media / hard violations / conflicts | PASS / 0 / 0 |
| Ảnh | [creative-pass.png](../../../tests/fixtures/ba/v2.1/images/creative-pass.png) |
| Route | HUMAN_REVIEW_REQUIRED |
| Business / processing | PENDING_APPROVAL / HUMAN_REVIEW_REQUIRED |
| Final decision / source | null / null |
| Category | AUTHORITY_EXCEEDED |
| Reason bắt buộc | BUDGET_LIMIT_EXCEEDED |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-012 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** 100.000.001 VND vượt hạn mức tự động 100.000.000 VND đúng 1 VND. Checker được giao vui lòng thẩm định theo quyền hiện có.

**Kiểm thêm:** Không được tạo final decision hoặc chuyển REJECTED tại bước engine; Checker vẫn là người được giao.

### GT-013 · Ngân sách lớn hơn L, vẫn một Checker

**Nhóm:** AUTHORITY_EXCEEDED · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 1,200,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 91 / 0.92 |
| VLM / Media confidence | 0.95 / 0.95 |
| Media / hard violations / conflicts | PASS / 0 / 0 |
| Ảnh | [creative-pass.png](../../../tests/fixtures/ba/v2.1/images/creative-pass.png) |
| Route | HUMAN_REVIEW_REQUIRED |
| Business / processing | PENDING_APPROVAL / HUMAN_REVIEW_REQUIRED |
| Final decision / source | null / null |
| Category | AUTHORITY_EXCEEDED |
| Reason bắt buộc | BUDGET_LIMIT_EXCEEDED |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-013 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** 1.200.000.000 VND vượt hạn mức tự động 100.000.000 VND. Vui lòng thẩm định thủ công; hệ thống không tự tạo thêm cấp duyệt.

**Kiểm thêm:** Không được tạo final decision hoặc chuyển REJECTED tại bước engine; Checker vẫn là người được giao.

### GT-014 · Token claim vi phạm rule demo

**Nhóm:** HARD_VIOLATION · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 50,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 85 / 0.9 |
| VLM / Media confidence | 0.97 / 0.97 |
| Media / hard violations / conflicts | REVIEW_REQUIRED / 1 / 0 |
| Ảnh | [hard-claim-demo.png](../../../tests/fixtures/ba/v2.1/images/hard-claim-demo.png) |
| Route | HUMAN_REVIEW_REQUIRED |
| Business / processing | PENDING_APPROVAL / HUMAN_REVIEW_REQUIRED |
| Final decision / source | null / null |
| Category | null — xem reason code |
| Reason bắt buộc | MEDIA_REVIEW_REQUIRED, HARD_VIOLATION |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-014 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Token CAM KẾT DEMO TUYỆT ĐỐI bị HV-DEMO-01 đánh dấu. Vui lòng kiểm tra ảnh/rule demo trước khi quyết định; đây chưa phải quyết định từ chối.

**Kiểm thêm:** Không được tạo final decision hoặc chuyển REJECTED tại bước engine; Checker vẫn là người được giao.

### GT-015 · Token thông tin khách hàng giả lập bị rule demo chặn

**Nhóm:** HARD_VIOLATION · **Layer:** DECISION_POLICY_CONTRACT · **Actual:** NOT_RUN.

| Input/expected | Giá trị |
|---|---|
| Maker / Checker | DEMO-MAKER-01 / DEMO-CHECKER-01 |
| Ngân sách / limit | 40,000,000 / 100,000,000 VND |
| Score / Strategy confidence | 80 / 0.85 |
| VLM / Media confidence | 0.95 / 0.95 |
| Media / hard violations / conflicts | REVIEW_REQUIRED / 1 / 0 |
| Ảnh | [synthetic-private-demo.png](../../../tests/fixtures/ba/v2.1/images/synthetic-private-demo.png) |
| Route | HUMAN_REVIEW_REQUIRED |
| Business / processing | PENDING_APPROVAL / HUMAN_REVIEW_REQUIRED |
| Final decision / source | null / null |
| Category | null — xem reason code |
| Reason bắt buộc | MEDIA_REVIEW_REQUIRED, HARD_VIOLATION |

**Cách chạy:** dùng đầy đủ context, plan snapshot, policy và agent outputs của GT-015 trong [ground-truth-cases.json](../../../tests/fixtures/ba/v2.1/ground-truth-cases.json); gọi decision evaluator qua test harness của app. Sau đó kiểm state/decision/audit phù hợp layer được chạy.

**Giải thích/câu hỏi:** Token khách hàng giả lập DEMO-0001 bị HV-DEMO-02 đánh dấu. Vui lòng xem bằng chứng và rule demo trước khi quyết định; ảnh không chứa dữ liệu cá nhân thật.

**Kiểm thêm:** Không được tạo final decision hoặc chuyển REJECTED tại bước engine; Checker vẫn là người được giao.


## 4. Quy tắc sử dụng dataset

Không dùng case_id/tên file/tên kế hoạch làm điều kiện quyết định trong production. Mock provider được chọn theo fixture cấu hình riêng để test, nhưng engine chỉ đọc structured facts/policy. Đổi case name/JSON key order không đổi nghĩa và phải cho cùng route.

Để chạy end-to-end qua UI cần seed người dùng, policy, limit, ảnh và provider test; nếu Strategy/Media chạy model thật thì điểm/kết quả có thể khác fixture và phải ghi đúng actual. Không ghi “model sai” chỉ vì không ra đúng 84; phân biệt lỗi perception/scoring với lỗi áp dụng gate.
