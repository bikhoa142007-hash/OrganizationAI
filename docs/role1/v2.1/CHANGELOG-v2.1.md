# Changelog v2.1 — diff chính xác theo ZIP người dùng

Baseline: Role1_Sprint1_v2.zip tại Downloads, SHA-256: 096549169b53b84d4b3f68d5ce7c535c59e57355132b7d8a32b1e617fe583e43.

## Quyết định

Giữ phương án A cho GT-007/008/009 và VERIFY-A04: FACT_UNCERTAIN. Outcome HUMAN_REVIEW_REQUIRED; final/source null. Bổ sung fact evidence rõ, không đổi business policy/limit/threshold hoặc media confidence/result để ép pass.

**Giới hạn:** extension fixture là đề xuất; chưa nhận schema WP1/WP2 nên chưa xác nhận drop-in compatibility/engine pass. Actual NOT_RUN. [Chi tiết tích hợp](19-wp1-wp2-mapping-and-regression.md).

## Tóm tắt theo case

| Case | Sửa input | Sửa expected |
|---|---|---|
| GT-007 | Conflict budget 50m/120m/180m với source pointers/evidence, unresolved; hash evaluation | Giữ FACT_UNCERTAIN; rationale, policy refs, explanation requirements; bỏ media-only reason bắt buộc |
| GT-008 | Conflict KPI1200/12000; giữ OCR .90; hash evaluation | Giữ FACT_UNCERTAIN; rationale/refs; không suy policy-scope |
| GT-009 | Mock partial OCR, is_complete=false, vùng evidence đúng dòng; verified_value null | Giữ FACT_UNCERTAIN; nêu incomplete text, không bịa claim/disclaimer |
| VERIFY-A04 | Materialize GT-007, chỉ đổi identity/hashes; giữ cùng evidence IDs | expected deep-equal GT-007 |

AUTO_APPROVE trong legacy route được sửa spelling thành AUTO_APPROVED theo catalog người dùng: 6 GT auto, 3 Verify expected auto và 1 mock mode. Không đổi 6/9 hay 3/2 phân bổ nghiệp vụ.

## Những trường giữ nguyên

Base-policy bytes, mọi policy_snapshot, scores/weights, confidence VLM/Media/Strategy, form budgets, limit, media.result, policy_scope_covered, unresolved_conflict_count, attachment PNG bytes và hai nguồn Scope/Sprint. Unrelated GT inputs và Verify inputs ngoài A04 không đổi. Các thay đổi route spelling được ghi riêng dưới đây.

## Diff từng field

JSON Pointer trỏ vào root của từng file. ABSENT nghĩa chưa có field, khác null. Giá trị dưới đây lấy từ diff tự động, không gõ lại. Object mới được tách đến leaf; danh sách bị thay được ghi nguyên before/after. Bản machine-readable gồm các patch đầy đủ tại [changes-v2.1.json](../archive/v2.1/data/changes-v2.1.json).

### data/fixture-manifest.json

| Operation | JSON Pointer | Before | After |
|---|---|---|---|
| add | /artifact_revision | ABSENT | "2.1" |
| add | /business_policy_version_unchanged | ABSENT | "2.0" |
| add | /wp1_wp2_compatibility_status | ABSENT | "NOT_VERIFIED" |
| replace | /dataset_version | "ROLE1-DEMO-V2" | "ROLE1-DEMO-V2.1" |
| replace | /files | [{"path":"data/base-policy.json","sha256":"94ffd06c66d4df4bade1275f46ff33fe0b274e20ea5156f561144e97b66464bb"},{"path":"data/ground-truth-cases.json","sha256":"ac344004b4038620b2f21a9b38a272b3c6df76be80f0ee594981a11d5792e29d"},{"path":"data/verify-inputs.json","sha256":"d54e396c1b0bb271d2a88af4db816b881a6e2f4bc95807fd089dc37405d178e4"},{"path":"data/verify-expected-results.json","sha256":"00457ede32006ebeeba14515d433490c44cb86c80261b16b9b88695bb67958af"}] | [{"path":"data/base-policy.json","sha256":"94ffd06c66d4df4bade1275f46ff33fe0b274e20ea5156f561144e97b66464bb"},{"path":"data/ground-truth-cases.json","sha256":"d7ccf17e7cf974b17209569309d4e1abd3dcca321b850e74f66beb7d908c43e0"},{"path":"data/verify-inputs.json","sha256":"9a6740620ba714383660b0438fb324529c93b95955bba73646aff16085de8b41"},{"path":"data/verify-expected-results.json","sha256":"0e109a6c64f2fc1473076ae6083e053ef385c61ec89388500814e10d8ca123bd"},{"path":"data/fact-verification.schema.json","sha256":"bbf6a148c7d998400aba8e1f719ebd205f837e633eefedc9342077da80e50f38"},{"path":"data/wp1-wp2-mapping-status.json","sha256":"18adbaac2a0e806f25fdaa8e447ef6ee4c5776309dd6661a7915d8895856dee5"}] |

