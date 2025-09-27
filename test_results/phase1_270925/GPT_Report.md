# 1) Q: “DBMS là gì?”

**Kết quả hiện tại (tóm tắt, định dạng lại):**

* **Định nghĩa:** DBMS là phần mềm cho phép người dùng định nghĩa, tạo, duy trì và kiểm soát quyền truy cập vào CSDL [6:46], [6:36].
* **Cách gọi khác:** “Phần mềm quản lý và điều khiển quyền truy cập cơ sở dữ liệu.” [6:31]
* **Ngôn ngữ đi kèm:**

  * DDL – định nghĩa lược đồ (kiểu dữ liệu, cấu trúc, ràng buộc) [6:36]
  * DML – chèn, cập nhật, xóa, truy xuất dữ liệu [6:36]

**Đánh giá:**

* ✅ **Đúng & súc tích**; câu trả lời đã có **trích dẫn nội tuyến** đúng vị trí.
* ✅ **Bao quát tối thiểu cần có** (định nghĩa + DDL/DML).
* ➕ Có thể thêm 1 dòng “mục tiêu/ích lợi” (bảo mật, toàn vẹn, khôi phục) để giàu ý hơn, từ [6:47].

**Gợi ý chỉnh nhỏ (không cần đổi code):**

* Prompt sinh câu trả lời: thêm 1 bullet “nêu 1–2 lợi ích điển hình” để câu ngắn nhưng tròn ý.

---

# 2) Q: “Hệ quản trị CSDL có những **thành phần và chức năng** gì?”

**Kết quả hiện tại (format lại):**

**Chức năng chính:**

* Quản lý/điều khiển quyền truy cập CSDL [6:31].
* Cung cấp DDL (định nghĩa lược đồ) [6:36].
* Cung cấp DML (thao tác dữ liệu) [6:36].

**Thành phần (theo giáo trình):**

* **Query Processor (Bộ xử lý truy vấn):** biên dịch/truy tối ưu truy vấn → lệnh cấp thấp [6:13].
* **Database Manager (DM):** nhận truy vấn từ app, kiểm tra lược đồ, gọi File Manager [6:13]; các thành phần con thể hiện trong Hình 1.7 [6:13], [6:17].
* **File Manager:** thao tác tệp vật lý, phân bổ không gian lưu trữ, quản lý chỉ mục [6:13].

**Đánh giá:**

* ✅ **Đúng và chia mục rõ**, trích dẫn hợp lý.
* ⚠️ **Coverage**: Có nhắc vai trò bảo mật/toàn vẹn/khôi phục rải rác trong tài liệu (ví dụ [6:51]), nhưng phần “chức năng” chưa gom nhóm (security, integrity, concurrency, recovery, catalog).
* ➕ Đề nghị thêm 1 nhóm “**Dịch vụ hệ thống**”: bảo mật, toàn vẹn, đồng thời, khôi phục, catalog (nêu ngắn + 1 cite tổng).

**Gợi ý chỉnh code:**

