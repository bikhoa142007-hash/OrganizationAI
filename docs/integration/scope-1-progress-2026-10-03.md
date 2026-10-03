# OrganizationAI Scope 1 handoff — 2026-10-03

## Kết quả

**PARTIAL — Auth-first và các kiểm tra cách ly đã sẵn sàng; chưa deploy staging và
chưa thể tuyên bố hoàn tất Scope 1.** Không có Render service/database nào được tạo
hoặc cập nhật trong phiên này. Chưa có URL hay commit đang chạy trên staging.

Branch làm việc: `feature/auth-first-staging`, bắt đầu từ `29ec623`.

## Phân biệt nguồn scope

`docs/scope-phase-1.md` phiên bản 1.1 (20/09/2026) ghi trạng thái *baseline cập nhật
theo kiến trúc AI, chờ PO/Stakeholder xác nhận*. Tài liệu mô tả sản phẩm Phase 1 rộng:
Maker–AI–Checker, SLA, thông báo, audit, quản lý tài khoản/vai trò và cấu hình.

`docs/sprint-1-deliverables.md` xác định Sprint 1 là lát dọc 72 giờ, không phải toàn
bộ Phase 1. Draft, version/round, upload, submit, AI/policy, Checker, từ chối và gửi
lại là Must. SLA đơn giản, thông báo in-app, màn hình cấu hình, retry thủ công và
dashboard là Should; quản trị nhân sự/tài khoản hoàn chỉnh và email thật nằm ngoài
Sprint. Các hướng dẫn Sprint trong `AGENTS.md` của người dùng tiếp tục có hiệu lực.

Vì vậy, chưa coi các phần chỉ có trong Phase 1 draft là acceptance đã được duyệt,
và cũng không đánh dấu Scope 1 hoàn tất chỉ vì route hoặc màn hình tồn tại.

## Ma trận phạm vi và bằng chứng

| Hạng mục | Kết quả hiện tại | Bằng chứng / phần còn thiếu |
|---|---|---|
| Auth là cửa vào website | Đã triển khai ở code: `/` khôi phục phiên rồi chuyển `/login` hoặc trang theo vai trò; protected workflow giữ deep link; 401 khác lỗi backend; 403 sang trang từ chối; logout lỗi không giả báo thành công. | Vitest, typecheck, production build đã đạt. Auth Playwright live bị skip vì không có tài khoản/mật khẩu DB staging; chưa xác minh trình duyệt trên URL thật. |
| Maker/Checker workflow | Backend Auth workflow, quyền, version/round, file riêng tư, Checker decision, audit và optimistic concurrency đã có; smoke thủ công nay dùng duy nhất một plan qua reject → sửa/resubmit → approve. | Backend suite và Playwright demo cách ly đạt. Chưa chạy workflow Auth trên PostgreSQL thật. |
| Self-registration | Route public config chỉ lộ `registration_enabled`; public registration tạo MAKER; email/phone không được coi là đã xác minh. Login giới hạn 50/IP và 10/identifier trong 15 phút; register 5/IP và 25 toàn service mỗi giờ. | Giới hạn trong bộ nhớ một API worker, mất khi process restart; phù hợp staging lưu lượng thấp, chưa phải limiter phân tán cho production. Staging Blueprint bật đăng ký; chưa có Render access protection. |
| PostgreSQL Auth | Migration bổ sung catalog MAKER/CHECKER/ADMIN, không tạo người dùng. Launcher staging bắt buộc `APP_ENV=production`, HTTPS origin, cookie Secure và PostgreSQL; migrate trước khi mở một Uvicorn worker. | Migration lên/xuống được kiểm thử với DB SQLite tạm dành riêng cho migration test. Không có `DATABASE_URL` PostgreSQL khả dụng; chưa kết nối hoặc chạy migration trên DB người dùng. |
| Judge Demo | Route app chuyển dưới `/demo/*`; legacy route redirect sang `/demo`; demo tắt trong Auth staging và được bật tường minh trong cấu hình Judge Demo hiện tại. Không ghép `X-Demo-Actor` với JWT. | Playwright chạy riêng trên SQLite mới có timestamp. Không mở hay ghi vào SQLite đã restore. |
| Media/Strategy/Local VLM | UI hiển thị kết quả từng stage; điểm 0 được phân biệt với thiếu kết quả; media ngoài scope không bị gọi là model đã đánh giá. Provider và Mock là tường minh; pipeline fail closed sang Human Review khi thiếu cấu hình. | Test dùng mock/transport giả lập. Không chạy Local VLM/inference. Auto-approval vẫn tắt. Cấu hình Media/Strategy, policy/budget được duyệt và inference runtime staging còn thiếu. Theo thông tin người dùng cung cấp (chưa đọc lại DB), plan `MKT-C792…` đang APPROVED V1/R1 với Strategy score 0 và Media skipped do scope mismatch; không dùng dữ liệu đó làm bằng chứng live mới. Point anchors Strategy chưa được PO phê duyệt. |
| SLA, notifications, admin/config screens | Chưa hoàn thiện; không nằm trong Sprint 1 Must theo tài liệu deliverables. | Phase 1 doc vẫn pending PO/Stakeholder confirmation. Đây là gap nếu PO xác nhận chúng bắt buộc cho Scope 1. Admin-only chỉ vào `/account`, không có quyền đọc/duyệt plan mặc định. |
| Staging/deployment | Có Blueprint riêng `deployment/render.auth-staging.yaml`, API/static/PostgreSQL Free, branch hiện tại, auto-deploy off, DB private-only, health/readiness check và SPA rewrite. | Deploy bị chặn: chưa có authenticated Render dashboard/project visibility để xác nhận ownership, service tác động, còn Free Postgres slot hay không, hoặc chấp nhận thời hạn Free DB. Không xóa/thay database hiện hữu để giải phóng slot. |

