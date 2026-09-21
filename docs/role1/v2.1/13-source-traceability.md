# 13 · Nguồn, đối chiếu yêu cầu và độ phủ tài liệu

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Hai file người dùng vừa gửi đã đọc theo thứ tự Scope → Sprint; đối chiếu bộ Role 1 trước sau đó.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Nguồn sơ cấp và độ tin cậy

| Snapshot | Vai trò nguồn | SHA-256 |
|---|---|---|
| [scope-phase-1.md](../../scope-phase-1.md) | PRODUCT_BASELINE | c952d35596a9053a3bb5800dd3be37e1d0081293b7a3068e48bf962efbadf69f |
| [sprint-1-deliverables.md](../../sprint-1-deliverables.md) | SPRINT_SUBSET | 41e12255f316333c5649b860a2a59a109664c15e51d577f4a95641a379286d0b |

Hai snapshot được sao chép nguyên bytes vào sources/ để bộ bàn giao tự chứa nguồn. Scope ghi version 1.1, cập nhật 20/09/2026, chờ PO/Stakeholder xác nhận. Sprint không ghi số version riêng; hash là dấu nhận dạng file đã đọc, không tự tạo “version chính thức”.

File `role-1-role-3-task-allocation (1).md` không còn ở đường dẫn người dùng gửi trước đây. Đã tìm trong các thư mục liên quan được đọc; chưa có bản gốc để đọc lại nguyên văn. Bộ `outputs/role1-package` và bản sao trong Downloads/zip là tài liệu assistant tạo trước, chỉ dùng khôi phục đề mục, không coi là yêu cầu mới được PO xác nhận. Người dùng xác nhận muốn làm Role 1 nhưng chưa cung cấp đường dẫn mới.

Do đó, bộ này có độ phủ đầy đủ **các đề mục Role 1 đang còn trong gói cũ** và quy tắc Scope/Sprint đọc được; chưa thể chứng nhận khớp từng dòng của file phân công Role nguyên bản. Đây là giới hạn nguồn cụ thể, không phải phần yêu cầu bị tự ý bỏ qua.

## 2. Ma trận đề mục Role 1 kế thừa

| Đề mục | File v2 | Cách xử lý |
|---|---|---|
| Scope/process | [01-scope-and-process.md](01-scope-and-process.md) | Theo gói cũ 01 |
| Marketing approval policy | [02-marketing-approval-policy.md](02-marketing-approval-policy.md) | Theo gói cũ 02; bỏ auto-reject |
| Authority matrix | [03-authority-matrix.md](03-authority-matrix.md) | Theo gói cũ 03; bỏ giới hạn chức danh bịa |
| Escalation policy | [04-escalation-policy.md](04-escalation-policy.md) | Theo gói cũ 04; category metadata đề xuất |
| 15 ground-truth cases | [05-ground-truth-cases.md](05-ground-truth-cases.md) | Thay JSON-only bằng Markdown + JSON bổ trợ |
| Test catalog | [06-test-case-catalog.md](06-test-case-catalog.md) | Bổ sung đủ 18 test Sprint và 22 ca biên |
| 5 Verify inputs | [07-verify-cases.md](07-verify-cases.md) | Input đầy đủ, không chỉ các field rút gọn |
| Verify expected results | [08-verify-expected-results.md](08-verify-expected-results.md) | Expected riêng actual, NOT_RUN |
| Measurement | [09-measurement-plan.md](09-measurement-plan.md) | Mẫu số, counts, giới hạn thống kê |
| UAT report | [10-uat-report.md](10-uat-report.md) | Report chưa chạy, gate và evidence |
| Submission/slides/video/build log | [11-submission-content.md](11-submission-content.md) | Storyboard theo 4 demo Sprint |
| Domain data dictionary | [12-domain-data-dictionary.md](12-domain-data-dictionary.md) | Thiết kế bổ trợ app, không chứng minh có migration |

File 13–17 bổ trợ nguồn, handoff, quyết định mở, contract và seed để app dễ tích hợp. Không chuyển công việc triển khai code của vai trò khác thành tuyên bố Role 1 đã hoàn tất.

## 3. Traceability toàn bộ Business Rules trong Scope

