"""
Service helpers for Linked Helper person/contact ingestion.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from backend.db.linkedin_helper_persistence import (
    persist_linkedin_helper_person_snapshot,
)


def ingest_linkedin_helper_person(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize and persist one Linked Helper sourced person/contact payload.
    """

    persistence_payload = build_linkedin_helper_person_persistence_payload(payload)
    return persist_linkedin_helper_person_snapshot(persistence_payload)


def build_linkedin_helper_person_persistence_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the normalized persistence payload for one Linked Helper row.
    """

    source_payload = _sanitize_json_ready_value(payload["source_payload"])
    record_kind = payload["record_kind"]
    contact_type = _clean_optional_string(payload.get("contact_type"))
    is_hiring_manager = bool(payload.get("is_hiring_manager"))

    if contact_type is None and record_kind == "contact":
        contact_type = "client_contact"
    if contact_type is None and record_kind == "hiring_manager":
        contact_type = "hiring_manager"
        is_hiring_manager = True

    first_name = _clean_optional_string(payload.get("first_name"))
    last_name = _clean_optional_string(payload.get("last_name"))
    full_name = _clean_optional_string(payload.get("full_name")) or _build_full_name(
        first_name=first_name,
        last_name=last_name,
    )

    source_record_id = _clean_optional_string(payload.get("source_record_id"))
    if source_record_id is None:
        source_record_id = _build_fallback_source_record_id(
            linkedin_url=_clean_optional_string(payload.get("linkedin_url")),
            primary_email=_clean_optional_string(payload.get("primary_email")),
            full_name=full_name,
            company_name=_clean_optional_string(payload.get("company_name")),
        )

    import_run_id = _clean_optional_string(payload.get("import_run_id"))
    if import_run_id is None:
        import_run_id = (
            f"linkedin_helper_person_export:{source_record_id}:"
            f"{datetime.now(timezone.utc).isoformat()}"
        )

    return {
        "source_record_id": source_record_id,
        "source_payload": source_payload,
        "source_payload_hash": _hash_json_ready_payload(source_payload),
        "import_run_id": import_run_id,
        "record_kind": record_kind,
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": _clean_optional_string(payload.get("primary_email")),
        "primary_phone": _clean_optional_string(payload.get("primary_phone")),
        "linkedin_url": _clean_optional_string(payload.get("linkedin_url")),
        "location": _clean_optional_string(payload.get("location")),
        "headline": _clean_optional_string(payload.get("headline")),
        "summary": _clean_optional_string(payload.get("summary")),
        "company_name": _clean_optional_string(payload.get("company_name")),
        "company_domain": _clean_optional_string(payload.get("company_domain")),
        "company_website_url": _clean_optional_string(payload.get("company_website_url")),
        "company_linkedin_url": _clean_optional_string(payload.get("company_linkedin_url")),
        "role_title": _clean_optional_string(payload.get("role_title")),
        "seniority": _clean_optional_string(payload.get("seniority")),
        "postcode": _clean_optional_string(payload.get("postcode")),
        "contact_type": contact_type,
        "is_hiring_manager": is_hiring_manager,
        "is_current_company": bool(payload.get("is_current_company", True)),
        "role_start_date": payload.get("role_start_date"),
        "role_end_date": payload.get("role_end_date"),
        "candidate_status": _clean_optional_string(payload.get("candidate_status")),
        "availability_status": _clean_optional_string(payload.get("availability_status")),
        "resume_updated_at": payload.get("resume_updated_at"),
        "last_contacted_at": payload.get("last_contacted_at"),
        "employment_roles": payload.get("employment_roles", []),
        "skills": [
            skill
            for value in payload.get("skills", [])
            for skill in [_clean_optional_string(value)]
            if skill is not None
        ],
    }


def _build_fallback_source_record_id(
    *,
    linkedin_url: str | None,
    primary_email: str | None,
    full_name: str,
    company_name: str | None,
) -> str:
    stable_key = linkedin_url or primary_email or f"{full_name}:{company_name or ''}"
    return hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]


def _build_full_name(*, first_name: str | None, last_name: str | None) -> str:
    joined_name = " ".join(
        part for part in (first_name, last_name) if part is not None and part != ""
    ).strip()
    if joined_name != "":
        return joined_name
    return "Unknown Person"


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
    "build_linkedin_helper_person_persistence_payload",
    "ingest_linkedin_helper_person",
]
