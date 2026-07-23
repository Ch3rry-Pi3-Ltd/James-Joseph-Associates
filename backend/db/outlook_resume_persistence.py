"""
Database helpers for persisting narrow Outlook advert-response resume data.

This module contains the first narrow write path for turning a confirmed
Outlook advert-response message attachment into canonical Supabase/Postgres
rows.

It gives the rest of the repository a stable way to talk about:

- saving an Outlook message snapshot as a provenance-bearing source record
- saving an Outlook attachment snapshot as a provenance-bearing source record
- upserting the linked canonical resume document row
- linking those source records back to canonical entities explicitly
- keeping direct SQL write logic out of service orchestration and operator
  scripts

Why this module exists
----------------------
The Outlook side has moved beyond OAuth and mailbox inspection.

For the `tw394` slice, we have already proved:

- Tom's Outlook OAuth connection works
- the advert-response folder path is discoverable through Graph
- real mailbox messages exist for vacancy-coded advert responses
- real file attachments can be downloaded and parsed locally

That changes the next question:

    "How do we persist one real Outlook advert-response attachment into the
    canonical schema without making the script own raw SQL?"

This module is the answer to that narrow question.

Important scope boundary
------------------------
This is intentionally not the full Outlook ingestion system.

It does not attempt to:

- reconcile the email directly to a canonical person or candidate yet
- create interaction rows from the message itself yet
- persist `.eml` message bodies as first-class documents yet
- chunk the resume into embeddings yet

Instead, it implements the smallest reliable write slice already justified by
the current evidence:

- one Outlook message source record
- one Outlook attachment source record
- one canonical `resume` document
- optional job links when the `tw...` code resolves cleanly
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor, sql
from psycopg.types.json import Jsonb

from backend.db.connection import postgres_connection

SourceRecordType = Literal[
    "outlook_message",
    "outlook_message_attachment",
]


def persist_outlook_resume_snapshot(
    persistence_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist one Outlook message plus one Outlook attachment snapshot.

    Parameters
    ----------
    persistence_payload : dict[str, Any]
        Normalized payload prepared by the service layer.

        The payload should already contain:

        - Outlook message identifiers and provenance fields
        - Outlook attachment identifiers and extracted text
        - stable source payload hashes

    Returns
    -------
    dict[str, Any]
        Small persistence summary containing the canonical IDs and important
        source-record IDs written by the transaction.

    Example
    -------
    Persisting a prepared payload returns a summary such as:

        {
            "document_id": "...",
            "resolved_job_id": null,
            "message_source_record_id": "...",
            "attachment_source_record_id": "...",
        }

    A later rerun for the same message and same attachment stays idempotent at
    the source-record level while still reusing the canonical resume document
    when the content hash matches.
    """

    persisted_at = datetime.now(timezone.utc)

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            # Keep the email message provenance and the file-attachment
            # provenance separate. They answer different lineage questions:
            #
            # - which mailbox message did this advert response arrive in?
            # - which concrete file attachment became the canonical resume
            #   document row?
            sync_status = persistence_payload.get("quality_status") or "accepted"

            message_source_record = _upsert_source_record(
                cursor,
                source_system="outlook",
                source_record_type="outlook_message",
                source_record_id=persistence_payload["message_source_record_id"],
                source_payload=persistence_payload["message_source_payload"],
                source_payload_hash=persistence_payload["message_source_payload_hash"],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status=sync_status,
            )

            attachment_source_record = _upsert_source_record(
                cursor,
                source_system="outlook",
                source_record_type="outlook_message_attachment",
                source_record_id=persistence_payload["attachment_source_record_id"],
                source_payload=persistence_payload["attachment_source_payload"],
                source_payload_hash=persistence_payload[
                    "attachment_source_payload_hash"
                ],
                import_run_id=persistence_payload.get("import_run_id"),
                processed_at=persisted_at,
                sync_status=sync_status,
            )

            resolved_job_id = _find_job_id_by_tw_code(
                cursor,
                tw_code=persistence_payload.get("tw_code"),
            )

            document_id = _upsert_resume_document(
                cursor,
                source_record_id=attachment_source_record["id"],
                resume_title=persistence_payload.get("resume_title"),
                mime_type=persistence_payload.get("resume_mime_type"),
                source_uri=persistence_payload.get("resume_source_uri"),
                content_hash=persistence_payload.get("resume_content_hash"),
                extracted_text=persistence_payload.get("cleaned_resume_text"),
            )

            _ensure_source_record_link(
                cursor,
                source_record_id=message_source_record["id"],
                document_id=document_id,
            )
            _ensure_source_record_link(
                cursor,
                source_record_id=attachment_source_record["id"],
                document_id=document_id,
            )

            if resolved_job_id is not None:
                _ensure_source_record_link(
                    cursor,
                    source_record_id=message_source_record["id"],
                    job_id=resolved_job_id,
                )
                _ensure_source_record_link(
                    cursor,
                    source_record_id=attachment_source_record["id"],
                    job_id=resolved_job_id,
                )
                # This link says "this resume document arrived as an advert
                # response for this job", not "this document already belongs to
                # a reconciled candidate".
                _ensure_document_link(
                    cursor,
                    document_id=document_id,
                    job_id=resolved_job_id,
                    relationship_type="advert_response_resume",
                    source_record_id=attachment_source_record["id"],
                )

        connection.commit()

    return _make_json_safe_summary(
        {
            "persisted_at": persisted_at.isoformat(),
            "tw_code": persistence_payload.get("tw_code"),
            "quality_status": persistence_payload.get("quality_status"),
            "quality_score": persistence_payload.get("quality_score"),
            "resolved_job_id": resolved_job_id,
            "document_id": document_id,
            "message_source_record_id": message_source_record["id"],
            "attachment_source_record_id": attachment_source_record["id"],
        }
    )


