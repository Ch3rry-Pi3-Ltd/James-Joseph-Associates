"""Deterministic, read-only Linked Helper person reconciliation."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import unquote, urlparse

MATCH_METHOD_PRIORITY = (
    "existing_source_link",
    "linkedin_profile",
    "email",
    "phone",
    "name_and_company",
)
COMPANY_MATCH_METHOD_PRIORITY = (
    "existing_source_link",
    "linkedin_company",
    "domain",
    "name",
)


def build_canonical_company_identity_index(
    *,
    companies: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
) -> dict[str, dict[str, set[str]]]:
    """Build company indexes without hiding duplicate canonical identities."""

    index: dict[str, dict[str, set[str]]] = {
        "existing_source_link": defaultdict(set),
        "linkedin_company": defaultdict(set),
        "domain": defaultdict(set),
        "name": defaultdict(set),
    }
    for row in source_links:
        source_record_id = _clean_optional_string(row.get("source_record_id"))
        company_id = _clean_optional_string(row.get("company_id"))
        if source_record_id and company_id:
            index["existing_source_link"][source_record_id].add(company_id)

    for row in companies:
        company_id = _clean_optional_string(row.get("company_id"))
        if company_id is None:
            continue
        linkedin_key = normalize_linkedin_company(row.get("linkedin_url"))
        if linkedin_key:
            index["linkedin_company"][linkedin_key].add(company_id)

        domain_keys = {
            key
            for value in (row.get("domain"), row.get("website_url"))
            for key in [normalize_domain(value)]
            if key
        }
        for domain_key in domain_keys:
            index["domain"][domain_key].add(company_id)

        name_key = normalize_text_key(row.get("name"))
        if name_key:
            index["name"][name_key].add(company_id)
    return index


def build_canonical_identity_index(
    *,
    people: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
) -> dict[str, dict[str, set[str]]]:
    """Build multi-value indexes so duplicate canonical keys remain visible."""

    index: dict[str, dict[str, set[str]]] = {
        "existing_source_link": defaultdict(set),
        "linkedin_profile": defaultdict(set),
        "email": defaultdict(set),
        "phone": defaultdict(set),
        "name_and_company": defaultdict(set),
        "name": defaultdict(set),
    }
    for row in source_links:
        source_record_id = _clean_optional_string(row.get("source_record_id"))
        person_id = _clean_optional_string(row.get("person_id"))
        if source_record_id and person_id:
            index["existing_source_link"][source_record_id].add(person_id)

    for row in people:
        person_id = _clean_optional_string(row.get("person_id"))
        if person_id is None:
            continue
        name_key = normalize_text_key(row.get("full_name"))
        if name_key:
            index["name"][name_key].add(person_id)

        linkedin_key = normalize_linkedin_profile(row.get("linkedin_url"))
        if linkedin_key:
            index["linkedin_profile"][linkedin_key].add(person_id)

        email_key = normalize_email(row.get("primary_email"))
        if email_key:
            index["email"][email_key].add(person_id)

        phone_key = normalize_phone(row.get("primary_phone"))
        if phone_key:
            index["phone"][phone_key].add(person_id)

        for company_name in _iter_company_names(row):
            company_key = normalize_text_key(company_name)
            if name_key and company_key:
                index["name_and_company"][f"{name_key}|{company_key}"].add(person_id)
    return index


def reconcile_linkedin_helper_people(
    *,
    payloads: list[dict[str, Any]],
    canonical_index: dict[str, dict[str, set[str]]],
) -> dict[str, Any]:
    """Classify mapped people as matched, new, ambiguous, or skipped."""

    source_name_company_counts = Counter(
        key
        for payload in payloads
        for key in [_payload_name_company_key(payload)]
        if key is not None
    )
    results = [
        _classify_payload(
            payload,
            canonical_index=canonical_index,
            source_name_company_counts=source_name_company_counts,
        )
        for payload in payloads
    ]
    classification_counts = Counter(result["classification"] for result in results)
    match_method_counts = Counter(
        str(result["match_method"])
        for result in results
        if result.get("match_method")
    )
    return {
        "total": len(results),
        "matched": classification_counts["matched"],
        "new": classification_counts["new"],
        "ambiguous": classification_counts["ambiguous"],
        "skipped": classification_counts["skipped"],
        "match_methods": dict(sorted(match_method_counts.items())),
        "results": results,
    }


def reconcile_linkedin_helper_companies(
    *,
    payloads: list[dict[str, Any]],
    canonical_index: dict[str, dict[str, set[str]]],
) -> dict[str, Any]:
    """Classify mapped organisations as matched, new, ambiguous, or skipped."""

    source_name_counts = Counter(
        key
        for payload in payloads
        for key in [normalize_text_key(payload.get("name"))]
        if key is not None
    )
    results = [
        _classify_company_payload(
            payload,
            canonical_index=canonical_index,
            source_name_counts=source_name_counts,
        )
        for payload in payloads
    ]
    classification_counts = Counter(result["classification"] for result in results)
    match_method_counts = Counter(
        str(result["match_method"])
        for result in results
        if result.get("match_method")
    )
    return {
        "total": len(results),
        "matched": classification_counts["matched"],
        "new": classification_counts["new"],
        "ambiguous": classification_counts["ambiguous"],
        "skipped": classification_counts["skipped"],
        "match_methods": dict(sorted(match_method_counts.items())),
        "results": results,
    }


def _classify_company_payload(
    payload: dict[str, Any],
    *,
    canonical_index: dict[str, dict[str, set[str]]],
    source_name_counts: Counter[str],
) -> dict[str, Any]:
    source_record_id = _clean_optional_string(payload.get("source_record_id"))
    name = _clean_optional_string(payload.get("name"))
    linkedin_url = _clean_optional_string(payload.get("linkedin_url"))
    domain = normalize_domain(payload.get("domain") or payload.get("website_url"))
    base_result = {
        "source_record_id": source_record_id,
        "name": name,
        "linkedin_url": linkedin_url,
        "domain": domain,
        "canonical_company_ids": [],
        "match_method": None,
        "reason": None,
    }

    name_key = normalize_text_key(name)
    source_name_count = _payload_source_identity_count(
        payload,
        field_name="source_name_count",
        fallback=source_name_counts.get(name_key or "", 0),
    )
    signal_values: dict[str, list[str]] = {
        "existing_source_link": [source_record_id] if source_record_id else [],
        "linkedin_company": _payload_linkedin_company_keys(payload),
        "domain": [domain] if domain else [],
        "name": (
            [name_key]
            if name_key is not None and source_name_count == 1
            else []
        ),
    }
    method_matches: dict[str, set[str]] = {}
    ambiguous_methods: list[str] = []
    for method in COMPANY_MATCH_METHOD_PRIORITY:
        matched_ids: set[str] = set()
        for value in signal_values[method]:
            matched_ids.update(canonical_index[method].get(value, set()))
        if len(matched_ids) > 1:
            ambiguous_methods.append(method)
        elif matched_ids:
            method_matches[method] = matched_ids

    all_matched_ids = set().union(*method_matches.values()) if method_matches else set()
    if ambiguous_methods or len(all_matched_ids) > 1:
        return {
            **base_result,
            "classification": "ambiguous",
            "canonical_company_ids": sorted(all_matched_ids),
            "reason": (
                "non_unique_" + "_and_".join(ambiguous_methods)
                if ambiguous_methods
                else "conflicting_deterministic_signals"
            ),
        }

    if len(all_matched_ids) == 1:
        match_method = next(
            method
            for method in COMPANY_MATCH_METHOD_PRIORITY
            if method in method_matches
        )
        return {
            **base_result,
            "classification": "matched",
            "canonical_company_ids": sorted(all_matched_ids),
            "match_method": match_method,
        }

    name_matches = canonical_index["name"].get(name_key, set()) if name_key else set()
    if name_matches:
        return {
            **base_result,
            "classification": "ambiguous",
            "canonical_company_ids": sorted(name_matches),
            "reason": "name_only_review_candidate",
        }

    if not any((source_record_id, linkedin_url, domain, name_key)):
        return {
            **base_result,
            "classification": "skipped",
            "reason": "missing_usable_identity",
        }
    return {**base_result, "classification": "new"}


def _classify_payload(
    payload: dict[str, Any],
    *,
    canonical_index: dict[str, dict[str, set[str]]],
    source_name_company_counts: Counter[str],
) -> dict[str, Any]:
    source_record_id = _clean_optional_string(payload.get("source_record_id"))
    full_name = _clean_optional_string(payload.get("full_name"))
    company_name = _clean_optional_string(payload.get("company_name"))
    linkedin_url = _clean_optional_string(payload.get("linkedin_url"))
    base_result = {
        "source_record_id": source_record_id,
        "full_name": full_name,
        "linkedin_url": linkedin_url,
        "company_name": company_name,
        "canonical_person_ids": [],
        "match_method": None,
        "reason": None,
    }

    signal_values: dict[str, list[str]] = {
        "existing_source_link": [source_record_id] if source_record_id else [],
        "linkedin_profile": _payload_linkedin_keys(payload),
        "email": [
            value
            for value in [normalize_email(payload.get("primary_email"))]
            if value
        ],
        "phone": [
            value
            for value in [normalize_phone(payload.get("primary_phone"))]
            if value
        ],
        "name_and_company": [],
    }
    name_company_key = _payload_name_company_key(payload)
    source_name_company_count = _payload_source_identity_count(
        payload,
        field_name="source_name_company_count",
        fallback=source_name_company_counts.get(name_company_key or "", 0),
    )
    if (
        name_company_key is not None
        and source_name_company_count == 1
    ):
        signal_values["name_and_company"] = [name_company_key]

    method_matches: dict[str, set[str]] = {}
    ambiguous_methods: list[str] = []
    for method in MATCH_METHOD_PRIORITY:
        matched_ids: set[str] = set()
        for value in signal_values[method]:
            matched_ids.update(canonical_index[method].get(value, set()))
        if len(matched_ids) > 1:
            ambiguous_methods.append(method)
        elif matched_ids:
            method_matches[method] = matched_ids

    all_matched_ids = set().union(*method_matches.values()) if method_matches else set()
    if ambiguous_methods or len(all_matched_ids) > 1:
        return {
            **base_result,
            "classification": "ambiguous",
            "canonical_person_ids": sorted(all_matched_ids),
            "reason": (
                "non_unique_" + "_and_".join(ambiguous_methods)
                if ambiguous_methods
                else "conflicting_deterministic_signals"
            ),
        }

    if len(all_matched_ids) == 1:
        match_method = next(
            method for method in MATCH_METHOD_PRIORITY if method in method_matches
        )
        return {
            **base_result,
            "classification": "matched",
            "canonical_person_ids": sorted(all_matched_ids),
            "match_method": match_method,
        }

    name_key = normalize_text_key(full_name)
    name_matches = canonical_index["name"].get(name_key, set()) if name_key else set()
    if name_matches:
        return {
            **base_result,
            "classification": "ambiguous",
            "canonical_person_ids": sorted(name_matches),
            "reason": "name_only_review_candidate",
        }

    has_stable_identity = any(
        (
            source_record_id,
            linkedin_url,
            normalize_email(payload.get("primary_email")),
            normalize_phone(payload.get("primary_phone")),
            name_key,
        )
    )
    if not has_stable_identity:
        return {
            **base_result,
            "classification": "skipped",
            "reason": "missing_usable_identity",
        }

    return {**base_result, "classification": "new"}


def _payload_linkedin_keys(payload: dict[str, Any]) -> list[str]:
    values: list[Any] = [payload.get("linkedin_url")]
    source_payload = payload.get("source_payload")
    if isinstance(source_payload, dict):
        public_identifiers = source_payload.get("public_identifiers")
        if isinstance(public_identifiers, list):
            values.extend(public_identifiers)
    return list(
        dict.fromkeys(
            key for value in values for key in [normalize_linkedin_profile(value)] if key
        )
    )


def _payload_source_identity_count(
    payload: dict[str, Any],
    *,
    field_name: str,
    fallback: int,
) -> int:
    source_payload = payload.get("source_payload")
    if isinstance(source_payload, dict):
        value = source_payload.get(field_name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return fallback


def _payload_linkedin_company_keys(payload: dict[str, Any]) -> list[str]:
    values: list[Any] = [payload.get("linkedin_url")]
    source_payload = payload.get("source_payload")
    if isinstance(source_payload, dict):
        for field_name in ("public_identifiers", "company_identifiers"):
            identifiers = source_payload.get(field_name)
            if isinstance(identifiers, list):
                values.extend(identifiers)
    return list(
        dict.fromkeys(
            key
            for value in values
            for key in [normalize_linkedin_company(value)]
            if key
        )
    )


def _payload_name_company_key(payload: dict[str, Any]) -> str | None:
    name_key = normalize_text_key(payload.get("full_name"))
    company_key = normalize_text_key(payload.get("company_name"))
    if not name_key or not company_key:
        return None
    return f"{name_key}|{company_key}"


def _iter_company_names(row: dict[str, Any]) -> list[str]:
    values: list[Any] = [row.get("company_name")]
    company_names = row.get("company_names")
    if isinstance(company_names, list):
        values.extend(company_names)
    return [
        cleaned
        for value in values
        for cleaned in [_clean_optional_string(value)]
        if cleaned
    ]


def normalize_linkedin_profile(value: Any) -> str | None:
    """Return a stable case-folded LinkedIn public profile slug."""

    cleaned = _clean_optional_string(value)
    if cleaned is None:
        return None
    decoded = unquote(cleaned).strip()
    parsed = urlparse(decoded if "://" in decoded else f"https://{decoded}")
    if parsed.netloc.casefold().endswith("linkedin.com") and "/in/" in parsed.path:
        slug = parsed.path.split("/in/", 1)[1].split("/", 1)[0]
        return slug.casefold() or None
    if "/" not in decoded and " " not in decoded:
        return decoded.casefold()
    return None


def normalize_linkedin_company(value: Any) -> str | None:
    """Return a stable case-folded LinkedIn company identifier."""

    cleaned = _clean_optional_string(value)
    if cleaned is None:
        return None
    decoded = unquote(cleaned).strip()
    parsed = urlparse(decoded if "://" in decoded else f"https://{decoded}")
    if parsed.netloc.casefold().endswith("linkedin.com") and "/company/" in parsed.path:
        identifier = parsed.path.split("/company/", 1)[1].split("/", 1)[0]
        return identifier.casefold() or None
    if "/" not in decoded and " " not in decoded:
        return decoded.casefold()
    return None


def normalize_domain(value: Any) -> str | None:
    cleaned = _clean_optional_string(value)
    if cleaned is None:
        return None
    parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
    hostname = parsed.hostname
    if hostname is None:
        return None
    normalized = hostname.casefold().strip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized or None


def normalize_email(value: Any) -> str | None:
    cleaned = _clean_optional_string(value)
    return cleaned.casefold() if cleaned else None


def normalize_phone(value: Any) -> str | None:
    cleaned = _clean_optional_string(value)
    if cleaned is None:
        return None
    digits = re.sub(r"\D", "", cleaned)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits if len(digits) >= 7 else None


def normalize_text_key(value: Any) -> str | None:
    cleaned = _clean_optional_string(value)
    if cleaned is None:
        return None
    normalized = unicodedata.normalize("NFKC", cleaned).casefold()
    collapsed = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", collapsed).strip() or None


def _clean_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.replace("\x00", "").strip()
    return cleaned or None


__all__ = [
    "build_canonical_company_identity_index",
    "build_canonical_identity_index",
    "normalize_domain",
    "normalize_email",
    "normalize_linkedin_company",
    "normalize_linkedin_profile",
    "normalize_phone",
    "normalize_text_key",
    "reconcile_linkedin_helper_companies",
    "reconcile_linkedin_helper_people",
]
