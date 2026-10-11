# Kiểm chứng PostgreSQL và Auth notification E2E — 2026-10-11

## Kết quả

**PASS — work package in-app notification đã qua kiểm chứng trên PostgreSQL tạm và Auth browser E2E.** Kết quả này chỉ áp dụng cho fingerprint source/test bên dưới; không tính lại evidence PostgreSQL head `20261010_10` trước migration notification.

- Worktree: `C:\Users\Khoa Bi\.codex\worktrees\scope1-continuation-20261011\OrganizationAI`
- Branch / HEAD: `codex/scope1-phase1-judge-continuation-20261011` / `a806fbf1a816764c4f1dd8713b60579aa910a1fb`
- Migration head: `20261011_11`
- Dirty tree trước khi chạy: có, chứa các thay đổi AI/Auth chưa commit đã có từ trước. Runner lưu danh sách path; không reset/stash/commit.
- Checkout cũ: branch `codex/scope1-phase1-continuation-20261010`, HEAD `a1f5225a5f9828f61c07045afbf6125dbd40930d`; evidence ghi `old_checkout_status_unchanged=true`.
- Code fingerprint SHA-256: `6227209e830c26058d622d4c5de5dd01ecec8364998c5b1a6ccc5d29a89882dd`. Danh sách hash file nguồn nằm trong evidence JSON.
- Evidence: [notification-postgres-evidence.json](../docs/integration/evidence/auth-postgres-notifications/c285992f40c0447ba08537ad19dc9e9c/notification-postgres-evidence.json), run ID `c285992f40c0447ba08537ad19dc9e9c`.

## PostgreSQL và migration

Runner tạo network/container PostgreSQL 16 riêng; database directory chạy trên tmpfs. Không dùng `DATABASE_URL` của ứng dụng. Kiểm tra gồm:

1. Database rỗng được nâng đến `20261011_11`; notification table/schema được xác nhận.
2. Database synthetic được dừng ở `20261010_10`, có 2 user, role assignment, 1 plan, version và event; nâng đến `20261011_11`. Snapshot trước/sau trùng khớp cho `users`, `user_roles`, `auth_workflow_plans`, `auth_workflow_versions`, `auth_workflow_events`; không có notification tự sinh khi migration.
3. Schema notification có FK tới `users` và `auth_workflow_plans` với `RESTRICT`; index theo recipient/created và recipient/unread; unique `event_key`; CHECK constraint `ck_auth_workflow_notifications_event_type`.
4. PostgreSQL acceptance test: **1 passed**, 1 cảnh báo deprecation Starlette/httpx.

## Notification và quyền truy cập

Acceptance test trên PostgreSQL xác nhận:

- Submit/resubmit gửi `PLAN_SUBMITTED` cho Checker được gán ở round đó; round 2 gửi đến Checker mới.
- Reject/approve gửi đúng event đến Maker; synthetic auto-approve gửi `PLAN_AUTO_APPROVED` cho Maker.
- Replay quyết định và ghi lại cùng event key không nhân đôi notification.
- Lỗi chèn sau khi đã ghi notification làm rollback cả submit hoặc decision; không còn notification hay trạng thái/quyết định dở dang.
- User khác không liệt kê/đánh dấu đã đọc notification và không mở plan bằng link notification.
- GET không đổi `read_at`; mark-read lặp lại trả cùng thời điểm đọc.
- Notification chỉ chứa routing metadata cần thiết; test không tìm thấy objective, summary, note hoặc nội dung riêng khác trong response.
- Notification link không cấp quyền mới: Checker cũ sau khi plan được giao lại không còn mở được plan; người nhận hiện tại mới có quyền theo workflow.

Auto-approve chỉ chạy với cấu hình policy/budget synthetic được dựng ngay trong test trên database tạm; không bật policy trên DB/config live.

## Auth browser E2E và runtime