Bảng này là **độ phủ tài liệu**, không phải kết quả thực thi. Cột test là nhóm liên quan; một số rule chỉ thuộc Phase 1/Should nên không được gán PASS Sprint. Chỉ những test được mô tả chi tiết và có actual sau này mới tạo bằng chứng kiểm chứng rule tương ứng.

| Rule nguồn | Nội dung nguyên văn | Tài liệu giải quyết | Test/ghi chú phạm vi |
|---|---|---|---|
| BR-AUTH-01 | Người dùng phải đăng nhập và có quyền tương ứng mới được truy cập chức năng | [03](03-authority-matrix.md) | ST-03, ST-16, BT-16; role builder đầy đủ ngoài Sprint |
| BR-AUTH-02 | Maker chỉ sửa kế hoạch do mình tạo, trừ khi có quyền quản trị riêng | [03](03-authority-matrix.md) | ST-03, ST-16, BT-16; role builder đầy đủ ngoài Sprint |
| BR-AUTH-03 | Checker chỉ ra quyết định với kế hoạch được giao | [03](03-authority-matrix.md) | ST-03, ST-16, BT-16; role builder đầy đủ ngoài Sprint |
| BR-AUTH-04 | Maker và Checker của cùng một vòng duyệt không được là cùng một người | [03](03-authority-matrix.md) | ST-03, ST-16, BT-16; role builder đầy đủ ngoài Sprint |
| BR-AUTH-05 | Người có cả quyền Maker và Checker vẫn không được tự duyệt kế hoạch của mình | [03](03-authority-matrix.md) | ST-03, ST-16, BT-16; role builder đầy đủ ngoài Sprint |
| BR-AUTH-06 | Bộ phận, chức danh và vai trò hệ thống là ba thuộc tính độc lập | [03](03-authority-matrix.md) | ST-03, ST-16, BT-16; role builder đầy đủ ngoài Sprint |
| BR-AUTH-07 | Không được xóa vai trò đang được gán cho nhân viên; chỉ cho ngừng hoạt động hoặc chuyển nhân viên trước | [03](03-authority-matrix.md) | ST-03, ST-16, BT-16; role builder đầy đủ ngoài Sprint |
| BR-AUTH-08 | Nhân viên ngừng hoạt động hoặc tài khoản bị khóa không được chọn làm Checker mới | [03](03-authority-matrix.md) | ST-03, ST-16, BT-16; role builder đầy đủ ngoài Sprint |
| BR-PLAN-01 | Mỗi kế hoạch có một mã duy nhất do hệ thống tự sinh | [01](01-scope-and-process.md) | ST-01, ST-02, ST-04, ST-14 |
| BR-PLAN-02 | Lưu nháp không yêu cầu đủ toàn bộ trường bắt buộc gửi duyệt | [01](01-scope-and-process.md) | ST-01, ST-02, ST-04, ST-14 |
| BR-PLAN-03 | Các giá trị đã nhập khi lưu nháp vẫn phải đúng định dạng | [01](01-scope-and-process.md) | ST-01, ST-02, ST-04, ST-14 |
| BR-PLAN-04 | Chỉ kế hoạch Nháp hoặc Đã từ chối mới được Maker chỉnh sửa | [01](01-scope-and-process.md) | ST-01, ST-02, ST-04, ST-14 |
| BR-PLAN-05 | Kế hoạch Chờ duyệt và Đã duyệt là read-only | [01](01-scope-and-process.md) | ST-01, ST-02, ST-04, ST-14 |
| BR-PLAN-06 | Chỉ hệ thống được chuyển trạng thái theo các hành động hợp lệ | [01](01-scope-and-process.md) | ST-01, ST-02, ST-04, ST-14 |
| BR-PLAN-07 | Không có trạng thái Đang duyệt trong Phase 1 | [01](01-scope-and-process.md) | ST-01, ST-02, ST-04, ST-14 |
| BR-PLAN-08 | Không có hành động Yêu cầu chỉnh sửa riêng; dùng Từ chối kèm lý do | [01](01-scope-and-process.md) | ST-01, ST-02, ST-04, ST-14 |
| BR-APR-01 | Gửi duyệt phải có đầy đủ trường bắt buộc và ít nhất một file | [02](02-marketing-approval-policy.md) | ST-02, ST-05, ST-13, ST-14, ST-16 |
| BR-APR-02 | Tại một thời điểm chỉ có một vòng duyệt đang hoạt động cho một kế hoạch | [02](02-marketing-approval-policy.md) | ST-02, ST-05, ST-13, ST-14, ST-16 |
| BR-APR-03 | Phê duyệt hoặc từ chối phải kiểm tra lại trạng thái để ngăn xử lý trùng | [02](02-marketing-approval-policy.md) | ST-02, ST-05, ST-13, ST-14, ST-16 |
| BR-APR-04 | Lý do từ chối là bắt buộc và không được chỉ chứa khoảng trắng | [02](02-marketing-approval-policy.md) | ST-02, ST-05, ST-13, ST-14, ST-16 |
| BR-APR-05 | Lý do từ chối đã xác nhận không được sửa hoặc xóa | [02](02-marketing-approval-policy.md) | ST-02, ST-05, ST-13, ST-14, ST-16 |
| BR-APR-06 | Sau khi bị từ chối, Maker được sửa và gửi lại | [02](02-marketing-approval-policy.md) | ST-02, ST-05, ST-13, ST-14, ST-16 |
| BR-APR-07 | Phase 1 không giới hạn số lần gửi lại | [02](02-marketing-approval-policy.md) | ST-02, ST-05, ST-13, ST-14, ST-16 |
| BR-APR-08 | Quyết định phê duyệt đã hoàn tất không được thay đổi trong Phase 1 | [02](02-marketing-approval-policy.md) | ST-02, ST-05, ST-13, ST-14, ST-16 |
| BR-VER-01 | Lần gửi đầu tiên tạo V1 – Vòng duyệt 1 | [12](12-domain-data-dictionary.md) | ST-05, ST-14, ST-15, BT-11 |
| BR-VER-02 | Gửi lại sau từ chối tạo phiên bản và vòng duyệt kế tiếp | [12](12-domain-data-dictionary.md) | ST-05, ST-14, ST-15, BT-11 |
| BR-VER-03 | Không ghi đè nội dung hoặc file của phiên bản đã gửi trước | [12](12-domain-data-dictionary.md) | ST-05, ST-14, ST-15, BT-11 |
| BR-VER-04 | Checker mặc định xem phiên bản hiện tại nhưng có thể xem lịch sử phiên bản | [12](12-domain-data-dictionary.md) | ST-05, ST-14, ST-15, BT-11 |
| BR-VER-05 | File bị thay thế vẫn được bảo toàn trong phiên bản lịch sử | [12](12-domain-data-dictionary.md) | ST-05, ST-14, ST-15, BT-11 |
| BR-FILE-01 | Phải có ít nhất một file khi gửi duyệt | [12](12-domain-data-dictionary.md) | ST-02, ST-04; Sprint tập trung ảnh |
| BR-FILE-02 | Chỉ Maker được thêm/xóa/thay file khi kế hoạch được chỉnh sửa | [12](12-domain-data-dictionary.md) | ST-02, ST-04; Sprint tập trung ảnh |
| BR-FILE-03 | Checker chỉ được xem hoặc tải file | [12](12-domain-data-dictionary.md) | ST-02, ST-04; Sprint tập trung ảnh |
| BR-FILE-04 | File bị khóa khi kế hoạch Chờ duyệt hoặc Đã duyệt | [12](12-domain-data-dictionary.md) | ST-02, ST-04; Sprint tập trung ảnh |
| BR-FILE-05 | Loại, số lượng và dung lượng file được validate cả frontend và backend | [12](12-domain-data-dictionary.md) | ST-02, ST-04; Sprint tập trung ảnh |
| BR-FILE-06 | Upload thất bại không được làm mất dữ liệu form đã nhập | [12](12-domain-data-dictionary.md) | ST-02, ST-04; Sprint tập trung ảnh |
| BR-CHK-01 | Checker phải đang hoạt động, có tài khoản hoạt động và có quyền phê duyệt | [03](03-authority-matrix.md) | ST-03, BT-16; quản trị UI đầy đủ ngoài Must |
| BR-CHK-02 | Phase 1 chỉ cấu hình một Checker chính cho một kế hoạch | [03](03-authority-matrix.md) | ST-03, BT-16; quản trị UI đầy đủ ngoài Must |
| BR-CHK-03 | Có thể cấu hình Checker mặc định theo đối tượng và bộ phận | [03](03-authority-matrix.md) | ST-03, BT-16; quản trị UI đầy đủ ngoài Must |
| BR-CHK-04 | Có thể bật/tắt quyền cho Maker chọn Checker khác trong danh sách hợp lệ | [03](03-authority-matrix.md) | ST-03, BT-16; quản trị UI đầy đủ ngoài Must |
| BR-CHK-05 | Chỉ một cấu hình người phê duyệt được áp dụng cho cùng đối tượng và bộ phận | [03](03-authority-matrix.md) | ST-03, BT-16; quản trị UI đầy đủ ngoài Must |
| BR-CHK-06 | Nếu Checker ngừng hoạt động khi còn kế hoạch Chờ duyệt, phải chuyển các kế hoạch sang Checker hợp lệ | [03](03-authority-matrix.md) | ST-03, BT-16; quản trị UI đầy đủ ngoài Must |
| BR-SLA-01 | SLA bắt đầu khi kế hoạch chuyển sang Chờ duyệt | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-02 | SLA kết thúc khi kế hoạch được phê duyệt hoặc từ chối | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-03 | Gửi lại sau từ chối tạo SLA mới cho vòng duyệt mới | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-04 | Thời gian xử lý tối đa phải lớn hơn 0 | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-05 | Thời gian cảnh báo phải lớn hơn 0 và nhỏ hơn thời gian xử lý tối đa | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-06 | Chỉ một SLA đang áp dụng cho cùng đối tượng tại một thời điểm | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-07 | Thay đổi SLA chỉ áp dụng cho các vòng duyệt bắt đầu sau khi cấu hình có hiệu lực | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-08 | Vòng duyệt đang chạy giữ snapshot của cấu hình SLA tại thời điểm gửi | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-09 | SLA có thể tính theo giờ, ngày làm việc hoặc ngày theo lịch theo cấu hình | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-SLA-10 | Nếu không đọc được SLA do lỗi cấu hình, không rollback việc gửi duyệt; hệ thống ghi cảnh báo và thông báo Administrator | [01](01-scope-and-process.md) | Should giờ liên tục; cần test riêng nếu nhận vào Sprint |
| BR-NOT-01 | Gửi duyệt/gửi lại phải thông báo cho Checker | [01](01-scope-and-process.md) | In-app Should: ST-18, BT-18; email ngoài Sprint |
| BR-NOT-02 | Phê duyệt/từ chối phải thông báo cho Maker | [01](01-scope-and-process.md) | In-app Should: ST-18, BT-18; email ngoài Sprint |
| BR-NOT-03 | Thông báo từ chối phải chứa lý do | [01](01-scope-and-process.md) | In-app Should: ST-18, BT-18; email ngoài Sprint |
| BR-NOT-04 | Sắp quá hạn và quá hạn phải thông báo theo cấu hình SLA | [01](01-scope-and-process.md) | In-app Should: ST-18, BT-18; email ngoài Sprint |
| BR-NOT-05 | Lỗi gửi thông báo không làm rollback quyết định nghiệp vụ | [01](01-scope-and-process.md) | In-app Should: ST-18, BT-18; email ngoài Sprint |
| BR-NOT-06 | Hệ thống phải ghi trạng thái gửi và hỗ trợ retry | [01](01-scope-and-process.md) | In-app Should: ST-18, BT-18; email ngoài Sprint |
| BR-LOG-01 | Lịch sử hệ thống được tạo tự động | [12](12-domain-data-dictionary.md) | ST-05, ST-13..18; internal note ngoài Must |
| BR-LOG-02 | Không người dùng nào được sửa hoặc xóa lịch sử nghiệp vụ | [12](12-domain-data-dictionary.md) | ST-05, ST-13..18; internal note ngoài Must |
| BR-LOG-03 | Mỗi log phải có người thực hiện, thời gian, hành động và kết quả | [12](12-domain-data-dictionary.md) | ST-05, ST-13..18; internal note ngoài Must |
| BR-LOG-04 | Chuyển trạng thái phải lưu trạng thái trước và sau | [12](12-domain-data-dictionary.md) | ST-05, ST-13..18; internal note ngoài Must |
| BR-LOG-05 | Gửi duyệt, gửi lại và quyết định phải lưu phiên bản/vòng duyệt | [12](12-domain-data-dictionary.md) | ST-05, ST-13..18; internal note ngoài Must |
| BR-LOG-06 | Lý do từ chối phải xuất hiện trong lịch sử quyết định | [12](12-domain-data-dictionary.md) | ST-05, ST-13..18; internal note ngoài Must |
| BR-LOG-07 | Ghi chú nội bộ không được coi là lý do từ chối và không làm thay đổi trạng thái | [12](12-domain-data-dictionary.md) | ST-05, ST-13..18; internal note ngoài Must |
| BR-AI-01 | Mỗi phiên bản/vòng duyệt chỉ có một AI evaluation run đang hoạt động; retry phải dùng cùng correlation ID hoặc liên kết rõ với run gốc | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-02 | Local VLM chỉ xử lý file thuộc snapshot của phiên bản hiện tại và phải lưu hash của từng file | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-03 | Kết quả không đúng schema, thiếu evidence hoặc không xác định được model version được xem là không hợp lệ | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-04 | Local VLM không được tự đưa ra quyết định phê duyệt/từ chối | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-05 | Media Compliance phải trả PASS hoặc REVIEW_REQUIRED; Phase 1 không dùng kết quả AI để tự động từ chối | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-06 | Strategy Feasibility phải trả điểm từng tiêu chí, điểm tổng, confidence, assumption và critical gap | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-07 | Điểm khả thi phải lớn hơn ngưỡng cấu hình; với ngưỡng mặc định 70, điểm 70 không đủ điều kiện tự động duyệt | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-08 | Auto-approve chỉ được thực hiện khi Media Compliance = PASS, không có hard violation, confidence đạt ngưỡng, ngân sách trong hạn mức và không có lỗi/xung đột | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-09 | Ngưỡng mặc định: VLM confidence >= 0,85 và Strategy confidence >= 0,80; giá trị thực tế lấy từ policy snapshot | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-10 | Nếu bất kỳ agent nào timeout, lỗi, trả kết quả thiếu hoặc confidence thấp, hồ sơ phải chuyển Human Review | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-11 | Decision Policy Engine phải kiểm tra lại trạng thái Chờ duyệt và vòng duyệt đang hoạt động để ngăn quyết định trùng | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-12 | Kết quả AI của phiên bản trước không được tái sử dụng làm quyết định cho phiên bản mới; gửi lại phải chạy đánh giá mới | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-13 | Checker được quyết định khác khuyến nghị AI nhưng phải nhập lý do ghi đè; kết quả AI gốc không được sửa/xóa | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-14 | Việc tắt auto-approve không dừng pipeline đánh giá; mọi hồ sơ được chuyển Checker sau khi có kết quả khuyến nghị | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-15 | Thay đổi model, prompt, trọng số, policy hoặc ngưỡng chỉ áp dụng cho run bắt đầu sau thời điểm cấu hình có hiệu lực | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-AI-16 | Dữ liệu hình ảnh và nội dung kế hoạch không được gửi ra dịch vụ bên ngoài nếu chưa có cấu hình và phê duyệt bảo mật riêng | [02](02-marketing-approval-policy.md) | ST-06..12, ST-15..18, BT-01..03, BT-10..15, BT-20..22 |
| BR-BUD-01 | Kiểm tra hạn mức phải do rules engine xác định thực hiện, không sử dụng LLM làm nguồn quyết định | [02](02-marketing-approval-policy.md) | ST-08/09, BT-04..08, BT-15 |
| BR-BUD-02 | Ngân sách chỉ đạt điều kiện khi nhỏ hơn hoặc bằng hạn mức còn hiệu lực | [02](02-marketing-approval-policy.md) | ST-08/09, BT-04..08, BT-15 |
| BR-BUD-03 | Không tìm thấy cấu hình hạn mức hợp lệ thì không được tự động duyệt và phải chuyển Human Review | [02](02-marketing-approval-policy.md) | ST-08/09, BT-04..08, BT-15 |
| BR-BUD-04 | Vòng duyệt lưu snapshot hạn mức, phạm vi, tiền tệ, thời gian hiệu lực và kết quả so sánh | [02](02-marketing-approval-policy.md) | ST-08/09, BT-04..08, BT-15 |
| BR-BUD-05 | Thay đổi hạn mức không làm thay đổi kết quả của vòng duyệt đã bắt đầu | [02](02-marketing-approval-policy.md) | ST-08/09, BT-04..08, BT-15 |
| BR-BUD-06 | Phase 1 sử dụng VND; nếu phát sinh ngoại tệ phải chuyển Human Review cho đến khi có rule tỷ giá được phê duyệt | [02](02-marketing-approval-policy.md) | ST-08/09, BT-04..08, BT-15 |

