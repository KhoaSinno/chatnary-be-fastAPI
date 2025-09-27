# Alembic Migrations Guide (FastAPI + PostgreSQL/pgvector)

> Mục tiêu: giúp bạn đưa **quản lý phiên bản schema DB** (versioned migrations) vào dự án hiện tại (đang dùng `psycopg`/raw SQL). Bạn **không cần** đổi runtime sang ORM – chỉ dùng Alembic để quản lý vòng đời schema.

---

## Alembic là gì? Giải quyết vấn đề gì?

* **Alembic** là công cụ **quản lý migration** cho PostgreSQL (dựa trên SQLAlchemy).
* Cho phép bạn mô tả **mỗi thay đổi schema** (tạo bảng/cột/index/extension…) thành **một revision có mã số** (file Python).
* Hỗ trợ:

  * **Lên phiên bản** (`upgrade`) và **lùi phiên bản** (`downgrade`) an toàn.
  * **Đồng bộ Dev–Test–Prod**: mọi môi trường lên cùng revision → tránh “schema drift”.
  * **Tự động hoá CI/CD**: trước khi start app, chạy `alembic upgrade head`.
  * **Audit/Review**: migration là code, commit Git, review được.

**Nếu không có Alembic**, bạn sẽ:

* Khó biết DB đang ở **phiên bản** nào, ai đổi gì, khi nào.
* **Rollback** khó khăn khi deploy lỗi.
* Dễ lệch schema giữa các môi trường (máy em chạy, máy anh không).
* Migration bằng tay (raw SQL) → dễ quên bước, khó tự động hoá.

> Câu trả lời nhanh khi bị hỏi: *“Giai đoạn MVP em dùng raw SQL cho nhanh. Khi hệ thống ổn định, em dùng Alembic để **version hoá schema**, hỗ trợ **rollback** và **đồng bộ môi trường** – đúng chuẩn dự án thực tế.”*

---

## Yêu cầu & Chuẩn bị

* Python 3.10+ (khớp với dự án).
* PostgreSQL đã cài extension `pgvector`, `pg_trgm` (nếu dùng).
* Dự án dạng:

  ```
  /api
    ├─ app/...
    ├─ requirements.txt
    ├─ alembic.ini            (sẽ tạo)
    └─ migrations/            (sẽ tạo)
  ```

* Biến môi trường DB:

  ```
  DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
  ```

  > Lưu ý: Alembic dùng URL **SQLAlchemy** (`postgresql+psycopg://...`), **không** phải DSN psycopg thuần.

---

## Cài đặt & Khởi tạo

1. **Cài package**

```bash
cd api
pip install alembic SQLAlchemy psycopg[binary] python-dotenv
# nhớ thêm vào requirements.txt:
# alembic
# SQLAlchemy
# psycopg[binary]
# python-dotenv
```

2. **Khởi tạo Alembic**

```bash
alembic init migrations
```

Thao tác này tạo:

* `alembic.ini`: cấu hình chung.
* `migrations/`: thư mục chứa script migration + `env.py`.

---

## Cấu hình `alembic.ini` & `env.py`

### `alembic.ini` (giữ trống URL – sẽ đọc từ env)

* Tìm dòng `sqlalchemy.url =` và **để trống hoặc comment**.
* Đặt `script_location = migrations`.

### `migrations/env.py` (đọc `DATABASE_URL` từ `.env`)

Thay nội dung chính (rút gọn, **không dùng ORM**; `target_metadata = None`):

