# Cấu hình Media và Strategy — OrganizationAI
Ngày soạn: 15/10/2026. Bộ cấu hình đã được đối chiếu với service Render đang chạy trên nhánh `main` (commit `b50ef9cec0484fd481b4b833844769b8399c2e0b`) và mã mới nhất `origin/main` (`e2a65258ae05d45f55e5861b98cd99131b2ac110`). Các file `.env.example`, `task_config.py`, `task_providers.py`, `ollama_identity.py`, `backend/api/app.py`, `backend/application/auth_workflow_ai.py`, `backend/application/approval_configuration.py`, `backend/domain/policy.py` và `backend/rules/decision.py` không đổi giữa hai commit này. Nhánh checkout ban đầu là feature branch và khác ở các file backend liên quan; nội dung này được căn theo production `main`.

## Các file
- render-media-strategy.env.example: tên biến được backend hỗ trợ; bật remote theo yêu cầu đã xác nhận, để trống endpoint tunnel và pin digest hiện lấy từ inventory đã kiểm chứng.
- strategy-rubric.json: bảy tiêu chí cố định, trọng số 15/15/15/15/15/15/10, tổng 100.
- media-policy.draft.json: hai quy tắc rà soát nội bộ đề xuất; DISABLED, chưa được phê duyệt. Không phải bộ policy hoàn chỉnh cho production, không đại diện luật quảng cáo.
- Không tự bật auto-approval hoặc thay đổi approval policy, budget và authority.

## Kết quả đối chiếu Render — 15/10/2026
- `AUTH_WORKFLOW_STRATEGY_RUBRIC_JSON` trên Render khớp rubric trong gói: `BA-STRATEGY-7-1.0`, bảy tiêu chí và trọng số cố định tổng 100. PostgreSQL có thể có rubric hiệu lực riêng cho approval round; trạng thái đó chưa được đọc.
- Render environment chưa có `AUTH_WORKFLOW_MEDIA_POLICY_JSON`; policy draft bên dưới còn placeholder scope và giữ `DISABLED`. PostgreSQL lưu các revision hiệu lực gồm `media_policy`, `strategy_rubric`, `approval_policy`, `budget`, `authority` và `checker_assignment`; API GET `/api/workflow/configuration` yêu cầu role `ADMIN`. Request đọc trong phiên này trả `401 UNAUTHENTICATED`, vì vậy trạng thái DB hiện hành chưa được xác nhận.
- `LOCAL_VLM_MODEL=qwen3-vl:4b` hiện có digest `sha256:e8503d318d8df6622abc18a317c0e5eee044821322c87a16a6acddd62984da84` trong Ollama inventory. Hai task model `organizationai-qwen3:4b-ctx8192` cùng khớp digest `sha256:b2ef2f414e31e4e10ef46366751464631a5fa4b5c1bf183b1e3b9076ab2116ef`.
- VLM digest pin cũ trên Render không khớp model ID; đã thay bằng digest inventory và restart service. Chưa chạy inference với hồ sơ/ảnh production.
- Khi không có revision DB hiệu lực, backend khởi tạo từ `unconfigured_approval_configuration`: auto-approval `false`, budgets rỗng, authority `null`; revision DB hiệu lực được chụp vào approval round khi submit. Validator production hiện từ chối `approval_policy.enabled=true` với lỗi `Auto-approval cannot be enabled before PO sign-off.` Không được ghi thẳng DB hoặc lách validator; cần PO sign-off và một đường cấu hình được phê duyệt.

## Dùng với phiên Codex đang cấu hình Render
1. Đính kèm bộ file này cho phiên Codex đó; yêu cầu đối chiếu với loader trên đúng nhánh đang deploy trước khi áp dụng.
2. Điền cùng URL HTTPS của tunnel (kết thúc bằng /v1) vào LOCAL_VLM_BASE_URL, AUTH_WORKFLOW_MEDIA_BASE_URL và AUTH_WORKFLOW_STRATEGY_BASE_URL.
3. Trên máy chạy Ollama, dùng PowerShell để lấy tên và digest thực tế:
   Invoke-RestMethod http://localhost:11434/api/tags | Select-Object -ExpandProperty models | Select-Object name,digest
   Điền digest đầy đủ sha256:... của đúng model vào từng MODEL_VERSION. Không dùng digest lịch sử.
