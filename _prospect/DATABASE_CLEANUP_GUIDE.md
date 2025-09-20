# Database Cleanup System - Hướng Dẫn Implementation

## 🎯 Mục Tiêu

Hiện tại hệ thống **không tự động xóa** dữ liệu trong database khi xóa file trong thư mục `data/`. Cần tạo hệ thống quản lý để:

- Phát hiện files bị thiếu trong filesystem nhưng vẫn có trong DB
- Cleanup database để xóa documents và chunks của files đã bị xóa
- Cung cấp API endpoints để quản lý database
- Tạo tools dễ sử dụng cho admin

## 📋 Checklist Implementation

### Step 1: Tạo Database Cleanup Module

- [ ] Tạo file `api/app/cleanup.py`
- [ ] Implement function `get_missing_files()`
- [ ] Implement function `cleanup_missing_documents()`
- [ ] Implement function `sync_database_with_files()`
- [ ] Add logging và error handling

### Step 2: Thêm Admin API Endpoints

- [ ] Update `api/app/main.py`
- [ ] Add endpoint `GET /admin/missing-files`
- [ ] Add endpoint `POST /admin/cleanup`
- [ ] Add endpoint `POST /admin/sync`
- [ ] Add endpoint `GET /admin/stats`

### Step 3: Tạo Management Script

- [ ] Tạo script `scripts/manage_database.sh`
- [ ] Implement các commands: check, stats, sync, cleanup
- [ ] Make script executable và test

### Step 4: Testing & Documentation

- [ ] Test tất cả endpoints
- [ ] Test script với different scenarios
- [ ] Update README với usage instructions

## 🔧 Detailed Implementation Guide

### 1. Database Cleanup Module (`api/app/cleanup.py`)

```python
"""
Database Cleanup Module
Handles synchronization between filesystem and database
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional
from .db import get_conn

logger = logging.getLogger(__name__)

def get_missing_files() -> List[Dict]:
    """
    Find documents in database where source file no longer exists
    
    Returns:
        List of missing file info with document_id, title, source, chunks_count
    """
    # TODO: Implement
    # 1. Query all documents from database
    # 2. Check if each source file exists in filesystem
    # 3. Return list of missing files with metadata
    pass

def get_chunks_count(document_id: int) -> int:
    """
    Get number of chunks for a specific document
    
    Args:
        document_id: The document ID to count chunks for
        
    Returns:
        Number of chunks for the document
    """
    # TODO: Implement
    # Query chunks table for specific document_id
    pass

def cleanup_missing_documents(document_ids: Optional[List[int]] = None) -> Dict:
    """
    Remove documents and their chunks from database
    
    Args:
        document_ids: List of document IDs to delete. If None, delete all missing files
        
    Returns:
        Dictionary with deletion statistics
    """
    # TODO: Implement
    # 1. If document_ids is None, get all missing files
    # 2. Delete chunks first (foreign key constraint)
    # 3. Delete documents
    # 4. Return statistics
    pass

def sync_database_with_files() -> Dict:
    """
    Full synchronization: remove database entries for missing files
    
    Returns:
        Dictionary with sync results and statistics
    """
    # TODO: Implement
    # 1. Find missing files
    # 2. Cleanup missing documents
    # 3. Return comprehensive results
    pass

def get_database_stats() -> Dict:
    """
    Get current database statistics
    
    Returns:
        Dictionary with database statistics
    """
    # TODO: Implement
    # 1. Count total documents
    # 2. Count total chunks
    # 3. Get recent documents
    # 4. Calculate storage stats
    pass
```

### 2. API Endpoints (`api/app/main.py`)

```python
# Add these imports at the top
from typing import List, Optional
from .cleanup import (
    get_missing_files, 
    cleanup_missing_documents, 
    sync_database_with_files,
    get_database_stats
)

# Add these endpoints before the existing @app.get("/capabilities")

@app.get("/admin/missing-files")
def list_missing_files():
    """
    List documents in database where source files no longer exist
    
    Returns:
        - missing_count: Number of missing files
        - missing_files: List of missing file details
        - total_chunks_affected: Total chunks that would be deleted
    """
    # TODO: Implement
    # 1. Call get_missing_files()
    # 2. Calculate total affected chunks
    # 3. Return formatted response
    pass

@app.post("/admin/cleanup")
def cleanup_database(document_ids: Optional[List[int]] = None):
    """
    Clean up database by removing documents and chunks for missing files
    
    Args:
        document_ids: Optional list of specific document IDs to clean up
        
    Returns:
        Cleanup results and statistics
    """
    # TODO: Implement
    # 1. Call cleanup_missing_documents()
    # 2. Handle errors gracefully
    # 3. Return results
    pass

@app.post("/admin/sync")
def sync_database():
    """
    Synchronize database with filesystem - remove entries for deleted files
    
    Returns:
        Sync results and statistics
    """
    # TODO: Implement
    # 1. Call sync_database_with_files()
    # 2. Return comprehensive results
    pass

@app.get("/admin/stats")
def get_stats():
    """
    Get database statistics and health information
    
    Returns:
        Database statistics including document count, chunk count, recent files
    """
    # TODO: Implement
    # 1. Call get_database_stats()
    # 2. Add additional health checks
    # 3. Return formatted stats
    pass
```

