# 📚 Chatnary RAG Backend - Tóm tắt Dự án

## 🎯 Tổng quan

**Chatnary** là hệ thống RAG (Retrieval Augmented Generation) backend được xây dựng bằng Python FastAPI, tích hợp AI để trả lời câu hỏi dựa trên tài liệu đã được ingest. Hệ thống hỗ trợ xử lý PDF, văn bản với OCR và embedding vector để tìm kiếm ngữ nghĩa.

### Tính năng chính

- ✅ Ingest tài liệu PDF/TXT/MD với OCR fallback cho PDF scan
- ✅ Vector similarity search + Full-text search (hybrid)
- ✅ Reranking với Cohere
- ✅ Trả lời câu hỏi với Google Gemini
- ✅ Hỗ trợ tiếng Việt và tiếng Anh

---

## 🏗️ Kiến trúc hệ thống

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │───▶│   FastAPI       │───▶│   PostgreSQL    │
│   (External)    │    │   Backend       │    │   + pgvector    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   AI Services   │
                       │ OpenAI/Cohere/  │
                       │   Gemini        │
                       └─────────────────┘
```

### Luồng xử lý

1. **Ingest**: PDF → Text → Chunks → Embeddings → PostgreSQL
2. **Query**: Question → Hybrid Search → Rerank → LLM → Answer

---

## 📁 Cấu trúc thư mục

```
chatnary-be-fastAPI/
├── api/                     # Ứng dụng FastAPI chính
│   ├── app/
│   │   ├── main.py         # FastAPI endpoints
│   │   ├── settings.py     # Cấu hình môi trường
│   │   ├── db.py           # Database connection
│   │   ├── pdf_processor.py # Xử lý PDF với OCR
│   │   ├── chunker.py      # Chia nhỏ văn bản
│   │   ├── ingest.py       # Ingest tài liệu
│   │   ├── llm.py          # AI services (OpenAI, Cohere, Gemini)
│   │   └── retrieval.py    # Hybrid search
│   ├── Dockerfile
│   └── requirements.txt
├── db/
│   └── init/               # SQL schema initialization
│       ├── 00-extensions.sql
│       └── 01-schema.sql
├── data/                   # Thư mục tài liệu để ingest
└── docker-compose.yml      # Docker orchestration
```

---

## 🗄️ Database Schema (PostgreSQL + pgvector)

### Tables

#### `documents`

```sql
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    source TEXT,                    -- đường dẫn file
    title TEXT,                     -- tên file
    url TEXT,                       -- URL (optional)
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### `chunks`

```sql
CREATE TABLE chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,  -- thứ tự chunk trong document
    content TEXT NOT NULL,          -- nội dung text
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content,''))) STORED,
    embedding vector(1536)          -- vector embedding từ OpenAI
);
```

### Indexes

- **Vector HNSW**: `idx_chunks_embedding_hnsw` cho cosine similarity search
- **Full-text GIN**: `idx_chunks_tsv_gin` cho keyword search
- **Trigram GIN**: `idx_chunks_trgm` cho fuzzy Vietnamese search

---

## 🚀 Tech Stack

### Core Framework

- **FastAPI**: Web framework với async support
- **Uvicorn**: ASGI server
- **Pydantic**: Data validation
- **psycopg**: PostgreSQL driver

### AI & ML

- **OpenAI**: text-embedding-3-small (1536 dims)
- **Cohere**: rerank-multilingual-v3.0
- **Google Gemini**: gemini-2.5-flash-lite

### Document Processing

- **PyPDF**: PDF text extraction
- **pdfminer.six**: Advanced PDF parsing
- **pdf2image + pytesseract**: OCR cho PDF scan
- **Pillow**: Image processing

### Database

- **PostgreSQL 16**: Main database
- **pgvector**: Vector similarity extension
- **pg_trgm**: Trigram fuzzy search

---

## 📄 API Endpoints

### `POST /ask`

Trả lời câu hỏi dựa trên tài liệu đã ingest

**Request:**

```json
{
    "query": "Tài liệu này nói gì về bảo mật?",
    "k_vector": 60,
    "k_keyword": 30,
    "rerank_top_n": 8,
    "answer_language": "vi"
}
```

**Response:**

```json
{
    "answer": "Tài liệu đề cập các biện pháp bảo mật...",
    "sources": [
        {
            "document_id": 1,
            "chunk_index": 2,
            "title": "security_guide",
            "source": "/data/security_guide.pdf",
            "preview": "Bảo mật dữ liệu là yếu tố quan trọng..."
        }
    ]
}
```

