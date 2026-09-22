# UI FLOW — Luồng hoạt động giao diện (Frontend Developer)

> Phạm vi: mô tả toàn bộ màn hình, luồng thao tác, trạng thái và lỗi của UI để thiết kế và dựng frontend.
> Nguồn: mục 3 (Frontend Developer), mục 4, mục 5 và mục 6 trong tài liệu nhiệm vụ tổng quát.
> Đề xuất đặt file tại `src/frontend/UI_FLOW.md` (thuộc quyền sở hữu của Frontend Developer).
> Tên trạng thái và tên trường API lấy theo hợp đồng API của Role 2; file này chỉ mô tả cách UI thể hiện.

---

## 1. Nguyên tắc bất biến

| # | Nguyên tắc | Cách kiểm |
|---|---|---|
| 1 | Judge Demo Mode: không đăng nhập, không cài đặt | Mở URL trong cửa sổ ẩn danh, thao tác được ngay |
| 2 | Frontend không tự quyết định kết quả nghiệp vụ | Trong mã frontend không có logic duyệt/từ chối hay so ngưỡng |
| 3 | Form không gửi `case_id` và không chứa đáp án | Tab Network (F12): body request không có `case_id` |
| 4 | Không hiển thị `PASS` cố định | Đổi tạm expected trong bản thử, dòng đó phải hiện FAIL |
| 5 | Input nghi vấn không nhận kết luận khẳng định | Ca chờ con người không hiện nhãn duyệt/từ chối cuối cùng |
| 6 | Không chỉ hiển thị một điểm số đơn lẻ | Màn kết quả có đủ điểm, confidence, rule, bằng chứng, lý do |
| 7 | Audit chỉ đọc | Không có nút sửa hoặc xóa trong audit |
| 8 | Ghi rõ dữ liệu và vai trò mô phỏng | Có nhãn trên UI |

---

## 2. Bản đồ màn hình

```text
                        ┌───────────────────────┐
                        │ 1. LANDING            │
                        └─┬───────┬───────┬─────┘
       [Thử hồ sơ mới]    │       │[Verify]│  [Policy]   [Audit history]
                          ▼       ▼        ▼         ▼
                   2. FORM   7. VERIFY   8. POLICY   6. AUDIT
                      │      DASHBOARD    (chỉ đọc)   TIMELINE
                      ▼
               3. ĐANG XỬ LÝ ──[Stop]──► 3b. ĐÃ DỪNG
                      │
                      ▼
               4. KẾT QUẢ ──(cần con người)──► 5. HUMAN REVIEW QUEUE
                      │                                │
                      └────────► 6. AUDIT TIMELINE ◄───┘
```

| Mã | Màn hình | Vai trò |
|---|---|---|
| 1 | Landing | Giới thiệu, điểm vào duy nhất |
| 2 | Form gửi kế hoạch | Nhập hồ sơ mới |
| 3 / 3b | Đang xử lý / Đã dừng | Theo dõi tiến độ, dừng |
| 4 | Kết quả | Hiển thị quyết định và căn cứ |
| 5 | Human Review Queue | Con người xử lý ca chuyển tiếp |
| 6 | Audit Timeline | Tra lịch sử hành động |
| 7 | Verify Dashboard | Chạy 5 case qua backend thật |
| 8 | Policy | Xem quy định (chỉ đọc) |

---

## 3. Pipeline hoạt động

### 3.1. Luồng A: thử hồ sơ mới

```text
Landing ──[Thử hồ sơ mới]──► Form
Form ──(hợp lệ) [Gửi]──► Đang xử lý
Đang xử lý ──► kết quả từ backend:
   ├─ Tự quyết định   ──► Kết quả (Nguồn: system) ──► [Xem audit]
   ├─ Cần con người   ──► Kết quả (Chờ xử lý) ──► Human Review ──► Kết quả (Nguồn: human)
   ├─ Bị dừng (Stop)  ──► Đã dừng ──► [Xem audit]
   └─ Lỗi/Không hỗ trợ ──► Kết quả (trạng thái lỗi an toàn) ──► [Thử lại] / [Xem audit]
```

### 3.2. Luồng B: Verify

```text
Landing ──[Verify]──► Verify Dashboard
Dashboard ──[Run all 5 cases]──► chạy lần lượt từng case qua backend thật
   ──► mỗi dòng hiện Actual + Result + Time
   ──► tổng hợp "x/5 PASS"
   ──► bấm một dòng ──► chi tiết case ──► [Xem audit]
```

