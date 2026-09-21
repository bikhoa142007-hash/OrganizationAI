# 06 · Catalog kiểm thử nghiệp vụ và ca biên

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Sprint §9 đủ 18 mục; Scope §18 và Business Rules.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Cách sử dụng

ST-01..ST-18 giữ nguyên thứ tự 18 yêu cầu kiểm thử trong Sprint. Đây là đặc tả kiểm thử cho app, không phải báo cáo test đã pass. GT/Verify kiểm tra policy bằng structured fixture; ST kiểm tra cả workflow, quyền, persistence và concurrency.

Chạy trên cơ sở dữ liệu demo tách biệt, một namespace/session riêng; reset dữ liệu theo cơ chế seed của repo. Mỗi biến thể có policy snapshot/case input riêng, không sửa expected trong lúc thực thi. HTTP status cụ thể theo convention repo; 401/403/409/422 là lựa chọn triển khai cần chốt, không phải các mã đã được nguồn quy định.

## 2. Mười tám test bắt buộc

### ST-01 · Lưu nháp thiếu dữ liệu

- **Given:** Maker có quyền; form chỉ có tên hoặc còn trống.
- **When:** Lưu nháp.
- **Then:** Lưu DRAFT; không tạo version đã gửi, round hoặc AI run.
- **Nguồn:** BR-PLAN-02/03; Sprint §9, ca số 1.
- **Lưu ý:** Giá trị đã nhập sai kiểu vẫn phải bị báo lỗi.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-02 · Submit thiếu dữ liệu

- **Given:** DRAFT; lần lượt bỏ name, objective, summary, dates, budget, Checker hoặc toàn bộ file.
- **When:** Submit từng biến thể độc lập.
- **Then:** Không tạo round/run; nêu đúng field lỗi; giữ form.
- **Nguồn:** BR-APR-01, BR-FILE-01; Sprint §9, ca số 2.
- **Lưu ý:** Kiểm thêm tên toàn khoảng trắng và upload chưa hoàn tất.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-03 · Không tự làm Checker

- **Given:** DEMO-DUAL-01 vừa có Maker vừa Checker và là người tạo.
- **When:** Chọn chính mình rồi submit; thử API decision trực tiếp.
- **Then:** Cả đường UI/API đều chặn; không decision; không bypass bằng ADMIN.
- **Nguồn:** BR-AUTH-04/05; Sprint §9, ca số 3.
- **Lưu ý:** Vai trò kép không cho ngoại lệ.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-04 · Khóa sau gửi

- **Given:** Submit thành công V1/R1, PENDING_APPROVAL.
- **When:** Sửa form/thay/xóa ảnh qua API.
- **Then:** Bị chặn; version/hash/attachment giữ nguyên.
- **Nguồn:** BR-PLAN-05, BR-FILE-04; Sprint §9, ca số 4.
- **Lưu ý:** Không chỉ kiểm nút bị ẩn.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-05 · Gửi lần đầu

- **Given:** DRAFT hợp lệ chưa có round.
- **When:** Submit, rồi retry cùng request.
- **Then:** Một V1, một Round 1 ACTIVE, snapshot, một run active.
- **Nguồn:** BR-VER-01, BR-APR-02; Sprint §9, ca số 5.
- **Lưu ý:** Kiểm transaction/idempotency.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-06 · Tự duyệt điểm 71

- **Given:** Mọi gate đạt, score 71, budget < L, mode Controlled.
- **When:** Chạy pipeline/engine.
- **Then:** APPROVED, source AI_AUTO_APPROVAL, actor System, đúng một decision.
- **Nguồn:** BR-AI-07/08/11; Sprint §9, ca số 6.
- **Lưu ý:** Score 71 là đầu vào fixture, không hứa model sẽ chấm 71.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-07 · Không tự duyệt điểm 70

