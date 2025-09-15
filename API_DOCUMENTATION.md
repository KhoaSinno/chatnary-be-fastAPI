# RAG Backend API Documentation

## Overview

This is a Retrieval-Augmented Generation (RAG) backend service built with FastAPI that provides intelligent document search and question-answering capabilities. The system ingests PDF, TXT, and MD files, creates vector embeddings, and allows users to ask questions about the document content.

## Architecture

- **FastAPI**: Web framework for API endpoints
- **PostgreSQL + pgvector**: Database with vector search capabilities
- **OpenAI**: Text embeddings generation
- **Cohere**: Document reranking
- **Google Gemini**: Answer generation
- **Docker**: Containerized deployment

## Prerequisites

- Docker and Docker Compose
- API keys for:
  - OpenAI (for embeddings)
  - Cohere (for reranking)
  - Google AI/Gemini (for answer generation)

## Setup and Installation

### 1. Environment Configuration

Create a `.env` file in the project root with the following variables:

```bash
# Database Configuration
PGHOST=rag_db
PGPORT=5432
PGDATABASE=rag
PGUSER=rag
PGPASSWORD=ragpw

POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=ragdb

# API Keys
OPENAI_API_KEY=your_openai_api_key_here
COHERE_API_KEY=your_cohere_api_key_here
GOOGLE_API_KEY=your_google_api_key_here

# Model Configuration
OPENAI_EMBED_MODEL=text-embedding-3-small
COHERE_RERANK_MODEL=rerank-multilingual-v3.0
GEMINI_MODEL=gemini-2.0-flash

# Document Processing
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
```

### 2. Start the Services

```bash
# Build and start all containers
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f api
```

### 3. Document Ingestion

Place your documents (PDF, TXT, MD files) in the `./data` directory, then run:

```bash
# Ingest documents into the system
docker compose exec api python -m app.ingest //data

# For Git Bash users, use double slash to avoid path conversion
```

## API Endpoints

### Health Check

**GET** `/health`

Check if the API and database are working properly.

**Response:**

```json
{
  "ok": true
}
```

**Example:**

```bash
curl http://localhost:8000/health
```

### Ask Questions

**POST** `/ask`

Submit a question and get an AI-generated answer based on the ingested documents.

**Request Body:**

```json
{
  "query": "Your question here",
  "k_vector": 40,        // Optional: Number of vector search results
  "k_keyword": 20,       // Optional: Number of keyword search results  
  "rerank_top_n": 8,     // Optional: Top results after reranking
  "answer_language": "vi" // Optional: Response language (vi/en)
}
```

**Response:**

```json
{
  "answer": "AI-generated answer based on document content",
  "sources": [
    {
      "document_id": 1,
      "chunk_index": 5,
      "title": "Document Title",
      "source": "/data/filename.pdf",
      "preview": "Text preview of the relevant chunk..."
    }
  ]
}
```

## Testing Examples

### 1. Basic Health Check

```bash
curl -X GET http://localhost:8000/health
```

Expected response:

```json
{"ok": true}
```

### 2. Simple Question (Vietnamese)

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "luận văn là gì?"
  }'
```

### 3. Question with Custom Parameters

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the main topic of the thesis?",
    "k_vector": 50,
    "k_keyword": 30,
    "rerank_top_n": 10,
    "answer_language": "en"
  }'
```

### 4. Complex Query

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Những bước thực hiện chính trong nghiên cứu này là gì?"
  }'
```

## Testing with Python

### Using requests library

```python
import requests
import json

# Base URL
BASE_URL = "http://localhost:8000"

# Health check
def test_health():
    response = requests.get(f"{BASE_URL}/health")
    print("Health:", response.json())

