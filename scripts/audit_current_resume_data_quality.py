"""Run an aggregate-only, read-only audit of canonical current CV quality."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from typing import Any

from backend.db.connection import postgres_connection


CORE_QUALITY_SQL = """
with raw_current_candidate_links as (
    select
        dl.candidate_id,
        dl.document_id,
        count(*) as raw_link_count
    from document_links dl
    where dl.relationship_type = 'current_resume'
      and dl.candidate_id is not null
    group by dl.candidate_id, dl.document_id
),
candidate_current as (
    select candidate_id, document_id
    from raw_current_candidate_links
),
valid_current as (
    select
        cc.candidate_id,
        candidate.person_id,
        cc.document_id,
        document.extracted_text,
        document.resume_search_vector,
        document.source_uri,
        document.storage_path,
        document.title,
        document.mime_type,
        document.content_hash,
        document.resume_updated_at,
        candidate.resume_updated_at as candidate_resume_updated_at
    from candidate_current cc
    join candidates candidate on candidate.id = cc.candidate_id
    join documents document on document.id = cc.document_id
    where document.document_type = 'resume'
),
current_documents as (
    select distinct on (document_id)
        document_id,
        extracted_text,
        resume_search_vector,
        source_uri,
        storage_path,
        title,
        mime_type,
        content_hash,
        resume_updated_at
    from valid_current
    order by document_id
),
candidate_current_counts as (
    select candidate_id, count(*) as document_count
    from candidate_current
    group by candidate_id
),
resume_history_candidates as (
    select distinct candidate_id
    from document_links
    where relationship_type = 'resume'
      and candidate_id is not null
),
candidate_mirror_gaps as (
    select vc.candidate_id, vc.document_id
    from valid_current vc
    where not exists (
        select 1
        from document_links mirror
        where mirror.person_id = vc.person_id
          and mirror.document_id = vc.document_id
          and mirror.relationship_type = 'current_resume'
    )
),
candidate_history_gaps as (
    select vc.candidate_id, vc.document_id
    from valid_current vc
    where not exists (
        select 1
        from document_links history
        where history.candidate_id = vc.candidate_id
          and history.document_id = vc.document_id
          and history.relationship_type = 'resume'
    )
)
select
    (select count(*) from candidates)::integer as total_candidates,
    (select count(*) from candidate_current_counts)::integer
        as candidates_with_current_link_count,
    (
        select count(*)
        from candidate_current_counts
        where document_count = 1
    )::integer as candidates_with_one_current_document_count,
    (
        select count(*)
        from candidate_current_counts
        where document_count > 1
    )::integer as candidates_with_multiple_current_documents_count,
    (
        (select count(*) from candidates)
        - (select count(*) from candidate_current_counts)
    )::integer as candidates_without_current_link_count,
    (select count(*) from resume_history_candidates)::integer
        as candidates_with_resume_history_count,
    (
        select count(*)
        from resume_history_candidates history
        where not exists (
            select 1
            from candidate_current_counts current_link
            where current_link.candidate_id = history.candidate_id
        )
    )::integer as candidates_with_history_but_no_current_count,
    (
        select count(*)
        from candidates candidate
        where not exists (
            select 1
            from resume_history_candidates history
            where history.candidate_id = candidate.id
        )
    )::integer as candidates_without_resume_history_count,
    (select count(*) from candidate_current)::integer
        as current_candidate_document_pair_count,
    (
        select count(*)
        from raw_current_candidate_links
        where raw_link_count > 1
    )::integer as duplicate_current_link_group_count,
    (
        select count(*)
        from candidate_current cc
        join documents document on document.id = cc.document_id
        where document.document_type <> 'resume'
    )::integer as non_resume_current_link_count,
    (select count(*) from candidate_mirror_gaps)::integer
        as missing_person_mirror_link_count,
    (select count(*) from candidate_history_gaps)::integer
        as current_document_missing_history_link_count,
    (select count(*) from current_documents)::integer
        as distinct_current_resume_document_count,
    (
        select count(*)
        from current_documents
        where extracted_text is null or octet_length(extracted_text) = 0
    )::integer as missing_text_document_count,
    (
        select count(*)
        from current_documents
        where extracted_text is not null
          and octet_length(extracted_text) > 0
          and length(btrim(extracted_text)) < 200
    )::integer as very_short_text_document_count,
    (
        select count(*)
        from current_documents
        where extracted_text is not null
          and length(extracted_text) > 1000000
    )::integer as very_large_text_document_count,
    (
        select count(*)
        from current_documents
        where resume_search_vector is null
    )::integer as missing_search_vector_document_count,
    (
        select count(*)
        from current_documents
        where nullif(btrim(source_uri), '') is null
          and nullif(btrim(storage_path), '') is null
    )::integer as missing_source_locator_document_count,
    (
        select count(*)
        from current_documents
        where nullif(btrim(title), '') is null
    )::integer as missing_title_document_count,
    (
        select count(*)
        from current_documents
        where nullif(btrim(mime_type), '') is null
    )::integer as missing_mime_type_document_count,
    (
        select count(*)
        from current_documents
        where nullif(btrim(content_hash), '') is null
    )::integer as missing_content_hash_document_count,
    (
        select count(*)
        from current_documents
        where resume_updated_at is null
    )::integer as missing_document_resume_date_count,
    (
        select count(*)
        from current_documents current_document
        where not exists (
            select 1
            from source_record_links provenance
            where provenance.document_id = current_document.document_id
        )
    )::integer as missing_document_provenance_count,
    (
        select count(*)
        from current_documents current_document
        where not exists (
            select 1
            from document_chunks chunk
            where chunk.document_id = current_document.document_id
        )
    )::integer as missing_chunk_document_count,
    (
        select count(*)
        from current_documents current_document
        where not exists (
            select 1
            from document_chunks chunk
            where chunk.document_id = current_document.document_id
              and chunk.embedding is not null
        )
    )::integer as missing_embedded_chunk_document_count