### 3.3. Luồng C: người có thẩm quyền xử lý

```text
Human Review Queue ──► chọn hồ sơ ──► xem chi tiết
   ──► nhập lý do (bắt buộc)
   ──► Approve / Reject / Request Changes
   ──► xác nhận ──► backend ghi nhận ──► về Queue (trạng thái cập nhật)
```

### 3.4. Luồng D: tra audit và can thiệp

```text
Kết quả (hoặc Đang xử lý) ──► [Xem audit] ──► Audit Timeline
   ──► chọn sự kiện xem chi tiết
   ──► (từ Kết quả) Stop / Override / Undo ──► backend xác nhận ──► timeline có sự kiện mới
```

---

## 4. Đặc tả từng màn hình

### Màn 1: Landing

**Mục tiêu:** giám khảo hiểu sản phẩm và biết thao tác đầu tiên trong dưới 1 phút.

| Thành phần | Nội dung / hành vi |
|---|---|
| Mô tả sản phẩm | 1 đến 2 câu |
| Câu hướng dẫn | "Chọn “Verify” để chạy năm trường hợp kiểm thử hoặc tải lên kế hoạch mới để kiểm tra khả năng xử lý tự động và chuyển tiếp." |
| Nút `Thử hồ sơ mới` | Đi tới Màn 2 |
| Nút `Verify` | Đi tới Màn 7 |
| Liên kết Policy | Đi tới Màn 8 |
| Liên kết Audit history | Đi tới Màn 6 |
| Nhãn Judge Demo Mode | Cho biết không cần đăng nhập, dữ liệu là mô phỏng |
| Mục giới hạn (đề xuất) | Vài dòng ngắn nêu giới hạn của sản phẩm, phục vụ bước kiểm tra giới hạn ở phút 7:30 |

### Màn 2: Form gửi kế hoạch

**Mục tiêu:** nhập hồ sơ mới nhanh, phát hiện lỗi đầu vào sớm.

| Trường | Ghi chú |
|---|---|
| Tên chiến dịch | Bắt buộc |
| Mục tiêu | Bắt buộc |
| Đối tượng | Bắt buộc |
| Kênh truyền thông | Bắt buộc |
| Thời gian | Định dạng theo hợp đồng API |
| Ngân sách | Số |
| KPI | Bắt buộc |
| Nội dung chiến lược | Văn bản dài |
| Hình ảnh hoặc tệp đính kèm | Có preview và tiến trình upload |
| Người hoặc cấp đề xuất | Bắt buộc |

Hành vi:

- Validation báo ngay tại từng trường; nút **Gửi** tắt khi chưa hợp lệ.
- Upload có thanh tiến trình, preview ảnh, nút thay/xóa; upload lỗi thì hiện nút thử lại.
- Lỗi validation từ backend gắn vào đúng trường.
- Khi gửi: **không truyền `case_id`**, thứ tự field không ảnh hưởng kết quả.
- Nút Gửi → Màn 3.

### Màn 3: Đang xử lý (3b: Đã dừng)

| Thành phần | Nội dung / hành vi |
|---|---|
| Mã hồ sơ | Hiện ngay khi có |
| Tiến độ | Chỉ hiện các bước mà backend trả về, không tự bịa tiến độ |
| Nút Stop | Có hộp xác nhận; sau khi backend xác nhận mới chuyển sang 3b |
| Tự chuyển | Xong thì sang Màn 4 |
| Timeout / sai schema | Thông báo lỗi, nút Thử lại, liên kết Xem audit |

Màn 3b "Đã dừng": nhãn "Đã dừng", thời điểm dừng, liên kết Xem audit.

### Màn 4: Kết quả

**Mục tiêu:** người xem hiểu quyết định, căn cứ và độ tin cậy mà không cần đọc mã.

| Khối | Nội dung |
|---|---|
| Đầu trang | Kết quả cuối cùng; **nguồn quyết định** (system hoặc human) |
| Điểm | Điểm khả thi và confidence |
| Media | Kết quả kiểm tra ảnh |
| Ngân sách | Ngân sách và hạn mức áp dụng |
| Rule | Danh sách applied rule IDs; bấm vào mở Màn 8 tại đúng rule |
| Bằng chứng | Evidence trích xuất |
| Lý do | Ngôn ngữ dễ hiểu |
| Phiên bản | Policy/model version (khối thu gọn) |
| Hành động | Xem audit, Stop/Override/Undo (nếu trạng thái cho phép), Gửi hồ sơ khác |

