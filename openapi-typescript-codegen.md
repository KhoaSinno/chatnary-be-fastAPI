# **Hướng dẫn tích hợp RAG API với Next.js + TypeScript**

> **Sử dụng `openapi-typescript-codegen` để tự động generate client code từ OpenAPI spec**

---

## ✅ Mục tiêu

* FE **không tải file** spec thủ công
* Build/dev **tự fetch** OpenAPI từ BE và **generate client + types**
* **Type-safe** API calls với TypeScript
* Hỗ trợ cả **Client Component** (với CORS) và **Server Route Handler**

---

## 📋 Điều kiện tiên quyết

### Backend Requirements

* ✅ BE (FastAPI) đang chạy ở: `http://localhost:8000`
* ✅ CORS đã được cấu hình cho `http://localhost:3000`
* ✅ Endpoint `/openapi.json` có sẵn

### Frontend Requirements  

* Node 18+ hoặc 20+
* Next.js 14/15 (App Router)
* TypeScript

### Kiểm tra Backend

```bash
# Test API health
curl http://localhost:8000/health

# Test CORS headers
curl -I -H "Origin: http://localhost:3000" http://localhost:8000/health

# Xem OpenAPI spec
curl http://localhost:8000/openapi.json | jq '.'
```

---

## 1️⃣ Cài đặt packages

```bash
# Vào thư mục frontend Next.js
npm i -D openapi-typescript-codegen

# Optional: thêm các utility packages
npm i -D @types/node
```

---

## 2️⃣ Cấu hình Scripts

### `package.json`

```json
{
  "scripts": {
    "gen:client": "openapi -i http://localhost:8000/openapi.json -o ./lib/api-client -c fetch --exportSchemas true --exportCore true",
    "dev": "npm run gen:client && next dev",
    "build": "npm run gen:client && next build",
    "start": "next start",
    "gen:only": "openapi -i http://localhost:8000/openapi.json -o ./lib/api-client -c fetch --exportSchemas true --exportCore true"
  }
}
```

**Giải thích parameters:**
* `-i`: Input URL (fetch từ backend API)
* `-o`: Output directory
* `-c fetch`: Sử dụng fetch API
* `--exportSchemas true`: Export TypeScript types
* `--exportCore true`: Export core utilities

---

## 3️⃣ Cấu trúc Generated Code

Sau khi chạy `npm run gen:client`:

```
lib/
  api-client/
    core/
      ApiError.ts         # Error handling
      ApiRequestOptions.ts # Request config
      ApiResult.ts        # Response wrapper
      CancelablePromise.ts # Cancellation support
      OpenAPI.ts          # Main configuration
      request.ts          # Core request function
    models/               # TypeScript interfaces
      AskRequest.ts       # /ask request model
      AskResponse.ts      # /ask response model  
      HTTPValidationError.ts
      ValidationError.ts
    services/             # API service functions
      DefaultService.ts   # All endpoints (no tags defined)
    index.ts              # Export everything
```

---

## 4️⃣ API Configuration

### `lib/api-config.ts`

```typescript
import { OpenAPI } from '@/lib/api-client';

export function initApiClient() {
  // Base URL từ environment
  OpenAPI.BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
  
  // Headers mặc định 
  OpenAPI.HEADERS = {
    'X-User-Id': process.env.NEXT_PUBLIC_USER_ID || '1',
    'X-Request-Id': generateRequestId(),
    'Content-Type': 'application/json',
  };
  
  // Request/Response interceptors (optional)
  OpenAPI.interceptors = {
    request: (options) => {
      if (process.env.NODE_ENV === 'development') {
        console.log('🚀 API Request:', options.method, options.url);
      }
      return options;
    },
    response: (response) => {
      if (process.env.NODE_ENV === 'development') {
        console.log('✅ API Response:', response.status, response.url);
      }
      return response;
    }
  };
}

function generateRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).substring(2, 15);
}

// Export convenient wrapper functions
export { initApiClient };
```

### `.env.local`

```bash
# API Configuration
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_USER_ID=1

# Development settings  
NODE_ENV=development
```

---

## 5️⃣ API Usage Examples

### 🎯 Complete Search Component