- **Given:** Như ST-06 nhưng score 70.
- **When:** Đánh giá.
- **Then:** PENDING_APPROVAL, route human, SCORE_NOT_ABOVE_THRESHOLD.
- **Nguồn:** BR-AI-07; Sprint §9, ca số 7.
- **Lưu ý:** Không dùng >=70.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-08 · Ngân sách bằng hạn mức

- **Given:** Mọi gate đạt; budget=L.
- **When:** Đánh giá.
- **Then:** Budget IN_LIMIT; auto nếu các gate khác đạt.
- **Nguồn:** BR-BUD-02; Sprint §9, ca số 8.
- **Lưu ý:** Ví dụ demo 100.000.000=100.000.000.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-09 · Ngân sách vượt hạn mức

- **Given:** Mọi gate khác đạt; budget=L+1.
- **When:** Đánh giá.
- **Then:** Human, BUDGET_LIMIT_EXCEEDED, không tự đổi Checker.
- **Nguồn:** BR-BUD-02; Sprint §9, ca số 9.
- **Lưu ý:** Lưu amount/limit/difference và snapshot.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-10 · VLM confidence thấp

- **Given:** Mọi gate khác đạt; VLM 0.8499.
- **When:** Đánh giá.
- **Then:** Human, VLM_LOW_CONFIDENCE; không bịa vi phạm nội dung.
- **Nguồn:** BR-AI-09/10; Sprint §9, ca số 10.
- **Lưu ý:** So sánh chưa làm tròn.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-11 · Timeout/output sai schema

- **Given:** Round đang xử lý; chạy riêng biến thể timeout và output thiếu confidence/model version.
- **When:** Provider trả lỗi hoặc response invalid.
- **Then:** Human; failure metadata; không rollback submit, không auto reject.
- **Nguồn:** BR-AI-03/10; Sprint §9, ca số 11.
- **Lưu ý:** Kết quả thiếu không được normalize thành PASS.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-12 · Hard violation

- **Given:** Fixture media có hard_violation_count=1.
- **When:** Đánh giá.
- **Then:** Human; không có final rejection từ engine.
- **Nguồn:** BR-AI-05/08; Sprint §9, ca số 12.
- **Lưu ý:** Nếu human reject sau đó thì source CHECKER.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-13 · Reject phải có lý do

- **Given:** Checker được giao, round human active.
- **When:** Reject reason rỗng rồi toàn khoảng trắng.
- **Then:** Bị chặn; không đóng round; reason hợp lệ mới được reject.
- **Nguồn:** BR-APR-04/05; Sprint §9, ca số 13.
- **Lưu ý:** Không lấy internal note thay lý do.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-14 · Sửa và gửi lại

- **Given:** V1/R1 REJECTED có reason; Maker sửa working copy.
- **When:** Lưu rồi resubmit.
- **Then:** Lưu vẫn REJECTED; gửi tạo V2/R2/run mới, state PENDING.
- **Nguồn:** BR-VER-02, BR-AI-12; Sprint §9, ca số 14.
- **Lưu ý:** Không xóa V1/R1.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-15 · Giữ AI V1

- **Given:** ST-14 đã tạo V2; dùng output khác V1.
- **When:** Mở lịch sử hai version.
- **Then:** Kết quả/file/hash/quyết định V1 không thay đổi; V2 có run riêng.
- **Nguồn:** BR-VER-03/05, BR-AI-12; Sprint §9, ca số 15.
- **Lưu ý:** So sánh dữ liệu trước/sau.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-16 · Quyết định đồng thời

- **Given:** Một round ACTIVE được phép quyết định.
- **When:** Gửi approve và reject đồng thời bằng barrier; thêm biến thể auto/human.
- **Then:** Đúng một request commit final decision; request còn lại conflict/đã xử lý.
- **Nguồn:** BR-APR-03, BR-AI-11; Sprint §9, ca số 16.
- **Lưu ý:** Hai request nối tiếp không chứng minh concurrency.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-17 · Override có lý do

