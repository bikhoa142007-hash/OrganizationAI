# 17 · Danh mục dữ liệu demo và hướng dẫn seed cho app

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Scope §9, §12; Sprint §§1, 5.2, 6, 13. Seed và ảnh trong gói là tổng hợp.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Có gì trong data/

| Artifact | Nội dung | Mục đích |
|---|---|---|
| [base-policy.json](../../../tests/fixtures/role1/v2.1/base-policy.json) | Ngưỡng, trọng số, mode, limit demo | Seed profile v2 cần review OQ-01 |
| [ground-truth-cases.json](../../../tests/fixtures/role1/v2.1/ground-truth-cases.json) | 15 input đầy đủ + expected + actual null | Policy contract tests |
| [verify-inputs.json](../../../tests/fixtures/role1/v2.1/verify-inputs.json) | 5 input độc lập expected | Runner Verify |
| [verify-expected-results.json](../../../tests/fixtures/role1/v2.1/verify-expected-results.json) | Nhãn Verify riêng | Không gửi oracle vào engine |
| [fixture-manifest.json](../../../tests/fixtures/role1/v2.1/fixture-manifest.json) | SHA-256 của file dữ liệu/ảnh | Kiểm toàn vẹn artifact seed |
| [mock-provider-modes.json](../../../tests/fixtures/role1/v2.1/mock-provider-modes.json) | PASS, low confidence, timeout, invalid output | Mock VLM/fault injection test |
| fixtures/ | 7 PNG chữ tổng hợp, 1280×720 | Upload/demo có ảnh thật trên đĩa |

Các JSON là **fixture**, không phải migration hay code app. Cần map vào schema repo, seed auth bằng cơ chế dự án và nối test harness; không chỉ copy JSON vào production là có ứng dụng chạy.

## 2. Bộ tài khoản và quyền

Dùng DEMO-MAKER-01, DEMO-CHECKER-01, DEMO-ADMIN-01, DEMO-DUAL-01 như file 03. ID không chứa dữ liệu cá nhân thật. Role cố định cho Sprint; không bắt xây role builder. Mật khẩu demo/cách đăng nhập phải được đội triển khai tạo và ghi trong README môi trường demo, không giả định tài khoản đã tồn tại.

## 3. Giá trị policy/limit

- Dataset version ROLE1-DEMO-V2; policy DEMO-POLICY-V2; currency VND; scope DEMO-DEPT-01.
- Score >70, VLM≥0.85, Strategy≥0.80 theo nguồn; Media≥0.85 là profile đề xuất giải quyết khác biệt OQ-01.
- Limit L=100.000.000 VND **synthetic**, dùng mọi case; không có cap theo Lead/Manager.
- Effective time giả lập 2026-10-01 đến cuối 2026-12-31; submitted_at fixture 2026-10-01T02:00:00Z. Nếu chạy theo đồng hồ thực ngoài khoảng này, dùng test clock hoặc tạo seed version mới với thời gian phù hợp; không sửa ngầm hiệu lực policy sản xuất để ép pass.
- Criteria weights 15/15/15/15/15/15/10. Đồng nhất điểm criteria trong fixture chỉ nhằm có tổng chính xác, không phải rubric chấm nội dung thật.

## 4. Content rule demo

| ID | Rule synthetic | Expected Media/Decision |
|---|---|---|
| HV-DEMO-01 | Creative chứa token chính xác “CAM KẾT DEMO TUYỆT ĐỐI” bị policy demo cấm | REVIEW_REQUIRED + hard violation; human |
| HV-DEMO-02 | Creative chứa token “MÃ KHÁCH HÀNG GIẢ LẬP: DEMO-0001” bị policy demo chặn | REVIEW_REQUIRED + hard violation; human |
| SCOPE-DEMO-01 | DEMO-SPECIAL-DOMAIN chưa có mapping nội dung | REVIEW_REQUIRED, POLICY_OUT_OF_SCOPE |
| SCOPE-DEMO-02 | NewLiveChannel chưa có mapping nội dung | REVIEW_REQUIRED, POLICY_OUT_OF_SCOPE |

Đây không phải luật quảng cáo hay danh mục dữ liệu nhạy cảm thực. Không dùng token/demo rule làm hệ thống tuân thủ pháp luật sản xuất. Không có dữ liệu cá nhân thật trong ảnh.

## 5. Ảnh và provenance

