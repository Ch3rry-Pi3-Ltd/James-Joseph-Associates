BEGIN;

-- Fail promptly if active work prevents the short schema change. The stored
-- vector stays current on every insert/update without a separate backfill job.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';
ALTER TABLE public.documents ADD COLUMN resume_search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(extracted_text, ''))) STORED;
CREATE INDEX idx_documents_resume_fts ON public.documents
    USING gin (resume_search_vector) WHERE document_type = 'resume';
CREATE INDEX idx_document_links_current_document ON public.document_links
    (document_id, candidate_id) WHERE relationship_type = 'current_resume';
CREATE INDEX idx_document_links_current_candidate ON public.document_links
    (candidate_id, document_id) WHERE relationship_type = 'current_resume';

ANALYZE public.documents;
ANALYZE public.document_links;
COMMIT;
