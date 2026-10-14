# 15 · Quyết định còn mở và thay đổi so với bộ Role 1 cũ

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Đối chiếu hai nguồn mới với outputs/role1-package, không coi tài liệu assistant cũ là nguồn có thẩm quyền.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Quy tắc giải quyết khác biệt

Scope định nghĩa nghiệp vụ sản phẩm; Sprint chọn phần phải xây trong 72 giờ. Sprint không tự mở thêm trạng thái/cấp duyệt bị Scope loại trừ. Nếu hai nguồn diễn đạt khác nhau, ghi OPEN và phương án demo đề xuất; không giả danh PO đã chốt. File Role gốc phân công công việc không được suy diễn từ tên chức danh.

## 2. Sổ quyết định mở

| ID | Vấn đề | Căn cứ | Owner đề xuất | Cách dùng tạm trong tài liệu/demo | Cần chốt | Trạng thái |
|---|---|---|---|---|---|---|
| OQ-01 | VLM confidence hay media confidence? | Scope BR-AI-09: VLM ≥0.85; Sprint §4: media ≥0.85; Sprint §12: VLM | PO + người phụ trách AI | Profile demo đề xuất kiểm cả hai, lưu riêng; không nói nguồn đã thống nhất | Chốt field, ngưỡng, cách gộp nhiều ảnh và test chỉ một confidence đạt | OPEN |
| OQ-02 | Snapshot tại submit hay lúc run bắt đầu? | Scope §7.2/§18.23 và BR-AI-15 khác cách diễn đạt | PO + kỹ thuật | Đề xuất khóa tất cả tại submit/round; retries giữ snapshot | Run trễ không được vô tình nhận model/policy mới | OPEN |
| OQ-03 | Tắt auto khi run đang chạy có hiệu lực tức thời? | BR-AI-14 về tắt auto; snapshot bất biến cho vòng đang chạy | PO + kỹ thuật | Demo không đổi toggle giữa run; tài liệu không cam kết Stop/Undo | Chốt runtime kill switch, audit và ca race; không sửa final decision | OPEN |
| OQ-04 | In-app notification Must hay Should? | Sprint §3.2 Should; WP5/timeline nhắc phải có | PO | Treat as Should theo bảng ưu tiên; vẫn ghi yêu cầu chống duplicate nếu làm | Chốt scope trước giờ 68, tách audit Must | OPEN |
| OQ-05 | Khuyến nghị nào để xác định override? | Scope BR-AI-13, Sprint §9.17; Media chỉ PASS/REVIEW_REQUIRED | PO + BA/AI | Tách route, recommendation và final decision; REVIEW không mặc định REJECT | Chốt enum recommendation, khi nào cần override_reason, Shadow tránh lộ khuyến nghị | OPEN |
| OQ-06 | Giới hạn quyền Checker với hard violation/vượt ngân sách? | Nguồn chặn auto, chưa cho limit theo chức danh hay rule cấm human override cụ thể | PO + Policy/Finance owner | Một Checker được giao; không bịa Lead/Manager 300m/1b; cần reason theo rule | Không tự tuyên bố human được bỏ qua mọi policy pháp lý | OPEN |
| OQ-07 | Limit tiền và phạm vi áp dụng thực tế | Chưa có số tiền/quy tắc ưu tiên scope từ hai nguồn | PO/Finance | DEMO-LIMIT-V2=100m chỉ fixture; missing/overlap không rõ → human | Cần amount, currency, department scope, hiệu lực, owner duyệt | OPEN |
| OQ-08 | Content/brand policy chính thức | Nguồn yêu cầu policy nhưng không cung cấp toàn bộ rule nội dung | Brand/Policy owner | Dùng token/vi phạm giả lập cho test, không tuyên bố luật thật | Cần rule IDs, evidence chuẩn, severity và trường hợp cần expert | OPEN |
| OQ-09 | Critical gaps và rubric chấm score | Scope yêu cầu output gaps, trọng số; chưa có rubric chi tiết/cách block | Role 1 + PO + AI | Rubric và gap blocking là đề xuất; case nền dùng gaps rỗng | Chốt từng tiêu chí, calibration, rounding và human disagreement | OPEN |
| OQ-10 | Timeout/retry/provider/model | Scope yêu cầu cấu hình; Sprint cần Local+Mock, không chỉ định model/hardware | Kỹ thuật | Không đặt số ms hay số retry thành yêu cầu đã chốt | Cần tên/version/license/phần cứng/timeout/attempt semantics | OPEN |
| OQ-11 | Upload limits và nhiều ảnh/không ảnh | Scope cho nhiều loại file; Sprint ưu tiên hình ảnh | PO + kỹ thuật | Seed dùng PNG; missing visual evaluation không coi PASS | Cần MIME/size/count, chính sách gộp confidence và hồ sơ chỉ có tài liệu | OPEN |
| OQ-12 | SLA, múi giờ, thông báo | SLA Should Sprint; không chốt số giờ; Phase có lịch làm việc/email | PO | Không gán 4h/8h theo escalation; optional giờ liên tục | Cần duration/warning/recipient/timezone; không email thật trong Sprint | OPEN |
| OQ-13 | File phân công Role nguyên văn | Đường dẫn role-1-role-3-task-allocation (1).md không còn | Người cung cấp tài liệu | Kế thừa danh sách đầu việc từ gói Role 1 cũ; chưa xác minh nguyên văn | Đối chiếu lại số case/định dạng submission/ownership khi có file | OPEN |
| OQ-14 | Bảo toàn dữ liệu và bảo mật triển khai | Scope cấm gửi ngoài khi chưa duyệt; chưa nêu retention/backup cụ thể | Chủ hệ thống | Không dùng thông tin thật; không gửi external VLM trong bộ này | Chốt access/storage/retention; không hứa ledger hay chữ ký | OPEN |
| OQ-15 | Enum stage failure/route và schema deterministic budget | Scope có AI_PROCESSING_FAILED; Sprint tập trung HUMAN_REVIEW_REQUIRED và mẫu agent chung | BA + kỹ thuật | Giữ stage failure + route human; typed budget schema không bịa confidence | Chốt adapter mapping, queue filter và JSON Schema | OPEN |

