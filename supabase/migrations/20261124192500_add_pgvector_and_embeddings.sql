-- Enable the pgvector extension to work with embedding vectors
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding vector column to knowledge_base (768 dimensions for Gemini embeddings)
ALTER TABLE knowledge_base 
ADD COLUMN IF NOT EXISTS embedding vector(768);

-- Create HNSW index for fast approximate nearest neighbor cosine search
CREATE INDEX IF NOT EXISTS knowledge_base_embedding_hnsw_idx 
ON knowledge_base 
USING hnsw (embedding vector_cosine_ops);
