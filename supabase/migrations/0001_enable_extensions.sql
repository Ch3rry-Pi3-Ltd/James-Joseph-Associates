-- Enable required Postgres extensions for the recruitment intelligence schema.
--
-- pgcrypto gives us gen_random_uuid() for UUID primary keys.
--
--  - Future tables can use:
--
--      id uuid primary key default gen_random_uuid()
--
--  - This gives records stable, hard-to-guess IDs instead of sequential IDs.
--  - This is useful for APIs, imports, distributed systems, and source data
--    arriving from multiple external tools.
--
-- vector enables pgvector columns for semantic embedding search.
--
--  - Future document chunk tables can use columns such as:
--
--      embedding vector(1536)
--
--  - This lets Postgres store AI embedding vectors.
--  - Those vectors support semantic search, such as finding CV chunks that are
--    similar to a job description.
--
-- IF NOT EXISTS makes each extension setup safe to rerun.
-- If the extension is already enabled, Postgrest leaves it alone.

CREATE extension IF NOT EXISTS pgcrypto;
CREATE extension IF NOT EXISTS vector;