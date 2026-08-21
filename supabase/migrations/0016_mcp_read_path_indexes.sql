BEGIN;

-- Live EXPLAIN ANALYZE on 22 August 2026 showed candidate/person provenance
-- lookups touching 2,963 shared blocks to return three rows because only the
-- source_record_links primary key was indexed.
CREATE INDEX IF NOT EXISTS idx_source_record_links_candidate_id
    ON source_record_links (candidate_id)
    WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_source_record_links_person_id
    ON source_record_links (person_id)
    WHERE person_id IS NOT NULL;

-- The same evidence check showed a 61,671-row sequential scan for one person's
-- recent employment. The index prefix serves the equality predicate while the
-- remaining columns support the bounded recency ordering.
CREATE INDEX IF NOT EXISTS idx_person_company_roles_person_recency
    ON person_company_roles (
        person_id,
        is_current DESC,
        end_date DESC NULLS LAST,
        start_date DESC NULLS LAST
    );

COMMIT;
