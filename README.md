# RAG Skeleton

## Prerequisites

- Docker & Docker Compose
- API keys for:
  - OpenAI
  - Cohere
  - Google Gemini

## 1. Clone and prepare

```bash
cp .env.example .env
# Fill in your keys
```

## 2. Start services

```bash
docker compose up -d --build
```

## 3. Put docs

Drop your PDFs/TXT/MD into `./data/`

## 4. Ingest

```bash
docker compose exec api python -m app.ingest /data
```

## 5. Ask

```bash
curl -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query": "Tài liệu này nói gì về bảo mật dữ liệu?", "rerank_top_n": 8}'
```

---

## Notes

- Embedding model dims are set for text-embedding-3-small (1536). If you change models/dims, update the SQL schema accordingly.
- Keyword search uses basic Postgres FTS (dictionary simple) and trigram fallback for Vietnamese.
- If `COHERE_API_KEY` is not set, the pipeline will skip reranking.
- If `GOOGLE_API_KEY` is not set, `/ask` will error (generation required).

---

## Tips to extend

- Add auth & rate limiting.
- Persist chat history per user and re‑rank with conversation context.
- Add RAG evaluation (RAGAS) and telemetry.
- Support DOCX/HTML with `python-docx`/`readability-lxml`.
- Switch to SQLAlchemy + Alembic for migrations if you scale.
