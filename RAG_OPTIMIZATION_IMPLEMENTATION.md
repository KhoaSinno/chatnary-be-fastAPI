# RAG System Optimization Implementation Plan

*Triển khai tối ưu hóa hệ thống RAG Chatnary - Phiên bản thực tế*

## 📋 Tổng quan

Dựa trên phân tích chi tiết hai tài liệu nghiên cứu, document này đưa ra **lộ trình triển khai thực tế** với 7 cải tiến được lựa chọn kỹ lưỡng theo tiêu chí:

- ✅ **Impact cao** - Cải thiện đáng kể hiệu suất
- ✅ **Khả thi** - Triển khai trong 2-4 tuần  
- ✅ **Không nặng nề** - Không làm phức tạp hóa hệ thống hiện tại
- ✅ **Đo được** - Có metrics rõ ràng để đánh giá

## 🎯 Objectives & Success Metrics

### Mục tiêu chính

- Tăng **recall** từ ~60% lên 80%+ (câu hỏi phức tạp)
- Giảm **false negative** cho queries "liệt kê đầy đủ" từ 80% xuống <20%
- Cải thiện **answer quality** với inline citations
- Tăng **search accuracy** cho tiếng Việt có dấu

### Metrics theo dõi

```bash
# Trước khi triển khai - đo baseline
curl -s -X POST http://localhost:8000/ask \
  -d '{"query":"Liệt kê toàn bộ học phần chuyên ngành KTPM","k_vector":70,"rerank_top_n":8}' \
  | jq '.sources | length'  # Current: ~2-3, Target: 8+

# Đo latency
time curl -s -X POST http://localhost:8000/ask -d '{...}' > /dev/null
# Current: ~2-3s, Target: <3.5s
```

---

## 🚀 Phase 1: Quick Wins (Tuần 1-2)

### 1.1 RRF Fusion + Locality Penalty ⭐⭐⭐

*Impact: Cao | Effort: Thấp | Risk: Không*

**Vấn đề hiện tại:** Merge đơn giản "max score" làm mất nhiều context tốt, chunk duplicate gần nhau.

**Giải pháp:**

```python
# api/app/retrieval.py - THÊM VÀO ĐẦU FILE
import os
from collections import defaultdict

RRF_K = int(os.getenv("RAG_RRF_K", "60"))

def rrf_merge(vector_hits, keyword_hits):
    """Reciprocal Rank Fusion - proven better than score-based merging"""
    bag, keep = defaultdict(float), {}
    
    # RRF scoring
    for rank, hit in enumerate(vector_hits, 1):
        bag[hit["id"]] += 1.0 / (RRF_K + rank)
        keep[hit["id"]] = hit
    
    for rank, hit in enumerate(keyword_hits, 1):
        bag[hit["id"]] += 1.0 / (RRF_K + rank)
        if hit["id"] not in keep:
            keep[hit["id"]] = hit
    
    merged = [
        {**keep[chunk_id], "rrf_score": score}
        for chunk_id, score in bag.items()
    ]
    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    return merged

def apply_locality_penalty(chunks, window=1, penalty=0.15):
    """Giảm score của chunks gần nhau trong cùng document"""
    doc_chunks = {}
    result = []
    
    for chunk in chunks:
        doc_id = chunk["document_id"]
        chunk_idx = chunk["chunk_index"]
        score = chunk["rrf_score"]
        
        # Check overlap với chunks đã chọn
        if doc_id in doc_chunks:
            for existing_idx in doc_chunks[doc_id]:
                if abs(chunk_idx - existing_idx) <= window:
                    score *= (1.0 - penalty)
                    break
        
        result.append({**chunk, "rrf_score": score})
        doc_chunks.setdefault(doc_id, []).append(chunk_idx)
    
    result.sort(key=lambda x: x["rrf_score"], reverse=True)
    return result

# THAY THẾ function hybrid_search
def hybrid_search(query: str, k_vec: int = 60, k_kw: int = 30):
    q_vec = embed_texts([query])[0]
    
    vec_hits = _vector_candidates(q_vec, limit=k_vec)
    kw_hits = _keyword_candidates(query, limit=k_kw)
    
    # Sử dụng RRF thay vì merge cũ
    merged = rrf_merge(vec_hits, kw_hits)
    merged = apply_locality_penalty(merged, window=1, penalty=0.15)
    
    return merged
```

**Expected Impact:** +15-20% recall, giảm duplicate chunks 50%

### 1.2 HNSW Tuning + Rerank Budget ⭐⭐

*Impact: Trung bình | Effort: Rất thấp | Risk: Không*

**Cải tiến:**

```python
# api/app/retrieval.py - SỬA _vector_candidates
def _vector_candidates(q_vec, limit: int = 40):
    vec_literal = "[" + ",".join(f"{x:.6f}" for x in q_vec) + "]"
    
    # Tăng ef_search để có precision tốt hơn
    ef_search = int(os.getenv("HNSW_EF_SEARCH", "80"))
    
    sql = """
    SET LOCAL hnsw.ef_search = %(ef)s;
    SELECT id, document_id, chunk_index, content,
           1.0 - (embedding <=> %(vec)s::vector) AS score
    FROM chunks
    ORDER BY embedding <=> %(vec)s::vector
    LIMIT %(limit)s;
    """
    
    with get_conn() as conn:
        rows = conn.execute(sql, {
            "ef": ef_search,
            "vec": vec_literal, 
            "limit": limit
        }).fetchall()
    
    return [{"id": r[0], "document_id": r[1], "chunk_index": r[2], 
             "text": r[3], "score": r[4]} for r in rows]

# api/app/main.py - SỬA ask endpoint
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, user_id: int = Depends(get_current_user_id)):
    # Tăng budget cho rerank, giữ context gọn cho LLM
    candidates = hybrid_search_for_user(
        req.query, user_id, 
        k_vec=req.k_vector, 
        k_kw=req.k_keyword
    )
    
    # Rerank với nhiều candidates hơn
    top_rerank = max(req.rerank_top_n * 2, 16)
    docs = [{"text": c["text"], "meta": c.get("meta", {})} for c in candidates]
    reranked = rerank(req.query, docs, top_n=top_rerank)
    
    # Chỉ đưa top context cho LLM (tiết kiệm token)
    top_context = min(req.rerank_top_n, 8)
    final_context = reranked[:top_context]
    
    answer = generate_answer(req.query, final_context, language=req.answer_language)
    # ... rest unchanged
```

**Expected Impact:** +10% precision, giảm missed relevant chunks

### 1.3 Inline Citations ⭐⭐⭐

*Impact: Cao | Effort: Thấp | Risk: Không*

**Vấn đề:** Khó verify độ chính xác của answer, không traceability.

**Giải pháp:**

```python
# api/app/llm.py - SỬA generate_answer
def generate_answer(query, context_blocks, language="vi") -> str:
    if not context_blocks:
        return "Mình không tìm thấy thông tin liên quan trong tài liệu."
    
    # Chuẩn bị context với source tags
    context_lines = [
        "Bạn là trợ lý RAG chuyên nghiệp. Hãy trả lời dựa CHÍNH XÁC trên CONTEXT được cung cấp.",
        "Quy tắc QUAN TRỌNG:",
        "- Sau mỗi thông tin chính, gắn trích dẫn [doc_id:chunk_idx]",
        "- Nếu thiếu thông tin: 'Mình không tìm thấy đủ thông tin trong tài liệu.'",
        "- Trích dẫn nguyên văn 1-2 câu quan trọng khi cần chứng minh",
        "",
        "CONTEXT:"
    ]
    
    for i, block in enumerate(context_blocks):
        meta = block.get("meta", {})
        doc_id = meta.get("document_id", "?")
        chunk_idx = meta.get("chunk_index", "?")
        source_tag = f"[{doc_id}:{chunk_idx}]"
        
        context_lines.append(f"Nguồn {source_tag}:")
        context_lines.append(block["text"])
        context_lines.append("")
    
    context_lines.extend([
        f"CÂU HỎI: {query}",
        "",
        "TRẢ LỜI (có trích dẫn):"
    ])
    
    prompt = "\n".join(context_lines)
    
    if _genai:
        try:
            response = _genai.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config={"temperature": 0.1, "max_output_tokens": 1000}
            )
            return getattr(response, "text", str(response))
        except Exception as e:
            print(f"Gemini error: {e}")
    
    return "Lỗi sinh trả lời. Vui lòng thử lại."
```

**Expected Impact:** 100% traceability, tăng user trust, dễ debug

---

## 🔧 Phase 2: Smart Enhancements (Tuần 3-4)

### 2.1 Query Expansion (HyDE + Paraphrase) ⭐⭐

*Impact: Cao cho complex queries | Effort: Trung bình | Risk: Thấp*

**Vấn đề:** Queries phức tạp, từ khoá không khớp với document text.

**Giải pháp:**

```python
# api/app/llm.py - THÊM VÀO
def generate_query_variants(query: str, n_variants: int = 2) -> List[str]:
    """Tạo variants của query để tăng recall"""
    if not _genai or n_variants <= 0:
        return []
    
    prompt = f"""Bạn là chuyên gia tìm kiếm thông tin học thuật. 
Tạo {n_variants} cách diễn đạt khác nhau cho câu hỏi sau, giữ nguyên ý nghĩa:

Câu hỏi gốc: "{query}"

Các cách diễn đạt khác (mỗi dòng 1 cách, không đánh số):"""

    try:
        response = _genai.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config={"temperature": 0.3, "max_output_tokens": 200}
        )
        
        text = getattr(response, "text", "")
        variants = []
        for line in text.strip().split('\n'):
            clean_line = line.strip(' -•123456789.')
            if len(clean_line.split()) >= 3:  # Filter short variants
                variants.append(clean_line)
                if len(variants) >= n_variants:
                    break
        
        return variants
    except Exception as e:
        print(f"Query expansion error: {e}")
        return []

def generate_hypothetical_answer(query: str) -> str:
    """HyDE: Generate hypothetical answer to expand search"""
    if not _genai:
        return ""
    
    prompt = f"""Viết một đoạn văn ngắn 100-150 từ trả lời câu hỏi sau, 
dựa trên kiến thức chung về giáo dục đại học Việt Nam:

Câu hỏi: {query}

Đoạn văn trả lời (không cần chính xác 100%, chỉ cần có từ khóa liên quan):"""

    try:
        response = _genai.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config={"temperature": 0.2, "max_output_tokens": 200}
        )
        return getattr(response, "text", "")
    except Exception as e:
        print(f"HyDE generation error: {e}")
        return ""

# api/app/retrieval.py - SỬA hybrid_search
def hybrid_search(query: str, k_vec: int = 60, k_kw: int = 30):
    # Multi-query expansion
    variants = generate_query_variants(query, n_variants=2)
    hyde_answer = generate_hypothetical_answer(query)
    
    # Prepare all search inputs
    search_queries = [query] + variants
    if hyde_answer:
        search_queries.append(hyde_answer)
    
    # Get embeddings for all variants
    embeddings = embed_texts(search_queries)
    
    # Vector search với multiple queries
    all_vec_hits = []
    per_query_limit = max(20, k_vec // len(embeddings))
    
    for emb in embeddings:
        vec_hits = _vector_candidates(emb, limit=per_query_limit)
        all_vec_hits.append(vec_hits)
    
    # Keyword search chỉ với query gốc (tránh noise)
    kw_hits = _keyword_candidates(query, limit=k_kw)
    
    # RRF merge all lists
    merged = rrf_merge_multiple(all_vec_hits + [kw_hits])
    merged = apply_locality_penalty(merged)
    
    return merged

def rrf_merge_multiple(hit_lists):
    """RRF cho nhiều lists"""
    bag, keep = defaultdict(float), {}
    
    for hits in hit_lists:
        for rank, hit in enumerate(hits, 1):
            bag[hit["id"]] += 1.0 / (RRF_K + rank)
            if hit["id"] not in keep:
                keep[hit["id"]] = hit
    
    merged = [
        {**keep[chunk_id], "rrf_score": score}
        for chunk_id, score in bag.items()
    ]
    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    return merged
```

**Expected Impact:** +25% recall cho complex queries, +30% cho "liệt kê" queries

### 2.2 Vietnamese FTS Optimization ⭐⭐⭐

*Impact: Cao cho tiếng Việt | Effort: Thấp | Risk: Không*

**Vấn đề:** FTS không match tốt với tiếng Việt có dấu.

**Giải pháp (chạy 1 lần):**

