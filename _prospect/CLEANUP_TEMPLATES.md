# Database Cleanup - Quick Implementation Templates

## 🚀 Quick Start Templates

### 1. Cleanup Module Template (`api/app/cleanup.py`)

```python
"""Database Cleanup Module"""

import os
import logging
from typing import List, Dict, Optional
from .db import get_conn

logger = logging.getLogger(__name__)

def get_missing_files() -> List[Dict]:
    """Find documents where source file no longer exists"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, title, source, created_at 
            FROM documents 
            ORDER BY created_at DESC
        """).fetchall()
    
    missing = []
    for doc_id, title, source, created_at in rows:
        # Convert DB path to filesystem path
        if source.startswith('//data/') or source.startswith('/data/'):
            file_path = source.replace('//data/', 'data/').replace('/data/', 'data/')
        else:
            file_path = source
            
        if not os.path.exists(file_path):
            missing.append({
                "document_id": doc_id,
                "title": title,
                "source": source,
                "created_at": created_at,
                "chunks_count": get_chunks_count(doc_id)
            })
    
    return missing

def get_chunks_count(document_id: int) -> int:
    """Count chunks for a document"""
    with get_conn() as conn:
        result = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = %s",
            (document_id,)
        ).fetchone()
        return result[0] if result else 0

def cleanup_missing_documents(document_ids: Optional[List[int]] = None) -> Dict:
    """Remove documents and chunks from database"""
    if document_ids is None:
        missing = get_missing_files()
        document_ids = [doc["document_id"] for doc in missing]
    
    if not document_ids:
        return {"deleted_documents": 0, "deleted_chunks": 0}
    
    deleted_chunks = 0
    deleted_docs = 0
    
    with get_conn() as conn:
        # Delete chunks first (foreign key constraint)
        for doc_id in document_ids:
            chunks_result = conn.execute(
                "DELETE FROM chunks WHERE document_id = %s",
                (doc_id,)
            )
            deleted_chunks += chunks_result.rowcount
        
        # Delete documents
        docs_result = conn.execute(
            "DELETE FROM documents WHERE id = ANY(%s)",
            (document_ids,)
        )
        deleted_docs = docs_result.rowcount
        
        conn.commit()
    
    logger.info(f"Cleaned up {deleted_docs} documents and {deleted_chunks} chunks")
    
    return {
        "deleted_documents": deleted_docs,
        "deleted_chunks": deleted_chunks,
        "document_ids": document_ids
    }

def sync_database_with_files() -> Dict:
    """Full sync: remove DB entries for missing files"""
    missing = get_missing_files()
    if not missing:
        return {"message": "Database is already in sync", "missing_files": 0}
    
    result = cleanup_missing_documents()
    result["missing_files_found"] = len(missing)
    result["missing_files"] = [f["source"] for f in missing]
    
    return result

def get_database_stats() -> Dict:
    """Get database statistics"""
    with get_conn() as conn:
        docs_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        
        # Recent documents
        recent = conn.execute("""
            SELECT title, source, created_at 
            FROM documents 
            ORDER BY created_at DESC 
            LIMIT 5
        """).fetchall()
    
    return {
        "total_documents": docs_count,
        "total_chunks": chunks_count,
        "recent_documents": [
            {"title": r[0], "source": r[1], "created_at": r[2]}
            for r in recent
        ]
    }
```

### 2. API Endpoints Template (add to `api/app/main.py`)

```python
# Add this import
from typing import List, Optional
from .cleanup import (
    get_missing_files, 
    cleanup_missing_documents, 
    sync_database_with_files,
    get_database_stats
)

# Add these endpoints before @app.get("/capabilities")

@app.get("/admin/missing-files")
def list_missing_files():
    """List documents in DB where source files no longer exist"""
    missing = get_missing_files()
    return {
        "missing_count": len(missing),
        "missing_files": missing,
        "total_chunks_affected": sum(f["chunks_count"] for f in missing)
    }

@app.post("/admin/cleanup")
def cleanup_database(document_ids: Optional[List[int]] = None):
    """Clean up database by removing documents and chunks for missing files"""
    try:
        result = cleanup_missing_documents(document_ids)
        return result
    except Exception as e:
        return {"error": str(e), "success": False}

@app.post("/admin/sync")
def sync_database():
    """Sync database with file system - remove entries for deleted files"""
    try:
        result = sync_database_with_files()
        return result
    except Exception as e:
        return {"error": str(e), "success": False}

@app.get("/admin/stats")
def get_stats():
    """Get database statistics"""
    try:
        stats = get_database_stats()
        return stats
    except Exception as e:
        return {"error": str(e)}
```

