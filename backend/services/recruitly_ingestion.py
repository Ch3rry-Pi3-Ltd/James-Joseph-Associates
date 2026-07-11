"""
Service helpers for Recruitly company/contact ingestion.
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
)
from backend.services.recruitly_api import (
    fetch_recruitly_companies_preview,
    fetch_recruitly_contacts_preview,
)

RecruitlyIngestResource = Literal["companies", "contacts"]

_RECRUITLY_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"


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

    if resource == "companies":
        preview = fetch_recruitly_companies_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
        normalized_import_run_id = import_run_id or _build_import_run_id(
            resource=resource,
            page=page,
        )
        persisted_rows = [
            ingest_recruitly_company(row, import_run_id=normalized_import_run_id)
            for row in preview["data"]
        ]
    else:
        preview = fetch_recruitly_contacts_preview(
            api_base_url=api_base_url,
            api_key=api_key,
            query=query,
            page=page,
            size=size,
        )
        normalized_import_run_id = import_run_id or _build_import_run_id(
            resource=resource,
            page=page,
        )
        persisted_rows = [
            ingest_recruitly_contact(row, import_run_id=normalized_import_run_id)
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
    """
    Normalize and persist one Recruitly company payload.
    """

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
    """
    Normalize and persist one Recruitly contact payload.
    """

    persistence_payload = build_recruitly_contact_persistence_payload(
        payload,
        import_run_id=import_run_id,
    )
    return persist_recruitly_contact_snapshot(persistence_payload)


def build_recruitly_company_persistence_payload(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    """
    Build the normalized persistence payload for one Recruitly company row.
    """

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
        "created_at": _parse_recruitly_datetime(payload.get("createdOn")),
        "updated_at": _parse_recruitly_datetime(payload.get("updatedOn")),
    }


def build_recruitly_contact_persistence_payload(
    payload: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    """
    Build the normalized persistence payload for one Recruitly contact row.
    """

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


def _build_import_run_id(*, resource: RecruitlyIngestResource, page: int) -> str:
    return f"recruitly:{resource}:page:{page}:{datetime.now(timezone.utc).isoformat()}"


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


def _parse_recruitly_datetime(value: Any) -> datetime | None:
    cleaned_value = _clean_optional_string(value)
    if cleaned_value is None:
        return None
    try:
        parsed = datetime.strptime(cleaned_value, _RECRUITLY_DATETIME_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


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
    "ingest_recruitly_collection_page",
    "ingest_recruitly_company",
    "ingest_recruitly_contact",
]