Bốn biến thể:

| Biến thể | Hiển thị | Không được hiển thị |
|---|---|---|
| Tự quyết định | Kết quả đầy đủ, nguồn = system | — |
| Chờ con người | Lý do automation dừng, câu hỏi chuyển tiếp, người/cấp có thẩm quyền, liên kết tới Màn 5 | Kết luận duyệt/từ chối khẳng định |
| Đã có quyết định của người | Kết quả, nguồn = human, lý do người xử lý | — |
| Lỗi / không hỗ trợ | Thông báo an toàn, lý do | Kết luận nghiệp vụ |

### Màn 5: Human Review Queue

**Danh sách:**

| Cột | Ghi chú |
|---|---|
| Campaign | Tên chiến dịch |
| Escalation category | Nhóm chuyển tiếp |
| Lý do automation dừng | Ngắn gọn |
| Mức ưu tiên | Theo backend |
| Người/cấp có thẩm quyền | Người nhận |
| Thời gian tạo | Timestamp thật |
| Trạng thái | Theo backend |

**Chi tiết một hồ sơ:**

- Input gốc và hình ảnh
- VLM evidence
- Applied rules
- Câu hỏi chuyển tiếp
- 3 nút: `Approve`, `Reject`, `Request Changes`
- Ô lý do **bắt buộc**

Hành vi:

- Nút quyết định tắt cho đến khi có lý do.
- Sau khi backend xác nhận, quay về Queue và trạng thái cập nhật từ backend.
- Hồ sơ đã có người xử lý trước: hiện banner "đã được xử lý", yêu cầu tải lại, không ghi đè.

### Màn 6: Audit Timeline

| Trường mỗi sự kiện | Ghi chú |
|---|---|
| Actor hoặc agent | Ai thực hiện |
| Hành động và thời gian | Timestamp thật |
| Input/version | Phiên bản dữ liệu |
| Policy/model version | Khi có |
| Lý do quyết định | Văn bản |
| Giá trị trước và sau override | Khi là override |
| Stop / Undo | Hiển thị thành loại sự kiện riêng |

Hành vi: lọc theo hồ sơ hoặc lần chạy; chọn sự kiện để mở chi tiết; chỉ đọc, không có nút sửa hay xóa.

### Màn 7: Verify Dashboard

```text
[Chưa chạy] ──[Run all 5 cases]──► [Đang chạy: từng dòng có trạng thái]
                                ──► [Xong: tổng hợp "x/5 PASS"]
```

| Case | Expected | Actual | Category | Question | Time | Result |
|---|---|---|---|---|---|---|

Yêu cầu:

- Một nút `Run all 5 cases` chạy toàn bộ case qua **backend thật**.
- Timestamp thật và duration.
- `PASS/FAIL` từng dòng, tổng hợp số case đạt.
- Mở được chi tiết từng case (input, actual, expected, rule, liên kết audit).
- Case timeout hoặc lỗi: dòng hiện error kèm lý do, các dòng còn lại vẫn chạy.
- **Không hard-code** kết quả PASS.

### Màn 8: Policy (chỉ đọc)

- Hiển thị bộ quy định do BA sở hữu; Frontend Developer chỉ hiển thị.
- Mỗi rule có neo theo rule ID để Màn 4 nhảy tới đúng chỗ.

---

## 5. Bảng trạng thái hồ sơ và nút cho phép

> Tên trạng thái do hợp đồng API của Role 2 quyết định; cột 1 chỉ là tên mô tả.

| Trạng thái | UI hiển thị | Nút cho phép |
|---|---|---|
| Đang xử lý | Spinner, mã hồ sơ | Stop |
| Đã quyết định (system) | Kết quả đầy đủ | Xem audit, Override |
| Chờ con người | Câu hỏi, người nhận | Xem Review Queue, Xem audit |
| Đã quyết định (human) | Kết quả, nguồn = human | Xem audit, Undo |
| Đã dừng | Nhãn "Đã dừng" | Xem audit |
| Lỗi | Lý do, không kết luận | Thử lại, Xem audit |

---

## 6. Tình huống lỗi mà UI phải xử lý