### `GET /health`

Kiểm tra trạng thái hệ thống

### `GET /capabilities`

Thông tin về khả năng xử lý PDF và OCR

---

## 🧠 Chi tiết Implementation

### 1. PDF Processing (`pdf_processor.py`)

**Multi-stage PDF extraction với fallback:**

```python
class PDFProcessor:
    def extract_text(self, pdf_path: pathlib.Path) -> str:
        # 1. PyPDF (nhanh nhất)
        text = self._try_pypdf(pdf_path)
        if text.strip():
            return text
            
        # 2. pdfminer.six (cho PDF phức tạp)
        text = self._try_pdfminer(pdf_path)
        if text.strip():
            return text
            
        # 3. OCR (cho PDF scan)
        text = self._try_ocr(pdf_path)
        return text
```

**OCR với image enhancement:**

- Convert PDF → images (300 DPI)
- Grayscale conversion
- Contrast & sharpness enhancement
- Tesseract với vie+eng languages

### 2. Text Chunking (`chunker.py`)

**Smart chunking với overlap:**

```python
def chunk_text(text: str, max_chars: int = 1000, overlap: int = 200) -> List[str]:
    # Chia text thành chunks với overlap
    # Tránh cắt giữa paragraph khi có thể
    # Trả về list chunks không trống
```

### 3. Embedding & Vector Storage (`llm.py`)

**OpenAI Embeddings:**

```python
def embed_texts(texts: List[str]) -> List[List[float]]:
    # Sử dụng text-embedding-3-small
    # Batch processing để tối ưu API calls
    # Trả về vectors 1536 dimensions
```

### 4. Hybrid Search (`retrieval.py`)

**Vector + Keyword search combination:**

```python
def hybrid_search(query: str, k_vec: int = 60, k_kw: int = 30) -> List[Dict]:
    # 1. Vector similarity với pgvector cosine distance
    q_vec = embed_texts([query])[0]
    vec_hits = _vector_candidates(q_vec, limit=k_vec)
    
    # 2. Keyword search với PostgreSQL FTS + trigram fallback
    kw_hits = _keyword_candidates(query, limit=k_kw)
    
    # 3. Merge & deduplicate, giữ score cao nhất
    return merged_results
```

**Vector Search Query:**

```sql
SELECT id, document_id, chunk_index, content,
       1.0 - (embedding <=> %s::vector) AS score
FROM chunks
ORDER BY embedding <=> %s::vector
LIMIT %s
```

**Keyword Search với FTS:**

```sql
SELECT id, document_id, chunk_index, content, 
       ts_rank(content_tsv, plainto_tsquery('simple', %s)) AS score
FROM chunks
WHERE content_tsv @@ plainto_tsquery('simple', %s)
ORDER BY score DESC
```

**Trigram Fallback:**

```sql
SELECT id, document_id, chunk_index, content, 
       similarity(content, %s) AS score
FROM chunks
WHERE content ILIKE %s
ORDER BY score DESC
```

### 5. Reranking (`llm.py`)

**Cohere reranking để cải thiện relevance:**

```python
def rerank(query: str, docs: List[Dict], top_n: int = 8) -> List[Dict]:
    # Sử dụng rerank-multilingual-v3.0
    # Re-score và re-order candidates
    # Trả về top_n kết quả tốt nhất
```

### 6. Answer Generation (`llm.py`)

**Google Gemini với context từ retrieved chunks:**

```python
def generate_answer(query: str, context_blocks: List[Dict], language: str = "vi") -> str:
    # Build prompt với context từ top chunks
    # Thêm guardrails và source citations
    # Sử dụng gemini-2.5-flash-lite
```

**Prompt Template:**

```
Bạn là trợ lý RAG. Trả lời NGẮN GỌN bằng tiếng Việt dựa hoàn toàn vào CONTEXT dưới đây.
Nếu không đủ thông tin, nói rõ: 'Mình không tìm thấy đủ thông tin trong tài liệu.'
Luôn kèm mục 'Nguồn' với [doc_id:chunk] đã dùng.

---
CONTEXT:
- [1:0] security_guide.pdf → Bảo mật dữ liệu là yếu tố quan trọng...
- [2:5] user_manual.pdf → Hệ thống authentication sử dụng JWT...

---
CÂU HỎI: Tài liệu này nói gì về bảo mật?
```

---

## 🔧 Configuration (`settings.py`)

### Environment Variables

