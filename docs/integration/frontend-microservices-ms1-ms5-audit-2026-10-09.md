# Frontend MS1–MS5 branch audit — 2026-10-09

## Kết luận

**Cần sửa trước khi tích hợp.** Nhánh đồng đội có một vertical slice frontend đáng giữ và gọi đúng các endpoint Auth workflow hiện có; source diff của nhánh không thêm backend service, API hay migration. Tuy nhiên, form mới từ chối ngân sách `0` trong khi API và rule hiện hành chấp nhận `0`. Giao diện audit cũng không hiển thị `override_reason` dù server đã lưu nó. Cần sửa hai điểm này và chạy kiểm chứng trên đúng trạng thái tích hợp trước khi coi luồng đã sẵn sàng.

Tên `microservices MS1–MS5` là tên commit/nhánh, không phải bằng chứng có năm microservice độc lập. Thực tế 5 nhóm được rà trong báo cáo là các khu vực chức năng của frontend dùng chung FastAPI Auth workflow.

## Baseline và phạm vi bằng chứng

| Mục | Kết quả |
|---|---|
| Working branch | `codex/scope1-phase1-20261009` |
| Current HEAD | `e85363ee722e838791e1053900af9d44088f982b` |
| Remote baseline sau fetch | `origin/codex/scope1-phase1-20261009` = `e85363ee722e838791e1053900af9d44088f982b` |
| Nhánh đồng đội sau fetch | `origin/feature/frontend-microservices-ms1-ms5` = `7ebb9ddd1044a59eb2994e6ab4a48569f3b775b5` |
| Merge-base thực tế | `6ba137c0e5d57ad924754cb0949b92def3655299` |
| Số commit sau merge-base | Baseline: 1; nhánh đồng đội: 5 |
| Working tree trước khi viết báo cáo | Sạch: không staged, unstaged hay untracked |
| Fetch | Thành công từ `origin`; không dùng `main` làm baseline |