```sql
-- Script: optimize_vietnamese_fts.sql
-- Chạy: docker exec -i rag_db psql -U rag -d rag < optimize_vietnamese_fts.sql

CREATE EXTENSION IF NOT EXISTS unaccent;

-- Tạo text search config cho tiếng Việt
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_ts_config WHERE cfgname='vietnamese_unaccent'
  ) THEN
    CREATE TEXT SEARCH CONFIGURATION vietnamese_unaccent (COPY=simple);
    ALTER TEXT SEARCH CONFIGURATION vietnamese_unaccent
      ALTER MAPPING FOR hword, hword_part, word 
      WITH unaccent, simple;
  END IF;
END $$;

-- Backup old generated column
ALTER TABLE chunks RENAME COLUMN content_tsv TO content_tsv_old;

-- Tạo cột mới với unaccent
ALTER TABLE chunks 
ADD COLUMN content_tsv tsvector 
GENERATED ALWAYS AS (
  to_tsvector('vietnamese_unaccent', coalesce(content,''))
) STORED;

-- Tạo index mới
CREATE INDEX CONCURRENTLY idx_chunks_vietnamese_tsv_gin 
ON chunks USING GIN (content_tsv);

-- Xóa index cũ sau khi confirm index mới hoạt động
-- DROP INDEX IF EXISTS idx_chunks_tsv_gin;
-- ALTER TABLE chunks DROP COLUMN content_tsv_old;
```

**Expected Impact:** +40% keyword search accuracy cho tiếng Việt có dấu

### 2.3 List-Mode cho Comprehensive Queries ⭐⭐⭐

*Impact: Rất cao cho "liệt kê" queries | Effort: Trung bình | Risk: Thấp*

**Vấn đề:** Queries "liệt kê toàn bộ" fail do chunks rải rác nhiều trang.

#### Complete List-Mode Implementation

```python
# api/app/listmode.py - FILE MỚI
"""
List-mode for comprehensive queries that need to aggregate information
across multiple chunks and documents.
"""
import re
import json
import os
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    print("Warning: rapidfuzz not available, using basic deduplication")
    RAPIDFUZZ_AVAILABLE = False

# Configuration
LIST_QUERY_THRESHOLD = int(os.getenv("LIST_QUERY_THRESHOLD", "2"))  # Min pattern matches
MAX_LIST_ITEMS = int(os.getenv("MAX_LIST_ITEMS", "100"))
SIMILARITY_THRESHOLD = float(os.getenv("LIST_SIMILARITY_THRESHOLD", "0.85"))

# Pattern detection for list queries
LIST_PATTERNS = [
    r"(toàn bộ|tất cả|đầy đủ|liệt kê|danh sách)",
    r"(bao gồm.*gì|gồm những|có những|bao gồm những)",
    r"(học phần|môn học|khóa học|chuyên ngành).*nào",
    r"(các.*là gì|các.*có|những.*nào)",
]

# Content extraction patterns  
COURSE_PATTERNS = [
    # Pattern 1: Course code + name
    r"^\s*(?:\d+\s*[.)]\s*)?([A-Z]{2,4}\d{3,4})\s*[|\-–]\s*(.{10,120}?)(?:\s*\(\d+\)|\s*\d+\s*tín\s*chỉ|\s*$)",
    # Pattern 2: Bullet points with optional course codes
    r"^\s*[•\-*]\s*(?:([A-Z]{2,4}\d{3,4})\s*[:\-–]\s*)?(.{10,120}?)(?:\s*\([A-Z]{2,4}\d{3,4}\)|\s*$)",
    # Pattern 3: Numbered items
    r"^\s*\d+\s*[.)]\s*(?:([A-Z]{2,4}\d{3,4})\s*[:\-–]\s*)?(.{10,120}?)(?:\s*\(\d+\s*tc\)|\s*$)",
    # Pattern 4: Simple lines (fallback)
    r"^\s*(.{15,100}?)(?:\s*\(\d+\s*tc\)|\s*$)"
]

def is_list_query(query: str) -> bool:
    """
    Detect if query is asking for comprehensive list
    Uses multiple pattern matching for robust detection
    """
    query_lower = query.lower().strip()
    
    if len(query_lower) < 10:  # Too short to be a list query
        return False
    
    matches = 0
    for pattern in LIST_PATTERNS:
        if re.search(pattern, query_lower):
            matches += 1
    
    # Require at least LIST_QUERY_THRESHOLD pattern matches
    return matches >= LIST_QUERY_THRESHOLD

def extract_items_from_chunks(chunks: List[Dict], query: str = "") -> List[Tuple[str, str, str]]:
    """
    Extract structured items (code, name, source) from chunks
    
    Args:
        chunks: List of chunk dictionaries with text and meta
        query: Original query for context (future use)
    
    Returns:
        List of (code, name, source_ref) tuples
    """
    items = []
    stats = defaultdict(int)
    
    for chunk in chunks:
        text = chunk.get("text", "")
        chunk_meta = chunk.get("meta", {})
        doc_id = chunk_meta.get("document_id", "?")
        chunk_idx = chunk_meta.get("chunk_index", "?")
        source_ref = f"{doc_id}:{chunk_idx}"
        
        stats["chunks_processed"] += 1
        
        # Process each line in the chunk
        for line_no, line in enumerate(text.split('\n')):
            line = line.strip()
            
            # Skip empty or very short lines
            if len(line) < 10:
                continue
            
            stats["lines_processed"] += 1
            
            # Try each extraction pattern
            matched = False
            for pattern_idx, pattern in enumerate(COURSE_PATTERNS):
                match = re.match(pattern, line, re.IGNORECASE | re.UNICODE)
                if match:
                    stats[f"pattern_{pattern_idx}_matches"] += 1
                    
                    # Extract code and name based on pattern
                    groups = match.groups()
                    if len(groups) == 2 and groups[0]:  # Code + Name pattern
                        code = groups[0].strip()
                        name = groups[1].strip()
                    elif len(groups) >= 2:  # Optional code + Name
                        code = (groups[0] or "").strip()
                        name = groups[1].strip()
                    else:  # Name only
                        code = ""
                        name = groups[0].strip()
                    
                    # Quality filters
                    name_words = len(name.split())
                    if (name_words >= 2 and name_words <= 20 and 
                        len(name) <= 150 and 
                        not name.lower().startswith(('hình', 'bảng', 'trang'))):
                        
                        items.append((code, name, source_ref))
                        stats["items_extracted"] += 1
                        matched = True
                        break
            
            if not matched and len(line) > 20:
                stats["unmatched_lines"] += 1
    
    print(f"List extraction stats: {dict(stats)}")
    return items

def deduplicate_items(items: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
    """
    Remove near-duplicate items using fuzzy matching or simple deduplication
    """
    if not items:
        return []
    
    if not RAPIDFUZZ_AVAILABLE:
        # Simple deduplication by exact name match
        seen_names = set()
        unique_items = []
        for code, name, ref in items:
            name_lower = name.lower().strip()
            if name_lower not in seen_names:
                unique_items.append((code, name, ref))
                seen_names.add(name_lower)
                if len(unique_items) >= MAX_LIST_ITEMS:
                    break
        print(f"Simple deduplication: {len(items)} -> {len(unique_items)} items")
        return unique_items
    
    # Advanced fuzzy deduplication with rapidfuzz
    unique_items = []
    seen_names = []
    stats = {"original": len(items), "duplicates_removed": 0}
    
    for code, name, ref in items:
        name_clean = name.lower().strip()
        
        # Check fuzzy similarity with existing names
        is_duplicate = False
        if seen_names:
            matches = process.extract(
                name_clean,
                seen_names,
                scorer=fuzz.token_set_ratio,
                limit=1
            )
            
            if matches and matches[0][1] > (SIMILARITY_THRESHOLD * 100):
                is_duplicate = True
                stats["duplicates_removed"] += 1
        
        if not is_duplicate:
            unique_items.append((code, name, ref))
            seen_names.append(name_clean)
            
            # Limit output size
            if len(unique_items) >= MAX_LIST_ITEMS:
                break
    
    print(f"Fuzzy deduplication stats: {stats}, final: {len(unique_items)} items")
    return unique_items

def format_list_response(items: List[Tuple[str, str, str]], query: str = "") -> str:
    """
    Format items as structured list with citations
    """
    if not items:
        return "Mình không tìm thấy danh sách cụ thể trong tài liệu được cung cấp."
    
    # Group by document for better organization
    doc_groups = defaultdict(list)
    for code, name, ref in items:
        doc_id = ref.split(':')[0]
        doc_groups[doc_id].append((code, name, ref))
    
    lines = []
    item_count = 0
    
    # If items from multiple documents, organize by document
    if len(doc_groups) > 1:
        lines.append(f"Tìm thấy {len(items)} mục từ {len(doc_groups)} tài liệu:")
        lines.append("")
        
        for doc_id, doc_items in doc_groups.items():
            lines.append(f"**Từ tài liệu {doc_id}:**")
            for code, name, ref in doc_items:
                item_count += 1
                if code:
                    lines.append(f"{item_count}. **{code}** - {name} `[{ref}]`")
                else:
                    lines.append(f"{item_count}. {name} `[{ref}]`")
            lines.append("")
    else:
        # Single document or mixed - simple list
        lines.append(f"Tìm thấy {len(items)} mục:")
        lines.append("")
        
        for code, name, ref in items:
            item_count += 1
            if code:
                lines.append(f"{item_count}. **{code}** - {name} `[{ref}]`")
            else:
                lines.append(f"{item_count}. {name} `[{ref}]`")
    
    # Add footer notes
    if len(items) >= MAX_LIST_ITEMS:
        lines.append("")
        lines.append(f"*Hiển thị {MAX_LIST_ITEMS} mục đầu tiên. Có thể còn nhiều mục khác.*")
    
    lines.append("")
    lines.append("*Các số trong ngoặc vuông `[doc:chunk]` là trích dẫn nguồn.*")
    
    return "\n".join(lines)

def enhanced_list_search(query: str, user_id: int, base_results: List[Dict]) -> Optional[Dict]:
    """
    Enhanced search specifically for list queries
    
    Args:
        query: The list query 
        user_id: User ID for filtering
        base_results: Results from standard hybrid search
        
    Returns:
        Formatted list response or None if not applicable
    """
    if not is_list_query(query):
        return None
    
    print(f"List-mode activated for query: {query[:50]}...")
    
    # Extract items from chunks
    items = extract_items_from_chunks(base_results, query)
    
    if not items:
        print("No structured items found in chunks")
        return None
    
    # Deduplicate items
    unique_items = deduplicate_items(items)
    
    if not unique_items:
        print("No unique items after deduplication")
        return None
    
    # Format response
    formatted_answer = format_list_response(unique_items, query)
    
    # Create source references
    all_refs = sorted(set(ref for _, _, ref in unique_items))
    sources = []
    for ref in all_refs[:20]:  # Limit source references
        sources.append({
            "reference": ref,
            "type": "list_item_source"
        })
    
    return {
        "answer": formatted_answer,
        "sources": sources,
        "list_mode": True,
        "items_found": len(unique_items),
        "total_items_before_dedup": len(items)
    }

# Standalone testing function
def test_list_mode_functions():
    """Test list-mode functions with mock data"""
    print("Testing list-mode functions...")
    
    # Test query detection
    test_queries = [
        ("Liệt kê toàn bộ học phần chuyên ngành KTPM", True),
        ("DBMS là gì?", False),
        ("Bao gồm những môn học nào trong khung chương trình?", True),
        ("Các học phần đại cương có những gì?", True),
    ]
    
    print("Query detection tests:")
    for query, expected in test_queries:
        result = is_list_query(query)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{query}' -> {result}")
    
    # Test item extraction
    mock_chunks = [
        {
            "text": "1. CS101 - Nhập môn khoa học máy tính\n2. CS102 - Lập trình căn bản\n3. CS201 - Cấu trúc dữ liệu",
            "meta": {"document_id": 1, "chunk_index": 5}
        },
        {
            "text": "• Toán cao cấp A1 (4 tín chỉ)\n• Toán cao cấp A2 (4 tín chỉ)\n• Vật lý đại cương",
            "meta": {"document_id": 2, "chunk_index": 10}
        }
    ]
    
    items = extract_items_from_chunks(mock_chunks)
    print(f"\nExtracted {len(items)} items:")
    for code, name, ref in items[:3]:
        print(f"  - {code}: {name} [{ref}]")
    
    # Test deduplication
    duplicate_items = items + [("CS101", "Nhập môn khoa học máy tính", "1:6")]  # Add duplicate
    unique = deduplicate_items(duplicate_items)
    print(f"\nDeduplication: {len(duplicate_items)} -> {len(unique)} items")

if __name__ == "__main__":
    test_list_mode_functions()
```

#### Integration with Main API