```tsx
'use client';

import { useEffect, useState, useCallback } from 'react';
import { initApiClient } from '@/lib/api-config';
import { DefaultService } from '@/lib/api-client/services/DefaultService';
import type { AskRequest, AskResponse } from '@/lib/api-client';

interface DocumentSuggestion {
  id: number;
  title: string;
}

interface DocumentPreview {
  document_id: number;
  preview: string;
}

export default function RAGSearchComponent() {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<DocumentSuggestion[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<DocumentPreview | null>(null);
  const [chatResponse, setChatResponse] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initialize API client once
  useEffect(() => {
    initApiClient();
  }, []);

  // Debounced autocomplete search
  useEffect(() => {
    if (!query.trim()) {
      setSuggestions([]);
      return;
    }

    const timeoutId = setTimeout(async () => {
      try {
        setLoading(true);
        setError(null);
        
        const results = await DefaultService.suggestDocumentsSuggestGet({
          q: query
        });
        
        setSuggestions(results as DocumentSuggestion[]);
      } catch (err) {
        console.error('Suggest error:', err);
        setError('Lỗi tìm kiếm gợi ý');
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [query]);

  // Preview document
  const handlePreviewDoc = useCallback(async (docId: number) => {
    try {
      setLoading(true);
      setError(null);
      
      const preview = await DefaultService.previewDocDocumentsDocIdPreviewGet({
        docId: docId
      });
      
      setSelectedDoc(preview as DocumentPreview);
    } catch (err) {
      console.error('Preview error:', err);
      setError('Lỗi xem trước tài liệu');
    } finally {
      setLoading(false);
    }
  }, []);

  // Ask AI with RAG
  const handleAskAI = useCallback(async () => {
    if (!query.trim()) return;
    
    try {
      setLoading(true);
      setError(null);
      setChatResponse(null);
      
      const request: AskRequest = {
        query: query,
        k_vector: 60,
        k_keyword: 30,
        rerank_top_n: 8,
        answer_language: 'vi'
      };
      
      const response = await DefaultService.askAskPost({
        requestBody: request
      });
      
      setChatResponse(response);
    } catch (err) {
      console.error('Ask error:', err);
      setError('Lỗi khi hỏi AI');
    } finally {
      setLoading(false);
    }
  }, [query]);

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {/* Search Input */}
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tìm kiếm tài liệu hoặc đặt câu hỏi cho AI..."
          className="w-full p-4 text-lg border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        
        {loading && (
          <div className="absolute right-4 top-4">
            <div className="animate-spin h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full" />
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleAskAI}
          disabled={!query.trim() || loading}
          className="flex-1 bg-blue-600 text-white py-3 px-6 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          🤖 Hỏi AI
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Document Suggestions */}
        {suggestions.length > 0 && (
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="p-4 border-b border-gray-200 bg-gray-50">
              <h3 className="font-semibold text-gray-800">📚 Tài liệu liên quan</h3>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {suggestions.map((doc) => (
                <div
                  key={doc.id}
                  className="p-4 hover:bg-gray-50 cursor-pointer border-b last:border-b-0 transition-colors"
                  onClick={() => handlePreviewDoc(doc.id)}
                >
                  <div className="font-medium text-gray-900">{doc.title}</div>
                  <div className="text-sm text-gray-500 mt-1">
                    Document ID: {doc.id} • Click để xem preview
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Document Preview */}
        {selectedDoc && (
          <div className="bg-white border border-gray-200 rounded-lg">
            <div className="p-4 border-b border-gray-200 bg-gray-50">
              <h3 className="font-semibold text-gray-800">
                👁️ Preview - Document {selectedDoc.document_id}
              </h3>
            </div>
            <div className="p-4 max-h-96 overflow-y-auto">
              <div className="text-sm text-gray-700 whitespace-pre-wrap">
                {selectedDoc.preview}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* AI Response */}
      {chatResponse && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg">
          <div className="p-4 border-b border-blue-200">
            <h3 className="font-semibold text-blue-800">🤖 Câu trả lời từ AI</h3>
          </div>
          
          <div className="p-6">
            <div className="prose prose-blue max-w-none">
              <div 
                className="text-gray-800 leading-relaxed"
                dangerouslySetInnerHTML={{ 
                  __html: chatResponse.answer
                    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em>$1</em>')
                    .replace(/\n/g, '<br />') 
                }} 
              />
            </div>
            
            {/* Sources */}
            {chatResponse.sources && chatResponse.sources.length > 0 && (
              <div className="mt-6 pt-4 border-t border-blue-200">
                <h4 className="font-medium text-blue-800 mb-3">📖 Nguồn tham khảo:</h4>
                <div className="grid gap-3">
                  {chatResponse.sources.map((source: any, index: number) => (
                    <div key={index} className="bg-white p-3 rounded border border-blue-100">
                      <div className="font-medium text-gray-900">{source.title}</div>
                      <div className="text-sm text-gray-600 mt-1 line-clamp-2">
                        {source.preview}
                      </div>
                      <div className="text-xs text-gray-400 mt-2 flex gap-4">
                        <span>📄 Doc ID: {source.document_id}</span>
                        <span>📝 Chunk: {source.chunk_index}</span>
                        <span>📁 {source.source}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

### 🎯 Server-side API Route (Alternative approach)

```typescript
// app/api/suggest/route.ts
import { NextRequest } from 'next/server';
import { initApiClient } from '@/lib/api-config';
import { DefaultService } from '@/lib/api-client';