Merge-base là `6ba137c` (checkpoint trước PR #20), không phải giả định rằng toàn bộ nhánh đồng đội đã vào `main`. So với merge-base, baseline hiện tại thêm các thay đổi Scope 1/Verify; nhánh đồng đội thêm hoặc sửa 26 file frontend, không có backend file hay migration trong diff của chính nhánh đó. Không có file nào bị xóa trong diff `6ba137c..7ebb9dd`.

So sánh hai cây cuối có nhiều file chỉ xuất hiện ở baseline e853 (Verify CI, Verify Dashboard tests, auth PostgreSQL E2E script và các báo cáo/evidence mới). Đây là phần nằm ngoài lịch sử của nhánh đồng đội sau merge-base, **không phải bằng chứng nhánh đồng đội chủ ý xóa chúng**. Khi tích hợp phải giữ phần baseline này; không thay toàn bộ cây e853 bằng cây 7ebb.

Phạm vi audit là source và tài liệu tại hai revision trên. Không sửa source, chạy test/build/lint, chạm database/container, migration/seed, gọi model, commit hay push. Các kết quả test nêu dưới đây là do người dùng cung cấp, không phải lượt chạy của audit này.

## Repository context theo hướng dẫn dự án

- **Stack và package manager:** React + TypeScript + Vite ở `frontend/`, dùng npm và `frontend/package-lock.json`; backend Python FastAPI/Uvicorn, SQLAlchemy/Alembic, PostgreSQL cho Auth workflow. `requirements.txt` là dependency list Python; repository không khai báo Poetry/uv.
- **Database và demo:** Auth workflow dùng PostgreSQL qua `src/backend/db/session.py` và API workflow có xác thực. Judge Demo giữ API/client và workflow riêng, SQLite riêng; frontend vẫn có `/demo` và legacy redirect trong `AppRoutes.tsx`. Không được thay service Auth bằng demo actor hoặc mock.
- **AI:** Provider boundary và pipeline nằm dưới `src/ai_pipeline/` (bao gồm adapter/Local VLM, task evaluators và mock provider); Auth orchestration được nối từ `src/backend/application/auth_workflow_ai.py`. Nhánh đồng đội không đổi chúng.
- **Authentication/authorization:** cookie JWT `HttpOnly`, `/api/auth/login`, `/me`, `/logout`; các route dùng dependency kiểm tra role và service kiểm tra ownership/assignment ở backend. Client gửi `credentials: 'include'`. Frontend role guard chỉ bổ sung UX, không thay backend authorization.
- **Schema/migrations:** Alembic revisions `20260925_01` đến `20261009_08`; revision 08 thêm creation idempotency key/hash và unique index theo Maker. Seed code có `src/backend/seed_auth.py` và `src/backend/seed_demo.py`.
- **Lệnh hiện có:** backend `python -m pytest -q`; frontend `npm run test`, `npm run build`/`npm run typecheck`, `npm run test:e2e`. `build` gồm TypeScript build và Vite build. Không tìm thấy script lint hoặc cấu hình ESLint/Ruff trong repository.
- **Module có thể tái dùng:** `authWorkflowService`, `authService`, `AuthContext`, `RequireAuth`, `AuthWorkflowRoleGuard`, `AuthenticatedWorkflowShell`, `StatePanel`, workflow DTO/types, backend `auth_workflow` application service, `WorkflowPlanFilters` mới trong nhánh đồng đội.

### Thay đổi dự kiến nếu được tích hợp sau này

Frontend: `AuthContext`, login/register/session routing, `AuthenticatedPlansPage`, `AuthenticatedWorkflowFormPage`, `AuthenticatedWorkflowDetailPage`, `authWorkflowService`, workflow types, filter module/tests và `styles.css`. Backend contract hiện có đã đủ cho các bước Maker/Checker; diff của nhánh đồng đội không yêu cầu API hoặc migration mới. Cần hòa giải riêng phần `styles.css` vì cả e853 và nhánh đồng đội đều sửa file này. Không chép đè frontend: cần giữ `/demo`, Verify Dashboard, test, mock service và các thay đổi Verify từ e853.

## Ma trận 5 nhóm chức năng

| Nhóm | File chính | Bản hiện tại `e85363e` | Nhánh đồng đội `7ebb9dd` | API/contract | Mock hay dữ liệu thật | Xung đột / đề xuất |
|---|---|---|---|---|---|---|
| **Auth và phân quyền** | `frontend/src/context/AuthContext.tsx`, `services/auth.ts`, `services/authNavigation.ts`, `components/auth/RequireAuth.tsx`, `components/auth/AuthenticatedWorkflowShell.tsx`, `routes/AppRoutes.tsx`, Login/Register pages | Đã có cookie session và role-aware routes từ phần code chung; current commit e853 chủ yếu bổ sung Verify/evidence, không thay Auth API. | Tăng xử lý network/API errors, correlation IDs, hết hạn session, safe return path và route tests. Giữ ba miền `/workflow`, `/demo`, legacy redirect. | `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`; request Auth có credentials. Route guard theo `MAKER`, `CHECKER`, `ADMIN`; backend kiểm quyền lại. | Auth page gọi API thật; test có stub service. Judge Demo là luồng riêng. | Hợp đồng login/session phù hợp backend. `homeForRoles()` hiện đưa ADMIN tới `/workflow/plans`; test hiện hành cũng yêu cầu vậy, route đọc được cho ADMIN. Giữ redirect này. Tại thời điểm audit, ma trận chưa diễn đạt rõ tổ hợp `ADMIN+MAKER`; quyết định 2026-10-10 và phần test hồi quy được ghi ở mục follow-up bên dưới. Pure ADMIN vẫn bị chặn sửa/quyết định ở route/API. |
| **Maker tạo/sửa/upload/submit** | `AuthenticatedWorkflowFormPage.tsx`, `services/authWorkflow.ts`, `types/authWorkflow.ts`, `src/backend/api/auth_workflow.py`, `src/backend/application/auth_workflow.py` | API backend đã có draft, upload riêng tư, expected revision, submit, version/round và idempotency. UI cũ có cùng các điểm nối cơ bản. | Form mới làm rõ tải Checker, validate, lưu draft, cập nhật → upload → submit tuần tự, giữ dữ liệu khi lỗi và xử lý revision conflict. | `GET /workflow/checkers`; `POST /workflow/plans` + `Idempotency-Key`; `PUT /plans/{id}` + `expected_revision`; `POST /plans/{id}/attachments` multipart + revision; `POST /plans/{id}/submit` + revision. Các route và field khớp backend. | Workflow dùng PostgreSQL/Auth API thật; không có mock fallback runtime. | **P1:** UI loại `0` khỏi ngân sách dù backend chấp nhận; sửa trước. Key tạo draft nằm trong `Map` bộ nhớ nên còn được dùng lại khi retry cùng trang nhưng mất khi reload sau phản hồi mạng không rõ; cần quyết định cách giữ stable key nếu phải bảo đảm retry qua reload. Không thấy endpoint xóa/thay attachment; scope hiện chỉ bắt buộc upload ít nhất một ảnh. |
| **Checker review queue và quyết định** | `AuthenticatedPlansPage.tsx` (`reviews`), `AuthenticatedWorkflowDetailPage.tsx`, `authWorkflow.ts`, `src/backend/api/auth_workflow.py`, `src/backend/application/auth_workflow.py` | Backend list review giới hạn plan đang `PENDING_APPROVAL` được giao; detail và quyết định enforce checker được giao, active round, không tự duyệt và idempotent. | Queue dùng API phân trang; detail khóa Maker content và cho Checker approve/reject, tải trạng thái mới, xử lý 409, recovery qua POST. Từ chối cần lý do; override được gửi trong body. | `GET /workflow/reviews?offset&limit`; `GET /plans/{id}`; `POST /plans/{id}/rounds/{round}/decision`; recovery `POST /plans/{id}/rounds/{round}/recovery`. Backend kiểm quyền và active round; recovery không chạy qua GET. | Dữ liệu thật từ Auth/PostgreSQL. UI không tự quyết định kết quả AI. | Hợp đồng request khớp. Frontend khóa action khi AI đang pending/processing và backend từ chối thêm. Cần xác nhận nghĩa nghiệp vụ của `RECOMMEND_HUMAN_REVIEW`: cả UI/backend hiện coi nó tương ứng với hành động REJECTED để không yêu cầu override, dù nhãn mô tả là “Checker xem xét”; nếu đó chỉ là route sang người, đây không phải recommendation cuối cùng và cần thống nhất mapping/override. |
| **Audit, lịch sử và evidence** | `AuthenticatedWorkflowDetailPage.tsx`, `AuthenticatedAuditPage.tsx`, `authWorkflow.ts`, `auth_workflow_schemas.py`, `_plan_dict()` | Backend trả history, version snapshots, hashes, AI evaluations/decision; global audit có `items/offset/limit/total`. | Detail render event history, rounds/versions, Local VLM/task outputs, errors, recommendation, evidence, hashes; attachment fetch dùng cookie và object URL tạm. Global audit page dùng API thật. | `GET /workflow/plans/{id}`, `GET /workflow/audit?offset&limit`, `GET /plans/{id}/attachments/{attachment_id}`; read path không làm recovery/ghi dữ liệu. | API thật. Attachment không có public URL; Admin không được tải ảnh nếu không đồng thời là Maker/Checker được phép. | **P2:** server ghi `override_reason` trong audit event/decision nhưng plan timeline chỉ hiển thị `details.reason`; global AuditRow cũng chỉ liệt kê version, round, reason. Hiển thị trường override trong audit view để trace quyết định. Previous snapshot hiện bày summary và tên/hash file, không render toàn bộ payload snapshot; cân nhắc nếu checker cần xem trọn nội dung từng version trên UI. |
| **Tìm kiếm, lọc và danh sách** | `AuthenticatedPlansPage.tsx`, `components/auth/workflow/WorkflowPlanFilters.tsx`, `services/workflowPlanFilters.ts`, `authWorkflow.ts`, `auth_workflow.py` | Backend list hiện hỗ trợ `offset/limit`; phân quyền maker/admin và queue checker được lọc ở server. | Thêm lọc từ URL, lọc text/trạng thái/bộ phận/ngày trên các trang đã tải, tải tiếp theo page size 100, trạng thái loading/error/retry. | `GET /workflow/plans?offset&limit`, `GET /workflow/reviews?offset&limit`; response là array, không có `total` hoặc server-side query/filter. | Server trả dữ liệu thật; thao tác filter hiện chạy trên frontend. | Trang ghi rõ “kết quả trong yêu cầu đã tải” và báo khi còn trang; không nhận diện nhầm kết quả local là toàn bộ server. Nếu yêu cầu là search toàn bộ dữ liệu hoặc tổng số chính xác, API hiện thiếu query params và total count; nếu chấp nhận lọc trên dữ liệu đã tải thì có thể giữ nguyên. |

## Findings theo mức độ

### P1 — Ngân sách bằng 0 không thể gửi từ UI

`frontend/src/pages/AuthenticatedWorkflowFormPage.tsx@7ebb9dd:304-305,380-381` ghi hướng dẫn “số nguyên dương” và dùng regex bắt đầu bằng `[1-9]`, nên `0` bị chặn ngay trên frontend. Trong khi `src/backend/application/auth_workflow.py@e85363e:718-719` chấp nhận `0|[1-9]...` và `docs/role1/v2.1/02-marketing-approval-policy.md@e85363e:25` ghi rõ 0 hợp lệ. Detail formatter tại `AuthenticatedWorkflowDetailPage.tsx@7ebb9dd:489` cũng hiển thị `0` thành `—`.

**Tác động:** Maker không thể gửi một kế hoạch có ngân sách bằng 0 qua form, và audit/detail làm mất giá trị hiển thị. Đồng bộ validation/help/formatting với contract backend trước khi tích hợp.

### P2 — Không nhìn thấy lý do override trong audit UI

Backend ghi `override_reason` vào audit event (`src/backend/application/auth_workflow.py@e85363e:1295-1308`). Nhánh UI gửi field này qua decision endpoint, nhưng detail history chỉ đọc `event.details.reason` (`AuthenticatedWorkflowDetailPage.tsx@7ebb9dd:170`), còn global AuditRow chỉ gom `version`, `round`, `reason` (`frontend/src/pages/AuthenticatedAuditPage.tsx@e85363e:52-54`).

**Tác động:** Dữ liệu vẫn được lưu ở backend nhưng người xem audit không thấy lý do ghi đè AI. Hiển thị rõ `override_reason`; không cần đổi schema backend.

### P2 — Creation idempotency key chỉ tồn tại trong bộ nhớ tab

`authWorkflow.ts@7ebb9dd:5,98-109` tạo key UUID và giữ trong `pendingDraftKeys` module map. API backend hỗ trợ key và revision migration tạo unique index theo Maker. Nếu người dùng thử lại cùng trang sau lỗi network không rõ, key được tái sử dụng. Sau reload, map mất; một attempt mới có thể gửi key mới và tạo thêm draft nếu request trước đã commit nhưng phản hồi bị mất.

**Tác động:** Resilience tốt trong một phiên component nhưng chưa chứng minh idempotency qua reload/crash. Khi tích hợp, chọn cơ chế giữ key ổn định theo một lần tạo (ví dụ lưu tạm theo form attempt) hoặc cung cấp bước tra cứu/resolve kết quả chưa xác nhận; tránh tự động gửi lần hai với key mới.

### P2 — Bộ lọc tìm trên dữ liệu đã tải, không phải toàn bộ server

`AuthenticatedPlansPage.tsx@7ebb9dd:123-127,220-246` gọi `filterWorkflowPlans()` trên rows đã tải; service gửi `offset/limit` nhưng response plan list không có total. Màn hình đã nói rõ phạm vi này và có nút tải tiếp, nên hiện không tuyên bố sai. Đây là giới hạn contract nếu acceptance cần tìm toàn dataset.

### Follow-up nghiệp vụ — role kết hợp đã được chốt

- **ADMIN + MAKER (chốt 2026-10-10 theo quyết định người dùng):** quyền role được cộng dồn. ADMIN-only vẫn chỉ đọc workflow; ADMIN+MAKER có thao tác Maker trong phạm vi kế hoạch do mình tạo. ADMIN không cấp quyền Checker; assignment và cấm tự duyệt vẫn giữ. Ma trận và test Auth workflow được cập nhật trong nhánh tích hợp; backend authorization vốn kiểm tra role MAKER cùng ownership nên không cần mở rộng quyền.
- **`RECOMMEND_HUMAN_REVIEW`:** UI/backend hiện ghép recommendation này với `REJECTED` khi kiểm tra override (`AuthenticatedWorkflowDetailPage.tsx@7ebb9dd:71-75`; `src/backend/application/auth_workflow.py@e85363e:1271-1278`). Tuy nhiên UI mô tả đây là khuyến nghị “Checker xem xét”. Scope nói Checker là người ra quyết định và AI không tự từ chối. Hãy xác nhận `RECOMMEND_HUMAN_REVIEW` có phải một recommendation cuối có thể được override hay chỉ là định tuyến trước khi giữ mapping hiện tại.

## Hợp đồng và invariant đã rà

- **GET list/detail/audit/attachment:** route GET chỉ đọc; không gọi recovery. Recovery là POST riêng, role Checker, plan được giao và round còn active.
- **Maker:** draft có thể chưa đầy đủ; submit cần title/objective/summary, ngày ISO hợp lệ, budget không âm, attachment và Checker hợp lệ. Submit snapshot/round do backend tạo; form gửi `expected_revision`.
- **Checker:** list được lọc `checker_id` và trạng thái pending ở server; decision endpoint kiểm assigned Checker, Maker khác Checker, trạng thái/round active, rejection reason, stale decision và uniqueness.
- **Read-only / media:** Auth image fetch gửi cookie và tạo object URL có revoke; server xác thực quyền truy cập attachment. Không phát sinh public URL.
- **Version/evidence:** response schema backend có `versions`, `ai_evaluations`, `engine_decisions`, `history`, input/policy/model/hash; frontend types và detail dùng các trường đó. VLM provenance được hiển thị qua attachment/input/output hashes.
- **AI failure/config:** feature diff không đổi backend. Backend hiện route lỗi, timeout, thiếu evaluation hoặc trạng thái bất định sang Human Review; không thấy AI rejection path trong Auth flow.
- **Judge Demo và Verify:** `/demo` vẫn tách route; Auth workflow dùng `/api/workflow`, cookie session. Không gộp service mock của Judge Demo vào Auth. Khi hòa nhập phải giữ Verify Dashboard và các suite mới ở e853; cây 7ebb chỉ chưa có các additions này vì merge-base cũ.

## Giữ gì và thứ tự tích hợp đề xuất

1. **Giữ nguyên baseline e853 trước:** `.github/workflows/verify.yml`, `scripts/run-auth-postgres-e2e.ps1`, `VerifyDashboardPage` tests, Verify mock tests, backend verification changes, evidence/report mới và migration/auth behavior hiện hành. Các file này thuộc diff `merge-base..e853`, không nằm trong diff tính năng đồng đội.
2. **Auth/session/navigation:** lấy cải thiện error/session state, safe return path và tests từ nhánh đồng đội; giữ kiểm tra cookie/role ở backend và contract Admin destination hiện được test là `/workflow/plans`. Role kết hợp đã được chốt theo hướng cộng quyền; backend giữ nguyên kiểm tra MAKER và ownership.
3. **Danh sách/filter:** giữ phân trang server `offset/limit` và filter URL/local của nhánh đồng đội cùng thông báo phạm vi đã tải. Nếu cần kết quả server-wide, đó là API work riêng sau khi chốt requirement.
4. **Maker form:** giữ create/update/upload/submit tuần tự, revision handling, client + server file validation, checker selection và API errors. Sửa `0`, ổn định key creation retry, sau đó chạy form/service tests và backend workflow tests.
5. **Checker/detail/audit:** giữ assigned queue, decision controls, active round handling, POST recovery, version/evidence view và private attachments. Bổ sung hiển thị override reason; chốt nghĩa recommendation trước khi đổi rule.
6. **Hòa giải CSS và regression:** giải quyết `frontend/src/styles.css` bằng cách giữ cả Auth UI và Verify Dashboard styling; không thay `frontend/src/services/api/index.ts` hoặc `types/index.ts` của Judge Demo bằng Auth workflow service/types.

### Verification plan sau khi được phép tích hợp

- Frontend: `cd frontend; npm run test` (bao gồm Auth navigation/forms/list/detail, filter và Verify Dashboard), `npm run build`; `npm run test:e2e` chỉ trong môi trường cô lập với `MOCK_VLM` và database test.
- Backend: `python -m pytest -q` trên database test/in-memory fixtures; nhấn mạnh tests cho zero budget, permission và dual-role decision, active-round recovery, idempotency/replay, resubmit V2/Round 2, audit override, private attachment và GET không side effect.
- PostgreSQL/Auth E2E: chỉ chạy theo script hiện có sau khi kiểm tra cấu hình được trỏ tới DB cô lập. Không chạy migration/seed lên DB sống. Không gọi model thật trong suite audit; dùng `MOCK_VLM`.
- Build/typecheck/lint: build/typecheck có script; repository hiện không có lint script được khai báo.

## Kết quả test và giới hạn

Các kết quả dưới đây **do người dùng cung cấp cho baseline e853**, không phải do audit chạy và không áp dụng tự động cho nhánh `7ebb` hoặc merge tương lai:

- Backend: 305 passed, 84 subtests passed, 1 warning.
- Judge Demo E2E: 5 passed.
- PostgreSQL tạm: migration tới `20261009_08` và unique index PASS.
- Auth E2E: 2 passed, 0 skipped, 0 unexpected, 0 flaky.
- Auth E2E dùng `MOCK_VLM`, không xác nhận inference thật.
- Phần lưu artifacts của script được sửa sau lượt Auth E2E pass; chưa có lượt E2E đầy đủ xác minh phần lưu mới.

Không chạy kiểm tra trong lượt này. Vì vậy khả năng build/test của chính tree `7ebb9dd`, và của tree sau khi hòa giải CSS/API/tests, vẫn chưa được xác nhận. Bằng chứng Local VLM inference thật và artifact-save sau E2E vẫn còn thiếu theo báo cáo baseline.

## Handoff

- **Outcome:** hoàn tất audit source và tạo báo cáo riêng; chưa tích hợp.
- **Files changed:** chỉ thêm `docs/integration/frontend-microservices-ms1-ms5-audit-2026-10-09.md`.
- **Commands/evidence:** fetch hai ref thành công; `rev-parse`, `merge-base`, `status`, `log`, `diff --stat/name-status`, source/docs inspection. Không chạy tests/build/lint.

## Follow-up 2026-10-10 — quyết định role và tích hợp

- Người dùng chốt quyền cộng dồn: ADMIN-only chỉ đọc workflow; ADMIN+MAKER có quyền Maker trên kế hoạch của mình; ADMIN không tự cấp CHECKER. Quy tắc assignment Checker và cấm Maker tự duyệt vẫn áp dụng.
- Cập nhật `docs/role1/v2.1/03-authority-matrix.md` và BR-AUTH trong `docs/scope-phase-1.md` để ghi rõ phạm vi quyền và loại bỏ ngoại lệ có thể bị hiểu là ADMIN sửa mọi kế hoạch.
- Thêm `test_admin_maker_gets_maker_permissions_without_checker_authority` trong `tests/integration/test_auth_workflow.py`: kiểm tra role Maker tạo/sửa/submit được kế hoạch của mình; ADMIN vẫn đọc được danh sách theo quyền hiện hành; không sửa được kế hoạch Maker khác; không được gán làm Checker, vào Review Queue hoặc tự duyệt.
- Thêm test route UI trong `frontend/src/routes/AppRoutes.test.tsx`: ADMIN+MAKER có thể mở form Maker, nhưng không hiện điều hướng Checker.
- Backend authorization không cần nới quyền: API yêu cầu role MAKER cho thao tác Maker, service giới hạn theo maker_id, còn review/decision yêu cầu role CHECKER và kiểm tra assignment/khác Maker.
- Focused test: `.venv-test-20261009\\Scripts\\python.exe -m pytest tests/integration/test_auth_workflow.py::test_admin_maker_gets_maker_permissions_without_checker_authority -q` — 1 passed, 1 Starlette deprecation warning.
- Auth/RBAC regression: `.venv-test-20261009\\Scripts\\python.exe -m pytest tests/integration/test_auth_workflow.py tests/integration/test_rbac_validation.py -q` — 55 passed, 1 Starlette deprecation warning.
- Frontend: `npm run test -- --maxWorkers=2` — 17 files / 138 tests passed; `npm run typecheck` — passed; `npm run build` — passed. UI-focused `AppRoutes.test.tsx` — 14 passed.
- Judge Demo E2E 5 passed và Auth PostgreSQL E2E 2 passed từ lượt tích hợp trước; lượt cập nhật này chỉ đổi tài liệu/test, không đổi runtime backend/frontend. E2E Auth dùng PostgreSQL tạm, SQLite Demo tạm và MOCK_VLM.
- Quét 5 file bằng chứng Auth E2E cho JWT/Bearer token, connection string có mật khẩu, private key và credential assignment phổ biến: không có kết quả khớp. Bằng chứng là dữ liệu synthetic; không chứa credential phát hiện được.
- **Assumptions:** `e85363e` là baseline đích theo yêu cầu; lấy remote-tracking ref vừa fetch của nhánh đồng đội làm trạng thái cần review; không xem tên “microservices” là kiến trúc đã được chứng minh.
- **Known limitations:** chưa thực thi tree teammate; chưa chứng minh inference Local VLM thật; artifact save mới của Auth E2E chưa được verify; còn hai quyết định role/recommendation cần xác nhận.
- **Next safe work package:** sau khi người dùng cho phép tích hợp, xử lý budget zero và audit override trước; giữ nguyên thay đổi e853; sau đó hòa nhập từng nhóm frontend và chạy verification trong môi trường cô lập.

## Follow-up 2026-10-10 — Auth creation intent sau reload

### Hành vi và quyền

- Query `creation_intent` là UUID gắn với một ý định tạo form. Frontend chuyển nó thành header `Idempotency-Key: workflow-create:<UUID>`; đây không phải cookie, bearer token hay thông tin đăng nhập. `creation_pending=1` chỉ giúp UI cảnh báo khi reload sau kết quả mạng không rõ.
- `POST /api/workflow/plans` vẫn yêu cầu Maker session và kiểm tra Checker ở backend. Backend truy vấn key cùng `maker_id`, so sánh hash chuẩn hóa của payload và Checker. Cùng chủ sở hữu/key/body trả lại draft đã tồn tại; body khác trả HTTP 409 với `IDEMPOTENCY_CONFLICT`, không thêm draft hoặc `CREATED` event. Form dùng intent UUID mới khi bắt đầu ý định tạo mới.
- UI hiện hướng dẫn kiểm tra danh sách sau phản hồi không rõ. Nếu cùng intent được gửi với nội dung khác, UI báo máy chủ không tạo thêm draft, khóa thao tác tạo tiếp bằng intent đó và dẫn tới danh sách hoặc form mới.
- Test quyền gửi cùng key dưới Maker khác: backend tạo draft riêng cho Maker đó, không trả draft của người đầu; đọc draft người khác vẫn 404. Gửi cùng key không có session vẫn 401. Các kiểm tra này xác nhận key không cấp quyền và không vượt qua owner check.

### Hồi quy E2E và bằng chứng

- `frontend/e2e/auth-live.spec.ts` có thêm một ca trình duyệt trên API thật: `route.fetch()` gửi POST tới backend PostgreSQL tạm, đợi response 201 chứa plan ID rồi cố ý abort response trước khi trình duyệt nhận. Sau reload URL và intent phải giữ nguyên; Maker kiểm tra danh sách, nhập lại đúng payload, retry và nhận cùng plan ID. Ca này tiếp tục tạo form mới với cùng payload nhưng intent mới, rồi gửi payload khác dưới intent cũ để kiểm tra 409, UI guidance, số draft và `CREATED` event đã lưu.
- Ca E2E gửi cùng idempotency header từ API context không có cookie và yêu cầu 401. Test tích hợp backend kiểm tra thêm key cùng chủ sở hữu, khác body, và phạm vi Maker khác.
- `scripts/run-auth-postgres-e2e.ps1` nay yêu cầu đúng 3 test kỳ vọng, 0 skipped, 0 unexpected và 0 flaky; retries Playwright vẫn bằng 0. Test reporter JSON và process logs được archive qua bộ lọc redaction của script sau lượt chạy thành công.
- Auth E2E trên container PostgreSQL 16 dùng tmpfs: **3 passed, 0 skipped, 0 unexpected, 0 flaky**. Migration xác nhận ở `20261009_08` và unique index `uq_auth_workflow_plans_maker_creation_key` tồn tại. Cấu hình dùng `MOCK_VLM`, SQLite Demo riêng trong temp; script dừng container riêng của lần chạy thành công, không báo lỗi cleanup. Không dùng DB/container ứng dụng có sẵn hoặc model thật.
- JSON Playwright và logs đã lưu tại `docs/integration/evidence/auth-postgres-e2e/dad1ec0cfc874550b95b983eaf3d0d31/`. Bản archive xác nhận `expected=3`, `skipped=0`, `unexpected=0`, `flaky=0`; bản ghi E2E cho thấy response đã commit rồi bị chặn khỏi browser, reload giữ intent, retry trả cùng plan, intent mới tạo plan khác, payload đổi nhận 409, hai draft gốc có một `CREATED` event mỗi bản, payload đổi không tạo draft và request không cookie nhận 401. Quét 5 file archive không thấy raw credential, JWT, chuỗi PostgreSQL có mật khẩu hoặc private key.
- Backend: `.venv-test-20261009\\Scripts\\python.exe -m pytest tests/integration/test_auth_workflow.py tests/integration/test_rbac_validation.py -q` — **56 passed**, 1 Starlette/httpx deprecation warning. Bộ focused test idempotency chạy riêng cũng **1 passed**.
- Frontend: `npm run test -- --maxWorkers=1 --pool=threads --reporter=verbose` — **17 files / 142 tests passed**; `npm run typecheck` — pass; `npm run build` — pass. Playwright discovery thấy đúng 3 ca; Auth E2E spec TypeScript được kiểm tra độc lập — pass. PowerShell parser và `git diff --check` — pass.
- Các kết quả trên là lượt chạy của tree local sau follow-up, không lấy lại kết quả baseline/user-reported trước đó. Không commit, push, merge main hoặc deploy trong lượt này.
