# 🚀 Hướng Dẫn Implementation API Endpoints cho Chatnary Backend

## 📋 **Tổng Quan Tình Hình**

### **Current State Analysis**

- ✅ **PostgreSQL + pgvector**: Hybrid search hoạt động tốt
- ✅ **Basic RAG**: `/ask` endpoint đã implement  
- ❌ **Missing**: Authentication, File Management, User System
- ❌ **Gap**: Frontend expects full API theo SYSTEM_ARCHITECTURE.md

### **Implementation Strategy**

**Approach**: Giữ nguyên tech stack hiện tại (PostgreSQL) nhưng implement đầy đủ API endpoints để tương thích với frontend. Không migrate sang MongoDB để tránh breaking changes.

---

## 🎯 **Roadmap Implementation (Theo Độ Ưu Tiên)**

### **Phase 1: Core Authentication & User Management** ⭐⭐⭐

```
🔐 Authentication System
├── JWT-based auth với PostgreSQL
├── User registration/login
├── Password hashing với bcrypt
└── Middleware cho protected routes
```

### **Phase 2: File Management System** ⭐⭐⭐

```
📁 File Operations  
├── Upload files với validation
├── Store metadata trong PostgreSQL
├── Download/delete files
└── Link files với users
```

### **Phase 3: Enhanced RAG Features** ⭐⭐

```
🤖 Advanced Chat
├── Per-user document filtering
├── Chat history tracking
├── Multi-document conversations
└── Source citation improvements
```

### **Phase 4: Additional Features** ⭐

```
🔍 Search & Analytics
├── Full-text search (PostgreSQL FTS)
├── User statistics
├── System monitoring
└── Advanced query options
```

---

## 🔧 **Phase 1: Authentication Implementation**

### **1.1 Database Schema Changes**

```sql
-- File: db/migrations/001_add_users_auth.sql

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Add user_id to documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_email VARCHAR(255);

-- Add user_id to chunks table for filtering
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_user_id ON chunks(user_id);

-- Chat history table
CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources JSONB,
    model_used VARCHAR(50),
    processing_time FLOAT,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id, created_at DESC);
```

### **1.2 Authentication Dependencies**

```python
# File: api/app/auth.py

import jwt
import bcrypt
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from .settings import settings
from .db import get_conn

security = HTTPBearer()

class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password với bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    @staticmethod
    def create_jwt_token(user_id: int, email: str) -> str:
        """Tạo JWT token"""
        payload = {
            'user_id': user_id,
            'email': email,
            'exp': datetime.utcnow() + timedelta(days=settings.JWT_EXPIRATION_DAYS),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm='HS256')
    
    @staticmethod
    def decode_jwt_token(token: str) -> dict:
        """Decode JWT token"""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency để get current user từ JWT token"""
    token = credentials.credentials
    payload = AuthService.decode_jwt_token(token)
    
    user_id = payload.get('user_id')
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    # Get user from database
    with get_conn() as conn:
        user = conn.execute(
            "SELECT id, email, full_name, role, is_active FROM users WHERE id = %s",
            (user_id,)
        ).fetchone()
        
        if not user or not user[4]:  # is_active check
            raise HTTPException(status_code=401, detail="User not found or inactive")
    
    return {
        'id': user[0],
        'email': user[1], 
        'full_name': user[2],
        'role': user[3],
        'is_active': user[4]
    }

# Optional auth for public endpoints
async def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))):
    """Optional authentication - trả về None nếu không có token"""
    if not credentials:
        return None
    return await get_current_user(credentials)
```

### **1.3 Auth API Endpoints**

