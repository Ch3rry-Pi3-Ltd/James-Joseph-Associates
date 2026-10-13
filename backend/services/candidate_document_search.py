"""Auditable current-CV search, pagination, coverage, and CSV export."""

from __future__ import annotations

import base64
import csv
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
import json
import re
from typing import Any
from uuid import UUID

from backend.core.read_budget import bounded_read
from backend.db.candidate_document_search import (
    iter_current_resume_document_matches,
    search_current_resume_documents,
)
from backend.db.candidates import get_candidate_source_details
from backend.services.candidate_source_metadata import (
    classify_candidate_source_category,
)


class CandidateDocumentSearchCursorError(ValueError):
    """Raised when a document-search cursor is malformed or incomplete."""


@bounded_read
def search_candidate_documents(
    *,
    query: str,
    page_size: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Search all searchable current CVs and return one auditable result page."""

    normalized_query = query.strip()
    bounded_page_size = max(1, min(int(page_size), 100))
    cursor_values = decode_candidate_document_search_cursor(cursor)
    database_result = search_current_resume_documents(
        query=normalized_query,
        limit=bounded_page_size + 1,
        **cursor_values,
    )
    raw_results = list(database_result["results"])
    has_more = len(raw_results) > bounded_page_size
    page_rows = raw_results[:bounded_page_size]
    results = _enrich_document_results(page_rows)
    coverage = _normalise_coverage(database_result["coverage"])

    next_cursor = None
    if has_more and page_rows:
        next_cursor = encode_candidate_document_search_cursor(page_rows[-1])

    return {
        "query": normalized_query,
        "scope": "current_resume",
        "page_size": bounded_page_size,
        "returned_result_count": len(results),
        "has_more": has_more,
        "next_cursor": next_cursor,
        "coverage": coverage,
        "results": results,
    }


def stream_candidate_document_search_csv(*, query: str) -> Iterator[str]:
    """Stream every matching current CV as a formula-safe UTF-8 CSV."""

    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "candidate_id",
            "candidate_name",
            "current_title",
            "current_company",
            "candidate_status",
            "resume_updated_at",
            "document_id",
            "original_filename",
            "document_source_uri",
            "source_systems",
            "match_score",
            "matching_evidence",
        ]
    )
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for batch in iter_current_resume_document_matches(query=query):
        for result in _enrich_document_results(batch):
            writer.writerow(
                [
                    _csv_cell(result.get("candidate_id")),
                    _csv_cell(result.get("full_name")),
                    _csv_cell(result.get("current_title")),
                    _csv_cell(result.get("current_company_name")),
                    _csv_cell(result.get("candidate_status")),
                    _csv_cell(result.get("resume_updated_at")),
                    _csv_cell(result.get("document_id")),
                    _csv_cell(result.get("document_title")),
                    _csv_cell(result.get("document_source_uri")),
                    _csv_cell(", ".join(result.get("source_systems", []))),
                    _csv_cell(result.get("match_score")),
                    _csv_cell(_strip_highlight_markup(result.get("match_excerpt"))),
                ]
            )
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


def encode_candidate_document_search_cursor(row: dict[str, Any]) -> str:
    """Encode the deterministic rank tuple used by keyset pagination."""

    updated_at = row.get("sort_resume_updated_at")
    payload = {
        "score": str(row["match_score"]),
        "updated_at": (
            updated_at.isoformat()
            if isinstance(updated_at, datetime)
            else str(updated_at)
        ),
        "candidate_id": str(row["candidate_id"]),
        "document_id": str(row["document_id"]),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return encoded.rstrip("=")


def decode_candidate_document_search_cursor(
    cursor: str | None,
) -> dict[str, Any]:
    """Decode and validate an opaque document-search cursor."""

    if cursor is None or not cursor.strip():
        return {
            "after_score": None,
            "after_updated_at": None,
            "after_candidate_id": None,
            "after_document_id": None,
        }

    try:
        normalized = cursor.strip()
        padding = "=" * (-len(normalized) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(normalized + padding).decode("utf-8")
        )
        score = Decimal(str(payload["score"]))
        if not score.is_finite():
            raise ValueError
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        candidate_id = str(UUID(str(payload["candidate_id"])))
        document_id = str(UUID(str(payload["document_id"])))
    except (
        InvalidOperation,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise CandidateDocumentSearchCursorError(
            "Document-search cursor is invalid or expired."
        ) from exc

    return {
        "after_score": score,
        "after_updated_at": updated_at,
        "after_candidate_id": candidate_id,
        "after_document_id": document_id,
    }


def _enrich_document_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_ids = {
        str(row.get("candidate_id") or "").strip()
        for row in rows
        if str(row.get("candidate_id") or "").strip()
    }
    source_details_by_candidate = get_candidate_source_details(candidate_ids)
    enriched: list[dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        candidate_id = str(row.get("candidate_id") or "")
        source_details = source_details_by_candidate.get(candidate_id, [])
        source_systems = [str(detail["source_system"]) for detail in source_details]
        row.pop("sort_resume_updated_at", None)
        row["candidate_id"] = candidate_id
        row["person_id"] = str(row.get("person_id") or "")
        row["document_id"] = str(row.get("document_id") or "")
        row["resume_updated_at"] = _normalise_datetime(row.get("resume_updated_at"))
        row["match_score"] = float(row.get("match_score") or 0)
        row["source_details"] = [
            {
                "source_system": str(detail.get("source_system") or ""),
                "latest_record_received_at": _normalise_datetime(
                    detail.get("latest_record_received_at")
                ),
            }
            for detail in source_details
            if str(detail.get("source_system") or "")
        ]
        row["source_systems"] = source_systems
        row["source_category"] = classify_candidate_source_category(
            source_systems,
            has_resume_document=True,
        )
        row["download_url"] = f"/api/v1/candidates/{candidate_id}/current-resume"
        enriched.append(row)
    return enriched


def _normalise_coverage(raw_coverage: dict[str, Any]) -> dict[str, Any]:
    coverage = {
        key: int(raw_coverage.get(key) or 0)
        for key in (
            "total_candidates",
            "eligible_document_count",
            "searchable_document_count",
            "excluded_missing_text_count",
            "candidates_without_current_resume_count",
            "matched_document_count",
            "matched_candidate_count",
        )
    }
    coverage["searched_document_count"] = coverage["searchable_document_count"]
    coverage["coverage_status"] = (
        "complete"
        if coverage["excluded_missing_text_count"] == 0
        else "complete_with_exclusions"
    )
    coverage["is_exhaustive"] = coverage["excluded_missing_text_count"] == 0
    return coverage


def _normalise_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _strip_highlight_markup(value: Any) -> str:
    return re.sub(r"</?mark>", "", str(value or ""), flags=re.IGNORECASE)


def _csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


__all__ = [
    "CandidateDocumentSearchCursorError",
    "decode_candidate_document_search_cursor",
    "encode_candidate_document_search_cursor",
    "search_candidate_documents",
    "stream_candidate_document_search_csv",
]
