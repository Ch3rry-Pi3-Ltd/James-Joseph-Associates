BEGIN;

CREATE TABLE candidate_match_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    match_run_id uuid NOT NULL,
    candidate_id uuid NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
    reviewer_user_id text NOT NULL,
    reviewer_email text,
    feedback_value text NOT NULL,
    feedback_reason text,
    job_description_hash text NOT NULL,
    job_description text NOT NULL,
    shortlist_rank integer NOT NULL,
    fit_score integer NOT NULL,
    retrieval_score double precision NOT NULL,
    graph_context_score double precision,
    ranking_input_score double precision,
    source_category text NOT NULL DEFAULT 'unknown',
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT candidate_match_feedback_value_check
        CHECK (feedback_value IN ('good_match', 'not_suitable')),
    CONSTRAINT candidate_match_feedback_rank_check
        CHECK (shortlist_rank BETWEEN 1 AND 10),
    CONSTRAINT candidate_match_feedback_fit_score_check
        CHECK (fit_score BETWEEN 0 AND 100),
    CONSTRAINT candidate_match_feedback_reason_length_check
        CHECK (
            feedback_reason IS NULL
            OR char_length(feedback_reason) <= 1000
        ),
    CONSTRAINT candidate_match_feedback_run_candidate_reviewer_unique
        UNIQUE (match_run_id, candidate_id, reviewer_user_id)
);

CREATE INDEX idx_candidate_match_feedback_candidate_id
    ON candidate_match_feedback (candidate_id);

CREATE INDEX idx_candidate_match_feedback_job_description_hash
    ON candidate_match_feedback (job_description_hash);

CREATE INDEX idx_candidate_match_feedback_value_updated_at
    ON candidate_match_feedback (feedback_value, updated_at DESC);

CREATE TRIGGER trg_candidate_match_feedback_updated_at
BEFORE UPDATE ON candidate_match_feedback
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
