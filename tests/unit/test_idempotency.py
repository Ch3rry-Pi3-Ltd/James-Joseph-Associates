"""
Unit tests for shared idempotency helper functions.

These tests check the retry-safety utilities in `backend.core.idempotency`.

The important question is:

    "Can the backend recognise a safe retry versus a risky duplicate request?"

That matters because future Make.com-facing endpoints will receive write
requests. Make.com scenarios can retry requests after errors, and the backend
should not accidentally create duplicate records or duplicate workflow actions.

These tests do not call real API routes.

They test the helper functions directly:

    normalise_idempotency_key(...)
    require_idempotency_key(...)
    canonicalise_json_payload(...)
    hash_payload(...)
    build_idempotency_metadata(...)
    detect_idempotency_conflict(...)
    get_request_idempotency_key(...)

The expected behaviour is:

- missing idempotency keys are rejected
- blank idempotency keys are rejected
- useful idempotency keys are trimmed and accepted
- equivalent JSON payloads produce the same canonical form
- equivalent JSON payloads produce the same hash
- different JSON payloads produce different hashes
- same key plus same payload hash is treated as a safe retry
- same key plus different payload hash is treated as a conflict

In plain language:

- this file checks the small idempotency helper tools
- it does not store anything in Supabase
- it does not call Make.com
- it does not decide business-level duplicates
- it prepares the backend for safe protected write routes later
"""

import pytest
from fastapi import Request

from backend.core.idempotency import (
    IdempotencyConflict,
    IdempotencyFailureReason,
    IdempotencyMetadata,
    build_idempotency_metadata,
    canonicalise_json_payload,
    detect_idempotency_conflict,
    get_request_idempotency_key,
    hash_payload,
    normalise_idempotency_key,
    require_idempotency_key,
)


def make_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    """
    Build a minimal FastAPI request object for idempotency helper tests.

    The request-level helper in `backend.core.idempotency` expects a FastAPI
    `Request` object so it can read the `Idempotency-Key` header.

    These tests do not need a real server or a real route. They only need a
    request object with headers attached.

    Parameters
    ----------
    headers : list[tuple[bytes, bytes]] | None
        Optional ASGI-style request headers.

        ASGI stores headers as byte pairs:

            (header_name, header_value)

        For example:

            (b"idempotency-key", b"make-run-123-step-1")

    Returns
    -------
    Request
        Minimal FastAPI request object containing the supplied headers.

    Notes
    -----
    - This does not start Uvicorn.
    - This does not call the real app.
    - This does not send a network request.
    - It only creates enough request structure for idempotency-header tests.

    In plain language:

    - build a fake request
    - attach fake idempotency headers
    - pass it into the idempotency helper functions
    """

    # FastAPI's `Request` object is built from an ASGI scope.
    #   - The scope is a dictionary describing the incoming request.
    #   - For these tests, we only need the request type, method, path, and
    #     headers.
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/protected-write-example",
            "headers": headers or [],
        }
    )


def test_normalise_idempotency_key_returns_none_for_missing_value() -> None:
    """
    Verify that a missing idempotency key stays missing.

    FastAPI returns `None` when a header is not present on the request.

    Notes
    -----
    - Missing retry keys should not become an empty string.
    - Returning `None` makes it clear that the client did not provide the key.
    - The required-key helper later turns this into a precise failure reason.

    In plain language:

    - no idempotency key came in
    - no usable idempotency key should come out
    """

    assert normalise_idempotency_key(None) is None


def test_normalise_idempotency_key_returns_none_for_blank_value() -> None:
    """
    Verify that blank idempotency key values are treated as missing.

    A client can accidentally send the header name without useful content.

    For example:

        Idempotency-Key:

    Notes
    -----
    - Empty strings are not usable retry keys.
    - Whitespace-only strings are not usable retry keys.
    - Both should become `None`.
    """

    assert normalise_idempotency_key("") is None
    assert normalise_idempotency_key("   ") is None