export async function GET(req: NextRequest) {
  try {
    initApiClient();
    
    const { searchParams } = new URL(req.url);
    const q = searchParams.get('q');
    
    if (!q) {
      return new Response('Missing query parameter', { status: 400 });
    }

    const data = await DefaultService.suggestDocumentsSuggestGet({ q });
    
    return Response.json(data);
  } catch (error) {
    console.error('API Route error:', error);
    return new Response('Internal Server Error', { status: 500 });
  }
}
```

---

## 6️⃣ Available Endpoints

Dựa trên OpenAPI spec hiện tại:

### 🔍 Document Search & Suggestions

```typescript
// Autocomplete suggestions
const suggestions = await DefaultService.suggestDocumentsSuggestGet({
  q: 'search term'
});

// Full-text search
const searchResults = await DefaultService.searchDocsDocumentsSearchGet({
  q: 'search query'
});

// Document preview
const preview = await DefaultService.previewDocDocumentsDocIdPreviewGet({
  docId: 123
});
```

### 🤖 RAG Chat

```typescript
import type { AskRequest } from '@/lib/api-client';

const request: AskRequest = {
  query: 'Tài liệu nói gì về bảo mật?',
  k_vector: 60,      // Top K vector search results
  k_keyword: 30,     // Top K keyword search results  
  rerank_top_n: 8,   // Final reranked results
  answer_language: 'vi'
};

const response = await DefaultService.askAskPost({
  requestBody: request
});

console.log('Answer:', response.answer);
console.log('Sources:', response.sources);
```

### 🔧 System Info

```typescript
// Check API capabilities
const capabilities = await DefaultService.getCapabilitiesCapabilitiesGet();

// Health check
const health = await DefaultService.healthHealthGet();
```

---

## 7️⃣ Error Handling

```typescript
import { ApiError } from '@/lib/api-client';

try {
  const response = await DefaultService.askAskPost({ requestBody });
} catch (error) {
  if (error instanceof ApiError) {
    console.error('API Error:', error.status, error.message);
    console.error('Response body:', error.body);
  } else {
    console.error('Network or other error:', error);
  }
}
```

---

## 8️⃣ Development Workflow

### Automatic Generation

```bash
# Development (auto-generates client)
npm run dev

# Production build (auto-generates client)  
npm run build

# Manual generation only
npm run gen:only
```

### .gitignore Recommendations

```gitignore
# Keep generated API client in version control for team consistency
# lib/api-client/

# Environment variables
.env.local
.env.*.local
```

---

## 🔧 Troubleshooting

### Common Issues

**❌ "404 /openapi.json"**

```bash
# Check if backend is running
curl http://localhost:8000/health
```

**❌ "CORS errors in browser"**
* Ensure CORS is configured in FastAPI backend
* Check console for specific CORS error details

**❌ "Import errors for generated types"**

```bash
# Regenerate client code
npm run gen:only

