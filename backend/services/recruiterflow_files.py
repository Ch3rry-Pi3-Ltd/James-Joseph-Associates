"""
Recruiterflow file-download helpers.

This module contains the first narrow transport helper for Recruiterflow file
references exposed through signed URLs inside the official backup export.

It gives the rest of the repository a stable way to talk about:

- downloading one Recruiterflow file reference transiently into memory
- normalizing transport failures into one small backend exception type
- preserving enough metadata for later extraction and provenance writes

Important scope boundary
------------------------
This module does not parse CV text and does not write to the database.

Its job is narrower:

- fetch the bytes behind one signed Recruiterflow file URL
- infer a sensible file name when the provider response is minimal
- hand the bytes to the extraction and persistence layers
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

import httpx


class RecruiterflowFileDownloadError(RuntimeError):
    """
    Raised when a Recruiterflow file reference cannot be downloaded safely.

    Attributes
    ----------
    message : str
        Safe human-readable explanation of what failed.

    status_code : int | None
        HTTP status code returned by the upstream file host, if available.

    source_uri : str | None
        Signed source URL associated with the failure.

    Example
    -------
    A caller may inspect:

        error.status_code
        error.source_uri

    to distinguish between an expired signed URL and a local network problem.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        source_uri: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.source_uri = source_uri

    def __str__(self) -> str:
        """
        Return the human-readable error message.
        """

        return self.message


def download_recruiterflow_file_reference(
    *,
    source_uri: str,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """
    Download one Recruiterflow file reference transiently into memory.

    Parameters
    ----------
    source_uri : str
        Signed file URL carried in the Recruiterflow export.

    timeout_seconds : float, default=60.0
        HTTP timeout used for the file download.

    Returns
    -------
    dict[str, Any]
        Normalized transient file download containing:

        - `source_uri`
        - `file_name`
        - `content_type`
        - `content_bytes`
        - `byte_count`
        - `status_code`

    Raises
    ------
    RecruiterflowFileDownloadError
        If the URL is empty, unreachable, or returns an error response.

    Example
    -------
    A caller can download a signed Recruiterflow file URL like:

        downloaded_file = download_recruiterflow_file_reference(
            source_uri="https://.../documents/5679/Candidate%20CV.pdf?...",
        )

    and then pass:

        downloaded_file["content_bytes"]

    into the local resume text extractor.
    """

    cleaned_source_uri = source_uri.strip() if isinstance(source_uri, str) else ""
    if cleaned_source_uri == "":
        raise RecruiterflowFileDownloadError(
            "Recruiterflow file URL cannot be empty.",
            source_uri=source_uri if isinstance(source_uri, str) else None,
        )

    try:
        response = httpx.get(
            cleaned_source_uri,
            follow_redirects=True,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise RecruiterflowFileDownloadError(
            "Could not reach the Recruiterflow file URL.",
            source_uri=cleaned_source_uri,
        ) from exc

    if response.status_code >= 400:
        raise RecruiterflowFileDownloadError(
            "Recruiterflow file download failed.",
            status_code=response.status_code,
            source_uri=cleaned_source_uri,
        )

    content_bytes = response.content
    file_name = _infer_file_name_from_url(cleaned_source_uri)

    return {
        "source_uri": cleaned_source_uri,
        "file_name": file_name,
        "content_type": response.headers.get("Content-Type"),
        "content_bytes": content_bytes,
        "byte_count": len(content_bytes),
        "status_code": response.status_code,
    }


def _infer_file_name_from_url(source_uri: str) -> str | None:
    """
    Infer a human-readable file name from one signed file URL.

    Example
    -------
    A URL path ending in:

        `/documents/5679/Candidate%20CV.pdf?...`

    returns:

        `"Candidate CV.pdf"`
    """

    parsed = urlparse(source_uri)
    path_name = PurePosixPath(parsed.path).name
    if path_name == "":
        return None
    return unquote(path_name)


__all__ = [
    "RecruiterflowFileDownloadError",
    "download_recruiterflow_file_reference",
]
