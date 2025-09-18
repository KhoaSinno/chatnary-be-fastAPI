# RAG System Testing Guide

## Overview

This guide provides comprehensive testing procedures for the RAG (Retrieval-Augmented Generation) system, including API testing with Postman, multilingual document evaluation, and performance assessment checklist.

## Prerequisites

- System is running via `docker compose up -d --build`
- Documents have been ingested into the system
- Postman application installed
- API endpoints accessible on localhost

## API Testing with Postman

### 1. Health Check Endpoint

**Request Configuration:**

- **Method:** GET
- **URL:** `http://localhost:8000/health`
- **Headers:** `Content-Type: application/json`

**Expected Response:**

```json
{
  "ok": true
}
```

### 2. Ask Question Endpoint

**Request Configuration:**

- **Method:** POST
- **URL:** `http://localhost:8000/ask`
- **Headers:** `Content-Type: application/json`

**Request Body Templates:**

#### Template 1: Basic Vietnamese Query

```json
{
  "query": "Hệ thống này hoạt động như thế nào?",
  "k_vector": 40,
  "k_keyword": 20,
  "rerank_top_n": 8,
  "answer_language": "vi"
}
```

#### Template 2: English Query

```json
{
  "query": "How does this system work?",
  "k_vector": 40,
  "k_keyword": 20,
  "rerank_top_n": 8,
  "answer_language": "en"
}
```

#### Template 3: Mixed Language Context

```json
{
  "query": "What is machine learning và nó hoạt động ra sao?",
  "k_vector": 50,
  "k_keyword": 25,
  "rerank_top_n": 10,
  "answer_language": "vi"
}
```

**Expected Response Structure:**

```json
{
  "answer": "Detailed answer text...",
  "sources": [
    {
      "document_id": 1,
      "chunk_index": 0,
      "title": "Document Title",
      "source": "path/to/document.pdf",
      "preview": "First 240 characters of the chunk..."
    }
  ]
}
```

## Multilingual Testing Strategy

### Phase 1: Single Language Document Testing

#### Vietnamese Documents Test Cases

1. **Technical Content:** Upload Vietnamese technical documents
2. **Academic Content:** Upload Vietnamese research papers
3. **General Content:** Upload Vietnamese news articles or guides

#### English Documents Test Cases

1. **Technical Content:** Upload English technical documentation
2. **Academic Content:** Upload English research papers
3. **General Content:** Upload English articles or manuals

### Phase 2: Mixed Language Environment Testing

#### Test Scenarios

1. **Vietnamese query on English documents**
2. **English query on Vietnamese documents**
3. **Mixed language query on mixed document collection**
4. **Code-switching queries** (mixing Vietnamese and English in same question)

### Phase 3: Document Variety Testing

#### File Types

- [ ] PDF documents (both languages)
- [ ] Markdown files (both languages)
- [ ] Text files (both languages)

#### Content Types

- [ ] Technical documentation
- [ ] Academic papers
- [ ] Business documents
- [ ] User manuals
- [ ] News articles
- [ ] Legal documents

## Performance Evaluation Checklist

### System Health Assessment

#### Database Connectivity

- [ ] Health endpoint returns `{"ok": true}`
- [ ] Database connection stable under load
- [ ] No timeout errors during testing

#### Response Times

- [ ] Health check: < 100ms
- [ ] Simple queries: < 2 seconds
- [ ] Complex queries: < 5 seconds
- [ ] Large document retrieval: < 10 seconds

### Retrieval Quality Assessment

#### Relevance Testing

For each test query, evaluate:

**Query:** ________________________________
**Language:** ____________________________
**Document Language(s):** _________________

**Retrieval Results:**

- [ ] Top result highly relevant (Score: 1-5) ___
- [ ] Top 3 results contain answer (Yes/No) ___
- [ ] Source attribution correct (Yes/No) ___
- [ ] Chunk selection appropriate (Yes/No) ___

**Answer Quality:**

- [ ] Factually accurate (Score: 1-5) ___
- [ ] Language consistency (Score: 1-5) ___
- [ ] Completeness (Score: 1-5) ___
- [ ] Clarity (Score: 1-5) ___

### Multilingual Performance Matrix

| Test Scenario | Query Lang | Doc Lang | Retrieval Quality | Answer Quality | Issues Found |
|---------------|------------|----------|-------------------|----------------|--------------|
| VN → VN       | Vietnamese | Vietnamese | ___/5 | ___/5 | |
| EN → EN       | English    | English    | ___/5 | ___/5 | |
| VN → EN       | Vietnamese | English    | ___/5 | ___/5 | |
| EN → VN       | English    | Vietnamese | ___/5 | ___/5 | |
| Mixed → Mixed | Both       | Both       | ___/5 | ___/5 | |

### Edge Cases Testing

#### Character Encoding

- [ ] Vietnamese diacritics handled correctly
- [ ] Special characters in English preserved
- [ ] Unicode characters in document names
- [ ] Mixed encoding scenarios

#### Query Complexity

- [ ] Single word queries
- [ ] Long paragraph queries
- [ ] Technical terminology queries
- [ ] Colloquial language queries
- [ ] Questions with typos

#### Document Size Variations

- [ ] Small documents (< 1 page)
- [ ] Medium documents (5-10 pages)
- [ ] Large documents (50+ pages)
- [ ] Very large documents (100+ pages)

## Common Issues and Troubleshooting

### Potential Multilingual Issues

#### 1. Embedding Quality

**Symptoms:** Poor retrieval for non-English content
**Check:** Test embedding API directly with curl:

```bash
curl https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-3-small",
    "input": "xin chào thế giới"
  }'
```

#### 2. Language Detection

**Symptoms:** Incorrect answer language
**Test Cases:**

- Query in Vietnamese, expect Vietnamese answer
- Query in English, expect English answer
- Verify `answer_language` parameter respected

#### 3. Cross-Language Retrieval

**Symptoms:** No results when query and document languages differ
**Test Strategy:**

- Use conceptually similar terms in both languages
- Test with proper nouns that should match across languages

### Performance Issues

#### 1. Slow Response Times

**Check:**

- [ ] Database query performance
- [ ] Embedding API latency
- [ ] Reranking service performance
- [ ] LLM generation time

#### 2. Memory Usage

**Monitor:**

- [ ] Container memory usage
- [ ] Database connection pool
- [ ] Vector index size

## Test Data Preparation

### Sample Documents for Testing

#### Vietnamese Content Suggestions

1. Technical documentation (e.g., software manuals)
2. Academic papers from Vietnamese universities
3. Government documents or policies
4. Business reports in Vietnamese

#### English Content Suggestions

1. Technical white papers
2. Academic research papers
3. Software documentation
4. Industry reports

#### Mixed Content Suggestions

1. International company reports (bilingual)
2. Academic papers with English abstracts
3. Technical documentation with English terms

## Reporting Template

### Test Session Report

**Date:** _______________
**Tester:** _______________
**System Version:** _______________

#### Document Collection

- Total documents: ___
- Vietnamese documents: ___
- English documents: ___
- Mixed language documents: ___

#### Test Results Summary

- Total queries tested: ___
- Successful responses: ___
- Failed responses: ___
- Average response time: ___

#### Key Findings

1. ________________________________
2. ________________________________
3. ________________________________

#### Recommendations

1. ________________________________
2. ________________________________
3. ________________________________

#### Critical Issues (if any)

1. ________________________________
2. ________________________________

---

**Notes:** Use this checklist systematically to ensure comprehensive testing coverage. Pay special attention to cross-language scenarios as they often reveal system limitations in multilingual environments.