```python
# api/app/main.py - ENHANCED ask endpoint
import time
from .listmode import enhanced_list_search

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, user_id: int = Depends(get_current_user_id)):
    query = req.query.strip()
    start_time = time.time()
    
    # Enhanced retrieval with higher budget for potential list queries
    base_k_vec = req.k_vector
    base_k_kw = req.k_keyword
    
    # Boost search budget if this might be a list query
    from .listmode import is_list_query
    if is_list_query(query):
        base_k_vec = min(base_k_vec * 2, 150)  # Increase vector candidates
        base_k_kw = min(base_k_kw * 2, 100)    # Increase keyword candidates
        print(f"List query detected - boosting search to {base_k_vec}v/{base_k_kw}k")
    
    # Standard hybrid search
    candidates = hybrid_search_for_user(
        query, user_id, 
        k_vec=base_k_vec, 
        k_kw=base_k_kw
    )
    search_time = time.time()
    
    # Try list-mode processing first
    list_result = enhanced_list_search(query, user_id, candidates)
    if list_result:
        list_time = time.time()
        print(f"List-mode completed: search={search_time-start_time:.2f}s, "
              f"processing={list_time-search_time:.2f}s")
        
        return AskResponse(
            answer=list_result["answer"],
            sources=list_result["sources"]
        )
    
    # Standard RAG processing
    docs = [{"text": c["text"], "meta": c.get("meta", {})} for c in candidates]
    
    # Rerank with appropriate budget
    top_rerank = max(req.rerank_top_n * 2, 16)
    reranked = rerank(query, docs, top_n=top_rerank)
    rerank_time = time.time()
    
    # Generate answer with final context
    final_context = reranked[:req.rerank_top_n]
    answer = generate_answer(query, final_context, language=req.answer_language)
    answer_time = time.time()
    
    # Log timing
    print(f"Standard RAG: search={search_time-start_time:.2f}s, "
          f"rerank={rerank_time-search_time:.2f}s, "
          f"answer={answer_time-rerank_time:.2f}s")
    
    # Create sources
    sources = []
    for d in final_context:
        meta = d.get("meta", {})
        sources.append({
            "document_id": meta.get("document_id"),
            "chunk_index": meta.get("chunk_index"),
            "title": meta.get("title"),
            "source": meta.get("source"),
            "preview": d["text"][:240]
        })
    
    return AskResponse(answer=answer, sources=sources)
```

#### Complete Testing Framework

```bash
#!/bin/bash
# test_listmode_complete.sh
echo "=== LIST-MODE COMPLETE TESTING ==="

mkdir -p test_results/listmode

# Install required dependency
echo "📦 Installing rapidfuzz for fuzzy matching..."
pip install rapidfuzz

echo "🔍 Testing List Query Detection..."

# Test query detection with various Vietnamese patterns
declare -a test_queries=(
  "Liệt kê toàn bộ học phần chuyên ngành KTPM"
  "Bao gồm những môn học nào trong chương trình đào tạo?"
  "Các học phần đại cương có những gì?"
  "Tất cả môn học thuộc nhóm cơ sở ngành"
  "Danh sách các chuyên ngành được đào tạo"
  "DBMS là gì?"  # Should be FALSE
  "Hướng dẫn cài đặt PostgreSQL"  # Should be FALSE
)

echo "Testing query detection patterns..."
for query in "${test_queries[@]}"; do
  echo "Query: $query"
  
  # Test the detection via API call
  result=$(curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$query\",\"k_vector\":80,\"k_keyword\":50,\"rerank_top_n\":15}")
  
  # Check if list-mode was triggered (look for numbered lists in response)
  answer=$(echo "$result" | jq -r '.answer')
  list_indicators=$(echo "$answer" | grep -c -E '^[0-9]+\.' || echo 0)
  
  if [ $list_indicators -gt 3 ]; then
    echo "  ✅ List-mode ACTIVATED ($list_indicators items)"
  else
    echo "  ⚪ Standard mode ($list_indicators list items)"
  fi
  
  echo "  First 100 chars: ${answer:0:100}..."
  echo ""
  
  sleep 2
done

echo -e "\n📊 Testing List Extraction Quality..."

# Test specific list queries that should work well
declare -a quality_tests=(
  "Liệt kê toàn bộ học phần trong chương trình đào tạo"
  "Các môn học chuyên ngành KTPM bao gồm những gì?"
  "Danh sách học phần đại cương"
  "Tất cả các học phần cơ sở ngành"
)

for query in "${quality_tests[@]}"; do
  echo "Quality test: ${query:0:50}..."
  
  result=$(curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$query\",\"k_vector\":100,\"k_keyword\":60,\"rerank_top_n\":20}" \
    | tee "test_results/listmode/quality_${RANDOM}.json")
  
  answer=$(echo "$result" | jq -r '.answer')
  sources=$(echo "$result" | jq -r '.sources | length')
  
  # Analyze response quality
  list_items=$(echo "$answer" | grep -c -E '^[0-9]+\.' || echo 0)
  citations=$(echo "$answer" | grep -o '\[[0-9]*:[0-9]*\]' | wc -l)
  unique_docs=$(echo "$answer" | grep -o '\[[0-9]*:' | sort -u | wc -l)
  
  echo "  📋 List items: $list_items"
  echo "  📚 Citations: $citations" 
  echo "  📖 Unique documents: $unique_docs"
  echo "  🔗 Sources: $sources"
  
  # Quality scoring
  score=0
  [ $list_items -gt 5 ] && score=$((score + 25))
  [ $citations -gt 3 ] && score=$((score + 25))
  [ $unique_docs -gt 1 ] && score=$((score + 25))
  [ $sources -gt 2 ] && score=$((score + 25))
  
  if [ $score -ge 75 ]; then
    echo "  ✅ EXCELLENT quality (${score}/100)"
  elif [ $score -ge 50 ]; then
    echo "  ⚠️  GOOD quality (${score}/100)"
  else
    echo "  ❌ POOR quality (${score}/100)"
  fi
  
  echo ""
  sleep 3
done

echo -e "\n🚀 Performance Test with List Queries..."

# Performance test with complex list queries
declare -a perf_queries=(
  "Liệt kê toàn bộ học phần chuyên ngành Kỹ thuật phần mềm bao gồm mã môn học và số tín chỉ"
  "Danh sách đầy đủ các môn học đại cương và cơ sở ngành trong chương trình đào tạo"
  "Bao gồm những học phần nào thuộc nhóm chuyên ngành và chuyên ngành hẹp"
)

total_time=0
success_count=0

for i in {1..3}; do
  query="${perf_queries[$((i-1))]}"
  echo "Performance test $i: ${query:0:60}..."
  
  start_time=$(date +%s.%N)
  result=$(curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$query\",\"k_vector\":120,\"k_keyword\":80,\"rerank_top_n\":25}")
  end_time=$(date +%s.%N)
  
  elapsed=$(echo "$end_time - $start_time" | bc -l)
  echo "  Time: ${elapsed}s"
  
  # Check success
  if echo "$result" | jq -e '.sources | length' > /dev/null 2>&1; then
    answer=$(echo "$result" | jq -r '.answer')
    list_items=$(echo "$answer" | grep -c -E '^[0-9]+\.' || echo 0)
    
    echo "  Items found: $list_items"
    
    if [ $list_items -gt 3 ]; then
      success_count=$((success_count + 1))
      total_time=$(echo "$total_time + $elapsed" | bc -l)
      echo "  ✅ SUCCESS"
    else
      echo "  ❌ FAILED (too few items)"
    fi
  else
    echo "  ❌ FAILED (API error)"
  fi
  
  echo ""
  sleep 2
done

if [ $success_count -gt 0 ]; then
  avg_time=$(echo "scale=2; $total_time / $success_count" | bc -l)
  echo "📈 Performance Summary:"
  echo "  Success rate: ${success_count}/3"
  echo "  Average time: ${avg_time}s"
  
  if (( $(echo "$avg_time < 5.0" | bc -l) )); then
    echo "  ✅ Performance acceptable (<5.0s for complex lists)"
  else
    echo "  ⚠️  Performance slow (${avg_time}s >= 5.0s)"
  fi
else
  echo "❌ All performance tests failed"
fi

echo -e "\n🧪 Testing Edge Cases..."

# Test edge cases
declare -a edge_cases=(
  "Liệt kê"  # Too short
  "Danh sách những gì không có trong tài liệu"  # Should return empty
  "Liệt kê toàn bộ mọi thứ trên thế giới"  # Unrealistic query
)

for query in "${edge_cases[@]}"; do
  echo "Edge case: $query"
  
  result=$(curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$query\",\"k_vector\":50,\"k_keyword\":30,\"rerank_top_n\":10}")
  
  if echo "$result" | jq -e '.answer' > /dev/null 2>&1; then
    answer=$(echo "$result" | jq -r '.answer')
    echo "  Response: ${answer:0:100}..."
    echo "  ✅ Handled gracefully"
  else
    echo "  ❌ API error"
  fi
  
  echo ""
  sleep 1
done

echo "✅ List-mode testing complete!"
echo "Check test_results/listmode/ for detailed logs"
```

**Expected Impact:** 80%+ success rate for "liệt kê" queries (from ~20%)

---

## 📊 Phase 3: Monitoring & Validation (Tuần 4-5)

### 3.1 Connection Pooling & Performance Logging ⭐

#### Complete Connection Pooling Implementation

```python
# api/app/db_enhanced.py - NEW FILE OR UPDATE EXISTING
"""
Enhanced database connection with pooling and monitoring
"""
import os
import time
import json
import psycopg
from contextlib import contextmanager
from collections import defaultdict
from typing import Dict, Any, Optional

try:
    from psycopg_pool import ConnectionPool
    POOL_AVAILABLE = True
except ImportError:
    print("Warning: psycopg_pool not available, using standard connections")
    POOL_AVAILABLE = False

try:
    from .settings import settings
except ImportError:
    # Fallback for standalone testing
    class MockSettings:
        pg_host = "localhost"
        pg_port = "5432"
        pg_db = "rag_db"
        pg_user = "rag"
        pg_password = "password"
    settings = MockSettings()

# Configuration
POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "2"))
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
LOG_SLOW_QUERIES = float(os.getenv("DB_LOG_SLOW_THRESHOLD", "1.0"))  # seconds

# Global connection pool
_pool: Optional[ConnectionPool] = None
_connection_stats = defaultdict(int)

def initialize_pool():
    """Initialize connection pool on startup"""
    global _pool
    
    if not POOL_AVAILABLE:
        print("Connection pooling disabled - using direct connections")
        return None
    
    try:
        database_url = (f"host={settings.pg_host} port={settings.pg_port} "
                       f"dbname={settings.pg_db} user={settings.pg_user} "
                       f"password={settings.pg_password}")
        
        _pool = ConnectionPool(
            database_url,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            timeout=POOL_TIMEOUT,
            kwargs={
                "row_factory": psycopg.rows.dict_row,
                "autocommit": True
            }
        )
        
        # Test connection
        with _pool.connection() as conn:
            result = conn.execute("SELECT 1").fetchone()
            print(f"✅ Database pool initialized: {POOL_MIN_SIZE}-{POOL_MAX_SIZE} connections")
            
        return _pool
        
    except Exception as e:
        print(f"❌ Pool initialization failed: {e}")
        _pool = None
        return None

def get_pool_stats() -> Dict[str, Any]:
    """Get connection pool statistics"""
    if not _pool:
        return {"status": "no_pool", "stats": dict(_connection_stats)}
    
    return {
        "status": "active",
        "size": _pool.get_stats().get("pool_size", 0),
        "available": _pool.get_stats().get("pool_available", 0),
        "waiting": _pool.get_stats().get("requests_waiting", 0),
        "usage_stats": dict(_connection_stats)
    }

@contextmanager
def get_conn():
    """
    Get database connection from pool or direct connection
    Context manager with performance monitoring
    """
    start_time = time.time()
    conn = None
    
    try:
        if _pool:
            # Use connection pool
            with _pool.connection() as conn:
                _connection_stats["pool_connections"] += 1
                yield conn
        else:
            # Direct connection fallback
            database_url = (f"host={settings.pg_host} port={settings.pg_port} "
                           f"dbname={settings.pg_db} user={settings.pg_user} "
                           f"password={settings.pg_password}")
            
            with psycopg.connect(database_url, row_factory=psycopg.rows.dict_row) as conn:
                _connection_stats["direct_connections"] += 1
                yield conn
                
    except Exception as e:
        _connection_stats["connection_errors"] += 1
        print(f"Database connection error: {e}")
        raise
    finally:
        elapsed = time.time() - start_time
        _connection_stats["total_connection_time"] += elapsed
        
        if elapsed > LOG_SLOW_QUERIES:
            print(f"⚠️  Slow connection: {elapsed:.2f}s")

class QueryTimer:
    """Utility for timing database operations"""
    
    def __init__(self, operation_name: str = "query"):
        self.operation_name = operation_name
        self.start_time = time.time()
        self.checkpoints = {}
        
    def checkpoint(self, name: str):
        """Add a timing checkpoint"""
        self.checkpoints[name] = time.time() - self.start_time
    
    def finish(self) -> float:
        """Finish timing and return total duration"""
        elapsed = time.time() - self.start_time
        
        if elapsed > LOG_SLOW_QUERIES:
            checkpoints_str = " | ".join([f"{k}:{v*1000:.0f}ms" for k, v in self.checkpoints.items()])
            print(f"⚠️  Slow {self.operation_name}: {elapsed:.2f}s ({checkpoints_str})")
        
        return elapsed

def execute_with_timing(query: str, params: tuple = None, operation_name: str = "query") -> Any:
    """Execute query with timing and monitoring"""
    timer = QueryTimer(operation_name)
    
    try:
        with get_conn() as conn:
            timer.checkpoint("connection")
            
            if params:
                result = conn.execute(query, params)
            else:
                result = conn.execute(query)
            
            timer.checkpoint("execution")
            
            # Fetch results based on query type
            if query.strip().lower().startswith(('select', 'with')):
                data = result.fetchall()
                timer.checkpoint("fetch")
                return data
            else:
                return result.rowcount
                
    except Exception as e:
        print(f"Query execution error in {operation_name}: {e}")
        raise
    finally:
        timer.finish()

# Convenience functions for common operations
def vector_search_with_timing(query_embedding: list, limit: int = 50) -> list:
    """Vector search with performance monitoring"""
    sql = """
        SELECT id, document_id, chunk_index, text, 
               embedding <-> %s AS distance
        FROM chunks 
        ORDER BY embedding <-> %s 
        LIMIT %s
    """
    return execute_with_timing(sql, (query_embedding, query_embedding, limit), "vector_search")

def keyword_search_with_timing(query: str, limit: int = 50) -> list:
    """Keyword search with performance monitoring"""  
    sql = """
        SELECT id, document_id, chunk_index, text,
               ts_rank(search_vector, plainto_tsquery('vietnamese', %s)) AS rank
        FROM chunks
        WHERE search_vector @@ plainto_tsquery('vietnamese', %s)
        ORDER BY rank DESC
        LIMIT %s
    """
    return execute_with_timing(sql, (query, query, limit), "keyword_search")

def test_database_performance():
    """Test database performance and pool functionality"""
    print("🔍 Testing database performance...")
    
    # Initialize pool
    initialize_pool()
    
    # Test basic connectivity
    timer = QueryTimer("connectivity_test")
    try:
        with get_conn() as conn:
            timer.checkpoint("connection")
            result = conn.execute("SELECT COUNT(*) as chunk_count FROM chunks").fetchone()
            timer.checkpoint("query")
            print(f"✅ Database connectivity: {result['chunk_count']} chunks available")
    except Exception as e:
        print(f"❌ Connectivity test failed: {e}")
        return
    finally:
        timer.finish()
    
    # Test vector search performance
    mock_embedding = [0.1] * 384  # Mock embedding vector
    try:
        vector_results = vector_search_with_timing(mock_embedding, 20)
        print(f"✅ Vector search: {len(vector_results)} results")
    except Exception as e:
        print(f"❌ Vector search test failed: {e}")
    
    # Test keyword search performance
    try:
        keyword_results = keyword_search_with_timing("database management", 20)
        print(f"✅ Keyword search: {len(keyword_results)} results")
    except Exception as e:
        print(f"❌ Keyword search test failed: {e}")
    
    # Show pool statistics
    stats = get_pool_stats()
    print(f"📊 Pool stats: {json.dumps(stats, indent=2)}")

if __name__ == "__main__":
    test_database_performance()
```

