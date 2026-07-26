"""Controlled native Linked Helper backup import planning and execution."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from typing import Any

from backend.db.linkedin_helper_persistence import (
    persist_linkedin_helper_company_snapshot,
    persist_linkedin_helper_person_snapshot,
)
from backend.services.linkedin_helper_backup import (
    map_linkedin_helper_backup_companies,
    map_linkedin_helper_backup_people,
)
from backend.services.linkedin_helper_ingestion import (
    build_linkedin_helper_person_persistence_payload,
)
from backend.services.linkedin_helper_reconciliation import (
    build_canonical_company_identity_index,
    build_canonical_identity_index,
    normalize_text_key,
    reconcile_linkedin_helper_companies,
    reconcile_linkedin_helper_people,
)

MAX_IMPORT_LIMIT = 100
MAX_RELATED_COMPANIES = 250


def build_linkedin_helper_backup_import_plan(
    *,
    content_bytes: bytes,
    limit: int,
    offset: int,
    people_snapshot: dict[str, Any],
    companies_snapshot: dict[str, Any],
    import_run_id: str,
) -> dict[str, Any]:
    """Build a bounded plan that excludes every ambiguous canonical identity."""

    if limit <= 0 or limit > MAX_IMPORT_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_IMPORT_LIMIT}.")
    if offset < 0:
        raise ValueError("offset must be zero or greater.")

    people = map_linkedin_helper_backup_people(
        content_bytes,
        limit=limit,
        offset=offset,
        include_profile_details=True,
        import_run_id=import_run_id,
    )
    people_report = reconcile_linkedin_helper_people(
        payloads=people,
        canonical_index=build_canonical_identity_index(
            people=people_snapshot["people"],
            source_links=people_snapshot["source_links"],
        ),
    )
    people_by_source_id = {
        str(payload["source_record_id"]): payload for payload in people
    }

    all_companies = map_linkedin_helper_backup_companies(
        content_bytes,
        limit=None,
        offset=0,
        import_run_id=import_run_id,
    )
    company_name_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    company_original_id_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for company in all_companies:
        name_key = normalize_text_key(company.get("name"))
        if name_key:
            company_name_index[name_key].append(company)
        original_id = company.get("source_payload", {}).get("original_id")
        if original_id is not None:
            company_original_id_index[str(original_id)].append(company)

    related_companies: dict[str, dict[str, Any]] = {}
    unresolved_role_companies = 0
    for result in people_report["results"]:
        if result["classification"] not in {"matched", "new"}:
            continue
        person = people_by_source_id[str(result["source_record_id"])]
        for company_name, company_original_id in _iter_person_company_references(person):
            company = _resolve_source_company(
                company_name=company_name,
                company_original_id=company_original_id,
                name_index=company_name_index,
                original_id_index=company_original_id_index,
            )
            if company is None:
                unresolved_role_companies += 1
                continue
            related_companies[str(company["source_record_id"])] = company

    if len(related_companies) > MAX_RELATED_COMPANIES:
        raise ValueError(
            "Bounded people slice references too many companies "
            f"({len(related_companies)} > {MAX_RELATED_COMPANIES})."
        )

    company_payloads = list(related_companies.values())
    company_report = reconcile_linkedin_helper_companies(
        payloads=company_payloads,
        canonical_index=build_canonical_company_identity_index(
            companies=companies_snapshot["companies"],
            source_links=companies_snapshot["source_links"],
        ),
    )
    company_decisions = {
        str(result["source_record_id"]): result
        for result in company_report["results"]
    }

    planned_people: list[dict[str, Any]] = []
    for result in people_report["results"]:
        if result["classification"] not in {"matched", "new"}:
            continue
        person = people_by_source_id[str(result["source_record_id"])]
        planned_people.append(
            {
                "payload": person,
                "classification": result["classification"],
                "canonical_person_id": _single_id(
                    result.get("canonical_person_ids")
                ),
                "current_company_source_record_id": _resolve_company_source_id(
                    company_name=person.get("company_name"),
                    company_original_id=None,
                    name_index=company_name_index,
                    original_id_index=company_original_id_index,
                ),
                "employment_history": _plan_employment_history(
                    person,
                    company_name_index=company_name_index,
                    company_original_id_index=company_original_id_index,
                ),
            }
        )

    return {
        "limit": limit,
        "offset": offset,
        "people_report": people_report,
        "company_report": company_report,
        "company_decisions": company_decisions,
        "company_payloads": related_companies,
        "people": planned_people,
        "unresolved_role_companies": unresolved_role_companies,
    }


def execute_linkedin_helper_backup_import_plan(
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Execute only safe rows from a previously reconciled bounded plan."""

    company_ids: dict[str, str] = {}
    company_results: list[dict[str, Any]] = []
    skipped_companies = Counter()
    for source_record_id, payload in plan["company_payloads"].items():
        decision = plan["company_decisions"][source_record_id]
        classification = decision["classification"]
        if classification not in {"matched", "new"}:
            skipped_companies[classification] += 1
            continue
        persistence_payload = {
            **payload,
            "source_payload_hash": _hash_json(payload["source_payload"]),
        }
        result = persist_linkedin_helper_company_snapshot(
            persistence_payload,
            canonical_company_id=_single_id(
                decision.get("canonical_company_ids")
            ),
        )
        company_ids[source_record_id] = str(result["company_id"])
        company_results.append(result)

    person_results: list[dict[str, Any]] = []
    for row in plan["people"]:
        payload = dict(row["payload"])
        current_company_id = company_ids.get(
            row["current_company_source_record_id"]
        )
        employment_roles = [
            {
                **role,
                "company_id": company_ids[role["company_source_record_id"]],
            }
            for role in row["employment_history"]
            if role["company_source_record_id"] in company_ids
        ]
        payload["employment_roles"] = employment_roles
        payload["skills"] = payload["source_payload"].get("skills", [])
        if current_company_id is None:
            payload["company_name"] = None
            payload["company_domain"] = None
            payload["company_website_url"] = None
            payload["company_linkedin_url"] = None
            payload["is_current_company"] = False
        persistence_payload = build_linkedin_helper_person_persistence_payload(payload)
        result = persist_linkedin_helper_person_snapshot(
            persistence_payload,
            canonical_person_id=row["canonical_person_id"],
            canonical_company_id=current_company_id,
        )
        person_results.append(result)

    return {
        "people_persisted": len(person_results),
        "companies_persisted": len(company_results),
        "roles_persisted": sum(
            len(result["employment_role_ids"]) for result in person_results
        ),
        "skills_persisted": sum(
            len(result["person_skill_ids"]) for result in person_results
        ),
        "skipped_companies": dict(skipped_companies),
        "person_results": person_results,
        "company_results": company_results,
    }


