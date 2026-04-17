"""
Standard idempotency helpers for the James Joseph Associates intelligence API.

This module contains small utilities for handling idempotency metadata.

It gives the rest of the repository a stable way to talk about:

- `Idempoetncy-Key` headers
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

class IndempotencyFailureReason(StrEnum):
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

    - this enum gives tests and future handlders a precise reason for
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
            whether a retry is tryly the same request.

        Notes
        -----
        - This object does not prove the request is new.
        - It only represents the metadata needed for a future lookup.
        - The actual "have we seen this before?" check will need a database table or
          another persistence layer.

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
    reason: IndempotencyFailureReason = (
        IndempotencyFailureReason.IDEMPOTENCY_CONFLICT
    )

    