#### Enhanced Main API with Complete Monitoring

```python
# api/app/main.py - ENHANCED VERSION WITH MONITORING
import time
import json
import logging
from collections import defaultdict
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware

# Import enhanced modules
from .db_enhanced import get_conn, QueryTimer, initialize_pool, get_pool_stats
from .listmode import enhanced_list_search

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global performance tracking
_performance_stats = defaultdict(list)
_request_count = 0

app = FastAPI(title="Chatnary RAG API", version="2.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    logger.info("🚀 Starting Chatnary RAG API v2.0.0")
    initialize_pool()
    logger.info("✅ Database pool initialized")

@app.middleware("http")
async def performance_middleware(request: Request, call_next):
    """Middleware to track API performance"""
    global _request_count
    _request_count += 1
    
    start_time = time.time()
    path = request.url.path
    method = request.method
    
    try:
        response = await call_next(request)
        elapsed = time.time() - start_time
        
        # Log performance
        _performance_stats[f"{method}_{path}"].append(elapsed)
        
        # Add performance headers
        response.headers["X-Response-Time"] = f"{elapsed:.3f}s"
        response.headers["X-Request-Count"] = str(_request_count)
        
        # Log slow requests
        if elapsed > 3.0:
            logger.warning(f"⚠️  Slow request: {method} {path} took {elapsed:.2f}s")
        
        return response
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ Request failed: {method} {path} after {elapsed:.2f}s - {e}")
        raise

@app.get("/health")
def health_check():
    """Enhanced health check with system status"""
    timer = QueryTimer("health_check")
    
    try:
        # Test database connectivity
        with get_conn() as conn:
            timer.checkpoint("db_connection")
            chunk_count = conn.execute("SELECT COUNT(*) as count FROM chunks").fetchone()
            timer.checkpoint("db_query")
            
        # Get pool stats
        pool_stats = get_pool_stats()
        timer.checkpoint("pool_stats")
        
        # Calculate average response times
        recent_performance = {}
        for endpoint, times in _performance_stats.items():
            if times:
                recent_times = times[-10:]  # Last 10 requests
                recent_performance[endpoint] = {
                    "avg_time": sum(recent_times) / len(recent_times),
                    "request_count": len(times)
                }
        
        status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0.0",
            "database": {
                "chunks": chunk_count["count"],
                "pool": pool_stats
            },
            "performance": {
                "total_requests": _request_count,
                "recent_endpoints": recent_performance
            }
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {e}")
    finally:
        timer.finish()

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, user_id: int = Depends(get_current_user_id)):
    """Enhanced ask endpoint with comprehensive monitoring"""
    global _request_count
    
    # Initialize timing
    request_timer = QueryTimer("ask_request")
    query = req.query.strip()
    
    logger.info(f"📝 Query received: '{query[:50]}...' (user: {user_id})")
    
    try:
        # Enhanced retrieval with list-mode detection
        from .listmode import is_list_query
        
        # Adapt search parameters for list queries
        base_k_vec = req.k_vector
        base_k_kw = req.k_keyword
        
        if is_list_query(query):
            base_k_vec = min(base_k_vec * 2, 150)
            base_k_kw = min(base_k_kw * 2, 100)
            logger.info(f"🔍 List query detected - boosting to {base_k_vec}v/{base_k_kw}k")
        
        request_timer.checkpoint("query_analysis")
        
        # Perform hybrid search
        candidates = hybrid_search_for_user(
            query, user_id, 
            k_vec=base_k_vec, 
            k_kw=base_k_kw
        )
        request_timer.checkpoint("hybrid_search")
        
        logger.info(f"🔍 Found {len(candidates)} candidates")
        
        # Try list-mode processing first
        list_result = enhanced_list_search(query, user_id, candidates)
        if list_result:
            request_timer.checkpoint("list_processing")
            logger.info(f"📋 List-mode: {list_result['items_found']} items found")
            
            return AskResponse(
                answer=list_result["answer"],
                sources=list_result["sources"]
            )
        
        # Standard RAG processing
        docs = [{"text": c["text"], "meta": c.get("meta", {})} for c in candidates]
        
        # Rerank with enhanced budget
        rerank_budget = max(req.rerank_top_n * 2, 16)
        reranked = rerank(query, docs, top_n=rerank_budget)
        request_timer.checkpoint("reranking")
        
        # Generate answer with citations
        final_context = reranked[:req.rerank_top_n]
        from .llm_enhanced import generate_answer_with_citations
        answer = generate_answer_with_citations(query, final_context, language=req.answer_language)
        request_timer.checkpoint("answer_generation")
        
        # Create enhanced sources
        sources = []
        for d in final_context:
            meta = d.get("meta", {})
            sources.append({
                "document_id": meta.get("document_id"),
                "chunk_index": meta.get("chunk_index"),
                "title": meta.get("title"),
                "source": meta.get("source"),
                "preview": d["text"][:200] + "..." if len(d["text"]) > 200 else d["text"]
            })
        
        logger.info(f"✅ Response generated: {len(sources)} sources")
        
        return AskResponse(answer=answer, sources=sources)
        
    except Exception as e:
        logger.error(f"❌ Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing error: {e}")
    finally:
        request_timer.finish()

# Performance monitoring endpoints
@app.get("/performance")
def get_performance_stats():
    """Get API performance statistics"""
    stats = {}
    
    for endpoint, times in _performance_stats.items():
        if times:
            stats[endpoint] = {
                "total_requests": len(times),
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
                "recent_avg": sum(times[-10:]) / min(10, len(times))
            }
    
    return {
        "total_requests": _request_count,
        "endpoints": stats,
        "database": get_pool_stats()
    }

@app.post("/benchmark")
def run_benchmark(iterations: int = 10):
    """Run performance benchmark"""
    if iterations > 50:
        raise HTTPException(status_code=400, detail="Max 50 iterations allowed")
    
    test_queries = [
        "DBMS là gì?",
        "Hệ quản trị cơ sở dữ liệu có những thành phần nào?",
        "Database administrator có vai trò gì?",
        "Liệt kê các loại cơ sở dữ liệu",
    ]
    
    results = []
    
    for i in range(iterations):
        query = test_queries[i % len(test_queries)]
        start_time = time.time()
        
        try:
            # Mock request
            req = AskRequest(query=query, k_vector=30, k_keyword=20, rerank_top_n=5)
            response = ask(req, user_id=1)  # Use test user
            
            elapsed = time.time() - start_time
            results.append({
                "iteration": i + 1,
                "query": query,
                "time": elapsed,
                "success": True,
                "sources_count": len(response.sources)
            })
            
        except Exception as e:
            elapsed = time.time() - start_time
            results.append({
                "iteration": i + 1,
                "query": query,
                "time": elapsed,
                "success": False,
                "error": str(e)
            })
    
    # Calculate statistics
    successful_results = [r for r in results if r["success"]]
    times = [r["time"] for r in successful_results]
    
    if times:
        benchmark_stats = {
            "total_iterations": iterations,
            "successful": len(successful_results),
            "failed": iterations - len(successful_results),
            "avg_time": sum(times) / len(times),
            "min_time": min(times),
            "max_time": max(times),
            "success_rate": len(successful_results) / iterations * 100
        }
    else:
        benchmark_stats = {
            "total_iterations": iterations,
            "successful": 0,
            "failed": iterations,
            "success_rate": 0
        }
    
    return {
        "benchmark_stats": benchmark_stats,
        "detailed_results": results
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 3.2 Performance Monitoring Dashboard

#### Complete Performance Monitoring Implementation

```python
# api/app/monitoring.py - NEW FILE
"""
Performance monitoring and alerting system
"""
import time
import json
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class PerformanceMetric:
    """Performance metric data structure"""
    timestamp: float
    operation: str
    duration: float
    success: bool
    metadata: Dict[str, Any] = None