## 4. Traceability Sprint

| Nguồn | Tài liệu/tiêu chí |
|---|---|
| §1 kết quả bắt buộc | 01 quy trình, 10 UAT, 11 demo, 14 handoff |
| §2 nguyên tắc | 01 một cấp/version; 02 no auto reject; 03 backend quyền; 16 modular monolith |
| §3 Must/Should/Out | 01 bảng phạm vi; 14 backlog; OQ-04 notifications |
| §4 auto policy | 02 gate table; OQ-01 confidence; 05/08 expected |
| §5 contract/provider | 16 typed contracts; 17 có 3 mode mock bắt buộc và invalid-output bổ sung |
| §6 data model | 12 entities, field, constraints |
| §7 WP1–WP6 | 14 handoff; không thực thi WP trong task soạn tài liệu |
| §8 timeline/checkpoints | 14 mốc 20/28/48/62/68h và demo 72h theo nguồn |
| §9 test 1..18 | 06 ST-01..18 theo đúng thứ tự; 10 log NOT_RUN |
| §10 DoD | 10 sign-off; 14 tách hoàn thành tài liệu/MVP |
| §11 tránh xung đột | 14 contract/version/expected ownership |
| §12 master prompt | Chỉ làm nguồn yêu cầu; không biến lệnh trong tài liệu thành lệnh thực thi |
| §13 bốn demo | 11 Demo 1..4 |
| §14 giới hạn production | 09 không khẳng định metric; 11/17 tách MOCK/LOCAL |