### data/ground-truth-cases.json

| Operation | JSON Pointer | Before | After |
|---|---|---|---|
| replace | /0/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| replace | /1/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| replace | /2/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| replace | /3/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| replace | /4/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| replace | /5/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| add | /6/expected/explanation_requirements/affected_fields/0 | ABSENT | "budget_vnd" |
| add | /6/expected/explanation_requirements/issue_types/0 | ABSENT | "CONFLICTING_VALUES" |
| add | /6/expected/explanation_requirements/required_evidence_refs/0 | ABSENT | "E-GT-007" |
| add | /6/expected/explanation_requirements/required_factual_issue_refs/0 | ABSENT | "ISSUE-GT-007-01" |
| add | /6/expected/explanation_requirements/must_describe_unresolved_fact | ABSENT | true |
| add | /6/expected/explanation_requirements/media_result_alone_is_insufficient | ABSENT | true |
| add | /6/expected/explanation_requirements/wp_runtime_code_mapping_status | ABSENT | "NOT_VERIFIED" |
| add | /6/expected/policy_references/0/source | ABSENT | "sources/scope-phase-1.md" |
| add | /6/expected/policy_references/0/reference | ABSENT | "BR-AI-10" |
| add | /6/expected/policy_references/0/supports | ABSENT | "Confidence thấp/kết quả thiếu phải chuyển Human Review." |
| add | /6/expected/policy_references/1/source | ABSENT | "sources/sprint-1-deliverables.md" |
| add | /6/expected/policy_references/1/reference | ABSENT | "§4: unresolved_conflict_count = 0" |
| add | /6/expected/policy_references/1/supports | ABSENT | "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping." |
| add | /6/expected/policy_references/2/source | ABSENT | "04-escalation-policy.md" |
| add | /6/expected/policy_references/2/reference | ABSENT | "FACT_UNCERTAIN / precedence" |
| add | /6/expected/policy_references/2/supports | ABSENT | "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi." |
| add | /6/expected/policy_references/3/source | ABSENT | "18-fact-uncertainty-correction.md" |
| add | /6/expected/policy_references/3/reference | ABSENT | "R1-FIX-CONFLICT-01" |
| add | /6/expected/policy_references/3/supports | ABSENT | "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2." |
| add | /6/expected/rationale | ABSENT | "Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR." |
| replace | /6/expected/question_example | "Form ghi 50.000.000 VND nhưng ảnh nêu 120.000.000 và 180.000.000 VND, VLM confidence 0,61. Vui lòng đối chiếu ảnh gốc và ghi căn cứ; nếu nội dung cần sửa, từ chối để Maker gửi phiên bản mới." | "Form ghi 50.000.000 VND, ảnh nêu phương án A 120.000.000 và B 180.000.000 VND. Hãy đối chiếu E-GT-007 và xác định ngân sách chính thức. Nếu cần sửa hồ sơ, từ chối có lý do để Maker gửi phiên bản mới." |
| replace | /6/expected/required_reason_codes | ["VLM_LOW_CONFIDENCE","MEDIA_CONFIDENCE_BELOW_THRESHOLD","MEDIA_REVIEW_REQUIRED","UNRESOLVED_CONFLICT"] | ["VLM_LOW_CONFIDENCE","UNRESOLVED_CONFLICT"] |
| add | /6/input/evaluation_fixture_hash | ABSENT | "f2e1598cd6b216f805bbbce5f72adc3ec1f6874f68b193a09f63a0848751fe35" |
| add | /6/input/fact_verification/schema_version | ABSENT | "role1.fact-verification/1.0-proposed" |
| add | /6/input/fact_verification/verification_status | ABSENT | "UNCERTAIN" |
| add | /6/input/fact_verification/assertion_origin | ABSENT | "SYNTHETIC_FIXTURE" |
| add | /6/input/fact_verification/issues/0/issue_id | ABSENT | "ISSUE-GT-007-01" |
| add | /6/input/fact_verification/issues/0/field | ABSENT | "budget_vnd" |
| add | /6/input/fact_verification/issues/0/affected_input_pointer | ABSENT | "/plan_snapshot/budget_vnd" |
| add | /6/input/fact_verification/issues/0/issue_type | ABSENT | "CONFLICTING_VALUES" |
| add | /6/input/fact_verification/issues/0/status | ABSENT | "UNRESOLVED" |
| add | /6/input/fact_verification/issues/0/verified_value | ABSENT | null |
| add | /6/input/fact_verification/issues/0/sources/0/kind | ABSENT | "PLAN_FIELD" |
| add | /6/input/fact_verification/issues/0/sources/0/pointer | ABSENT | "/plan_snapshot/budget_vnd" |
| add | /6/input/fact_verification/issues/0/sources/0/observed_value | ABSENT | 50000000 |
| add | /6/input/fact_verification/issues/0/sources/0/normalized_value | ABSENT | 50000000 |
| add | /6/input/fact_verification/issues/0/sources/0/evidence_ref | ABSENT | null |
| add | /6/input/fact_verification/issues/0/sources/1/kind | ABSENT | "VLM_EVIDENCE" |
| add | /6/input/fact_verification/issues/0/sources/1/pointer | ABSENT | "/agent_outputs/vlm/evidence/0/observed_text" |
| add | /6/input/fact_verification/issues/0/sources/1/observed_value | ABSENT | "Phương án A: 120.000.000 VND" |
| add | /6/input/fact_verification/issues/0/sources/1/normalized_value | ABSENT | 120000000 |
| add | /6/input/fact_verification/issues/0/sources/1/evidence_ref | ABSENT | "E-GT-007" |
| add | /6/input/fact_verification/issues/0/sources/2/kind | ABSENT | "VLM_EVIDENCE" |
| add | /6/input/fact_verification/issues/0/sources/2/pointer | ABSENT | "/agent_outputs/vlm/evidence/0/observed_text" |
| add | /6/input/fact_verification/issues/0/sources/2/observed_value | ABSENT | "Phương án B: 180.000.000 VND" |
| add | /6/input/fact_verification/issues/0/sources/2/normalized_value | ABSENT | 180000000 |
| add | /6/input/fact_verification/issues/0/sources/2/evidence_ref | ABSENT | "E-GT-007" |
| add | /6/input/fact_verification/issues/0/evidence_refs/0 | ABSENT | "E-GT-007" |
| add | /6/input/fact_verification/issues/0/rationale | ABSENT | "Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR." |
| add | /6/input/fact_verification/issues/0/fixture_rule_ref | ABSENT | "R1-FIX-CONFLICT-01" |
| add | /6/input/agent_outputs/vlm/evidence/0/fact_verification_status | ABSENT | "UNRESOLVED" |
| add | /6/input/agent_outputs/vlm/evidence/0/factual_issue_refs/0 | ABSENT | "ISSUE-GT-007-01" |
| add | /7/expected/explanation_requirements/affected_fields/0 | ABSENT | "kpi_expected" |
| add | /7/expected/explanation_requirements/issue_types/0 | ABSENT | "CONFLICTING_VALUES" |
| add | /7/expected/explanation_requirements/required_evidence_refs/0 | ABSENT | "E-GT-008" |
| add | /7/expected/explanation_requirements/required_factual_issue_refs/0 | ABSENT | "ISSUE-GT-008-01" |
| add | /7/expected/explanation_requirements/must_describe_unresolved_fact | ABSENT | true |
| add | /7/expected/explanation_requirements/media_result_alone_is_insufficient | ABSENT | true |
| add | /7/expected/explanation_requirements/wp_runtime_code_mapping_status | ABSENT | "NOT_VERIFIED" |
| add | /7/expected/policy_references/0/source | ABSENT | "sources/scope-phase-1.md" |
| add | /7/expected/policy_references/0/reference | ABSENT | "BR-AI-10" |
| add | /7/expected/policy_references/0/supports | ABSENT | "Confidence thấp/kết quả thiếu phải chuyển Human Review." |
| add | /7/expected/policy_references/1/source | ABSENT | "sources/sprint-1-deliverables.md" |
| add | /7/expected/policy_references/1/reference | ABSENT | "§4: unresolved_conflict_count = 0" |
| add | /7/expected/policy_references/1/supports | ABSENT | "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping." |
| add | /7/expected/policy_references/2/source | ABSENT | "04-escalation-policy.md" |
| add | /7/expected/policy_references/2/reference | ABSENT | "FACT_UNCERTAIN / precedence" |
| add | /7/expected/policy_references/2/supports | ABSENT | "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi." |
| add | /7/expected/policy_references/3/source | ABSENT | "18-fact-uncertainty-correction.md" |
| add | /7/expected/policy_references/3/reference | ABSENT | "R1-FIX-CONFLICT-01" |
| add | /7/expected/policy_references/3/supports | ABSENT | "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2." |
| add | /7/expected/rationale | ABSENT | "Form/KPI nêu 1.200 lượt đăng ký, trong khi dòng KPI chính trên ảnh nêu 12.000 lượt đăng ký. Confidence OCR 0,90 không giải quyết được xung đột liên nguồn. Chưa xác định target chính thức; không đổi score/confidence để ép case." |
| replace | /7/expected/question_example | "Form ghi 1.200 lượt đăng ký còn ảnh ghi 12.000. Vui lòng xác định căn cứ KPI được thẩm định hoặc từ chối để Maker sửa và gửi lại." | "Form ghi 1.200 lượt đăng ký, dòng KPI trên ảnh E-GT-008 ghi 12.000. Hãy xác định target được thẩm định và căn cứ. Nếu nội dung phải sửa, từ chối để Maker gửi phiên bản mới." |
| replace | /7/expected/required_reason_codes | ["MEDIA_REVIEW_REQUIRED","UNRESOLVED_CONFLICT"] | ["UNRESOLVED_CONFLICT"] |
| add | /7/input/evaluation_fixture_hash | ABSENT | "180ad61f4837526c3cf596ad14ef70f241d83179a26d728a9e848b41d258b8a5" |
| add | /7/input/fact_verification/schema_version | ABSENT | "role1.fact-verification/1.0-proposed" |
| add | /7/input/fact_verification/verification_status | ABSENT | "UNCERTAIN" |
| add | /7/input/fact_verification/assertion_origin | ABSENT | "SYNTHETIC_FIXTURE" |
| add | /7/input/fact_verification/issues/0/issue_id | ABSENT | "ISSUE-GT-008-01" |
| add | /7/input/fact_verification/issues/0/field | ABSENT | "kpi_expected" |
| add | /7/input/fact_verification/issues/0/affected_input_pointer | ABSENT | "/plan_snapshot/kpi_expected" |
| add | /7/input/fact_verification/issues/0/issue_type | ABSENT | "CONFLICTING_VALUES" |
| add | /7/input/fact_verification/issues/0/status | ABSENT | "UNRESOLVED" |
| add | /7/input/fact_verification/issues/0/verified_value | ABSENT | null |
| add | /7/input/fact_verification/issues/0/sources/0/kind | ABSENT | "PLAN_FIELD" |
| add | /7/input/fact_verification/issues/0/sources/0/pointer | ABSENT | "/plan_snapshot/kpi_expected" |
| add | /7/input/fact_verification/issues/0/sources/0/observed_value | ABSENT | "1.200 lượt đăng ký trước 2026-10-30" |
| add | /7/input/fact_verification/issues/0/sources/0/normalized_value | ABSENT | 1200 |
| add | /7/input/fact_verification/issues/0/sources/0/evidence_ref | ABSENT | null |
| add | /7/input/fact_verification/issues/0/sources/1/kind | ABSENT | "VLM_EVIDENCE" |
| add | /7/input/fact_verification/issues/0/sources/1/pointer | ABSENT | "/agent_outputs/vlm/evidence/0/observed_text" |
| add | /7/input/fact_verification/issues/0/sources/1/observed_value | ABSENT | "Mục tiêu: 12.000 lượt đăng ký" |
| add | /7/input/fact_verification/issues/0/sources/1/normalized_value | ABSENT | 12000 |
| add | /7/input/fact_verification/issues/0/sources/1/evidence_ref | ABSENT | "E-GT-008" |
| add | /7/input/fact_verification/issues/0/evidence_refs/0 | ABSENT | "E-GT-008" |
| add | /7/input/fact_verification/issues/0/rationale | ABSENT | "Form/KPI nêu 1.200 lượt đăng ký, trong khi dòng KPI chính trên ảnh nêu 12.000 lượt đăng ký. Confidence OCR 0,90 không giải quyết được xung đột liên nguồn. Chưa xác định target chính thức; không đổi score/confidence để ép case." |
| add | /7/input/fact_verification/issues/0/fixture_rule_ref | ABSENT | "R1-FIX-CONFLICT-01" |
| add | /7/input/agent_outputs/vlm/evidence/0/fact_verification_status | ABSENT | "UNRESOLVED" |
| add | /7/input/agent_outputs/vlm/evidence/0/factual_issue_refs/0 | ABSENT | "ISSUE-GT-008-01" |
| add | /8/expected/explanation_requirements/affected_fields/0 | ABSENT | "creative_text" |
| add | /8/expected/explanation_requirements/issue_types/0 | ABSENT | "INCOMPLETE_EXTRACTION" |
| add | /8/expected/explanation_requirements/required_evidence_refs/0 | ABSENT | "E-GT-009" |
| add | /8/expected/explanation_requirements/required_factual_issue_refs/0 | ABSENT | "ISSUE-GT-009-01" |
| add | /8/expected/explanation_requirements/must_describe_unresolved_fact | ABSENT | true |
| add | /8/expected/explanation_requirements/media_result_alone_is_insufficient | ABSENT | true |
| add | /8/expected/explanation_requirements/wp_runtime_code_mapping_status | ABSENT | "NOT_VERIFIED" |
| add | /8/expected/policy_references/0/source | ABSENT | "sources/scope-phase-1.md" |
| add | /8/expected/policy_references/0/reference | ABSENT | "BR-AI-10" |
| add | /8/expected/policy_references/0/supports | ABSENT | "Confidence thấp/kết quả thiếu phải chuyển Human Review." |
| add | /8/expected/policy_references/1/source | ABSENT | "sources/sprint-1-deliverables.md" |
| add | /8/expected/policy_references/1/reference | ABSENT | "§4: unresolved_conflict_count = 0" |
| add | /8/expected/policy_references/1/supports | ABSENT | "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping." |
| add | /8/expected/policy_references/2/source | ABSENT | "04-escalation-policy.md" |
| add | /8/expected/policy_references/2/reference | ABSENT | "FACT_UNCERTAIN / precedence" |
| add | /8/expected/policy_references/2/supports | ABSENT | "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi." |
| add | /8/expected/policy_references/3/source | ABSENT | "18-fact-uncertainty-correction.md" |
| add | /8/expected/policy_references/3/reference | ABSENT | "R1-FIX-INCOMPLETE-01" |
| add | /8/expected/policy_references/3/supports | ABSENT | "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2." |
| add | /8/expected/rationale | ABSENT | "Mock OCR chỉ trả phần đầu 'Thông điệp'; phần còn lại của dòng chưa được xác minh. Case mô phỏng trích xuất không đầy đủ, không khẳng định một model thật đã chạy hoặc ảnh chứa claim/disclaimer vi phạm. creative_text chưa đủ bằng chứng nên cần human review." |
| replace | /8/expected/question_example | "VLM confidence 0,72 thấp hơn 0,85. Vui lòng đọc lại ảnh gốc và xác nhận bằng chứng đủ cho quyết định; không suy đoán phần chữ chưa rõ." | "Kết quả OCR E-GT-009 chỉ xác minh phần đầu 'Thông điệp', chưa xác minh phần còn lại (confidence 0,72). Hãy đọc ảnh gốc hoặc yêu cầu Maker gửi ảnh/phiên bản đủ rõ qua luồng từ chối và gửi lại." |
| replace | /8/expected/required_reason_codes | ["VLM_LOW_CONFIDENCE","MEDIA_REVIEW_REQUIRED"] | ["VLM_LOW_CONFIDENCE"] |
| add | /8/input/evaluation_fixture_hash | ABSENT | "6115a418c1a0e815fc3788ed0fb9c0a9746ab10b94f72fe71ec8b1d300ab5bb6" |
| add | /8/input/fact_verification/schema_version | ABSENT | "role1.fact-verification/1.0-proposed" |
| add | /8/input/fact_verification/verification_status | ABSENT | "UNCERTAIN" |
| add | /8/input/fact_verification/assertion_origin | ABSENT | "SYNTHETIC_FIXTURE" |
| add | /8/input/fact_verification/issues/0/issue_id | ABSENT | "ISSUE-GT-009-01" |
| add | /8/input/fact_verification/issues/0/field | ABSENT | "creative_text" |
| add | /8/input/fact_verification/issues/0/affected_input_pointer | ABSENT | "/agent_outputs/vlm/evidence/0/observed_text" |
| add | /8/input/fact_verification/issues/0/issue_type | ABSENT | "INCOMPLETE_EXTRACTION" |
| add | /8/input/fact_verification/issues/0/status | ABSENT | "UNRESOLVED" |
| add | /8/input/fact_verification/issues/0/verified_value | ABSENT | null |
| add | /8/input/fact_verification/issues/0/sources/0/kind | ABSENT | "VLM_EVIDENCE" |
| add | /8/input/fact_verification/issues/0/sources/0/pointer | ABSENT | "/agent_outputs/vlm/evidence/0/observed_text" |
| add | /8/input/fact_verification/issues/0/sources/0/observed_value | ABSENT | "Thông điệp [phần còn lại chưa xác minh]" |
| add | /8/input/fact_verification/issues/0/sources/0/normalized_value | ABSENT | null |
| add | /8/input/fact_verification/issues/0/sources/0/evidence_ref | ABSENT | "E-GT-009" |
| add | /8/input/fact_verification/issues/0/evidence_refs/0 | ABSENT | "E-GT-009" |
| add | /8/input/fact_verification/issues/0/rationale | ABSENT | "Mock OCR chỉ trả phần đầu 'Thông điệp'; phần còn lại của dòng chưa được xác minh. Case mô phỏng trích xuất không đầy đủ, không khẳng định một model thật đã chạy hoặc ảnh chứa claim/disclaimer vi phạm. creative_text chưa đủ bằng chứng nên cần human review." |
| add | /8/input/fact_verification/issues/0/fixture_rule_ref | ABSENT | "R1-FIX-INCOMPLETE-01" |
| add | /8/input/agent_outputs/vlm/evidence/0/extraction_mode | ABSENT | "MOCK_PARTIAL_OCR" |
| add | /8/input/agent_outputs/vlm/evidence/0/fact_verification_status | ABSENT | "UNVERIFIED" |
| add | /8/input/agent_outputs/vlm/evidence/0/factual_issue_refs/0 | ABSENT | "ISSUE-GT-009-01" |
| add | /8/input/agent_outputs/vlm/evidence/0/is_complete | ABSENT | false |
| replace | /8/input/agent_outputs/vlm/evidence/0/bbox_normalized/0 | 0.02 | 0.025 |
| replace | /8/input/agent_outputs/vlm/evidence/0/bbox_normalized/1 | 0.15 | 0.33 |
| replace | /8/input/agent_outputs/vlm/evidence/0/bbox_normalized/2 | 0.98 | 0.975 |
| replace | /8/input/agent_outputs/vlm/evidence/0/bbox_normalized/3 | 0.84 | 0.44 |
| replace | /8/input/agent_outputs/vlm/evidence/0/observed_text | "Thông điệp cần được đọc lại từ ảnh gốc. &#124; Không suy đoán phần chữ không rõ. &#124; Confidence thấp được đặt trong fixture test." | "Thông điệp [phần còn lại chưa xác minh]" |
| replace | /8/input/agent_outputs/vlm/quality_flags | ["LOW_CONFIDENCE"] | ["LOW_CONFIDENCE","INCOMPLETE_TEXT_EXTRACTION"] |