```python
# Database
PGHOST=localhost
PGPORT=5432
PGDATABASE=rag
PGUSER=rag
PGPASSWORD=ragpw

# AI Services
OPENAI_API_KEY=sk-...
OPENAI_EMBED_MODEL=text-embedding-3-small

COHERE_API_KEY=...
COHERE_RERANK_MODEL=rerank-multilingual-v3.0

GOOGLE_API_KEY=...  # hoặc GEMINI_API_KEY
GEMINI_MODEL=gemini-2.5-flash-lite

# Chunking
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
```

---

## 🐳 Docker Setup

### `docker-compose.yml`

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: rag
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: ragpw
    volumes:
      - ./db/init:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"

  api:
    build: ./api
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./data:/data
    ports:
      - "8000:8000"
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

---

## ⚡ Quy trình sử dụng

### 1. Setup & Start

```bash
# Copy environment
cp .env.example .env
# Điền API keys

# Start services
docker compose up -d --build
```

### 2. Ingest Documents

```bash
# Đặt PDFs/TXT/MD vào ./data/
# Ingest tất cả
docker compose exec api python -m app.ingest /data

# Test trước khi ingest
docker compose exec api python test_pdf.py "filename.pdf"
```

### 3. Query

```bash
curl -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "Tài liệu này nói gì về bảo mật?"}'
```

---

## 🔍 Key Features & Optimizations

### 1. Robust PDF Processing

- **3-stage fallback**: PyPDF → pdfminer → OCR
- **Image enhancement**: Contrast, sharpness cho OCR tốt hơn
- **Multi-language OCR**: Tiếng Việt + English
- **Error handling**: Graceful degradation

### 2. Intelligent Search

- **Hybrid approach**: Vector similarity + Keyword search
- **Vietnamese support**: Simple dictionary + trigram fuzzy
- **Deduplication**: Merge results, keep best scores
- **Scalable indexing**: HNSW cho vector, GIN cho text

### 3. AI Pipeline

- **Batch embeddings**: Minimize OpenAI API calls
- **Quality reranking**: Cohere multilingual model
- **Contextual generation**: Source-aware answers
- **Guardrails**: Clear limitations và source citations

### 4. Production Ready

- **Health checks**: Database connectivity monitoring
- **Error handling**: Comprehensive exception management
- **Docker support**: Full containerization
- **Environment configs**: Flexible deployment settings

---

## 🎯 Điểm mạnh của Architecture

1. **Modularity**: Mỗi component độc lập, dễ test và maintain
2. **Scalability**: PostgreSQL với pgvector scale tốt
3. **Reliability**: Multiple fallbacks cho PDF processing
4. **Performance**: HNSW indexing, batch processing
5. **Flexibility**: Support multiple AI providers
6. **Vietnamese-first**: Tối ưu cho tiếng Việt từ OCR đến search

---

## 📝 Future Enhancements

- [ ] User authentication & rate limiting
- [ ] Chat history persistence
- [ ] DOCX/HTML support
- [ ] SQLAlchemy + Alembic migrations
- [ ] RAG evaluation với RAGAS
- [ ] Telemetry và monitoring
- [ ] Advanced chunking strategies

---

## 📁 Source Code Đầy Đủ

### 🚀 `api/app/main.py` - FastAPI Application

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict
import orjson
from .settings import settings
from .retrieval import hybrid_search
from .llm import rerank, generate_answer
from .db import get_conn
from .pdf_processor import pdf_processor

app = FastAPI(title="RAG Skeleton")


class AskRequest(BaseModel):
    query: str
    k_vector: int = 60
    k_keyword: int = 30
    rerank_top_n: int = 8
    answer_language: str = "vi"


class AskResponse(BaseModel):
    answer: str
    sources: List[Dict]

# Check health


@app.get("/health")
def health():
    # quick DB ping
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}

# Ask a question


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    candidates = hybrid_search(
        req.query, k_vec=req.k_vector, k_kw=req.k_keyword)

    # add friendly metadata (title)
    if candidates:
        ids = list({c["document_id"] for c in candidates})
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, title, source FROM documents WHERE id = ANY(%s)",
                (ids,)
            ).fetchall()
#             rows = [
#               (2, "report", r"C:\data\report.pdf"),
#               (5, "notes", r"C:\data\notes.md"),
#                 ...]
        meta = {r[0]: {"title": r[1], "source": r[2]} for r in rows}
