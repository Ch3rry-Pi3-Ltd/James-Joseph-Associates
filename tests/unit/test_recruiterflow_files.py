"""
Unit tests for Recruiterflow file-download helpers.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.services.recruiterflow_files import (
    RecruiterflowFileDownloadError,
    download_recruiterflow_file_reference,
)


def test_download_recruiterflow_file_reference_returns_bytes_and_filename() -> None:
    """
    Verify that the helper returns transient bytes plus an inferred filename.
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"pdf-bytes"
    mock_response.headers = {"Content-Type": "application/pdf"}

    with patch(
        "backend.services.recruiterflow_files.httpx.get",
        return_value=mock_response,
    ) as mock_get:
        result = download_recruiterflow_file_reference(
            source_uri="https://example.com/documents/5679/Candidate%20CV.pdf?sig=abc"
        )

    assert result["file_name"] == "Candidate CV.pdf"
    assert result["content_type"] == "application/pdf"
    assert result["content_bytes"] == b"pdf-bytes"
    assert result["byte_count"] == 9
    mock_get.assert_called_once()


def test_download_recruiterflow_file_reference_raises_on_http_error() -> None:
    """
    Verify that provider HTTP failures become a normalized backend exception.
    """

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.content = b""
    mock_response.headers = {}

    with patch(
        "backend.services.recruiterflow_files.httpx.get",
        return_value=mock_response,
    ):
        with pytest.raises(RecruiterflowFileDownloadError) as exc_info:
            download_recruiterflow_file_reference(
                source_uri="https://example.com/documents/5679/Candidate%20CV.pdf?sig=abc"
            )

    assert exc_info.value.status_code == 403
