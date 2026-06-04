"""
Backfill canonical resume timestamps and current-resume links.

This script upgrades existing persisted resume data so the newer
candidate-level current-CV rule applies to rows that were ingested before the
rule existed.

It does two things:

1. backfills `documents.resume_updated_at` from linked resume attachment source
   records where `source_payload.latest_resume.created_at` is present
2. refreshes one `relationship_type='current_resume'` document link per
   candidate/person pair using the shared persistence helper
"""

from __future__ import annotations

from backend.db.connection import postgres_connection
from backend.db.resume_extraction_persistence import _refresh_current_resume_links


def main() -> None:
    """
    Backfill current-resume metadata for existing canonical resume documents.
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                with document_resume_timestamps as (
                    select
                        srl.document_id,
                        max(
                            nullif(
                                sr.source_payload -> 'latest_resume' ->> 'created_at',
                                ''
                            )::timestamptz
                        ) as resume_updated_at
                    from source_record_links srl
                    join source_records sr
                      on sr.id = srl.source_record_id
                    where srl.document_id is not null
                    group by srl.document_id
                )
                update documents d
                set resume_updated_at = drt.resume_updated_at
                from document_resume_timestamps drt
                where d.id = drt.document_id
                  and drt.resume_updated_at is not null
                  and (
                    d.resume_updated_at is null
                    or drt.resume_updated_at > d.resume_updated_at
                  )
                """
            )

            cursor.execute(
                """
                select distinct
                    dl.candidate_id,
                    c.person_id
                from document_links dl
                join candidates c
                  on c.id = dl.candidate_id
                where dl.candidate_id is not null
                  and dl.relationship_type = 'resume'
                order by dl.candidate_id
                """
            )
            candidate_rows = cursor.fetchall()

            refreshed_count = 0
            for row in candidate_rows:
                _refresh_current_resume_links(
                    cursor,
                    candidate_id=row["candidate_id"],
                    person_id=row["person_id"],
                    source_record_id=None,
                )
                refreshed_count += 1

        connection.commit()

    print(
        f"Backfilled resume timestamps and refreshed current resume links for "
        f"{refreshed_count} candidates."
    )


if __name__ == "__main__":
    main()
