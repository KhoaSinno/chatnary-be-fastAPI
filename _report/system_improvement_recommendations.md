# Báo Cáo Đánh Giá và Khuyến Nghị Cải Thiện Hệ Thống RAG

## 📊 Tổng Quan Đánh Giá

Dựa trên kết quả test trong `testing-query-chatRAG.txt` và phân tích từ `r1.md`, hệ thống đã hoạt động cơ bản nhưng còn một số vấn đề cần cải thiện về độ chính xác và relevance.

### Dữ Liệu Hiện Tại

- **7 tài liệu PDF** với 2 chủ đề chính:
  - **Mật mã học** (tiếng Việt): 4 chương về mã hóa, chữ ký số
  - **DBMS/IoT** (tiếng Anh/Việt): Quản trị cơ sở dữ liệu, IoT
- **Ngôn ngữ hỗn hợp**: Tiếng Việt, Anh, và truy vấn song ngữ

## 🔍 Phân Tích Vấn Đề Hiện Tại

### 1. **Vấn Đề Về Độ Chính Xác Nguồn**

```
❌ Query: "Mã hóa khóa bất đối xứng"
❌ Kết quả: Trả về cả Chương 2 (đối xứng) + kb_dbms (không liên quan)
✅ Mong muốn: Chỉ Chương 3 (bất đối xứng) + các thuật toán PKC
```

**Nguyên nhân:**

- Hybrid search thiếu bước lọc theo chủ đề
- Không có chuẩn hóa thang điểm vector vs keyword
- Thiếu diversification theo document

### 2. **Vấn Đề Với Tiếng Việt**

```
❌ Keyword search: "mã hóa" không match "mã hóa" (encoding khác nhau)
❌ Chunk bị cắt: Tiêu đề slide + nội dung tách biệt
✅ Cần: Chuẩn hóa không dấu + chunking thông minh
```

### 3. **Vấn Đề Về Thuật Toán**

```python
# Hiện tại trong hybrid_search()
vec_hits = vector_search(query, k=40)
kw_hits = keyword_search(query, k=20) 
# Chỉ merge theo ID, không lọc chất lượng
```

**Thiếu:**

- Post-filtering theo relevance threshold
- MMR (Maximal Marginal Relevance) để giảm trùng lặp
- Topic gating cho low-score results

## 🎯 Khuyến Nghị Cải Thiện

### **Cấp Độ 1: Cải Thiện Ngay (Quick Wins)**

#### 1.1 Thêm Chuẩn Hóa Tiếng Việt

```sql
-- Thêm vào database
ALTER TABLE chunks ADD COLUMN content_normalized TEXT 
GENERATED ALWAYS AS (unaccent(lower(content))) STORED;

CREATE INDEX idx_chunks_content_norm_gin 
ON chunks USING GIN (content_normalized gin_trgm_ops);
```

#### 1.2 Cải Thiện Keyword Search

```python
# Trong retrieval.py - _keyword_candidates()
def normalize_vietnamese(text):
    import unicodedata
    return unicodedata.normalize('NFD', text.lower()).encode('ascii', 'ignore').decode('ascii')

# Sửa SQL query
sql_trgm = """
    SELECT id, document_id, chunk_index, content, 
           similarity(content_normalized, %s) AS score
    FROM chunks
    WHERE content_normalized ILIKE %s
    ORDER BY score DESC
    LIMIT %s
"""
normalized_query = normalize_vietnamese(query)
rows = conn.execute(sql_trgm, (normalized_query, f'%{normalized_query}%', limit))
```

#### 1.3 Tăng Tham Số Tìm Kiếm

```python
# Trong retrieval.py - hybrid_search()
def hybrid_search(query: str, k: int = 8, k_vec: int = 60, k_kw: int = 30):
    # Tăng từ 40/20 lên 60/30 cho tiếng Việt
```

### **Cấp Độ 2: Post-Processing Thông Minh**

#### 2.1 Post-Filter Sau Reranking

