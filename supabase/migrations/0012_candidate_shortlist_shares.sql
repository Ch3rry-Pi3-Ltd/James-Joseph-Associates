BEGIN;

CREATE TABLE candidate_shortlist_shares (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    match_run_id uuid NOT NULL,
    created_by_user_id text NOT NULL,
    created_by_email text,
    role_title text,
    job_description text NOT NULL,
    shortlisted_candidates jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT candidate_shortlist_shares_candidates_array_check
        CHECK (jsonb_typeof(shortlisted_candidates) = 'array'),
    CONSTRAINT candidate_shortlist_shares_candidates_count_check
        CHECK (jsonb_array_length(shortlisted_candidates) BETWEEN 1 AND 10),
    CONSTRAINT candidate_shortlist_shares_role_title_length_check
        CHECK (role_title IS NULL OR char_length(role_title) <= 200),
    CONSTRAINT candidate_shortlist_shares_run_creator_unique
        UNIQUE (match_run_id, created_by_user_id)
);

CREATE INDEX idx_candidate_shortlist_shares_expires_at
    ON candidate_shortlist_shares (expires_at);

CREATE INDEX idx_candidate_shortlist_shares_creator
    ON candidate_shortlist_shares (created_by_user_id, created_at DESC);

CREATE TRIGGER trg_candidate_shortlist_shares_updated_at
BEFORE UPDATE ON candidate_shortlist_shares
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
