# 09 · Kế hoạch đo lường và tiêu chí chất lượng

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Scope AI-10, §18; Sprint §§9–10; đề mục measurement kế thừa Role 1 cũ.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Đơn vị đo và cách tách mẫu

Đơn vị chính là **một evaluation của một version/round hợp lệ**, không phải từng HTTP request hay từng attempt retry. Chỉ tính lần kết thúc logic của round/run cho accuracy; attempt dùng đo reliability/latency riêng. Tách provider_mode MOCK/LOCAL, dataset version, policy snapshot, mode vận hành và môi trường. Không gộp GT với Verify rồi coi 20 ca là 20 quan sát độc lập: Verify là biến thể 5 ca nền.

Loại validation failure trước submit khỏi denominator auto/escalation của hồ sơ gửi hợp lệ. Ca phân quyền và concurrency có nhóm kiểm thử riêng. Pipeline timeout phải được tính là case cần human, không loại khỏi denominator để đẹp số liệu.

## 2. Metric và công thức

| Metric | Tử số / mẫu số | Cách đọc |
|---|---|---|
| Decision-route accuracy | Số route khớp expected / số case đã chạy có nhãn | Route AUTO_APPROVED/HUMAN, không đồng nhất với hiệu quả kinh doanh |
| Human-review recall | Case expected human thực tế human / toàn bộ expected human đã chạy | Ưu tiên phát hiện bỏ sót cần người |
| False-escalation rate | Case expected auto thực tế human / toàn bộ expected auto đã chạy | Không dùng tổng hồ sơ làm mẫu số |
| Unsafe-auto rate | Case expected human thực tế auto / toàn bộ expected human đã chạy | Đếm kèm raw count; 1 lỗi cũng chặn demo gate đề xuất |
| Auto-processing share | Round tự duyệt / tổng round đã gửi hợp lệ đã xử lý | Chỉ báo tỷ trọng, không tự là mục tiêu tăng tối đa |
| Category accuracy | Primary category đúng / case có expected category không null | Báo thêm reason-code coverage cho category null |
| Reason coverage | Case human có đủ reason bắt buộc / tổng case human | Không bắt buộc khớp từng chữ câu hỏi |
| Question completeness | Case human đạt rubric / tổng case human cần câu hỏi | Rubric bên dưới |
| Pipeline failure rate | Logical run thất bại/timeout cuối cùng / logical run đã kết thúc | Báo retry-attempt failure riêng |
| Override rate | Human decision khác recommendation rõ / human decisions có recommendation rõ | Không dùng toàn bộ human review; xem OQ-05 |
| Duplicate decision count | Round có hơn 1 final decision đã commit | Mục tiêu invariant = 0 |
| Audit completeness | Round có đủ trường/sự kiện bắt buộc / round đã kết thúc | Kèm danh sách thiếu, không chỉ phần trăm |
| Processing latency | completed_at − started_at mỗi run | p50/p95, n, hardware/provider, đơn vị ms |
| Human queue time | decided_at − human_review_required_at | Tách thời gian chờ với active handling nếu không có telemetry |
| Confirmed false approval | Quyết định auto được chuyên gia xác nhận sai / auto đã được review | Không suy ra từ confidence hoặc lấy mẫu chưa hoàn tất |

Mẫu số 0 → `N/A`, không ghi 0% hoặc 100%. Báo counts dạng 9/9, không chỉ phần trăm. Trên 9 expected human của GT v2, mục tiêu recall ≥95% tương đương phải 9/9; mất 1 là 88,89%. Đây là tập rất nhỏ, không chứng minh đạt 95% ngoài thực tế.

## 3. Targets và release gate

Hai nguồn mới không chốt ngưỡng thống kê 95%, 10%, <5% lỗi hoặc latency <5ms/<10ms. Những số đó trong gói cũ không phải SLA/success thực tế. `[ĐỀ XUẤT]` gate demo: 15/15 GT, 5/5 Verify, 18 nhóm ST bắt buộc và biến thể liên quan PASS, 0 unsafe auto/duplicate/self-approval, audit đầy đủ. Đây là mục tiêu nghiệm thu đề xuất, hiện **CHƯA CHẠY**.

Không đặt tỷ lệ tự động duyệt 92%, escalation 8% hay tỷ lệ tiết kiệm thời gian khi chưa có dữ liệu thật. Muốn đo cải thiện cần cùng bộ case, nhóm/thiết kế đối chứng, thời gian xử lý trước/sau và kiểm soát chất lượng.

## 4. Rubric câu hỏi, mỗi tiêu chí 1 điểm

1. Chỉ rõ vấn đề và giá trị/confidence/threshold liên quan.
2. Có evidence ref truy được đến file/vùng/phiên bản.
3. Nêu việc người duyệt cần xác nhận hoặc thẩm định.
4. Đúng Checker, không tạo bước phê duyệt ngoài phạm vi.
5. Không yêu cầu sửa trực tiếp snapshot đang khóa hoặc coi trao đổi là final decision.

Đề xuất đạt 5/5; Role 1 ghi chấm và nhận xét. Câu chữ được phép khác expected nếu giữ đủ ý và không thêm kết luận sai.

## 5. Instrumentation tối thiểu

plan/version/round/run/correlation/attempt ID; actor/role; timestamp UTC; input hash; attachment hash; model/agent/prompt/policy version; snapshot ID; structured outputs; raw output reference khi được phép; score/criterion/confidence/evidence; rule/reason codes; route/final decision/source; override reason; latency/error; dedupe key nếu triển khai notifications.

Hash phải dựa dữ liệu thực, không dùng chuỗi placeholder làm bằng chứng truy vết. Audit append-only ở mức nghiệp vụ không tự chứng minh có hash chain, chữ ký số hoặc ledger chống can thiệp; đây là các năng lực khác chưa được triển khai/xác nhận.

## 6. Mẫu báo cáo

| Chỉ tiêu | n | Kết quả | Trạng thái |
|---|---:|---|---|
| GT route accuracy | 0/15 đã chạy | N/A | NOT_RUN |
| Verify | 0/5 đã chạy | N/A | NOT_RUN |
| ST bắt buộc | 0/18 nhóm đã chạy | N/A | NOT_RUN |
| Unsafe auto | 0 lượt chạy | Chưa đo | NOT_RUN |
| p50/p95 Local VLM | 0 | N/A | Chưa có máy/model |

Không thay “chưa đo” bằng số 0 để tạo ấn tượng đã đạt. Tách kết quả kiểm tra cấu trúc tài liệu/fixture khỏi kết quả chạy app.

## Theo dõi regression v2.1

Tách ba cột: artifact checks, WP schema compatibility và actual engine regression. Không gộp 192 checks artifact thành 192 app tests. Theo dõi bốn case mục tiêu riêng: expected category, actual category, normalized evidence có bị mất không, factual field/rationale và source refs còn đầy đủ không.

Category accuracy chỉ có mẫu số là case đã chạy engine thật. Bốn case hiện NOT_RUN; không ghi 4/4 engine PASS từ việc expected đúng hoặc validator pass. Giữ metric source/classification errors với counts thực sau khi có app.