def test_normalise_idempotency_key_trims_useful_text() -> None:
    """
    Verify that useful idempotency key text is stripped of surrounding whitespace.

    Clients or workflow tools may accidentally add spaces around header values.

    For example:

        Idempotency-Key:  make-run-123-step-1 

    Notes
    -----
    - The useful value is `make-run-123-step-1`.
    - Leading and trailing spaces are not meaningful.
    - The helper should clean the value before endpoint code uses it.
    """

    assert (
        normalise_idempotency_key(" make-run-123-step-1 ")
        == "make-run-123-step-1"
    )


def test_require_idempotency_key_rejects_missing_key() -> None:
    """
    Verify that a missing idempotency key returns a missing-key reason.

    Notes
    -----
    - Future write endpoints should usually require idempotency keys.
    - Missing keys should be rejected before business logic runs.
    """

    result = require_idempotency_key(None)

    assert result == IdempotencyFailureReason.MISSING_IDEMPOTENCY_KEY


def test_require_idempotency_key_rejects_blank_key() -> None:
    """
    Verify that a blank idempotency key returns a blank-key reason.

    Notes
    -----
    - Blank strings are different from missing headers internally.
    - Keeping a separate reason makes future API error details clearer.
    """

    result = require_idempotency_key("   ")

    assert result == IdempotencyFailureReason.BLANK_IDEMPOTENCY_KEY


def test_require_idempotency_key_returns_clean_key() -> None:
    """
    Verify that a useful idempotency key is trimmed and accepted.

    In plain language:

    - the client sent a retry key
    - the helper removes accidental spaces
    - the endpoint receives the clean value
    """

    result = require_idempotency_key(" make-run-123-step-1 ")

    assert result == "make-run-123-step-1"


def test_canonicalise_json_payload_sorts_dictionary_keys() -> None:
    """
    Verify that equivalent dictionaries produce the same canonical JSON string.

    Dictionary insertion order should not affect idempotency payload
    fingerprints.

    These payloads are equivalent:

        {"b": 2, "a": 1}

        {"a": 1, "b": 2}

    Notes
    -----
    - Stable canonicalisation is needed before hashing.
    - Otherwise, equivalent JSON could produce different hashes.
    """

    first_payload = {"b": 2, "a": 1}
    second_payload = {"a": 1, "b": 2}

    assert canonicalise_json_payload(first_payload) == canonicalise_json_payload(
        second_payload
    )


def test_canonicalise_json_payload_removes_unnecessary_spaces() -> None:
    """
    Verify that canonical JSON output is compact.

    The canonical payload string is designed for hashing, not display.

    Notes
    -----
    - Compact output avoids whitespace-driven hash differences.
    - The exact compact string also makes this behaviour easy to test.
    """

    payload = {
        "source_system": "make",
        "source_record_id": "abc-123",
    }

    assert (
        canonicalise_json_payload(payload)
        == '{"source_record_id":"abc-123","source_system":"make"}'
    )


def test_hash_payload_returns_same_hash_for_equivalent_payloads() -> None:
    """
    Verify that equivalent JSON payloads produce the same hash.

    Notes
    -----
    - The two dictionaries contain the same data.
    - Their keys are inserted in different orders.
    - The resulting hash should still match.
    """

    first_payload = {"b": 2, "a": 1}
    second_payload = {"a": 1, "b": 2}

    assert hash_payload(first_payload) == hash_payload(second_payload)


def test_hash_payload_returns_different_hash_for_different_payloads() -> None:
    """
    Verify that different JSON payloads produce different hashes.

    In plain language:

    - the request body changed
    - the fingerprint should change too
    """

    first_payload = {"source_record_id": "abc-123"}
    second_payload = {"source_record_id": "xyz-999"}

    assert hash_payload(first_payload) != hash_payload(second_payload)