# meta = {
#   2: {"title": "report", "source": "C:\\data\\report.pdf"},
#   5: {"title": "notes",  "source": "C:\\data\\notes.md"}
# }
        for c in candidates:
            c.setdefault("meta", {}).update(meta.get(c["document_id"], {}))

    # Prepare docs for rerank
    docs = [{"text": c["text"], "meta": c.get("meta", {})} for c in candidates]
    # Call rerank
    top = rerank(req.query, docs, top_n=req.rerank_top_n)

    # Call LLM to generate answer
    answer = generate_answer(req.query, top, language=req.answer_language)

    # expose minimal source info
    sources = [
        {
            "document_id": d["meta"].get("document_id"),
            "chunk_index": d["meta"].get("chunk_index"),
            "title": d["meta"].get("title"),
            "source": d["meta"].get("source"),
            "preview": d["text"][:240]
        }
        for d in top
    ]
    return AskResponse(answer=answer, sources=sources)


@app.get("/capabilities")
def get_capabilities():
    """Check PDF processing capabilities"""
    return {
        "pdf_processing": pdf_processor.get_capabilities(),
        "database": "connected",
        "version": "2.0.0-ocr"
    }
```

### ⚙️ `api/app/settings.py` - Configuration Management

```python
import os
from dataclasses import dataclass


@dataclass
class Settings:
 pg_host: str = os.getenv("PGHOST", "localhost")
 pg_port: int = int(os.getenv("PGPORT", "5432"))
 pg_db: str = os.getenv("PGDATABASE", "rag")
 pg_user: str = os.getenv("PGUSER", "rag")
 pg_password: str = os.getenv("PGPASSWORD", "ragpw")


 openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
 openai_embed_model: str = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")


 cohere_api_key: str = os.getenv("COHERE_API_KEY", "")
 cohere_rerank_model: str = os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0")


 google_api_key: str = os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
 gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


 chunk_size: int = int(os.getenv("CHUNK_SIZE", "1000"))
 chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "200"))


settings = Settings()
```

### 🗄️ `api/app/db.py` - Database Connection

```python
# ingest.py: insert chunks & embeddings in Postgres.

# retrieval.py: query vector similarity (pgvector).

# llm.py: fetch chunk text to build context for responses.


from contextlib import contextmanager
import psycopg
from .settings import settings


DSN = f"host={settings.pg_host} port={settings.pg_port} dbname={settings.pg_db} user={settings.pg_user} password={settings.pg_password}"


@contextmanager
def get_conn():
    with psycopg.connect(DSN) as conn:
        yield conn
```

### 📄 `api/app/pdf_processor.py` - PDF Processing với OCR

```python
"""
OCR Module for handling scanned PDFs and images
Supports multiple OCR approaches with intelligent fallback
"""

import tempfile
import pathlib
import logging
from typing import Optional, List
import io

