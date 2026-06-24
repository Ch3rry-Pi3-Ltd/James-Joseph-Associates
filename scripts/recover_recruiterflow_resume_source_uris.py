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
import unicodedata
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
from typing import Iterable

from backend.db.connection import postgres_connection

DEFAULT_BATCH_SIZE = 100

_WHITESPACE_RE = re.compile(r"\s+")
_IDENTITY_RE = re.compile(r"[^a-z0-9]+")
_EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
_LINKEDIN_SLUG_RE = re.compile(r"linkedin\.com/in/([a-z0-9-]{3,})")
_GENERIC_TITLE_KEYS = {
    "profilepdf",
    "profiledoc",
    "profiledocx",
    "cvpdf",
    "cvdoc",
    "cvdocx",
    "resumepdf",
    "resumedoc",
    "resumedocx",
    "sourcewhaleresumepdf",
    "sourcewhaleresumedoc",
    "sourcewhaleresumedocx",
}
_NAME_LINE_EXCLUDE_TERMS = {
    "address",
    "contact",
    "curriculum",
    "email",
    "experience",
    "linkedin",
    "mobile",
    "objective",
    "personal",
    "profile",
    "skills",
    "summary",
    "telephone",
    "tel",
    "top",
    "work",
    "www",
}


@dataclass(frozen=True)
class ResumeRow:
    source_system: str
    candidate_id: str
    document_id: str
    full_name: str | None
    current_company_name: str | None
    current_title: str | None
    document_title: str | None
    resume_updated_at: str | None
    source_uri: str | None
    content_hash: str | None
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
        "--apply-review-matches",
        action="store_true",
        help=(
            "Also persist unique title/name review matches. Use only after "
            "reviewing the dry-run output."
        ),
    )
    parser.add_argument(
        "--apply-same-candidate-review-matches",
        action="store_true",
        help=(
            "Persist only review matches where the recovered Dropbox document "
            "already belongs to the same canonical candidate."
        ),
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
    parser.add_argument(
        "--report-path",
        type=str,
        default=None,
        help="Optional path to write a JSON review report.",
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

            applied_review_count = 0
            if args.apply_review_matches:
                applied_review_count = _apply_recoveries(
                    cursor,
                    connection=connection,
                    recoveries=recovery_plan["title_name_review_matches"],
                    batch_size=args.batch_size,
                    label="Review-match source_uri",
                )

            applied_same_candidate_review_count = 0
            if args.apply_same_candidate_review_matches:
                same_candidate_review_recoveries = [
                    recovery
                    for group_name in (
                        "email_identity_review_matches",
                        "linkedin_identity_review_matches",
                        "title_name_review_matches",
                        "profile_identity_review_matches",
                        "filename_name_review_matches",
                        "source_uri_filename_review_matches",
                        "extracted_text_name_review_matches",
                    )
                    for recovery in recovery_plan[group_name]
                    if str(recovery.get("strategy", "")).endswith("_same_candidate")
                ]
                applied_same_candidate_review_count = _apply_recoveries(
                    cursor,
                    connection=connection,
                    recoveries=same_candidate_review_recoveries,
                    batch_size=args.batch_size,
                    label="Same-candidate review-match source_uri",
                )

    summary = {
        "missing_recruiterflow_current_resumes": len(missing_rows),
        "dropbox_resume_documents_scanned": len(dropbox_rows),
        "exact_hash_recoveries": len(recovery_plan["exact_hash_recoveries"]),
        "exact_hash_ambiguous": len(recovery_plan["exact_hash_ambiguous"]),
        "exact_text_recoveries": len(recovery_plan["exact_text_recoveries"]),
        "exact_text_ambiguous": len(recovery_plan["exact_text_ambiguous"]),
        "email_identity_review_matches": len(recovery_plan["email_identity_review_matches"]),
        "email_identity_ambiguous": len(recovery_plan["email_identity_ambiguous"]),
        "linkedin_identity_review_matches": len(recovery_plan["linkedin_identity_review_matches"]),
        "linkedin_identity_ambiguous": len(recovery_plan["linkedin_identity_ambiguous"]),
        "title_name_review_matches": len(recovery_plan["title_name_review_matches"]),
        "title_name_ambiguous": len(recovery_plan["title_name_ambiguous"]),
        "profile_identity_review_matches": len(recovery_plan["profile_identity_review_matches"]),
        "profile_identity_ambiguous": len(recovery_plan["profile_identity_ambiguous"]),
        "filename_name_review_matches": len(recovery_plan["filename_name_review_matches"]),
        "filename_name_ambiguous": len(recovery_plan["filename_name_ambiguous"]),
        "source_uri_filename_review_matches": len(recovery_plan["source_uri_filename_review_matches"]),
        "source_uri_filename_ambiguous": len(recovery_plan["source_uri_filename_ambiguous"]),
        "extracted_text_name_review_matches": len(recovery_plan["extracted_text_name_review_matches"]),
        "extracted_text_name_ambiguous": len(recovery_plan["extracted_text_name_ambiguous"]),
        "unmatched": len(recovery_plan["unmatched"]),
        "applied_exact_text_recoveries": applied_count,
        "applied_title_name_review_matches": applied_review_count,
        "applied_same_candidate_review_matches": applied_same_candidate_review_count,
        "examples": {
            "exact_hash_recoveries": recovery_plan["exact_hash_recoveries"][:5],
            "exact_text_recoveries": recovery_plan["exact_text_recoveries"][:5],
            "email_identity_review_matches": recovery_plan["email_identity_review_matches"][:5],
            "linkedin_identity_review_matches": recovery_plan["linkedin_identity_review_matches"][:5],
            "title_name_review_matches": recovery_plan["title_name_review_matches"][:5],
            "profile_identity_review_matches": recovery_plan["profile_identity_review_matches"][:5],
            "filename_name_review_matches": recovery_plan["filename_name_review_matches"][:5],
            "source_uri_filename_review_matches": recovery_plan["source_uri_filename_review_matches"][:5],
            "extracted_text_name_review_matches": recovery_plan["extracted_text_name_review_matches"][:5],
            "unmatched": recovery_plan["unmatched"][:5],
        },
    }
    if args.report_path:
        report = build_review_report(recovery_plan=recovery_plan)
        report["summary"] = {
            "missing_recruiterflow_current_resumes": len(missing_rows),
            "review_candidates": len(report["review_candidates"]),
            "unmatched_candidates": len(report["unmatched_candidates"]),
        }
        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )
        summary["report_path"] = str(report_path)
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
                coalesce(comp.name, '') as current_company_name,
                c.current_title,
                d.title as document_title,
                coalesce(d.resume_updated_at, c.resume_updated_at)::text as resume_updated_at,
                d.source_uri,
                d.content_hash,
                d.extracted_text
            from documents d
            join document_links dl
              on dl.document_id = d.id
             and dl.relationship_type = 'current_resume'
            join candidates c
              on c.id = dl.candidate_id
            join people p
              on p.id = c.person_id
            left join companies comp
              on comp.id = c.current_company_id
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
                coalesce(comp.name, '') as current_company_name,
                c.current_title,
                d.title as document_title,
                coalesce(d.resume_updated_at, c.resume_updated_at)::text as resume_updated_at,
                d.source_uri,
                d.content_hash,
                d.extracted_text
            from documents d
            join document_links dl
              on dl.document_id = d.id
             and dl.relationship_type in ('resume', 'current_resume')
            join candidates c
              on c.id = dl.candidate_id
            join people p
              on p.id = c.person_id
            left join companies comp
              on comp.id = c.current_company_id
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
    dropbox_by_content_hash: dict[str, list[ResumeRow]] = {}
    dropbox_by_text_hash: dict[str, list[ResumeRow]] = {}
    dropbox_by_title_name: dict[tuple[str, str], list[ResumeRow]] = {}
    dropbox_by_filename_name_key: dict[tuple[str, ...], list[ResumeRow]] = {}
    dropbox_by_source_filename_name_key: dict[tuple[str, ...], list[ResumeRow]] = {}
    dropbox_by_extracted_name_key: dict[tuple[str, ...], list[ResumeRow]] = {}
    dropbox_by_email: dict[str, list[ResumeRow]] = {}
    dropbox_by_linkedin_slug: dict[str, list[ResumeRow]] = {}
    dropbox_by_full_name: dict[str, list[ResumeRow]] = {}

    for row in dropbox_rows:
        if isinstance(row.content_hash, str) and row.content_hash.strip() != "":
            dropbox_by_content_hash.setdefault(row.content_hash.strip(), []).append(row)

        text_hash = _normalized_text_hash(row.extracted_text)
        if text_hash is not None:
            dropbox_by_text_hash.setdefault(text_hash, []).append(row)

        title_key = _title_name_key(full_name=row.full_name, document_title=row.document_title)
        if title_key is not None:
            dropbox_by_title_name.setdefault(title_key, []).append(row)

        normalized_full_name = _normalize_identity_token(row.full_name)
        if normalized_full_name is not None:
            dropbox_by_full_name.setdefault(normalized_full_name, []).append(row)

        filename_name_key = _full_name_token_key(
            full_name=row.full_name,
            fallback_value=row.document_title,
        )
        if filename_name_key is not None and _document_title_key(row.document_title) not in _GENERIC_TITLE_KEYS:
            dropbox_by_filename_name_key.setdefault(filename_name_key, []).append(row)

        source_filename_name_key = _full_name_token_key(
            full_name=row.full_name,
            fallback_value=_source_uri_attachment_name(row.source_uri),
        )
        if source_filename_name_key is not None:
            dropbox_by_source_filename_name_key.setdefault(
                source_filename_name_key,
                [],
            ).append(row)

        for extracted_name_key in _name_keys_from_extracted_text(row.extracted_text):
            dropbox_by_extracted_name_key.setdefault(extracted_name_key, []).append(row)

        for email in _emails_from_extracted_text(row.extracted_text):
            dropbox_by_email.setdefault(email, []).append(row)

        for linkedin_slug in _linkedin_slugs_from_extracted_text(row.extracted_text):
            dropbox_by_linkedin_slug.setdefault(linkedin_slug, []).append(row)

    exact_hash_recoveries: list[dict[str, object]] = []
    exact_hash_ambiguous: list[dict[str, object]] = []
    exact_text_recoveries: list[dict[str, object]] = []
    exact_text_ambiguous: list[dict[str, object]] = []
    title_name_review_matches: list[dict[str, object]] = []
    title_name_ambiguous: list[dict[str, object]] = []
    profile_identity_review_matches: list[dict[str, object]] = []
    profile_identity_ambiguous: list[dict[str, object]] = []
    filename_name_review_matches: list[dict[str, object]] = []
    filename_name_ambiguous: list[dict[str, object]] = []
    source_uri_filename_review_matches: list[dict[str, object]] = []
    source_uri_filename_ambiguous: list[dict[str, object]] = []
    extracted_text_name_review_matches: list[dict[str, object]] = []
    extracted_text_name_ambiguous: list[dict[str, object]] = []
    email_identity_review_matches: list[dict[str, object]] = []
    email_identity_ambiguous: list[dict[str, object]] = []
    linkedin_identity_review_matches: list[dict[str, object]] = []
    linkedin_identity_ambiguous: list[dict[str, object]] = []
    unmatched: list[dict[str, object]] = []

    for missing in missing_rows:
        if isinstance(missing.content_hash, str) and missing.content_hash.strip() != "":
            hash_matches = dropbox_by_content_hash.get(missing.content_hash.strip(), [])
            hash_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=hash_matches,
                strategy="exact_content_hash",
            )
            if hash_result["status"] == "recovered":
                exact_hash_recoveries.append(hash_result)
                continue
            if hash_result["status"] == "ambiguous":
                exact_hash_ambiguous.append(hash_result)
                continue

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

        missing_emails = _emails_from_extracted_text(missing.extracted_text)
        if missing_emails:
            email_matches = [
                row
                for email in missing_emails
                for row in dropbox_by_email.get(email, [])
            ]
            email_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=email_matches,
                strategy="email_identity_review",
            )
            if email_result["status"] == "recovered":
                email_identity_review_matches.append(email_result)
                continue
            if email_result["status"] == "ambiguous":
                email_identity_ambiguous.append(email_result)
                continue

        missing_linkedin_slugs = _linkedin_slugs_from_extracted_text(missing.extracted_text)
        if missing_linkedin_slugs:
            linkedin_matches = [
                row
                for linkedin_slug in missing_linkedin_slugs
                for row in dropbox_by_linkedin_slug.get(linkedin_slug, [])
            ]
            linkedin_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=linkedin_matches,
                strategy="linkedin_identity_review",
            )
            if linkedin_result["status"] == "recovered":
                linkedin_identity_review_matches.append(linkedin_result)
                continue
            if linkedin_result["status"] == "ambiguous":
                linkedin_identity_ambiguous.append(linkedin_result)
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

        normalized_missing_name = _normalize_identity_token(missing.full_name)
        if normalized_missing_name is not None:
            full_name_matches = dropbox_by_full_name.get(normalized_missing_name, [])
            aligned_matches = [
                row
                for row in full_name_matches
                if _company_match(missing.current_company_name, row.current_company_name)
                or bool(_title_overlap(missing.current_title, row.current_title))
            ]
            profile_identity_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=aligned_matches,
                strategy="profile_identity_review",
            )
            if profile_identity_result["status"] == "recovered":
                profile_identity_review_matches.append(profile_identity_result)
                continue
            if profile_identity_result["status"] == "ambiguous":
                profile_identity_ambiguous.append(profile_identity_result)
                continue

        filename_name_key = _full_name_token_key(
            full_name=missing.full_name,
            fallback_value=missing.full_name,
        )
        if filename_name_key is not None:
            filename_name_matches = dropbox_by_filename_name_key.get(filename_name_key, [])
            filename_name_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=filename_name_matches,
                strategy="filename_name_review",
            )
            if filename_name_result["status"] == "recovered":
                filename_name_review_matches.append(filename_name_result)
                continue
            if filename_name_result["status"] == "ambiguous":
                filename_name_ambiguous.append(filename_name_result)
                continue

            source_uri_filename_matches = dropbox_by_source_filename_name_key.get(
                filename_name_key,
                [],
            )
            source_uri_filename_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=source_uri_filename_matches,
                strategy="source_uri_filename_review",
            )
            if source_uri_filename_result["status"] == "recovered":
                source_uri_filename_review_matches.append(source_uri_filename_result)
                continue
            if source_uri_filename_result["status"] == "ambiguous":
                source_uri_filename_ambiguous.append(source_uri_filename_result)
                continue

            extracted_text_name_matches = dropbox_by_extracted_name_key.get(
                filename_name_key,
                [],
            )
            extracted_text_name_result = _choose_unique_match(
                missing_row=missing,
                matched_rows=extracted_text_name_matches,
                strategy="extracted_text_name_review",
            )
            if extracted_text_name_result["status"] == "recovered":
                extracted_text_name_review_matches.append(extracted_text_name_result)
                continue
            if extracted_text_name_result["status"] == "ambiguous":
                extracted_text_name_ambiguous.append(extracted_text_name_result)
                continue

        unmatched.append(_missing_row_summary(missing, strategy="unmatched"))

    return {
        "exact_hash_recoveries": exact_hash_recoveries,
        "exact_hash_ambiguous": exact_hash_ambiguous,
        "exact_text_recoveries": exact_text_recoveries,
        "exact_text_ambiguous": exact_text_ambiguous,
        "title_name_review_matches": title_name_review_matches,
        "title_name_ambiguous": title_name_ambiguous,
        "profile_identity_review_matches": profile_identity_review_matches,
        "profile_identity_ambiguous": profile_identity_ambiguous,
        "filename_name_review_matches": filename_name_review_matches,
        "filename_name_ambiguous": filename_name_ambiguous,
        "source_uri_filename_review_matches": source_uri_filename_review_matches,
        "source_uri_filename_ambiguous": source_uri_filename_ambiguous,
        "extracted_text_name_review_matches": extracted_text_name_review_matches,
        "extracted_text_name_ambiguous": extracted_text_name_ambiguous,
        "email_identity_review_matches": email_identity_review_matches,
        "email_identity_ambiguous": email_identity_ambiguous,
        "linkedin_identity_review_matches": linkedin_identity_review_matches,
        "linkedin_identity_ambiguous": linkedin_identity_ambiguous,
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


def build_review_report(
    *,
    recovery_plan: dict[str, list[dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    review_candidates = []
    for group_name in (
        "email_identity_review_matches",
        "linkedin_identity_review_matches",
        "title_name_review_matches",
        "profile_identity_review_matches",
        "filename_name_review_matches",
        "source_uri_filename_review_matches",
        "extracted_text_name_review_matches",
        "email_identity_ambiguous",
        "linkedin_identity_ambiguous",
        "title_name_ambiguous",
        "profile_identity_ambiguous",
        "filename_name_ambiguous",
        "source_uri_filename_ambiguous",
        "extracted_text_name_ambiguous",
        "exact_hash_ambiguous",
        "exact_text_ambiguous",
    ):
        for candidate in recovery_plan.get(group_name, []):
            if str(candidate.get("strategy", "")).endswith("_same_candidate"):
                continue
            review_candidates.append(_decorate_review_candidate(candidate))

    unmatched_candidates = [
        _decorate_unmatched_candidate(candidate)
        for candidate in recovery_plan.get("unmatched", [])
    ]

    review_candidates.sort(
        key=lambda item: (
            -int(item["confidence_score"]),
            str(item.get("full_name") or ""),
            str(item.get("candidate_id") or ""),
        )
    )
    unmatched_candidates.sort(
        key=lambda item: (
            -int(item["priority_score"]),
            str(item.get("full_name") or ""),
            str(item.get("candidate_id") or ""),
        )
    )

    return {
        "review_candidates": review_candidates,
        "unmatched_candidates": unmatched_candidates,
    }


def _decorate_review_candidate(candidate: dict[str, object]) -> dict[str, object]:
    confidence_score = 0
    strategy = str(candidate.get("strategy") or "")
    document_title_key = _document_title_key(candidate.get("document_title"))
    if strategy == "filename_name_review":
        confidence_score += 60
    elif strategy == "source_uri_filename_review":
        confidence_score += 65
    elif strategy == "extracted_text_name_review":
        confidence_score += 70
    elif strategy == "email_identity_review":
        confidence_score += 95
    elif strategy == "linkedin_identity_review":
        confidence_score += 90
    elif strategy == "title_name_review":
        confidence_score += 55
    elif "ambiguous" in strategy:
        confidence_score += 40
    if document_title_key and document_title_key not in _GENERIC_TITLE_KEYS:
        confidence_score += 15
    if _full_name_token_count(candidate.get("full_name")) >= 2:
        confidence_score += 10
    if isinstance(candidate.get("current_title"), str) and candidate["current_title"].strip():
        confidence_score += 5

    confidence_label = "low"
    if confidence_score >= 75:
        confidence_label = "high"
    elif confidence_score >= 55:
        confidence_label = "medium"

    return {
        **candidate,
        "confidence_score": confidence_score,
        "confidence_label": confidence_label,
    }


def _decorate_unmatched_candidate(candidate: dict[str, object]) -> dict[str, object]:
    priority_score = 0
    document_title_key = _document_title_key(candidate.get("document_title"))
    if document_title_key and document_title_key not in _GENERIC_TITLE_KEYS:
        priority_score += 20
    if _full_name_token_count(candidate.get("full_name")) >= 2:
        priority_score += 10
    if isinstance(candidate.get("current_title"), str) and candidate["current_title"].strip():
        priority_score += 5

    return {
        **candidate,
        "priority_score": priority_score,
    }


def _normalized_text_hash(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    normalized = _WHITESPACE_RE.sub(" ", text.strip()).casefold()
    if normalized == "":
        return None
    return md5(normalized.encode("utf-8")).hexdigest()


def _emails_from_extracted_text(text: str | None) -> list[str]:
    emails: set[str] = set()
    for segment in _contact_scan_segments(text, join_adjacent=False):
        emails.update(_EMAIL_RE.findall(segment))
    return sorted(emails)


def _linkedin_slugs_from_extracted_text(text: str | None) -> list[str]:
    slugs: set[str] = set()
    for segment in _contact_scan_segments(text, join_adjacent=True):
        for slug in _LINKEDIN_SLUG_RE.findall(segment):
            if _is_plausible_linkedin_slug(slug):
                slugs.add(slug)
    return sorted(slugs)


def _contact_scan_segments(text: str | None, *, join_adjacent: bool) -> list[str]:
    if not isinstance(text, str):
        return []
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    raw_lines = [line for line in normalized.splitlines() if line.strip()]
    compact_lines = [re.sub(r"\s+", "", line.casefold()) for line in raw_lines]
    compact_lines = [line for line in compact_lines if line]

    segments: list[str] = []
    seen: set[str] = set()
    for index, line in enumerate(compact_lines):
        if line not in seen:
            seen.add(line)
            segments.append(line)
        if join_adjacent and index + 1 < len(compact_lines):
            joined = line + compact_lines[index + 1]
            if joined not in seen:
                seen.add(joined)
                segments.append(joined)
    return segments


def _normalize_identity_token(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _IDENTITY_RE.sub("", value.casefold())
    return normalized or None


def _document_title_key(document_title: str | None) -> str | None:
    return _normalize_identity_token(document_title)


def _company_match(left: object, right: object) -> bool:
    normalized_left = _normalize_free_text(left)
    normalized_right = _normalize_free_text(right)
    if normalized_left == "" or normalized_right == "":
        return False
    if normalized_left == normalized_right:
        return True
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return True

    compact_left = normalized_left.replace(" ", "")
    compact_right = normalized_right.replace(" ", "")
    if compact_left == compact_right:
        return True
    return compact_left in compact_right or compact_right in compact_left


def _title_overlap(left: object, right: object) -> list[str]:
    stop_words = {
        "senior",
        "lead",
        "principal",
        "vice",
        "president",
        "director",
        "associate",
        "manager",
        "software",
        "engineer",
        "developer",
        "head",
        "of",
        "and",
        "the",
    }
    left_tokens = {
        token
        for token in _normalize_free_text(left).split()
        if len(token) >= 4 and token not in stop_words
    }
    right_tokens = {
        token
        for token in _normalize_free_text(right).split()
        if len(token) >= 4 and token not in stop_words
    }
    return sorted(left_tokens & right_tokens)


def _normalize_free_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _full_name_token_key(
    *,
    full_name: str | None,
    fallback_value: str | None,
) -> tuple[str, ...] | None:
    normalized_name = _normalize_identity_token(full_name)
    normalized_value = _normalize_identity_token(fallback_value)
    if normalized_name is None or normalized_value is None:
        return None

    parts = [part for part in re.split(r"[^a-z0-9]+", full_name.casefold()) if part]
    cleaned_parts = tuple(
        part
        for part in parts
        if len(part) >= 3 and part not in {"cv", "resume", "profile"}
    )
    if len(cleaned_parts) < 2:
        return None

    normalized_parts = tuple(sorted(_normalize_identity_token(part) for part in cleaned_parts if _normalize_identity_token(part)))
    if not normalized_parts:
        return None

    if not all(part in normalized_value for part in normalized_parts):
        return None

    return normalized_parts


def _full_name_token_count(full_name: object) -> int:
    if not isinstance(full_name, str):
        return 0
    parts = [part for part in re.split(r"[^a-z0-9]+", full_name.casefold()) if part]
    return sum(1 for part in parts if len(part) >= 3 and part not in {"cv", "resume", "profile"})


def _name_keys_from_extracted_text(text: str | None) -> list[tuple[str, ...]]:
    if not isinstance(text, str):
        return []

    keys: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:12]:
        key = _name_key_from_text_line(line)
        if key is None or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _name_key_from_text_line(line: str) -> tuple[str, ...] | None:
    normalized_line = _normalize_free_text(line)
    if normalized_line == "":
        return None
    if any(char.isdigit() for char in line):
        return None
    if any(term in normalized_line.split() for term in _NAME_LINE_EXCLUDE_TERMS):
        return None

    parts = [
        part
        for part in re.split(r"[^a-z]+", line.casefold())
        if len(part) >= 2 and part not in {"cv", "resume", "profile"}
    ]
    if len(parts) < 2 or len(parts) > 5:
        return None

    token_key = tuple(sorted(_normalize_identity_token(part) for part in parts if _normalize_identity_token(part)))
    if len(token_key) < 2:
        return None
    return token_key


def _is_plausible_linkedin_slug(slug: str) -> bool:
    if len(slug) < 6 or slug.startswith("-") or slug.endswith("-"):
        return False
    tokens = [token for token in slug.split("-") if token]
    if len(tokens) >= 2:
        return True
    return any(char.isdigit() for char in slug)


def _source_uri_attachment_name(source_uri: str | None) -> str | None:
    if not isinstance(source_uri, str) or source_uri.strip() == "":
        return None

    candidate_marker = "#candidate="
    attachment_marker = "&attachment="
    if attachment_marker in source_uri:
        attachment_value = source_uri.split(attachment_marker, 1)[1]
        attachment_name = re.split(r"[\\/]", attachment_value)[-1].strip()
        return attachment_name or None

    source_path = source_uri.removeprefix("dropbox:///")
    if candidate_marker in source_path:
        source_path = source_path.split(candidate_marker, 1)[0]
    source_name = re.split(r"[\\/]", source_path)[-1].strip()
    return source_name or None


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
    return _apply_recoveries(
        cursor,
        connection=connection,
        recoveries=exact_recoveries,
        batch_size=batch_size,
        label="Recovered source_uri",
    )


def _apply_recoveries(
    cursor,
    *,
    connection,
    recoveries: list[dict[str, object]],
    batch_size: int,
    label: str,
) -> int:
    update_rows = [
        {
            "document_id": recovery["document_id"],
            "source_uri": recovery["matched_source_uri"],
        }
        for recovery in recoveries
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
        print(f"{label} batch committed: {processed}/{len(update_rows)}")
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