"""


CANDIDATE_EVIDENCE_SQL = """
with valid_current_candidates as (
    select distinct
        candidate.id as candidate_id,
        candidate.person_id,
        candidate.current_title,
        candidate.current_company_id,
        coalesce(document.resume_updated_at, candidate.resume_updated_at)
            as effective_resume_updated_at
    from document_links link
    join documents document
      on document.id = link.document_id
     and document.document_type = 'resume'
    join candidates candidate on candidate.id = link.candidate_id
    where link.relationship_type = 'current_resume'
      and link.candidate_id is not null
)
select
    count(*)::integer as candidate_count,
    count(*) filter (
        where nullif(btrim(current_title), '') is null
    )::integer as missing_current_title_count,
    count(*) filter (
        where current_company_id is null
    )::integer as missing_current_company_count,
    count(*) filter (
        where effective_resume_updated_at is null
    )::integer as missing_effective_resume_date_count,
    count(*) filter (
        where effective_resume_updated_at > now() + interval '1 day'
    )::integer as future_resume_date_count,
    count(*) filter (
        where effective_resume_updated_at >= now() - interval '6 months'
          and effective_resume_updated_at <= now() + interval '1 day'
    )::integer as resume_age_under_6_months_count,
    count(*) filter (
        where effective_resume_updated_at < now() - interval '6 months'
          and effective_resume_updated_at >= now() - interval '1 year'
    )::integer as resume_age_6_to_12_months_count,
    count(*) filter (
        where effective_resume_updated_at < now() - interval '1 year'
          and effective_resume_updated_at >= now() - interval '2 years'
    )::integer as resume_age_1_to_2_years_count,
    count(*) filter (
        where effective_resume_updated_at < now() - interval '2 years'
          and effective_resume_updated_at >= now() - interval '5 years'
    )::integer as resume_age_2_to_5_years_count,
    count(*) filter (
        where effective_resume_updated_at < now() - interval '5 years'
    )::integer as resume_age_over_5_years_count,
    count(*) filter (
        where not exists (
            select 1 from candidate_skills skill
            where skill.candidate_id = valid_current_candidates.candidate_id
        )
    )::integer as missing_structured_skills_count,
    count(*) filter (
        where not exists (
            select 1 from person_company_roles role
            where role.person_id = valid_current_candidates.person_id
        )
    )::integer as missing_employment_history_count,
    count(*) filter (
        where not exists (
            select 1 from person_company_roles role
            where role.person_id = valid_current_candidates.person_id
              and role.is_current
        )
    )::integer as missing_current_employment_role_count,
    count(*) filter (
        where not exists (
            select 1 from candidate_semantic_blocks block
            where block.candidate_id = valid_current_candidates.candidate_id
        )
    )::integer as missing_semantic_blocks_count,
    count(*) filter (
        where not exists (
            select 1 from candidate_semantic_blocks block
            where block.candidate_id = valid_current_candidates.candidate_id
              and block.embedding is not null
        )
    )::integer as missing_semantic_embeddings_count
