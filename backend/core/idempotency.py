"""
Standard idempotency helpers for the James Joseph Associates intelligence API.

This module contains small utilities for handling idempotency metadata.

It gives the rest of the repository a stable way to talk about:

- `Idempotency-Key` headers
- missing idempotency keys
- blank idempotency keys
- stable request payload fingerprints
- safe retry handling for Make.com
- future database-backed idempotency records

Keeping idempotency helpers in one place makes the project easier to extend because:

- endpoint modules do not need to repeat idempotency parsing logic
- Make.com retries can be handled consistently
- future write endpoints can share the same duplicate-request protection
- tests can verify idempotency behaviour without needing real business endpoints

In plain language:

- this module answers the question:

    "Is this write request safe to process, or have we seen it before?"

- it does not define API routes
- it does not connect to Supabase yet
- it does not store idempotency records yet
- it does not decide business-level duplicate logic
- it does not replace database constraints

Notes
-----
- This is a foundation module, not the full idempotency system.
- The first likely caller is Make.com.
- Make.com scenarios can retry requests after errors.
- Idempotency lets the backend avoid creating duplicate records or duplicate
  workflow actions during those retries.
- This module currently handles normalisation and payload hashing only.
- Future endpoint/service code can store idempotency keys and payload hashes in
  Supabase.
"""

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any

from fastapi import Request

from backend.core.http import IDEMPOTENCY_KEY_HEADER


class IdempotencyFailureReason(StrEnum):
    """
    Machine-readable reason why idempotency metadata could not be accepted.

    Attributes
    ----------
    MISSING_IDEMPOTENCY_KEY : str
        No `Idempotency-Key` value was provided.

    BLANK_IDEMPOTENCY_KEY : str
        The idempotency key existed but contained no useful text.

    IDEMPOTENCY_CONFLICT : str
        The same idempotency key was reused with different request content.

    Notes
    -----
    - These values are internal helper reasons.
    - Public API error codes should still use the shared API error schema.
    - A future endpoint may translate `IDEMPOTENCY_CONFLICT` into the public
      `idempotency_conflict` error code.

    In plain language:

    - this enum gives tests and future handlers a precise reason for
      idempotency failure.
    """

    MISSING_IDEMPOTENCY_KEY = "missing_idempotency_key"
    BLANK_IDEMPOTENCY_KEY = "blank_idempotency_key"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


@dataclass(frozen=True, slots=True)
class IdempotencyMetadata:
    """
    Normalised idempotency metadata for a write request.

    Attributes
    ----------
    key : str
        Normalised idempotency key.

        This usually comes from the `Idempotency-Key` request header.

    payload_hash : str
        Stable SHA-256 hash of the request payload.

        This can later be stored alongside the key so the backend can detect
        whether a retry is truly the same request.

    Notes
    -----
    - This object does not prove the request is new.
    - It only represents the metadata needed for a future lookup.
    - The actual "have we seen this before?" check will need a database table
      or another persistence layer.

    Example
    -------
    A Make.com request might send:

        Idempotency-Key: make-run-123-step-1

    with a JSON payload.

    This module can turn that into:

        IdempotencyMetadata(
            key="make-run-123-step-1",
            payload_hash="<sha256>"
        )

    In plain language:

    - keep the retry key
    - keep a fingerprint of the request body
    """

    key: str
    payload_hash: str


@dataclass(frozen=True, slots=True)
class IdempotencyConflict:
    """
    Description of an idempotency-key conflict.

    Attributes
    ----------
    key : str
        Idempotency key that was reused.

    existing_payload_hash : str
        Payload hash already recorded for the key.

    incoming_payload_hash : str
        Payload hash calculated for the current request.

    reason : IdempotencyFailureReason
        Machine-readable conflict reason.

    Notes
    -----
    - A conflict means the same idempotency key was used for different content.
    - That is unsafe because the backend cannot know which request the key was
      meant to represent.
    - Future endpoint code should turn this into a standard API error response.

    In plain language:

    - same retry key
    - different request body
    - reject it instead of guessing
    """

    key: str
    existing_payload_hash: str
    incoming_payload_hash: str
    reason: IdempotencyFailureReason = (
        IdempotencyFailureReason.IDEMPOTENCY_CONFLICT
    )