- Playwright: `expected=3`, `skipped=0`, `unexpected=0`, `flaky=0`.
- Browser flow: Checker đăng nhập, nhận notification submit, mở đúng plan và đánh dấu đã đọc; sau Checker từ chối, Maker nhận notification, mở cùng plan và đánh dấu đã đọc.
- Runner tự sinh password/secret ngẫu nhiên cho DB, JWT và Auth seed; test fail nếu thiếu password, không skip. Không sử dụng credential thật.
- Interpreter thực sự: `/usr/local/bin/python`, Python `3.13.15` bên trong image có sẵn `organizationai-backend:latest`; pytest `9.1.1`, SQLAlchemy `2.1.1`, FastAPI `0.141.1`, psycopg `3.3.6`. Không cần `.venv` riêng trong worktree.
- Provider: `MOCK_VLM` deterministic fixture. Đây không phải inference AI thật.
- Runner đã dừng container PostgreSQL/API và xóa network do chính run tạo; evidence ghi các container có trước được giữ nguyên, checkout cũ không đổi. Log được giữ trong thư mục evidence của run.

Lệnh chạy lại từ CMD hoặc PowerShell, không cần tự điền `DATABASE_URL`:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Khoa Bi\.codex\worktrees\scope1-continuation-20261011\OrganizationAI\scripts\run-auth-postgres-e2e.ps1"
```

Entry point gọi notification-aware runner; runner yêu cầu Docker image local, không pull image, tự tạo credentials và DB tạm rồi cleanup.

## Requirement Scope 1 còn thiếu hoặc chưa nghiệm thu

Danh sách này gộp `AGENTS.md`, `docs/scope-phase-1.md`, `docs/sprint-1-deliverables.md` và gap matrix hiện có. Các phần đã được kiểm chứng ở trên không được xem là evidence cho yêu cầu khác.

| Requirement | Trạng thái còn lại |
|---|---|
| SLA (§§8.5, 12; BR-SLA-01..10) | Chưa có persistence/configuration UI và lịch cảnh báo/quá hạn; thời lượng, ngưỡng, timezone/loại giờ, owner và cách tính khi reassign chưa được duyệt. Đây là Should trong Sprint 1 nhưng bắt buộc trong Scope Phase 1. |
| Notification SLA (BR-NOT-04) | Inbox cho submit/resubmit, Checker decisions và auto-approve đã kiểm chứng. Chưa phát warning/overdue vì policy SLA chưa chốt. Email/SMS/production provider bị loại khỏi Sprint 1 và vẫn tắt. |
| Quản lý nhân viên/quyền (Scope §§5, 8; AGENTS §4) | Lifecycle nền đã có nhưng ADMIN bootstrap/grant/revoke đang khóa đến khi owner/operator được chỉ định. API/UI custom-role vẫn tồn tại nhưng role builder động hoàn chỉnh nằm ngoài Sprint 1; CRUD/assignment custom-role chưa có PostgreSQL nghiệm thu. Cần chốt cách xử lý khác biệt giữa Scope Phase 1 và Sprint 1 trước khi mở rộng. |
| Internal note (UC_MKT_08, BR-AUTH/Scope) | Chưa triển khai luồng note và quy tắc ai được đọc/ghi; permission catalog `MARKETING_INTERNAL_NOTE` chưa có hành vi/API đầy đủ. |
| Cấu hình nghiệp vụ (Scope §§7–8; Sprint Should) | Màn hình/API quản trị cho AI policy, budget limit, rubric/threshold và version/effective date chưa đủ. Auto-approve production vẫn tắt; policy synthetic chỉ dùng trong DB tạm ở test này. |
| AI thật (AGENTS §§8–9; Sprint Must) | Adapter Local VLM và Mock có trong source, nhưng lượt này chỉ chạy Mock. Inference Local VLM chưa nghiệm thu do model digest/provenance issue đã ghi ở traceability; không thay pin digest. |
| Manual pipeline retry và dashboard (Sprint Should) | Chưa đủ nghiệm thu; không nằm trong gói notification vừa kiểm chứng. |
| Scope v1.1 approval | Tài liệu `docs/scope-phase-1.md` vẫn ghi chờ PO/Stakeholder xác nhận; owner/admin, SLA và policy doanh nghiệp còn mở. |

**Judge Đề A là gói riêng, không phải kết quả của kiểm chứng Auth notification.** Public route/API chưa có public PASS; inference thật chưa xác minh; Judge cần session/data isolation, quota/rate limit và bằng chứng cross-session; bộ artifact/feedback cuộc thi còn thiếu theo gap matrix. Kết quả Render “loading” sau 15 giây không kết luận API hỏng. Không đổi digest, bỏ Auth, hay deploy.

## Bảng chính sách SLA đề xuất để PO chốt

Các giá trị dưới đây là **đề xuất**, chưa phải policy được duyệt. Scope hiện quy định bắt đầu lúc `PENDING_APPROVAL`, kết thúc khi approve/reject và round mới có SLA mới; AGENTS chỉ cho phép bản đơn giản theo giờ liên tục trong Sprint 1.

| Quyết định | Đề xuất mặc định | Cần PO xác nhận |
|---|---|---|
| Thời lượng | 24 giờ liên tục cho mỗi approval round | Có muốn thời lượng khác theo loại/bộ phận không? |
| Ngưỡng cảnh báo | Một cảnh báo khi còn 4 giờ; một cảnh báo quá hạn khi vượt deadline | Có cần nhắc lặp lại sau quá hạn không? |
| Loại giờ | Giờ lịch liên tục; không tính lịch làm việc/ngày lễ. Lưu UTC, hiển thị Asia/Saigon | Chấp nhận cách tính đơn giản này cho Phase 1 không? |
| Bắt đầu/kết thúc | Bắt đầu khi submit thành công và plan vào `PENDING_APPROVAL` (theo BR-SLA-01); kết thúc ở approve/reject hoặc auto-approve | AI evaluation time được tính trong SLA như rule hiện tại, hay chỉ tính từ lúc vào `HUMAN_REVIEW_REQUIRED`? |
| Resubmit/reassign | Resubmit tạo SLA/deadline mới theo round mới. Reassign trong cùng round giữ nguyên deadline để không reset đồng hồ | Chấp nhận giữ nguyên deadline khi đổi Checker? |
| Người nhận | Warning/quá hạn gửi in-app cho Maker và Checker đang được gán; khi reassign, thông báo cho Checker mới và Maker. Lỗi cấu hình SLA gửi Admin | Có cần báo Checker cũ khi reassign hoặc đổi danh sách người nhận không? |

**Đề xuất để xác nhận:** 24 giờ lịch liên tục, cảnh báo trước 4 giờ, bắt đầu từ submit theo BR-SLA-01, round mới khi resubmit, không reset khi reassign, warning/overdue đến Maker và Checker hiện tại. Chưa triển khai SLA cho đến khi PO xác nhận policy và owner.

## Handoff

- Outcome: notification in-app đã qua DB migration/behavior/Auth browser verification trên fingerprint ghi ở trên.
- Files trong notification package gồm migration `alembic/versions/20261011_11_in_app_notifications.py`, runner `scripts/run-auth-postgres-notifications-e2e.ps1` và wrapper `scripts/run-auth-postgres-e2e.ps1`, helper `scripts/verify_auth_postgres_notifications.py`, PostgreSQL acceptance test `tests/integration/test_auth_workflow_postgres_notifications.py`, notification UI/Auth E2E cùng các module Auth workflow đã có trong fingerprint.
- Lệnh đã chạy và pass: `scripts/run-auth-postgres-e2e.ps1` (evidence ID nêu trên). Không chạy runner từ checkout cũ.
- Assumptions: in-app only theo quyết định người dùng; Mock provider là bằng chứng plumbing/test chứ không inference thật; policy tự động duyệt chỉ synthetic.
- Limitations: SLA chưa có policy/implementation; Judge public riêng; migration chưa áp dụng lên database cấu hình/live; Scope 1 còn partial.
- Next safe work package: PO duyệt SLA values/owner; sau đó mới xây SLA service/configuration, cảnh báo và tests trên DB tạm. Judge public tiếp tục độc lập.
