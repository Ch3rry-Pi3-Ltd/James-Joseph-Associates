"""
Shared HTTP helpers for the James Joseph Associates intelligence API.

This module contains small utilities for reading common HTTP request metadata.

It gives the rest of the repository a stable way to talk about:

- request headers
- idempotency keys
- source-system names
- Make.com run IDs
- request IDs for future logging and tracing

Keeping these helpers in one place makes the project easier to extend because:

- endpoint modules do not need to repeat header parsing logic
- Make.com integration can use the same header names everywhere
- future audit logging can read request metadata consistently
- tests can verify HTTP metadata handling without needing real business routes

In plain language:

- this module answers the question:

    "How do we read useful metadata from an HTTP request?"

- it does not define API routes
- it does not connect to Supabase
- it does not validate request bodies
- it does not decide whether a request is authorised
- it does not execute Make.com workflows

Notes
-----
- These helpers are intentionally small.
- They should stay framework-adjacent, not business-domain-specific.
- Header values are normalised by trimming whitespace.
- Empty header values are treated as missing.
- Missing optional headers return `None`.
- Required-header behaviour can be added later once authentication and
  idempotency rules are finalised.

Common request flow
-------------------
A future ingestion request might arrive like this:

    POST /api/v1/source-records
    Authorization: Bearer <token>
    Idempotency-Key: jobadder-candidate-123
    X-Source-System: jobadder
    X-Make-Run-Id: make-run-456
    X-Request-Id: request-789

Endpoint code can then call:

    metadata = get_request_metadata(request)

and receive:

    {
        "idempotency_key": "jobadder-candidate-123",
        "source_system": "jobadder",
        "make_run_id": "make-run-456",
        "request_id": "request-789"
    }

That metadata can later be stored with source records, audit logs, import runs,
or proposed workflow actions.
"""

from fastapi import Request

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
SOURCE_SYSTEM_HEADER = "X-Source-System"
MAKE_RUN_ID_HEADER = "X-Make-Run-Id"
REQUEST_ID_HEADER = "X-Request-Id"

def normalise_header_value(value: str | None) -> str | None:
    """
    Convert a raw HTTP header value into a clean optional string.

    Parameters
    ----------
    value : str | None
        Raw header value read from the incoming request.

        FastAPI returns `None` when the header is missing.

    Returns
    -------
    str | None
        Cleaned header value.

        The return value is:

        - a stripped string when the header contains useful text
        - `None` when the header is missing
        - `None` when the header contains only whitespace

    Notes
    -----
    - HTTP clients can accidentally send blank headers.
    - A blank idempotency key or source-system header should not be treated as a
      real value.
    - This helper keeps that rule consistent across all request metadata helpers.

    Example
    -------
    These values become useful strings:

        " jobadder " -> "jobadder"
        "abc-123"    -> "abc-123"

    These values become `None`:

        None
        ""
        "   "

    In plain language:

    - remove whitespace from the edges
    - treat empty values as missing
    """

    # Missing headers should remain missing
    #   - FastAPI returns `None` when a header is not present.
    #   - Keeping that as `None` lets callers distinguish missing metadata from
    #     real text values.
    if value is None:
        return None
    
    # Trim accidental whitespace from the header value
    #   - This makes values like `" jobadder "` behave as `"jobadder"`.
    normalised_value = value.strip()

    # Empty strings should not count as useful metadata
    #   - A header containing only spaces should be treated the same as a missing
    #     header.
    if normalised_value == "":
        return None
    
    return normalised_value

def get_optional_header(request: Request, header_name: str) -> str | None:
    """
    Read and normalise one optional request header.

    Parameters
    ----------
    request : Request
        FastAPI request object

    header_name : str
        Name of the HTTP header to read.

        Header lookup is case-insensitive because FastAPI's header container
        follows normal HTTP header behaviour.

    Returns
    -------
    str | None
        Normalised header value, or `None` if the header is missing or blank.

    Notes
    -----
    - This helper does not raise an error when the header is missing.
    - It is suitable for metadata that is useful but not always required.
    - Required-header validation can be layered on later once endpoint rules are
      finalised.

    Example
    -------
    If a request contains:

        X-Source-System: jobadder

    then:

        get_optional_header(request, "X-Source-System")

    returns:

        "jobadder"

    In plain language:

    - look for a header
    - clean it
    - return it if it contains useful text
    """

    # Read the raw value from FastAPI's request headers
    #   - `request.headers.get(...)` returns `None` if the header is missing.
    #   - We then pass the value through one normalisation function so all header
    #     reads follow the same whitespace and blank-value rules.
    return normalise_header_value(request.headers.get(header_name))

def get_request_metadata(request: Request) -> dict[str, str]:
    """
    Extract common request metadata from HTTP headers.

    Parameters
    ----------
    request : Request
        FastAPI request object.

    Returns
    -------
    dict[str, str]
        Dictionary containing any recognised metadata headers that were present
        and non-empty.

        Possible keys are:

        - `idempotency_key`
        - `source_system`
        - `make_run_id`
        - `request_id`

    Notes
    -----
    - Missing headers are simply omitted from the returned dictionary.
    - Blank headers are treated as missing.
    - This helper does not validate whether a value is authorised or meaningful.
    - Endpoint-specific validation should happen in endpoint or service code.
    - The returned dictionary is safe to pass into future logging, audit, or
      persistence layers, assuming values are not treated as trusted identity.

    Header mapping
    --------------
    The mapping is:

        Idempotency-Key -> idempotency_key
        X-Source-System -> source_system
        X-Make-Run-Id   -> make_run_id
        X-Request-Id    -> request_id

    Example
    -------
    If a request contains:

        Idempotency-Key: jobadder-candidate-123
        X-Source-System: jobadder
        X-Make-Run-Id: make-run-456

    then this helper returns:

        {
            "idempotency_key": "jobadder-candidate-123",
            "source_system": "jobadder",
            "make_run_id": "make-run-456"
        }

    In plain language:

    - collect the request headers we care about
    - ignore the ones that are missing
    - return a small metadata dictionary
    """

    metadata: dict[str, str] = {}

    # Each tuple connects the external HTTP header name to the internal metadata
    # key we want to use in Python.
    #   - Header names stay in HTTP style.
    #   - Dictionary keys stay in Python snake_case.
    header_mappings = [
        ("idempotency_key", IDEMPOTENCY_KEY_HEADER),
        ("source_system", SOURCE_SYSTEM_HEADER),
        ("make_run_id", MAKE_RUN_ID_HEADER),
        ("request_id", REQUEST_ID_HEADER),
    ]

    for metadata_key, header_name in header_mappings:
        # Read and clean the header value using the shared helper
        #   - Missing headers return `None`.
        #   - Blank headers return `None`.
        #   - Useful values return a stripped string.
        value = get_optional_header(request=request, header_name=header_name)

        # Only include metadata that was actually provided
        #   - This keeps the returned dictionary compact.
        #   - It also avoids storing keys with meaningless empty values.
        if value is not None:
            metadata[metadata_key] = value

    return metadata

__all__ = [
    "IDEMPOTENCY_KEY_HEADER",
    "MAKE_RUN_ID_HEADER",
    "REQUEST_ID_HEADER",
    "SOURCE_SYSTEM_HEADER",
    "get_optional_header",
    "get_request_metadata",
    "normalise_header_value",
]