BEGIN;

CREATE TABLE candidate_saved_briefs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by_user_id text NOT NULL,
    created_by_email text,
    title text NOT NULL,
    job_description text NOT NULL,
    target_company_name text,
    retrieval_focus_terms text NOT NULL,
    search_result_limit smallint NOT NULL DEFAULT 5,
    retrieval_limit smallint NOT NULL DEFAULT 25,
    shortlist_limit smallint NOT NULL DEFAULT 3,
    last_match_run_id uuid,
    retrieved_candidate_count integer NOT NULL DEFAULT 0,
    search_results jsonb NOT NULL DEFAULT '[]'::jsonb,
    shortlisted_candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT candidate_saved_briefs_title_length_check
        CHECK (char_length(title) BETWEEN 1 AND 200),
    CONSTRAINT candidate_saved_briefs_company_length_check
        CHECK (
            target_company_name IS NULL
            OR char_length(target_company_name) <= 300
        ),
    CONSTRAINT candidate_saved_briefs_search_limit_check
        CHECK (search_result_limit BETWEEN 1 AND 50),
    CONSTRAINT candidate_saved_briefs_retrieval_limit_check
        CHECK (retrieval_limit BETWEEN 1 AND 100),
    CONSTRAINT candidate_saved_briefs_shortlist_limit_check
        CHECK (shortlist_limit BETWEEN 1 AND 10),
    CONSTRAINT candidate_saved_briefs_retrieved_count_check
        CHECK (retrieved_candidate_count >= 0),
    CONSTRAINT candidate_saved_briefs_search_results_array_check
        CHECK (jsonb_typeof(search_results) = 'array'),
    CONSTRAINT candidate_saved_briefs_shortlist_array_check
        CHECK (jsonb_typeof(shortlisted_candidates) = 'array')
);

CREATE INDEX idx_candidate_saved_briefs_owner_updated
    ON candidate_saved_briefs (created_by_user_id, updated_at DESC);

CREATE TRIGGER trg_candidate_saved_briefs_updated_at
BEFORE UPDATE ON candidate_saved_briefs
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
