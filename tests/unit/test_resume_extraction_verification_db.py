"""
Unit tests for DB-side resume-extraction verification helpers.

This module pins the narrow normalization behaviour at the verification read
boundary.

It gives the rest of the repository a stable way to check:

- DB-native UUID values are converted to strings
- DB-native datetimes are converted to ISO strings
- nested verification snapshot payloads become JSON-safe before the service and
  script layers consume them
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from backend.db.resume_extraction_verification import _make_json_safe_value


def test_make_json_safe_value_normalizes_uuid_and_datetime_recursively() -> None:
    """
    Verify that verification snapshot values become JSON-safe recursively.

    Example
    -------
    A nested structure containing `UUID` and `datetime` values should come back
    with:

    - UUIDs converted to strings
    - datetimes converted to ISO strings
    """

    candidate_uuid = uuid4()
    checked_at = datetime(2026, 5, 13, 9, 30, tzinfo=timezone.utc)

    payload = {
        "candidate_profile": {
            "candidate_id": candidate_uuid,
            "checked_at": checked_at,
        },
        "source_record_links": [
            {"candidate_id": candidate_uuid},
        ],
    }

    normalized = _make_json_safe_value(payload)

    assert normalized["candidate_profile"]["candidate_id"] == str(candidate_uuid)
    assert normalized["candidate_profile"]["checked_at"] == checked_at.isoformat()
    assert normalized["source_record_links"][0]["candidate_id"] == str(candidate_uuid)


def test_make_json_safe_value_normalizes_decimal_values() -> None:
    """
    Verify that DB-native `Decimal` values become JSON-safe numeric values.

    Example
    -------
    A verification snapshot field such as:

        {"confidence": Decimal("1.0")}

    should come back as:

        {"confidence": 1.0}
    """

    payload = {
        "candidate_skills": [
            {"confidence": Decimal("1.0")},
        ]
    }

    normalized = _make_json_safe_value(payload)

    assert normalized["candidate_skills"][0]["confidence"] == 1.0
