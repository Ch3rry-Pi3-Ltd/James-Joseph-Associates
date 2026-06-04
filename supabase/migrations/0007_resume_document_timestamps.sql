ALTER TABLE documents
ADD COLUMN IF NOT EXISTS resume_updated_at timestamptz;

