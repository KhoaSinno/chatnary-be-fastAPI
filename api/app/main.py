from fastapi import FastAPI, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import orjson
from .settings import settings
from .retrieval import _keyword_candidates_for_user, hybrid_search, hybrid_search_for_user
from .llm import rerank, generate_answer
from .db import get_conn
from .pdf_processor import pdf_processor

app = FastAPI(title="RAG Skeleton")

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def get_current_user_id(x_user_id: int | None = Header(default=None, alias="X-User-Id")) -> int:
    return x_user_id or 1


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
def ask(req: AskRequest, user_id: int = Depends(get_current_user_id)):
    candidates = hybrid_search_for_user(
        req.query, user_id, k_vec=req.k_vector, k_kw=req.k_keyword)

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

    top_rerank = max(req.rerank_top_n * 2, 16)  # at least 16
    # Prepare docs for rerank
    docs = [{"text": c["text"], "meta": c.get("meta", {})} for c in candidates]
    # Call rerank
    reranked = rerank(req.query, docs, top_n=top_rerank)
    # limit top context at least 8
    top_context = min(req.rerank_top_n, 8)
    final_context = reranked[:top_context]
    # Call LLM to generate answer
    answer = generate_answer(req.query, final_context,
                             language=req.answer_language)

    # expose minimal source info
    sources = [
        {
            "document_id": d["meta"].get("document_id"),
            "chunk_index": d["meta"].get("chunk_index"),
            "title": d["meta"].get("title"),
            "source": d["meta"].get("source"),
            "preview": d["text"][:240]
        }
        for d in final_context
    ]
    return AskResponse(answer=answer, sources=sources)


@app.get("/documents/suggest")
def suggest(q: str = Query(min_length=1), user_id: int = Depends(get_current_user_id)):
    sql = """
      SELECT d.id, d.title
      FROM documents d
      WHERE d.owner_id = %s
        AND d.title ILIKE %s
      ORDER BY similarity(d.title, %s) DESC, d.title ASC
      LIMIT 8
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (user_id, f'%{q}%', q)).fetchall()
    return [{"id": r[0], "title": r[1]} for r in rows]


@app.get("/documents/search")
def search_docs(q: str = Query(min_length=1), user_id: int = Depends(get_current_user_id)):
    # Dùng keyword_candidates_for_user để có preview từ chunk
    hits = _keyword_candidates_for_user(q, user_id, limit=20)
    # gộp theo document, lấy preview đầu
    out = {}
    for h in hits:
        did = h["document_id"]
        if did not in out:
            out[did] = {"document_id": did, "preview": h["text"]
                        [:280], "chunks": [h["meta"]["chunk_index"]]}
        else:
            if len(out[did]["chunks"]) < 3:
                out[did]["chunks"].append(h["meta"]["chunk_index"])
    # thêm title/source
    with get_conn() as conn:
        meta = conn.execute(
            "SELECT id, title, source FROM documents WHERE id = ANY(%s)", (list(out.keys()),)).fetchall()
    for (did, title, source) in meta:
        out[did].update({"title": title, "source": source})
    return list(out.values())


@app.get("/documents/{doc_id}/preview")
def preview_doc(doc_id: int, user_id: int = Depends(get_current_user_id)):
    # trả text preview nhanh từ vài chunk đầu tiên
    sql = """
      SELECT c.content
      FROM chunks c
      JOIN documents d ON d.id = c.document_id
      WHERE c.document_id = %s AND d.owner_id = %s
      ORDER BY c.chunk_index ASC
      LIMIT 3
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (doc_id, user_id)).fetchall()
    text = "\n\n".join(r[0] for r in rows) if rows else ""
    return {"document_id": doc_id, "preview": text[:2000]}


@app.get("/capabilities")
def get_capabilities():
    """Check PDF processing capabilities"""
    return {
        "pdf_processing": pdf_processor.get_capabilities(),
        "database": "connected",
        "version": "2.0.0-ocr"
    }
