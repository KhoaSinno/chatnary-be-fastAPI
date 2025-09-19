-- Documents and chunks
CREATE TABLE IF NOT EXISTS documents (
id SERIAL PRIMARY KEY,
source TEXT, -- file path
title TEXT,
url TEXT,
created_at TIMESTAMPTZ DEFAULT now()
);


-- text-embedding-3-small -> 1536 dims
CREATE TABLE IF NOT EXISTS chunks (
id SERIAL PRIMARY KEY,
document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
chunk_index INTEGER NOT NULL,
content TEXT NOT NULL,
content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content,''))) STORED,
embedding vector(1536)
);


-- Vector HNSW (cosine distance)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
ON chunks USING hnsw (embedding vector_cosine_ops);
-- vector_cosine_ops: When create index, let use cosine distance to compare vectors

-- Full-text (basic); works reasonably with 'simple' for vi-en mixed text
CREATE INDEX IF NOT EXISTS idx_chunks_tsv_gin
ON chunks USING GIN (content_tsv);


-- Optional trigram fuzzy match for Vietnamese
CREATE INDEX IF NOT EXISTS idx_chunks_trgm
ON chunks USING GIN (content gin_trgm_ops);

-- gin_trgm_ops: Let use trigram to compare text, support fuzzy match