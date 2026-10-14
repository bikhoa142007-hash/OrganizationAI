# 11 · Nội dung trình bày, kịch bản demo và build log

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Sprint §§1, 8, 10, 13–14; nội dung submission kế thừa bộ Role 1 cũ.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Thông điệp trình bày

“MVP hỗ trợ phê duyệt kế hoạch marketing: AI trích xuất và giải thích; rules engine kiểm ngân sách; chỉ tự duyệt khi mọi điều kiện đạt; Checker quyết định các trường hợp còn lại. Mỗi lần gửi tạo version và vòng duyệt có thể truy vết.”

Đây là lời mô tả **mục tiêu thiết kế**. Khi trình bày demo thật cần đổi sang lời xác nhận các tính năng đã chạy, căn cứ build/log. Không tự thêm tỷ lệ thành công, latency hoặc doanh thu.

## 2. Nội dung 6 slide đề xuất

| Slide | Nội dung cụ thể | Hình/ bằng chứng nên dùng |
|---|---|---|
| 1. Bài toán và ranh giới | Một hồ sơ, Maker–AI–Checker, 1 cấp; tránh duyệt thiếu bằng chứng | Trước/sau về quy trình; không bịa số tiết kiệm |
| 2. Dòng xử lý | Form/ảnh → VLM → Media + Strategy + Budget → Decision → human/auto | Sơ đồ file 01; gắn nhãn MOCK/LOCAL |
| 3. Policy | >70, confidence, budget≤L, không violation/error/conflict | Bảng gate file 02; đánh dấu OQ-01 và L demo |
| 4. Kiểm soát con người | Evidence, reason, approve/reject, override, resubmit V2 | Ảnh app thật sau khi triển khai |
| 5. Kiểm chứng | 15 GT, 5 Verify, 18 test workflow + ca biên | Hiện actual/pass/fail có nguồn; nếu chưa chạy ghi NOT_RUN |
| 6. Giới hạn và bước tiếp | Mock không chứng minh model thật; policy còn cần PO; Should/Sprint sau | Danh sách quyết định mở và roadmap |

## 3. Kịch bản demo theo Sprint §13

### Demo 1 · Tự động duyệt

Maker tạo đủ trường, ảnh PASS, budget 50m với limit demo 100m; provider/fixture tạo confidence và score đạt. Submit → V1/R1 → xử lý → APPROVED. Mở audit: source AI_AUTO_APPROVAL, actor System, gate summary, hash và policy version. Nếu provider thật không cho cùng score thì không ép output; đổi sang demo MOCK công khai.

### Demo 2 · Chuyển Checker

Dùng GT-009 hoặc VERIFY-A04, form hợp lệ, VLM 0.61/0.72 theo fixture. Submit → human, vẫn PENDING. Checker thấy ảnh gốc/vùng evidence/reason/question. Chỉ có approve/reject; không có route Manager tự động hay nút “yêu cầu chỉnh sửa”.

### Demo 3 · Từ chối và gửi lại

Checker từ chối có lý do “Ảnh không đủ rõ để xác minh nội dung; vui lòng bổ sung ảnh rõ”. Maker sửa working copy, lưu vẫn REJECTED, thay ảnh và resubmit. Chứng minh V2/R2/run mới; mở V1 thấy ảnh, AI output và quyết định cũ còn nguyên. Không gọi thao tác này là undo quyết định.

### Demo 4 · Pipeline lỗi

Chọn Mock timeout được cấu hình test. Giữ submit thành công; AI_PROCESSING_FAILED + human queue; mở failure reason/correlation ID. Không auto reject, không rollback về DRAFT. Nếu retry Should chưa làm, demo dừng ở Checker xử lý hợp lệ.

## 4. Video 3 phút [đề xuất định dạng kế thừa bộ cũ]

| Mốc | Cảnh | Câu dẫn |
|---|---|---|
| 00:00–00:20 | Vấn đề/scope | “Một cấp phê duyệt, AI có bằng chứng, người kiểm soát ngoại lệ.” |
| 00:20–00:55 | Tạo/gửi và auto | “Các gate đạt; quyết định lưu nguồn System và policy.” |
| 00:55–01:35 | Case ảnh không rõ | “Confidence chưa đủ; Checker thấy lý do và ảnh gốc.” |
| 01:35–02:10 | Reject/resubmit | “V2 được đánh giá mới; V1 không bị ghi đè.” |
| 02:10–02:35 | Timeout và audit | “Lỗi AI chuyển người, không tự từ chối.” |
| 02:35–03:00 | Kết quả/giới hạn | Đọc số test actual, nhãn MOCK/LOCAL, các mục chưa làm |

Không cắt dựng để làm trạng thái dự kiến giống kết quả đã chạy. Nếu chưa có app, nội dung này chỉ dùng làm storyboard.

## 5. Build/change log mẫu

| Thời điểm | Build/commit | Thay đổi | Lý do/nguồn | Test/evidence | Người review |
|---|---|---|---|---|---|
| Chưa chạy | Chưa có | Chưa triển khai app trong task này | Đây là bộ tài liệu Role 1 | NOT_RUN | Chưa có |

Log nghiệp vụ cần lưu version policy/dataset, lý do đổi expected và ảnh hưởng. Không đổi ngưỡng để làm ca lỗi thành pass mà không có change request.

## 6. Nội dung cần tránh khi nộp

Không tuyên bố production-ready, Local VLM chạy thật, 92% tự động, ledger mật mã, rollback/undo, email thật, nhiều cấp hoặc các giới hạn nhân sự 300m/1b. Những nội dung đó chưa được nguồn/triển khai xác nhận và phần lớn ngoài Sprint.

## Theo dõi regression v2.1

Khi demo, minh họa các giá trị 50m/120m/180m, target 1200/12000 và OCR partial, không chỉ cho xem category. Nếu UI hiện MEDIA_PASS, vẫn mở normalized factual findings để chứng minh đã map uncertainty. Chưa có engine run thì gọi đây là demo dữ liệu/contract proposal; không trình bày bốn case đã PASS backend.
