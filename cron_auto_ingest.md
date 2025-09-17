Chuẩn câu hỏi “sản phẩm thật” nè. Người dùng không (và không nên) SSH vào container để gõ `python -m app.ingest`. Ta cần biến “ingest + re-embedding” thành **dịch vụ nền** có API, hàng đợi job, và lịch (scheduler). Dưới đây là blueprint gọn – bạn có thể triển khai dần mà không đụng mạnh vào core RAG:

# Mục tiêu

1. Người dùng upload file qua **HTTP API** → hệ thống tự ingest (chunk → embed → lưu DB).
2. Cho phép **re-embedding** khi: cập nhật file, đổi model embedding, hoặc định kỳ cải thiện chất lượng.
3. Không block request: xử lý **async** (job queue + worker).
4. Dễ mở rộng: thêm provider/model, batch, retry, giám sát.

---

# Kiến trúc tổng quát

* **API (FastAPI)**: nhận upload, tạo job, trả về `job_id`.
* **Hàng đợi**: Redis (Celery/RQ) để đẩy việc nặng sang **Worker**.
* **Worker**: thực thi ingest/re-embed, batch embed, ghi DB.
* **Lưu trữ file**: S3-compatible (MinIO) hoặc local volume (tạm thời).
* **DB**: Postgres + pgvector (như hiện tại).
* **Scheduler**: Celery Beat (hoặc cron) để chạy re-embed/cleanup định kỳ.

```
Client → POST /v1/documents (file) → API → enqueue(Job)
                                   ↘ 201 {job_id}
Worker ← Redis queue  ← Job
Worker → Postgres (documents, chunks, embeddings)
```

---

# Lược đồ dữ liệu (đề xuất)

Bổ sung các bảng “quản trị vòng đời tài liệu”:

```sql
-- Tài liệu gốc
CREATE TABLE documents (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  title TEXT,
  source_uri TEXT,            -- s3://bucket/key.pdf hoặc file:///...
  mime_type TEXT,
  bytes_count BIGINT,
  hash_sha256 TEXT,           -- detect thay đổi file
  status TEXT,                -- ready | processing | failed
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Phiên bản xử lý (để re-embed không đè lẫn)
CREATE TABLE doc_versions (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id),
  embed_model TEXT,           -- ví dụ text-embedding-3-small
  chunk_size INT,
  chunk_overlap INT,
  state TEXT,                 -- indexing | ready | failed | superseded
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Chunk thuộc 1 version
CREATE TABLE doc_chunks (
  id UUID PRIMARY KEY,
  doc_version_id UUID REFERENCES doc_versions(id),
  chunk_index INT,
  content TEXT,
  content_hash TEXT
);

-- Vector tách riêng, gắn model/version
CREATE TABLE chunk_embeddings (
  id UUID PRIMARY KEY,
  chunk_id UUID REFERENCES doc_chunks(id),
  embed_model TEXT,
  vector VECTOR(1536),        -- tùy model
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Job hàng đợi/giám sát
CREATE TABLE jobs (
  id UUID PRIMARY KEY,
  job_type TEXT,              -- ingest|reembed|delete|repair
  document_id UUID,
  doc_version_id UUID,
  status TEXT,                -- queued|running|succeeded|failed
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

> Lợi ích: bạn **giữ lại history** theo `doc_versions`, phục vụ rollback/so sánh, và có thể “supersede” version cũ khi re-embed.

---

# API endpoints (đi tối thiểu)

```http
POST   /v1/documents            # upload file, tạo document + job ingest
GET    /v1/jobs/{job_id}        # xem trạng thái job
POST   /v1/documents/{id}/reembed   # yêu cầu re-embed (toàn bộ/1 version)
POST   /v1/documents/{id}/delete    # xoá tài liệu + vector kèm theo (soft/hard)
GET    /v1/documents/{id}/versions  # liệt kê các version + model dùng
```

### Ví dụ handler (rút gọn – FastAPI)

```python
@router.post("/v1/documents")
async def upload_document(file: UploadFile, user=Depends(auth)):
    # 1) Lưu file -> S3/MinIO, tính sha256
    uri, size, sha = await save_and_hash(file)
    # 2) Tạo documents + job ingest
    doc_id = uuid4()
    db.insert_document(doc_id, user.id, file.filename, uri, file.content_type, size, sha, status="processing")
    job_id = enqueue_job(type="ingest", document_id=doc_id, params={"chunk_size": 1000, "overlap": 200})
    return {"document_id": str(doc_id), "job_id": str(job_id)}