## 3. Changelog v1 → v2

| Điểm ở gói cũ | Sửa ở v2 | Tác động app/test |
|---|---|---|
| Required bao gồm KPI, audience, channels, strategy_content | Theo Scope §9: KPI/audience/channels optional; không thêm strategy_content bắt buộc | Không chặn submit ngoài yêu cầu |
| Media FAIL và HARD_REJECTED | Media chỉ PASS/REVIEW_REQUIRED; hard violation chuyển human | Hai case hard violation không expected auto reject |
| Cap 100m + Lead 300m + Manager 1b | Một applicable limit có cấu hình; L demo=100m | Budget gate xác định, không xây multi-level |
| Routing Manager/cấp cao hơn | Checker đang được giao, Admin hỗ trợ kỹ thuật/cấu hình | Giữ một cấp và một Checker |
| FACT_UNCERTAIN do budget null ở hồ sơ gửi | Budget form hợp lệ; OCR mâu thuẫn là evidence | Phân biệt validation với pipeline |
| Score/route/decision dùng tên lẫn nhau | Route AUTO_APPROVED/HUMAN; business APPROVED/PENDING; source riêng | Không lưu human route thành final decision |
| Confidence không phân biệt media/VLM | Tách hai field, OQ-01 | Tránh đổi field ngầm |
| SLA escalation 4h/8h | Bỏ số giờ không có nguồn | Should; cấu hình chưa chốt |
| UAT có Stop/Undo, email thật | Stop/Undo ngoài workflow đã chốt; email out Sprint | Không đưa vào gate Must |
| Verify chỉ có input rút gọn, thiếu context | Base fixture + full materialized JSON + ảnh demo/hash | Dùng được để seed/harness rõ layer |
| Expected tự gọi “chính thức” | Expected demo/contract chưa PO sign-off, actual NOT_RUN | Tránh hiểu nhầm đã được nghiệm thu |
| 95%,10%,<5% như target có sẵn | Đổi thành đề xuất hoặc bỏ; raw counts rõ mẫu số | Không khẳng định thống kê sản phẩm |
| Budget engine có model confidence giả | Typed schema deterministic, confidence không áp dụng | Không để LLM quyết ngân sách |

## 4. Thay đổi nào cần version mới?

Đổi gate/threshold/weights/content rule/limit scope/expected route/category contract → tạo policy hoặc dataset version mới, ghi lý do và case ảnh hưởng. Sửa lỗi chính tả không đổi nghĩa có thể patch tài liệu. Chưa có sign-off nào được ghi là đã hoàn tất trong bản này.

## 5. Thông tin chưa thể thu thập từ hai nguồn

Hạn mức công ty thật; brand/content/legal guideline; tên người duyệt và quyền thực; dữ liệu chiến dịch/KPI lịch sử; model/hardware/benchmark; codebase/endpoint/build; SLA sản xuất; retention. Bộ này không bịa các mục đó. Data tổng hợp đủ để mô tả và thử contract, chưa thay dữ liệu doanh nghiệp hoặc đánh giá model thật.

## OQ-16 · Contract WP1/WP2 và regression engine v2.1

**OPEN.** Đã sửa semantic fixture theo A. Chưa có source/schema WP1/WP2 hoặc endpoint engine để xác nhận drop-in compatibility hay actual pass. Cần contract, mapping, runtime reason/rule codes và normalized input đã gây lỗi.

Không đổi policy/limit/threshold; không yêu cầu thay engine sang contract do tài liệu tự đặt. Proposal là dữ liệu đầy đủ để map vào contract thật, có thể đổi tên field khi nhận contract mà vẫn giữ nghiệp vụ.