```python
# File: api/app/routes/auth.py

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from ..auth import AuthService, get_current_user
from ..db import get_conn

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Request/Response Models
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    created_at: str

class LoginResponse(BaseModel):
    success: bool
    message: str
    user: UserResponse
    token: str

class ApiResponse(BaseModel):
    success: bool
    message: str

@router.post("/register", response_model=LoginResponse)
async def register(req: UserRegisterRequest):
    """Đăng ký user mới"""
    
    # Validate password strength
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    with get_conn() as conn:
        # Check if email exists
        existing = conn.execute(
            "SELECT id FROM users WHERE email = %s", (req.email,)
        ).fetchone()
        
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hash password và insert user
        password_hash = AuthService.hash_password(req.password)
        
        user_id = conn.execute(
            """INSERT INTO users (email, password_hash, full_name) 
               VALUES (%s, %s, %s) RETURNING id""",
            (req.email, password_hash, req.full_name)
        ).fetchone()[0]
        
        conn.commit()
        
        # Get full user data
        user = conn.execute(
            "SELECT id, email, full_name, role, created_at FROM users WHERE id = %s",
            (user_id,)
        ).fetchone()
    
    # Tạo JWT token
    token = AuthService.create_jwt_token(user[0], user[1])
    
    return LoginResponse(
        success=True,
        message="Registration successful",
        user=UserResponse(
            id=user[0],
            email=user[1],
            full_name=user[2],
            role=user[3],
            created_at=user[4].isoformat()
        ),
        token=token
    )

@router.post("/login", response_model=LoginResponse)
async def login(req: UserLoginRequest):
    """Đăng nhập user"""
    
    with get_conn() as conn:
        user = conn.execute(
            "SELECT id, email, password_hash, full_name, role, is_active FROM users WHERE email = %s",
            (req.email,)
        ).fetchone()
        
        if not user or not user[5]:  # not found or not active
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Verify password
        if not AuthService.verify_password(req.password, user[2]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Update last login
        conn.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
            (user[0],)
        )
        conn.commit()
    
    # Tạo JWT token
    token = AuthService.create_jwt_token(user[0], user[1])
    
    return LoginResponse(
        success=True,
        message="Login successful",
        user=UserResponse(
            id=user[0],
            email=user[1],
            full_name=user[3],
            role=user[4],
            created_at=""  # Not needed for login
        ),
        token=token
    )

@router.get("/profile", response_model=UserResponse)
async def get_profile(current_user = Depends(get_current_user)):
    """Lấy thông tin profile của user hiện tại"""
    
    with get_conn() as conn:
        user = conn.execute(
            "SELECT id, email, full_name, role, created_at FROM users WHERE id = %s",
            (current_user['id'],)
        ).fetchone()
    
    return UserResponse(
        id=user[0],
        email=user[1],
        full_name=user[2],
        role=user[3],
        created_at=user[4].isoformat()
    )

@router.put("/profile", response_model=ApiResponse)
async def update_profile(
    req: dict,  # {"full_name": "New Name"}
    current_user = Depends(get_current_user)
):
    """Cập nhật profile"""
    
    full_name = req.get('full_name')
    if not full_name or len(full_name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Full name is required")
    
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET full_name = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (full_name.strip(), current_user['id'])
        )
        conn.commit()
    
    return ApiResponse(success=True, message="Profile updated successfully")
```

### **1.4 Update Main App**

```python
# File: api/app/main.py (additions)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from .routes import auth
from .auth import get_current_user, get_current_user_optional

app = FastAPI(title="RAG Chatnary Backend")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include auth routes
app.include_router(auth.router)

# Update existing ask endpoint to use auth
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, current_user = Depends(get_current_user_optional)):
    """Ask question với optional authentication"""
    
    # Filter documents by user if authenticated
    user_filter = None
    if current_user:
        user_filter = current_user['id']
    
    candidates = hybrid_search(
        req.query, 
        k_vec=req.k_vector, 
        k_kw=req.k_keyword,
        user_id=user_filter  # Add user filtering
    )
    
    # ... rest of the existing logic
```

### **1.5 Update Settings**

```python
# File: api/app/settings.py (additions)

import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Existing settings...
    
    # Authentication
    JWT_SECRET: str = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
    JWT_EXPIRATION_DAYS: int = int(os.getenv("JWT_EXPIRATION_DAYS", "7"))
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 📁 **Phase 2: File Management Implementation**

### **2.1 File Upload System**

```python
# File: api/app/routes/files.py

import os
import uuid
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from ..auth import get_current_user
from ..db import get_conn
from ..ingest import process_document_for_user  # We'll create this

router = APIRouter(prefix="/api/files", tags=["File Management"])

# Response Models
class FileMetadata(BaseModel):
    id: str
    original_name: str
    filename: str
    size: int
    mimetype: str
    upload_time: str
    indexed: bool
    indexed_at: Optional[str]
    chunk_count: Optional[int]

class FileUploadResponse(BaseModel):
    success: bool
    message: str
    file: FileMetadata

class FileListResponse(BaseModel):
    success: bool
    data: dict

class FileStatsResponse(BaseModel):
    success: bool
    stats: dict