from valid_current_candidates
"""


TEXT_LENGTH_SQL = """
with current_documents as (
    select distinct document.id, length(document.extracted_text) as text_length
    from document_links link
    join documents document on document.id = link.document_id
    where link.relationship_type = 'current_resume'
      and link.candidate_id is not null
      and document.document_type = 'resume'
      and document.extracted_text is not null
      and octet_length(document.extracted_text) > 0
)
select
    count(*)::integer as measured_document_count,
    min(text_length)::integer as minimum_characters,
    percentile_cont(0.05) within group (order by text_length)::integer
        as p05_characters,
    percentile_cont(0.50) within group (order by text_length)::integer
        as median_characters,
    percentile_cont(0.95) within group (order by text_length)::integer
        as p95_characters,
    max(text_length)::integer as maximum_characters
from current_documents
"""


PROVENANCE_SQL = """
with current_documents as (
    select distinct document.id as document_id
    from document_links link
    join documents document on document.id = link.document_id
    where link.relationship_type = 'current_resume'
      and link.candidate_id is not null
      and document.document_type = 'resume'
),
document_sources as (
    select distinct current_document.document_id, source.source_system
    from current_documents current_document
    join source_record_links provenance
      on provenance.document_id = current_document.document_id
    join source_records source on source.id = provenance.source_record_id
)
select source_system, count(*)::integer as document_count
from document_sources
group by source_system
order by document_count desc, source_system
"""


DUPLICATE_SIGNAL_SQL = """
with valid_current as (
    select distinct
        link.candidate_id,
        document.id as document_id,
        nullif(btrim(document.content_hash), '') as content_hash,
        nullif(btrim(document.source_uri), '') as source_uri
    from document_links link
    join documents document on document.id = link.document_id
    where link.relationship_type = 'current_resume'
      and link.candidate_id is not null
      and document.document_type = 'resume'
),
duplicate_hashes as (
    select content_hash, count(distinct document_id) as documents,
           count(distinct candidate_id) as candidates
    from valid_current
    where content_hash is not null
    group by content_hash
    having count(distinct candidate_id) > 1
),
duplicate_uris as (
    select source_uri, count(distinct document_id) as documents,
           count(distinct candidate_id) as candidates
    from valid_current
    where source_uri is not null
    group by source_uri
    having count(distinct candidate_id) > 1
)
select
    (select count(*) from duplicate_hashes)::integer
        as duplicate_content_hash_group_count,
    coalesce((select sum(documents) from duplicate_hashes), 0)::integer
        as documents_in_duplicate_content_hash_groups,
    coalesce((select sum(candidates) from duplicate_hashes), 0)::integer
        as candidates_in_duplicate_content_hash_groups,
    (select count(*) from duplicate_uris)::integer
        as duplicate_source_uri_group_count,
    coalesce((select sum(documents) from duplicate_uris), 0)::integer
        as documents_in_duplicate_source_uri_groups,
    coalesce((select sum(candidates) from duplicate_uris), 0)::integer
        as candidates_in_duplicate_source_uri_groups
