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
