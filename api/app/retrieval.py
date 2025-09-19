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


def hybrid_search(query: str, k_vec: int = 30, k_kw: int = 30) -> List[Dict]:
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