```python
def post_filter_results(reranked_results, query, low_score_threshold=0.35, max_per_doc=2):
    """
    Lọc kết quả sau reranking để loại bỏ nhiễu và đảm bảo đa dạng
    """
    # Từ điển chủ đề để topic gating
    topic_keywords = {
        "mã hóa bất đối xứng": ["khóa công khai", "PKC", "RSA", "ElGamal", "DSA", "asymmetric"],
        "mã hóa đối xứng": ["AES", "DES", "symmetric", "khóa bí mật"],
        "transaction": ["ACID", "commit", "rollback", "giao dịch"],
        "client-server": ["client", "server", "kiến trúc", "architecture"]
    }
    
    # Chuẩn hóa query
    query_lower = normalize_vietnamese(query)
    query_terms = set(query_lower.split())
    
    # Tìm topic keywords phù hợp
    relevant_keywords = set()
    for topic, keywords in topic_keywords.items():
        if any(term in query_lower for term in topic.split()):
            relevant_keywords.update([normalize_vietnamese(kw) for kw in keywords])
    
    filtered_results = []
    doc_count = {}
    
    for result in reranked_results:
        score = result.get('relevance_score', 0)
        text_normalized = normalize_vietnamese(result['text'])
        doc_id = result['metadata']['document_id']
        
        # Topic gating cho điểm thấp
        if score < low_score_threshold:
            has_topic_match = any(kw in text_normalized for kw in relevant_keywords)
            if not has_topic_match:
                continue
        
        # Giới hạn số chunk per document
        if doc_count.get(doc_id, 0) >= max_per_doc:
            continue
            
        filtered_results.append(result)
        doc_count[doc_id] = doc_count.get(doc_id, 0) + 1
        
        # Dừng khi đủ kết quả chất lượng
        if len(filtered_results) >= 8:
            break
    
    return filtered_results
```

#### 2.2 MMR Diversification

```python
def mmr_diversify(results, query_embedding, lambda_param=0.7, top_k=6):
    """
    Maximal Marginal Relevance để giảm trùng lặp semantic
    """
    if not results:
        return results
        
    selected = []
    remaining = results.copy()
    
    # Chọn item đầu tiên (relevance cao nhất)
    selected.append(remaining.pop(0))
    
    while remaining and len(selected) < top_k:
        best_score = -1
        best_idx = -1
        
        for i, candidate in enumerate(remaining):
            # Relevance score
            relevance = candidate.get('relevance_score', 0)
            
            # Similarity với các đã chọn
            max_sim = 0
            for selected_item in selected:
                similarity = compute_text_similarity(candidate['text'], selected_item['text'])
                max_sim = max(max_sim, similarity)
            
            # MMR score
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
            
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i
        
        if best_idx != -1:
            selected.append(remaining.pop(best_idx))
        else:
            break
            
    return selected

def compute_text_similarity(text1, text2):
    """Tính cosine similarity đơn giản giữa 2 text"""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform([text1, text2])
    return cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
```

### **Cấp Độ 3: Cải Thiện Chunking**

#### 3.1 Smart Chunking cho PDF Slides

```python
def smart_chunk_slides(text, chunk_size=500, overlap=100):
    """
    Chunking thông minh cho slide PDF - nhóm tiêu đề với nội dung
    """
    import re
    
    # Patterns cho slide headers
    slide_patterns = [
        r'^[CHƯƠNG|CHAPTER]\s+\d+',
        r'^\d+\.\d+\s+\w+',
        r'^[A-Z][^a-z]{10,}$',  # ALL CAPS headers
        r'^❖\s*\w+',  # Bullet points
    ]
    
    lines = text.split('\n')
    chunks = []
    current_chunk = ""
    current_size = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Kiểm tra xem có phải header không
        is_header = any(re.match(pattern, line) for pattern in slide_patterns)
        
        # Nếu là header và chunk hiện tại đã đủ lớn
        if is_header and current_size > chunk_size * 0.7:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = line + "\n"
            current_size = len(line)
        else:
            current_chunk += line + "\n"
            current_size += len(line)
            
            # Nếu vượt quá kích thước tối đa
            if current_size > chunk_size + overlap:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                # Giữ lại overlap
                overlap_text = current_chunk[-overlap:]
                current_chunk = overlap_text
                current_size = len(overlap_text)
    
    # Thêm chunk cuối cùng
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks
```

### **Cấp Độ 4: Tối Ưu Hóa Database**

