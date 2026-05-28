-- First-pass reconciliation decision storage.
--
-- This migration adds an explicit place to store duplicate-resolution and
-- cross-source matching decisions instead of forcing that state to stay hidden
-- inside importer-specific code paths.
--
-- Important design decision
-- -------------------------
-- Reconciliation is recorded as data.
--
-- We do not want fuzzy matching rules to mutate canonical rows silently with
-- no audit trail. Instead, each accepted source record can carry one current
-- reconciliation decision row that explains:
--
-- - which canonical rows were chosen
-- - whether the match was automatic, newly created, or still needs review
-- - what evidence was used to reach that decision

BEGIN;

CREATE TABLE reconciliation_decisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id uuid NOT NULL REFERENCES source_records(id) ON DELETE CASCADE,
    document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
    person_id uuid REFERENCES people(id) ON DELETE SET NULL,
    candidate_id uuid REFERENCES candidates(id) ON DELETE SET NULL,
    decision_status text NOT NULL,
    decision_reason text,
    confidence numeric(5, 4),
    evidence_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    reviewed_at timestamptz,
    reviewed_by text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT reconciliation_decisions_source_record_unique UNIQUE (source_record_id)
);

CREATE INDEX idx_reconciliation_decisions_status
    ON reconciliation_decisions (decision_status);

CREATE INDEX idx_reconciliation_decisions_document_id
    ON reconciliation_decisions (document_id);

CREATE INDEX idx_reconciliation_decisions_person_id
    ON reconciliation_decisions (person_id);

CREATE INDEX idx_reconciliation_decisions_candidate_id
    ON reconciliation_decisions (candidate_id);

CREATE INDEX idx_reconciliation_decisions_evidence_payload_gin
    ON reconciliation_decisions
    USING gin (evidence_payload);

CREATE TRIGGER trg_reconciliation_decisions_updated_at
BEFORE UPDATE ON reconciliation_decisions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