"""


LOCATOR_RECOVERY_SQL = """
with missing_locator_documents as (
    select distinct document.id as document_id
    from document_links link
    join documents document on document.id = link.document_id
    where link.relationship_type = 'current_resume'
      and link.candidate_id is not null
      and document.document_type = 'resume'
      and nullif(btrim(document.source_uri), '') is null
      and nullif(btrim(document.storage_path), '') is null
),
preferred_provenance as (
    select
        missing.document_id,
        provenance.source_system,
        provenance.source_record_id,
        provenance.source_payload
    from missing_locator_documents missing
    left join lateral (
        select
            source.source_system,
            source.source_record_id,
            source.source_payload
        from source_record_links provenance_link
        join source_records source
          on source.id = provenance_link.source_record_id
        where provenance_link.document_id = missing.document_id
        order by
            case
                when source.source_record_type in (
                    'dropbox_resume_attachment',
                    'recruiterflow_resume_attachment',
                    'outlook_message_attachment'
                ) then 0
                when source.source_record_type like '%%resume_attachment' then 1
                when source.source_record_type like '%%resume_extraction' then 2
                else 3
            end,
            source.processed_at desc nulls last,
            source.created_at desc nulls last,
            source.id desc
        limit 1
    ) provenance on true
),
classified as (
    select
        document_id,
        source_system,
        case
            when source_system = 'dropbox' then
                nullif(source_payload -> 'latest_resume' ->> 'attachment_id', '')
                    is not null
                or nullif(source_record_id, '') is not null
            when source_system = 'recruiterflow' then
                nullif(source_payload -> 'latest_resume' ->> 'source_uri', '')
                    is not null
                or nullif(source_payload -> 'latest_resume' ->> 'url', '')
                    is not null
                or nullif(source_payload -> 'latest_resume' ->> 'link', '')
                    is not null
                or nullif(source_payload ->> 'source_uri', '') is not null
                or nullif(source_payload ->> 'url', '') is not null
                or nullif(source_payload ->> 'link', '') is not null
            else false
        end as locator_derivable
    from preferred_provenance
)
select
    count(*)::integer as missing_direct_locator_count,
    count(*) filter (where locator_derivable)::integer
        as provenance_derivable_locator_count,
    count(*) filter (where not locator_derivable)::integer
        as unresolved_locator_count