#### 4.1 Index Tối Ưu

```sql
-- Vector search optimization
CREATE INDEX idx_chunks_embedding_cosine 
ON chunks USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- Full-text search cho tiếng Việt
CREATE INDEX idx_chunks_content_fts_vi 
ON chunks USING GIN (to_tsvector('simple', content_normalized));

-- Compound index cho filtering
CREATE INDEX idx_chunks_doc_chunk 
ON chunks (document_id, chunk_index);
```

#### 4.2 Metadata Enrichment

```sql
-- Thêm metadata cho topic classification
ALTER TABLE documents ADD COLUMN topic VARCHAR(50);
ALTER TABLE documents ADD COLUMN language VARCHAR(10);
ALTER TABLE documents ADD COLUMN document_type VARCHAR(20);

-- Update existing data
UPDATE documents SET 
    topic = CASE 
        WHEN title LIKE '%ma%hoa%' THEN 'cryptography'
        WHEN title LIKE '%dbms%' OR title LIKE '%database%' THEN 'database'
        WHEN title LIKE '%iot%' THEN 'iot'
        ELSE 'general'
    END,
    language = CASE 
        WHEN title LIKE '%Chuong%' THEN 'vi'
        ELSE 'en'
    END;
```

## 🚀 Plan Triển Khai

### **Phase 1: Quick Fixes (1-2 ngày)**

1. ✅ Thêm `content_normalized` column và index
2. ✅ Update keyword search với Vietnamese normalization  
3. ✅ Tăng `k_vec=60, k_kw=30`
4. ✅ Implement `post_filter_results()`

### **Phase 2: Advanced Features (3-5 ngày)**

1. ✅ Implement MMR diversification
2. ✅ Add topic-based filtering
3. ✅ Improve source citation grouping
4. ✅ Add metadata enrichment

### **Phase 3: Monitoring & Tuning (ongoing)**

1. ✅ Setup evaluation metrics (P@5, nDCG@10)
2. ✅ A/B test different parameter combinations
3. ✅ Collect user feedback for continuous improvement

## 📈 Metrics để Đo Lường

### **Immediate Metrics**

```python
def evaluate_query_results(query, expected_docs, actual_results):
    """
    Đánh giá chất lượng kết quả cho một query
    """
    # Precision@K
    relevant_results = [r for r in actual_results[:5] 
                       if r['metadata']['document_id'] in expected_docs]
    precision_at_5 = len(relevant_results) / min(5, len(actual_results))
    
    # Topic coherence - tất cả results có cùng topic không?
    topics = [get_document_topic(r['metadata']['document_id']) 
              for r in actual_results[:5]]
    topic_coherence = len(set(topics)) == 1
    
    return {
        'precision_at_5': precision_at_5,
        'topic_coherence': topic_coherence,
        'num_unique_docs': len(set(r['metadata']['document_id'] 
                                   for r in actual_results[:5]))
    }
```

### **Test Cases để Validate**

```python
test_cases = [
    {
        'query': 'Mã hóa khóa bất đối xứng là gì, có những thuật toán nào',
        'expected_docs': [8],  # Chương 3 - Hệ mã bất đối xứng
        'expected_keywords': ['RSA', 'ElGamal', 'DSA', 'khóa công khai']
    },
    {
        'query': 'Transaction trong SQL hoạt động ra sao',
        'expected_docs': [10],  # kb_dbms.pdf
        'expected_keywords': ['ACID', 'commit', 'rollback']
    },
    {
        'query': 'Client server architecture advantages',
        'expected_docs': [10, 5],  # kb_dbms + IoT book
        'expected_keywords': ['client', 'server', 'scalability']
    }
]
```

## 💡 Code Examples để Implement

### **1. Update retrieval.py**

