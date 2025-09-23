# Database Reset & Schema Update Guide

## Tổng quan

Khi phát triển và cần update schema database (thêm bảng, cột, thay đổi cấu trúc), có 2 cách chính:

1. **Database Reset** (khuyến nghị cho dev environment)
2. **Migration** (khuyến nghị cho production)

---

## 🔄 Cách 1: Database Reset (Development)

### Khi nào dùng

- ✅ Môi trường development/testing
- ✅ Có thể mất dữ liệu test
- ✅ Schema thay đổi lớn
- ✅ Nhanh và đơn giản

### Các bước thực hiện

#### 1. Dừng containers

```bash
docker compose down
```

#### 2. Xóa volume database (⚠️ MẤT TOÀN BỘ DỮ LIỆU)

```bash
docker volume rm chatnary-be-fastapi_pg_data
```

#### 3. Cập nhật schema file

Chỉnh sửa `db/init/01-schema.sql` với:

- Thêm bảng mới
- Thêm/sửa cột
- Thêm dữ liệu test

#### 4. Khởi động lại containers

```bash
docker compose up -d
```

Database sẽ được tạo lại từ `db/init/*.sql`

#### 5. Ingest dữ liệu

```bash
docker compose exec api python -m app.ingest //data --owner 1
```

### Script tự động

```bash
#!/bin/bash
# reset-db.sh
echo "🛑 Stopping containers..."
docker compose down

echo "🗑️ Removing database volume..."
docker volume rm chatnary-be-fastapi_pg_data

echo "🚀 Starting fresh database..."
docker compose up -d

echo "⏳ Waiting for database..."
sleep 10

echo "📚 Ingesting data..."
docker compose exec api python -m app.ingest /data --owner 1

echo "✅ Database reset complete!"
```

---

## 🔧 Cách 2: Migration (Production)

### Khi nào dùng

- ✅ Môi trường production
- ✅ Không được mất dữ liệu
- ✅ Schema thay đổi nhỏ
- ✅ Có thể rollback

### Cách thực hiện

#### 1. Tạo migration script

```sql
-- migrations/001_add_owner_id.sql
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users (id) ON DELETE CASCADE;

INSERT INTO users (id, email, name)
VALUES (1, 'test@local', 'Test User')
ON CONFLICT (id) DO NOTHING;
```

#### 2. Chạy migration

```bash
# Truy cập database container
docker compose exec db psql -U rag -d rag

# Chạy script migration
\i /path/to/migration.sql
```

Hoặc từ host:

```bash
docker compose exec db psql -U rag -d rag -f /docker-entrypoint-initdb.d/migration.sql
```

#### 3. Kiểm tra thay đổi

```sql
-- Kiểm tra cột mới
\d documents

-- Kiểm tra dữ liệu
SELECT * FROM users;
```

---

## 📋 Best Practices

### Development Environment

- **Dùng Database Reset** - nhanh, đơn giản
- Backup dữ liệu test quan trọng trước khi reset
- Tự động hóa bằng script

### Production Environment

- **Dùng Migration** - an toàn, có thể rollback
- Test migration trên staging trước
- Backup database trước khi migration
- Viết rollback script

### Cả hai môi trường

- Version control cho migration scripts
- Document mọi thay đổi schema
- Test kỹ trước khi deploy

---

## 🔍 Troubleshooting

### Lỗi: "column does not exist"

```bash
# Kiểm tra schema hiện tại
docker compose exec db psql -U rag -d rag -c "\d documents"

# Chạy lại migration hoặc reset database
```

### Lỗi: "relation does not exist"

```bash
# Kiểm tra các bảng
docker compose exec db psql -U rag -d rag -c "\dt"

# Reset database để tạo lại schema
```

### Lỗi: "volume in use"

```bash
# Dừng tất cả containers trước
docker compose down

# Hoặc force remove
docker volume rm chatnary-be-fastapi_pg_data --force
```

---

## 📝 Checklist

### Trước khi reset database

- [ ] Backup dữ liệu quan trọng (nếu có)
- [ ] Commit code changes
- [ ] Update `db/init/01-schema.sql`
- [ ] Test script trên local

### Sau khi reset

- [ ] Kiểm tra containers đang chạy: `docker compose ps`
- [ ] Kiểm tra database connection: `docker compose exec db psql -U rag -d rag -c "SELECT 1"`
- [ ] Test API endpoints: `curl http://localhost:8000/health`
- [ ] Ingest test data

---

## 🚨 Cảnh báo

⚠️ **KHÔNG BAO GIỜ** dùng Database Reset trên production!
⚠️ **LUÔN** backup trước khi thay đổi schema!
⚠️ **TEST** migration trên staging environment trước!

---

## Ví dụ hoàn chỉnh

```bash
# Development workflow
git add .
git commit -m "Add owner_id column to documents"

# Reset database
docker compose down
docker volume rm chatnary-be-fastapi_pg_data
docker compose up -d

# Wait for startup
sleep 10

# Verify schema
docker compose exec db psql -U rag -d rag -c "\d documents"

# Ingest data
docker compose exec api python -m app.ingest /data --owner 1

# Test API
curl http://localhost:8000/health
```

Với cách này, mọi thay đổi schema sẽ được áp dụng tự động khi khởi động database mới!