| File | Nội dung | SHA-256 rút gọn |
|---|---|---|
| [creative-pass.png](../../../tests/fixtures/role1/v2.1/images/creative-pass.png) | CHIẾN DỊCH DEMO | db5193a49b36567a… |
| [budget-conflict.png](../../../tests/fixtures/role1/v2.1/images/budget-conflict.png) | NGÂN SÁCH CẦN ĐỐI CHIẾU | 6f0c5dc2a9edc284… |
| [kpi-conflict.png](../../../tests/fixtures/role1/v2.1/images/kpi-conflict.png) | KPI TRONG ẢNH DEMO | 13c73ad43b335d29… |
| [creative-low-quality.png](../../../tests/fixtures/role1/v2.1/images/creative-low-quality.png) | ẢNH DEMO CHẤT LƯỢNG THẤP | 4eb86ba25a3dcd82… |
| [scope-missing.png](../../../tests/fixtures/role1/v2.1/images/scope-missing.png) | PHẠM VI DEMO CHƯA CÓ POLICY | c588d0138629b371… |
| [hard-claim-demo.png](../../../tests/fixtures/role1/v2.1/images/hard-claim-demo.png) | VI PHẠM QUY TẮC DEMO | ca08398eb4e67de2… |
| [synthetic-private-demo.png](../../../tests/fixtures/role1/v2.1/images/synthetic-private-demo.png) | THÔNG TIN KHÁCH HÀNG GIẢ LẬP | 3e87fb31cd011af3… |

Hash đầy đủ nằm trong manifest và từng attachment fixture. Evidence bbox bao phủ vùng chữ chính của ảnh; observed_text lấy đúng chuỗi tạo ảnh. Confidence là số định trước trong mock, không phải confidence đã đo bằng Local VLM. Không có bộ ảnh tự nhiên/ground-truth OCR độc lập trong gói.

## 6. Thứ tự seed đề xuất

1. Users/permissions/department demo bằng cơ chế có sẵn.
2. Content policy demo và rubric/threshold/limit có version/effective time.
3. Upload/register ảnh, tính hash bytes, map attachment IDs; không dùng original filename làm identity.
4. Chọn provider MOCK và test clock/fixture scenario; không lẫn production/local configuration.
5. Với contract tests: nạp plan snapshot/context/output được đặt trước. Với E2E: tạo DRAFT thật, upload, submit qua workflow thật, để backend sinh version/round/hash/ID rồi ghi mapping.
6. Đọc expected ở runner riêng; engine không đọc file oracle. Lưu actual ở test output/report riêng.
7. Reset chỉ namespace/database demo theo repo; không xóa audit production hoặc ghi đè file nguồn.

## 7. Phân biệt ba tầng dữ liệu kiểm thử

**Contract:** output VLM/Media/Strategy được fixture đặt trước; chứng minh gate/route. **Workflow E2E với Mock VLM:** adapter giả lập VLM, các module khác thật hoặc stub có nhãn riêng; chứng minh luồng/quyền/persistence. **Local VLM thật:** ảnh chạy qua model/hardware thật; phải lưu output/latency và gán nhãn independent để đánh giá OCR/quality. Một tầng pass không chứng minh các tầng khác pass.

Sprint bắt buộc có Mock VLM; mock Strategy/Media trong fixture chỉ là cơ chế test ở layer contract, không thay yêu cầu triển khai hai agent đó. Không tính kết quả mock là chất lượng của model thật.

## 8. Các danh mục chưa phải master data thật

Kênh DEMO_SOCIAL/DEMO_WEBINAR, bộ phận DEMO-DEPT-01, người dùng DEMO-*, token guideline và KPI đều synthetic. Danh sách channel/industry/brand thật, budget owner và policy approval chưa được cung cấp. Giữ trường/enum mở theo thiết kế repo, không khóa giá trị doanh nghiệp vào danh mục demo.

## Seed v2.1

PNG giữ nguyên bytes. GT-009 thay mock OCR hoàn chỉnh bằng partial extraction công khai; không nói Local VLM đã đọc lỗi ảnh này. Đây là contract/fault-injection fixture. Benchmark thật cần chạy model và gán nhãn riêng.

File thêm: fact-verification.schema.json (proposal), wp1-wp2-mapping-status.json (NOT_VERIFIED), changes-v2.1.json (diff chính xác), tools/validate_package.py (artifact validator). Đọc file 19 trước khi nạp API; không giả định engine nhận unknown fields.
