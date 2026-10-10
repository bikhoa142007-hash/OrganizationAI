# Mô tả checkpoint EMP/Role — Scope Phase 1

## Tóm tắt

- Thêm hồ sơ nhân viên độc lập với tài khoản đăng nhập; bổ sung API, giao diện Admin và migration `20261010_09`–`20261010_10`.
- Thêm luồng kích hoạt/đặt lại mật khẩu bằng token một lần, hết hạn sau 30 phút và chỉ lưu hash. Admin bàn giao link riêng; người nhận tự đặt mật khẩu. Cấp lại vô hiệu link cũ; reset thành công thu hồi session cũ.
- Thêm quản lý role tùy chỉnh và gán Maker/Checker cho tài khoản khác đã kích hoạt. Role built-in bất biến; ADMIN grant/revoke và bootstrap vẫn bị khóa chờ chỉ định system owner/operator. Evidence PostgreSQL ghi role seed và các guard Checker; chưa ghi gate riêng cho CRUD/assignment role tùy chỉnh.
- Khi ngừng Checker đang có hồ sơ chờ, Admin phải chọn người thay thế hợp lệ cho từng hồ sơ. Reassign, chuyển nhân viên sang INACTIVE, khóa account, thu hồi session/token và audit cùng transaction; lỗi thì rollback. Khóa account hoặc thu hồi Checker khi còn hồ sơ chờ bị chặn. Kích hoạt lại nhân viên không tự mở account hay phục hồi role.
- Cập nhật traceability và báo cáo race token với evidence PostgreSQL do người dùng chạy ngoài sandbox.

## Xác minh

- Focused evidence [`auth-postgres-verification-dd41dd5e78.json`](../docs/integration/evidence/auth-postgres-verification-dd41dd5e78.json): **PASS** cho migration DB trống lên `20261010_10` và helper employee/account/token/reassignment. JSON ghi `migration_legacy_database`, `admin_directory_postgres`, `auth_e2e` trong `gates_not_run`; các gate này chưa được tính là PASS trong focused run.
- Full evidence [`auth-postgres-verification-7308c19051.json`](../docs/integration/evidence/auth-postgres-verification-7308c19051.json): **PASS** cho migration DB trống và schema synthetic cũ lên `20261010_10`, giữ dữ liệu legacy, directory authorization/filter/pagination, lifecycle/token/reassignment và Auth E2E. E2E: 3 expected, 0 skipped, 0 unexpected, 0 flaky; có idempotency/reload case.
- Cả hai lượt được người dùng xác nhận chạy ngoài sandbox trên PostgreSQL tạm. Cleanup ghi nhận container và temporary files do runner tạo đã xóa, container có trước được giữ nguyên, `errors=[]`.
- Race RESET trong cả hai evidence có hai client/session/transaction/connection độc lập; chính xác một HTTP 204 và một HTTP 422 `VALIDATION_ERROR`; session-version và reset-audit mỗi tăng 1; password/session/replay assertions đều đạt.
- Fingerprint working tree được tái tính từ tập file của từng lượt và khớp evidence: focused `15d75df87e5f426056882c7b541629a6a0e830814a55858bd9bd81bda2b3022f`; full `b488befbf4727f435310ca2398612f819ddaa4b524e0600f16852d6f74a0b3be`. Cả hai ghi branch `codex/scope1-phase1-continuation-20261010`, HEAD `f27e6ba0e9d96fa8d1b420c140a43a7e8cd466e0`, `dirty=true`. HEAD đơn lẻ không định danh source; fingerprint bao gồm toàn working tree tại runner start. README và báo cáo được cập nhật sau hai lượt; implementation source và test không đổi.
- Local evidence [`emp-role-local-verification-2026-10-10.json`](../docs/integration/evidence/emp-role-local-verification-2026-10-10.json) ghi full backend 326 passed/84 subtests, focused EMP/role 19 passed, frontend 150 tests trong cả hai lượt (không timeout/skip), typecheck/build/compile/Alembic head PASS. Đây là test local, không thay thế PostgreSQL; file ghi database URL đã được gỡ khỏi process environment. Không chạy lại full suite trong bước đóng checkpoint này vì implementation source và test không đổi.

## Còn thiếu

- Scope Phase 1 vẫn **PARTIAL**. PostgreSQL/Auth E2E dùng `MOCK_VLM`, không chứng minh real AI inference hoặc chất lượng nội dung AI.
- ADMIN grant/revoke và bootstrap vẫn khóa đến khi có system owner/operator được chỉ định.
- Một số quyền trong catalog chưa có hành vi API/workflow tương ứng; CRUD/assignment role tùy chỉnh chưa có gate PostgreSQL riêng trong evidence đã cung cấp. SLA, notification và cấu hình policy còn thiếu.
- Live judge route không cần tài khoản, các artifact/tiêu chí competition và public deployment chưa được các evidence này xác minh.
- Evidence lỗi lịch sử có SQL parameters/token hash được giữ local và không nằm trong checkpoint công khai.

## Cơ sở migration và publication

Migration `20261010_10` nối tiếp `20261010_09`. Hai runner dùng PostgreSQL synthetic, không đọc/ghi DB live; cả hai xác nhận cleanup tài nguyên riêng và giữ nguyên container có trước. Checkpoint thuộc branch `codex/scope1-phase1-continuation-20261010`; nội dung này không tuyên bố Scope 1 hoàn tất.
