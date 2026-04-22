-- First-pass canonical core schema for the recruitment intelligence platform.
--
-- This migration establishes:
--
--  - canonical business entities in Supabase/Postgres
--  - raw source-record capture for provenance
--  - relationship/link tables for graph-style traversal
--  - document and chunk storage for future GraphRAG retrieval
--
-- Important design decision
-- -------------------------
-- Supabase owns the canonical UUID primary keys.
-- External systems such as JobAdder, Dropbox, Pipedrive, LinkedIn, or Make.com
-- do NOT become the primary-key source of truth.
--
-- Their IDs should be stored in `source_records` and linked to canonical
-- entities through `source_record_links`.
--
-- This is a first-pass schema.
-- It should be refined once we have:
--
--  - JobAdder API payloads
--  - Dropbox CV document samples
--  - Pipedrive field exports
--  - any custom fields the client actually uses
--
-- This migration assumes `pgcrypto` and `vector` have already been enabled
-- by `0001_enable_extensions.sql`.

BEGIN;

-- Keep updated_at maintenance inside the database so inserts and updates remain
-- consistent across backend code, scripts, and future Make.com ingestion paths.
--  - define a Postgres function called set_updated_at; if it already exists,
--    replace it.
CREATE OR REPLACE FUNCTION set_updated_at()

--  - this is not called like a normal SQL function. It is meant to be attached
--    to a trigger.
RETURNS trigger

--  - the function is written in PostgreSWL's procedural language.
LANGUAGE plpgsql

--  - `AS $$ ... $$` wraps the function body.
AS $$
BEGIN

--  - `NEW` means "the row as it is about to be written"
--  - This line changes that row's updated_at value to the current timestamp
    NEW.updated_at = NOW();

--  - Return the modified row so Postgres can continue with the update
    RETURN NEW;
END;
$$;

-- ============================================================================
-- Core canonical entities
-- ============================================================================

CREATE TABLE companies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    domain text,
    website_url text,
    linkedin_url text,
    industry text,
    size_range text,
    location text,
    description text,
    status text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE people (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name text NOT NULL,
    first_name text,
    last_name text,
    primary_email text,
    primary_phone text,
    linkedin_url text,
    location text,
    headline text,
    summary text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    current_title text,
    current_company_id uuid REFERENCES companies(id) ON DELETE SET NULL,
    candidate_status text,
    availability_status text,
    salary_expectation numeric(12, 2),
    notice_period text,
    last_contacted_at timestamptz,
    resume_updated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT candidates_person_id_unique UNIQUE (person_id)
);

CREATE TABLE contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    company_id uuid REFERENCES companies(id) ON DELETE SET NULL,
    role_title text,
    contact_type text,
    seniority text,
    is_hiring_manager boolean NOT NULL DEFAULT false,
    postcode text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT contacts_person_company_unique UNIQUE (person_id, company_id)
);

CREATE TABLE jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid REFERENCES companies(id) ON DELETE SET NULL,
    hiring_manager_contact_id uuid REFERENCES contacts(id) ON DELETE SET NULL,
    title text NOT NULL,
    description text,
    location text,
    workplace_type text,
    employment_type text,
    work_type text,
    source text,
    owner_name text,
    salary_min numeric(12, 2),
    salary_max numeric(12, 2),
    currency text,
    status text,
    opened_at timestamptz,
    closed_at timestamptz,
    updated_from_source_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- Applications are important because JobAdder visibly exposes them and they sit
-- between candidates and jobs. They are not just a duplicate of the candidate
-- or job record; they represent the relationship state.
CREATE TABLE applications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    application_status text,
    source text,
    rating text,
    candidate_rating text,
    current_position text,
    current_employer text,
    social_profiles jsonb,
    applied_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT applications_candidate_job_unique UNIQUE (candidate_id, job_id)
);

