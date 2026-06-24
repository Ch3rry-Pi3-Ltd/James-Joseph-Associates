"""
Backfill current-resume document metadata in controllable batches.

This script exists because the original one-shot maintenance query became too
expensive once the corpus grew. It now supports narrower operations:

1. backfill missing Dropbox `documents.source_uri` values
2. backfill `documents.resume_updated_at` from linked source payloads
3. refresh `relationship_type='current_resume'` links in bounded batches
"""

from __future__ import annotations

import argparse

from backend.db.connection import postgres_connection
from backend.db.resume_extraction_persistence import _refresh_current_resume_links

DEFAULT_BATCH_SIZE = 250


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill current-resume metadata in bounded batches."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per batch. Default: {DEFAULT_BATCH_SIZE}",
    )
    parser.add_argument(
        "--dropbox-source-uris-only",
        action="store_true",
        help="Only backfill missing Dropbox resume source URIs.",
    )
    parser.add_argument(
        "--resume-timestamps-only",
        action="store_true",
        help="Only backfill resume_updated_at values.",
    )
    parser.add_argument(
        "--refresh-current-links-only",
        action="store_true",
        help="Only refresh current_resume document links.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=None,
        help="Optional limit for the current_resume refresh candidate set.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    operations = _resolve_operations(args)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("set statement_timeout = 0")

            dropbox_count = 0
            if operations["dropbox_source_uris"]:
                dropbox_count = _backfill_dropbox_source_uris(
                    cursor,
                    connection=connection,
                    batch_size=args.batch_size,
                )

            resume_timestamp_count = 0
            if operations["resume_timestamps"]:
                resume_timestamp_count = _backfill_resume_timestamps(
                    cursor,
                    connection=connection,
                    batch_size=args.batch_size,
                )

            refreshed_count = 0
            if operations["refresh_current_links"]:
                refreshed_count = _refresh_current_resume_batches(
                    cursor,
                    connection=connection,
                    batch_size=args.batch_size,
                    candidate_limit=args.candidate_limit,
                )

    print(
        "Backfill summary: "
        f"dropbox_source_uris={dropbox_count}, "
        f"resume_timestamps={resume_timestamp_count}, "
        f"current_resume_links={refreshed_count}"
    )


def _resolve_operations(args: argparse.Namespace) -> dict[str, bool]:
    explicit_flags = [
        args.dropbox_source_uris_only,
        args.resume_timestamps_only,
        args.refresh_current_links_only,
    ]
    if not any(explicit_flags):
        return {
            "dropbox_source_uris": True,
            "resume_timestamps": True,
            "refresh_current_links": True,
        }

    return {
        "dropbox_source_uris": args.dropbox_source_uris_only,
        "resume_timestamps": args.resume_timestamps_only,
        "refresh_current_links": args.refresh_current_links_only,
    }


def _backfill_dropbox_source_uris(
    cursor,
    *,
    connection,
    batch_size: int,
) -> int:
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
            join documents d
              on d.id = srl.document_id
             and d.document_type = 'resume'
            join document_links dl
              on dl.document_id = d.id
             and dl.relationship_type = 'current_resume'
            where sr.source_system = 'dropbox'
              and sr.source_record_type = 'dropbox_resume_attachment'
              and d.source_uri is null
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
    rows = cursor.fetchall()
    processed = 0
    for batch in _iter_batches(rows, batch_size=batch_size):
        cursor.executemany(
            """
            update documents
            set source_uri = %(source_uri)s
            where id = %(document_id)s
              and source_uri is null
            """,
            batch,
        )
        connection.commit()
        processed += len(batch)
        print(f"Dropbox source_uri batch committed: {processed}/{len(rows)}")
    return processed


def _backfill_resume_timestamps(
    cursor,
    *,
    connection,
    batch_size: int,
) -> int:
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
    rows = cursor.fetchall()
    processed = 0
    for batch in _iter_batches(rows, batch_size=batch_size):
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
        connection.commit()
        processed += len(batch)
        print(f"Resume timestamp batch committed: {processed}/{len(rows)}")
    return processed


def _refresh_current_resume_batches(
    cursor,
    *,
    connection,
    batch_size: int,
    candidate_limit: int | None,
) -> int:
    limit_sql = ""
    params: dict[str, object] = {}
    if candidate_limit is not None:
        limit_sql = "limit %(candidate_limit)s"
        params["candidate_limit"] = candidate_limit

    cursor.execute(
        f"""
        select distinct
            dl.candidate_id,
            c.person_id
        from document_links dl
        join candidates c
          on c.id = dl.candidate_id
        where dl.candidate_id is not null
          and dl.relationship_type = 'resume'
        order by dl.candidate_id
        {limit_sql}
        """,
        params,
    )
    candidate_rows = cursor.fetchall()
    processed = 0
    for batch in _iter_batches(candidate_rows, batch_size=batch_size):
        for row in batch:
            _refresh_current_resume_links(
                cursor,
                candidate_id=row["candidate_id"],
                person_id=row["person_id"],
                source_record_id=None,
            )
        connection.commit()
        processed += len(batch)
        print(f"Current-resume link batch committed: {processed}/{len(candidate_rows)}")
    return processed


def _iter_batches(
    rows: list[dict[str, object]],
    *,
    batch_size: int,
) -> list[list[dict[str, object]]]:
    return [
        rows[index : index + batch_size]
        for index in range(0, len(rows), batch_size)
    ]


if __name__ == "__main__":
    main()
