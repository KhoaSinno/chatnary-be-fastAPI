
# Phương án A (khuyến nghị): 1 VPS + Docker Compose + reverse proxy (TLS)

Phù hợp nhất với skeleton của bạn vì dự án đã có `docker-compose.yml` sẵn (service `api` và `db` pgvector) .

### 0) Chuẩn bị

* VPS Ubuntu LTS (2 vCPU, 4GB RAM là thoải mái).
* Một domain/subdomain (ví dụ: `rag.yourdomain.com`).
* Cài Docker & Compose plugin:

  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER && newgrp docker
  sudo apt-get install -y docker-compose-plugin
  ```

### 1) Clone code & tạo env

```bash
sudo mkdir -p /srv/rag && cd /srv/rag
git clone <repo> .
cp .env.example .env
# Nhập khóa: OPENAI_API_KEY, COHERE_API_KEY, GOOGLE_API_KEY
```

Các biến `.env` đã được skeleton dùng để cấu hình API và DB (PGHOST, PGUSER, …) .

### 2) Compose file cho production

Tạo thêm `docker-compose.prod.yml` (giữ DB chỉ chạy nội bộ, bật restart, logging):

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    container_name: rag_db
    environment:
      POSTGRES_DB: ${PGDATABASE:-rag}
      POSTGRES_USER: ${PGUSER:-rag}
      POSTGRES_PASSWORD: ${PGPASSWORD:-ragpw}
    # KHÔNG publish port 5432 ra Internet trong prod
    volumes:
      - ./db/init:/docker-entrypoint-initdb.d
      - pg_data:/var/lib/postgresql/data
    restart: unless-stopped

  api:
    build: ./api
    container_name: rag_api
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./api:/app
      - ./data:/data
    # API chỉ lắng nghe nội bộ, reverse-proxy sẽ terminate TLS
    ports:
      - "127.0.0.1:8000:8000"
    command: ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
    restart: unless-stopped

volumes:
  pg_data:
```

### 3) Reverse proxy + HTTPS (Caddy hoặc Nginx)

**Caddy** (nhanh gọn, tự lấy Let’s Encrypt):

```bash
sudo apt-get install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
rag.yourdomain.com {
  reverse_proxy 127.0.0.1:8000
}
EOF
sudo systemctl restart caddy
```

(Nếu dùng Nginx, cấu hình server block reverse proxy về `127.0.0.1:8000` + certbot để lấy TLS.)

### 4) Build & chạy

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Service `db` (Postgres + pgvector) và `api` (FastAPI) sẽ chạy. Trong skeleton, `db` tạo extension `vector`, `pg_trgm` và schema `documents/chunks` từ `./db/init` .

### 5) Nạp dữ liệu (tạm thời, thủ công)

Copy tài liệu vào server:

```bash
mkdir -p /srv/rag/data
# scp hoặc rsync file PDF/TXT/MD vào /srv/rag/data
docker compose exec api python -m app.ingest /data
```

(Lệnh ingest chính là entry point đã mô tả trong README của skeleton .)

### 6) Gọi API

* Health: `https://rag.yourdomain.com/health`
* Hỏi đáp: `POST https://rag.yourdomain.com/ask` (body như README) .

### 7) Bảo mật & vận hành tối thiểu

* **Không** expose Postgres public; chỉ proxy cổng 8000 qua Caddy.
* `ufw` mở 80/443:

  ```bash
  sudo ufw allow OpenSSH
  sudo ufw allow 80,443/tcp
  sudo ufw enable
  ```

* Sao lưu DB:

  ```bash
  docker exec rag_db pg_dump -U rag -d rag > /srv/rag/backup_$(date +%F).sql
  ```

* Log:

  ```bash
  docker logs -f rag_api
  docker logs -f rag_db
  ```

> Tip: Khi lên production lâu dài, bạn nên chuyển cơ chế ingest thủ công sang **API upload + job queue** như mình đã đề xuất trước (Celery/RQ + Redis), để người dùng không cần SSH chạy lệnh.

---

# Phương án B: PaaS (Render/Fly.io/Railway)

* Build image `api` từ Dockerfile, dùng Postgres managed của nhà cung cấp.
* Ưu: ít vận hành. Nhược: phí + giới hạn tài nguyên, cấu hình pgvector tùy nền tảng.

---

## CI/CD (tuỳ chọn)

* GitHub Actions: build & push image, SSH/rsync đến VPS và `docker compose pull && up -d`.
* Hoặc dùng `watchtower` để auto-pull image mới (nếu bạn publish registry).

---

## Checklist nhanh (prod)

* [ ] `.env` đã điền khóa & **không commit**.
* [ ] DB **không** publish port 5432 ra ngoài.
* [ ] Reverse proxy TLS hoạt động (Caddy/Nginx).
* [ ] Ingest xong dữ liệu mẫu.
* [ ] Sao lưu định kỳ `pg_dump`.
* [ ] Giới hạn rate, log access (thêm sau ở FastAPI/nginx).

Nếu bạn cho mình domain thật bạn định dùng, mình có thể xuất luôn file Caddy/Nginx đúng tên miền + script deploy một phát chạy được.