### 3. Management Script Template (`scripts/manage_database.sh`)

```bash
#!/bin/bash

BASE_URL="http://localhost:8000"

show_help() {
    echo "=== Database Management Tool ==="
    echo "Usage: $0 {check|stats|sync|cleanup} [document_id]"
    echo ""
    echo "Commands:"
    echo "  check    - List missing files"
    echo "  stats    - Show database statistics"  
    echo "  sync     - Remove DB entries for missing files"
    echo "  cleanup  - Clean specific document or all missing"
}

check_missing() {
    echo "🔍 Checking for missing files..."
    curl -s "$BASE_URL/admin/missing-files" | \
        python -m json.tool 2>/dev/null || \
        echo "❌ Failed to connect to API"
}

show_stats() {
    echo "📊 Database statistics..."
    curl -s "$BASE_URL/admin/stats" | \
        python -m json.tool 2>/dev/null || \
        echo "❌ Failed to connect to API"
}

sync_database() {
    echo "🔄 Syncing database with filesystem..."
    echo "⚠️  This will delete database entries for missing files!"
    read -p "Continue? (y/N): " confirm
    
    if [[ $confirm =~ ^[Yy]$ ]]; then
        curl -s -X POST "$BASE_URL/admin/sync" | \
            python -m json.tool 2>/dev/null || \
            echo "❌ Failed to sync database"
    else
        echo "❌ Operation cancelled"
    fi
}

cleanup_database() {
    local doc_id="$1"
    
    if [ -z "$doc_id" ]; then
        echo "🧹 Cleaning up all missing files..."
        echo "⚠️  This will permanently delete documents and chunks!"
        read -p "Continue? (y/N): " confirm
        
        if [[ $confirm =~ ^[Yy]$ ]]; then
            curl -s -X POST "$BASE_URL/admin/cleanup" \
                -H "Content-Type: application/json" | \
                python -m json.tool 2>/dev/null || \
                echo "❌ Failed to cleanup database"
        else
            echo "❌ Operation cancelled"
        fi
    else
        echo "🧹 Cleaning up document ID: $doc_id..."
        curl -s -X POST "$BASE_URL/admin/cleanup" \
            -H "Content-Type: application/json" \
            -d "[$doc_id]" | \
            python -m json.tool 2>/dev/null || \
            echo "❌ Failed to cleanup document"
    fi
}

case "$1" in
    "check")
        check_missing
        ;;
    "stats")
        show_stats
        ;;
    "sync")
        sync_database
        ;;
    "cleanup")
        cleanup_database "$2"
        ;;
    *)
        show_help
        exit 1
        ;;
esac
```

## 📝 Implementation Steps

1. **Copy cleanup module:**

   ```bash
   # Create and paste cleanup.py content
   touch api/app/cleanup.py
   ```

2. **Update main.py:**

   ```bash
   # Add imports and endpoints to api/app/main.py
   ```

3. **Create management script:**

   ```bash
   # Create and make executable
   touch scripts/manage_database.sh
   chmod +x scripts/manage_database.sh
   ```

4. **Test the system:**

   ```bash
   # Rebuild container
   docker compose build api
   docker compose up -d
   
   # Test endpoints
   curl http://localhost:8000/admin/stats
   ./scripts/manage_database.sh check
   ```

## 🧪 Quick Test Scenario

```bash
# 1. Add a test file and ingest
echo "Test content" > data/test_file.txt
docker compose exec api python -m app.ingest //data

# 2. Check it's in database
./scripts/manage_database.sh stats

# 3. Remove file from filesystem  
rm data/test_file.txt

# 4. Check for missing files
./scripts/manage_database.sh check

# 5. Clean up database
./scripts/manage_database.sh sync
```

## ⚡ Ready-to-Use Commands

```bash
# Check what files are missing
curl http://localhost:8000/admin/missing-files | jq '.missing_files[].source'

# Get database stats
curl http://localhost:8000/admin/stats | jq '.total_documents, .total_chunks'

# Sync database (remove missing files)
curl -X POST http://localhost:8000/admin/sync

# Clean up specific document ID
curl -X POST http://localhost:8000/admin/cleanup -H "Content-Type: application/json" -d "[123]"
```