# Upload endpoint
@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user)
):
    """Upload file và trigger RAG processing"""
    
    # Validate file type
    allowed_types = {
        'application/pdf': 'pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'application/msword': 'doc',
        'text/plain': 'txt',
        'text/markdown': 'md'
    }
    
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, 
            detail=f"File type {file.content_type} not supported. Allowed: PDF, DOCX, DOC, TXT, MD"
        )
    
    # Validate file size (10MB max)
    if file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 10MB")
    
    # Generate unique filename
    file_extension = allowed_types[file.content_type]
    unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{file.filename}"
    
    # Ensure uploads directory exists
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, unique_filename)
    
    # Save file to disk
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Save metadata to database
    file_id = str(uuid.uuid4())
    
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO documents (id, title, source, user_id, user_email, original_name, 
                                     filename, file_size, mimetype, upload_time, indexed, path) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                file_id,
                file.filename,  # title = original filename
                file_path,      # source = file path
                current_user['id'],
                current_user['email'],
                file.filename,
                unique_filename,
                file.size,
                file.content_type,
                datetime.now(),
                False,  # indexed = false initially
                file_path
            )
        )
        conn.commit()
    
    # Trigger background processing
    try:
        await process_document_for_user(file_id, file_path, current_user['id'])
    except Exception as e:
        # Log error but don't fail the upload
        print(f"Background processing failed for {file_id}: {str(e)}")
    
    return FileUploadResponse(
        success=True,
        message="File uploaded successfully. Processing in background.",
        file=FileMetadata(
            id=file_id,
            original_name=file.filename,
            filename=unique_filename,
            size=file.size,
            mimetype=file.content_type,
            upload_time=datetime.now().isoformat(),
            indexed=False,
            indexed_at=None,
            chunk_count=None
        )
    )

# List files with pagination
@router.get("", response_model=FileListResponse)
async def list_files(
    page: int = 1,
    limit: int = 20,
    sort_by: str = "upload_time",
    sort_order: str = "desc",
    current_user = Depends(get_current_user)
):
    """List user's files với pagination"""
    
    offset = (page - 1) * limit
    order_direction = "DESC" if sort_order.lower() == "desc" else "ASC"
    
    # Validate sort_by column
    allowed_sort_columns = ["upload_time", "title", "file_size", "indexed"]
    if sort_by not in allowed_sort_columns:
        sort_by = "upload_time"
    
    with get_conn() as conn:
        # Get total count
        total = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE user_id = %s",
            (current_user['id'],)
        ).fetchone()[0]
        
        # Get files
        files = conn.execute(f"""
            SELECT id, title, original_name, filename, file_size, mimetype, 
                   upload_time, indexed, indexed_at, chunk_count
            FROM documents 
            WHERE user_id = %s 
            ORDER BY {sort_by} {order_direction}
            LIMIT %s OFFSET %s
        """, (current_user['id'], limit, offset)).fetchall()
    
    file_list = [
        FileMetadata(
            id=f[0],
            original_name=f[2],
            filename=f[3],
            size=f[4],
            mimetype=f[5],
            upload_time=f[6].isoformat(),
            indexed=f[7],
            indexed_at=f[8].isoformat() if f[8] else None,
            chunk_count=f[9]
        )
        for f in files
    ]
    
    return FileListResponse(
        success=True,
        data={
            "files": file_list,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
    )

# Get file details
@router.get("/{file_id}", response_model=FileMetadata)
async def get_file_details(
    file_id: str,
    current_user = Depends(get_current_user)
):
    """Lấy chi tiết file"""
    
    with get_conn() as conn:
        file_data = conn.execute(
            """SELECT id, title, original_name, filename, file_size, mimetype,
                      upload_time, indexed, indexed_at, chunk_count
               FROM documents 
               WHERE id = %s AND user_id = %s""",
            (file_id, current_user['id'])
        ).fetchone()
        
        if not file_data:
            raise HTTPException(status_code=404, detail="File not found")
    
    return FileMetadata(
        id=file_data[0],
        original_name=file_data[2],
        filename=file_data[3],
        size=file_data[4],
        mimetype=file_data[5],
        upload_time=file_data[6].isoformat(),
        indexed=file_data[7],
        indexed_at=file_data[8].isoformat() if file_data[8] else None,
        chunk_count=file_data[9]
    )

# Download file
@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    current_user = Depends(get_current_user)
):
    """Download file gốc"""
    
    with get_conn() as conn:
        file_data = conn.execute(
            "SELECT path, original_name, mimetype FROM documents WHERE id = %s AND user_id = %s",
            (file_id, current_user['id'])
        ).fetchone()
        
        if not file_data:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path, original_name, mimetype = file_data
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=original_name,
        media_type=mimetype
    )

# Delete file
@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    current_user = Depends(get_current_user)
):
    """Xóa file và associated data"""
    
    with get_conn() as conn:
        # Get file info
        file_data = conn.execute(
            "SELECT path FROM documents WHERE id = %s AND user_id = %s",
            (file_id, current_user['id'])
        ).fetchone()
        
        if not file_data:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path = file_data[0]
        
        # Delete from database (cascading will handle chunks)
        conn.execute("DELETE FROM chunks WHERE document_id = (SELECT id FROM documents WHERE id = %s)", (file_id,))
        conn.execute("DELETE FROM documents WHERE id = %s", (file_id,))
        conn.commit()
        
        # Delete physical file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Failed to delete physical file {file_path}: {str(e)}")
    
    return {"success": True, "message": "File deleted successfully"}

