# Verify execution results — 2026-10-09

Executed with `.venv-test-20261009` Python 3.12.0; `pip check` passed. Each fixture case used a fresh in-memory `ApprovalWorkflow` and `ApprovalRepository(":memory:")`; database URL variables were unset for these processes.

Expected results are read only after all application executions finish. The real application Decision Policy Engine and deterministic Budget Rules Engine ran against synthetic agent output from `BAMockProvider` (`MOCK_VLM`). No real VLM, Media Compliance model, or Strategy model ran. This is not real-model evidence.

Suite selection: `general` = first 4 of the 5 Verify inputs; `escalation` = all 5 Verify inputs; `regression` = all 15 ground-truth regression cases. These runs overlap. The 15-case regression catalog has been used during development and is not an independent holdout.

Input fixture SHA-256: `9a6740620ba714383660b0438fb324529c93b95955bba73646aff16085de8b41`; expected SHA-256: `0e109a6c64f2fc1473076ae6083e053ef385c61ec89388500814e10d8ca123bd`; regression fixture SHA-256: `d7ccf17e7cf974b17209569309d4e1abd3dcca321b850e74f66beb7d908c43e0`.

The focused `tests/unit/verify` pytest command also passed: **11/11**, including
oracle-field rejection and ID/title/filename invariance tests.

## general: 4/4 passed

### VERIFY-A01 — Verify / Kế hoạch thông thường đủ gate

- Result: **PASS**; classification: `SYNTHETIC`; duration: 17 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### VERIFY-A02 — Verify / Ngân sách bằng đúng L

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### VERIFY-A03 — Verify / Điểm 70,1 vượt ngưỡng 70

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### VERIFY-A04 — Verify / Form và hai giá trị OCR không thống nhất

