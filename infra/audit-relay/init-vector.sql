-- pgvector + codebase embedding store (runs after 10-audit-log.sql).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS codebase_embeddings (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    chunk_content TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS codebase_embeddings_file_path_idx ON codebase_embeddings (file_path);
