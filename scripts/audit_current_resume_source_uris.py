"""
Audit current-resume source URI coverage and Recruiterflow recoverability.
"""

from __future__ import annotations

import json

from backend.db.connection import postgres_connection


def main() -> None:
    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                with current_resume_docs as (
                    select distinct
                        d.id as document_id,
                        d.source_uri,
                        sr.source_system
                    from document_links dl
                    join documents d
                      on d.id = dl.document_id
                     and d.document_type = 'resume'
                    left join source_record_links srl
                      on srl.document_id = d.id
                    left join source_records sr
                      on sr.id = srl.source_record_id
                    where dl.relationship_type = 'current_resume'
                )
                select
                    coalesce(source_system, '<none>') as source_system,
                    count(distinct document_id) as current_resume_documents,
                    count(distinct document_id) filter (
                        where source_uri is null
                    ) as missing_source_uri
                from current_resume_docs
                group by coalesce(source_system, '<none>')
                order by missing_source_uri desc, source_system
                """
            )
            coverage_rows = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                with recruiterflow_missing as (
                    select distinct on (d.id)
                        d.id as document_id,
                        sr.source_record_type,
                        sr.source_record_id,
                        sr.source_payload
                    from document_links dl
                    join documents d
                      on d.id = dl.document_id
                     and d.document_type = 'resume'
                    left join source_record_links srl
                      on srl.document_id = d.id
                    left join source_records sr
                      on sr.id = srl.source_record_id
                    where dl.relationship_type = 'current_resume'
                      and d.source_uri is null
                      and sr.source_system = 'recruiterflow'
                    order by
                        d.id,
                        case
                            when sr.source_record_type = 'recruiterflow_resume_attachment' then 0
                            when sr.source_record_type = 'recruiterflow_resume_extraction' then 1
                            else 2
                        end,
                        sr.processed_at desc nulls last,
                        sr.created_at desc nulls last,
                        sr.id desc
                )
                select
                    source_record_type,
                    count(*) as documents,
                    count(*) filter (
                        where nullif(source_payload -> 'latest_resume' ->> 'source_uri', '') is not null
                    ) as latest_resume_source_uri_count,
                    count(*) filter (
                        where nullif(source_payload -> 'latest_resume' ->> 'url', '') is not null
                    ) as latest_resume_url_count,
                    count(*) filter (
                        where nullif(source_payload -> 'latest_resume' ->> 'link', '') is not null
                    ) as latest_resume_link_count,
                    count(*) filter (
                        where nullif(source_payload ->> 'source_uri', '') is not null
                    ) as payload_source_uri_count,
                    count(*) filter (
                        where nullif(source_payload ->> 'url', '') is not null
                    ) as payload_url_count,
                    count(*) filter (
                        where nullif(source_payload ->> 'link', '') is not null
                    ) as payload_link_count
                from recruiterflow_missing
                group by source_record_type
                order by documents desc, source_record_type
                """
            )
            recruiterflow_rows = [dict(row) for row in cursor.fetchall()]

    summary = {
        "coverage_by_source_system": coverage_rows,
        "recruiterflow_missing_recoverability": recruiterflow_rows,
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