try:
    from pdf2image import convert_from_path
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Robust PDF processor with multiple extraction methods"""

    def __init__(self):
        self.ocr_available = OCR_AVAILABLE
        self.pdfminer_available = PDFMINER_AVAILABLE

        # Configure tesseract for Vietnamese + English
        if self.ocr_available:
            self.ocr_languages = 'vie+eng'

    def extract_text(self, pdf_path: pathlib.Path) -> str:
        """
        Extract text from PDF using multiple methods:
        1. PyPDF (fast, for text-based PDFs)
        2. pdfminer.six (fallback for complex PDFs)
        3. OCR (for scanned PDFs)
        """
        logger.info(f"Processing PDF: {pdf_path.name}")

        # Method 1: Try PyPDF first (fastest)
        text = self._try_pypdf(pdf_path)
        if text.strip():
            logger.info(f"✓ PyPDF successful for {pdf_path.name}")
            return text

        # Method 2: Try pdfminer.six
        if self.pdfminer_available:
            text = self._try_pdfminer(pdf_path)
            if text.strip():
                logger.info(f"✓ pdfminer successful for {pdf_path.name}")
                return text

        # Method 3: OCR as last resort
        if self.ocr_available:
            text = self._try_ocr(pdf_path)
            if text.strip():
                logger.info(f"✓ OCR successful for {pdf_path.name}")
                return text

        logger.warning(f"❌ All methods failed for {pdf_path.name}")
        return ""

    def _try_pypdf(self, pdf_path: pathlib.Path) -> str:
        """Extract text using PyPDF"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages).strip()
        except Exception as e:
            logger.debug(f"PyPDF failed for {pdf_path.name}: {e}")
            return ""

    def _try_pdfminer(self, pdf_path: pathlib.Path) -> str:
        """Extract text using pdfminer.six"""
        try:
            text = pdfminer_extract(str(pdf_path)) or ""
            return text.strip()
        except Exception as e:
            logger.debug(f"pdfminer failed for {pdf_path.name}: {e}")
            return ""

    def _try_ocr(self, pdf_path: pathlib.Path) -> str:
        """Extract text using OCR (for scanned PDFs)"""
        try:
            logger.info(f"🔍 Starting OCR for {pdf_path.name}...")

            # Convert PDF to images
            images = convert_from_path(
                str(pdf_path),
                dpi=300,  # High quality for better OCR
                fmt='PNG'
            )

            if not images:
                logger.warning(f"No images extracted from {pdf_path.name}")
                return ""

            logger.info(f"📄 Processing {len(images)} pages with OCR...")

            # OCR each page
            ocr_texts = []
            for i, image in enumerate(images):
                try:
                    # Enhance image quality for better OCR
                    enhanced_image = self._enhance_image(image)

                    # Perform OCR
                    page_text = pytesseract.image_to_string(
                        enhanced_image,
                        lang=self.ocr_languages,
                        config='--psm 1'  # Automatic page segmentation
                    )

                    if page_text.strip():
                        ocr_texts.append(
                            f"=== Page {i+1} ===\n{page_text.strip()}")
                        logger.debug(
                            f"✓ OCR page {i+1}: {len(page_text)} chars")
                    else:
                        logger.debug(f"⚠ OCR page {i+1}: empty result")

                except Exception as e:
                    logger.warning(f"OCR failed for page {i+1}: {e}")
                    continue

            result = "\n\n".join(ocr_texts)
            logger.info(f"✓ OCR completed: {len(result)} characters extracted")
            return result

        except Exception as e:
            logger.error(f"OCR processing failed for {pdf_path.name}: {e}")
            return ""

    def _enhance_image(self, image: Image.Image) -> Image.Image:
        """Enhance image quality for better OCR results"""
        try:
            # Convert to grayscale for better OCR
            if image.mode != 'L':
                image = image.convert('L')

            # Increase contrast and sharpness
            from PIL import ImageEnhance

            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)

            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.0)

            return image
        except Exception as e:
            logger.debug(f"Image enhancement failed: {e}")
            return image

    def get_capabilities(self) -> dict:
        """Return available processing capabilities"""
        return {
            "pypdf": True,
            "pdfminer": self.pdfminer_available,
            "ocr": self.ocr_available,
            "ocr_languages": getattr(self, 'ocr_languages', None)
        }


# Global processor instance
pdf_processor = PDFProcessor()


def extract_text_from_pdf(pdf_path: pathlib.Path) -> str:
    """Convenience function for extracting text from PDF"""
    return pdf_processor.extract_text(pdf_path)
```

### ✂️ `api/app/chunker.py` - Text Chunking

```python
from typing import List

# chunks = [ "Chapter 1: Introduction\n\nThis chapter explains the design goals... (continues up to ~1000 chars)", "...(overlap 200 chars continues) Chapter 2: Architecture\n\nComponents include db, llm, chunker... (next ~1000 chars)",...
# ]


def chunk_text(text: str, max_chars: int = 1000, overlap: int = 200) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunk = text[start:end]
        # avoid cutting middle of a paragraph if possible
        if end < n:
            last_nl = chunk.rfind("\n")
            if last_nl > max_chars * 0.5:
                end = start + last_nl
                chunk = text[start:end]
        chunks.append(chunk.strip())
        start = max(end - overlap, end)
    return [c for c in chunks if c]
```

### 📥 `api/app/ingest.py` - Document Ingestion

```python
import argparse
import os
import pathlib
from typing import List, Tuple
from .pdf_processor import extract_text_from_pdf
from .chunker import chunk_text
from .llm import embed_texts
from .db import get_conn
TEXT_EXT = {".txt", ".md"}

# Read text from a file (PDF or text)
# input: Path("doc.pdf")  -> output: "Trang 1 text\n\nTrang 2 text\n\n..."
# input: Path("notes.md") -> output: "nội dung file markdown..."
# input: Path("image.png") -> output: ""


def _read_file(path: pathlib.Path) -> str:
    if path.suffix.lower() == ".pdf":
        # Use robust PDF processor with OCR fallback
        return extract_text_from_pdf(path)
    elif path.suffix.lower() in TEXT_EXT:
        return path.read_text(encoding="utf-8", errors="ignore")
    else:
        return ""

# argument(source, title): ("C:\\data\\newfile.pdf", "newfile")