# Check if files exist
ls -la lib/api-client/
```

**❌ "Type errors with responses"**
* Backend OpenAPI spec may need better response schemas
* Use `unknown` type and manual casting as temporary solution

### Debug Tools

```typescript
// Enable request/response logging
OpenAPI.interceptors = {
  request: (options) => {
    console.log('🚀 Request:', options);
    return options;
  },
  response: (response) => {
    console.log('✅ Response:', response);
    return response;
  }
};
```

---

## 🚀 Quick Start Checklist

* [ ] ✅ Backend running at `http://localhost:8000`
* [ ] ✅ CORS configured for `http://localhost:3000`  
* [ ] ✅ Install: `npm i -D openapi-typescript-codegen`
* [ ] ✅ Add scripts to `package.json`
* [ ] ✅ Create `.env.local` with API config
* [ ] ✅ Create `lib/api-config.ts`
* [ ] ✅ Run: `npm run gen:client`
* [ ] ✅ Import and use `DefaultService` in components
* [ ] ✅ Call `initApiClient()` before API usage

**🎉 Done! You now have type-safe, auto-generated API client for your RAG system.**

# 2) Thêm script “codegen từ URL” vào package.json

Mở `package.json`, thêm:

```json
{
  "scripts": {
    "gen:client": "openapi -i http://localhost:8000/openapi.json -o ./lib/api-client -c fetch --exportSchemas true",
    "dev": "npm run gen:client && next dev",
    "build": "npm run gen:client && next build"
  }
}
```

> `openapi` là alias của `openapi-typescript-codegen`.
> Lệnh này **tự fetch** spec từ URL mỗi khi bạn `dev`/`build`, không cần lưu file JSON.

---

# 3) Cấu trúc sau khi generate

Sau khi chạy `npm run gen:client`, tool sẽ tạo thư mục:

```
lib/
  api-client/
    core/               # request, Base, OpenAPI config
    models/             # types (schemas)
    services/           # các service theo tags (vd: DocumentsService)
    index.ts            # export tổng
```

---

# 4) Cấu hình BASE URL & headers mặc định

File `lib/api-client/core/OpenAPI.ts` sẽ có object `OpenAPI`.
Tạo file cấu hình mỏng để set base & headers:

**`lib/api.ts`**

```ts
import { OpenAPI } from '@/lib/api-client';

export function initApiClient() {
  // Base URL (từ .env.local)
  OpenAPI.BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

  // Headers mặc định cho mọi request (mock user + trace)
  OpenAPI.HEADERS = {
    'X-User-Id': '1',
    'X-Request-Id': (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2),
  };
}
```

**`.env.local`**

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Gọi `initApiClient()` **trước khi** dùng services (ở đầu mỗi nơi bạn khởi dùng API, hoặc put vào một module init chung).

---

# 5) Cách gọi API

## 5.1. Gọi trực tiếp từ **Client Component** (cần bật CORS ở BE)

BE FastAPI phải bật CORS:

```py
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Client Component ví dụ (autocomplete suggest)**

```tsx
'use client';

import { useEffect, useState } from 'react';
import { initApiClient } from '@/lib/api';
import { DocumentsService } from '@/lib/api-client'; // tên service do codegen sinh ra

type SuggestItem = { id: number; title: string };

export default function SuggestBox() {
  const [q, setQ] = useState('');
  const [items, setItems] = useState<SuggestItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    initApiClient();
  }, []);

  useEffect(() => {
    if (!q) { setItems([]); return; }
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      try {
        setLoading(true);
        const res = await DocumentsService.suggestDocumentsSuggestGet({ q }); // tên method = operationId
        setItems(res as unknown as SuggestItem[]); // (nếu spec chưa có schema, có thể xài unknown)
      } finally {
        setLoading(false);
      }
    }, 200);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [q]);

  return (
    <div className="p-4">
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search..." />
      {loading && <div>Loading...</div>}
      <ul>
        {items.map(it => <li key={it.id}>{it.title}</li>)}
      </ul>
    </div>
  );
}
```

> ⚠️ Nếu trong spec của bạn response chưa có schema, codegen sẽ không đoán type; bạn có thể:
>
> * Bổ sung schemas vào OpenAPI (khuyến nghị), **hoặc**
> * Tạm thời cast `unknown` → type thủ công như trên.

## 5.2. Gọi qua **Server Route Handler** (khỏi lo CORS, recommended)

**`app/api/suggest/route.ts`**

```ts
import { NextRequest } from 'next/server';
import { initApiClient } from '@/lib/api';
import { DocumentsService } from '@/lib/api-client';