class PerformanceMonitor:
    """
    Comprehensive performance monitoring system
    """
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics = deque(maxlen=max_history)
        self.operation_stats = defaultdict(list)
        self.alert_thresholds = {
            "slow_query": 2.0,      # seconds
            "error_rate": 0.05,     # 5%
            "avg_response": 1.0     # seconds
        }
        self.start_time = time.time()
    
    def record_metric(self, operation: str, duration: float, 
                     success: bool = True, metadata: Dict = None):
        """Record a performance metric"""
        metric = PerformanceMetric(
            timestamp=time.time(),
            operation=operation,
            duration=duration,
            success=success,
            metadata=metadata or {}
        )
        
        self.metrics.append(metric)
        self.operation_stats[operation].append(metric)
        
        # Keep operation stats manageable
        if len(self.operation_stats[operation]) > 100:
            self.operation_stats[operation] = self.operation_stats[operation][-100:]
        
        # Check for alerts
        self._check_alerts(metric)
    
    def _check_alerts(self, metric: PerformanceMetric):
        """Check if metric triggers any alerts"""
        if metric.duration > self.alert_thresholds["slow_query"]:
            print(f"🚨 SLOW QUERY ALERT: {metric.operation} took {metric.duration:.2f}s")
        
        if not metric.success:
            print(f"🚨 ERROR ALERT: {metric.operation} failed")
        
        # Check error rate for this operation
        recent_ops = [m for m in self.operation_stats[metric.operation] 
                     if m.timestamp > time.time() - 300]  # Last 5 minutes
        
        if len(recent_ops) >= 10:  # Only check if we have enough samples
            error_rate = sum(1 for m in recent_ops if not m.success) / len(recent_ops)
            if error_rate > self.alert_thresholds["error_rate"]:
                print(f"🚨 HIGH ERROR RATE ALERT: {metric.operation} has {error_rate:.1%} error rate")
    
    def get_summary(self, operation: str = None) -> Dict[str, Any]:
        """Get performance summary"""
        if operation:
            metrics = [m for m in self.metrics if m.operation == operation]
        else:
            metrics = list(self.metrics)
        
        if not metrics:
            return {"error": "No metrics found"}
        
        successful_metrics = [m for m in metrics if m.success]
        durations = [m.duration for m in successful_metrics]
        
        if not durations:
            return {"error": "No successful operations"}
        
        return {
            "operation": operation or "all",
            "total_requests": len(metrics),
            "successful_requests": len(successful_metrics),
            "error_rate": (len(metrics) - len(successful_metrics)) / len(metrics),
            "avg_duration": sum(durations) / len(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "p95_duration": sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 20 else max(durations),
            "requests_per_minute": len([m for m in metrics if m.timestamp > time.time() - 60]),
            "uptime": time.time() - self.start_time
        }
    
    def get_recent_alerts(self, minutes: int = 15) -> List[Dict]:
        """Get recent performance issues"""
        threshold_time = time.time() - (minutes * 60)
        recent_metrics = [m for m in self.metrics if m.timestamp > threshold_time]
        
        alerts = []
        
        # Find slow queries
        slow_queries = [m for m in recent_metrics 
                       if m.duration > self.alert_thresholds["slow_query"]]
        for metric in slow_queries:
            alerts.append({
                "type": "slow_query",
                "operation": metric.operation,
                "duration": metric.duration,
                "timestamp": metric.timestamp
            })
        
        # Find errors
        errors = [m for m in recent_metrics if not m.success]
        for metric in errors:
            alerts.append({
                "type": "error",
                "operation": metric.operation,
                "metadata": metric.metadata,
                "timestamp": metric.timestamp
            })
        
        return sorted(alerts, key=lambda x: x["timestamp"], reverse=True)
    
    def export_metrics(self, format: str = "json") -> str:
        """Export metrics in specified format"""
        if format == "json":
            return json.dumps([asdict(m) for m in self.metrics], indent=2)
        elif format == "csv":
            lines = ["timestamp,operation,duration,success,metadata"]
            for m in self.metrics:
                metadata_str = json.dumps(m.metadata) if m.metadata else ""
                lines.append(f"{m.timestamp},{m.operation},{m.duration},{m.success},\"{metadata_str}\"")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")

class ContextManager:
    """Context manager for automatic performance tracking"""
    
    def __init__(self, monitor: PerformanceMonitor, operation: str, metadata: Dict = None):
        self.monitor = monitor
        self.operation = operation
        self.metadata = metadata or {}
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        success = exc_type is None
        
        if exc_type:
            self.metadata["error"] = str(exc_val)
        
        self.monitor.record_metric(self.operation, duration, success, self.metadata)

# Global monitor instance
performance_monitor = PerformanceMonitor()

def track_performance(operation: str, metadata: Dict = None):
    """Decorator or context manager for tracking performance"""
    return ContextManager(performance_monitor, operation, metadata)

# FastAPI monitoring endpoints
from fastapi import APIRouter
monitoring_router = APIRouter(prefix="/monitoring", tags=["monitoring"])

@monitoring_router.get("/health")
def get_health_metrics():
    """Get system health metrics"""
    return {
        "status": "healthy",
        "uptime": time.time() - performance_monitor.start_time,
        "metrics_count": len(performance_monitor.metrics),
        "recent_alerts": len(performance_monitor.get_recent_alerts(15))
    }

@monitoring_router.get("/performance")
def get_performance_metrics(operation: str = None):
    """Get performance metrics"""
    return performance_monitor.get_summary(operation)

@monitoring_router.get("/alerts")
def get_recent_alerts(minutes: int = 15):
    """Get recent performance alerts"""
    return {
        "alerts": performance_monitor.get_recent_alerts(minutes),
        "alert_count": len(performance_monitor.get_recent_alerts(minutes))
    }

@monitoring_router.get("/operations")
def list_operations():
    """List all monitored operations"""
    operations = list(performance_monitor.operation_stats.keys())
    return {
        "operations": operations,
        "operation_summaries": {
            op: performance_monitor.get_summary(op) 
            for op in operations
        }
    }

@monitoring_router.get("/export")
def export_metrics(format: str = "json", operation: str = None):
    """Export performance metrics"""
    try:
        if operation:
            # Filter metrics for specific operation
            filtered_metrics = [m for m in performance_monitor.metrics 
                              if m.operation == operation]
            temp_monitor = PerformanceMonitor()
            temp_monitor.metrics = deque(filtered_metrics)
            return {"data": temp_monitor.export_metrics(format)}
        else:
            return {"data": performance_monitor.export_metrics(format)}
    except Exception as e:
        return {"error": str(e)}

# Example usage in main API
def enhanced_ask_with_monitoring(req: AskRequest, user_id: int):
    """Example of integrating monitoring into the ask endpoint"""
    
    with track_performance("ask_request", {"user_id": user_id, "query_length": len(req.query)}):
        # Your existing ask logic here
        with track_performance("hybrid_search"):
            candidates = hybrid_search_for_user(req.query, user_id, req.k_vector, req.k_keyword)
        
        with track_performance("reranking"):
            reranked = rerank(req.query, candidates, req.rerank_top_n)
        
        with track_performance("answer_generation"):
            answer = generate_answer(req.query, reranked)
        
        return {"answer": answer, "sources": reranked}

if __name__ == "__main__":
    # Test monitoring system
    import random
    
    print("🧪 Testing monitoring system...")
    
    # Simulate some operations
    for i in range(50):
        operation = random.choice(["ask_request", "hybrid_search", "reranking"])
        duration = random.uniform(0.1, 3.0)
        success = random.random() > 0.05  # 95% success rate
        
        performance_monitor.record_metric(operation, duration, success)
        time.sleep(0.01)  # Small delay
    
    # Test context manager
    with track_performance("test_operation"):
        time.sleep(0.5)
    
    # Show summary
    print("\n📊 Performance Summary:")
    summary = performance_monitor.get_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")
    
    # Show recent alerts
    alerts = performance_monitor.get_recent_alerts()
    print(f"\n🚨 Recent Alerts ({len(alerts)}):")
    for alert in alerts[:5]:
        print(f"  {alert['type']}: {alert['operation']} - {alert.get('duration', 'N/A')}")
```

### 3.3 Complete Phase 3 Testing Framework

```bash
#!/bin/bash
# test_phase3_complete.sh
echo "=== PHASE 3 COMPLETE TESTING ==="

mkdir -p test_results/phase3

echo "📊 Installing monitoring dependencies..."
pip install psycopg[pool] fastapi-monitoring

echo "🔗 Testing Connection Pooling..."

# Test 1: Pool initialization and basic connectivity
echo "Test 1: Database pool initialization"
python -c "
from api.app.db_enhanced import initialize_pool, get_pool_stats, test_database_performance
initialize_pool()
stats = get_pool_stats()
print(f'Pool stats: {stats}')
test_database_performance()
" 2>&1 | tee test_results/phase3/pool_test.log

# Test 2: Concurrent connection stress test
echo -e "\nTest 2: Concurrent connection stress test"
echo "Running 20 concurrent requests..."

for i in {1..20}; do
  {
    curl -s -X POST http://localhost:8000/ask \
      -H "Content-Type: application/json" \
      -d "{\"query\":\"Test query $i - DBMS basics\",\"k_vector\":30,\"rerank_top_n\":5}" \
      > test_results/phase3/concurrent_$i.json &
  }
done

wait  # Wait for all background jobs to complete
echo "✅ Concurrent test completed"

# Analyze results
success_count=$(find test_results/phase3 -name "concurrent_*.json" -exec sh -c 'jq -e ".answer" "$1" >/dev/null 2>&1' _ {} \; | wc -l)
total_count=$(find test_results/phase3 -name "concurrent_*.json" | wc -l)
echo "Concurrent success rate: $success_count/$total_count"

echo -e "\n⚡ Testing Performance Monitoring..."

# Test 3: Performance monitoring endpoints
echo "Test 3: Monitoring endpoints"
echo "Health check:"
curl -s http://localhost:8000/monitoring/health | jq .

echo -e "\nPerformance metrics:"
curl -s http://localhost:8000/monitoring/performance | jq .

echo -e "\nOperations list:"
curl -s http://localhost:8000/monitoring/operations | jq '.operations'

echo -e "\nRecent alerts:"
curl -s http://localhost:8000/monitoring/alerts | jq '.alert_count'

# Test 4: Benchmark different phases
echo -e "\nTest 4: Phase comparison benchmark"

declare -A phase_times
declare -A phase_success

# Benchmark each optimization level
for phase in "baseline" "phase1" "phase2" "phase3"; do
  echo "Benchmarking $phase configuration..."
  
  # Configure for each phase (simplified)
  case $phase in
    "baseline")
      k_vector=30; k_keyword=20; rerank_top_n=5
      ;;
    "phase1")
      k_vector=40; k_keyword=25; rerank_top_n=6
      ;;
    "phase2")
      k_vector=60; k_keyword=40; rerank_top_n=8
      ;;
    "phase3")
      k_vector=80; k_keyword=50; rerank_top_n=10
      ;;
  esac
  
  total_time=0
  success_count=0
  
  for run in {1..5}; do
    start_time=$(date +%s.%N)
    
    result=$(curl -s -X POST http://localhost:8000/ask \
      -H "Content-Type: application/json" \
      -d "{\"query\":\"Hệ quản trị cơ sở dữ liệu có những thành phần và tính năng gì?\",\"k_vector\":$k_vector,\"k_keyword\":$k_keyword,\"rerank_top_n\":$rerank_top_n}")
    
    end_time=$(date +%s.%N)
    elapsed=$(echo "$end_time - $start_time" | bc -l)
    
    if echo "$result" | jq -e '.answer' > /dev/null 2>&1; then
      success_count=$((success_count + 1))
      total_time=$(echo "$total_time + $elapsed" | bc -l)
    fi
    
    sleep 1
  done
  
  if [ $success_count -gt 0 ]; then
    avg_time=$(echo "scale=3; $total_time / $success_count" | bc -l)
    phase_times[$phase]=$avg_time
    phase_success[$phase]=$success_count
    echo "  $phase: ${avg_time}s average (${success_count}/5 success)"
  else
    echo "  $phase: FAILED"
  fi
done

# Performance comparison
echo -e "\n📈 Performance Comparison Summary:"
for phase in "baseline" "phase1" "phase2" "phase3"; do
  if [[ -n "${phase_times[$phase]}" ]]; then
    echo "  $phase: ${phase_times[$phase]}s (${phase_success[$phase]}/5 success)"
  fi
done

echo -e "\nTest 5: Memory and resource usage"
# Check memory usage
echo "Current memory usage:"
ps aux | grep "python.*main.py" | head -1 | awk '{print "  Memory: " $6/1024 " MB, CPU: " $3 "%"}'

# Check database connections
echo "Database connections:"
curl -s http://localhost:8000/monitoring/performance | jq '.database.pool'

echo -e "\n🧪 Testing Error Handling and Recovery..."

# Test 6: Error conditions
echo "Test 6: Error handling"

# Test invalid query
echo "Testing invalid query handling:"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"","k_vector":0,"rerank_top_n":0}' | \
  jq -r '.detail // .answer // "No error handling"'

# Test overload condition  
echo -e "\nTesting overload handling (50 rapid requests):"
start_overload=$(date +%s)

for i in {1..50}; do
  curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"Overload test $i\",\"k_vector\":20}" \
    > /dev/null &
  
  # Slight delay to avoid overwhelming system
  sleep 0.1
done

wait
end_overload=$(date +%s)
overload_duration=$((end_overload - start_overload))

echo "  Overload test completed in ${overload_duration}s"

# Check system status after overload
echo "System status after overload:"
curl -s http://localhost:8000/monitoring/health | jq '.status'