def _upsert_document(conn, source: str, title: str) -> int:
    # return document ID
    row = conn.execute("SELECT id FROM documents WHERE source = %s",
                       (source,)).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "INSERT INTO documents (source, title) VALUES (%s, %s) RETURNING id",
        (source, title)
    ).fetchone()
    return row[0]

# doc_id = 2
# chunks = ["This is chunk one.", "Second chunk content..."]
# vectors = [
#   [0.123456789, -0.000001234, 0.9999999],
#   [0.5, 0.25, -0.125]
# ]


def _insert_chunks(conn, doc_id: int, chunks: List[str], vectors: List[List[float]]):
    assert len(chunks) == len(vectors)
    for i, (text, vec) in enumerate(zip(chunks, vectors)):
        # vec_literal_0 = "[0.012346,-0.001235,0.999999,0.000001,-0.123457,0.543211,...]"  # 1536 entries total
        vec_literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
        conn.execute(
            """
                INSERT INTO chunks (document_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s::vector)
                """,

            (doc_id, i, text, vec_literal)
        )


def ingest_dir(root: str, chunk_size: int, overlap: int):
    root_path = pathlib.Path(root)
    # Loop all project structure file
    paths = [p for p in root_path.rglob(
        "*") if p.suffix.lower() in {".pdf", ".txt", ".md"}]
    print(f"Found {len(paths)} files under {root}")
    with get_conn() as conn:
        with conn.transaction():
            for path in paths:
                text = _read_file(path)
                if not text.strip():
                    print(f"Skip empty: {path}")
                    continue
                doc_id = _upsert_document(conn, str(path), path.stem)
# chunks = [ "Chapter 1: Introduction\n\nThis chapter explains the design goals... (continues up to ~1000 chars)", "...(overlap 200 chars continues) Chapter 2: Architecture\n\nComponents include db, llm, chunker... (next ~1000 chars)",...
# ]
                chunks = chunk_text(
                    text, max_chars=chunk_size, overlap=overlap)
                if not chunks:
                    continue
                # embed in batches to minimize API calls
                batch = 64
                for s in range(0, len(chunks), batch):
                    sub = chunks[s:s+batch]
                    vecs = embed_texts(sub)
                    _insert_chunks(conn, doc_id, sub, vecs)
        print("Ingestion complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="Directory containing PDFs/TXT/MD")
    parser.add_argument("--chunk", type=int,
                        default=int(os.getenv("CHUNK_SIZE", "1000")))
    parser.add_argument("--overlap", type=int,
                        default=int(os.getenv("CHUNK_OVERLAP", "200")))
    args = parser.parse_args()

    import os
    chunk = args.chunk
    overlap = args.overlap
    ingest_dir(args.root, chunk, overlap)
```

### 🤖 `api/app/llm.py` - AI Services Integration

```python
import os
import json
import requests
from typing import List, Dict
from openai import OpenAI
import cohere
from google import genai
from .settings import settings


# ==== OpenAI (Embeddings) ====
_openai = None
if settings.openai_api_key:
    try:
        _openai = OpenAI(api_key=settings.openai_api_key)
    except Exception as e:
        print(f"Warning: Could not initialize OpenAI client: {e}")
        _openai = None

# vectors = [
#   [0.123456789, -0.000001234, 0.9999999],
#   [0.5, 0.25, -0.125]
# ]
def embed_texts(texts: List[str]) -> List[List[float]]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    # If OpenAI client failed, use direct API calls
    if not _openai:
        print("Using direct API calls for embeddings...")
        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": settings.openai_embed_model,
            "input": texts
        }

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return [d["embedding"] for d in result["data"]]

    # Use OpenAI client if available
    resp = _openai.embeddings.create(
        model=settings.openai_embed_model, input=texts)
    return [d.embedding for d in resp.data]


# ==== Cohere (Rerank) ====
_co = None
if settings.cohere_api_key:
    try:
        _co = cohere.Client(api_key=settings.cohere_api_key)
    except Exception as e:
        print(f"Warning: Could not initialize Cohere client: {e}")
        _co = None


def rerank(query: str, docs: List[Dict], top_n: int = 8) -> List[Dict]:
    """
    docs: List of {"text": str, "meta": {...}}
    Returns: same docs subset with added 'score', sorted by score desc
    """
    if not _co:
        # no cohere key -> simple fallback: return first top_n
        return docs[:top_n]
    # Cohere accepts list of strings or dicts with 'text'
    results = _co.rerank(
        model=settings.cohere_rerank_model,
        query=query,
        documents=[{"text": d["text"]} for d in docs],
        top_n=min(top_n, len(docs))
    )
