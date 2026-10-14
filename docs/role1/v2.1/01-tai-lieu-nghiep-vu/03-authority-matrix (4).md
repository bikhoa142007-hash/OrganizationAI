# 03 · Ma trận quyền, người duyệt và hạn mức

> Bộ Role 1 · Bản 2.1 · Ngày 21/09/2026 · Phạm vi: tài liệu nghiệp vụ và evaluation cho Sprint 1.
> Trạng thái: bản soạn để review; không phải xác nhận PO đã phê duyệt hoặc ứng dụng đã chạy đạt.

**Căn cứ:** Scope §4.1, §§8.1–8.2, BR-AUTH, BR-CHK, BR-BUD, §17.2; Sprint §§2–3, 9.

**Quy ước:** `[NGUỒN]` = yêu cầu đọc được trong hai file mới; `[ĐỀ XUẤT]` = thiết kế bổ sung cần chốt; `[DEMO]` = dữ liệu tổng hợp; `[CHƯA CHẠY]` = chưa có kết quả thực thi. Danh sách đầu việc Role 1 kế thừa bộ cũ; chưa đối chiếu lại được nguyên văn file phân công Role đã không còn tại đường dẫn trước đây.

## 1. Nguyên tắc

Chức danh nhân sự, bộ phận và vai trò hệ thống độc lập. “Marketing Lead” hoặc “Manager” không tự tạo quyền duyệt. Một người có cả Maker/Checker vẫn không được xử lý chính hồ sơ mình lập. Administrator không tự động được coi là Checker cho mọi hồ sơ.

## 2. Ma trận quyền backend

| Hành động | Maker | Checker được giao | Admin | System |
|---|---|---|---|---|
| Tạo/lưu nháp | Kế hoạch của mình | Nếu có thêm quyền Maker | Theo quyền bổ sung | Không giả danh người lập |
| Sửa/xóa/thay attachment | Của mình, DRAFT/REJECTED | Không | Không mặc định vượt khóa version | Quản lý lưu trữ snapshot |
| Submit/resubmit | Của mình, state hợp lệ | Không thay Maker | Không mặc định | Validate + transaction |
| Xem nội dung/file | Của mình | Hồ sơ được giao | Theo quyền xem toàn bộ | Theo nhiệm vụ xử lý |
| Approve/reject | Không nếu là Maker hồ sơ đó | Có khi active, stage cho phép | Chỉ khi cũng là Checker hợp lệ được giao | Chỉ auto-approve khi đủ policy |
| Sửa final decision/audit | Không | Không | Không | Không; chỉ ghi thêm sự kiện hợp lệ |
| Cấu hình policy/limit | Không | Không mặc định | Có quyền quản trị tương ứng | Áp dụng snapshot |
| Thay Checker mất hoạt động | Không tùy ý khi chờ | Không tự ủy quyền | Theo cấu hình/quy trình quản trị | Ghi lịch sử chuyển |
| Xem audit | Theo quyền xem hồ sơ | Theo quyền xem hồ sơ | Theo quyền audit | Ghi log |

Ẩn nút không đủ: mọi API mutation và tải file phải xác minh actor từ phiên đăng nhập, quyền, ownership/assignment, trạng thái và row version. Không tin `maker_id`, `actor_id` hoặc role trong request body.

## 3. Chọn Checker

Điều kiện đồng thời: nhân viên active, tài khoản active/không khóa, quyền approve/reject phù hợp, khác Maker; chỉ một người chính trong vòng. Cấu hình mặc định theo đối tượng/bộ phận; Maker chỉ được đổi nếu bật cấu hình và chỉ chọn người hợp lệ.

Nếu Checker bị khóa khi hồ sơ chờ: backend chặn người đó ra quyết định. Admin chuyển sang một Checker hợp lệ và ghi old/new/reason/time. Không mở round song song hoặc tự thêm cấp duyệt. UI quản trị hoàn chỉnh không phải Must Sprint; trường hợp chuyển có thể được seed/thao tác quản trị theo cơ chế repo sau khi đội triển khai chốt.

## 4. Quyền tự động khác quyền Checker

| Tình huống | System | Checker hiện tại |
|---|---|---|
| Budget ≤ L, mọi gate đạt | Auto nếu mode/enabled cho phép | Không tạo thêm decision sau khi System đã commit |
| Budget > L | Human Review, reason BUDGET_LIMIT_EXCEEDED | Xem xét theo quyền nghiệp vụ được giao; nguồn không quy định cap riêng theo chức danh |
| Không có limit/currency chưa hỗ trợ | Không auto | Xem evidence và lý do thiếu cấu hình; Admin hỗ trợ |
| Confidence thấp/hard violation | Không auto | Có 2 lựa chọn approve/reject theo policy đã chốt; không sửa evidence |
| Sai assignment/tự duyệt | Không biến thành ngoại lệ auto | Request bị chặn authorization; không tạo quyết định |

`AUTHORITY_EXCEEDED` trong bộ v2 chỉ mô tả vượt điều kiện/hạn mức tự động khi đã biết L; không suy diễn Checker mất quyền hay phải chuyển Manager. Quy định cap con người và ngoại lệ hard violation là thông tin còn thiếu, không tự bịa để xây workflow nhiều cấp.

## 5. Dữ liệu authority demo

| ID | Vai trò seed | Phạm vi |
|---|---|---|
| DEMO-MAKER-01 | MAKER | Tạo kế hoạch demo thuộc DEMO-DEPT-01 |
| DEMO-CHECKER-01 | CHECKER | Người duyệt được gán trong các case |
| DEMO-ADMIN-01 | ADMIN | Cấu hình và audit |
| DEMO-DUAL-01 | MAKER + CHECKER | Ca kiểm tra không tự duyệt |

Tên/email thực không có trong nguồn; các ID là tổng hợp. Không đưa mật khẩu production vào tài liệu; cơ chế tạo tài khoản demo do repo/README ứng dụng cung cấp. Một `DEMO-LIMIT-V2`, scope department DEMO-DEPT-01, currency VND, L = 100.000.000 VND để test; không gán L bằng tên chức danh.

## 6. Acceptance

1. Maker và Checker cùng ID → chặn trước submit; nếu assignment bị thay gian lận, backend vẫn chặn decision.
2. Checker khác người được giao → không đọc/duyệt ngoài quyền; không lộ evidence trong lỗi.
3. Người dùng có role ADMIN nhưng không được giao → không tự gọi approve thành công.
4. Checker bị khóa sau submit → request quyết định thất bại, round và snapshot không mất.
5. Hai request approve/reject hoặc auto/human cùng round → chỉ một final decision commit; request còn lại nhận conflict/đã xử lý theo contract repo.
6. Thay assignment cần audit, không đổi snapshot nội dung hoặc tạo thêm cấp.