def test_build_idempotency_metadata_returns_clean_key_and_payload_hash() -> None:
    """
    Verify that idempotency metadata is built from a key and payload.

    Notes
    -----
    - The key should be normalised.
    - The payload should be hashed.
    - The returned object should contain both values.
    """

    payload = {"source_record_id": "abc-123"}

    metadata = build_idempotency_metadata(
        key=" make-run-123-step-1 ",
        payload=payload,
    )

    assert metadata == IdempotencyMetadata(
        key="make-run-123-step-1",
        payload_hash=hash_payload(payload),
    )


def test_build_idempotency_metadata_rejects_blank_key() -> None:
    """
    Verify that metadata cannot be built with a blank idempotency key.

    Notes
    -----
    - A blank key cannot safely protect a write request from duplicates.
    - The helper raises `ValueError` because this is programmer misuse.
    """

    with pytest.raises(ValueError):
        build_idempotency_metadata(
            key="   ",
            payload={"source_record_id": "abc-123"},
        )


def test_detect_idempotency_conflict_returns_none_for_matching_hashes() -> None:
    """
    Verify that same key plus same payload hash is treated as safe.

    This represents a likely retry of the same request.

    Notes
    -----
    - Future service code may return the original response for this case.
    - The helper only says there is no conflict.
    """

    payload_hash = hash_payload({"source_record_id": "abc-123"})

    conflict = detect_idempotency_conflict(
        key="make-run-123-step-1",
        existing_payload_hash=payload_hash,
        incoming_payload_hash=payload_hash,
    )

    assert conflict is None


def test_detect_idempotency_conflict_returns_conflict_for_different_hashes() -> None:
    """
    Verify that same key plus different payload hash is treated as a conflict.

    This means the caller reused an idempotency key for different content.

    Notes
    -----
    - The backend should reject this later.
    - Processing it would be unsafe because the key no longer identifies one
      stable request.
    """

    existing_payload_hash = hash_payload({"source_record_id": "abc-123"})
    incoming_payload_hash = hash_payload({"source_record_id": "xyz-999"})

    conflict = detect_idempotency_conflict(
        key="make-run-123-step-1",
        existing_payload_hash=existing_payload_hash,
        incoming_payload_hash=incoming_payload_hash,
    )

    assert conflict == IdempotencyConflict(
        key="make-run-123-step-1",
        existing_payload_hash=existing_payload_hash,
        incoming_payload_hash=incoming_payload_hash,
    )


def test_get_request_idempotency_key_reads_header() -> None:
    """
    Verify that request-level idempotency checks read `Idempotency-Key`.

    This test checks the wrapper that accepts a FastAPI `Request`.

    Notes
    -----
    - Real protected write endpoints will receive a `Request` object from
      FastAPI.
    - This helper reads the header and delegates to `require_idempotency_key`.
    """

    request = make_request(
        headers=[
            (b"idempotency-key", b"make-run-123-step-1"),
        ]
    )

    result = get_request_idempotency_key(request)

    assert result == "make-run-123-step-1"


def test_get_request_idempotency_key_reports_missing_header() -> None:
    """
    Verify that request-level checks report a missing idempotency header.

    In plain language:

    - the request has no `Idempotency-Key` header
    - the helper rejects it with a clear reason
    """

    request = make_request()

    result = get_request_idempotency_key(request)

    assert result == IdempotencyFailureReason.MISSING_IDEMPOTENCY_KEY


def test_get_request_idempotency_key_reports_blank_header() -> None:
    """
    Verify that request-level checks report a blank idempotency header.

    In plain language:

    - the request has an `Idempotency-Key` header
    - but the value contains only whitespace
    - the helper rejects it with a clear reason
    """

    request = make_request(
        headers=[
            (b"idempotency-key", b"   "),
        ]
    )

    result = get_request_idempotency_key(request)

    assert result == IdempotencyFailureReason.BLANK_IDEMPOTENCY_KEY