def normalise_idempotency_key(value: str | None) -> str | None:
    """
    Convert a raw idempotency key into a clean optional string.

    Parameters
    ----------
    value : str | None
        Raw idempotency key value.

        This usually comes from the `Idempotency-Key` request header.

    Returns
    -------
    str | None
        Cleaned idempotency key.

        The return value is:

        - a stripped string when the key contains useful text
        - `None` when the key is missing
        - `None` when the key contains only whitespace

    Notes
    -----
    - Idempotency keys are external request metadata.
    - Clients can accidentally send blank or whitespace-padded values.
    - This helper keeps key handling consistent across future endpoints.

    Example
    -------
    These values become useful strings:

        " make-run-123 " -> "make-run-123"
        "abc-123"        -> "abc-123"

    These values become `None`:

        None
        ""
        "   "

    In plain language:

    - remove accidental whitespace
    - treat empty values as missing
    """

    # Missing keys should remain missing.
    #   - FastAPI returns `None` when a header is not present.
    #   - Keeping that as `None` lets callers identify the missing-key case.
    if value is None:
        return None

    # Trim accidental whitespace from the full key.
    #   - This makes `" make-run-123 "` behave as `"make-run-123"`.
    normalised_value = value.strip()

    # Empty strings should not count as idempotency keys.
    #   - A header containing only spaces should behave like no header.
    if normalised_value == "":
        return None

    return normalised_value


def require_idempotency_key(
    value: str | None,
) -> str | IdempotencyFailureReason:
    """
    Return a normalised idempotency key or a failure reason.

    Parameters
    ----------
    value : str | None
        Raw idempotency key value.

    Returns
    -------
    str | IdempotencyFailureReason
        Normalised key when a useful value is present.

        A failure reason when the key is missing or blank.

    Notes
    -----
    - Write endpoints should usually require idempotency keys.
    - This helper does not raise an exception.
    - Returning a reason makes it easy for future endpoint code to build a
      standard API error response.

    In plain language:

    - accept a useful retry key
    - reject missing or blank retry keys clearly
    """

    if value is None:
        return IdempotencyFailureReason.MISSING_IDEMPOTENCY_KEY

    normalised_key = normalise_idempotency_key(value)

    if normalised_key is None:
        return IdempotencyFailureReason.BLANK_IDEMPOTENCY_KEY

    return normalised_key


def canonicalise_json_payload(payload: Any) -> str:
    """
    Convert a JSON-like payload into a stable string representation.

    Parameters
    ----------
    payload : Any
        JSON-like payload to canonicalise.

        This should usually be made from dictionaries, lists, strings, numbers,
        booleans, and `None`.

    Returns
    -------
    str
        Stable JSON string representation of the payload.

    Notes
    -----
    - Dictionary key order should not affect the resulting string.
    - Whitespace should not affect the resulting string.
    - The output is designed for hashing, not for display.
    - Non-JSON-serialisable objects should raise `TypeError`.

    Example
    -------
    These two payloads should produce the same canonical string:

        {"b": 2, "a": 1}

        {"a": 1, "b": 2}

    In plain language:

    - turn a payload into one predictable string
    - so equivalent JSON produces the same hash
    """

    # `sort_keys=True` makes dictionary order stable.
    #   - Without this, two equivalent dictionaries could produce different
    #     strings depending on insertion order.
    #
    # `separators=(",", ":")` removes unnecessary spaces.
    #   - That keeps the string compact and avoids whitespace-driven hash changes.
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def hash_payload(payload: Any) -> str:
    """
    Create a stable SHA-256 hash for a JSON-like payload.

    Parameters
    ----------
    payload : Any
        JSON-like payload to hash.

    Returns
    -------
    str
        Hex-encoded SHA-256 hash of the canonical payload string.

    Notes
    -----
    - This does not store the payload.
    - This does not hide secrets if the original payload is logged elsewhere.
    - The hash is useful for comparing whether two requests had the same content.
    - Equivalent JSON objects should produce the same hash even if dictionary key
      order differs.

    In plain language:

    - canonicalise the payload
    - hash the canonical string
    - use the hash as a request fingerprint
    """

    canonical_payload = canonicalise_json_payload(payload)

    # SHA-256 expects bytes, so encode the canonical JSON string as UTF-8.
    return sha256(canonical_payload.encode("utf-8")).hexdigest()


