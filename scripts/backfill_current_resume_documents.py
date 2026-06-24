"""
Backfill canonical resume timestamps and current-resume links.

This script upgrades existing persisted resume data so the newer
candidate-level current-CV rule applies to rows that were ingested before the
rule existed.

It does two things:

1. backfills `documents.resume_updated_at` from linked resume attachment source
   records where `source_payload.latest_resume.created_at` is present
2. backfills missing Dropbox `documents.source_uri` values from linked
   provenance where the Dropbox path is already known
3. refreshes one `relationship_type='current_resume'` document link per
   candidate/person pair using the shared persistence helper
"""

from __future__ import annotations

from backend.db.connection import postgres_connection
from backend.db.resume_extraction_persistence import _refresh_current_resume_links

BATCH_SIZE = 500


def main() -> None:
    """
    Backfill current-resume metadata for existing canonical resume documents.
    """

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("set statement_timeout = 0")

            cursor.execute(
                """
                with latest_dropbox_resume_sources as (
                    select distinct on (srl.document_id)
                        srl.document_id,
                        coalesce(
                            nullif(
                                sr.source_payload -> 'latest_resume' ->> 'attachment_id',
                                ''
                            ),
                            nullif(sr.source_record_id, '')
                        ) as dropbox_path
                    from source_record_links srl
                    join source_records sr
                      on sr.id = srl.source_record_id
                    where sr.source_system = 'dropbox'
                      and sr.source_record_type = 'dropbox_resume_attachment'
                    order by
                        srl.document_id,
                        sr.processed_at desc nulls last,
                        sr.created_at desc nulls last,
                        sr.id desc
                )
                select
                    document_id,
                    (
                        'dropbox://' || dropbox_path
                        || '#candidate=' || dropbox_path
                        || '&attachment=' || dropbox_path
                    ) as source_uri
                from latest_dropbox_resume_sources
                where dropbox_path like '/%'
                """
            )
            dropbox_source_rows = cursor.fetchall()
            backfilled_source_uri_count = 0
            for batch in _iter_batches(dropbox_source_rows, batch_size=BATCH_SIZE):
                cursor.executemany(
                    """
                    update documents
                    set source_uri = %(source_uri)s
                    where id = %(document_id)s
                      and source_uri is null
                    """,
                    batch,
                )
                backfilled_source_uri_count += len(batch)

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
                select
                    document_id,
                    resume_updated_at
                from document_resume_timestamps
                where resume_updated_at is not null
                """
            )
            document_resume_timestamp_rows = cursor.fetchall()
            backfilled_resume_timestamp_count = 0
            for batch in _iter_batches(
                document_resume_timestamp_rows,
                batch_size=BATCH_SIZE,
            ):
                cursor.executemany(
                    """
                    update documents
                    set resume_updated_at = %(resume_updated_at)s
                    where id = %(document_id)s
                      and (
                        resume_updated_at is null
                        or %(resume_updated_at)s::timestamptz > resume_updated_at
                      )
                    """,
                    batch,
                )
                backfilled_resume_timestamp_count += len(batch)

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
        f"Backfilled {backfilled_source_uri_count} Dropbox source URIs, "
        f"{backfilled_resume_timestamp_count} resume timestamps, and refreshed "
        f"current resume links for {refreshed_count} candidates."
    )


def _iter_batches(
    rows: list[dict[str, object]],
    *,
    batch_size: int,
) -> list[list[dict[str, object]]]:
    """
    Yield fixed-size batches from one in-memory row list.
    """

    return [
        rows[index : index + batch_size]
        for index in range(0, len(rows), batch_size)
    ]


if __name__ == "__main__":
    main()