```

---

# Worker flow (ingest)

1. Tải file từ S3 (stream).
2. Trích xuất text (PDF/TXT/MD) → **chunk\_text**(size/overlap từ config).
3. Tạo **doc\_versions** (ghi model, tham số).
4. **Batch embed** (vd 64–128 chunk/lần) → ghi `chunk_embeddings`.
5. Cập nhật `jobs.status = succeeded`, `documents.status = ready`.

### Worker (rút gọn)

```python
def run_ingest(document_id, chunk_size, overlap):
    doc = db.get_document(document_id)
    text = extract_text(doc.source_uri, mime=doc.mime_type)
    chunks = chunk_text(text, chunk_size, overlap)
    ver_id = db.create_version(document_id, embed_model=CFG.EMBED_MODEL, chunk_size=chunk_size, chunk_overlap=overlap, state="indexing")

    ids = db.insert_chunks(ver_id, chunks)  # trả về list chunk_id theo index
    for batch in batched(ids, size=64):
        vecs = openai_embed([db.get_chunk_text(cid) for cid in batch], model=CFG.EMBED_MODEL)
        db.insert_embeddings(batch, vecs, model=CFG.EMBED_MODEL)

    db.mark_version_ready(ver_id)
```

---

# Re-embedding: khi nào & làm sao

**Khi nào**

* Thay đổi **embed model** (ví dụ từ `text-embedding-3-small` sang `text-embedding-3-large`).
* Người dùng **sửa/replace file** (hash khác).
* Tối ưu tham số **chunk\_size/overlap**.
* Định kỳ cải thiện chất lượng (nếu bạn bật cohere-rerank thì có thể giảm tần suất re-embed).

**Cách làm** (không dừng hệ thống)

* Tạo **doc\_version mới** với model/param mới, **không xoá** version cũ ngay.
* Sau khi index xong, set `doc_versions.state = ready` cho bản mới, **gắn route retrieval** đọc bản mới theo rule:

  * Mặc định: chọn `doc_version` **mới nhất có state=ready** cho mỗi `document_id`.
  * Giữ bản cũ `state = superseded` để fallback hoặc kiểm chứng.
* Lên lịch **Celery Beat**:

  * Nightly job: tìm `documents` có `hash_sha256` thay đổi hoặc `embed_model` mục tiêu khác → enqueue re-embed theo batch.

### Endpoint re-embed

```python
@router.post("/v1/documents/{doc_id}/reembed")
def reembed_document(doc_id: UUID, params: ReembedParams):
    # params: target_model?, chunk_size?, overlap?, scope=all|version_id
    job_id = enqueue_job(type="reembed", document_id=doc_id, params=params.dict())
    return {"job_id": str(job_id)}
```

---

# Docker Compose bổ sung

```yaml
services:
  api:
    # như hiện tại
  worker:
    build: ./api
    command: celery -A app.queue worker --concurrency=2 --loglevel=INFO
    depends_on: [redis, db]
    env_file: [.env]
  beat:
    build: ./api
    command: celery -A app.queue beat --loglevel=INFO
    depends_on: [redis, db]
    env_file: [.env]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

---

# Retrieval không gián đoạn

* Query chọn **doc\_version mới nhất = ready**.
* Nếu re-embed đang chạy: vẫn dùng version cũ.
* Khi bản mới xong: chuyển route đọc sang bản mới (atomic switch).

---

# Tối ưu & vận hành

* **Batching**: 64–128 input/lần cho embed; exponential backoff khi 429.
* **Idempotency**: khóa theo `document_id + model + chunk_params` để không enqueue trùng.
* **Auth/Quota**: mỗi `user_id` có quota tài liệu/số ký tự/ngày.
* **Sanitization**: chặn file quá lớn, scan PDF (maldoc), giới hạn mine type.
* **Observability**: lưu `jobs.duration_ms`, Prometheus metrics (jobs\_running, embeds/sec).
* **Migrate model dims**: nếu đổi model vector dim → tạo **cột/vector mới** hoặc bảng embeddings mới; đừng reuse sai dim.
* **Partial re-embed**: nếu chỉ vài chunk thay đổi (so sánh `content_hash`), chỉ re-embed các chunk đó.

---

# TL;DR – Checklist để làm ngay

1. Thêm bảng `documents`, `doc_versions`, `doc_chunks`, `chunk_embeddings`, `jobs`.
2. Viết `POST /v1/documents` (upload + enqueue ingest).
3. Thêm Redis + Celery (worker + beat) vào compose.
4. Worker: `run_ingest` + `run_reembed` (batch embed + ghi DB).
5. Retrieval đọc `doc_version` mới nhất `ready`; giữ bản cũ làm fallback.
6. Beat: job đêm tìm tài liệu đổi hash/model → enqueue re-embed.

Nếu bạn muốn, mình có thể draft sẵn file `queue.py` (Celery) + router `documents.py` (FastAPI) tối giản để bạn copy vào repo hiện tại và chạy được ngay trong compose.
