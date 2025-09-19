# DB desc

### Bảng `documents`

* `id SERIAL PRIMARY KEY`
  Khóa chính duy nhất cho mỗi tài liệu.
* `source TEXT`
  Đường dẫn gốc (file path) để biết tài liệu lấy từ đâu (debug/truy vết).
* `title TEXT`
  Tên hiển thị thân thiện khi show “Nguồn” ở UI.
* `url TEXT`
  Nếu tài liệu đến từ link thay vì file local (tùy chọn).
* `created_at TIMESTAMPTZ DEFAULT now()`
  Khi tài liệu được ghi nhận; hỗ trợ audit/sort/lọc theo thời gian.

### Bảng `chunks`

* `id SERIAL PRIMARY KEY`
  Khóa chính cho từng mảnh (chunk) của tài liệu.
* `document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE`
  **Khóa ngoại** trỏ về `documents.id`.

  * “1 → N”: một document có N chunk.
  * `ON DELETE CASCADE`: nếu xóa document thì toàn bộ chunk của nó **xóa kèm**. Tránh rác, đảm bảo toàn vẹn dữ liệu.
* `chunk_index INTEGER NOT NULL`
  Thứ tự chunk trong tài liệu để **ghép lại đúng vị trí** khi cần (ví dụ hiển thị trích đoạn liên tiếp).
* `content TEXT NOT NULL`
  Nội dung text của chunk (sau khi tách, strip).
* `content_tsv tsvector GENERATED ALWAYS AS (...) STORED`
  Cột **sinh tự động** dùng cho **full-text search** của Postgres:

  * `to_tsvector('simple', coalesce(content,''))` chuyển `content` thành dạng token để FTS chạy nhanh.
  * Vì là `GENERATED STORED` nên không cần tự cập nhật bằng code — Postgres tự duy trì.
* `embedding vector(1536)`
  Cột vector từ **pgvector** để lưu **embedding** (ở đây 1536 chiều tương ứng `text-embedding-3-small`).
  Dùng cho **semantic search** (cosine distance).

### Indexes (tăng tốc truy vấn)

* `idx_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)`
  Chỉ mục **HNSW** trên cột vector để **tìm lân cận** theo cosine distance cực nhanh.
  (Không có index sẽ phải quét toàn bảng.)
* `idx_chunks_tsv_gin ON chunks USING GIN (content_tsv)`
  Chỉ mục **GIN** cho **FTS** (`@@`) → truy vấn keyword nhanh, xếp hạng với `ts_rank`.
* `idx_chunks_trgm ON chunks USING GIN (content gin_trgm_ops)`
  Chỉ mục **trigram** để **fuzzy search** (gõ sai/thiếu dấu vẫn match) với `similarity()` hoặc `ILIKE '%...%'`.

---

## Vì sao phải có các trường/quan hệ này?

* **Khóa ngoại `document_id` + CASCADE**:
  đảm bảo tính toàn vẹn; document là “cha”, chunk là “con”. Xóa cha thì xóa con → không tồn tại chunk mồ côi.
* **`chunk_index`**:
  giữ **thứ tự** các mảnh để khi cần ghép/ngữ cảnh liền mạch (ví dụ xem preview nhiều chunk).
* **`content_tsv` (GENERATED)**:
  tách riêng “dạng tsvector” để Postgres **index hóa** text và FTS cực nhanh, tránh tính lại mỗi lần query.
* **`embedding vector(1536)`**:
  cần cho **semantic search** với toán tử `<=>` (cosine distance). Không có cột vector thì không tìm theo nghĩa được.
* **Ba index** tương ứng 3 con đường tìm kiếm:

  1. **Semantic** (HNSW + cosine),
  2. **Keyword** (FTS GIN),
  3. **Fuzzy** (trigram GIN).
     Hybrid search của bạn kết hợp các đường này để tăng độ chính xác.

---

## Ví dụ truy vấn hay dùng

* **Semantic top-k**:

  ```sql
  SELECT id, document_id, chunk_index, content
  FROM chunks
  ORDER BY embedding <=> '[0.12, -0.05, ...]'::vector
  LIMIT 10;
  ```

* **Keyword (FTS) + ranking**:

  ```sql
  SELECT id, document_id, chunk_index, content,
         ts_rank(content_tsv, plainto_tsquery('simple', 'phuong phap nghien cuu')) AS score
  FROM chunks
  WHERE content_tsv @@ plainto_tsquery('simple', 'phuong phap nghien cuu')
  ORDER BY score DESC
  LIMIT 10;
  ```

* **Fuzzy/trigram**:

  ```sql
  SELECT id, content, similarity(content, 'nghien cuu') AS sim
  FROM chunks
  WHERE content ILIKE '%nghien cuu%'
  ORDER BY sim DESC
  LIMIT 10;
  ```

Bạn muốn mình xuất luôn file `.sql` tạo schema + indexes này thành một file để bạn tải về dùng riêng không?