def build_idempotency_metadata(
    key: str,
    payload: Any,
) -> IdempotencyMetadata:
    """
    Build normalised idempotency metadata for a write request.

    Parameters
    ----------
    key : str
        Idempotency key for the request.

    payload : Any
        JSON-like request payload.

    Returns
    -------
    IdempotencyMetadata
        Normalised idempotency key and stable payload hash.

    Notes
    -----
    - The key is normalised before use.
    - The payload is converted into a stable hash.
    - This helper does not check whether the key already exists.
    - Future service code can store this metadata in Supabase.

    In plain language:

    - clean the retry key
    - fingerprint the request body
    - package both values together
    """

    normalised_key = normalise_idempotency_key(key)

    if normalised_key is None:
        raise ValueError("idempotency key must contain useful text.")

    return IdempotencyMetadata(
        key=normalised_key,
        payload_hash=hash_payload(payload),
    )


def detect_idempotency_conflict(
    key: str,
    existing_payload_hash: str,
    incoming_payload_hash: str,
) -> IdempotencyConflict | None:
    """
    Detect whether an idempotency key was reused with different content.

    Parameters
    ----------
    key : str
        Idempotency key being checked.

    existing_payload_hash : str
        Payload hash already stored for this key.

    incoming_payload_hash : str
        Payload hash calculated for the current request.

    Returns
    -------
    IdempotencyConflict | None
        Conflict details when the hashes differ.

        `None` when the hashes match.

    Notes
    -----
    - Same key plus same hash means the request is probably a safe retry.
    - Same key plus different hash means the key has been reused incorrectly.
    - Future endpoint code should reject conflicts rather than processing them.

    In plain language:

    - same key and same body is okay
    - same key and different body is not okay
    """

    if existing_payload_hash == incoming_payload_hash:
        return None

    return IdempotencyConflict(
        key=key,
        existing_payload_hash=existing_payload_hash,
        incoming_payload_hash=incoming_payload_hash,
    )


def get_request_idempotency_key(
    request: Request,
) -> str | IdempotencyFailureReason:
    """
    Read and require the `Idempotency-Key` header from a FastAPI request.

    Parameters
    ----------
    request : Request
        FastAPI request object.

    Returns
    -------
    str | IdempotencyFailureReason
        Normalised idempotency key when present.

        Failure reason when missing or blank.

    Notes
    -----
    - This helper reads the header from the request.
    - It delegates normalisation and required-key checking to
      `require_idempotency_key`.
    - Keeping request-reading separate from key validation makes the core logic
      easier to test.

    Example
    -------
    A protected write endpoint might eventually do:

        key_or_reason = get_request_idempotency_key(request)

        if isinstance(key_or_reason, IdempotencyFailureReason):
            ...

    In plain language:

    - read `Idempotency-Key` from the request
    - return the key or explain why it cannot be used
    """

    # Read the raw `Idempotency-Key` header from FastAPI.
    #   - Header lookup is case-insensitive.
    #   - Missing headers return `None`.
    raw_key = request.headers.get(IDEMPOTENCY_KEY_HEADER)

    return require_idempotency_key(raw_key)


__all__ = [
    "IdempotencyConflict",
    "IdempotencyFailureReason",
    "IdempotencyMetadata",
    "build_idempotency_metadata",
    "canonicalise_json_payload",
    "detect_idempotency_conflict",
    "get_request_idempotency_key",
    "hash_payload",
    "normalise_idempotency_key",
    "require_idempotency_key",
]
