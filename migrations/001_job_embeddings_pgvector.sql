-- Run once against an existing Job-Match database before deploying the
-- application version whose JobEmbedding model uses Vector(1024).
-- The migration preserves existing BGE-M3 vectors and refuses unexpected
-- vector dimensions rather than silently truncating or padding them.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM job_embeddings
        WHERE embedding IS NULL OR cardinality(embedding) <> 1024
    ) THEN
        RAISE EXCEPTION 'job_embeddings contains vectors that are not 1024 dimensions';
    END IF;
END
$$;

ALTER TABLE job_embeddings
    ALTER COLUMN embedding TYPE vector(1024)
    USING embedding::vector(1024);

CREATE INDEX IF NOT EXISTS ix_job_embeddings_embedding_hnsw
    ON job_embeddings USING hnsw (embedding vector_cosine_ops);

COMMIT;