### data/mock-provider-modes.json

| Operation | JSON Pointer | Before | After |
|---|---|---|---|
| replace | /0/expected_route | "AUTO_APPROVE" | "AUTO_APPROVED" |

### data/verify-expected-results.json

| Operation | JSON Pointer | Before | After |
|---|---|---|---|
| replace | /0/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| replace | /1/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| replace | /2/expected/route | "AUTO_APPROVE" | "AUTO_APPROVED" |
| add | /3/expected/explanation_requirements/affected_fields/0 | ABSENT | "budget_vnd" |
| add | /3/expected/explanation_requirements/issue_types/0 | ABSENT | "CONFLICTING_VALUES" |
| add | /3/expected/explanation_requirements/required_evidence_refs/0 | ABSENT | "E-GT-007" |
| add | /3/expected/explanation_requirements/required_factual_issue_refs/0 | ABSENT | "ISSUE-GT-007-01" |
| add | /3/expected/explanation_requirements/must_describe_unresolved_fact | ABSENT | true |
| add | /3/expected/explanation_requirements/media_result_alone_is_insufficient | ABSENT | true |
| add | /3/expected/explanation_requirements/wp_runtime_code_mapping_status | ABSENT | "NOT_VERIFIED" |
| add | /3/expected/policy_references/0/source | ABSENT | "sources/scope-phase-1.md" |
| add | /3/expected/policy_references/0/reference | ABSENT | "BR-AI-10" |
| add | /3/expected/policy_references/0/supports | ABSENT | "Confidence thấp/kết quả thiếu phải chuyển Human Review." |
| add | /3/expected/policy_references/1/source | ABSENT | "sources/sprint-1-deliverables.md" |
| add | /3/expected/policy_references/1/reference | ABSENT | "§4: unresolved_conflict_count = 0" |
| add | /3/expected/policy_references/1/supports | ABSENT | "Conflict chưa giải quyết chặn auto; không chứng minh thiếu policy mapping." |
| add | /3/expected/policy_references/2/source | ABSENT | "04-escalation-policy.md" |
| add | /3/expected/policy_references/2/reference | ABSENT | "FACT_UNCERTAIN / precedence" |
| add | /3/expected/policy_references/2/supports | ABSENT | "Taxonomy kế thừa: fact chưa chắc được phân biệt với policy ngoài phạm vi." |
| add | /3/expected/policy_references/3/source | ABSENT | "18-fact-uncertainty-correction.md" |
| add | /3/expected/policy_references/3/reference | ABSENT | "R1-FIX-CONFLICT-01" |
| add | /3/expected/policy_references/3/supports | ABSENT | "Quy tắc dữ liệu fixture bổ sung; chưa phải rule ID runtime WP1/WP2." |
| add | /3/expected/rationale | ABSENT | "Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR." |
| replace | /3/expected/question_example | "Form ghi 50.000.000 VND nhưng ảnh nêu 120.000.000 và 180.000.000 VND, VLM confidence 0,61. Vui lòng đối chiếu ảnh gốc và ghi căn cứ; nếu nội dung cần sửa, từ chối để Maker gửi phiên bản mới." | "Form ghi 50.000.000 VND, ảnh nêu phương án A 120.000.000 và B 180.000.000 VND. Hãy đối chiếu E-GT-007 và xác định ngân sách chính thức. Nếu cần sửa hồ sơ, từ chối có lý do để Maker gửi phiên bản mới." |
| replace | /3/expected/required_reason_codes | ["VLM_LOW_CONFIDENCE","MEDIA_CONFIDENCE_BELOW_THRESHOLD","MEDIA_REVIEW_REQUIRED","UNRESOLVED_CONFLICT"] | ["VLM_LOW_CONFIDENCE","UNRESOLVED_CONFLICT"] |