## Cấu hình staging được chuẩn bị

- API và static site dùng hai origin HTTPS; CORS lấy đúng origin static từ Render.
- Cookie Auth: HttpOnly, Secure, SameSite=Lax; API base URL lấy từ service HTTPS.
- Đăng ký bật cho Maker; không seed tài khoản chung mật khẩu. Role catalog migration
  không tạo tài khoản Checker. Cần quy trình cấp Checker có kiểm soát trước live flow;
  không có endpoint công khai nâng role.
- Demo bị tắt ở site Auth. AI provider khai báo rõ `LOCAL_VLM`, remote inference tắt,
  không cấu hình model/host, không Mock fallback và auto-approval vẫn off. Staging sẽ
  báo `NOT_CONFIGURED`/Human Review cho đến khi có runtime và business config đã duyệt.
- Render Free Postgres có giới hạn lưu trữ ngắn: hết hạn sau 30 ngày, 14 ngày ân hạn,
  không có managed backup và chỉ một Free instance đang hoạt động mỗi workspace.
  Không dùng cấu hình này cho hồ sơ phê duyệt thật hoặc dữ liệu cần lưu dài hạn.
  [Render Free plan](https://render.com/docs/free).

## Kiểm thử đã chạy

| Lệnh | Kết quả |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | 286 passed, 84 subtests passed; 2 cảnh báo deprecation có sẵn từ FastAPI/Starlette test client. |
| `npm run test --prefix frontend` | 50 tests passed, 10 files. |
| `npm run build --prefix frontend` | TypeScript và Vite production build passed. |
| `npm run test:e2e --prefix frontend` | 5 passed, 2 Auth-live tests skipped do thiếu secret/tài khoản local; không gọi inference. |
| `node --test deployment/validate_frontend.test.mjs` | 2 passed. |
| `node deployment/validate_frontend.mjs` với fixture HTTPS | URL shape hợp lệ; đây không phải xác minh URL đã deploy. |
| `git diff --check` | Passed; Git chỉ cảnh báo line ending CRLF theo config Windows. |
| YAML parse local | Chưa chạy được: workspace không cài PyYAML, `yaml` hoặc `js-yaml`. YAML đã được rà soát thủ công; cần Render Blueprint validation sau khi có dashboard access. |

Playwright dùng DB riêng `runtime/demo-e2e-1791015511898.sqlite3`; test tạo đúng hai
plan synthetic trong DB này:

- `DEMO-f5b3a026-42b5-492b-a37a-a74abe1be312` — `E2E auto campaign`, Round 1 đã đóng
  với quyết định Checker APPROVED.
- `DEMO-f3280808-8d54-474a-ba0f-030cb141a798` — `E2E budget review`, Round 1 bị từ
  chối, Round 2 đang active sau Maker resubmit, chưa có final decision.

Đây là dữ liệu test trong SQLite tạm, không phải plan local Auth/PostgreSQL hay staging.
Không xóa file test hoặc bản ghi nào trong bước bàn giao.

## Bảo toàn dữ liệu

Fingerprint dùng cùng thuật toán đầu/cuối: mở SQLite `mode=ro`, bật
`PRAGMA query_only=ON`, sắp `attachment_id COLLATE BINARY`, tạo manifest gồm
`attachment_id`, `media_type`, byte size và SHA-256 nội dung BLOB; JSON key-sorted,
compact separators, rồi SHA-256 toàn manifest.

| File | Rows đầu phiên | Fingerprint đầu phiên | Rows cuối phiên | Fingerprint cuối phiên |
|---|---:|---|---:|---|
| `runtime/demo-organization.sqlite3` | 5 | `e7270cb30c34e22e401acde733c4637c1a19bacc0bc1f16ed01977d82f6992eb` | 5 | `e7270cb30c34e22e401acde733c4637c1a19bacc0bc1f16ed01977d82f6992eb` |
| `backups/judge-demo-restore-20261002-174216/judge-demo-seed-20260922.sqlite3` | 5 | `e7270cb30c34e22e401acde733c4637c1a19bacc0bc1f16ed01977d82f6992eb` | 5 | `e7270cb30c34e22e401acde733c4637c1a19bacc0bc1f16ed01977d82f6992eb` |
| `backups/judge-demo-restore-20261002-174216/pre-restore-container-state/organizationai/demo-organization.sqlite3` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `backups/judge-demo-20261002-171802/judge-demo.sqlite` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |

Không tìm thấy baseline theo từng attachment ID có timestamp lịch sử; so sánh này chỉ
xác nhận runtime hiện tại trùng seed backup đã nêu, không chứng minh hồi tố lịch sử
trước đó. Không có `DATABASE_URL` và Docker CLI để đối chiếu local PostgreSQL; không
truy cập hay sửa PostgreSQL, phiên bản/evaluation/decision/audit cũ, hai bản nháp,
SQLite restore hoặc backup. Không tạo live plan mới và không chạy model local.

## Dùng thử sau khi staging được duyệt

1. Operator vào `/register`, tạo tài khoản MAKER rồi đăng nhập tại `/login`.
   Email/phone hiện chỉ là dữ liệu nhập, chưa có bước xác minh.
2. MAKER được chuyển tới `/workflow/plans`; tạo draft, gán Checker đã được cấp role,
   đính kèm ảnh rồi submit. Trang chi tiết hiển thị Version/Round và từng bước AI.
3. Checker vào `/workflow/reviews`, xem bản snapshot, nhập lý do và approve/reject.
   Sau reject, Maker mở plan, sửa nội dung và gửi lại; round mới được tạo.
4. Chưa thể chạy bước 3 trên staging cho đến khi có Checker được provision an toàn và
   operator xác nhận DB/service staging. Với AI chưa cấu hình, kiểm tra fallback chỉ
   ở tests; không gọi Local VLM từ máy developer.

## Rollback và bước tiếp theo

- Rollback web/API bằng cách chọn deployment trước đó trong Render Dashboard. Không
  downgrade migration, drop database hoặc xóa dữ liệu khi rollback; migration role
  catalog là additive.
- Git handoff: branch `feature/auth-first-staging`; commits `6c4f9f9` (AI stage/smoke
  runner) và `d323990` (Auth-first/staging); [Draft PR #17](https://github.com/bikhoa142007-hash/OrganizationAI/pull/17).
- Bước cần quyền: đăng nhập Render trong dashboard, xác nhận project/workspace và
  rằng tạo đúng một PostgreSQL Free staging riêng được phép. Xác nhận slot Free còn
  trống và chấp nhận vòng đời 30 ngày; nếu cần persistence dài hơn, chọn provider/gói
  đã được chủ sở hữu duyệt trước. Không gửi secret qua chat.
- Sau đó validate Blueprint plan, tạo service/DB, chờ migration/readiness, kiểm tra
  cookie/CORS/deep links trên HTTPS. Chỉ tạo tối đa một live plan synthetic sau khi
  Checker identity và AI behavior được xác nhận; ghi ID/status ngay khi tạo.
- Trước merge cần code review PR. PR hiện ở trạng thái draft; branch chưa deploy.
