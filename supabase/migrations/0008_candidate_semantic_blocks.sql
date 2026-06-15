BEGIN;

CREATE TABLE candidate_semantic_blocks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
    block_type text NOT NULL,
    block_index integer NOT NULL DEFAULT 0,
    block_label text,
    block_text text NOT NULL,
    embedding vector(1536),
    token_count integer,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT candidate_semantic_blocks_candidate_block_unique
        UNIQUE (candidate_id, block_type, block_index)
);

CREATE INDEX idx_candidate_semantic_blocks_candidate_id
    ON candidate_semantic_blocks (candidate_id);

CREATE INDEX idx_candidate_semantic_blocks_person_id
    ON candidate_semantic_blocks (person_id);

CREATE INDEX idx_candidate_semantic_blocks_document_id
    ON candidate_semantic_blocks (document_id);

CREATE INDEX idx_candidate_semantic_blocks_block_type
    ON candidate_semantic_blocks (block_type);

CREATE INDEX idx_candidate_semantic_blocks_embedding
    ON candidate_semantic_blocks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TRIGGER trg_candidate_semantic_blocks_updated_at
BEFORE UPDATE ON candidate_semantic_blocks
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