# Ask a question
def test_ask(query, language="vi"):
    payload = {
        "query": query,
        "answer_language": language
    }
    response = requests.post(
        f"{BASE_URL}/ask", 
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    return response.json()

# Example usage
if __name__ == "__main__":
    # Test health
    test_health()
    
    # Test questions
    result = test_ask("Mục tiêu của luận văn là gì?")
    print("Answer:", result["answer"])
    print("Sources:", len(result["sources"]))
```

### Using httpx (async)

```python
import httpx
import asyncio

async def test_api():
    async with httpx.AsyncClient() as client:
        # Health check
        health = await client.get("http://localhost:8000/health")
        print("Health:", health.json())
        
        # Ask question
        response = await client.post(
            "http://localhost:8000/ask",
            json={"query": "Phương pháp nghiên cứu được sử dụng là gì?"}
        )
        result = response.json()
        print("Answer:", result["answer"])

# Run
asyncio.run(test_api())
```

## Frontend Integration Examples

### JavaScript/Fetch API

```javascript
// Health check
async function checkHealth() {
    const response = await fetch('http://localhost:8000/health');
    const data = await response.json();
    console.log('Health:', data);
}

// Ask question
async function askQuestion(query, language = 'vi') {
    const response = await fetch('http://localhost:8000/ask', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            query: query,
            answer_language: language
        })
    });
    
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    return data;
}

// Example usage
askQuestion("Kết luận của nghiên cứu là gì?")
    .then(result => {
        console.log('Answer:', result.answer);
        console.log('Sources:', result.sources);
    })
    .catch(error => console.error('Error:', error));
```

### React Example

```jsx
import React, { useState } from 'react';

function ChatInterface() {
    const [query, setQuery] = useState('');
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        
        try {
            const response = await fetch('http://localhost:8000/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            
            const data = await response.json();
            setResult(data);
        } catch (error) {
            console.error('Error:', error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <form onSubmit={handleSubmit}>
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Ask a question..."
                />
                <button type="submit" disabled={loading}>
                    {loading ? 'Searching...' : 'Ask'}
                </button>
            </form>
            
            {result && (
                <div>
                    <h3>Answer:</h3>
                    <p>{result.answer}</p>
                    <h4>Sources:</h4>
                    <ul>
                        {result.sources.map((source, idx) => (
                            <li key={idx}>
                                {source.title} - {source.preview}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}
```

## Troubleshooting

### Common Issues

1. **OpenAI Client Error**: If you see "proxies" related errors, the system will fallback to direct API calls automatically.

2. **No Documents Found**: Ensure documents are in the `./data` directory and run the ingestion command with `//data` (double slash) in Git Bash.

3. **Database Connection Issues**: Check if PostgreSQL container is running and healthy:

   ```bash
   docker compose ps
   docker compose logs db
   ```

4. **API Key Errors**: Verify all API keys are properly set in the `.env` file.

### Debug Commands

```bash
# Check container status
docker compose ps

# View API logs
docker compose logs -f api

# Check database content
docker compose exec api python -c "
from app.db import get_conn
with get_conn() as conn:
    docs = conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
    chunks = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
    print(f'Documents: {docs}, Chunks: {chunks}')
"

# Test embeddings directly
docker compose exec api python -c "
from app.llm import embed_texts
result = embed_texts(['test text'])
print(f'Embedding dimension: {len(result[0])}')
"
```

## Performance Considerations

- **Vector Search**: Adjust `k_vector` and `k_keyword` based on your document size
- **Reranking**: Higher `rerank_top_n` provides better accuracy but slower response
- **Chunking**: Optimize `CHUNK_SIZE` and `CHUNK_OVERLAP` for your document types
- **Caching**: Consider implementing Redis for frequently asked questions

## Security Notes

- Keep API keys secure and never commit them to version control
- Use environment variables for all sensitive configuration
- Consider implementing authentication for production use
- Validate and sanitize all user inputs

## API Documentation

Once the service is running, you can access the interactive API documentation at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

These provide detailed schema information and allow you to test endpoints directly from the browser.
