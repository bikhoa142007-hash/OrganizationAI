# Báo cáo sửa race token đặt lại mật khẩu — 2026-10-10

## Kết luận

Evidence `auth-postgres-verification-6c6fd6d1c9.json` ghi nhận hai request độc lập cùng dùng một token RESET đều trả HTTP 204; audit reset tăng 2 và `session_version` tăng 2. Evidence đồng thời xác nhận hai client, hai session, hai transaction và hai connection độc lập. Đây là lỗi xử lý cạnh tranh phía backend, không phải do test dùng chung session.

Trong service, truy vấn đầu tiên đã nạp toàn bộ `AuthManagementToken` vào SQLAlchemy identity map trước khi chờ các khóa hàng. Khi request thứ hai chờ request đầu commit rồi truy vấn token bằng `FOR UPDATE`, SQLAlchemy có thể trả lại instance đã nạp với `consumed_at` cũ nếu không yêu cầu refresh. Vì vậy request thua không nhìn thấy token vừa bị tiêu thụ.

## Bản sửa

`src/backend/application/employee_admin.py`, hàm `consume_management_token`:

- Truy vấn sơ bộ chỉ lấy scalar `user_id`, không nạp entity token trước khi khóa.
- Khóa theo thứ tự `EmployeeProfile → User → AuthManagementToken`; token được đọc bằng `FOR UPDATE` và `populate_existing=True` để lấy trạng thái mới nhất sau khi chờ.
- Đọc thời gian hiện tại sau khi lấy khóa. Kiểm tra hiệu lực, tiêu thụ token, cập nhật mật khẩu, tăng `session_version` và ghi audit vẫn nằm trong cùng `_write_transaction`; không có commit riêng.
- Token bị tiêu thụ/hết hạn trả lỗi nghiệp vụ hiện hành `422 VALIDATION_ERROR`. RESET và ACTIVATION dùng chung cơ chế này.
- Thứ tự khóa tương thích với các luồng reissue, khóa tài khoản và vô hiệu hóa: profile → user → management token.
- `AuthManagementToken` model khai báo cùng `CheckConstraint` `ck_auth_management_tokens_purpose` như migration head 10.
- Ca out-of-catalog thử `purpose='UNKNOWN'` trong savepoint và chỉ đạt nếu PostgreSQL trả `CheckViolation`, SQLSTATE `23514`, đúng constraint; sau rollback, token RESET hợp lệ vẫn còn nguyên và session tiếp tục truy vấn được.
- `/api/auth/activate` là endpoint chung; token purpose hợp lệ `ACTIVATE` hoặc `RESET` tự chọn thao tác. Không có endpoint reset riêng để thiết kế một ca token hợp lệ nhưng gửi nhầm hành động.
- Log/evidence mới khử dòng `Failing row contains`, khối `[SQL: ...]` và `[parameters: ...]`; giữ loại lỗi/constraint/vị trí cần chẩn đoán.

Override DB của runner tạo Session từ cùng session factory/engine PostgreSQL và chỉ gắn listener để ghi nhận session/transaction/connection. Override không đổi isolation, transaction boundary hay commit semantics.

## Kiểm tra đã chạy

| Gate | Kết quả | Bằng chứng / giới hạn |
|---|---|---|
| Unit/regression runner và employee-admin tests đã ghi trong `emp-role-local-verification-2026-10-10.json` | PASS — 19 focused tests | Kiểm tra cục bộ; không thay thế PostgreSQL. |
| Người dùng chạy `--only employee-admin` ngoài sandbox | PASS | `evidence/auth-postgres-verification-dd41dd5e78.json`: migration DB trống lên `20261010_10`; employee/account/token/reassignment helper PASS; gate migration legacy, directory và Auth E2E được ghi trong `gates_not_run`, nên không tính là PASS. |
| Người dùng chạy toàn runner ngoài sandbox | PASS | `evidence/auth-postgres-verification-7308c19051.json`: migration DB trống và synthetic legacy lên `20261010_10`, Admin directory, employee/account/token/reassignment và Auth E2E đều PASS. PostgreSQL 16.15; không truy cập DB live. |
| Race RESET trên PostgreSQL | PASS trong focused và full evidence | Mỗi lượt ghi hai client/session/transaction/connection độc lập; một HTTP 204, một HTTP 422 `VALIDATION_ERROR`, không exception. `session_version_delta=1`, `password_reset_audit_delta=1`; password của request thắng khớp, password cũ không khớp, session cũ bị thu hồi. Replay sau race bị 422 và không tạo side effect. |
| Purpose CHECK constraint | PASS trong focused và full evidence | Giá trị purpose ngoài catalog bị `CheckViolation`, SQLSTATE `23514`, constraint `ck_auth_management_tokens_purpose`; savepoint rollback giữ token RESET hợp lệ chưa tiêu thụ. `/api/auth/activate` là endpoint chung cho ACTIVATE/RESET nên không có endpoint reset riêng để thử token hợp lệ ở “sai thao tác”. |
| Cleanup | PASS trong cả hai evidence | Container và temporary files do mỗi runner tạo đã xóa; các container có trước được giữ nguyên; danh sách missing/changed rỗng; `errors=[]`. |

Người dùng xác nhận cả hai lượt được chạy ngoài sandbox. Hai evidence ghi branch `codex/scope1-phase1-continuation-20261010`, HEAD `f27e6ba0e9d96fa8d1b420c140a43a7e8cd466e0` và dirty working tree. Fingerprint tái tính từ tập file của từng lượt khớp evidence: focused `15d75df87e5f426056882c7b541629a6a0e830814a55858bd9bd81bda2b3022f`; full `b488befbf4727f435310ca2398612f819ddaa4b524e0600f16852d6f74a0b3be`. Snapshot định danh working tree đầy đủ, không chỉ HEAD hay riêng EMP/Role. Báo cáo này được cập nhật sau khi chạy; source implementation không đổi.

Evidence lỗi lịch sử `evidence/auth-postgres-verification-6c6fd6d1c9.json` và `evidence/auth-postgres-verification-f4802d9b15.json` được giữ nguyên. Evidence f480 chứa nội dung hàng/SQL parameters/token hash nên không đưa vào checkpoint công khai. Runner mới chỉ ghi loại lỗi, constraint và vị trí an toàn; không ghi `Failing row contains`, SQL parameters, token, password, cookie hay URL có token.

Auth E2E trong full runner là 3 expected, 0 skipped, 0 unexpected, 0 flaky; có idempotency/reload case và dùng `MOCK_VLM` xác định. Đây không phải real AI inference. Hai runner chỉ chứng minh các gate có tên trong JSON, không chứng minh hoàn tất Scope 1.