* Với câu hỏi chứa “**thành phần**/**chức năng**”, trong `answer` prompt thêm:

  * “Nếu câu hỏi có 2 vế (thành phần **và** chức năng), **xuất 2 nhóm đầu mục riêng**.”
* Tăng `RAG_TOP_CONTEXT` từ 8 → **10** cho loại câu “cấu trúc giáo trình” để có thêm bằng chứng (không tăng chi phí nhiều vì vẫn rerank trước).

---

# 3) Q: “**Liệt kê toàn bộ** học phần **chuyên ngành KTPM**”

**Kết quả hiện tại (định dạng lại các mục):**

1. Phân tích & Thiết kế HTTT … [5:55]
2. Khai phá dữ liệu … [5:55]
3. Phát triển ứng dụng IoT … [5:62]
4. Nguyên lý thiết kế & kiến trúc phần mềm … [5:62]
5. Điện toán đám mây … [5:63]
6. Đồ án HTTT … [5:63], [5:1]
7. Hệ CSDL đa phương tiện … [5:62]
8. Thương mại điện tử … [5:62]
9. Phân tích & trực quan hóa dữ liệu … [5:10]
10. Phần mềm mã nguồn mở … [5:10]

**Đánh giá:**

* ✅ **Định dạng danh sách** đã OK, có trích dẫn [doc:chunk].
* ⚠️ **Độ chính xác theo “KTPM”**: bạn đang truy xuất từ **HTTT_CTDH_2022** ([5:…]) – **đây là khung của ngành HTTT**, không chắc trùng **KTPM** (Kỹ thuật phần mềm). Vì vậy, danh sách có thể **lẫn** các học phần **không phải chuyên ngành KTPM**.
* ⚠️ **Nhiễu OCR/khử dấu** (ví dụ “Học phan”) vẫn còn, một vài mục có vẻ lấy từ **khối khác** (đại cương/cơ sở ngành).
* ⚠️ **Thiếu bộ lọc chuyên ngành**: list-mode đang “quét các dòng có pattern mã/tên học phần” chứ **chưa ràng buộc theo vùng/khối “chuyên ngành KTPM”**.

**Gợi ý chỉnh code (nhanh, không đổi DB):**

1. **Bộ lọc theo chuyên ngành/khối bằng tiêu đề gần kề**

   * Trong `extract_items(...)` (list-mode), trước khi duyệt dòng, lấy **cửa sổ heading**: nếu `section_title`/văn bản quanh chunk chứa các từ “**chuyên ngành**”, “**KTPM**”, “**Software Engineering/Kỹ thuật phần mềm**” thì **ưu tiên +1.0**; nếu chứa “đại cương/cơ sở ngành” thì **giảm -0.5**.
   * Chỉ giữ mục có **điểm ≥ 0**.
2. **Từ khóa KTPM**: `{"kỹ thuật phần mềm","KTPM","software engineering"}` – *casefold* + unaccent khi so khớp.
3. **Ngưỡng trích xuất theo “vùng gần heading”**: chỉ parse **N dòng kế tiếp** sau heading “Chuyên ngành …” trong cùng `page_no` hoặc **±1 chunk_index** (giảm lẫn mục).
4. **Nếu tài liệu hiện hành không có KTPM** (mismatch ngành), **trả cảnh báo mềm**: “Tài liệu hiện tại là HTTT, chưa xác định được KTPM. Vui lòng cung cấp PDF KTPM hoặc cho phép tìm theo từ khóa ‘Kỹ thuật phần mềm’ trong thư viện.” → vẫn trả **top-k dự đoán** nhưng gắn tag “(không chắc chuyên ngành)”.

> Với các chỉnh trên, bạn sẽ loại được phần lớn nhiễu và phù hợp hơn với cụm “**chuyên ngành KTPM**”.

---

## Nhìn tổng: chất lượng pipeline sau các patch của bạn

* **DBMS** (định nghĩa): **Tốt** — đúng, gọn, cite chuẩn.
* **DBMS (thành phần/chức năng)**: **Tốt +** — thêm nhóm “dịch vụ hệ thống” là tròn.
* **Liệt kê chuyên ngành**: **Cần tinh chỉnh** list-mode để **lọc đúng chuyên ngành** + xử lý mismatch tài liệu.

---

## Điều chỉnh nhanh (copy/paste) đề xuất ngay bây giờ

1. **Rerank feed lên 16, context đưa vào LLM ~8–10** (bạn đang 5–6 là hơi ít cho câu cấu trúc).
2. **Tăng `HNSW_EF_SEARCH` 64→96** nếu latency vẫn ổn (thường vẫn ổn).
3. **List-mode filter by heading** (sửa `extract_items`):

   * Lấy `heading_score = +1` nếu `section_title`/context có “chuyên ngành|KTPM|software engineering”; `-0.5` nếu “đại cương|cơ sở ngành”.
   * Bỏ các item tổng quát nếu `heading_score < 0`.
4. **Cảnh báo mềm nếu phát hiện mismatch ngành**:

   * Nếu trong top-chunk **không thấy** từ khoá KTPM ở heading/section → thêm dòng đầu: “(Không chắc đây là danh sách KTPM vì tài liệu hiện tại thuộc HTTT)”.

---

## Mẫu output mong muốn sau chỉnh (minh hoạ)

> **Liệt kê toàn bộ học phần chuyên ngành KTPM (tài liệu hiện tại: HTTT — có thể chưa đúng chuyên ngành, cần xác nhận)**
>
> * [KTPM] Phân tích & Thiết kế PM … [5:55]
> * [KTPM] Kiến trúc & Thiết kế PM … [5:62]
> * [KTPM] Điện toán đám mây (ứng dụng phát triển phần mềm) … [5:63]
> * …
>   *Ghi chú:* Nếu bạn có **PDF KTPM** đúng ngành, mình sẽ chạy lại để đảm bảo **độ đầy đủ & chính xác 100%**.
