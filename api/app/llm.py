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