### 3. Management Script (`scripts/manage_database.sh`)

```bash
#!/bin/bash

# Database Management Tool
# Provides easy CLI interface for database operations

BASE_URL="http://localhost:8000"

show_help() {
    echo "=== Database Management Tool ==="
    echo ""
    echo "Usage: $0 {command} [options]"
    echo ""
    echo "Commands:"
    echo "  check                    - List files in DB but missing from filesystem"
    echo "  stats                    - Show database statistics"
    echo "  sync                     - Remove DB entries for missing files"
    echo "  cleanup [document_id]    - Clean specific document or all missing"
    echo "  help                     - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 check                 # Check for missing files"
    echo "  $0 stats                 # Show database statistics"
    echo "  $0 sync                  # Sync database with filesystem"
    echo "  $0 cleanup               # Clean up all missing files"
    echo "  $0 cleanup 123           # Clean up specific document ID"
    echo ""
}

check_missing() {
    echo "🔍 Checking for missing files..."
    # TODO: Implement API call to /admin/missing-files
    # Use curl with proper error handling
    # Format output with jq if available
}

show_stats() {
    echo "📊 Database statistics..."
    # TODO: Implement API call to /admin/stats
    # Display formatted statistics
}

sync_database() {
    echo "🔄 Syncing database with filesystem..."
    # TODO: Implement API call to /admin/sync
    # Show progress and results
}

cleanup_database() {
    local doc_id="$1"
    
    if [ -z "$doc_id" ]; then
        echo "🧹 Cleaning up all missing files..."
        # TODO: Implement cleanup all missing files
        # Confirm before deletion
    else
        echo "🧹 Cleaning up document ID: $doc_id..."
        # TODO: Implement cleanup specific document
    fi
}

# Main script logic
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
    "help"|"--help"|"-h")
        show_help
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
```

## 🧪 Testing Strategy

### Test Cases cần cover

1. **Missing Files Detection:**

   ```bash
   # Tạo document trong DB
   # Xóa file khỏi filesystem
   # Verify API detect được missing file
   ```

2. **Cleanup Operations:**

   ```bash
   # Test cleanup single document
   # Test cleanup multiple documents
   # Test cleanup all missing files
   # Verify chunks được xóa đúng
   ```

3. **Error Handling:**

   ```bash
   # Test với database connection errors
   # Test với invalid document IDs
   # Test với permission issues
   ```

4. **Edge Cases:**

   ```bash
   # Test với empty database
   # Test với no missing files
   # Test với files có special characters
   ```

## 📚 Database Schema Reference

### Tables involved

```sql
-- documents table
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    source VARCHAR NOT NULL,      -- File path
    title VARCHAR NOT NULL,       -- Display name
    created_at TIMESTAMP DEFAULT NOW()
);

-- chunks table  
CREATE TABLE chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding VECTOR(1536)       -- OpenAI embedding dimension
);
```

### Important SQL queries

```sql
-- Find all documents
SELECT id, title, source, created_at FROM documents;

-- Count chunks per document
SELECT document_id, COUNT(*) as chunk_count 
FROM chunks 
GROUP BY document_id;

-- Delete chunks for a document
DELETE FROM chunks WHERE document_id = ?;

-- Delete document
DELETE FROM documents WHERE id = ?;
```

## 🛡️ Security & Safety Considerations

1. **Admin Endpoints Protection:**
   - Add authentication/authorization
   - Rate limiting
   - Input validation

2. **Database Safety:**
   - Use transactions for cleanup operations
   - Backup before bulk deletions
   - Confirm operations before execution

3. **File Path Security:**
   - Validate file paths
   - Prevent directory traversal
   - Handle special characters safely

## 📈 Future Enhancements

1. **Automatic Cleanup:**
   - Cron job for periodic cleanup
   - Configurable cleanup policies
   - Notification system

2. **Advanced Features:**
   - Backup/restore functionality
   - Audit logging
   - Performance monitoring

3. **UI Interface:**
   - Web dashboard for admin operations
   - Bulk operations interface
   - Real-time monitoring

## 🎯 Implementation Priority

1. **High Priority:** Core cleanup functionality
2. **Medium Priority:** Management script và API endpoints
3. **Low Priority:** Advanced features và UI

## 📝 Notes

- Test thoroughly with sample data before production use
- Consider database backup before implementing
- Monitor performance impact of cleanup operations
- Document all API endpoints với OpenAPI/Swagger
