import os
from dataclasses import dataclass


@dataclass
class Settings:
	pg_host: str = os.getenv("PGHOST", "localhost")
	pg_port: int = int(os.getenv("PGPORT", "5432"))
	pg_db: str = os.getenv("PGDATABASE", "rag")
	pg_user: str = os.getenv("PGUSER", "rag")
	pg_password: str = os.getenv("PGPASSWORD", "ragpw")


	openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
	openai_embed_model: str = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")


	cohere_api_key: str = os.getenv("COHERE_API_KEY", "")
	cohere_rerank_model: str = os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0")


	google_api_key: str = os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
	gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


	chunk_size: int = int(os.getenv("CHUNK_SIZE", "1000"))
	chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "200"))


settings = Settings()