# results is list of {index, relevance_score}
#     [
#   {
#     "text": "Đoạn văn liên quan nhất đến câu hỏi...",
#     "meta": {"document_id": 42, "chunk_index": 5, "title": "report", "source": "C:\\data\\report.pdf"},
#     "score": 0.92
#   }, ...]
    reranked = []
    for hit in results.results:
        item = docs[hit.index]
        item = {**item, "score": hit.relevance_score}
        reranked.append(item)
    return reranked


# ==== Gemini (Generation) ====
_genai = None
if settings.google_api_key:
    try:
        _genai = genai.Client(api_key=settings.google_api_key)
    except Exception as e:
        print(f"Warning: Could not initialize Google GenAI client: {e}")
        _genai = None


def generate_answer(query: str, context_blocks: List[Dict], language: str = "vi") -> str:
    if not _genai:
        raise RuntimeError("GOOGLE_API_KEY (or GEMINI_API_KEY) not set")

    # Build a compact prompt with guardrails
    lines = [
        "Bạn là trợ lý RAG. Trả lời NGẮN GỌN bằng tiếng %s dựa hoàn toàn vào CONTEXT dưới đây." % (
            "Việt" if language.startswith("vi") else language),
        "Nếu không đủ thông tin, nói rõ: 'Mình không tìm thấy đủ thông tin trong tài liệu.'",
        "Luôn kèm mục 'Nguồn' với [doc_id:chunk] đã dùng.",
        "\n---\nCONTEXT:"
    ]
    for b in context_blocks:
        src = b.get("meta", {})
        tag = f"[{src.get('document_id')}:{src.get('chunk_index')}]"
        ttl = src.get("title") or src.get("source") or ""
        lines.append(f"- {tag} {ttl} → {b['text']}")
    lines.append("\n---\nCÂU HỎI: " + query)

    resp = _genai.models.generate_content(
        model=settings.gemini_model,
        contents="\n".join(lines),
        config={"temperature": 0.2}
    )
    # New SDK returns object with .text
    return getattr(resp, "text", str(resp))
```

### 🔍 `api/app/retrieval.py` - Hybrid Search

```python
from typing import List, Dict, Tuple
from .db import get_conn
from .llm import embed_texts

# Cosine distance operator `<=>` in pgvector; we created a HNSW index with vector_cosine_ops


def _vector_candidates(q_vec: List[float], limit: int = 40) -> List[Dict]:
    vec_literal = "[" + ",".join(f"{x:.6f}" for x in q_vec) + "]"
    sql = f"""
        SELECT id, document_id, chunk_index, content,
        1.0 - (embedding <=> %s::vector) AS score
        FROM chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (vec_literal, vec_literal, limit)).fetchall()
    return [
        {
            "id": r[0],
            "document_id": r[1],
            "chunk_index": r[2],
            "text": r[3],
            "score": float(r[4]),
            "meta": {"document_id": r[1], "chunk_index": r[2]}
        }
        for r in rows
    ]


def _keyword_candidates(query: str, limit: int = 20) -> List[Dict]:
    # Try full-text first; fallback to trigram similarity
    sql_fts = """
        SELECT id, document_id, chunk_index, content, ts_rank(content_tsv, plainto_tsquery('simple', %s)) AS score
        FROM chunks
        WHERE content_tsv @@ plainto_tsquery('simple', %s)
        ORDER BY score DESC
        LIMIT %s
    """
    with get_conn() as conn:
        rows = conn.execute(sql_fts, (query, query, limit)).fetchall()
        if not rows:
            sql_trgm = """
            SELECT id, document_id, chunk_index, content, similarity(content, %s) AS score
            FROM chunks
            WHERE content ILIKE %s
            ORDER BY score DESC
            LIMIT %s
            """
            rows = conn.execute(
                sql_trgm, (query, f'%{query}%', limit)).fetchall()
    return [
        {
            "id": r[0],
            "document_id": r[1],
            "chunk_index": r[2],
            "text": r[3],
            "score": float(r[4] or 0.0),
            "meta": {"document_id": r[1], "chunk_index": r[2]}
        }
        for r in rows
    ]


def hybrid_search(query: str, k_vec: int = 60, k_kw: int = 30) -> List[Dict]:
    # 1) vector
    q_vec = embed_texts([query])[0]
    vec_hits = _vector_candidates(q_vec, limit=k_vec)
    # 2) keyword
    kw_hits = _keyword_candidates(query, limit=k_kw)

    # Merge & de-duplicate by chunk id, keep max score
    seen = {}
    for item in vec_hits + kw_hits:
        if item["id"] not in seen or item["score"] > seen[item["id"]]["score"]:
            seen[item["id"]] = item
    return list(seen.values())


# vec_hits = [
#   {"id": 1, "document_id": 10, "chunk_index": 0, "text": "Đoạn A (vector)", "score": 0.70, "meta": {"document_id":10,"chunk_index":0}},
#   {"id": 2, "document_id": 11, "chunk_index": 3, "text": "Đoạn B", "score": 0.60, "meta": {"document_id":11,"chunk_index":3}},
# ]

# kw_hits = [
#   {"id": 1, "document_id": 10, "chunk_index": 0, "text": "Đoạn A (keyword match)", "score": 0.90, "meta": {"document_id":10,"chunk_index":0}},  # duplicate id=1 với score cao hơn
#   {"id": 3, "document_id": 12, "chunk_index": 2, "text": "Đoạn C", "score": 0.50, "meta": {"document_id":12,"chunk_index":2}},
# ]

# === Final result ===
# result = [
#   {"id": 1, "document_id": 10, "chunk_index": 0, "text": "Đoạn A (keyword match)", "score": 0.90, "meta": {"document_id":10,"chunk_index":0}},
#   {"id": 2, "document_id": 11, "chunk_index": 3, "text": "Đoạn B", "score": 0.60, "meta": {"document_id":11,"chunk_index":3}},
#   {"id": 3, "document_id": 12, "chunk_index": 2, "text": "Đoạn C", "score": 0.50, "meta": {"document_id":12,"chunk_index":2}},
# ]
```

### 🧪 `api/test_pdf.py` - PDF Testing Tool

```python
#!/usr/bin/env python3
"""
PDF Processing Test Tool
Test OCR and text extraction on specific PDF files