# File statistics
@router.get("/stats", response_model=FileStatsResponse)
async def get_file_stats(current_user = Depends(get_current_user)):
    """Thống kê files của user"""
    
    with get_conn() as conn:
        stats = conn.execute("""
            SELECT 
                COUNT(*) as total_files,
                COUNT(*) FILTER (WHERE indexed = true) as indexed_files,
                COALESCE(SUM(file_size), 0) as total_size,
                COALESCE(SUM(chunk_count), 0) as total_chunks
            FROM documents 
            WHERE user_id = %s
        """, (current_user['id'],)).fetchone()
    
    return FileStatsResponse(
        success=True,
        stats={
            "total_files": stats[0],
            "indexed_files": stats[1],
            "total_size": stats[2],
            "total_chunks": stats[3],
            "processing_rate": round((stats[1] / stats[0] * 100) if stats[0] > 0 else 0, 1)
        }
    )
```

### **2.2 Enhanced Document Processing**

```python
# File: api/app/ingest.py (enhanced version)

import asyncio
from typing import Optional
from .chunker import chunk_document
from .llm import embed_texts
from .db import get_conn

async def process_document_for_user(file_id: str, file_path: str, user_id: int):
    """Process document cho specific user với user isolation"""
    
    try:
        # Extract và chunk text
        chunks = chunk_document(file_path)
        
        if not chunks:
            # Mark as failed
            with get_conn() as conn:
                conn.execute(
                    "UPDATE documents SET processing_error = %s WHERE id = %s",
                    ("No text content found", file_id)
                )
                conn.commit()
            return
        
        # Generate embeddings
        texts = [chunk["text"] for chunk in chunks]
        embeddings = embed_texts(texts)
        
        if not embeddings or len(embeddings) != len(chunks):
            raise Exception("Failed to generate embeddings")
        
        # Save chunks to database với user_id
        with get_conn() as conn:
            # Get document_id (numeric)
            doc_result = conn.execute(
                "SELECT id FROM documents WHERE id = %s", (file_id,)
            ).fetchone()
            
            if not doc_result:
                raise Exception("Document not found")
            
            document_id = doc_result[0]
            
            # Insert chunks với embeddings và user_id
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                conn.execute(
                    """INSERT INTO chunks (document_id, chunk_index, text, embedding, user_id)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (document_id, i, chunk["text"], embedding, user_id)
                )
            
            # Mark document as indexed
            conn.execute(
                """UPDATE documents 
                   SET indexed = true, indexed_at = CURRENT_TIMESTAMP, 
                       chunk_count = %s, processing_error = NULL
                   WHERE id = %s""",
                (len(chunks), file_id)
            )
            conn.commit()
            
        print(f"Successfully processed document {file_id} with {len(chunks)} chunks")
        
    except Exception as e:
        # Mark as failed với error message
        with get_conn() as conn:
            conn.execute(
                "UPDATE documents SET processing_error = %s WHERE id = %s",
                (str(e), file_id)
            )
            conn.commit()
        
        print(f"Failed to process document {file_id}: {str(e)}")
        raise
```

### **2.3 Update Retrieval for User Filtering**

```python
# File: api/app/retrieval.py (update existing)

def hybrid_search(query: str, k: int = 8, k_vec: int = 40, k_kw: int = 20, user_id: Optional[int] = None) -> List[Dict]:
    """
    Hybrid search với optional user filtering
    """
    
    # Vector search với user filter
    vec_hits = _vector_candidates(query, k_vec, user_id)
    
    # Keyword search với user filter  
    kw_hits = _keyword_candidates_normalized(query, k_kw, user_id)
    
    # Merge and deduplicate
    merged = _merge_candidates(vec_hits, kw_hits)
    
    if not merged:
        return []
    
    # Rerank with cohere
    if len(merged) > 1:
        try:
            docs = [{"text": hit["text"]} for hit in merged]
            reranked = rerank(query, docs, top_n=min(k, len(docs)))
            
            # Map back to original candidates
            result = []
            for doc in reranked:
                for candidate in merged:
                    if candidate["text"] == doc["text"]:
                        result.append(candidate)
                        break
            return result[:k]
        except Exception as e:
            print(f"Rerank failed: {e}")
            return merged[:k]
    
    return merged[:k]

def _vector_candidates(query: str, limit: int = 40, user_id: Optional[int] = None) -> List[Dict]:
    """Vector search với user filtering"""
    query_emb = embed_texts([query])[0]
    
    sql_base = """
        SELECT c.id, c.document_id, c.chunk_index, c.text, 
               (c.embedding <=> %s) AS distance
        FROM chunks c
    """
    
    params = [query_emb]
    
    if user_id:
        sql_base += " WHERE c.user_id = %s"
        params.append(user_id)
    
    sql_base += " ORDER BY distance LIMIT %s"
    params.append(limit)
    
    with get_conn() as conn:
        rows = conn.execute(sql_base, params).fetchall()
    
    return [
        {
            "id": r[0],
            "document_id": r[1],
            "chunk_index": r[2],
            "text": r[3],
            "score": 1.0 - float(r[4])  # Convert distance to similarity
        }
        for r in rows
    ]

def _keyword_candidates_normalized(query: str, limit: int = 20, user_id: Optional[int] = None) -> List[Dict]:
    """Keyword search với user filtering"""
    normalized_query = normalize_vietnamese(query)
    
    sql_base = """
        SELECT c.id, c.document_id, c.chunk_index, c.text, 
               similarity(c.content_normalized, %s) AS score
        FROM chunks c
        WHERE c.content_normalized ILIKE %s
    """
    
    params = [normalized_query, f'%{normalized_query}%']
    
    if user_id:
        sql_base += " AND c.user_id = %s"
        params.append(user_id)
    
    sql_base += " ORDER BY score DESC LIMIT %s"
    params.append(limit)
    
    with get_conn() as conn:
        rows = conn.execute(sql_base, params).fetchall()
    
    return [
        {
            "id": r[0],
            "document_id": r[1],
            "chunk_index": r[2],
            "text": r[3],
            "score": float(r[4])
        }
        for r in rows
    ]
```

---

## 🤖 **Phase 3: Enhanced Chat Features**

### **3.1 Chat History System**

```python
# File: api/app/routes/chat.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from ..auth import get_current_user, get_current_user_optional
from ..retrieval import hybrid_search
from ..llm import rerank, generate_answer
from ..db import get_conn

router = APIRouter(prefix="/api/chat", tags=["AI Chat"])

# Request/Response Models
class ChatRequest(BaseModel):
    query: str
    file_ids: Optional[List[str]] = None  # Specific files to search
    model: str = "gemini"  # gemini or openai
    top_k: int = 5
    k_vector: int = 40
    k_keyword: int = 20
    answer_language: str = "vi"

class ChatResponse(BaseModel):
    success: bool
    answer: str
    sources: List[Dict]
    processing_time: float
    model_used: str
    query: str

class ChatHistoryResponse(BaseModel):
    success: bool
    data: List[Dict]
    pagination: Dict

# Main chat endpoint
@router.post("", response_model=ChatResponse)
async def chat_with_documents(
    req: ChatRequest,
    current_user = Depends(get_current_user_optional)
):
    """Chat với documents sử dụng RAG"""
    import time
    start_time = time.time()
    
    try:
        # Determine user filter
        user_filter = current_user['id'] if current_user else None
        
        # If specific file_ids requested, add to filter
        document_filter = None
        if req.file_ids and current_user:
            with get_conn() as conn:
                # Verify user owns these files
                file_docs = conn.execute(
                    """SELECT id FROM documents 
                       WHERE id = ANY(%s) AND user_id = %s""",
                    (req.file_ids, current_user['id'])
                ).fetchall()
                document_filter = [doc[0] for doc in file_docs]
        
        # Perform hybrid search
        candidates = hybrid_search(
            req.query,
            k=req.top_k,
            k_vec=req.k_vector,
            k_kw=req.k_keyword,
            user_id=user_filter,
            document_ids=document_filter
        )
        
        if not candidates:
            return ChatResponse(
                success=True,
                answer="Tôi không tìm thấy thông tin liên quan trong tài liệu. Vui lòng thử câu hỏi khác.",
                sources=[],
                processing_time=time.time() - start_time,
                model_used=req.model,
                query=req.query
            )
        
        # Add document metadata
        if candidates:
            doc_ids = list({c["document_id"] for c in candidates})
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, title, source FROM documents WHERE id = ANY(%s)",
                    (doc_ids,)
                ).fetchall()
            
            meta = {r[0]: {"title": r[1], "source": r[2]} for r in rows}
            for c in candidates:
                c.setdefault("meta", {}).update(meta.get(c["document_id"], {}))
        
        # Prepare docs for rerank
        docs = [{"text": c["text"], "meta": c.get("meta", {})} for c in candidates]
        
        # Rerank
        top_docs = rerank(req.query, docs, top_n=req.top_k)
        
        # Generate answer
        answer = generate_answer(req.query, top_docs, language=req.answer_language, model=req.model)
        
        # Format sources
        sources = [
            {
                "document_id": d["meta"].get("document_id"),
                "chunk_index": d["meta"].get("chunk_index"),
                "title": d["meta"].get("title"),
                "source": d["meta"].get("source"),
                "preview": d["text"][:240] + "..." if len(d["text"]) > 240 else d["text"]
            }
            for d in top_docs
        ]
        
        processing_time = time.time() - start_time
        
        # Log conversation if user is authenticated
        if current_user:
            await _log_conversation(
                user_id=current_user['id'],
                query=req.query,
                answer=answer,
                sources=sources,
                model_used=req.model,
                processing_time=processing_time
            )
        
        return ChatResponse(
            success=True,
            answer=answer,
            sources=sources,
            processing_time=processing_time,
            model_used=req.model,
            query=req.query
        )
        
    except Exception as e:
        return ChatResponse(
            success=False,
            answer=f"Đã xảy ra lỗi khi xử lý câu hỏi: {str(e)}",
            sources=[],
            processing_time=time.time() - start_time,
            model_used=req.model,
            query=req.query
        )

# Chat history
@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    limit: int = 20,
    offset: int = 0,
    current_user = Depends(get_current_user)
):
    """Lấy lịch sử chat với pagination"""
    
    with get_conn() as conn:
        # Get total count
        total = conn.execute(
            "SELECT COUNT(*) FROM chat_history WHERE user_id = %s",
            (current_user['id'],)
        ).fetchone()[0]
        
        # Get chat history
        history = conn.execute(
            """SELECT query, answer, sources, model_used, processing_time, created_at
               FROM chat_history 
               WHERE user_id = %s 
               ORDER BY created_at DESC
               LIMIT %s OFFSET %s""",
            (current_user['id'], limit, offset)
        ).fetchall()
    
    chat_list = [
        {
            "query": h[0],
            "answer": h[1],
            "sources": h[2],  # JSONB field
            "model_used": h[3],
            "processing_time": h[4],
            "created_at": h[5].isoformat()
        }
        for h in history
    ]
    
    return ChatHistoryResponse(
        success=True,
        data=chat_list,
        pagination={
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + limit < total
        }
    )

# Available models
@router.get("/models")
async def get_available_models():
    """Kiểm tra available AI models"""
    
    models = {
        "gemini": True,  # Always available (free tier)
        "openai": bool(os.getenv("OPENAI_API_KEY"))
    }
    
    return {
        "success": True,
        "models": models,
        "message": "Available AI models"
    }

# Process document manually
@router.post("/process-document/{file_id}")
async def reprocess_document(
    file_id: str,
    current_user = Depends(get_current_user)
):
    """Re-process document nếu failed lần đầu"""
    
    with get_conn() as conn:
        file_data = conn.execute(
            "SELECT path, indexed FROM documents WHERE id = %s AND user_id = %s",
            (file_id, current_user['id'])
        ).fetchone()
        
        if not file_data:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_path, indexed = file_data
        
        if indexed:
            return {"success": True, "message": "Document already processed"}
    
    # Trigger reprocessing
    try:
        await process_document_for_user(file_id, file_path, current_user['id'])
        return {"success": True, "message": "Document processing started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

# Helper function
async def _log_conversation(
    user_id: int,
    query: str,
    answer: str,
    sources: List[Dict],
    model_used: str,
    processing_time: float
):
    """Log conversation to database"""
    
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO chat_history 
               (user_id, query, answer, sources, model_used, processing_time)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, query, answer, sources, model_used, processing_time)
        )
        conn.commit()
```

### **3.2 Update Main App với All Routes**

```python
# File: api/app/main.py (final version)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from .routes import auth, files, chat
from .auth import get_current_user_optional

app = FastAPI(
    title="Chatnary RAG Backend",
    description="RAG-powered document chat system",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(auth.router)
app.include_router(files.router)
app.include_router(chat.router)

# Root endpoint
@app.get("/")
def root():
    return {
        "message": "Chatnary RAG Backend API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "features": {
            "authentication": True,
            "file_management": True,
            "rag_chat": True,
            "chat_history": True,
            "multi_user": True
        }
    }

# Health check (updated)
@app.get("/health")
def health():
    try:
        from .db import get_conn
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return {
            "status": "healthy",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "backend": "FastAPI + PostgreSQL",
            "ai_integrated": True
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Legacy ask endpoint (for backward compatibility)
@app.post("/ask")
def ask_legacy(req: dict, current_user = Depends(get_current_user_optional)):
    """Legacy ask endpoint cho backward compatibility"""
    
    from .retrieval import hybrid_search
    from .llm import rerank, generate_answer
    
    query = req.get("query", "")
    if not query:
        return {"answer": "Query is required", "sources": []}
    
    user_filter = current_user['id'] if current_user else None
    
    candidates = hybrid_search(
        query,
        k_vec=req.get("k_vector", 40),
        k_kw=req.get("k_keyword", 20),
        user_id=user_filter
    )
    
    if not candidates:
        return {"answer": "Không tìm thấy thông tin liên quan.", "sources": []}
    
    # Add metadata
    if candidates:
        doc_ids = list({c["document_id"] for c in candidates})
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, title, source FROM documents WHERE id = ANY(%s)",
                (doc_ids,)
            ).fetchall()
        
        meta = {r[0]: {"title": r[1], "source": r[2]} for r in rows}
        for c in candidates:
            c.setdefault("meta", {}).update(meta.get(c["document_id"], {}))
    
    # Rerank và generate
    docs = [{"text": c["text"], "meta": c.get("meta", {})} for c in candidates]
    top = rerank(query, docs, top_n=req.get("rerank_top_n", 8))
    answer = generate_answer(query, top, language=req.get("answer_language", "vi"))
    
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
    
    return {"answer": answer, "sources": sources}
```

---

## 🔍 **Phase 4: Search & Additional Features**

### **4.1 Search System**

```python
# File: api/app/routes/search.py

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Dict, Optional
from ..auth import get_current_user_optional
from ..db import get_conn

router = APIRouter(prefix="/api/search", tags=["Search"])

class SearchResponse(BaseModel):
    success: bool
    data: Dict
    
# Full-text search
@router.get("", response_model=SearchResponse)
async def search_documents(
    query: str = Query(..., description="Search query"),
    limit: int = Query(20, description="Number of results"),
    offset: int = Query(0, description="Offset for pagination"),
    current_user = Depends(get_current_user_optional)
):
    """Full-text search trong documents"""
    
    if not query.strip():
        return SearchResponse(
            success=False,
            data={"error": "Query cannot be empty"}
        )
    
    user_filter = current_user['id'] if current_user else None
    
    # PostgreSQL Full-Text Search
    sql_base = """
        SELECT d.id, d.title, d.original_name, c.text, c.chunk_index,
               ts_rank(to_tsvector('simple', c.text), plainto_tsquery('simple', %s)) as rank
        FROM documents d
        JOIN chunks c ON d.id = c.document_id
        WHERE to_tsvector('simple', c.text) @@ plainto_tsquery('simple', %s)
    """
    
    params = [query, query]
    
    if user_filter:
        sql_base += " AND d.user_id = %s"
        params.append(user_filter)
    
    sql_base += " ORDER BY rank DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    with get_conn() as conn:
        # Get total count first
        count_sql = sql_base.replace("SELECT d.id, d.title, d.original_name, c.text, c.chunk_index, ts_rank", "SELECT COUNT(*)")
        count_sql = count_sql.split(" ORDER BY")[0]  # Remove ORDER BY and LIMIT
        
        total = conn.execute(count_sql, params[:-2]).fetchone()[0]
        
        # Get results
        results = conn.execute(sql_base, params).fetchall()
    
    hits = [
        {
            "document_id": r[0],
            "title": r[1],
            "filename": r[2],
            "text": r[3],
            "chunk_index": r[4],
            "relevance_score": float(r[5]),
            "preview": r[3][:200] + "..." if len(r[3]) > 200 else r[3]
        }
        for r in results
    ]
    
    return SearchResponse(
        success=True,
        data={
            "hits": hits,
            "query": query,
            "total": total,
            "limit": limit,
            "offset": offset,
            "processing_time_ms": 0  # Could add timing
        }
    )

# Search suggestions
@router.get("/suggestions")
async def get_search_suggestions(
    q: str = Query(..., description="Partial query for suggestions"),
    current_user = Depends(get_current_user_optional)
):
    """Auto-complete suggestions cho search"""
    
    if len(q.strip()) < 2:
        return {"success": True, "suggestions": []}
    
    user_filter = current_user['id'] if current_user else None
    
    # Simple suggestion based on document titles và frequent terms
    sql_base = """
        SELECT DISTINCT d.title
        FROM documents d
        WHERE LOWER(d.title) LIKE LOWER(%s)
    """
    
    params = [f'%{q}%']
    
    if user_filter:
        sql_base += " AND d.user_id = %s"
        params.append(user_filter)
    
    sql_base += " LIMIT 10"
    
    with get_conn() as conn:
        suggestions = conn.execute(sql_base, params).fetchall()
    
    return {
        "success": True,
        "suggestions": [s[0] for s in suggestions]
    }
```

### **4.2 Enhanced Settings & Environment**

```python
# File: .env.example

# Application
DEBUG=False
FRONTEND_URL=http://localhost:3000

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/chatnary_db

# Authentication
JWT_SECRET=your-super-secret-jwt-key-change-in-production
JWT_EXPIRATION_DAYS=7

# AI Services
OPENAI_API_KEY=sk-your-openai-key-here
COHERE_API_KEY=your-cohere-key-for-reranking

# File Upload
MAX_FILE_SIZE=10485760
UPLOAD_DIR=uploads

# Performance
MAX_CONCURRENT_REQUESTS=10
REQUEST_TIMEOUT=30
```

### **4.3 Production Deployment Guide**

```yaml
# File: docker-compose.prod.yml

version: '3.8'

services:
  chatnary-backend:
    build: 
      context: .
      dockerfile: Dockerfile.prod
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://chatnary:${DB_PASSWORD}@postgres:5432/chatnary_db
      - JWT_SECRET=${JWT_SECRET}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - COHERE_API_KEY=${COHERE_API_KEY}
    volumes:
      - ./uploads:/app/uploads
      - ./logs:/app/logs
    depends_on:
      - postgres
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_DB=chatnary_db
      - POSTGRES_USER=chatnary
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - chatnary-backend
    restart: unless-stopped

volumes:
  postgres_data:
```

---

## 🚀 **Implementation Timeline & Priorities**

### **Week 1: Authentication Foundation**

- ✅ Database schema setup
- ✅ JWT authentication system  
- ✅ User registration/login endpoints
- ✅ Basic middleware và security

### **Week 2: File Management**

- ✅ File upload với validation
- ✅ User-specific file isolation
- ✅ File listing và metadata
- ✅ Download/delete functionality

### **Week 3: Enhanced RAG**

- ✅ User-filtered search
- ✅ Chat history tracking
- ✅ Multiple file support
- ✅ Improved source citations

### **Week 4: Polish & Deploy**

- ✅ Search functionality
- ✅ Performance optimization
- ✅ Error handling improvements
- ✅ Production deployment

---

## 🎯 **Key Optimization Recommendations**

### **1. Performance Optimizations**

```python
# Connection pooling
from sqlalchemy.pool import QueuePool

# Async file processing
import asyncio
async def batch_process_documents(file_ids: List[str]):
    tasks = [process_document_for_user(fid, path, uid) for fid, path, uid in files]
    await asyncio.gather(*tasks, return_exceptions=True)

# Caching frequent queries
from functools import lru_cache

@lru_cache(maxsize=100)
def get_user_documents(user_id: int):
    # Cache user's document list
    pass
```

### **2. Security Enhancements**

```python
# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, ...):
    pass

# Input sanitization
from bleach import clean

def sanitize_input(text: str) -> str:
    return clean(text, tags=[], strip=True)
```

### **3. Monitoring & Analytics**

```python
# File: api/app/middleware/monitoring.py

import time
import logging
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logging.info(f"{request.method} {request.url} - {response.status_code} - {process_time:.3f}s")
    return response
```

---

## 📚 **Testing Strategy**

### **Unit Tests**

```python
# File: tests/test_auth.py

import pytest
from fastapi.testclient import TestClient
from api.app.main import app

client = TestClient(app)

def test_register_success():
    response = client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
        "full_name": "Test User"
    })
    assert response.status_code == 200
    assert response.json()["success"] == True

def test_login_success():
    # Register first
    client.post("/api/auth/register", json={
        "email": "test2@example.com", 
        "password": "password123",
        "full_name": "Test User 2"
    })
    
    # Then login
    response = client.post("/api/auth/login", json={
        "email": "test2@example.com",
        "password": "password123"
    })
    assert response.status_code == 200
    assert "token" in response.json()
```

### **Integration Tests**

```python
# File: tests/test_file_upload.py

def test_file_upload_flow():
    # 1. Register user
    # 2. Login and get token
    # 3. Upload file
    # 4. Check processing status
    # 5. Test chat with uploaded document
    pass
```

---

## 🔄 **Migration Guide từ Current System**

### **Step 1: Database Migration**

```bash
# 1. Backup current data
pg_dump chatnary_db > backup.sql

# 2. Run migration scripts
psql chatnary_db < db/migrations/001_add_users_auth.sql

# 3. Migrate existing documents to admin user
UPDATE documents SET user_id = 1, user_email = 'admin@chatnary.com' WHERE user_id IS NULL;
UPDATE chunks SET user_id = 1 WHERE user_id IS NULL;
```

### **Step 2: Code Deployment**

```bash
# 1. Update dependencies
pip install -r requirements.txt

# 2. Test endpoints
python -m pytest tests/

# 3. Deploy gradually
# Keep /ask endpoint for backward compatibility
# Add new authenticated endpoints
# Migrate frontend gradually
```

### **Step 3: Frontend Integration**

```javascript
// Frontend authentication integration
const token = localStorage.getItem('auth_token');
const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        query: 'Your question here',
        model: 'gemini'
    })
});
```

---

**🎯 Kết luận**: Document này cung cấp roadmap chi tiết để implement đầy đủ các API endpoints theo SYSTEM_ARCHITECTURE.md. Ưu tiên giữ nguyên tech stack hiện tại (PostgreSQL + pgvector) và implement từng phase một cách có hệ thống để đảm bảo tính ổn định và tương thích với frontend.