-- Placements are operationally distinct from applications.
-- A candidate may apply many times but be placed once per specific outcome.
CREATE TABLE placements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_id uuid REFERENCES jobs(id) ON DELETE SET NULL,
    company_id uuid REFERENCES companies(id) ON DELETE SET NULL,
    contact_id uuid REFERENCES contacts(id) ON DELETE SET NULL,
    placement_status text,
    start_date date,
    end_date date,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- Opportunities are included because the JobAdder UI exposes them separately
-- from jobs. We should preserve that distinction rather than force them into
-- the same table too early.
CREATE TABLE opportunities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    smart_summary text,
    company_id uuid REFERENCES companies(id) ON DELETE SET NULL,
    contact_id uuid REFERENCES contacts(id) ON DELETE SET NULL,
    stage text,
    last_contact_at timestamptz,
    next_task_at timestamptz,
    value numeric(12, 2),
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE skills (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    canonical_name text,
    skill_type text,
    description text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT skills_name_unique UNIQUE (name)
);

CREATE TABLE documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_type text NOT NULL,
    title text,
    source_uri text,
    storage_path text,
    mime_type text,
    content_hash text,
    extracted_text text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE interactions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_type text NOT NULL,
    occurred_at timestamptz,
    subject text,
    body text,
    summary text,
    source_system text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- Preserve raw external records before or alongside transformation.
CREATE TABLE source_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL,
    source_record_type text NOT NULL,
    source_record_id text NOT NULL,
    source_payload jsonb,
    source_payload_hash text,
    import_run_id text,
    received_at timestamptz NOT NULL DEFAULT NOW(),
    processed_at timestamptz,
    sync_status text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT source_records_source_unique UNIQUE (
        source_system,
        source_record_type,
        source_record_id
    )
);

-- ============================================================================
-- Relationship tables
-- ============================================================================

CREATE TABLE candidate_skills (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    skill_id uuid NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    source_record_id uuid REFERENCES source_records(id) ON DELETE SET NULL,
    confidence numeric(5, 4),
    evidence_text text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT candidate_skills_candidate_skill_unique UNIQUE (candidate_id, skill_id)
);