- Result: **PASS**; classification: `SYNTHETIC`; duration: 15 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "explanation_requirements": {"affected_fields": ["budget_vnd"], "issue_types": ["CONFLICTING_VALUES"], "media_result_alone_is_insufficient": true, "must_describe_unresolved_fact": true, "required_evidence_refs": ["E-GT-007"], "required_factual_issue_refs": ["ISSUE-GT-007-01"], "wp_runtime_code_mapping_status": "NOT_VERIFIED"}, "final_decision": null, "hard_violation_auto_reject_allowed": false, "policy_references": [{"reference": "BR-AI-10", "source": "sources/scope-phase-1.md", "supports": "Confidence thấp/kết quả thiếu phải chuyển Human Review."}, {"reference": "§4: unresolved_conflict_count = 0", "source": "sources/sprint-1-deliverables.md", "supports": "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping."}, {"reference": "FACT_UNCERTAIN / precedence", "source": "04-escalation-policy.md", "supports": "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi."}, {"reference": "R1-FIX-CONFLICT-01", "source": "18-fact-uncertainty-correction.md", "supports": "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2."}], "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Form ghi 50.000.000 VND, ảnh nêu phương án A 120.000.000 và B 180.000.000 VND. Hãy đối chiếu E-GT-007 và xác định ngân sách chính thức. Nếu cần sửa hồ sơ, từ chối có lý do để Maker gửi phiên bản mới.", "question_required": true, "rationale": "Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR.", "required_reason_codes": ["VLM_LOW_CONFIDENCE", "UNRESOLVED_CONFLICT"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS", "MEDIA_CONFIDENCE", "NO_EVIDENCE_CONFLICT"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

## escalation: 5/5 passed

### VERIFY-A01 — Verify / Kế hoạch thông thường đủ gate

- Result: **PASS**; classification: `SYNTHETIC`; duration: 17 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### VERIFY-A02 — Verify / Ngân sách bằng đúng L

- Result: **PASS**; classification: `SYNTHETIC`; duration: 13 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### VERIFY-A03 — Verify / Điểm 70,1 vượt ngưỡng 70

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### VERIFY-A04 — Verify / Form và hai giá trị OCR không thống nhất

- Result: **PASS**; classification: `SYNTHETIC`; duration: 18 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "explanation_requirements": {"affected_fields": ["budget_vnd"], "issue_types": ["CONFLICTING_VALUES"], "media_result_alone_is_insufficient": true, "must_describe_unresolved_fact": true, "required_evidence_refs": ["E-GT-007"], "required_factual_issue_refs": ["ISSUE-GT-007-01"], "wp_runtime_code_mapping_status": "NOT_VERIFIED"}, "final_decision": null, "hard_violation_auto_reject_allowed": false, "policy_references": [{"reference": "BR-AI-10", "source": "sources/scope-phase-1.md", "supports": "Confidence thấp/kết quả thiếu phải chuyển Human Review."}, {"reference": "§4: unresolved_conflict_count = 0", "source": "sources/sprint-1-deliverables.md", "supports": "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping."}, {"reference": "FACT_UNCERTAIN / precedence", "source": "04-escalation-policy.md", "supports": "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi."}, {"reference": "R1-FIX-CONFLICT-01", "source": "18-fact-uncertainty-correction.md", "supports": "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2."}], "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Form ghi 50.000.000 VND, ảnh nêu phương án A 120.000.000 và B 180.000.000 VND. Hãy đối chiếu E-GT-007 và xác định ngân sách chính thức. Nếu cần sửa hồ sơ, từ chối có lý do để Maker gửi phiên bản mới.", "question_required": true, "rationale": "Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR.", "required_reason_codes": ["VLM_LOW_CONFIDENCE", "UNRESOLVED_CONFLICT"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS", "MEDIA_CONFIDENCE", "NO_EVIDENCE_CONFLICT"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### VERIFY-A05 — Verify / Vượt L đúng 1 VND

- Result: **PASS**; classification: `SYNTHETIC`; duration: 15 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "final_decision": null, "hard_violation_auto_reject_allowed": false, "primary_category": "AUTHORITY_EXCEEDED", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "100.000.001 VND vượt hạn mức tự động 100.000.000 VND đúng 1 VND. Checker được giao vui lòng thẩm định theo quyền hiện có.", "question_required": true, "required_reason_codes": ["BUDGET_LIMIT_EXCEEDED"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["BUDGET_LIMIT", "AUTHORITY_LIMIT"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "AUTHORITY_EXCEEDED", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

## regression: 15/15 passed

### GT-001 — Kế hoạch thông thường đủ gate

- Result: **PASS**; classification: `SYNTHETIC`; duration: 17 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### GT-002 — Ngân sách bằng đúng L

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### GT-003 — Confidence bằng đúng các ngưỡng

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### GT-004 — Điểm 70,1 vượt ngưỡng 70

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### GT-005 — Kế hoạch webinar demo đủ gate

- Result: **PASS**; classification: `SYNTHETIC`; duration: 15 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### GT-006 — Ngân sách bằng 0 vẫn hợp lệ

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "expected_app_execution_status": "NOT_RUN", "final_decision": "APPROVED", "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "question_example": null, "question_required": false, "required_reason_codes": [], "route": "AUTO_APPROVED"}`
- Actual: `{"business_status": "APPROVED", "decision_source": "AI_AUTO_APPROVAL", "evaluation_status": "SUCCEEDED", "failed_rule_ids": [], "final_decision": "APPROVED", "model_version": "role1-mock-adapter-v2.1", "primary_category": null, "processing_stage": "AI_AUTO_APPROVED", "provider": "MOCK_VLM", "question_count": 0, "route": "AUTO_APPROVED"}`
- Differences: none

### GT-007 — Form và hai giá trị OCR không thống nhất

- Result: **PASS**; classification: `SYNTHETIC`; duration: 15 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "explanation_requirements": {"affected_fields": ["budget_vnd"], "issue_types": ["CONFLICTING_VALUES"], "media_result_alone_is_insufficient": true, "must_describe_unresolved_fact": true, "required_evidence_refs": ["E-GT-007"], "required_factual_issue_refs": ["ISSUE-GT-007-01"], "wp_runtime_code_mapping_status": "NOT_VERIFIED"}, "final_decision": null, "hard_violation_auto_reject_allowed": false, "policy_references": [{"reference": "BR-AI-10", "source": "sources/scope-phase-1.md", "supports": "Confidence thấp/kết quả thiếu phải chuyển Human Review."}, {"reference": "§4: unresolved_conflict_count = 0", "source": "sources/sprint-1-deliverables.md", "supports": "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping."}, {"reference": "FACT_UNCERTAIN / precedence", "source": "04-escalation-policy.md", "supports": "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi."}, {"reference": "R1-FIX-CONFLICT-01", "source": "18-fact-uncertainty-correction.md", "supports": "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2."}], "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Form ghi 50.000.000 VND, ảnh nêu phương án A 120.000.000 và B 180.000.000 VND. Hãy đối chiếu E-GT-007 và xác định ngân sách chính thức. Nếu cần sửa hồ sơ, từ chối có lý do để Maker gửi phiên bản mới.", "question_required": true, "rationale": "Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR.", "required_reason_codes": ["VLM_LOW_CONFIDENCE", "UNRESOLVED_CONFLICT"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS", "MEDIA_CONFIDENCE", "NO_EVIDENCE_CONFLICT"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### GT-008 — KPI form và ảnh mâu thuẫn

- Result: **PASS**; classification: `SYNTHETIC`; duration: 15 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "explanation_requirements": {"affected_fields": ["kpi_expected"], "issue_types": ["CONFLICTING_VALUES"], "media_result_alone_is_insufficient": true, "must_describe_unresolved_fact": true, "required_evidence_refs": ["E-GT-008"], "required_factual_issue_refs": ["ISSUE-GT-008-01"], "wp_runtime_code_mapping_status": "NOT_VERIFIED"}, "final_decision": null, "hard_violation_auto_reject_allowed": false, "policy_references": [{"reference": "BR-AI-10", "source": "sources/scope-phase-1.md", "supports": "Confidence thấp/kết quả thiếu phải chuyển Human Review."}, {"reference": "§4: unresolved_conflict_count = 0", "source": "sources/sprint-1-deliverables.md", "supports": "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping."}, {"reference": "FACT_UNCERTAIN / precedence", "source": "04-escalation-policy.md", "supports": "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi."}, {"reference": "R1-FIX-CONFLICT-01", "source": "18-fact-uncertainty-correction.md", "supports": "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2."}], "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Form ghi 1.200 lượt đăng ký, dòng KPI trên ảnh E-GT-008 ghi 12.000. Hãy xác định target được thẩm định và căn cứ. Nếu nội dung phải sửa, từ chối để Maker gửi phiên bản mới.", "question_required": true, "rationale": "Form/KPI nêu 1.200 lượt đăng ký, trong khi dòng KPI chính trên ảnh nêu 12.000 lượt đăng ký. Confidence OCR 0,90 không giải quyết được xung đột liên nguồn. Chưa xác định target chính thức; không đổi score/confidence để ép case.", "required_reason_codes": ["UNRESOLVED_CONFLICT"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS", "NO_EVIDENCE_CONFLICT"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### GT-009 — Ảnh chất lượng thấp, cần người đọc lại

- Result: **PASS**; classification: `SYNTHETIC`; duration: 15 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "explanation_requirements": {"affected_fields": ["creative_text"], "issue_types": ["INCOMPLETE_EXTRACTION"], "media_result_alone_is_insufficient": true, "must_describe_unresolved_fact": true, "required_evidence_refs": ["E-GT-009"], "required_factual_issue_refs": ["ISSUE-GT-009-01"], "wp_runtime_code_mapping_status": "NOT_VERIFIED"}, "final_decision": null, "hard_violation_auto_reject_allowed": false, "policy_references": [{"reference": "BR-AI-10", "source": "sources/scope-phase-1.md", "supports": "Confidence thấp/kết quả thiếu phải chuyển Human Review."}, {"reference": "§4: unresolved_conflict_count = 0", "source": "sources/sprint-1-deliverables.md", "supports": "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping."}, {"reference": "FACT_UNCERTAIN / precedence", "source": "04-escalation-policy.md", "supports": "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi."}, {"reference": "R1-FIX-INCOMPLETE-01", "source": "18-fact-uncertainty-correction.md", "supports": "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2."}], "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Kết quả OCR E-GT-009 chỉ xác minh phần đầu 'Thông điệp', chưa xác minh phần còn lại (confidence 0,72). Hãy đọc ảnh gốc hoặc yêu cầu Maker gửi ảnh/phiên bản đủ rõ qua luồng từ chối và gửi lại.", "question_required": true, "rationale": "Mock OCR chỉ trả phần đầu 'Thông điệp'; phần còn lại của dòng chưa được xác minh. Case mô phỏng trích xuất không đầy đủ, không khẳng định một model thật đã chạy hoặc ảnh chứa claim/disclaimer vi phạm. creative_text chưa đủ bằng chứng nên cần human review.", "required_reason_codes": ["VLM_LOW_CONFIDENCE"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS", "NO_EVIDENCE_CONFLICT"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "FACT_UNCERTAIN", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### GT-010 — Chưa có policy cho phạm vi nội dung

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "final_decision": null, "hard_violation_auto_reject_allowed": false, "primary_category": "POLICY_OUT_OF_SCOPE", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Chưa có content policy cho DEMO-SPECIAL-DOMAIN. Vui lòng xác định chính sách/căn cứ xử lý, không tự duyệt khi thiếu mapping.", "question_required": true, "required_reason_codes": ["MEDIA_REVIEW_REQUIRED", "POLICY_SCOPE_MISSING"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "POLICY_OUT_OF_SCOPE", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### GT-011 — Kênh thử nghiệm chưa mapping content policy

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "final_decision": null, "hard_violation_auto_reject_allowed": false, "primary_category": "POLICY_OUT_OF_SCOPE", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Chưa có content policy cho NewLiveChannel. Vui lòng xác định căn cứ áp dụng và thẩm định thủ công.", "question_required": true, "required_reason_codes": ["MEDIA_REVIEW_REQUIRED", "POLICY_SCOPE_MISSING"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "POLICY_OUT_OF_SCOPE", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### GT-012 — Vượt L đúng 1 VND

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "final_decision": null, "hard_violation_auto_reject_allowed": false, "primary_category": "AUTHORITY_EXCEEDED", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "100.000.001 VND vượt hạn mức tự động 100.000.000 VND đúng 1 VND. Checker được giao vui lòng thẩm định theo quyền hiện có.", "question_required": true, "required_reason_codes": ["BUDGET_LIMIT_EXCEEDED"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["BUDGET_LIMIT", "AUTHORITY_LIMIT"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "AUTHORITY_EXCEEDED", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### GT-013 — Ngân sách lớn hơn L, vẫn một Checker

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "final_decision": null, "hard_violation_auto_reject_allowed": false, "primary_category": "AUTHORITY_EXCEEDED", "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "1.200.000.000 VND vượt hạn mức tự động 100.000.000 VND. Vui lòng thẩm định thủ công; hệ thống không tự tạo thêm cấp duyệt.", "question_required": true, "required_reason_codes": ["BUDGET_LIMIT_EXCEEDED"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["BUDGET_LIMIT", "AUTHORITY_LIMIT"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "AUTHORITY_EXCEEDED", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### GT-014 — Token claim vi phạm rule demo

- Result: **PASS**; classification: `SYNTHETIC`; duration: 14 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "final_decision": null, "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Token CAM KẾT DEMO TUYỆT ĐỐI bị HV-DEMO-01 đánh dấu. Vui lòng kiểm tra ảnh/rule demo trước khi quyết định; đây chưa phải quyết định từ chối.", "question_required": true, "required_reason_codes": ["MEDIA_REVIEW_REQUIRED", "HARD_VIOLATION"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS", "NO_HARD_VIOLATION"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "POLICY_OUT_OF_SCOPE", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

### GT-015 — Token thông tin khách hàng giả lập bị rule demo chặn

- Result: **PASS**; classification: `SYNTHETIC`; duration: 13 ms.
- Expected: `{"assigned_checker_id": "DEMO-CHECKER-01", "business_status": "PENDING_APPROVAL", "decision_source": null, "expected_app_execution_status": "NOT_RUN", "final_decision": null, "hard_violation_auto_reject_allowed": false, "primary_category": null, "processing_stage": "HUMAN_REVIEW_REQUIRED", "question_example": "Token khách hàng giả lập DEMO-0001 bị HV-DEMO-02 đánh dấu. Vui lòng xem bằng chứng và rule demo trước khi quyết định; ảnh không chứa dữ liệu cá nhân thật.", "question_required": true, "required_reason_codes": ["MEDIA_REVIEW_REQUIRED", "HARD_VIOLATION"], "route": "HUMAN_REVIEW_REQUIRED"}`
- Actual: `{"business_status": "PENDING_APPROVAL", "decision_source": null, "evaluation_status": "SUCCEEDED", "failed_rule_ids": ["MEDIA_PASS", "NO_HARD_VIOLATION"], "final_decision": null, "model_version": "role1-mock-adapter-v2.1", "primary_category": "POLICY_OUT_OF_SCOPE", "processing_stage": "HUMAN_REVIEW_REQUIRED", "provider": "MOCK_VLM", "question_count": 1, "route": "HUMAN_REVIEW_REQUIRED"}`
- Differences: none

## Fresh-input smoke — custom inputs outside the fixture catalog

Authored a new synthetic plan and a new 1×1 PNG in `runtime/verify-fresh-input-2026-10-09`; no Verify fixture or expected oracle was loaded. Both runs used the same synthetic VLM/Media/Strategy outputs and deliberately unchanged stale budget advisory (`IN_LIMIT`); only submitted budget, title and input metadata varied. The actual deterministic budget/policy rules recomputed the submitted amount.

| Input title (contains contradictory label) | Submitted budget | Input plan ID | Actual route | Failed rules | Final decision | Provider |
|---|---:|---|---|---|---|---|
| `HUMAN_REVIEW_REQUIRED label only` | 500,000 VND | `CUSTOM-ID-HUMAN_REVIEW_REQUIRED` | `AUTO_APPROVED` | `none` | `APPROVED` | `MOCK_VLM` |
| `AUTO_APPROVED label only` | 1,500,000 VND | `CUSTOM-ID-AUTO_APPROVED` | `HUMAN_REVIEW_REQUIRED` | `BUDGET_LIMIT, AUTHORITY_LIMIT` | `None` | `MOCK_VLM` |

The title `HUMAN_REVIEW_REQUIRED` did not prevent auto-approval at 500,000 VND; the title `AUTO_APPROVED` did not bypass Human Review at 1,500,000 VND. The latter went to review with `BUDGET_LIMIT` and `AUTHORITY_LIMIT` failing even though the mock budget advisory still said `IN_LIMIT`. This proves only the rule path against synthetic provider output, not model quality.

## Verify boundary audit

- `run_suite` sends only `case["input"]` to `execute_input`; fixture case ID/name are recorded for reporting after the workflow call. The expected-results file is now read only after all actual executions.
- `compare_observation` and `contract_result` run after execution and only label the Verify assertion result; neither is passed to `ApprovalWorkflow`, the orchestrator, provider, or Decision Policy Engine.
- `BAMockProvider` uses the synthetic `agent_outputs` as mock observations. Those values do affect the actual evaluation/decision and are not real model output. The actual plan/budget policy rules run in application code.

Artifacts for the custom smoke are under ignored `runtime/verify-fresh-input-2026-10-09/`; this report records the observed values and classification.