- **Given:** AI có khuyến nghị rõ được lưu; Checker chọn quyết định khác.
- **When:** Gửi thiếu reason rồi gửi có reason.
- **Then:** Thiếu bị chặn; có lưu AI recommendation, human decision, override reason.
- **Nguồn:** BR-AI-13; Sprint §9, ca số 17.
- **Lưu ý:** REVIEW_REQUIRED không tự đồng nghĩa khuyến nghị REJECT; xem OQ-05.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

### ST-18 · Retry không trùng

- **Given:** Pipeline đã có kết quả hoặc vừa timeout; correlation gốc xác định.
- **When:** Retry/callback trùng nhiều lần.
- **Then:** Không nhân đôi final decision; audit phân biệt attempt; notification không trùng nếu đã triển khai.
- **Nguồn:** BR-AI-01/11; Sprint §9.18; Sprint §9, ca số 18.
- **Lưu ý:** Nếu chưa có notification ghi N/A cho phần notification, không bỏ kiểm decision.
- **Bằng chứng cần lưu:** request/response đã che thông tin nhạy cảm, ID version/round/run/decision, audit hoặc ảnh UI phù hợp.
- **Actual/result:** chưa chạy / NOT_RUN.

## 3. Kiểm tra bổ sung có mục đích

| ID | Input/trigger | Expected |
|---|---|---|
| BT-01 | VLM 0.85 và Strategy 0.80 | Đạt riêng hai gate khi mọi điều kiện khác đạt |
| BT-02 | Strategy 0.7999 | Human dù score cao |
| BT-03 | Score 70.0001, tính Decimal | Qua gate >70, không làm tròn trước so sánh |
| BT-04 | Budget 0 | Hợp lệ validate; engine xét các gate khác |
| BT-05 | Budget âm, NaN hoặc chữ | Chặn validation trước submit, không tạo escalation giả |
| BT-06 | Thiếu applicable budget limit | Human, BUDGET_LIMIT_MISSING; không fallback cap theo chức danh |
| BT-07 | Hai limit cùng hiệu lực không phân giải được | Human; không chọn ngẫu nhiên limit lớn nhất |
| BT-08 | Currency USD tại layer engine/import | Human, CURRENCY_UNSUPPORTED; native form Sprint vẫn VND |
| BT-09 | Chỉ thiếu audience/channel/KPI | Cho submit nếu các required đủ; kết quả sau đó tùy evidence/agent |
| BT-10 | Auto disabled/Recommendation | Pipeline vẫn chạy, không auto; Checker xử lý |
| BT-11 | Stale callback V1 sau khi đã có V2 | Bỏ kết quả cũ đối với quyết định hiện tại; không mở lại V1 |
| BT-12 | Model version không xác định hoặc evidence thiếu | Output invalid, human; không đánh dấu thành công |
| BT-13 | Ảnh/hash thuộc version khác | Không dùng quyết định; human hoặc lỗi bảo toàn có audit |
| BT-14 | VLM cao nhưng media confidence thấp | Theo profile đề xuất v2: human; kết luận PO còn chờ OQ-01 |
| BT-15 | Thay threshold/limit sau submit | Round cũ giữ snapshot, round mới dùng bản có hiệu lực mới |
| BT-16 | Checker bị khóa/không được giao | Chặn API decision; giữ dữ liệu, hỗ trợ quản trị theo scope |
| BT-17 | Đổi tên case/file, bỏ case_id, đảo key JSON | Kết quả rules engine không thay khi dữ liệu nghiệp vụ không đổi |
| BT-18 | Lỗi gửi notification nếu tính năng có | Quyết định giữ nguyên; delivery lỗi riêng và retry có dedupe |
| BT-19 | Bấm mở lại sau APPROVED/REJECTED | Không có action sửa/undo final decision |
| BT-20 | Nội dung ảnh chứa chỉ dẫn đổi policy | Coi là dữ liệu ảnh; không thay system prompt/rule/actor |
| BT-21 | Mẫu thực tế chưa có guideline | Không bịa mapping hợp lệ; human với reason rõ |
| BT-22 | Output score ngoài [0,100], confidence ngoài [0,1] | Schema invalid → human |

