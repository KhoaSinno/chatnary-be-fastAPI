# Vì sao dự án dùng SQL thuần

* **Kiểm soát chính xác**: pgvector có toán tử riêng (`<->`, `<=>`, `#<->`) + index HNSW/IVF. Viết SQL thẳng tay giúp bạn tối ưu truy vấn, hint index, tune `LIMIT`, `ORDER BY`, `WHERE` lọc metadata rất linh hoạt.
* **Đơn giản, nhẹ**: demo/microservice không cần ORM phức tạp. SQL thuần + DAO/repository đủ nhanh và dễ debug.
* **Tích hợp metadata**: bạn trộn **vector search + điều kiện** (user\_id, lang, doc\_version, created\_at, …) trong **một** câu SQL — điểm mạnh của Postgres.

> Dùng “SQL thuần” **không đồng nghĩa kém an toàn**. Bảo mật nằm ở **cách bạn dùng** (param hóa, quyền DB, RLS, API gateway…), chứ không ở việc có ORM hay không.

---

## Làm sao để an toàn (kể cả khi dùng SQL thuần)

### 1) Param hóa 100% (tránh SQL injection)

Tuyệt đối **không** format string. Dùng placeholder và binding:

```python
# psycopg (v3)
sql = """
SELECT id, content
FROM doc_chunks
WHERE doc_version_id = %s
ORDER BY embedding <=> %s
LIMIT %s
"""
with get_conn() as conn, conn.cursor() as cur:
    cur.execute(sql, (doc_version_id, query_vector, k))
    rows = cur.fetchall()
```

Hoặc dùng SQLAlchemy Core (nếu bạn muốn layer cao hơn) vẫn param hóa:

```python
from sqlalchemy import text
stmt = text("""
  SELECT id, content
  FROM doc_chunks
  WHERE doc_version_id = :ver
  ORDER BY embedding <=> :vec
  LIMIT :k
""")
db.execute(stmt, {"ver": ver_id, "vec": query_vec, "k": k})
```

### 2) **Row-Level Security (RLS)**: cách ly dữ liệu theo user

Bật RLS và viết policy để mỗi user chỉ đọc được tài liệu của họ:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE doc_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY doc_owner_only ON documents
  FOR ALL USING (user_id::text = current_setting('app.user_id', true));

CREATE POLICY chunk_owner_only ON doc_chunks
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM documents d
      WHERE d.id = doc_chunks.document_id
        AND d.user_id::text = current_setting('app.user_id', true)
    )
);
```

Trong mỗi request, sau khi xác thực, set **session variable** để Postgres biết bạn là ai:

```python
with get_conn() as conn, conn.cursor() as cur:
    cur.execute("SET LOCAL app.user_id = %s", (str(user_id),))
    # Mọi câu SELECT/INSERT sau đó tự động áp RLS
```

> Ưu điểm: **dù** code bạn có lỗi filter ở tầng app, RLS vẫn chặn ở DB.

### 3) Quyền tối thiểu (least privilege)

* Tạo user DB riêng cho API (ví dụ `rag_api`) chỉ có quyền `SELECT/INSERT` trên các bảng cần thiết, **không** `SUPERUSER`.
* Tách quyền admin/migration (dùng user khác khi chạy Alembic/migration).
* Chỉ `GRANT` cụ thể cột/bảng cần dùng; ẩn cột nhạy cảm sau **VIEW**.

### 4) Đóng gói truy vấn nhạy cảm vào **VIEW/Function**

Định nghĩa sẵn một function tìm kiếm đã “cứng” điều kiện:

```sql
CREATE OR REPLACE FUNCTION search_chunks(ver UUID, qvec vector, k INT)
RETURNS TABLE(chunk_id UUID, content TEXT) AS $$
  SELECT id, content
  FROM doc_chunks
  WHERE doc_version_id = ver
  ORDER BY embedding <=> qvec
  LIMIT k
$$ LANGUAGE sql STABLE;
```

App chỉ gọi `SELECT * FROM search_chunks(:ver, :vec, :k);` → less room for mistakes.

### 5) Transport & secrets

* **TLS** giữa API ↔ Postgres (nếu qua mạng).
* Secrets qua **.env** (không commit), có thể dùng Docker secrets/HashiCorp Vault.
* Rotate mật khẩu định kỳ. Log access (pg\_audit).

### 6) Tầng API làm cổng duy nhất

* Không expose DB ra Internet.
* Mọi thao tác đi qua **FastAPI** (JWT/OAuth2), rate-limit, audit log.
* Cấm nhận “raw SQL” từ client 😅.

### 7) Pooling & timeouts

* Dùng pool (psycopg `ConnectionPool`/SQLAlchemy pool), set `statement_timeout`, `idle_in_transaction_session_timeout` để tránh treo.
* Pgbouncer nếu cần.

---

## Khi nào nên cân nhắc ORM?

* Bạn muốn **unit of work**, mapping object, lazy loading, migration đồng bộ (Alembic), testability cao.
* Đội dev quen ORM, nhiều entity/quan hệ phức tạp.
* Bạn vẫn có thể dùng **ORM + SQL thuần (hybrid)** cho phần pgvector đặc thù.

Ví dụ SQLAlchemy + pgvector (dùng func):

```python
from sqlalchemy import select, func
stmt = (
  select(Chunk.id, Chunk.content)
  .where(Chunk.doc_version_id == ver_id)
  .order_by(func.cosine_distance(Chunk.embedding, query_vec))
  .limit(k)
)
db.execute(stmt)
```

---

## Kết luận

* Dự án dùng **Postgres + pgvector + SQL thuần** là có chủ đích: **đơn giản, linh hoạt, tối ưu truy vấn vector + filter metadata** trong một nơi.
* **An toàn** hay không nằm ở **thực hành**: param hóa, RLS, least-privilege, function/view, TLS, secrets, API gateway.
* Khi lớn hơn, bạn có thể chuyển dần sang **ORM** (cho domain khác) hoặc tách ra **vector DB chuyên dụng** nếu scale cực lớn; phần bảo mật cốt lõi bên trên **vẫn giữ nguyên**.

Nếu bạn muốn, mình viết luôn:

1. file `security.sql` bật RLS + policy,
2. hàm `search_chunks` như trên,
3. và một `repository.py` (FastAPI) mẫu có `SET LOCAL app.user_id` + truy vấn param-hóa.