```python
# File: api/app/retrieval.py

import unicodedata
from typing import List, Dict, Tuple
from .db import get_conn
from .llm import embed_texts

def normalize_vietnamese(text: str) -> str:
    """Chuẩn hóa tiếng Việt - loại bỏ dấu và lowercase"""
    return unicodedata.normalize('NFD', text.lower()).encode('ascii', 'ignore').decode('ascii')

def hybrid_search(query: str, k: int = 8, k_vec: int = 60, k_kw: int = 30) -> List[Dict]:
    """
    Improved hybrid search với post-processing
    """
    # Vector search
    vec_hits = _vector_candidates(query, k_vec)
    
    # Keyword search với Vietnamese normalization
    kw_hits = _keyword_candidates_normalized(query, k_kw)
    
    # Merge và loại trùng lặp
    merged = _merge_candidates(vec_hits, kw_hits)
    
    # Rerank với Cohere
    if len(merged) > 1:
        reranked = _rerank_with_cohere(query, merged, top_n=min(16, len(merged)))
    else:
        reranked = merged
    
    # Post-processing
    filtered = post_filter_results(reranked, query)
    final_results = mmr_diversify(filtered, query)
    
    return final_results[:k]

def _keyword_candidates_normalized(query: str, limit: int = 30) -> List[Dict]:
    """
    Keyword search với Vietnamese normalization
    """
    normalized_query = normalize_vietnamese(query)
    
    sql_trgm = """
        SELECT id, document_id, chunk_index, content, 
               similarity(content_normalized, %s) AS score
        FROM chunks
        WHERE content_normalized ILIKE %s
        ORDER BY score DESC
        LIMIT %s
    """
    
    with get_conn() as conn:
        rows = conn.execute(sql_trgm, (
            normalized_query, 
            f'%{normalized_query}%', 
            limit
        )).fetchall()
        
    return [
        {
            "id": r[0],
            "document_id": r[1], 
            "chunk_index": r[2],
            "content": r[3],
            "score": float(r[4])
        }
        for r in rows
    ]

# ... implement post_filter_results() và mmr_diversify() như ở trên
```

### **2. Database Migration Script**

```sql
-- File: db/migrations/add_vietnamese_support.sql

-- Bước 1: Enable unaccent extension
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Bước 2: Thêm column normalized
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_normalized TEXT 
GENERATED ALWAYS AS (unaccent(lower(content))) STORED;

-- Bước 3: Thêm indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_content_norm_gin 
ON chunks USING GIN (content_normalized gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_content_fts_vi 
ON chunks USING GIN (to_tsvector('simple', content_normalized));

-- Bước 4: Thêm metadata cho documents
ALTER TABLE documents ADD COLUMN IF NOT EXISTS topic VARCHAR(50);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS language VARCHAR(10);

-- Bước 5: Update existing data
UPDATE documents SET 
    topic = CASE 
        WHEN LOWER(title) LIKE '%ma%hoa%' OR LOWER(title) LIKE '%cryptograph%' THEN 'cryptography'
        WHEN LOWER(title) LIKE '%dbms%' OR LOWER(title) LIKE '%database%' THEN 'database'
        WHEN LOWER(title) LIKE '%iot%' THEN 'iot'
        ELSE 'general'
    END,
    language = CASE 
        WHEN title LIKE '%Chuong%' THEN 'vi'
        ELSE 'en'
    END
WHERE topic IS NULL OR language IS NULL;
```

## 🎯 Kết Quả Mong Đợi

Sau khi implement các cải thiện trên:

### **Query: "Mã hóa khóa bất đối xứng là gì, có những thuật toán nào"**

```json
{
  "answer": "Mã hóa khóa bất đối xứng hay PKC sử dụng cặp khóa công khai-bí mật. Các thuật toán chính gồm RSA, ElGamal, DSA, và ECC...",
  "sources": [
    {
      "document_id": 8,
      "title": "Chương 3 - Hệ mã bất đối xứng", 
      "chunks": ["Định nghĩa PKC", "Thuật toán RSA", "Thuật toán ElGamal"]
    }
  ]
}
```

### **Improvements**

- ✅ **100% relevance**: Chỉ trả về Chương 3 (bất đối xứng)
- ✅ **Đa dạng nội dung**: Định nghĩa + các thuật toán cụ thể  
- ✅ **Nguồn sạch**: Gộp theo document, không rải rác
- ✅ **Hỗ trợ tiếng Việt tốt**: Bắt được các từ có/không dấu

---

**📞 Contact & Support**: Sẵn sàng hỗ trợ implement từng phase và debug khi cần thiết!
