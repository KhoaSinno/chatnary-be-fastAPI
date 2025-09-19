# 🔹 PostgreSQL extension là gì?

Postgres có cơ chế **extension**: plugin cài thêm vào database để mở rộng khả năng.
Ví dụ:

* `uuid-ossp` → tạo UUID.
* `postgis` → xử lý dữ liệu địa lý.
* `pgvector` → xử lý dữ liệu vector.
* `pg_trgm` → xử lý fuzzy search dựa trên **trigram**.

Bạn bật bằng câu lệnh:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Trong skeleton, các lệnh này đã có trong `db/init/00-extensions.sql`.

---

## 🔹 1. pgvector

* Thêm **kiểu dữ liệu mới**: `vector(N)` → mảng số thực chiều dài cố định, ví dụ `vector(1536)`.
* Thêm **toán tử so sánh khoảng cách**:

  * `<->` = Euclidean distance (L2).
  * `<#>` = negative inner product.
  * `<=>` = cosine distance.

Ví dụ:

```sql
-- Tạo bảng có embedding vector
CREATE TABLE chunks (
  id SERIAL PRIMARY KEY,
  content TEXT,
  embedding vector(1536)
);

-- Tìm 3 đoạn gần nhất với một vector query
SELECT id, content
FROM chunks
ORDER BY embedding <=> '[0.12, 0.34, ...]'::vector
LIMIT 3;
```

👉 Ở đây `embedding <=> '[...]'` tính cosine distance. Kết quả càng nhỏ → càng giống.
Trong code của bạn, để biến distance thành **điểm similarity**, người ta làm:

```sql
1.0 - (embedding <=> %s::vector) AS score
```

→ Cosine distance \[0..2] được đổi thành similarity \[0..1].

Ngoài ra, pgvector hỗ trợ **index** kiểu IVF/HNSW để tăng tốc (tìm kiếm ANN thay vì scan toàn bộ).

---

## 🔹 2. pg\_trgm

* Dựa trên **trigram**: chia chuỗi thành các nhóm 3 ký tự liên tiếp để tính độ giống.
* Cung cấp:

  * Hàm `similarity(text, text)` → số \[0..1].
  * Toán tử `%` (match theo ngưỡng similarity).
  * Index GIN/GiST để tăng tốc tìm kiếm fuzzy.

Ví dụ:

```sql
-- Bật extension
CREATE EXTENSION pg_trgm;

-- Tạo index
CREATE INDEX idx_chunks_trgm ON chunks USING GIN (content gin_trgm_ops);

-- Truy vấn fuzzy
SELECT id, content, similarity(content, 'nghien cuu')
FROM chunks
WHERE content ILIKE '%nghien cuu%'
ORDER BY similarity(content, 'nghien cuu') DESC
LIMIT 5;
```

👉 Điều này hữu ích khi người dùng gõ **sai chính tả, gõ tắt, hoặc cần match gần đúng**.

---

## 🔹 Vì sao cần cả hai?

* **pgvector**: tìm theo **ngữ nghĩa** (semantic). VD: “research method” và “phương pháp nghiên cứu” có embedding gần nhau.
* **pg\_trgm**: tìm theo **ký tự gần giống** (lexical). VD: người dùng gõ “nghiêng cứu” vẫn match “nghiên cứu”.

Skeleton kết hợp cả hai trong `hybrid_search`:

1. Lấy ứng viên từ pgvector (semantic).
2. Lấy ứng viên từ pg\_trgm/FTS (keyword/fuzzy).
3. Merge lại, chọn score cao nhất.

---

✅ Tóm lại:

* **pgvector** = cho phép Postgres lưu vector embedding và tính similarity (semantic search).
* **pg\_trgm** = cho phép Postgres tính độ giống text bằng trigram (fuzzy lexical search).
* Cả hai chỉ là **extension** của Postgres, không phải DB riêng, và bạn có thể kết hợp trong cùng một bảng để vừa quản lý metadata, vừa tìm kiếm ngữ nghĩa + từ khóa.