```python
from __future__ import annotations
import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import create_engine, pool
from dotenv import load_dotenv

# Alembic Config
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Đọc env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# Không dùng ORM metadata
target_metadata = None

def run_migrations_offline():
    url = DATABASE_URL
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Cho phép DDL không transactional (để CREATE INDEX CONCURRENTLY nếu cần):
        transactional_ddl=False,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Cho phép DDL outside transaction nếu cần CONCURRENTLY:
            transactional_ddl=False,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

> Vì không dùng ORM, Alembic sẽ **không autogenerate**. Bạn viết migration thủ công bằng `op.execute()`/`op.create_table()`.

---

## Tạo **migration đầu tiên** (khởi tạo schema pgvector/FTS)

```bash
alembic revision -m "init schema: docs/chunks + vector + fts"
```

Sửa file vừa tạo trong `migrations/versions/<REV_ID>_init_...py`:

```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20250926_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Extensions (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # documents
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("ingest_version", sa.Text, server_default="v1", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )

    # chunks
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("document_id", sa.BigInteger, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_tsv", postgresql.TSVECTOR(), nullable=True),
        sa.Column("hash", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_chunks_doc_idx", "chunks", ["document_id", "chunk_index"], unique=True)

    # embeddings tách bảng → hỗ trợ đa model/dim
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("chunk_id", sa.BigInteger, sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("dim", sa.Integer, nullable=False),
        sa.Column("vector", postgresql.VECTOR(dim=1536), nullable=False),  # dim tùy model
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_chunk_embeddings_chunk_model", "chunk_embeddings", ["chunk_id", "model"], unique=True)

    # Index FTS + trigram
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_chunks_tsv_gin
      ON chunks USING GIN (content_tsv)
    """)
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_chunks_trgm
      ON chunks USING GIN (content gin_trgm_ops)
    """)

    # HNSW cho vector (Postgres pgvector >= 0.5)
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw
      ON chunk_embeddings USING hnsw (vector vector_cosine_ops)
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_chunk_embeddings_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_chunks_trgm")
    op.execute("DROP INDEX IF EXISTS idx_chunks_tsv_gin")
    op.drop_table("chunk_embeddings")
    op.drop_index("idx_chunks_doc_idx", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
    # KHÔNG drop extensions (tuỳ chọn):
    # op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    # op.execute("DROP EXTENSION IF EXISTS vector")
```

> Gợi ý: Nếu bạn cần **CREATE INDEX CONCURRENTLY**, Postgres không cho chạy trong transaction. Ở `env.py` đã set `transactional_ddl=False`, nên có thể dùng:
>
> ```python
> op.execute("COMMIT")  # đảm bảo ngoài transaction
> op.execute("CREATE INDEX CONCURRENTLY ...")
> ```

---

## Áp dụng migration

```bash
# Nâng lên revision mới nhất
alembic upgrade head

# Lùi 1 bước (rollback)
alembic downgrade -1
```

---

## Thao tác hằng ngày (Cheat-Sheet)

* Tạo migration mới (trống, tự viết tay):

  ```bash
  alembic revision -m "add column X to chunks"
  ```

* Tạo migration từ revision cũ (branch):

  ```bash
  alembic revision -m "branch for exp index" --head <rev_id>
  ```

* Xem lịch sử:

  ```bash
  alembic history --verbose
  ```

* Xem DB đang ở revision nào:

  ```bash
  alembic current
  ```

* Gắn (stamp) DB về mã revision mà **không chạy** upgrade/downgrade (dùng khi đồng bộ thủ công):

  ```bash
  alembic stamp head
  ```

* Merge 2 nhánh migration (khi có nhiều HEAD):

  ```bash
  alembic heads
  alembic merge -m "merge heads" <revA> <revB>
  ```

---

## Data Migration (backfill) trong Alembic

Thỉnh thoảng bạn cần **migrate dữ liệu** (không chỉ schema), ví dụ: tính `content_tsv`, gán `hash`, backfill `chunk_embeddings` tạm thời.

```python
def upgrade():
    # ví dụ: backfill TSV
    op.execute("UPDATE chunks SET content_tsv = to_tsvector('simple', content) WHERE content_tsv IS NULL")

    # ví dụ: chạy logic Python nhỏ
    bind = op.get_bind()
    rows = list(bind.execute(sa.text("SELECT id, content FROM chunks WHERE hash IS NULL LIMIT 10000")))
    for rid, content in rows:
        h = __import__("hashlib").sha256(content.encode("utf-8")).hexdigest()
        bind.execute(sa.text("UPDATE chunks SET hash=:h WHERE id=:rid"), {"h": h, "rid": rid})
```

> Với **khối lượng lớn**, nên viết **job ngoài Alembic** (Celery/RQ/cron) để tránh migration chạy quá lâu. Alembic nên chỉ giữ **DDL** + backfill nhẹ.

---

## Tích hợp Docker Compose (migrate-on-start)

Thêm service `migrate` để DB **luôn đúng schema** trước khi API chạy:

```yaml
# docker-compose.yml (trích)
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: ${PGDATABASE}
      POSTGRES_USER: ${PGUSER}
      POSTGRES_PASSWORD: ${PGPASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${PGUSER} -d ${PGDATABASE}"]
      interval: 5s
      timeout: 5s
      retries: 20

  migrate:
    build: ./api
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    command: ["alembic", "upgrade", "head"]

  api:
    build: ./api
    env_file: .env
    depends_on:
      migrate:
        condition: service_started
    # command: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> Đảm bảo Docker image của `api` **có cài alembic** và COPY thư mục `migrations/` + `alembic.ini`.

---

## CI/CD (ví dụ GitHub Actions)

```yaml
name: Deploy API
on: [push]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r api/requirements.txt
      - run: |
          cd api
          echo "DATABASE_URL=${{ secrets.DATABASE_URL }}" >> .env
          alembic upgrade head     # 1) migrate schema
          # 2) build & deploy app (tuỳ quy trình của bạn)
```

---

## Quy ước & Best Practices

1. **Mỗi thay đổi nhỏ = 1 revision** (atomic, dễ rollback).
2. **Idempotent** khi có thể: `CREATE EXTENSION/INDEX IF NOT EXISTS`.
3. **Có `downgrade()`** (reversible). Nếu không thể hoàn toàn, ghi chú rõ.
4. **Tránh khoá dài**: dùng `CREATE INDEX CONCURRENTLY` (cần ngoài transaction).
5. **Không trộn data job nặng** vào migration. Dùng job riêng cho re-embed/re-chunk.
6. **Đặt tên rõ ràng**: `YYYYMMDDHHMM_<short_desc>.py`.
7. **Feature flags** khi chuyển model embedding/dim → dual-read + rerank.
8. **Backup trước khi migrate**: `pg_dump` hoặc snapshot volume.

---

## Xử lý tình huống thường gặp

* **`permission denied to create extension`**
  → Role DB không đủ quyền: xin DBA cấp quyền hoặc tạo extension ở cấp DB trước.
* **`vector`/`pg_trgm` không có**
  → Cần cài `pgvector`/`pg_trgm` trên server (managed PG thường hỗ trợ sẵn). Nếu không, hãy bỏ phần index/extension tương ứng.
* **`CREATE INDEX CONCURRENTLY` báo lỗi “cannot run inside a transaction block”**
  → Đảm bảo `transactional_ddl=False` (env.py) **và** tách lệnh bằng `op.execute("COMMIT")` trước khi tạo index.
* **Đổi kích thước vector (dim)**
  → Tạo **bảng/column mới**, backfill dần, đổi read-policy → xoá cũ khi ổn.
* **Nhiều người tạo migration song song → nhiều HEAD**
  → Dùng `alembic merge` để hợp nhất.

---

## Makefile tiện dụng (tuỳ chọn)

```makefile
.PHONY: mig-new mig-up mig-down mig-heads mig-current

mig-new:
\tcd api && alembic revision -m "$(m)"

mig-up:
\tcd api && alembic upgrade head

mig-down:
\tcd api && alembic downgrade -1

mig-heads:
\tcd api && alembic heads

mig-current:
\tcd api && alembic current
```

---

## Kết luận

* Alembic **không bắt buộc bạn dùng ORM**; chỉ quản lý **vòng đời schema**.
* Bắt đầu bằng **một migration khởi tạo** (extensions/bảng/index), tích hợp **migrate-on-start** trong Compose/CI.
* Tuân thủ best practices → migration an toàn, có thể rollback, và **bảo trì lâu dài**.

> Cần mình tạo sẵn bộ file `alembic.ini`, `migrations/env.py` và **3 migration mẫu** (init schema, thêm bảng `chunk_embeddings`, thêm index FTS/trgm/HNSW) theo đúng repo của bạn không?

# Bộ file alembic.ini, migrations/env.py và 3 migration mẫu (init schema, thêm bảng chunk_embeddings, thêm index FTS/trgm/HNSW)

 **drop-in** vào thư mục `api/`.

---

## 1) `api/alembic.ini`

```ini
# --- Alembic Config (drop-in) ---
[alembic]
script_location = migrations
# Để trống URL vì ta đọc từ ENV trong migrations/env.py
# sqlalchemy.url =

# Tùy chọn log (giữ mặc định là ổn)
[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

---

## 2) `api/migrations/env.py`

> Đọc `DATABASE_URL` từ `.env` (ví dụ: `postgresql+psycopg://USER:PASS@HOST:5432/DBNAME`).
> Không dùng ORM → `target_metadata = None`. Bật `transactional_ddl=False` để linh hoạt các lệnh DDL.

```python
from __future__ import annotations
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from dotenv import load_dotenv

# --- Alembic Config ---
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Read ENV (.env in api/) ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (expected in .env)")

# Không dùng ORM metadata
target_metadata = None

def run_migrations_offline():
    """Run migrations in 'offline' mode (no live DB connection)."""
    context.configure(
        url=DATABASE_URL,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Cho phép DDL ngoài transaction nếu cần
        transactional_ddl=False,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode (with DB connection)."""
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transactional_ddl=False,  # để có thể tạo index dạng CONCURRENTLY nếu bạn chỉnh sửa
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## 3) 3 migration mẫu (đặt trong `api/migrations/versions/`)

> **Lưu ý:** Tên file có thể khác, nhưng bên trong mỗi file phải có biến `revision`/`down_revision` đúng chuỗi như dưới để nối chuỗi migration.

## 3.1 `api/migrations/versions/0001_init_schema.py`

Tạo extensions cơ bản và 2 bảng `documents`, `chunks` (chưa thêm cột `content_tsv` & index nâng cao ở bước này).

```python
from alembic import op
import sqlalchemy as sa

# Revision IDs
revision = "0001_init_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Extensions (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # documents
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("ingest_version", sa.Text, server_default="v1", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # chunks
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("document_id", sa.BigInteger, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("hash", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Index duy trì tính duy nhất theo (document_id, chunk_index)
    op.create_index("idx_chunks_doc_idx", "chunks", ["document_id", "chunk_index"], unique=True)


def downgrade():
    op.drop_index("idx_chunks_doc_idx", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
    # Giữ extensions lại (tuỳ chọn):
    # op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    # op.execute("DROP EXTENSION IF EXISTS vector")
```

---

## 3.2 `api/migrations/versions/0002_add_chunk_embeddings.py`

Tách embeddings ra bảng riêng để hỗ trợ **đa model/đa kích thước**.

> Dùng `op.execute` với SQL thuần để khai báo kiểu `vector(1536)` của pgvector cho tương thích tốt (khỏi cài thêm type adapter cho SQLAlchemy). Bạn có thể đổi `1536` → dim của model bạn đang dùng.

```python
from alembic import op

revision = "0002_add_chunk_embeddings"
down_revision = "0001_init_schema"
branch_labels = None
depends_on = None

EMBED_DIM = 1536  # đổi theo model embedding của bạn

def upgrade():
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
            id BIGSERIAL PRIMARY KEY,
            chunk_id BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            dim INT NOT NULL DEFAULT {EMBED_DIM},
            vector VECTOR({EMBED_DIM}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chunk_embeddings_chunk_model
        ON chunk_embeddings (chunk_id, model);
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_chunk_embeddings_chunk_model;")
    op.execute("DROP TABLE IF EXISTS chunk_embeddings;")
```

---

## 3.3 `api/migrations/versions/0003_add_search_indexes.py`

Thêm:

* Cột `content_tsv` (tsvector) + backfill cơ bản bằng `to_tsvector('simple', content)`
* Index GIN cho `content_tsv`
* Index GIN Trigram cho `content`
* Index HNSW cho `chunk_embeddings.vector` (cosine)

> Mặc định **không** dùng `CONCURRENTLY` để đảm bảo chạy an toàn trong mọi môi trường. Nếu dữ liệu đã rất lớn và bạn cần giảm khóa, bạn có thể đổi các dòng `CREATE INDEX` sang `CREATE INDEX CONCURRENTLY` **và** đảm bảo `transactional_ddl=False` (đã bật trong `env.py`), kèm `op.execute("COMMIT")` trước lệnh đó.

```python
from alembic import op
import sqlalchemy as sa

revision = "0003_add_search_indexes"
down_revision = "0002_add_chunk_embeddings"
branch_labels = None
depends_on = None

def upgrade():
    # 1) TSVECTOR column + backfill
    op.add_column("chunks", sa.Column("content_tsv", sa.TEXT(), nullable=True))
    # Dùng 'simple' cho ngôn ngữ không có stemming mặc định (vd: Vietnamese)
    op.execute("UPDATE chunks SET content_tsv = to_tsvector('simple', content) WHERE content_tsv IS NULL;")
    # (Tuỳ chọn) trigger tự động cập nhật TSV khi content đổi:
    op.execute("""
    CREATE OR REPLACE FUNCTION chunks_tsv_update() RETURNS trigger AS $$
    BEGIN
      NEW.content_tsv := to_tsvector('simple', NEW.content);
      RETURN NEW;
    END
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    DROP TRIGGER IF EXISTS trg_chunks_tsv_update ON chunks;
    CREATE TRIGGER trg_chunks_tsv_update
      BEFORE INSERT OR UPDATE OF content ON chunks
      FOR EACH ROW EXECUTE FUNCTION chunks_tsv_update();
    """)

    # 2) FTS index (GIN) + trigram index (GIN)
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_chunks_tsv_gin
      ON chunks USING GIN (content_tsv);
    """)
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_chunks_trgm
      ON chunks USING GIN (content gin_trgm_ops);
    """)

    # 3) HNSW index cho vector (cosine). Nếu PG/pgvector của bạn hỗ trợ CONCURRENTLY, có thể thêm từ khóa đó.
    op.execute("""
      CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw
      ON chunk_embeddings USING hnsw (vector vector_cosine_ops);
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_chunk_embeddings_hnsw;")
    op.execute("DROP INDEX IF EXISTS idx_chunks_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_chunks_tsv_gin;")
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv_update ON chunks;")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsv_update;")
    op.drop_column("chunks", "content_tsv")
```

---

## 4) `.env` mẫu (đặt trong `api/.env`)

```env
# SQLAlchemy-style URL (psycopg v3 driver)
DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/postgres
```

> Nếu bạn đang chạy local không qua Docker, đổi `db` → `localhost` và thông tin tương ứng.

---

## 5) Cách chạy

```bash
cd api

# 1) Cài dependencies nếu chưa có
pip install -r requirements.txt
# (đảm bảo requirements.txt có alembic, SQLAlchemy, psycopg[binary], python-dotenv)

# 2) Tạo thư mục migrations (nếu bạn copy y nguyên bộ file này, đã có sẵn)
# alembic init migrations   # (KHÔNG cần nếu đã copy cả thư mục)

# 3) Nâng schema lên HEAD (chạy tuần tự 0001 → 0002 → 0003)
alembic upgrade head

# 4) Kiểm tra trạng thái
alembic current
alembic history --verbose

# 5) Rollback 1 bước (nếu cần)
alembic downgrade -1
```

---

## 6) Tips & Nâng cao

* **Thay đổi dim vector** (vd 1536 → 3072):
  Tạo **migration mới**:

  1. Tạo bảng `chunk_embeddings_v2` với `VECTOR(3072)`.
  2. Backfill dần (job ngoài Alembic).
  3. Chuyển read-path sang v2 → xoá bảng cũ.

* **Giảm lock khi index trên bảng lớn**:
  Đổi các câu lệnh sang `CREATE INDEX CONCURRENTLY ...` và thêm `op.execute("COMMIT")` ngay trước mỗi lệnh đó. Giữ `transactional_ddl=False` trong `env.py`.

* **Migrate-on-start (Docker Compose)**:
  Tạo service `migrate` chạy `alembic upgrade head` trước khi khởi động API.

---
Next step (option):

* Viết `Dockerfile`/`docker-compose` tích hợp chạy migrate tự động.
* Thêm `Makefile` alias (`mig-new`, `mig-up`, `mig-down`…).
* Viết script `reembed.py` (batch) để backfill embeddings song song, không downtime.