4. Đảm bảo máy đang có qwen3-vl:4b và alias organizationai-qwen3:4b-ctx8192. Theo tài liệu repo, tạo alias bằng:
   ollama pull qwen3:4b
   ollama create organizationai-qwen3:4b-ctx8192 -f deployment/ollama/Modelfile.qwen3-4b-ctx8192
5. Chỉ thêm/cập nhật các biến AI; không thay toàn bộ environment của service. File này không chứa DATABASE_URL, JWT_SECRET hoặc CORS.
6. Giá trị AUTH_WORKFLOW_STRATEGY_RUBRIC_JSON là nội dung JSON thực tế, không phải đường dẫn file. Khi dán trực tiếp vào ô Value trên Render, dùng JSON nguyên văn từ strategy-rubric.json, không thêm dấu nháy đơn bao ngoài.
7. Để AUTH_WORKFLOW_MEDIA_POLICY_JSON trống (xóa policy smoke cũ nếu có) trong khi chờ duyệt. Chỉ sau khi duyệt nội dung, phạm vi và version mới đổi policy sang ACTIVE, điền đúng department/channel rồi dán JSON vào biến này.
8. Nếu endpoint có lớp xác thực, cấu hình API_KEY của từng adapter theo cơ chế backend hỗ trợ; không xóa thông tin xác thực đang có. Template không chứa secret.

## Media policy cần bạn chốt
Hai rule trong bản nháp chỉ là đề xuất để bắt đầu trao đổi:
- Khẳng định tuyệt đối: gắn WARNING để người duyệt kiểm tra nội dung tuyên bố.
- Điều kiện ưu đãi: kiểm tra mâu thuẫn/thiếu dữ kiện trong OCR; không tự bịa điều kiện.
Cần xác định: phòng ban, kênh áp dụng, quy tắc thương hiệu, tuyên bố nào bị cấm, điều kiện ưu đãi bắt buộc và bằng chứng để đánh giá. Không tự đặt danh sách từ cấm.
Schema hiện chỉ nhận ACTIVE/DISABLED, không nhận DRAFT; trạng thái bản nháp được thể hiện bằng DISABLED và tên file.
Các rule này cần thử bằng ảnh thực tế trước khi dùng. Chưa có đánh giá độ chính xác Qwen cho policy mới.
Media nhận bằng chứng trích xuất; không mặc định có ảnh gốc, tài liệu thương hiệu hay chứng cứ pháp lý để đối chiếu.

## Strategy
Rubric giữ nguyên ID/nhãn/trọng số backend đang hỗ trợ; không thêm trường mô tả chấm điểm mà schema không nhận.
Mỗi tiêu chí được chấm trên 100; tổng = tổng(điểm tiêu chí × trọng số / 100).
Điểm chỉ có tính tư vấn, không phải xác suất thành công và không tự quyết định phê duyệt.

## Kiểm tra sau khi cấu hình
- Gọi thử từ backend Render và xác nhận model identity cho từng bước.
- Chạy một hồ sơ có ảnh đọc được, kiểm tra log VLM, Strategy và việc Media chuyển human review khi chưa có policy.
- Khi Media được kích hoạt, kiểm tra ảnh đạt, ảnh có dấu hiệu theo rule và ảnh thiếu/không đọc được; kiểm tra kết quả có evidence_refs hợp lệ.
- Sai digest, lỗi schema, timeout hoặc thiếu cấu hình phải giữ fallback sang Checker; không dùng mock để báo kết nối thành công.
- Tunnel tạm phụ thuộc máy và Ollama đang chạy; đổi tunnel phải cập nhật cả ba BASE_URL.
Chưa chạy inference bằng backend Render; trong lần đối chiếu này chỉ đọc Ollama model inventory, nhận `401` khi đọc approval configuration không có ADMIN session, và restart service sau khi sửa pin.

## Nguồn đối chiếu
- https://github.com/bikhoa142007-hash/OrganizationAI/blob/main/.env.example
- https://github.com/bikhoa142007-hash/OrganizationAI/blob/main/src/backend/domain/policy.py
- https://github.com/bikhoa142007-hash/OrganizationAI/blob/main/src/ai_pipeline/task_evaluation.py
- https://github.com/bikhoa142007-hash/OrganizationAI/blob/main/docs/integration/local-media-strategy-inference.md
