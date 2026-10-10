CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1536)
);