export async function GET(req: NextRequest) {
  initApiClient();
  const { searchParams } = new URL(req.url);
  const q = searchParams.get('q') ?? '';
  if (!q) return new Response('Missing q', { status: 400 });

  const data = await DocumentsService.suggestDocumentsSuggestGet({ q });
  return Response.json(data);
}
```

**Client gọi nội bộ:**

```ts
const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
const items = await res.json();
```

---

# 6) Gọi các endpoint khác (ví dụ)

**Search docs (preview ngắn):**

```ts
import { DocumentsService } from '@/lib/api-client';

const docs = await DocumentsService.searchDocsDocumentsSearchGet({ q: 'ISO 27001' });
```

**Preview 1 doc:**

```ts
import { DocumentsService } from '@/lib/api-client';

const preview = await DocumentsService.previewDocDocumentsDocIdPreviewGet({ doc_id: 12 });
```

**Chatbot RAG:**

```ts
import { RagService } from '@/lib/api-client'; // tuỳ tag trong spec của bạn, có thể là DefaultService

const answer = await RagService.askAskPost({
  requestBody: {
    query: 'MFA ở đâu?',
    k_vector: 60,
    k_keyword: 30,
    answer_language: 'vi',
  }
});
```

> Tên `*Service` và method phụ thuộc **tags** + **operationId** trong OpenAPI. Nếu bạn muốn tên đẹp, đặt `tags` và `operationId` có nghĩa trong spec.

---

# 7) Tự động hoá & CI/CD

* **Dev/Build** đã auto chạy `gen:client`.
* **CI**: đảm bảo backend endpoint `/openapi.json` reachable (hoặc dùng biến môi trường trỏ staging).
* Nếu muốn “pin” spec theo build (tránh BE đang down), thêm fallback:

  * Tạo script nhỏ: fetch URL → nếu fail thì xài bản cache trong repo.

---

# 8) .gitignore & cache

* **NÊN commit** thư mục `lib/api-client/` để team FE không phụ thuộc kết nối đến BE lúc dev.

  * Nếu không commit, mỗi dev phải chạy backend trước khi `npm run dev`.
* Nếu commit, mỗi lần BE đổi spec, build của FE sẽ regenerate và diff nhỏ.

---

# 9) Troubleshooting nhanh

* **404 `/openapi.json`**: BE chưa chạy hoặc URL khác → sửa script input.
* **CORS khi gọi trực tiếp từ client**: bật CORS ở FastAPI, hoặc dùng **server route proxy**.
* **Tên method khó đọc**: chỉnh `operationId` trong spec (vd: `suggestDocuments`, `searchDocuments`, `previewDoc`, `ask`).
* **Thiếu types ở response**: bổ sung `responses.200.content.application/json.schema` trong spec → lần sau codegen ra types đẹp.

---

# 10) Tóm tắt “1 phút thiết lập”

1. `npm i -D openapi-typescript-codegen`
2. Thêm script:

   ```json
   "gen:client":"openapi -i http://localhost:8000/openapi.json -o ./lib/api-client -c fetch --exportSchemas true",
   "dev":"npm run gen:client && next dev",
   "build":"npm run gen:client && next build"
   ```

3. `.env.local`: `NEXT_PUBLIC_API_BASE=http://localhost:8000`
4. Tạo `lib/api.ts` với `initApiClient()` và headers default.
5. Gọi `DocumentsService.*` / `RagService.*` theo **operationId** (hoặc qua server route proxy).

Xong — từ giờ FE của bạn **luôn đọc spec trực tiếp từ URL** mỗi lần dev/build, type-safe, ít công sức bảo trì.