Usage:
  python test_pdf.py <filename>          # Test specific file
  python test_pdf.py                     # List available PDFs
  docker compose exec api python test_pdf.py <filename>
"""

from app.pdf_processor import pdf_processor
import sys
import pathlib
sys.path.insert(0, '/app')


def list_available_pdfs():
    """List all PDF files in data directory"""
    data_dir = pathlib.Path("/data")
    pdfs = list(data_dir.glob("*.pdf"))

    if not pdfs:
        print("❌ No PDF files found in /data")
        return

    print("📚 Available PDF files:")
    for i, pdf in enumerate(pdfs, 1):
        size_kb = pdf.stat().st_size / 1024
        print(f"  {i}. {pdf.name} ({size_kb:.1f} KB)")


def test_pdf_processing(pdf_filename):
    """Test PDF processing with detailed output"""
    pdf_path = pathlib.Path(f"/data/{pdf_filename}")

    if not pdf_path.exists():
        print(f"❌ File not found: {pdf_path}")
        print("\nTip: Use 'python test_pdf.py' to list available files")
        return False

    print(f"🔍 Testing PDF processing for: {pdf_filename}")
    print(f"📄 File size: {pdf_path.stat().st_size / 1024:.1f} KB")

    # Check system capabilities
    caps = pdf_processor.get_capabilities()
    print(f"🛠️ System capabilities:")
    for key, value in caps.items():
        status = "✅" if value else "❌"
        print(f"   {status} {key}: {value}")

    # Test extraction
    print(f"\n⏳ Starting text extraction...")
    try:
        text = pdf_processor.extract_text(pdf_path)

        if text.strip():
            print(f"✅ SUCCESS!")
            print(f"📊 Extracted {len(text)} characters")

            # Count lines and words
            lines = len(text.splitlines())
            words = len(text.split())
            print(f"📈 Statistics: {lines} lines, {words} words")

            print(f"\n📄 Content preview (first 500 chars):")
            print("=" * 60)
            print(text[:500] + ("..." if len(text) > 500 else ""))
            print("=" * 60)

            return True
        else:
            print(f"❌ No text extracted")
            return False

    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        return False


if __name__ == "__main__":
    print("🔧 PDF Processing Test Tool")
    print("=" * 40)

    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
        success = test_pdf_processing(pdf_file)
        sys.exit(0 if success else 1)
    else:
        list_available_pdfs()
        print("\nUsage: python test_pdf.py <filename>")
        sys.exit(0)
```

---

**Dự án này cung cấp foundation vững chắc cho RAG system với Vietnamese support, sẵn sàng scale và mở rộng tính năng.**