| Tình huống | UI hiển thị |
|---|---|
| Ảnh không đọc được | Báo ở Màn 2 hoặc Màn 4, cho tải ảnh khác |
| Policy không hỗ trợ | Kết quả "chưa hỗ trợ", không đoán |
| Timeout hoặc invalid schema | Trạng thái lỗi, nút Thử lại |
| Evidence mâu thuẫn | Hiện cả hai bằng chứng, không khẳng định |
| Override thiếu lý do | Chặn ngay ở ô lý do |
| Hai người cùng quyết định một hồ sơ | Banner "đã được xử lý", yêu cầu tải lại |
| Mất mạng / API không phản hồi | Thông báo lỗi kết nối, không trang trắng |
| Upload lỗi | Nút thử lại tại đúng tệp |

---

## 7. Đối chiếu hành trình 8 phút

| Thời gian | Màn hình | Thiết kế phải đảm bảo |
|---|---|---|
| 0:00 - 1:00 | Màn 1 | Hiểu sản phẩm và thao tác đầu trong một màn |
| 1:00 - 3:00 | Màn 7 | Một nút chạy hết, kết quả hiện dần |
| 3:00 - 5:00 | Màn 2, 3, 4 | Nhập nhanh hai hồ sơ, form không quá dài |
| 5:00 - 6:30 | Màn 7 (và 4) | Nhìn ra ngay 3 tự xử lý và 2 chuyển tiếp |
| 6:30 - 7:30 | Màn 6 (và 3 hoặc 4) | Từ kết quả sang audit và stop/override chỉ 1 thao tác |
| 7:30 - 8:00 | Màn 1, 4 | Có chỗ xem giới hạn |

---

## 8. Yêu cầu chống hard-code liên quan đến UI

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Đổi tên campaign | Kết quả không đổi vì tên |
| Thay ngân sách | Kết quả thay đổi đúng theo hạn mức |
| Thay nội dung và hình ảnh | Kết quả bám theo nội dung mới |
| Không truyền `case_id` | Vẫn xử lý được |
| Đổi thứ tự field | Kết quả không đổi |
| Thêm field không liên quan | Bị bỏ qua, không lỗi |

Nếu kết quả phụ thuộc ID hoặc tên case: đánh dấu lỗi **Critical**.

---

## 9. Checklist nghiệm thu UI

- [ ] Mở Live URL trong cửa sổ ẩn danh, không cần đăng nhập
- [ ] Landing có: mô tả, câu hướng dẫn, nút `Thử hồ sơ mới`, nút `Verify`, liên kết Policy và Audit history
- [ ] Form có đủ 10 trường, validation, upload progress, preview
- [ ] Request gửi đi không chứa `case_id`
- [ ] Màn kết quả có đủ: kết quả cuối, điểm và confidence, media, ngân sách/hạn mức, rule IDs, evidence, lý do, nguồn quyết định
- [ ] Ca chờ con người không hiện kết luận khẳng định
- [ ] Review Queue có đủ cột và 3 nút; nút tắt khi chưa có lý do
- [ ] Audit hiển thị đủ trường, có stop/undo, không có nút sửa/xóa
- [ ] Verify: một nút chạy 5 case qua backend thật, có timestamp, duration, PASS/FAIL, tổng hợp, chi tiết từng case
- [ ] Đổi tạm expected thì dòng Verify tương ứng hiện FAIL
- [ ] Mọi trạng thái lỗi ở mục 6 đều có thông báo, không có trang trắng
- [ ] Hoàn thành hành trình chính trong 8 phút

---

## 10. Điểm cần xác nhận trước khi thiết kế

| # | Điểm chưa rõ | Đề xuất tạm |
|---|---|---|
| 1 | Bản tài liệu nào là chuẩn (kế hoạch chiến dịch có ngân sách/ảnh, hay bài truyền thông văn bản ở bản trước) | Bám bản kế hoạch chiến dịch |
| 2 | Vị trí nút Stop, Override, Undo | Stop ở Màn 3; Override và Undo ở Màn 4 |
| 3 | Người xử lý ở Review Queue khi không có đăng nhập | Bộ chọn vai trò mô phỏng, có nhãn |
| 4 | Audit history ở Màn 1 là toàn bộ hay theo phiên demo | Theo phiên demo hiện tại |
| 5 | Giới hạn upload (loại tệp, dung lượng) | Lấy theo hợp đồng API của Role 2 |
| 6 | Quy tắc hiển thị score 70 (bằng và lớn hơn) | UI chỉ hiển thị giá trị backend trả về, BA xác nhận quy tắc |
