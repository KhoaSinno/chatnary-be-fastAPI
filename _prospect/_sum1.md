# “mỗi loại nguồn” rất nên có **profile xử lý riêng**. 

Cùng một pipeline (PostgreSQL + pgvector + FTS/trigram + Cohere rerank) nhưng ta **tùy biến ở bước ingest + search** để phù hợp cấu trúc tài liệu (slide, giáo trình, văn bản nội bộ, scan…).

# 1) Nguyên tắc chung (áp cho mọi nguồn)

* **Chuẩn hoá tiếng Việt**: thêm cột sinh tự động không dấu để keyword/fuzzy ổn định.

  ```sql
  CREATE EXTENSION IF NOT EXISTS unaccent;
  ALTER TABLE chunks
    ADD COLUMN content_norm TEXT
    GENERATED ALWAYS AS (unaccent(lower(coalesce(content,'')))) STORED;
  CREATE INDEX IF NOT EXISTS idx_chunks_norm_trgm
    ON chunks USING GIN (content_norm gin_trgm_ops);
  ```

  Khi keyword search, query trên `content_norm` với `unaccent(lower(query))`.

* **Chunking mặc định**: `max_chars=900–1100`, `overlap=150–250`.

* **Hybrid mặc định (VI)**: `k_vec=60`, `k_kw=30` (tăng keyword so với 40/20).

* **Rerank**: Cohere `top_n=12–16` → **post-filter** (topic gate + group-by document\_id ≤2) → **MMR** để giảm trùng.

* **Synonym & query expansion (VI)**: bơm một số từ khoá đồng nghĩa/ngành (VD “bất đối xứng” ↔ “khóa công khai/PKC/RSA/ElGamal/DSA”; “giao dịch” ↔ “ACID/commit/rollback”).

---

# 2) Profile theo loại nguồn

## A) Slide môn học (PDF slide, nhiều tiêu đề, câu rời)

**Vấn đề:** tiêu đề và nội dung bị tách trang; câu ngắn, nhiều bullet → semantic dễ “trượt”; keyword match mạnh nhưng lạc ngữ nghĩa.
**Gợi ý:**

* **Chunk theo khối slide** (tìm pattern khoảng trắng lớn/`---`/ngắt trang) thay vì thuần ký tự. Thường `max_chars=700–900`, `overlap=200`.
* **Heuristic nối tiêu đề**: nếu dòng đầu có NGẮN/IN HOA → giữ cùng nội dung bên dưới.
* **Hybrid:** tăng `k_kw` (ví dụ `k_vec=50, k_kw=50`).
* **Post-filter:** bắt buộc có ≥1 “term chủ đề” khi `score<0.35`.
* **Group-by doc\_id**: mỗi document ≤2 chunk.

## B) Giáo trình / tài liệu văn bản (chapter, mục, đoạn)

**Vấn đề:** đoạn dài, logic theo chương → semantic hoạt động tốt.
**Gợi ý:**

* **Chunk theo đoạn** (ngắt ở `\n\n` ưu tiên; nếu không có thì theo ký tự). `max_chars=1000–1200`, `overlap=150`.
* **Hybrid:** `k_vec=60–80, k_kw=20–30`.
* **Rerank:** top\_n=12, thường đủ; MMR nhẹ.
* **Nguồn trích dẫn:** gộp các chunk liên tiếp cùng `document_id` để tạo preview mạch lạc.

## C) Văn bản nội bộ trường/khoa (quy định, quy trình, thông báo)

**Vấn đề:** nhiều định nghĩa/điều khoản, thuật ngữ bắt buộc khớp chữ.
**Gợi ý:**

* **Chunk nhỏ hơn**: `max_chars=600–800`, `overlap=150`.
* **Keyword ưu tiên**: `k_vec=40, k_kw=60` (fuzzy hữu ích khi tên riêng có dấu).
* **Post-filter:** nếu là câu hỏi “định nghĩa/điều khoản”, nâng điểm mẫu chứa exact term; nếu là “quy trình”, ưu tiên chunk có “bước/step/điều”.
* **Rerank:** giữ `top_n=16` để đảm bảo đủ coverage.

## D) File scan / ảnh (OCR)

**Vấn đề:** lỗi chính tả, khoảng trắng lộn xộn.
**Gợi ý:**

* **OCR tốt** (Tesseract/Vision API) + **cleanup**: chuẩn hoá khoảng trắng, bỏ header/footer lặp.
* **Trigram cực quan trọng**: `k_kw` cao (50–70), `unaccent` bắt buộc.
* **Chunk ngắn**: `max_chars=500–700` để khoanh nhiễu.
* **Rerank:** cần thiết để loại nhiễu OCR.

## E) Tài liệu nhiều bảng/định nghĩa thuật ngữ

**Vấn đề:** bảng → embedding kém.
**Gợi ý:**

* Phát hiện bảng → **render bảng thành text có cấu trúc** (“| cột | … |”).
* Với “thuật ngữ – định nghĩa”, cân nhắc **chunk theo cặp (term: definition)**.
* Keyword quan trọng: `k_kw≥k_vec`.

---

# 3) Mẫu cấu hình (pseudo) theo profile

```yaml
profiles:
  slides_vi:
    chunk_size: 800
    overlap: 200
    k_vec: 50
    k_kw: 50
    rerank_top_n: 16
    post_filter:
      low_score_gate: 0.35
      max_per_doc: 2

  textbook_vi:
    chunk_size: 1100
    overlap: 150
    k_vec: 70
    k_kw: 30
    rerank_top_n: 12

  policy_internal_vi:
    chunk_size: 700
    overlap: 150
    k_vec: 40
    k_kw: 60
    rerank_top_n: 16
```

---

# 4) “Decision tree” nhanh khi ingest

* **PDF text chuẩn?** → `textbook_vi`
* **Slide nhiều bullet?** → `slides_vi`
* **Văn bản quy định/nội bộ?** → `policy_internal_vi`
* **Scan/OCR?** → profile giống `policy_internal_vi` nhưng tăng `k_kw`, giảm chunk size.

---

# 5) Vì sao cần “tùy biến theo nguồn”?

* **Hình thức trình bày** ảnh hưởng **chất lượng embedding** và **khả năng keyword match**.
* **Tiếng Việt**: FTS chưa có stemming tốt, **trigram + unaccent** rất đáng giá.
* Rerank chỉ chọn “tốt nhất trong các ứng viên bạn đưa cho nó” — nên bài toán cốt lõi là **đưa đúng ứng viên** từ từng loại nguồn.

---

Nếu bạn muốn, mình có thể:

* Viết nhanh `chunker_slides.py` (nối tiêu đề với nội dung),
* Thêm `content_norm` + truy vấn keyword trên cột này,
* Và drop-in `post_filter + MMR` sau Cohere để bạn dán vào project và test lại ngay với bộ file bạn đã gửi.