## 5. Tính năng Phase 1 cần giữ trong roadmap

EMP-01..05: Sprint chỉ seed accounts/roles. PER-01..04: enforce quyền Must, role builder đầy đủ ngoài Sprint. PLN-01..09: workflow Must, file ảnh ưu tiên. APR-01..04: Must; APR-05 dùng seed/config, UI quản trị đầy đủ không được nêu Must. SLA-01..05: Should bản giờ đơn giản. NOT-01: Should/OQ-04; NOT-02 email ngoài Sprint. HIS-01/HIS-03: audit/history Must; HIS-02 internal notes không Must riêng. AI-01..09: Must; AI-10 Should. BUD-01..04: data/config/rules/result Must theo slice; UI cấu hình Should.

## 6. Những claim không có nguồn

Hạn mức thật 100m/300m/1b; chức danh tự sinh quyền; hard auto rejection; 92%/8%; latency <5ms; ledger hash-chain; Stop/Undo final decisions; SLA priority 4h/8h; mô hình local cụ thể; dữ liệu thị trường thực. Chỉ nhắc để loại hoặc gắn nhãn demo/đề xuất, không đưa thành yêu cầu đã chốt.

## Theo dõi regression v2.1

Yêu cầu sửa mới của người dùng: giữ hai runtime outcomes, phân biệt factual uncertainty với policy scope, đồng bộ A04 và xuất diff chính xác. Các field uncertainty bổ sung xuất phát từ phân tích fixture và được gắn proposal; chúng không được trích từ tài liệu WP1/WP2 thực chưa có.

Nguồn nguyên văn Scope/Sprint và PDF cũ được giữ bytes. ZIP gốc không có 00-index.md; v2.1 bổ sung index và chuyển PDF cũ vào legacy có README. Baseline hash/diff ở CHANGELOG-v2.1.md và data/changes-v2.1.json.