### data/verify-inputs.json

| Operation | JSON Pointer | Before | After |
|---|---|---|---|
| add | /3/input/evaluation_fixture_hash | ABSENT | "3a8047a76ef12cef3fafa732582b8cd1358a27cf3a9ef14acd65cb017bdaa467" |
| add | /3/input/fact_verification/schema_version | ABSENT | "role1.fact-verification/1.0-proposed" |
| add | /3/input/fact_verification/verification_status | ABSENT | "UNCERTAIN" |
| add | /3/input/fact_verification/assertion_origin | ABSENT | "SYNTHETIC_FIXTURE" |
| add | /3/input/fact_verification/issues/0/issue_id | ABSENT | "ISSUE-GT-007-01" |
| add | /3/input/fact_verification/issues/0/field | ABSENT | "budget_vnd" |
| add | /3/input/fact_verification/issues/0/affected_input_pointer | ABSENT | "/plan_snapshot/budget_vnd" |
| add | /3/input/fact_verification/issues/0/issue_type | ABSENT | "CONFLICTING_VALUES" |
| add | /3/input/fact_verification/issues/0/status | ABSENT | "UNRESOLVED" |
| add | /3/input/fact_verification/issues/0/verified_value | ABSENT | null |
| add | /3/input/fact_verification/issues/0/sources/0/kind | ABSENT | "PLAN_FIELD" |
| add | /3/input/fact_verification/issues/0/sources/0/pointer | ABSENT | "/plan_snapshot/budget_vnd" |
| add | /3/input/fact_verification/issues/0/sources/0/observed_value | ABSENT | 50000000 |
| add | /3/input/fact_verification/issues/0/sources/0/normalized_value | ABSENT | 50000000 |
| add | /3/input/fact_verification/issues/0/sources/0/evidence_ref | ABSENT | null |
| add | /3/input/fact_verification/issues/0/sources/1/kind | ABSENT | "VLM_EVIDENCE" |
| add | /3/input/fact_verification/issues/0/sources/1/pointer | ABSENT | "/agent_outputs/vlm/evidence/0/observed_text" |
| add | /3/input/fact_verification/issues/0/sources/1/observed_value | ABSENT | "Phương án A: 120.000.000 VND" |
| add | /3/input/fact_verification/issues/0/sources/1/normalized_value | ABSENT | 120000000 |
| add | /3/input/fact_verification/issues/0/sources/1/evidence_ref | ABSENT | "E-GT-007" |
| add | /3/input/fact_verification/issues/0/sources/2/kind | ABSENT | "VLM_EVIDENCE" |
| add | /3/input/fact_verification/issues/0/sources/2/pointer | ABSENT | "/agent_outputs/vlm/evidence/0/observed_text" |
| add | /3/input/fact_verification/issues/0/sources/2/observed_value | ABSENT | "Phương án B: 180.000.000 VND" |
| add | /3/input/fact_verification/issues/0/sources/2/normalized_value | ABSENT | 180000000 |
| add | /3/input/fact_verification/issues/0/sources/2/evidence_ref | ABSENT | "E-GT-007" |
| add | /3/input/fact_verification/issues/0/evidence_refs/0 | ABSENT | "E-GT-007" |
| add | /3/input/fact_verification/issues/0/rationale | ABSENT | "Ngân sách khai báo trong form là 50.000.000 VND, còn ảnh có hai phương án 120.000.000 và 180.000.000 VND. Chưa có bằng chứng lựa chọn phương án chính thức. Đây là xung đột giá trị budget_vnd, không phải thiếu mapping policy. Giữ form hợp lệ; không tự thay ngân sách bằng OCR." |
| add | /3/input/fact_verification/issues/0/fixture_rule_ref | ABSENT | "R1-FIX-CONFLICT-01" |
| add | /3/input/agent_outputs/vlm/evidence/0/fact_verification_status | ABSENT | "UNRESOLVED" |
| add | /3/input/agent_outputs/vlm/evidence/0/factual_issue_refs/0 | ABSENT | "ISSUE-GT-007-01" |