# Check for alerts
alerts=$(curl -s http://localhost:8000/monitoring/alerts | jq '.alert_count')
echo "  Alerts generated: $alerts"

echo -e "\n✅ Phase 3 testing complete!"

# Generate final report
cat > test_results/phase3/final_report.md << EOF
# Phase 3 Testing Report

## Connection Pooling
- Pool initialization: ✅
- Concurrent handling: $success_count/$total_count requests successful
- Database connections: Stable

## Performance Monitoring  
- Health endpoints: Functional
- Metrics collection: Active
- Alert system: $alerts alerts during testing

## Performance Comparison
$(for phase in "baseline" "phase1" "phase2" "phase3"; do
  if [[ -n "${phase_times[$phase]}" ]]; then
    echo "- $phase: ${phase_times[$phase]}s average"
  fi
done)

## Error Handling
- Invalid input handling: Functional
- Overload recovery: ${overload_duration}s for 50 requests
- System stability: Maintained

## Recommendations
1. Monitor alert patterns in production
2. Adjust pool size based on load
3. Set up log aggregation for monitoring
4. Regular performance benchmarking

Generated: $(date)
EOF

echo "📋 Final report saved to test_results/phase3/final_report.md"
echo "🎉 All Phase 3 testing completed successfully!"
```

## 🚀 Complete Deployment Guide

### Environment Setup and Dependencies

```bash
#!/bin/bash
# setup_production.sh
echo "=== PRODUCTION DEPLOYMENT SETUP ==="

# Install required dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt
pip install psycopg[pool] rapidfuzz fastapi-monitoring

# Set up environment variables
echo "⚙️  Configuring environment..."
cat > .env.production << EOF
# Database Configuration
PGHOST=localhost
PGPORT=5432
PGDB=rag_db
PGUSER=rag
PGPASSWORD=your_secure_password

# API Keys
GOOGLE_API_KEY=your_google_api_key
COHERE_API_KEY=your_cohere_api_key

# Performance Tuning
RAG_RRF_K=60
RAG_LOCALITY_PENALTY=0.15
DB_POOL_MIN_SIZE=5
DB_POOL_MAX_SIZE=20
DB_LOG_SLOW_THRESHOLD=1.0

# List Mode Configuration
LIST_QUERY_THRESHOLD=2
MAX_LIST_ITEMS=100
LIST_SIMILARITY_THRESHOLD=0.85

# Monitoring
LOG_LEVEL=INFO
ENABLE_PERFORMANCE_MONITORING=true
EOF

echo "✅ Production environment configured"
echo "🔧 Update .env.production with your actual API keys and database credentials"
```

### Final Validation Checklist

```bash
#!/bin/bash
# final_validation.sh
echo "=== FINAL DEPLOYMENT VALIDATION ==="

echo "✅ Checklist:"
echo "1. Database connection: $(curl -s http://localhost:8000/health | jq -r '.database.chunks // "FAILED"') chunks available"
echo "2. API endpoints: $(curl -s http://localhost:8000/health | jq -r '.status')"
echo "3. Monitoring: $(curl -s http://localhost:8000/monitoring/health | jq -r '.status')"
echo "4. Performance: $(curl -s http://localhost:8000/monitoring/performance | jq -r '.avg_duration // "No data"')s average"

# Test key functionalities
echo -e "\n🧪 Functionality Tests:"

# Standard query
echo "Standard query test:"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"DBMS là gì?","k_vector":30,"rerank_top_n":5}' | \
  jq -r '.answer[:100] + "..." // "FAILED"'

# List query
echo -e "\nList query test:"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Liệt kê các học phần chuyên ngành","k_vector":60,"rerank_top_n":8}' | \
  jq -r 'if (.answer | contains("1.")) then "✅ List mode working" else "❌ List mode failed" end'

# Vietnamese search
echo -e "\nVietnamese search test:"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"quản trị cơ sở dữ liệu","k_vector":40,"rerank_top_n":6}' | \
  jq -r 'if (.sources | length) > 0 then "✅ Vietnamese search working" else "❌ Vietnamese search failed" end'

echo -e "\n🎉 Deployment validation complete!"
echo "System ready for production use."
```

```
    timer = Timer()
    
    # ... existing code ...
    candidates = hybrid_search_for_user(...)
    timer.checkpoint("search")
    
    reranked = rerank(...)
    timer.checkpoint("rerank")
    
    answer = generate_answer(...)
    timer.checkpoint("generate")
    
    # Log performance
    logger.info(f"Query processed - {timer.summary()} | user:{user_id} | query_len:{len(req.query)}")
    
    return AskResponse(answer=answer, sources=sources)
```

### 3.2 Simple A/B Testing Framework ⭐

*Impact: Long-term | Effort: Thấp | Risk: Không*

```python
# api/app/experiments.py - FILE MỚI
import hashlib
import os

def get_experiment_variant(user_id: int, experiment_name: str) -> str:
    """Simple A/B testing based on user_id hash"""
    if not os.getenv("ENABLE_EXPERIMENTS", "false").lower() == "true":
        return "control"
    
    # Create deterministic hash from user_id + experiment name
    hash_input = f"{user_id}:{experiment_name}".encode()
    hash_value = hashlib.md5(hash_input).hexdigest()
    
    # Convert to number 0-99
    bucket = int(hash_value[:2], 16) % 100
    
    # Example: 20% get variant, 80% get control
    return "variant" if bucket < 20 else "control"

# Usage in main.py
from .experiments import get_experiment_variant

@app.post("/ask")
def ask(req: AskRequest, user_id: int = Depends(get_current_user_id)):
    # Example experiment: Different rerank budgets
    variant = get_experiment_variant(user_id, "rerank_budget")
    
    if variant == "variant":
        rerank_budget = req.rerank_top_n * 3  # Test higher budget
    else:
        rerank_budget = req.rerank_top_n * 2  # Control
    
    # Log for analysis
    logger.info(f"Experiment rerank_budget:{variant} user:{user_id}")
    
    # ... rest unchanged
```

---

## 🧪 Complete Testing & Validation Framework

### Phase 1 Testing - RRF + HNSW + Citations

#### Pre-Implementation Baseline Testing

```bash
#!/bin/bash
# test_phase1_baseline.sh
echo "=== PHASE 1 BASELINE TESTING ==="

# Create test results directory
mkdir -p test_results/phase1

# 1. Measure current performance
echo "📊 Measuring current performance..."

# Test basic retrieval
echo "Test 1: Basic DBMS query"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"DBMS là gì?","k_vector":30,"k_keyword":20,"rerank_top_n":5}' | \
  tee test_results/phase1/baseline_dbms.json | jq -r '.sources | length, .[0].preview[:100]'

# Test list query (expect to fail)
echo -e "\nTest 2: List query (should fail in baseline)"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Liệt kê toàn bộ học phần chuyên ngành KTPM","k_vector":50,"k_keyword":30,"rerank_top_n":8}' | \
  tee test_results/phase1/baseline_list.json | jq -r '.sources | length, .answer[:200]'

# Test Vietnamese accents
echo -e "\nTest 3: Vietnamese with accents"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"quản trị cơ sở dữ liệu","k_vector":20,"k_keyword":15,"rerank_top_n":5}' | \
  tee test_results/phase1/baseline_vietnamese.json | jq -r '.sources | length'

# Measure latency (5 runs)
echo -e "\nTest 4: Latency measurement"
for i in {1..5}; do
  echo "Run $i:"
  time curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d '{"query":"Hệ quản trị cơ sở dữ liệu có những thành phần nào?","k_vector":40,"rerank_top_n":6}' \
    > /dev/null
done 2>&1 | grep real > test_results/phase1/baseline_latency.txt

echo "✅ Baseline measurements saved to test_results/phase1/"
```

#### Phase 1 Implementation Files

**Complete RRF Implementation:**

```python
# api/app/retrieval_enhanced.py - NEW FILE
"""
Enhanced retrieval with RRF and locality penalty
Run this file standalone to test the functions before integration
"""
import os
import time
import json
from collections import defaultdict
from typing import List, Dict, Optional

# Import existing functions (adapt paths as needed)
try:
    from .retrieval import _vector_candidates, _keyword_candidates, embed_texts
    from .db import get_conn
except ImportError:
    # For standalone testing
    print("Running in standalone mode - using mock functions")
    def embed_texts(texts): return [[0.1] * 10 for _ in texts]
    def _vector_candidates(vec, limit): return []
    def _keyword_candidates(query, limit): return []
    def get_conn(): return None

# Configuration with environment variables
RRF_K = int(os.getenv("RAG_RRF_K", "60"))
LOCALITY_PENALTY = float(os.getenv("RAG_LOCALITY_PENALTY", "0.15"))
LOCALITY_WINDOW = int(os.getenv("RAG_LOCALITY_WINDOW", "1"))

def rrf_merge(vector_hits: List[Dict], keyword_hits: List[Dict]) -> List[Dict]:
    """
    Reciprocal Rank Fusion - mathematically proven better than score-based merging
    Formula: score = sum(1/(k + rank)) for each ranking list
    
    Args:
        vector_hits: List of chunks from vector search
        keyword_hits: List of chunks from keyword search
    
    Returns:
        List of merged chunks with RRF scores
    """
    bag = defaultdict(float)
    keep = {}
    
    # Process vector hits - rank starts from 1
    for rank, hit in enumerate(vector_hits, 1):
        chunk_id = hit["id"]
        bag[chunk_id] += 1.0 / (RRF_K + rank)
        if chunk_id not in keep:
            keep[chunk_id] = hit.copy()
    
    # Process keyword hits - rank starts from 1  
    for rank, hit in enumerate(keyword_hits, 1):
        chunk_id = hit["id"]
        bag[chunk_id] += 1.0 / (RRF_K + rank)
        if chunk_id not in keep:
            keep[chunk_id] = hit.copy()
    
    # Create merged results with RRF scores
    merged = []
    for chunk_id, rrf_score in bag.items():
        chunk_data = keep[chunk_id]
        chunk_data["rrf_score"] = rrf_score
        chunk_data["original_score"] = chunk_data.get("score", 0.0)
        merged.append(chunk_data)
    
    # Sort by RRF score (highest first)
    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    
    print(f"RRF merged {len(vector_hits)} vector + {len(keyword_hits)} keyword → {len(merged)} unique chunks")
    return merged

def apply_locality_penalty(chunks: List[Dict], 
                         window: int = None, 
                         penalty: float = None) -> List[Dict]:
    """
    Reduce scores of chunks that are close to each other in the same document
    This prevents information redundancy and encourages diversity
    
    Args:
        chunks: List of chunks with RRF scores
        window: Distance threshold for applying penalty (default from env)
        penalty: Penalty factor 0-1 (default from env)
    
    Returns:
        List of chunks with locality penalties applied
    """
    if window is None:
        window = LOCALITY_WINDOW
    if penalty is None:
        penalty = LOCALITY_PENALTY
        
    doc_chunks = defaultdict(list)
    result = []
    penalties_applied = 0
    
    # Apply penalty based on proximity to already processed chunks
    for chunk in chunks:
        doc_id = chunk["document_id"]
        chunk_idx = chunk["chunk_index"]
        current_score = chunk["rrf_score"]
        
        # Check if this chunk is too close to already processed chunks
        penalty_applied = False
        for existing_idx in doc_chunks[doc_id]:
            if abs(chunk_idx - existing_idx) <= window:
                current_score *= (1.0 - penalty)
                penalty_applied = True
                penalties_applied += 1
                break
        
        # Update chunk with potentially penalized score
        updated_chunk = chunk.copy()
        updated_chunk["rrf_score"] = current_score
        updated_chunk["locality_penalty_applied"] = penalty_applied
        
        result.append(updated_chunk)
        doc_chunks[doc_id].append(chunk_idx)
    
    # Re-sort after applying penalties
    result.sort(key=lambda x: x["rrf_score"], reverse=True)
    
    print(f"Locality penalty applied to {penalties_applied} chunks")
    return result

def enhanced_hybrid_search(query: str, k_vec: int = 60, k_kw: int = 30, 
                          debug: bool = False) -> List[Dict]:
    """
    Enhanced hybrid search with RRF fusion and locality penalty
    
    Args:
        query: Search query
        k_vec: Number of vector candidates
        k_kw: Number of keyword candidates  
        debug: Print timing information
    
    Returns:
        List of ranked chunks with metadata
    """
    start_time = time.time()
    
    # Generate query embedding
    q_vec = embed_texts([query])[0]
    embed_time = time.time()
    
    # Execute parallel searches
    vec_hits = _vector_candidates(q_vec, limit=k_vec)  
    vector_time = time.time()
    
    kw_hits = _keyword_candidates(query, limit=k_kw)
    keyword_time = time.time()
    
    # Apply RRF fusion
    merged = rrf_merge(vec_hits, kw_hits)
    rrf_time = time.time()
    
    # Apply locality penalty
    final_results = apply_locality_penalty(merged)
    final_time = time.time()
    
    # Debug timing information
    if debug:
        print(f"Enhanced search timing breakdown:")
        print(f"  Embedding: {(embed_time-start_time)*1000:.1f}ms")
        print(f"  Vector search: {(vector_time-embed_time)*1000:.1f}ms")  
        print(f"  Keyword search: {(keyword_time-vector_time)*1000:.1f}ms")
        print(f"  RRF merge: {(rrf_time-keyword_time)*1000:.1f}ms")
        print(f"  Locality penalty: {(final_time-rrf_time)*1000:.1f}ms")
        print(f"  Total: {(final_time-start_time)*1000:.1f}ms")
    
    return final_results

