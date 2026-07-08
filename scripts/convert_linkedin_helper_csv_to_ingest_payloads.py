"""
Convert a Linked Helper style CSV export into backend ingest payload JSON.

This script exists for one operational purpose:

    "Take a rough Linked Helper CSV export and normalize it into the protected
    backend ingest payload shape."
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
from typing import Any

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "source_record_id": ("id", "record id", "person id", "profile id"),
    "full_name": ("full name", "name", "person name"),
    "first_name": ("first name", "firstname", "given name"),
    "last_name": ("last name", "lastname", "surname", "family name"),
    "primary_email": ("email", "email address", "work email", "personal email"),
    "primary_phone": ("phone", "mobile", "phone number", "mobile number"),
    "linkedin_url": (
        "linkedin url",
        "linkedin",
        "profile url",
        "linkedin profile",
        "person linkedin url",
    ),
    "location": ("location", "city", "region", "country"),
    "headline": ("headline", "tagline"),
    "summary": ("summary", "about", "bio"),
    "company_name": ("company", "current company", "company name"),
    "company_domain": ("company domain", "domain", "website domain"),
    "company_website_url": ("company website", "website", "company url"),
    "company_linkedin_url": ("company linkedin url", "company linkedin"),
    "role_title": ("title", "job title", "position", "current title"),
    "seniority": ("seniority", "level"),
    "postcode": ("postcode", "zip", "zip code", "postal code"),
}


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a Linked Helper style CSV export into backend ingest payload JSON."
        )
    )
    parser.add_argument("--input-csv", required=True, help="Path to the source CSV file.")
    parser.add_argument(
        "--output-json",
        required=True,
        help="Path to the normalized output JSON file.",
    )
    parser.add_argument(
        "--record-kind",
        choices=("candidate", "contact", "hiring_manager"),
        default="contact",
        help="Default canonical record kind to assign to each row.",
    )
    parser.add_argument(
        "--contact-type",
        default=None,
        help="Optional explicit contact_type override for contact/hiring-manager rows.",
    )
    parser.add_argument(
        "--is-hiring-manager",
        action="store_true",
        help="Mark every output row as a hiring manager contact.",
    )
    return parser


def normalize_header(value: str) -> str:
    """
    Normalize a CSV header for loose alias matching.
    """

    lowered = value.strip().casefold()
    collapsed = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", collapsed).strip()


def clean_optional_string(value: Any) -> str | None:
    """
    Return a stripped string or None when the input is blank-like.
    """

    if not isinstance(value, str):
        return None
    cleaned = value.replace("\x00", "").strip()
    if cleaned == "":
        return None
    return cleaned


def find_row_value(
    row: dict[str, Any],
    normalized_header_map: dict[str, str],
    target_field: str,
) -> str | None:
    """
    Return the first row value matching the target field aliases.
    """

    for alias in FIELD_ALIASES.get(target_field, ()):
        original_header = normalized_header_map.get(normalize_header(alias))
        if original_header is None:
            continue
        cleaned = clean_optional_string(row.get(original_header))
        if cleaned is not None:
            return cleaned
    return None


def build_payload_from_row(
    *,
    row: dict[str, Any],
    normalized_header_map: dict[str, str],
    row_index: int,
    default_record_kind: str,
    contact_type_override: str | None,
    is_hiring_manager: bool,
) -> dict[str, Any]:
    """
    Build one backend ingest payload from one CSV row.
    """

    payload: dict[str, Any] = {
        "source_payload": {
            key: value.replace("\x00", "") if isinstance(value, str) else value
            for key, value in row.items()
        },
        "record_kind": default_record_kind,
    }

    for field_name in FIELD_ALIASES:
        payload[field_name] = find_row_value(
            row,
            normalized_header_map,
            field_name,
        )

    if payload.get("source_record_id") is None:
        linkedin_url = payload.get("linkedin_url")
        primary_email = payload.get("primary_email")
        full_name = payload.get("full_name")
        payload["source_record_id"] = (
            linkedin_url
            or primary_email
            or f"linkedin-helper-csv-row-{row_index + 1}"
            or full_name
        )

    if payload.get("full_name") is None:
        first_name = payload.get("first_name")
        last_name = payload.get("last_name")
        payload["full_name"] = " ".join(
            part for part in (first_name, last_name) if part
        ).strip() or f"Unknown Person {row_index + 1}"

    payload["contact_type"] = (
        contact_type_override
        if contact_type_override is not None
        else (
            "hiring_manager"
            if default_record_kind == "hiring_manager" or is_hiring_manager
            else None
        )
    )
    payload["is_hiring_manager"] = bool(
        is_hiring_manager or default_record_kind == "hiring_manager"
    )
    payload["is_current_company"] = True
    payload["role_start_date"] = None
    payload["role_end_date"] = None
    payload["candidate_status"] = None
    payload["availability_status"] = None
    payload["resume_updated_at"] = None
    payload["last_contacted_at"] = None

    return payload


def convert_csv_to_payloads(
    *,
    input_csv: str,
    default_record_kind: str,
    contact_type_override: str | None,
    is_hiring_manager: bool,
) -> list[dict[str, Any]]:
    """
    Convert the source CSV into normalized backend ingest payloads.
    """

    csv_path = pathlib.Path(input_csv)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError("CSV file is missing a header row.")

        normalized_header_map = {
            normalize_header(header): header
            for header in reader.fieldnames
            if isinstance(header, str)
        }

        payloads: list[dict[str, Any]] = []
        for row_index, row in enumerate(reader):
            payloads.append(
                build_payload_from_row(
                    row=row,
                    normalized_header_map=normalized_header_map,
                    row_index=row_index,
                    default_record_kind=default_record_kind,
                    contact_type_override=contact_type_override,
                    is_hiring_manager=is_hiring_manager,
                )
            )
        return payloads


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    payloads = convert_csv_to_payloads(
        input_csv=args.input_csv,
        default_record_kind=args.record_kind,
        contact_type_override=args.contact_type,
        is_hiring_manager=args.is_hiring_manager,
    )

    output_path = pathlib.Path(args.output_json)
    output_path.write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "input_csv": str(pathlib.Path(args.input_csv)),
                "output_json": str(output_path),
                "payload_count": len(payloads),
                "record_kind": args.record_kind,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