def _iter_person_company_references(
    person: dict[str, Any],
) -> list[tuple[str | None, str | None]]:
    references = [(person.get("company_name"), None)]
    for role in person.get("source_payload", {}).get("employment_history", []):
        references.append((role.get("company_name"), role.get("company_id")))
    return references


def _plan_employment_history(
    person: dict[str, Any],
    *,
    company_name_index: dict[str, list[dict[str, Any]]],
    company_original_id_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    for role in person.get("source_payload", {}).get("employment_history", []):
        company_source_record_id = _resolve_company_source_id(
            company_name=role.get("company_name"),
            company_original_id=role.get("company_id"),
            name_index=company_name_index,
            original_id_index=company_original_id_index,
        )
        if company_source_record_id is None:
            continue
        roles.append(
            {
                "company_source_record_id": company_source_record_id,
                "role_title": _clean_string(role.get("title")),
                "start_date": _parse_role_date(role, prefix="start"),
                "end_date": _parse_role_date(role, prefix="end"),
                "is_current": bool(role.get("is_default")) or not any(
                    (
                        role.get("end"),
                        role.get("end_year"),
                        role.get("end_month"),
                    )
                ),
            }
        )
    return roles


def _resolve_company_source_id(
    *,
    company_name: Any,
    company_original_id: Any,
    name_index: dict[str, list[dict[str, Any]]],
    original_id_index: dict[str, list[dict[str, Any]]],
) -> str | None:
    company = _resolve_source_company(
        company_name=company_name,
        company_original_id=company_original_id,
        name_index=name_index,
        original_id_index=original_id_index,
    )
    return str(company["source_record_id"]) if company is not None else None


def _resolve_source_company(
    *,
    company_name: Any,
    company_original_id: Any,
    name_index: dict[str, list[dict[str, Any]]],
    original_id_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    if company_original_id is not None:
        matches = original_id_index.get(str(company_original_id), [])
        if len(matches) == 1:
            return matches[0]
    name_key = normalize_text_key(company_name)
    matches = name_index.get(name_key or "", [])
    return matches[0] if len(matches) == 1 else None


def _parse_role_date(role: dict[str, Any], *, prefix: str) -> date | None:
    direct = role.get(prefix)
    if isinstance(direct, str):
        cleaned = direct.strip()[:10]
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            pass
    year = role.get(f"{prefix}_year")
    month = role.get(f"{prefix}_month")
    if not isinstance(year, int) or isinstance(year, bool) or year < 1900:
        return None
    safe_month = month if isinstance(month, int) and 1 <= month <= 12 else 1
    return date(year, safe_month, 1)


def _single_id(values: Any) -> str | None:
    if not isinstance(values, list) or len(values) != 1:
        return None
    return str(values[0])


def _hash_json(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.replace("\x00", "").strip()
    return cleaned or None


__all__ = [
    "MAX_IMPORT_LIMIT",
    "build_linkedin_helper_backup_import_plan",
    "execute_linkedin_helper_backup_import_plan",
]