## File thêm và tài liệu đồng bộ

- data/fact-verification.schema.json: proposal shape, không phải schema WP đã trích.
- data/wp1-wp2-mapping-status.json: target mapping chưa xác định, block silent dropping.
- data/changes-v2.1.json: baseline hash và before/after chính xác.
- 18-fact-uncertainty-correction.md và 19-wp1-wp2-mapping-and-regression.md.
- tools/validate_package.py, regression-results.json và validation-report.md: kiểm artifact có phạm vi rõ.
- 00-index.md: tạo lại vì ZIP đầu vào không chứa index.
- Các tài liệu root đồng bộ route spelling/revision; 05 thay hẳn ba card để không có dữ liệu cũ mâu thuẫn; 08 sửa A04; các contract/seed/test docs bổ sung hướng dẫn.
- PDF có sẵn chuyển vào legacy/ với README, giữ nguyên bytes, không dùng làm oracle v2.1.

Chi tiết thay đổi văn bản cũ có tại [docs-v2.1.diff](../archive/v2.1/changes/docs-v2.1.diff). Đây không phải patch code engine. Tổng field leaf-level changes ghi trong bảng: 216.

## Điều kiện nghiệm thu

Artifact validator pass chỉ xác nhận dữ liệu/diff/parity. Để xác nhận sửa lỗi trên app: cần schema WP1/WP2, adapter và engine thật; chạy ma trận FIX-01..12, giữ actual request/normalized input/output/rules/evidence. Không đổi expected để khớp một output sai nghiệp vụ.