from classified
"""


def _integer_mapping(row: Mapping[str, Any] | None) -> dict[str, int]:
    return {key: int(value or 0) for key, value in dict(row or {}).items()}


def collect_current_resume_quality_snapshot(cursor: Any) -> dict[str, Any]:
    """Collect aggregate quality evidence without returning record content."""

    cursor.execute(CORE_QUALITY_SQL)
    core = _integer_mapping(cursor.fetchone())
    cursor.execute(CANDIDATE_EVIDENCE_SQL)
    candidate_evidence = _integer_mapping(cursor.fetchone())
    cursor.execute(TEXT_LENGTH_SQL)
    text_lengths = _integer_mapping(cursor.fetchone())
    cursor.execute(PROVENANCE_SQL)
    provenance = [
        {
            "source_system": str(row.get("source_system") or "<none>"),
            "document_count": int(row.get("document_count") or 0),
        }
        for row in cursor.fetchall()
    ]
    cursor.execute(DUPLICATE_SIGNAL_SQL)
    duplicate_signals = _integer_mapping(cursor.fetchone())
    cursor.execute(LOCATOR_RECOVERY_SQL)
    locator_recovery = _integer_mapping(cursor.fetchone())
    return {
        "core": core,
        "candidate_evidence": candidate_evidence,
        "text_lengths": text_lengths,
        "provenance_by_source_system": provenance,
        "duplicate_signals": duplicate_signals,
        "locator_recovery": locator_recovery,
    }


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def build_current_resume_quality_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Add rates and bounded findings to an aggregate database snapshot."""

    core = dict(snapshot.get("core") or {})
    evidence = dict(snapshot.get("candidate_evidence") or {})
    total_candidates = int(core.get("total_candidates") or 0)
    current_candidates = int(evidence.get("candidate_count") or 0)
    current_documents = int(core.get("distinct_current_resume_document_count") or 0)
    locator_recovery = dict(snapshot.get("locator_recovery") or {})

    rates = {
        "candidate_current_resume_coverage_percent": _percentage(
            int(core.get("candidates_with_current_link_count") or 0),
            total_candidates,
        ),
        "current_resume_text_coverage_percent": _percentage(
            current_documents - int(core.get("missing_text_document_count") or 0),
            current_documents,
        ),
        "current_resume_provenance_coverage_percent": _percentage(
            current_documents
            - int(core.get("missing_document_provenance_count") or 0),
            current_documents,
        ),
        "download_locator_coverage_percent": _percentage(
            current_documents
            - int(locator_recovery.get("unresolved_locator_count") or 0),
            current_documents,
        ),
        "current_title_coverage_percent": _percentage(
            current_candidates
            - int(evidence.get("missing_current_title_count") or 0),
            current_candidates,
        ),
        "current_company_coverage_percent": _percentage(
            current_candidates
            - int(evidence.get("missing_current_company_count") or 0),
            current_candidates,
        ),
        "structured_skills_coverage_percent": _percentage(
            current_candidates
            - int(evidence.get("missing_structured_skills_count") or 0),
            current_candidates,
        ),
        "employment_history_coverage_percent": _percentage(
            current_candidates
            - int(evidence.get("missing_employment_history_count") or 0),
            current_candidates,
        ),
        "semantic_embedding_coverage_percent": _percentage(
            current_candidates
            - int(evidence.get("missing_semantic_embeddings_count") or 0),
            current_candidates,
        ),
        "resume_updated_within_2_years_percent": _percentage(
            int(evidence.get("resume_age_under_6_months_count") or 0)
            + int(evidence.get("resume_age_6_to_12_months_count") or 0)
            + int(evidence.get("resume_age_1_to_2_years_count") or 0),
            current_candidates,
        ),
    }

    findings: list[dict[str, Any]] = []

    def add_finding(
        severity: str,
        code: str,
        count: int,
        message: str,
    ) -> None:
        if count > 0:
            findings.append(
                {
                    "severity": severity,
                    "code": code,
                    "count": int(count),
                    "message": message,
                }
            )

    add_finding(
        "error",
        "multiple_current_documents",
        int(core.get("candidates_with_multiple_current_documents_count") or 0),
        "Candidates should have at most one canonical current CV.",
    )
    add_finding(
        "error",
        "duplicate_current_links",
        int(core.get("duplicate_current_link_group_count") or 0),
        "Duplicate candidate/document current-CV link rows violate the canonical link invariant.",
    )
    add_finding(
        "error",
        "non_resume_current_links",
        int(core.get("non_resume_current_link_count") or 0),
        "A current-CV link points to a document not typed as a resume.",
    )
    add_finding(
        "error",
        "missing_current_text",
        int(core.get("missing_text_document_count") or 0),
        "Current CVs without extracted text cannot participate in complete full-text search.",
    )
    add_finding(
        "error",
        "missing_search_vector",
        int(core.get("missing_search_vector_document_count") or 0),
        "Current CVs without a search vector cannot use the indexed full-text path.",
    )
    add_finding(
        "warning",
        "resume_history_without_current_link",
        int(core.get("candidates_with_history_but_no_current_count") or 0),
        "Candidates have resume history but no selected canonical current CV.",
    )
    add_finding(
        "warning",
        "missing_person_mirror_link",
        int(core.get("missing_person_mirror_link_count") or 0),
        "Candidate current-CV links are not mirrored to their canonical person.",
    )
    add_finding(
        "warning",
        "missing_resume_history_link",
        int(core.get("current_document_missing_history_link_count") or 0),
        "A selected current CV is not retained in the candidate's resume history.",
    )
    add_finding(
        "warning",
        "very_short_extracted_text",
        int(core.get("very_short_text_document_count") or 0),
        "Very short extracted text may indicate parser or source-file quality problems.",
    )
    add_finding(
        "warning",
        "missing_source_locator",
        int(locator_recovery.get("unresolved_locator_count") or 0),
        "Current CVs have no direct or provenance-derivable download locator.",
    )
    add_finding(
        "warning",
        "missing_document_provenance",
        int(core.get("missing_document_provenance_count") or 0),
        "Current CV documents are not linked to a source record.",
    )
    add_finding(
        "warning",
        "future_resume_date",
        int(evidence.get("future_resume_date_count") or 0),
        "Resume dates more than one day in the future need review.",
    )
    add_finding(
        "warning",
        "duplicate_content_hash_across_candidates",
        int(
            (snapshot.get("duplicate_signals") or {}).get(
                "duplicate_content_hash_group_count", 0
            )
        ),
        "Identical CV content hashes are selected for multiple candidates.",
    )
    add_finding(
        "warning",
        "duplicate_source_uri_across_candidates",
        int(
            (snapshot.get("duplicate_signals") or {}).get(
                "duplicate_source_uri_group_count", 0
            )
        ),
        "The same source URI is selected as the current CV for multiple candidates.",
    )
    add_finding(
        "warning",
        "missing_structured_skills",
        int(evidence.get("missing_structured_skills_count") or 0),
        "Current-CV candidates lack structured skills evidence.",
    )
    add_finding(
        "warning",
        "missing_employment_history",
        int(evidence.get("missing_employment_history_count") or 0),
        "Current-CV candidates lack structured employment-history rows.",
    )
    add_finding(
        "warning",
        "missing_current_title",
        int(evidence.get("missing_current_title_count") or 0),
        "Current-CV candidates lack a structured current title.",
    )
    add_finding(
        "warning",
        "missing_current_company",
        int(evidence.get("missing_current_company_count") or 0),
        "Current-CV candidates lack a structured current company.",
    )
    add_finding(
        "info",
        "candidates_without_resume_history",
        int(core.get("candidates_without_resume_history_count") or 0),
        "Canonical candidates without any resume are outside current-CV search scope.",
    )
    add_finding(
        "info",
        "resume_older_than_2_years",
        int(evidence.get("resume_age_2_to_5_years_count") or 0)
        + int(evidence.get("resume_age_over_5_years_count") or 0),
        "Current CV dates older than two years may need recruiter-led freshness review.",
    )

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda item: (severity_rank[item["severity"]], item["code"]))
    status = (
        "needs_attention"
        if any(item["severity"] == "error" for item in findings)
        else "monitor"
        if findings
        else "healthy"
    )
    return {
        "status": status,
        "scope": "aggregate canonical current-resume quality",
        "core": core,
        "candidate_evidence": evidence,
        "text_lengths": dict(snapshot.get("text_lengths") or {}),
        "provenance_by_source_system": list(
            snapshot.get("provenance_by_source_system") or []
        ),
        "duplicate_signals": dict(snapshot.get("duplicate_signals") or {}),
        "locator_recovery": locator_recovery,
        "rates": rates,
        "findings": findings,
        "sensitive_content_returned": False,
        "writes_performed": 0,
    }


def run_current_resume_quality_audit(*, statement_timeout_seconds: int = 90) -> dict[str, Any]:
    """Run the live audit in a database-enforced read-only transaction."""

    bounded_timeout_ms = max(1000, min(int(statement_timeout_seconds) * 1000, 300000))
    with postgres_connection() as connection:
        with connection.transaction():
            connection.execute("set transaction read only")
            connection.execute(
                "select set_config('statement_timeout', %s, true)",
                (str(bounded_timeout_ms),),
            )
            with connection.cursor() as cursor:
                snapshot = collect_current_resume_quality_snapshot(cursor)
    return build_current_resume_quality_report(snapshot)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--statement-timeout-seconds", type=int, default=90)
    args = parser.parse_args()
    report = run_current_resume_quality_audit(
        statement_timeout_seconds=args.statement_timeout_seconds
    )
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