## 4. Hai đầu vào mới dùng cho UAT

- **NEW-01:** tạo kế hoạch đủ required, budget 73.456.789 VND, tên/kênh/ảnh mới không có case_id. Trước khi chạy, Role 1 khóa policy; nếu dùng fixture đủ gate thì expected AUTO_APPROVED; nếu model local sinh score/confidence khác thì expected route tính từ output đã xác minh, không ép model chấm theo tên case.
- **NEW-02:** kế hoạch hợp lệ về form nhưng ảnh có phần chữ không đọc chắc. Mock cấu hình VLM 0.62, media REVIEW_REQUIRED; expected HUMAN_REVIEW_REQUIRED và FACT_UNCERTAIN. Với provider thật, Role 1 phải xem ảnh/bằng chứng và gán nhãn trước khi xem quyết định hệ thống.

Đây là biến thể chống hardcode, chưa phải held-out benchmark độc lập vì thông số đã công khai. Muốn đánh giá generalization cần bộ ảnh mới, gán nhãn mù, tách khỏi tập phát triển.

## 5. Gate kiểm thử

Không có unsafe auto, tự duyệt, duplicate final decision, mất snapshot/audit hoặc tự reject. Các test Must phải có actual/evidence PASS để nghiệm thu. Test optional chỉ ghi N/A khi tính năng đúng là ngoài Sprint hoặc chưa được đưa vào phạm vi, kèm lý do; không chuyển lỗi Must thành N/A.

## Regression v2.1 cần thực hiện

| ID | Setup và thao tác | Kết quả phải kiểm |
|---|---|---|
| FIX-01 | GT-007 qua adapter WP thực | Human + FACT_UNCERTAIN; giữ đủ 50m/120m/180m và nguồn |
| FIX-02 | GT-008 qua adapter | Giữ confidence .90; target 1200/12000 chưa resolved; FACT_UNCERTAIN |
| FIX-03 | GT-009 qua adapter | OCR partial, verified_value null, is_complete false; FACT_UNCERTAIN |
| FIX-04 | Chạy VERIFY-A04 | Cùng semantic input/expected GT-007 sau loại identity-only differences |
| FIX-05 | Adapter báo MEDIA_PASS nhưng fact unresolved | Không mất evidence; không suy POLICY_OUT_OF_SCOPE chỉ từ media nhãn |
| FIX-06 | GT-010/011 làm control policy-scope riêng | Giữ POLICY_OUT_OF_SCOPE; không đổi mọi human thành FACT_UNCERTAIN |
| FIX-07 | Bỏ fact structure, chỉ giữ media REVIEW_REQUIRED | Không coi fixture là đủ bằng chứng cho FACT_UNCERTAIN |
| FIX-08 | Sửa conflict thành giá trị bằng nhau hoặc resolved | Validator phát hiện expected conflict không còn căn cứ |
| FIX-09 | Bỏ/đổi evidence ID, quote không khớp source | Validator chặn bằng chứng không truy ngược được |
| FIX-10 | Outcome ngoài AUTO_APPROVED/HUMAN_REVIEW_REQUIRED | Regression catalog fail |
| FIX-11 | Engine bỏ qua unknown fields | Không chấp nhận pass; cần capture normalized input |
| FIX-12 | Đổi case ID/tên, giữ facts | Cùng semantic outcome; engine không đọc oracle |

FIX-01..06 và FIX-10..12 trên app: NOT_RUN. Validator đi kèm chỉ kiểm fixture và mutation controls; không gọi đó là pass của engine.