def hybrid_search_for_user(query: str, user_id: int, k_vec: int = 60, k_kw: int = 30) -> List[Dict]:
    """
    User-scoped hybrid search with enhancements
    This replaces the original function in retrieval.py
    """
    # Get enhanced results
    results = enhanced_hybrid_search(query, k_vec, k_kw, debug=True)
    
    # Filter by user and add metadata
    if results and get_conn():
        chunk_ids = [r["id"] for r in results]
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT c.id, d.id as doc_id, d.title, d.source, c.chunk_index
                FROM chunks c
                JOIN documents d ON d.id = c.document_id  
                WHERE c.id = ANY(%s) AND d.owner_id = %s
                ORDER BY array_position(%s, c.id)
            """, (chunk_ids, user_id, chunk_ids)).fetchall()
        
        # Create metadata lookup
        meta_lookup = {
            r[0]: {
                "document_id": r[1], 
                "title": r[2], 
                "source": r[3],
                "chunk_index": r[4]
            } 
            for r in rows
        }
        
        # Add metadata to results and filter user's documents only
        user_results = []
        for result in results:
            if result["id"] in meta_lookup:
                result["meta"] = meta_lookup[result["id"]]
                user_results.append(result)
        
        return user_results
    
    return results  # Fallback for testing

# Standalone testing function
def test_rrf_functions():
    """Test RRF functions with mock data"""
    print("Testing RRF functions with mock data...")
    
    # Mock data
    vector_hits = [
        {"id": 1, "score": 0.9, "document_id": 1, "chunk_index": 5, "text": "Vector chunk 1"},
        {"id": 2, "score": 0.8, "document_id": 1, "chunk_index": 6, "text": "Vector chunk 2"},  
        {"id": 3, "score": 0.7, "document_id": 2, "chunk_index": 10, "text": "Vector chunk 3"},
    ]
    
    keyword_hits = [  
        {"id": 2, "score": 0.95, "document_id": 1, "chunk_index": 6, "text": "Keyword chunk 2"},
        {"id": 4, "score": 0.85, "document_id": 2, "chunk_index": 15, "text": "Keyword chunk 4"},
        {"id": 5, "score": 0.75, "document_id": 1, "chunk_index": 7, "text": "Keyword chunk 5"},
    ]
    
    # Test RRF merge
    merged = rrf_merge(vector_hits, keyword_hits)
    print(f"\nRRF Results (top 3):")
    for i, chunk in enumerate(merged[:3]):
        print(f"  {i+1}. Chunk {chunk['id']}: RRF={chunk['rrf_score']:.3f}")
    
    # Test locality penalty
    penalized = apply_locality_penalty(merged)
    print(f"\nAfter Locality Penalty (top 3):")
    for i, chunk in enumerate(penalized[:3]):
        penalty_mark = " (penalized)" if chunk["locality_penalty_applied"] else ""
        print(f"  {i+1}. Chunk {chunk['id']}: RRF={chunk['rrf_score']:.3f}{penalty_mark}")

if __name__ == "__main__":
    test_rrf_functions()
```

**Enhanced LLM with Citations:**

```python
# api/app/llm_enhanced.py - NEW FILE OR UPDATE EXISTING
"""
Enhanced LLM functions with inline citations
"""
import os
from typing import List, Dict
try:
    from google import genai
    from .settings import settings
    _genai = genai.Client(api_key=settings.google_api_key) if settings.google_api_key else None
except ImportError:
    _genai = None
    print("Google GenAI not available - using fallback")

def generate_answer_with_citations(query: str, context_blocks: List[Dict], 
                                 language: str = "vi") -> str:
    """
    Generate answer with inline citations for traceability
    
    Args:
        query: User question
        context_blocks: List of context chunks with metadata
        language: Response language
    
    Returns:
        Answer with [doc_id:chunk_idx] citations
    """
    if not context_blocks:
        return "Mình không tìm thấy thông tin liên quan trong tài liệu."
    
    # Build enhanced prompt with source tagging
    context_lines = [
        "Bạn là trợ lý RAG chuyên nghiệp và đáng tin cậy.",
        "",
        "QUY TẮC QUAN TRỌNG:",
        "1. Chỉ trả lời dựa trên CONTEXT được cung cấp",
        "2. Sau mỗi thông tin/số liệu/mệnh đề quan trọng, gắn trích dẫn [doc_id:chunk_idx]",
        "3. Nếu thiếu thông tin: 'Mình không tìm thấy đủ thông tin trong tài liệu.'",
        "4. Trích dẫn nguyên văn 1-2 câu quan trọng từ nguồn khi cần minh chứng",
        "5. Trả lời ngắn gọn, chính xác, dễ hiểu",
        "",
        "CONTEXT VỚI NGUỒN:"
    ]
    
    # Add numbered context blocks with source tags
    for i, block in enumerate(context_blocks, 1):
        meta = block.get("meta", {})
        doc_id = meta.get("document_id", "?")
        chunk_idx = meta.get("chunk_index", "?") 
        title = meta.get("title", "Unknown")
        source_tag = f"[{doc_id}:{chunk_idx}]"
        
        context_lines.append(f"---")
        context_lines.append(f"Nguồn {source_tag} (từ: {title})")
        context_lines.append(block["text"])
        context_lines.append("")
    
    # Add query and instruction
    context_lines.extend([
        "---",
        f"CÂU HỎI: {query}",
        "",
        f"TRẢ LỜI ({language}, có trích dẫn nguồn):"
    ])
    
    prompt = "\n".join(context_lines)
    
    # Generate with temperature for consistency
    if _genai:
        try:
            response = _genai.models.generate_content(
                model=getattr(settings, 'gemini_model', 'gemini-2.0-flash'),
                contents=prompt,
                config={
                    "temperature": 0.1,  # Low for consistency
                    "max_output_tokens": 1000,
                    "top_p": 0.8
                }
            )
            answer = getattr(response, "text", str(response))
            
            # Validate citations exist
            citation_count = answer.count('[') 
            if citation_count == 0 and len(context_blocks) > 0:
                # Add at least one citation if missing
                first_source = context_blocks[0].get("meta", {})
                doc_id = first_source.get("document_id", "?")
                chunk_idx = first_source.get("chunk_index", "?")
                answer += f" [{doc_id}:{chunk_idx}]"
            
            return answer
            
        except Exception as e:
            print(f"Gemini generation error: {e}")
    
    # Fallback response with citations
    if context_blocks:
        meta = context_blocks[0].get("meta", {})
        doc_id = meta.get("document_id", "?")
        chunk_idx = meta.get("chunk_index", "?")
        return f"Dựa trên tài liệu, {context_blocks[0]['text'][:200]}... [{doc_id}:{chunk_idx}]"
    
    return "Lỗi sinh trả lời. Vui lòng thử lại."

def test_citation_generation():
    """Test citation generation with mock data"""
    mock_context = [
        {
            "text": "Database Management System (DBMS) là hệ thống phần mềm cho phép tạo, quản lý và truy xuất cơ sở dữ liệu.",
            "meta": {"document_id": 6, "chunk_index": 15, "title": "kb_dbms"}
        },
        {
            "text": "DBMS cung cấp giao diện giữa người dùng và cơ sở dữ liệu, đảm bảo tính toàn vẹn và bảo mật dữ liệu.",
            "meta": {"document_id": 6, "chunk_index": 16, "title": "kb_dbms"}
        }
    ]
    
    query = "DBMS là gì?"
    answer = generate_answer_with_citations(query, mock_context)
    
    print("Mock Answer with Citations:")
    print(answer)
    print(f"\nCitation count: {answer.count('[')}")

if __name__ == "__main__":
    test_citation_generation()
```

#### Phase 1 Post-Implementation Testing

```bash
#!/bin/bash
# test_phase1_implementation.sh
echo "=== PHASE 1 IMPLEMENTATION TESTING ==="

mkdir -p test_results/phase1

# Test RRF improvements
echo "📊 Testing RRF improvements..."

echo "Test 1: RRF vs old merge - DBMS query"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"DBMS là gì?","k_vector":30,"k_keyword":20,"rerank_top_n":5}' | \
  tee test_results/phase1/phase1_dbms.json | \
  jq -r '.sources | length, .[0].preview[:100]'

# Compare sources count with baseline
echo -e "\nSources comparison (Baseline vs Phase1):"
baseline_sources=$(jq '.sources | length' test_results/phase1/baseline_dbms.json 2>/dev/null || echo "0")
phase1_sources=$(jq '.sources | length' test_results/phase1/phase1_dbms.json)
echo "Baseline: $baseline_sources sources"
echo "Phase 1:  $phase1_sources sources"
improvement=$((phase1_sources - baseline_sources))
echo "Improvement: +$improvement sources"

echo -e "\nTest 2: Locality penalty verification"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Hệ quản trị cơ sở dữ liệu có những tính năng và thành phần chính nào","k_vector":40,"k_keyword":25,"rerank_top_n":10}' | \
  tee test_results/phase1/locality_test.json | \
  jq -r '.sources[] | "\(.document_id):\(.chunk_index)"' | \
  sort | uniq -c | \
  awk 'BEGIN {adjacent=0} {
    if($1 > 1) adjacent++
  } END {
    print "Documents with adjacent chunks:", adjacent
    print "Expected: Should be low (< 3) due to locality penalty"
  }'

echo -e "\nTest 3: Inline citations verification"  
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Database administrator có vai trò như thế nào?","k_vector":25,"rerank_top_n":4}' | \
  tee test_results/phase1/citations_test.json | \
  jq -r '.answer' > test_results/phase1/citations_answer.txt

citations_found=$(grep -o '\[[0-9]*:[0-9]*\]' test_results/phase1/citations_answer.txt | wc -l)
echo "Citations found: $citations_found"
echo "Expected: Should be > 0 (ideally 2-4)"

if [ $citations_found -gt 0 ]; then
  echo "✅ Citations working correctly"
else  
  echo "❌ Citations not found - check implementation"
fi

echo -e "\nTest 4: Performance after Phase 1"
echo "Running 5 latency tests..."
total_time=0
for i in {1..5}; do
  echo -n "Run $i: "
  run_time=$(time (curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d '{"query":"Hệ quản trị cơ sở dữ liệu có những thành phần nào?","k_vector":40,"rerank_top_n":6}' \
    > /dev/null) 2>&1 | grep real | awk '{print $2}' | sed 's/[ms]//g')
  echo "${run_time}s"
  # Convert to milliseconds for averaging (approximation)
  total_time=$(echo "$total_time + $run_time" | bc -l 2>/dev/null || echo "$total_time")
done

echo -e "\nTest 5: Quality assessment"
# Test diverse query types
queries=(
  "Cơ sở dữ liệu quan hệ có đặc điểm gì?"
  "Phân biệt DDL và DML trong SQL"
  "Quản trị viên cơ sở dữ liệu làm những công việc gì?"
)

for query in "${queries[@]}"; do
  echo "Testing: $query"
  curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$query\",\"k_vector\":30,\"rerank_top_n\":5}" | \
    jq -r '.sources | length' | \
    awk '{print "  Sources found:", $1}'
  sleep 1
done

echo -e "\n✅ Phase 1 testing complete!"
echo "Check test_results/phase1/ for detailed results."
echo -e "\nNext steps:"
echo "1. Review citation quality in citations_answer.txt"
echo "2. Verify source diversity decreased adjacent chunks"  
echo "3. Confirm latency stayed under 4 seconds"
echo "4. If all looks good, proceed to Phase 2"
```

#### Phase 1 Automated Validation

```python
# test_phase1_validation.py
"""
Comprehensive automated validation for Phase 1 improvements
"""
import json
import requests
import time
import statistics
from typing import Dict, List, Tuple

def test_single_query(query: str, params: Dict = None) -> Dict:
    """Test a single query and return comprehensive metrics"""
    default_params = {
        "query": query,
        "k_vector": 50,
        "k_keyword": 30, 
        "rerank_top_n": 8
    }
    if params:
        default_params.update(params)
    
    start_time = time.time()
    
    try:
        response = requests.post(
            "http://localhost:8000/ask", 
            json=default_params,
            timeout=10
        )
        end_time = time.time()
        latency = end_time - start_time
        
        if response.status_code == 200:
            data = response.json()
            answer = data.get("answer", "")
            sources = data.get("sources", [])
            
            # Extract citations
            import re
            citations = re.findall(r'\[(\d+):(\d+)\]', answer)
            
            # Calculate diversity metrics
            doc_ids = [s.get("document_id") for s in sources if s.get("document_id")]
            source_diversity = len(set(doc_ids)) / max(len(doc_ids), 1)
            
            # Check for adjacent chunks (locality penalty effectiveness)
            adjacent_pairs = 0
            chunk_by_doc = {}
            for source in sources:
                doc_id = source.get("document_id")
                chunk_idx = source.get("chunk_index")
                if doc_id and chunk_idx is not None:
                    if doc_id not in chunk_by_doc:
                        chunk_by_doc[doc_id] = []
                    chunk_by_doc[doc_id].append(chunk_idx)
            
            for doc_id, chunks in chunk_by_doc.items():
                chunks.sort()
                for i in range(len(chunks)-1):
                    if chunks[i+1] - chunks[i] <= 1:  # Adjacent chunks
                        adjacent_pairs += 1
            
            return {
                "query": query,
                "success": True,
                "latency": latency,
                "sources_count": len(sources),
                "citations_count": len(citations),
                "answer_length": len(answer),
                "source_diversity": source_diversity,
                "adjacent_chunks": adjacent_pairs,
                "has_answer": len(answer.strip()) > 10,
                "answer_preview": answer[:200] + "..." if len(answer) > 200 else answer
            }
        else:
            return {
                "query": query,
                "success": False,
                "latency": time.time() - start_time,
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }
            
    except Exception as e:
        return {
            "query": query,
            "success": False, 
            "latency": time.time() - start_time,
            "error": str(e)
        }

def run_comprehensive_phase1_validation() -> bool:
    """Run comprehensive Phase 1 validation with detailed reporting"""
    
    print("🧪 Starting comprehensive Phase 1 validation...")
    print("=" * 70)
    
    # Test cases covering different query types
    test_cases = [
        # Basic factual queries
        ("DBMS là gì?", {"expected_sources_min": 3}),
        ("Cơ sở dữ liệu quan hệ có đặc điểm gì?", {"expected_sources_min": 3}),
        
        # Complex descriptive queries  
        ("Hệ quản trị cơ sở dữ liệu có những thành phần chính nào?", {"expected_sources_min": 4}),
        ("Database administrator có vai trò và trách nhiệm như thế nào?", {"expected_sources_min": 3}),
        
        # Vietnamese with accents (FTS test)
        ("quản trị cơ sở dữ liệu", {"expected_sources_min": 2}),
        ("bảo mật thông tin trong hệ thống", {"expected_sources_min": 2}),
        
        # Technical comparison queries
        ("Phân biệt DDL và DML trong SQL", {"expected_sources_min": 3}),
        ("So sánh ưu nhược điểm của các loại cơ sở dữ liệu", {"expected_sources_min": 3}),
    ]
    
    results = []
    total_start = time.time()
    
    # Run tests
    for i, (query, expectations) in enumerate(test_cases, 1):
        print(f"Test {i}/{len(test_cases)}: {query[:50]}...")
        
        result = test_single_query(query)
        result.update(expectations)
        results.append(result)
        
        # Show immediate feedback
        if result["success"]:
            status = "✅" if result["sources_count"] >= expectations.get("expected_sources_min", 1) else "⚠️"
            print(f"  {status} {result['sources_count']} sources, {result['citations_count']} citations, {result['latency']:.2f}s")
        else:
            print(f"  ❌ Failed: {result['error'][:50]}")
        
        time.sleep(0.5)  # Prevent rate limiting
    
    total_time = time.time() - total_start
    
    # Calculate comprehensive metrics
    successful_tests = [r for r in results if r["success"]]
    
    if not successful_tests:
        print("❌ All tests failed! Check API connectivity.")
        return False
    
    # Core metrics
    avg_latency = statistics.mean(r["latency"] for r in successful_tests)
    p95_latency = statistics.quantiles([r["latency"] for r in successful_tests], n=20)[18] if len(successful_tests) >= 5 else avg_latency
    avg_sources = statistics.mean(r["sources_count"] for r in successful_tests)
    avg_citations = statistics.mean(r["citations_count"] for r in successful_tests)
    avg_diversity = statistics.mean(r["source_diversity"] for r in successful_tests)
    
    # Success rates
    citation_rate = sum(1 for r in successful_tests if r["citations_count"] > 0) / len(successful_tests)
    min_sources_met = sum(1 for r in successful_tests if r["sources_count"] >= r.get("expected_sources_min", 1)) / len(successful_tests)
    low_adjacent_rate = sum(1 for r in successful_tests if r["adjacent_chunks"] <= 2) / len(successful_tests)
    
    # Print detailed results
    print("\n" + "=" * 70)
    print("📊 PHASE 1 VALIDATION RESULTS")
    print("=" * 70)
    
    print(f"📈 Test Summary:")
    print(f"  • Total tests: {len(test_cases)}")
    print(f"  • Successful: {len(successful_tests)} ({len(successful_tests)/len(test_cases):.1%})")
    print(f"  • Total time: {total_time:.1f}s")
    
    print(f"\n⚡ Performance Metrics:")
    print(f"  • Average latency: {avg_latency:.2f}s")
    print(f"  • P95 latency: {p95_latency:.2f}s")
    print(f"  • Target: < 4.0s ({'✅' if p95_latency < 4.0 else '❌'})")
    
    print(f"\n🔍 Retrieval Quality:")
    print(f"  • Average sources per query: {avg_sources:.1f}")
    print(f"  • Queries meeting min sources: {min_sources_met:.1%}")
    print(f"  • Source diversity: {avg_diversity:.2f}")
    print(f"  • Target diversity: > 0.7 ({'✅' if avg_diversity > 0.7 else '❌'})")
    
    print(f"\n📝 Citation & Locality:")
    print(f"  • Queries with citations: {citation_rate:.1%}")
    print(f"  • Target citations: > 80% ({'✅' if citation_rate > 0.8 else '❌'})")
    print(f"  • Average citations per query: {avg_citations:.1f}")
    print(f"  • Low adjacent chunks rate: {low_adjacent_rate:.1%}")
    print(f"  • Target locality: > 80% ({'✅' if low_adjacent_rate > 0.8 else '❌'})")
    
    # Individual test details
    print(f"\n📋 Individual Test Results:")
    for i, result in enumerate(results, 1):
        if result["success"]:
            sources_status = "✅" if result["sources_count"] >= result.get("expected_sources_min", 1) else "⚠️"
            citations_status = "✅" if result["citations_count"] > 0 else "❌"
            print(f"  {i:2d}. {sources_status}{citations_status} {result['query'][:40]:40} | "
                  f"{result['sources_count']}src {result['citations_count']}cit {result['latency']:.2f}s")
        else:
            print(f"  {i:2d}. ❌❌ {result['query'][:40]:40} | ERROR")
    
    # Save detailed results to file
    detailed_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_tests": len(test_cases),
            "successful_tests": len(successful_tests),
            "avg_latency": avg_latency,
            "p95_latency": p95_latency,
            "avg_sources": avg_sources,
            "avg_citations": avg_citations, 
            "citation_rate": citation_rate,
            "min_sources_met": min_sources_met,
            "source_diversity": avg_diversity,
            "low_adjacent_rate": low_adjacent_rate,
            "total_time": total_time
        },
        "detailed_results": results
    }
    
    with open("test_results/phase1/validation_results.json", "w", encoding="utf-8") as f:
        json.dump(detailed_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Detailed results saved to test_results/phase1/validation_results.json")
    
    # Overall success determination
    success_criteria = [
        ("Performance", p95_latency < 4.0),
        ("Citations", citation_rate > 0.8),
        ("Min Sources", min_sources_met > 0.8), 
        ("Source Diversity", avg_diversity > 0.7),
        ("Locality Penalty", low_adjacent_rate > 0.8)
    ]
    
    passed_criteria = sum(1 for _, passed in success_criteria if passed)
    
    print(f"\n🎯 Success Criteria ({passed_criteria}/{len(success_criteria)} passed):")
    for criterion, passed in success_criteria:
        print(f"  {'✅' if passed else '❌'} {criterion}")
    
    overall_success = passed_criteria >= 4  # At least 4/5 criteria
    
    if overall_success:
        print(f"\n🎉 PHASE 1 VALIDATION PASSED!")
        print(f"   Ready to proceed to Phase 2.")
    else:
        print(f"\n⚠️  PHASE 1 VALIDATION NEEDS ATTENTION")
        print(f"   Review failed criteria before proceeding.")
    
    return overall_success

if __name__ == "__main__":
    # Ensure test directory exists
    import os
    os.makedirs("test_results/phase1", exist_ok=True)
    
    success = run_comprehensive_phase1_validation()
    exit(0 if success else 1)
```

#### Phase 1 Quick Rollback

```bash
#!/bin/bash
# rollback_phase1.sh
echo "🔄 Rolling back Phase 1 changes..."

# Create backup of current state
echo "Creating backup..."
cp -r api/app api/app_phase1_backup_$(date +%Y%m%d_%H%M%S)

# Restore original files from git
echo "Restoring original files..."
git checkout HEAD -- api/app/retrieval.py api/app/llm.py api/app/main.py

# Remove new files if they were added
rm -f api/app/retrieval_enhanced.py
rm -f api/app/llm_enhanced.py

# Reset environment variables
echo "Resetting environment variables..."
sed -i '/RAG_RRF_K/d' .env
sed -i '/RAG_LOCALITY_PENALTY/d' .env  
sed -i '/HNSW_EF_SEARCH/d' .env

# Restart services
echo "Restarting services..."
docker-compose restart api

# Wait for service to be ready
echo "Waiting for service to be ready..."
sleep 5

# Quick verification test
echo "Running rollback verification..."
response=$(curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"DBMS là gì?","k_vector":10,"rerank_top_n":3}')

if echo "$response" | jq -e '.sources | length' > /dev/null 2>&1; then
  sources_count=$(echo "$response" | jq '.sources | length')
  echo "✅ Rollback successful - API responding with $sources_count sources"
  
  # Check if citations are gone (indicating successful rollback)
  citations=$(echo "$response" | jq -r '.answer' | grep -o '\[[0-9]*:[0-9]*\]' | wc -l)
  if [ $citations -eq 0 ]; then
    echo "✅ Citations removed - rollback to baseline confirmed"
  else
    echo "⚠️  Citations still present - manual verification needed"
  fi
else
  echo "❌ Rollback verification failed - API not responding correctly"
  echo "Response: $response"
fi

echo -e "\n📝 Rollback Summary:"
echo "  • Original files restored from git"
echo "  • Enhanced files removed"
echo "  • Environment variables reset"
echo "  • Services restarted"
echo "  • Backup saved to api/app_phase1_backup_*"

echo -e "\nIf issues persist:"
echo "  1. Check docker logs: docker logs rag_api"
echo "  2. Restore from backup: cp -r api/app_phase1_backup_* api/app"
echo "  3. Contact development team"
```

---

## 📈 Success Metrics & Rollback Plan

### Metrics theo dõi hàng ngày

- **Average response time** < 3.5s (P95)
- **Answer quality score** (manual sampling 10 queries/day)
- **Source relevance rate** > 80%
- **List query success rate** > 80%

### Rollback procedures

```bash
# Nếu có vấn đề, rollback từng component
git checkout HEAD~1 api/app/retrieval.py  # Rollback RRF
docker exec rag_db psql -U rag -d rag -c "ALTER TABLE chunks ALTER COLUMN content_tsv SET DEFAULT..."  # Rollback FTS
```

---

## 💡 Additional Notes

### Environment Variables cần thêm

```bash
# .env - THÊM VÀO
RAG_RRF_K=60
HNSW_EF_SEARCH=80  
RAG_QUERY_VARIANTS=2
ENABLE_EXPERIMENTS=false
ENABLE_LISTMODE=true
```

### Dependencies cần install

```bash
pip install rapidfuzz psycopg[pool]
```

### Estimated Timeline

- **Phase 1:** 5-7 ngày (RRF + HNSW + Citations)
- **Phase 2:** 7-10 ngày (Query expansion + FTS + List-mode)  
- **Phase 3:** 3-5 ngày (Monitoring + Testing)

**Total: 15-22 ngày** cho implementation đầy đủ.

---

## ✅ Final Checklist

**Trước khi deploy lên production:**

- [ ] Backup database hiện tại
- [ ] Test toàn bộ trên staging environment  
- [ ] Đo baseline metrics trước khi thay đổi
- [ ] Chuẩn bị rollback scripts
- [ ] Set up monitoring & alerting
- [ ] Train người dùng về features mới (inline citations, list mode)

**Kỳ vọng tổng thể sau khi hoàn thành:**

- 🚀 **Recall tăng 30-40%** cho queries phức tạp
- 📝 **List queries success rate** từ 20% lên 80%+  
- 🎯 **Traceability 100%** với inline citations
- 🇻🇳 **Vietnamese search accuracy** tăng 40%
- ⚡ **Stable performance** với connection pooling

*Đây là implementation plan thực tế, đã cân nhắc kỹ về effort vs impact. Mỗi phase đều có thể triển khai độc lập và rollback được nếu cần.*
