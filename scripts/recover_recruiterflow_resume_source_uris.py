"""
Recover missing Recruiterflow current-resume source URIs from Dropbox-backed CVs.

Strategy
--------
1. Load the small set of Recruiterflow current-resume documents whose
   `documents.source_uri` is still null.
2. Load Dropbox-backed candidate resume documents that already have a
   downloadable `source_uri`.
3. Match deterministically:
   - exact normalized extracted-text match for auto-recovery
   - exact normalized (full_name, document_title) match as review-only
4. Optionally apply the exact-text recoveries back onto the Recruiterflow
   `documents.source_uri` field.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from hashlib import md5
from typing import Iterable

from backend.db.connection import postgres_connection

DEFAULT_BATCH_SIZE = 100

_WHITESPACE_RE = re.compile(r"\s+")
_IDENTITY_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ResumeRow:
    source_system: str
    candidate_id: str
    document_id: str
    full_name: str | None
    current_title: str | None
    document_title: str | None
    resume_updated_at: str | None
    source_uri: str | None
    extracted_text: str | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recover missing Recruiterflow current-resume source URIs by matching "
            "against Dropbox-backed canonical resume documents."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist exact-text recoveries onto Recruiterflow documents.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Update batch size when --apply is used. Default: {DEFAULT_BATCH_SIZE}",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=None,
        help="Optional limit on missing Recruiterflow current resumes to inspect.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("set statement_timeout = 0")
            missing_rows = _load_missing_recruiterflow_rows(
                cursor,
                candidate_limit=args.candidate_limit,
            )
            dropbox_rows = _load_dropbox_resume_rows(cursor)

            recovery_plan = build_recovery_plan(
                missing_rows=missing_rows,
                dropbox_rows=dropbox_rows,
            )

            applied_count = 0
            if args.apply:
                applied_count = _apply_exact_text_recoveries(
                    cursor,
                    connection=connection,
                    exact_recoveries=recovery_plan["exact_text_recoveries"],
                    batch_size=args.batch_size,
                )

    summary = {
        "missing_recruiterflow_current_resumes": len(missing_rows),
        "dropbox_resume_documents_scanned": len(dropbox_rows),
        "exact_text_recoveries": len(recovery_plan["exact_text_recoveries"]),
        "exact_text_ambiguous": len(recovery_plan["exact_text_ambiguous"]),
        "title_name_review_matches": len(recovery_plan["title_name_review_matches"]),
        "title_name_ambiguous": len(recovery_plan["title_name_ambiguous"]),
        "unmatched": len(recovery_plan["unmatched"]),
        "applied_exact_text_recoveries": applied_count,
        "examples": {
            "exact_text_recoveries": recovery_plan["exact_text_recoveries"][:5],
            "title_name_review_matches": recovery_plan["title_name_review_matches"][:5],
            "unmatched": recovery_plan["unmatched"][:5],
        },
    }
    print(json.dumps(summary, indent=2, default=str))


def _load_missing_recruiterflow_rows(
    cursor,
    *,
    candidate_limit: int | None,
) -> list[ResumeRow]:
    limit_sql = ""
    params: dict[str, object] = {}
    if candidate_limit is not None:
        limit_sql = "limit %(candidate_limit)s"
        params["candidate_limit"] = candidate_limit

    cursor.execute(
        f"""
        with recruiterflow_current_resumes as (
            select distinct on (d.id)
                'recruiterflow' as source_system,
                c.id as candidate_id,
                d.id as document_id,
                p.full_name,
                c.current_title,
                d.title as document_title,
                coalesce(d.resume_updated_at, c.resume_updated_at)::text as resume_updated_at,
                d.source_uri,
                d.extracted_text
            from documents d
            join document_links dl
              on dl.document_id = d.id
             and dl.relationship_type = 'current_resume'
            join candidates c
              on c.id = dl.candidate_id
            join people p
              on p.id = c.person_id
            left join lateral (
                select
                    sr.source_system,
                    sr.source_record_type,
                    sr.processed_at,
                    sr.created_at,
                    sr.id
                from source_record_links srl
                join source_records sr
                  on sr.id = srl.source_record_id
                where srl.document_id = d.id
                order by
                    case
                        when sr.source_record_type = 'recruiterflow_resume_attachment' then 0
                        when sr.source_record_type = 'recruiterflow_resume_extraction' then 1
                        else 2
                    end,
                    sr.processed_at desc nulls last,
                    sr.created_at desc nulls last,
                    sr.id desc
                limit 1
            ) provenance on true
            where d.document_type = 'resume'
              and d.source_uri is null
              and provenance.source_system = 'recruiterflow'
            order by d.id
        )
        select *
        from recruiterflow_current_resumes
        order by candidate_id
        {limit_sql}
        """,
        params,
    )
    return [ResumeRow(**dict(row)) for row in cursor.fetchall()]


def _load_dropbox_resume_rows(cursor) -> list[ResumeRow]:
    cursor.execute(
        """
        with dropbox_resumes as (
            select distinct on (d.id)
                'dropbox' as source_system,
                dl.candidate_id,
                d.id as document_id,
                p.full_name,
                c.current_title,
                d.title as document_title,
                coalesce(d.resume_updated_at, c.resume_updated_at)::text as resume_updated_at,
                d.source_uri,
                d.extracted_text
            from documents d
            join document_links dl
              on dl.document_id = d.id
             and dl.relationship_type in ('resume', 'current_resume')
            join candidates c
              on c.id = dl.candidate_id
            join people p
              on p.id = c.person_id
            left join lateral (
                select
                    sr.source_system,
                    sr.source_record_type,
                    sr.processed_at,
                    sr.created_at,
                    sr.id
                from source_record_links srl
                join source_records sr
                  on sr.id = srl.source_record_id
                where srl.document_id = d.id
                order by
                    case
                        when sr.source_record_type = 'dropbox_resume_attachment' then 0
                        when sr.source_record_type = 'dropbox_resume_extraction' then 1
                        else 2
                    end,
                    sr.processed_at desc nulls last,
                    sr.created_at desc nulls last,
                    sr.id desc
                limit 1
            ) provenance on true
            where d.document_type = 'resume'
              and d.source_uri is not null
              and provenance.source_system = 'dropbox'
            order by d.id
        )
        select *
        from dropbox_resumes
        order by candidate_id, document_id
        """
    )
    return [ResumeRow(**dict(row)) for row in cursor.fetchall()]


def build_recovery_plan(
    *,
    missing_rows: Iterable[ResumeRow],
    dropbox_rows: Iterable[ResumeRow],
) -> dict[str, list[dict[str, object]]]:
    dropbox_rows = list(dropbox_rows)
    dropbox_by_text_hash: dict[str, list[ResumeRow]] = {}
    dropbox_by_title_name: dict[tuple[str, str], list[ResumeRow]] = {}

    for row in dropbox_rows:
        text_hash = _normalized_text_hash(row.extracted_text)
        if text_hash is not None:
            dropbox_by_text_hash.setdefault(text_hash, []).append(row)

        title_key = _title_name_key(full_name=row.full_name, document_title=row.document_title)
        if title_key is not None:
            dropbox_by_title_name.setdefault(title_key, []).append(row)

    exact_text_recoveries: list[dict[str, object]] = []
    exact_text_ambiguous: list[dict[str, object]] = []
    title_name_review_matches: list[dict[str, object]] = []
    title_name_ambiguous: list[dict[str, object]] = []
    unmatched: list[dict[str, object]] = []

    for missing in missing_rows:
        text_hash = _normalized_text_hash(missing.extracted_text)
        if text_hash is not None:
            text_matches = dropbox_by_text_hash.get(text_hash, [])
            exact_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=text_matches,
                strategy="exact_normalized_text",
            )
            if exact_result["status"] == "recovered":
                exact_text_recoveries.append(exact_result)
                continue
            if exact_result["status"] == "ambiguous":
                exact_text_ambiguous.append(exact_result)
                continue

        title_key = _title_name_key(
            full_name=missing.full_name,
            document_title=missing.document_title,
        )
        if title_key is not None:
            title_matches = dropbox_by_title_name.get(title_key, [])
            title_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=title_matches,
                strategy="title_name_review",
            )
            if title_result["status"] == "recovered":
                title_name_review_matches.append(title_result)
                continue
            if title_result["status"] == "ambiguous":
                title_name_ambiguous.append(title_result)
                continue

        unmatched.append(_missing_row_summary(missing, strategy="unmatched"))

    return {
        "exact_text_recoveries": exact_text_recoveries,
        "exact_text_ambiguous": exact_text_ambiguous,
        "title_name_review_matches": title_name_review_matches,
        "title_name_ambiguous": title_name_ambiguous,
        "unmatched": unmatched,
    }


def _choose_unique_match(
    *,
    missing_row: ResumeRow,
    matched_rows: list[ResumeRow],
    strategy: str,
) -> dict[str, object]:
    if not matched_rows:
        return {
            "status": "no_match",
            **_missing_row_summary(missing_row, strategy=strategy),
        }

    same_candidate_rows = [
        row for row in matched_rows if row.candidate_id == missing_row.candidate_id
    ]
    if same_candidate_rows:
        unique_same_candidate_uris = sorted(
            {
                row.source_uri
                for row in same_candidate_rows
                if isinstance(row.source_uri, str) and row.source_uri.strip() != ""
            }
        )
        if len(unique_same_candidate_uris) == 1:
            return {
                "status": "recovered",
                **_missing_row_summary(missing_row, strategy=f"{strategy}_same_candidate"),
                "matched_candidate_id": same_candidate_rows[0].candidate_id,
                "matched_document_id": same_candidate_rows[0].document_id,
                "matched_source_uri": unique_same_candidate_uris[0],
                "matched_uri_count": 1,
                "matched_document_count": len(
                    {row.document_id for row in same_candidate_rows}
                ),
            }

    unique_uris = sorted(
        {
            row.source_uri
            for row in matched_rows
            if isinstance(row.source_uri, str) and row.source_uri.strip() != ""
        }
    )
    if len(unique_uris) == 1:
        representative_row = matched_rows[0]
        return {
            "status": "recovered",
            **_missing_row_summary(missing_row, strategy=strategy),
            "matched_candidate_id": representative_row.candidate_id,
            "matched_document_id": representative_row.document_id,
            "matched_source_uri": unique_uris[0],
            "matched_uri_count": 1,
            "matched_document_count": len({row.document_id for row in matched_rows}),
        }

    return {
        "status": "ambiguous",
        **_missing_row_summary(missing_row, strategy=strategy),
        "matched_uri_count": len(unique_uris),
        "matched_document_count": len({row.document_id for row in matched_rows}),
        "matched_candidate_ids": sorted({row.candidate_id for row in matched_rows})[:10],
    }


def _missing_row_summary(
    row: ResumeRow,
    *,
    strategy: str,
) -> dict[str, object]:
    return {
        "candidate_id": row.candidate_id,
        "document_id": row.document_id,
        "full_name": row.full_name,
        "current_title": row.current_title,
        "document_title": row.document_title,
        "resume_updated_at": row.resume_updated_at,
        "strategy": strategy,
    }


def _normalized_text_hash(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    normalized = _WHITESPACE_RE.sub(" ", text.strip()).casefold()
    if normalized == "":
        return None
    return md5(normalized.encode("utf-8")).hexdigest()


def _normalize_identity_token(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _IDENTITY_RE.sub("", value.casefold())
    return normalized or None


def _title_name_key(
    *,
    full_name: str | None,
    document_title: str | None,
) -> tuple[str, str] | None:
    normalized_name = _normalize_identity_token(full_name)
    normalized_title = _normalize_identity_token(document_title)
    if normalized_name is None or normalized_title is None:
        return None
    return normalized_name, normalized_title


def _apply_exact_text_recoveries(
    cursor,
    *,
    connection,
    exact_recoveries: list[dict[str, object]],
    batch_size: int,
) -> int:
    update_rows = [
        {
            "document_id": recovery["document_id"],
            "source_uri": recovery["matched_source_uri"],
        }
        for recovery in exact_recoveries
        if isinstance(recovery.get("matched_source_uri"), str)
    ]
    processed = 0
    for batch in _iter_batches(update_rows, batch_size=batch_size):
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
        print(f"Recovered source_uri batch committed: {processed}/{len(update_rows)}")
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