CREATE TABLE job_required_skills (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id uuid NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    requirement_type text,
    importance text,
    source_record_id uuid REFERENCES source_records(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT job_required_skills_job_skill_unique UNIQUE (job_id, skill_id, requirement_type)
);

CREATE TABLE person_company_roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    role_title text,
    start_date date,
    end_date date,
    is_current boolean NOT NULL DEFAULT false,
    source_record_id uuid REFERENCES source_records(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE document_links (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    person_id uuid REFERENCES people(id) ON DELETE CASCADE,
    candidate_id uuid REFERENCES candidates(id) ON DELETE CASCADE,
    contact_id uuid REFERENCES contacts(id) ON DELETE CASCADE,
    company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
    job_id uuid REFERENCES jobs(id) ON DELETE CASCADE,
    application_id uuid REFERENCES applications(id) ON DELETE CASCADE,
    placement_id uuid REFERENCES placements(id) ON DELETE CASCADE,
    source_record_id uuid REFERENCES source_records(id) ON DELETE SET NULL,
    relationship_type text,
    created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE interaction_participants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_id uuid NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    person_id uuid REFERENCES people(id) ON DELETE CASCADE,
    candidate_id uuid REFERENCES candidates(id) ON DELETE CASCADE,
    contact_id uuid REFERENCES contacts(id) ON DELETE CASCADE,
    company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
    job_id uuid REFERENCES jobs(id) ON DELETE CASCADE,
    role_in_interaction text,
    created_at timestamptz NOT NULL DEFAULT NOW()
);

-- This table is what keeps Supabase canonical while still preserving where each
-- entity came from externally.
CREATE TABLE source_record_links (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id uuid NOT NULL REFERENCES source_records(id) ON DELETE CASCADE,
    person_id uuid REFERENCES people(id) ON DELETE CASCADE,
    candidate_id uuid REFERENCES candidates(id) ON DELETE CASCADE,
    contact_id uuid REFERENCES contacts(id) ON DELETE CASCADE,
    company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
    job_id uuid REFERENCES jobs(id) ON DELETE CASCADE,
    application_id uuid REFERENCES applications(id) ON DELETE CASCADE,
    placement_id uuid REFERENCES placements(id) ON DELETE CASCADE,
    opportunity_id uuid REFERENCES opportunities(id) ON DELETE CASCADE,
    document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
    linked_at timestamptz NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Retrieval / GraphRAG support
-- ============================================================================

CREATE TABLE document_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_record_id uuid REFERENCES source_records(id) ON DELETE SET NULL,
    chunk_index integer NOT NULL,
    chunk_text text NOT NULL,
    embedding vector(1536),
    token_count integer,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT document_chunks_document_index_unique UNIQUE (document_id, chunk_index)
);

-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX idx_companies_name ON companies (name);
CREATE INDEX idx_people_full_name ON people (full_name);
CREATE INDEX idx_people_primary_email ON people (primary_email);
CREATE INDEX idx_candidates_status ON candidates (candidate_status);
CREATE INDEX idx_contacts_company_id ON contacts (company_id);
CREATE INDEX idx_jobs_company_id ON jobs (company_id);
CREATE INDEX idx_jobs_status ON jobs (status);
CREATE INDEX idx_applications_candidate_id ON applications (candidate_id);
CREATE INDEX idx_applications_job_id ON applications (job_id);
CREATE INDEX idx_placements_candidate_id ON placements (candidate_id);
CREATE INDEX idx_opportunities_company_id ON opportunities (company_id);
CREATE INDEX idx_documents_document_type ON documents (document_type);
CREATE INDEX idx_source_records_source_system ON source_records (source_system);
CREATE INDEX idx_source_records_record_type ON source_records (source_record_type);
CREATE INDEX idx_source_records_sync_status ON source_records (sync_status);

-- JSONB payload search support for raw imported records.
--  - Create a GIN index on the source_payload JSONB column.
--      - source_payload stores raw JSON from external systems.
--      - later, you may want to query inside that JSON, e.g.:
--
--          - "find records where payload contains this email"
--          - "find records where status = active"
--
--      - A normal index is not great for arbitrary JSON searching
--      - A GIN index is designed for things like:
--
--          - JSONB
--          - arrays
--          - full-text-style membership lookup
--
--  In plain language:
--  - Make searching inside raw JSON payloads much faster.
CREATE INDEX idx_source_records_payload_gin
    ON source_records
    USING gin (source_payload);

-- pgvector ANN index for semantic retrieval.
--  - Creates a pgvector nearest-neighbour index on the embedding column.
--  - Document_chunks.embedding stores AI embedding vectors.
--      - Later, you may do semantic search such as:
--
--          - "find CV chunks similar to this job spec"
--          - "find candidate evidence related to this skill"
CREATE INDEX idx_document_chunks_embedding
    ON document_chunks

--  - `ivfflat` is an approximate nearest neighbour index type.
--      - It is much faster than similarity search
--      - Slightly approximate rather than perfectly exhaustive
--  - `vector_cosine_ops` means:
--      - "use cosine similarity as the comparison method"
    USING ivfflat (embedding vector_cosine_ops)

-- Configure the index with 100 clusters / partitions
--  - This affects the speed / accuracy tradeoff
-- 
-- In plain language:
--  - Make semantic vector search much faster for Graph RAG retrieval.
    WITH (lists = 100);

-- ============================================================================
-- updated_at triggers
-- ============================================================================

CREATE TRIGGER trg_companies_updated_at
BEFORE UPDATE ON companies
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_people_updated_at
BEFORE UPDATE ON people
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_candidates_updated_at
BEFORE UPDATE ON candidates
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_contacts_updated_at
BEFORE UPDATE ON contacts
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_jobs_updated_at
BEFORE UPDATE ON jobs
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_applications_updated_at
BEFORE UPDATE ON applications
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_placements_updated_at
BEFORE UPDATE ON placements
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_opportunities_updated_at
BEFORE UPDATE ON opportunities
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_skills_updated_at
BEFORE UPDATE ON skills
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_interactions_updated_at
BEFORE UPDATE ON interactions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;