def _upsert_source_record(
    cursor: Cursor[Any],
    *,
    source_system: str,
    source_record_type: SourceRecordType,
    source_record_id: str,
    source_payload: dict[str, Any],
    source_payload_hash: str,
    import_run_id: str | None,
    processed_at: datetime,
    sync_status: str,
) -> dict[str, Any]:
    """
    Insert or replace one provenance-bearing source-record row.

    Example
    -------
    A call with:

        source_record_type="outlook_message_attachment"

    updates the latest accepted snapshot for that attachment key instead of
    inserting a duplicate row on every rerun.
    """

    cursor.execute(
        """
        insert into source_records (
            source_system,
            source_record_type,
            source_record_id,
            source_payload,
            source_payload_hash,
            import_run_id,
            processed_at,
            sync_status,
            error_message
        )
        values (
            %(source_system)s,
            %(source_record_type)s,
            %(source_record_id)s,
            %(source_payload)s,
            %(source_payload_hash)s,
            %(import_run_id)s,
            %(processed_at)s,
            %(sync_status)s,
            null
        )
        on conflict (source_system, source_record_type, source_record_id)
        do update set
            source_payload = excluded.source_payload,
            source_payload_hash = excluded.source_payload_hash,
            import_run_id = excluded.import_run_id,
            processed_at = excluded.processed_at,
            sync_status = excluded.sync_status,
            error_message = null
        returning id, source_system, source_record_type, source_record_id
        """,
        {
            "source_system": source_system,
            "source_record_type": source_record_type,
            "source_record_id": source_record_id,
            "source_payload": Jsonb(source_payload),
            "source_payload_hash": source_payload_hash,
            "import_run_id": import_run_id,
            "processed_at": processed_at,
            "sync_status": sync_status,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist source_record row.")
    return dict(row)


def _find_job_id_by_tw_code(
    cursor: Cursor[Any],
    *,
    tw_code: str | None,
) -> str | None:
    """
    Return the first canonical job ID that matches one `tw...` code.

    Notes
    -----
    This is deliberately conservative. It only attempts the link when a clear
    vacancy code exists and falls back to `None` when no canonical job has
    been persisted for that code yet.

    Example
    -------
    A value such as:

        "tw398"

    can resolve to a canonical `jobs.id` when a row with title
    `tw398 - KDB Developer` already exists.
    """

    if not isinstance(tw_code, str) or tw_code.strip() == "":
        return None

    cursor.execute(
        """
        select id
        from jobs
        where lower(title) like %(title_pattern)s
        order by opened_at desc nulls last, updated_at desc nulls last
        limit 1
        """,
        {"title_pattern": f"{tw_code.strip().lower()}%"},
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row["id"]


def _upsert_resume_document(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    resume_title: str | None,
    mime_type: str | None,
    source_uri: str | None,
    content_hash: str | None,
    extracted_text: str | None,
) -> str:
    """
    Find or create the canonical resume document row.

    Notes
    -----
    The attachment-source record is treated as the primary identity when
    possible. If a document has not yet been linked to that source record, we
    fall back to the content hash to avoid obvious duplicate document rows for
    the same resume file arriving from multiple systems.

    Example
    -------
    If the same CV already exists from JobAdder or Dropbox with the same
    content hash, this helper can reuse the existing canonical `resume`
    document row.
    """

    existing_document_id = _find_linked_entity_id(
        cursor,
        source_record_id=source_record_id,
        entity_column="document_id",
    )

    if existing_document_id is None and content_hash:
        cursor.execute(
            """
            select id
            from documents
            where document_type = 'resume'
              and content_hash = %(content_hash)s
            limit 1
            """,
            {"content_hash": content_hash},
        )
        row = cursor.fetchone()
        if row is not None:
            existing_document_id = row["id"]

    if existing_document_id is None:
        cursor.execute(
            """
            insert into documents (
                document_type,
                title,
                source_uri,
                mime_type,
                content_hash,
                extracted_text
            )
            values (
                'resume',
                %(title)s,
                %(source_uri)s,
                %(mime_type)s,
                %(content_hash)s,
                %(extracted_text)s
            )
            returning id
            """,
            {
                "title": resume_title,
                "source_uri": source_uri,
                "mime_type": mime_type,
                "content_hash": content_hash,
                "extracted_text": extracted_text,
            },
        )
        inserted_row = cursor.fetchone()
        if inserted_row is None:
            raise RuntimeError("Failed to create document row.")
        return inserted_row["id"]

    # Once a canonical resume document already exists, keep the update
    # conservative. We only fill in missing fields or replace empty-ish values
    # with the newer Outlook-derived values instead of treating this as a full
    # overwrite of document history.
    cursor.execute(
        """
        update documents
        set
            title = coalesce(%(title)s, title),
            source_uri = coalesce(%(source_uri)s, source_uri),
            mime_type = coalesce(%(mime_type)s, mime_type),
            content_hash = coalesce(%(content_hash)s, content_hash),
            extracted_text = coalesce(%(extracted_text)s, extracted_text)
        where id = %(document_id)s
        """,
        {
            "document_id": existing_document_id,
            "title": resume_title,
            "source_uri": source_uri,
            "mime_type": mime_type,
            "content_hash": content_hash,
            "extracted_text": extracted_text,
        },
    )
    return existing_document_id


def _find_linked_entity_id(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    entity_column: Literal["job_id", "document_id"],
) -> str | None:
    """
    Return one linked canonical entity ID from `source_record_links`.

    Example
    -------
    A call with:

        entity_column="document_id"

    returns the document linked to that source record when such a link already
    exists, otherwise `None`.
    """

    cursor.execute(
        sql.SQL(
            """
        select {entity_column}
        from source_record_links
        where source_record_id = %(source_record_id)s
          and {entity_column} is not null
        limit 1
        """
        ).format(entity_column=sql.Identifier(entity_column)),
        {"source_record_id": source_record_id},
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row[entity_column]


def _ensure_source_record_link(
    cursor: Cursor[Any],
    *,
    source_record_id: str,
    job_id: str | None = None,
    document_id: str | None = None,
) -> None:
    """
    Insert one `source_record_links` row only when it does not already exist.

    Example
    -------
    A call with:

        source_record_id="..."
        document_id="..."

    inserts one document-target link on the first accepted run and becomes a
    no-op on later identical reruns.
    """

    column_name, entity_id = _pick_single_entity_target(
        job_id=job_id,
        document_id=document_id,
    )

    cursor.execute(
        sql.SQL(
            """
        select id
        from source_record_links
        where source_record_id = %(source_record_id)s
          and {column_name} = %(entity_id)s
        limit 1
        """
        ).format(column_name=sql.Identifier(column_name)),
        {
            "source_record_id": source_record_id,
            "entity_id": entity_id,
        },
    )
    if cursor.fetchone() is not None:
        return

    cursor.execute(
        """
        insert into source_record_links (
            source_record_id,
            job_id,
            document_id
        )
        values (
            %(source_record_id)s,
            %(job_id)s,
            %(document_id)s
        )
        """,
        {
            "source_record_id": source_record_id,
            "job_id": job_id,
            "document_id": document_id,
        },
    )


def _ensure_document_link(
    cursor: Cursor[Any],
    *,
    document_id: str,
    relationship_type: str,
    source_record_id: str | None,
    job_id: str | None = None,
) -> None:
    """
    Insert one `document_links` row only when it does not already exist.

    Example
    -------
    A call with:

        document_id="..."
        job_id="..."
        relationship_type="advert_response_resume"

    creates one job-targeted advert-response resume link and then becomes
    idempotent on later reruns.
    """

    column_name, entity_id = _pick_single_document_target(job_id=job_id)

    cursor.execute(
        sql.SQL(
            """
        select id
        from document_links
        where document_id = %(document_id)s
          and relationship_type = %(relationship_type)s
          and {column_name} = %(entity_id)s
        limit 1
        """
        ).format(column_name=sql.Identifier(column_name)),
        {
            "document_id": document_id,
            "relationship_type": relationship_type,
            "entity_id": entity_id,
        },
    )
    if cursor.fetchone() is not None:
        return

    cursor.execute(
        """
        insert into document_links (
            document_id,
            job_id,
            source_record_id,
            relationship_type
        )
        values (
            %(document_id)s,
            %(job_id)s,
            %(source_record_id)s,
            %(relationship_type)s
        )
        """,
        {
            "document_id": document_id,
            "job_id": job_id,
            "source_record_id": source_record_id,
            "relationship_type": relationship_type,
        },
    )


def _pick_single_entity_target(
    *,
    job_id: str | None,
    document_id: str | None,
) -> tuple[str, str]:
    """
    Return the one non-null source-link target column and value.

    Example
    -------
    A call with only:

        job_id="job-uuid"

    returns:

        ("job_id", "job-uuid")
    """

    populated_targets = [
        ("job_id", job_id),
        ("document_id", document_id),
    ]
    resolved_targets = [
        (column_name, value)
        for column_name, value in populated_targets
        if value is not None
    ]
    if len(resolved_targets) != 1:
        raise ValueError(
            "Expected exactly one entity target when inserting a source_record link."
        )
    return resolved_targets[0]


def _pick_single_document_target(
    *,
    job_id: str | None,
) -> tuple[str, str]:
    """
    Return the one non-null document-link target column and value.

    Example
    -------
    A call with only:

        job_id="job-uuid"

    returns:

        ("job_id", "job-uuid")
    """

    if job_id is None:
        raise ValueError(
            "Expected exactly one job target when inserting a document link."
        )
    return "job_id", job_id


def _make_json_safe_summary(value: Any) -> Any:
    """
    Convert the persistence summary into JSON-safe plain Python types.

    Example
    -------
    A summary such as:

        {"document_id": UUID("...")}

    becomes:

        {"document_id": "..."}
    """

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: _make_json_safe_summary(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [_make_json_safe_summary(item) for item in value]

    if isinstance(value, tuple):
        return [_make_json_safe_summary(item) for item in value]

    return value


__all__ = ["persist_outlook_resume_snapshot"]
