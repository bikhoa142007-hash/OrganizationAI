# Kiểm tra gói Role 1 Sprint 1 v2.1

## Kết quả artifact

**192/192 phép kiểm đạt, 0 lỗi.** Có 8 thử nghiệm dữ liệu sai có chủ đích, tất cả bị phát hiện đúng.

- 15 GT / 5 Verify còn đầy đủ; catalog outcome đúng AUTO_APPROVED/HUMAN_REVIEW_REQUIRED.
- GT-007/008/009 có fields, typed issues, source values, quotes/pointers, unresolved status và rationale có thể truy ngược.
- VERIFY-A04 input chỉ khác GT-007 ở identity allowlist; toàn bộ expected deep-equal.
- Diff tự động có exact before/after, áp ngược khôi phục đúng baseline canonical hash.
- Policy, score, confidence, budget, hình, snapshots nguồn và unrelated case inputs được bảo toàn.
- Partial OCR của GT-009 có is_complete=false; không cung cấp full text rồi nói không xác minh được.
- Input/evaluation hashes và manifest khớp; links/JSON examples/Unicode hợp lệ.

Chi tiết từng check: [regression-results.json](../archive/v2.1/regression-results.json).
Code để chạy lại: [tools/validate_package.py](../../../role1-sprint1-v2.1/tools/validate_package.py).

## Những gì chưa được kiểm

| Hạng mục | Trạng thái |
|---|---|
| WP1/WP2 schema compatibility | NOT_VERIFIED — chưa có contract thực |
| Engine classification của 4 case | NOT_RUN — chưa gọi app/engine |
| UAT/backend integration | NOT_RUN |
| Local VLM thực đọc ảnh | NOT_RUN — đây là mock fixture |

Các số đạt bên trên không phải test app đã pass. Không dùng chúng để tuyên bố bug runtime được xác nhận đã hết. Tài liệu mapping file 19 nêu rõ bằng chứng cần bổ sung.

## Chạy lại

~~~text
python tools/validate_package.py
~~~

Python 3, chỉ standard library; chỉ đọc gói và in JSON report. Không thay runtime catalog, không sửa engine, không đọc expected để quyết định trong production.

Integration note: run the command above from the original `role1-sprint1-v2.1/` directory. Its validator relies on the original package layout; this imported documentation directory is not an executable package copy.
