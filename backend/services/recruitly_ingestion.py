"""
Service helpers for Recruitly canonical ingestion.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal
from urllib.parse import urlparse

from backend.db.recruitly_persistence import (
    persist_recruitly_company_snapshot,
    persist_recruitly_contact_snapshot,
    persist_recruitly_job_snapshot,
    persist_recruitly_journal_entries,
    persist_recruitly_opportunity_snapshot,
)
from backend.services.recruitly_api import (
    fetch_recruitly_companies_preview,
    fetch_recruitly_contacts_preview,
    fetch_recruitly_jobs_preview,
    fetch_recruitly_opportunities_preview,
    fetch_recruitly_record_journal_preview,
)

RecruitlyIngestResource = Literal["companies", "contacts", "jobs", "opportunities"]

_RECRUITLY_DATETIME_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
    "%d/%m/%Y",
)
_RECRUITLY_JOURNAL_SUBJECT_KEYS = (
    "subject",
    "title",
    "activityType",
    "activityTypeName",
    "type",
    "eventType",
)
_RECRUITLY_JOURNAL_BODY_KEYS = (
    "body",
    "description",
    "comment",
    "note",
    "message",
    "text",
    "details",
    "content",
)
_RECRUITLY_JOURNAL_DATE_KEYS = (
    "occurredAt",
    "createdOn",
    "updatedOn",
    "date",
    "timestamp",
    "createdAt",
    "updatedAt",
)


def ingest_recruitly_collection_page(
    *,
    resource: RecruitlyIngestResource,
    api_base_url: str,
    api_key: str,
    query: str | None = None,
    page: int = 0,
    size: int = 20,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    """
    Fetch one bounded Recruitly page and persist the canonical rows.
    """

    normalized_import_run_id = import_run_id or _build_import_run_id(
        resource=resource,
        page=page,
    )

    if resource == "companies":
        preview = fetch_recruitly_companies_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
        persisted_rows = [
            ingest_recruitly_company(row, import_run_id=normalized_import_run_id)
            for row in preview["data"]
        ]
    elif resource == "contacts":
        preview = fetch_recruitly_contacts_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
        persisted_rows = [
            ingest_recruitly_contact(row, import_run_id=normalized_import_run_id)
            for row in preview["data"]
        ]
    elif resource == "jobs":
        preview = fetch_recruitly_jobs_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
        persisted_rows = [
            ingest_recruitly_job(row, import_run_id=normalized_import_run_id)
            for row in preview["data"]
        ]
    else:
        preview = fetch_recruitly_opportunities_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
        persisted_rows = [
            ingest_recruitly_opportunity(
                row,
                import_run_id=normalized_import_run_id,
            )
            for row in preview["data"]
        ]

    return {
        "resource": resource,
        "query": preview["query"],
        "page": preview["page"],
        "size": preview["size"],
        "item_count": preview["item_count"],
        "total_count": preview["total_count"],
        "persisted_count": len(persisted_rows),
        "persisted": persisted_rows,
    }


def ingest_recruitly_company(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    persistence_payload = build_recruitly_company_persistence_payload(
        payload,
        import_run_id=import_run_id,
    )
    return persist_recruitly_company_snapshot(persistence_payload)


def ingest_recruitly_contact(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    persistence_payload = build_recruitly_contact_persistence_payload(
        payload,
        import_run_id=import_run_id,
    )
    return persist_recruitly_contact_snapshot(persistence_payload)


def ingest_recruitly_job(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    persistence_payload = build_recruitly_job_persistence_payload(
        payload,
        import_run_id=import_run_id,
    )
    return persist_recruitly_job_snapshot(persistence_payload)


def ingest_recruitly_opportunity(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    persistence_payload = build_recruitly_opportunity_persistence_payload(
        payload,
        import_run_id=import_run_id,
    )
    return persist_recruitly_opportunity_snapshot(persistence_payload)


def ingest_recruitly_record_journal(
    *,
    api_base_url: str,
    api_key: str,
    record_type: str,
    record_id: str,
    page: int = 0,
    size: int = 20,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    """
    Fetch one bounded Recruitly journal slice and persist canonical interactions.
    """

    preview = fetch_recruitly_record_journal_preview(
        api_base_url=api_base_url,
        api_key=api_key,
        record_type=record_type,
        record_id=record_id,
        page=page,
        size=size,
    )
    normalized_import_run_id = import_run_id or _build_journal_import_run_id(
        record_type=preview["record_type"],
        record_id=preview["record_id"],
        page=page,
    )
    persistence_payload = build_recruitly_journal_persistence_payload(
        preview["data"],
        record_type=preview["record_type"],
        record_source_record_id=preview["record_id"],
        import_run_id=normalized_import_run_id,
    )
    persisted = persist_recruitly_journal_entries(persistence_payload)

    return {
        "record_type": preview["record_type"],
        "record_id": preview["record_id"],
        "page": preview["page"],
        "size": preview["size"],
        "item_count": preview["item_count"],
        "total_count": preview["total_count"],
        "interaction_count": persisted["interaction_count"],
        "persisted": persisted["persisted"],
    }


def build_recruitly_company_persistence_payload(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    source_payload = _sanitize_json_ready_value(payload)
    source_record_id = _clean_optional_string(payload.get("id")) or _fallback_id(
        _clean_optional_string(payload.get("reference")),
        _clean_optional_string(payload.get("name")),
        _clean_optional_string(payload.get("website")),
    )
    website_url = _clean_optional_string(payload.get("website"))

    return {
        "source_record_id": source_record_id,
        "source_payload": source_payload,
        "source_payload_hash": _hash_json_ready_payload(source_payload),
        "import_run_id": import_run_id,
        "company_name": _clean_optional_string(payload.get("name")),
        "company_domain": _extract_domain(website_url),
        "company_website_url": website_url,
        "industry": _clean_optional_string(payload.get("sectorName")),
        "location": _clean_optional_string(payload.get("location")),
        "status": _clean_optional_string(payload.get("statusName")),
        "description": _clean_optional_string(payload.get("description")),
        "created_at": _parse_recruitly_datetime_like(payload.get("createdOn")),
        "updated_at": _parse_recruitly_datetime_like(payload.get("updatedOn")),
    }


def build_recruitly_contact_persistence_payload(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    source_payload = _sanitize_json_ready_value(payload)
    first_name = _clean_optional_string(payload.get("firstName"))
    last_name = _clean_optional_string(payload.get("lastName"))
    full_name = _build_full_name(first_name=first_name, last_name=last_name)
    primary_email = (
        _clean_optional_string(payload.get("email"))
        or _clean_optional_string(payload.get("alternateEmail"))
    )

    return {
        "source_record_id": _clean_optional_string(payload.get("id")) or _fallback_id(
            _clean_optional_string(payload.get("reference")),
            primary_email,
            _clean_optional_string(payload.get("linkedIn")),
            full_name,
        ),
        "source_payload": source_payload,
        "source_payload_hash": _hash_json_ready_payload(source_payload),
        "import_run_id": import_run_id,
        "company_source_record_id": _clean_optional_string(payload.get("companyId")),
        "company_name": _clean_optional_string(payload.get("companyName")),
        "company_domain": _extract_domain_from_email(primary_email),
        "company_website_url": None,
        "company_location": _clean_optional_string(payload.get("companyLocation")),
        "company_status": _clean_optional_string(payload.get("companyStatusName")),
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "primary_phone": (
            _clean_optional_string(payload.get("mobile"))
            or _clean_optional_string(payload.get("workPhone"))
        ),
        "linkedin_url": _clean_optional_string(payload.get("linkedIn")),
        "location": _clean_optional_string(payload.get("location")),
        "headline": _clean_optional_string(payload.get("jobTitle")),
        "summary": _clean_optional_string(payload.get("description")),
        "role_title": _clean_optional_string(payload.get("jobTitle")),
        "contact_type": "client_contact",
        "seniority": _clean_optional_string(payload.get("seniority")),
        "postcode": _clean_optional_string(payload.get("postcode")),
        "is_hiring_manager": False,
        "is_current_company": True,
        "role_start_date": None,
        "role_end_date": None,
        "industry": None,
    }


def build_recruitly_job_persistence_payload(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    source_payload = _sanitize_json_ready_value(payload)
    min_pay = _clean_optional_number(payload.get("minPay"))
    max_pay = _clean_optional_number(payload.get("maxPay"))
    if max_pay == 0:
        max_pay = None

    return {
        "source_record_id": _clean_optional_string(payload.get("id")) or _fallback_id(
            _clean_optional_string(payload.get("reference")),
            _clean_optional_string(payload.get("title")),
            _clean_optional_string(payload.get("companyId")),
        ),
        "source_payload": source_payload,
        "source_payload_hash": _hash_json_ready_payload(source_payload),
        "import_run_id": import_run_id,
        "company_source_record_id": _clean_optional_string(payload.get("companyId")),
        "contact_source_record_id": _clean_optional_string(payload.get("contactId")),
        "company_name": _clean_optional_string(payload.get("companyName")),
        "title": _clean_optional_string(payload.get("title"))
        or _clean_optional_string(payload.get("reference"))
        or "Untitled Job",
        "description": _first_non_empty_string(
            payload.get("internalDescription"),
            payload.get("shortDescription"),
            payload.get("description"),
        ),
        "location": _clean_optional_string(payload.get("location")),
        "workplace_type": (
            "remote"
            if payload.get("remoteWorking") is True
            else None
        ),
        "employment_type": _clean_optional_string(payload.get("employmentTypeName")),
        "work_type": None,
        "owner_name": _clean_optional_string(payload.get("ownerName")),
        "salary_min": min_pay,
        "salary_max": max_pay,
        "currency": _clean_optional_string(payload.get("payCurrency")),
        "status": _clean_optional_string(payload.get("statusName")),
        "opened_at": _parse_recruitly_datetime_like(
            payload.get("dateOpened") or payload.get("createdOn")
        ),
        "closed_at": None,
        "updated_from_source_at": _parse_recruitly_datetime_like(
            payload.get("updatedOn") or payload.get("lastActivityDate")
        ),
    }


def build_recruitly_opportunity_persistence_payload(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    source_payload = _sanitize_json_ready_value(payload)

    return {
        "source_record_id": _clean_optional_string(payload.get("id")) or _fallback_id(
            _clean_optional_string(payload.get("reference")),
            _clean_optional_string(payload.get("name")),
            _clean_optional_string(payload.get("companyId")),
        ),
        "source_payload": source_payload,
        "source_payload_hash": _hash_json_ready_payload(source_payload),
        "import_run_id": import_run_id,
        "company_source_record_id": _clean_optional_string(payload.get("companyId")),
        "contact_source_record_id": _clean_optional_string(payload.get("contactId")),
        "company_name": _clean_optional_string(payload.get("companyName")),
        "title": _clean_optional_string(payload.get("name"))
        or _clean_optional_string(payload.get("reference"))
        or "Untitled Opportunity",
        "smart_summary": _first_non_empty_string(
            payload.get("description"),
            payload.get("stateReason"),
        ),
        "stage": _first_non_empty_string(
            payload.get("stateName"),
            payload.get("statusName"),
            payload.get("stateReason"),
        ),
        "last_contact_at": _parse_recruitly_datetime_like(payload.get("updatedOn")),
        "next_task_at": _parse_recruitly_datetime_like(
            payload.get("forecastedClosingDate")
        ),
        "value": _clean_optional_number(payload.get("bidValue")),
    }


def build_recruitly_journal_persistence_payload(
    entries: list[dict[str, Any]],
    *,
    record_type: str,
    record_source_record_id: str,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    normalized_record_type = record_type.strip().lower()
    normalized_entries = [
        _build_recruitly_journal_entry_payload(
            entry,
            record_type=normalized_record_type,
            record_source_record_id=record_source_record_id,
        )
        for entry in entries
    ]

    return {
        "record_type": normalized_record_type,
        "record_source_record_id": record_source_record_id,
        "import_run_id": import_run_id,
        "entries": normalized_entries,
    }


def _build_recruitly_journal_entry_payload(
    payload: dict[str, Any],
    *,
    record_type: str,
    record_source_record_id: str,
) -> dict[str, Any]:
    source_payload = _sanitize_json_ready_value(payload)
    subject = _extract_recruitly_journal_subject(payload)
    body = _extract_recruitly_journal_body(payload)
    occurred_at = _extract_recruitly_journal_occurred_at(payload)
    source_record_id = _clean_optional_string(payload.get("id")) or _fallback_id(
        record_type,
        record_source_record_id,
        _clean_optional_string(payload.get("createdOn")),
        subject,
        body,
        json.dumps(source_payload, ensure_ascii=False, sort_keys=True),
    )

    return {
        "source_record_id": source_record_id,
        "source_payload": source_payload,
        "source_payload_hash": _hash_json_ready_payload(source_payload),
        "interaction_type": f"recruitly_{record_type}_journal_entry",
        "occurred_at": occurred_at,
        "subject": subject,
        "body": body,
        "summary": _build_journal_summary(subject=subject, body=body),
    }


def _build_import_run_id(*, resource: RecruitlyIngestResource, page: int) -> str:
    return f"recruitly:{resource}:page:{page}:{datetime.now(timezone.utc).isoformat()}"


def _build_journal_import_run_id(
    *,
    record_type: str,
    record_id: str,
    page: int,
) -> str:
    return (
        "recruitly:journal:"
        f"{record_type}:{record_id}:page:{page}:{datetime.now(timezone.utc).isoformat()}"
    )


def _extract_recruitly_journal_subject(payload: dict[str, Any]) -> str | None:
    for key in _RECRUITLY_JOURNAL_SUBJECT_KEYS:
        value = _clean_optional_string(payload.get(key))
        if value is not None:
            return value
    return None


def _extract_recruitly_journal_body(payload: dict[str, Any]) -> str | None:
    for key in _RECRUITLY_JOURNAL_BODY_KEYS:
        value = _clean_optional_string(payload.get(key))
        if value is not None:
            return value
    return None


def _extract_recruitly_journal_occurred_at(
    payload: dict[str, Any],
) -> datetime | None:
    for key in _RECRUITLY_JOURNAL_DATE_KEYS:
        parsed = _parse_recruitly_datetime_like(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _build_journal_summary(*, subject: str | None, body: str | None) -> str | None:
    if subject is not None and body is not None:
        return f"{subject}: {body[:200]}".strip()
    if body is not None:
        return body[:240]
    return subject


def _fallback_id(*values: str | None) -> str:
    stable_value = "|".join(value for value in values if value is not None and value != "")
    if stable_value == "":
        stable_value = "recruitly-unknown"
    return hashlib.sha256(stable_value.encode("utf-8")).hexdigest()[:24]


def _build_full_name(*, first_name: str | None, last_name: str | None) -> str:
    full_name = " ".join(
        part for part in (first_name, last_name) if part is not None and part != ""
    ).strip()
    if full_name != "":
        return full_name
    return "Unknown Person"


def _extract_domain(website_url: str | None) -> str | None:
    if website_url is None:
        return None
    parsed = urlparse(website_url)
    hostname = parsed.hostname
    if hostname is None or hostname.strip() == "":
        return None
    return hostname.lower()


def _extract_domain_from_email(email: str | None) -> str | None:
    if email is None or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].strip().lower() or None


def _parse_recruitly_datetime_like(value: Any) -> datetime | None:
    cleaned_value = _clean_optional_string(value)
    if cleaned_value is None:
        return None

    normalized_value = cleaned_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized_value)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    for fmt in _RECRUITLY_DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(cleaned_value, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _clean_optional_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned_value = value.replace(",", "").strip()
        if cleaned_value == "":
            return None
        try:
            return float(cleaned_value)
        except ValueError:
            return None
    return None


def _first_non_empty_string(*values: Any) -> str | None:
    for value in values:
        cleaned = _clean_optional_string(value)
        if cleaned is not None:
            return cleaned
    return None


def _clean_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned_value = value.replace("\x00", "").strip()
    if cleaned_value == "":
        return None
    return cleaned_value


def _sanitize_json_ready_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_sanitize_json_ready_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json_ready_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize_json_ready_value(nested_value)
            for key, nested_value in value.items()
        }
    return value


def _hash_json_ready_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


__all__ = [
    "build_recruitly_company_persistence_payload",
    "build_recruitly_contact_persistence_payload",
    "build_recruitly_job_persistence_payload",
    "build_recruitly_journal_persistence_payload",
    "build_recruitly_opportunity_persistence_payload",
    "ingest_recruitly_collection_page",
    "ingest_recruitly_company",
    "ingest_recruitly_contact",
    "ingest_recruitly_job",
    "ingest_recruitly_opportunity",
    "ingest_recruitly_record_journal",
]
