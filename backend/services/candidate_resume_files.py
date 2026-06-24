"""
Current-resume file access helpers for matched/searchable candidates.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from backend.db.candidates import get_candidate_current_resume_document
from backend.db.dropbox_oauth import get_dropbox_oauth_connection
from backend.db.dropbox_oauth_read import get_latest_dropbox_oauth_connection
from backend.db.jobadder_oauth import get_jobadder_oauth_connection
from backend.db.outlook_oauth import get_outlook_oauth_connection
from backend.services.dropbox_api import download_dropbox_file
from backend.services.dropbox_oauth import (
    is_dropbox_access_token_expired,
    refresh_dropbox_access_token,
)
from backend.services.jobadder_api import download_jobadder_candidate_attachment
from backend.services.jobadder_oauth import (
    is_jobadder_access_token_expired,
    refresh_jobadder_access_token,
)
from backend.services.outlook_api import download_outlook_message_file_attachment
from backend.services.outlook_oauth import (
    is_outlook_access_token_expired,
    refresh_outlook_access_token,
)
from backend.services.recruiterflow_files import download_recruiterflow_file_reference

_JOBADDER_URI_PATTERN = re.compile(
    r"^jobadder://accounts/(?P<account>\d+)/candidates/(?P<candidate>\d+)/attachments/(?P<attachment>\d+)$"
)
_OUTLOOK_URI_PATTERN = re.compile(
    r"^outlook://users/(?P<user>[^/]+)/mailboxes/(?P<mailbox>[^/]+)/messages/(?P<message>[^/]+)/attachments/(?P<attachment>[^/]+)$"
)
_RECRUITERFLOW_EXPORT_URI_PATTERN = re.compile(
    r"^recruiterflow://"
)


class CandidateResumeFileAccessError(RuntimeError):
    """
    Raised when the backend cannot fetch the current resume file for a candidate.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []


def fetch_candidate_current_resume_file(
    candidate_id: str,
) -> dict[str, Any]:
    """
    Return the transient current-resume file bytes and metadata for one candidate.
    """

    current_resume = get_candidate_current_resume_document(candidate_id)
    if current_resume is None:
        raise CandidateResumeFileAccessError(
            "Current resume was not found for this candidate.",
            code="not_found",
            status_code=404,
            details=[{"candidate_id": candidate_id}],
        )

    source_uri = current_resume.get("document_source_uri")
    if not isinstance(source_uri, str) or source_uri.strip() == "":
        source_uri = _derive_missing_source_uri(current_resume)
    if not isinstance(source_uri, str) or source_uri.strip() == "":
        raise CandidateResumeFileAccessError(
            "Current resume does not have a downloadable source reference.",
            code="resume_source_unavailable",
            status_code=501,
            details=[
                {"candidate_id": candidate_id},
                {"document_id": str(current_resume["document_id"])},
            ],
        )

    try:
        downloaded_file = _download_current_resume_source(source_uri.strip())
    except CandidateResumeFileAccessError:
        raise
    except Exception as exc:
        raise CandidateResumeFileAccessError(
            "Current resume download failed.",
            code="resume_download_failed",
            status_code=502,
            details=[
                {"candidate_id": candidate_id},
                {"document_id": str(current_resume["document_id"])},
                {"source_uri": source_uri.strip()},
                {"error_type": exc.__class__.__name__},
                {"message": str(exc)},
            ],
        ) from exc

    return {
        "candidate_id": str(current_resume["candidate_id"]),
        "document_id": str(current_resume["document_id"]),
        "document_title": current_resume.get("document_title"),
        "document_source_uri": source_uri.strip(),
        "document_mime_type": current_resume.get("document_mime_type"),
        "file_name": downloaded_file.get("file_name")
        or current_resume.get("document_title")
        or f"{current_resume['document_id']}",
        "content_type": downloaded_file.get("content_type")
        or current_resume.get("document_mime_type")
        or "application/octet-stream",
        "content_bytes": downloaded_file["content_bytes"],
    }


def _derive_missing_source_uri(current_resume: dict[str, Any]) -> str | None:
    """
    Reconstruct a missing document source URI from linked provenance where possible.
    """

    source_system = current_resume.get("provenance_source_system")
    source_record_id = current_resume.get("provenance_source_record_id")
    source_payload = current_resume.get("provenance_source_payload")
    if not isinstance(source_payload, dict):
        source_payload = {}

    if source_system == "dropbox":
        attachment_path = _clean_optional_string(
            _nested_value(source_payload, "latest_resume", "attachment_id")
        ) or _clean_optional_string(source_record_id)
        if attachment_path is None:
            return None
        return _build_dropbox_resume_source_uri(attachment_path)

    if source_system == "outlook":
        microsoft_user_id = _clean_optional_string(
            source_payload.get("microsoft_user_id")
        )
        mailbox = _clean_optional_string(source_payload.get("mailbox")) or "me"
        message_id = _clean_optional_string(source_payload.get("message_id"))
        attachment_id = _clean_optional_string(source_payload.get("attachment_id"))
        if (
            microsoft_user_id is None
            or message_id is None
            or attachment_id is None
        ):
            return None
        return (
            f"outlook://users/{microsoft_user_id}/mailboxes/{mailbox}/messages/"
            f"{message_id}/attachments/{attachment_id}"
        )

    if source_system == "recruiterflow":
        for candidate_key in ("source_uri", "url", "link"):
            direct_source_uri = _clean_optional_string(
                _nested_value(source_payload, "latest_resume", candidate_key)
            ) or _clean_optional_string(source_payload.get(candidate_key))
            if direct_source_uri is not None:
                return direct_source_uri

    return None


def _download_current_resume_source(source_uri: str) -> dict[str, Any]:
    if source_uri.startswith("dropbox://"):
        return _download_dropbox_resume_source(source_uri)

    if source_uri.startswith("jobadder://"):
        return _download_jobadder_resume_source(source_uri)

    if source_uri.startswith("outlook://"):
        return _download_outlook_resume_source(source_uri)

    if source_uri.startswith("http://") or source_uri.startswith("https://"):
        return download_recruiterflow_file_reference(source_uri=source_uri)

    if _RECRUITERFLOW_EXPORT_URI_PATTERN.match(source_uri):
        raise CandidateResumeFileAccessError(
            "Recruiterflow export-backed resumes are not downloadable from the candidate UI yet.",
            code="resume_source_not_supported",
            status_code=501,
            details=[{"source_uri": source_uri}],
        )

    raise CandidateResumeFileAccessError(
        "Current resume source is not supported by the download route yet.",
        code="resume_source_not_supported",
        status_code=501,
        details=[{"source_uri": source_uri}],
    )


def _download_dropbox_resume_source(source_uri: str) -> dict[str, Any]:
    dropbox_path = _extract_dropbox_source_path(source_uri)
    if dropbox_path.strip() == "":
        raise CandidateResumeFileAccessError(
            "Dropbox resume source URI is malformed.",
            code="resume_source_invalid",
            status_code=502,
            details=[{"source_uri": source_uri}],
        )

    stored_connection = get_latest_dropbox_oauth_connection()
    if stored_connection is None:
        raise CandidateResumeFileAccessError(
            "No stored Dropbox OAuth connection is available for resume download.",
            code="integration_connection_missing",
            status_code=502,
            details=[{"source_uri": source_uri}],
        )

    access_token = stored_connection.get("access_token")
    refresh_token = stored_connection.get("refresh_token")
    obtained_at = stored_connection.get("obtained_at")
    expires_in_seconds = stored_connection.get("expires_in_seconds")

    if not isinstance(access_token, str) or access_token.strip() == "":
        raise CandidateResumeFileAccessError(
            "Stored Dropbox connection is missing a usable access token.",
            code="integration_connection_invalid",
            status_code=502,
            details=[{"source_uri": source_uri}],
        )

    resolved_access_token = access_token.strip()
    if is_dropbox_access_token_expired(
        obtained_at=obtained_at,
        expires_in_seconds=(
            int(expires_in_seconds) if expires_in_seconds is not None else None
        ),
    ):
        if not isinstance(refresh_token, str) or refresh_token.strip() == "":
            raise CandidateResumeFileAccessError(
                "Stored Dropbox connection cannot be refreshed.",
                code="integration_connection_invalid",
                status_code=502,
                details=[{"source_uri": source_uri}],
            )
        refreshed = refresh_dropbox_access_token(refresh_token=refresh_token.strip())
        resolved_access_token = refreshed.access_token

    return download_dropbox_file(
        access_token=resolved_access_token,
        path=dropbox_path,
    )


def _download_jobadder_resume_source(source_uri: str) -> dict[str, Any]:
    match = _JOBADDER_URI_PATTERN.match(source_uri)
    if match is None:
        raise CandidateResumeFileAccessError(
            "JobAdder resume source URI is malformed.",
            code="resume_source_invalid",
            status_code=502,
            details=[{"source_uri": source_uri}],
        )

    jobadder_account = int(match.group("account"))
    candidate_id = int(match.group("candidate"))
    attachment_id = int(match.group("attachment"))

    stored_connection = get_jobadder_oauth_connection(jobadder_account)
    if stored_connection is None:
        raise CandidateResumeFileAccessError(
            "Stored JobAdder OAuth connection was not found for this resume source.",
            code="integration_connection_missing",
            status_code=502,
            details=[{"jobadder_account": jobadder_account}],
        )

    access_token = stored_connection.get("access_token")
    refresh_token = stored_connection.get("refresh_token")
    api_url = stored_connection.get("api_url")
    obtained_at = stored_connection.get("obtained_at")
    expires_in_seconds = stored_connection.get("expires_in_seconds")

    if (
        not isinstance(access_token, str)
        or access_token.strip() == ""
        or not isinstance(api_url, str)
        or api_url.strip() == ""
    ):
        raise CandidateResumeFileAccessError(
            "Stored JobAdder connection is missing required fields.",
            code="integration_connection_invalid",
            status_code=502,
            details=[{"jobadder_account": jobadder_account}],
        )

    resolved_access_token = access_token.strip()
    if is_jobadder_access_token_expired(
        obtained_at=obtained_at,
        expires_in_seconds=(
            int(expires_in_seconds) if expires_in_seconds is not None else None
        ),
    ):
        if not isinstance(refresh_token, str) or refresh_token.strip() == "":
            raise CandidateResumeFileAccessError(
                "Stored JobAdder connection cannot be refreshed.",
                code="integration_connection_invalid",
                status_code=502,
                details=[{"jobadder_account": jobadder_account}],
            )
        refreshed = refresh_jobadder_access_token(
            refresh_token=refresh_token.strip()
        )
        resolved_access_token = refreshed.access_token

    return download_jobadder_candidate_attachment(
        api_url=api_url.strip(),
        access_token=resolved_access_token,
        candidate_id=candidate_id,
        attachment_id=attachment_id,
    )


def _download_outlook_resume_source(source_uri: str) -> dict[str, Any]:
    match = _OUTLOOK_URI_PATTERN.match(source_uri)
    if match is None:
        raise CandidateResumeFileAccessError(
            "Outlook resume source URI is malformed.",
            code="resume_source_invalid",
            status_code=502,
            details=[{"source_uri": source_uri}],
        )

    microsoft_user_id = match.group("user")
    mailbox = match.group("mailbox")
    message_id = match.group("message")
    attachment_id = match.group("attachment")

    stored_connection = get_outlook_oauth_connection(microsoft_user_id)
    if stored_connection is None:
        raise CandidateResumeFileAccessError(
            "Stored Outlook OAuth connection was not found for this resume source.",
            code="integration_connection_missing",
            status_code=502,
            details=[{"microsoft_user_id": microsoft_user_id}],
        )

    access_token = stored_connection.get("access_token")
    refresh_token = stored_connection.get("refresh_token")
    obtained_at = stored_connection.get("obtained_at")
    expires_in_seconds = stored_connection.get("expires_in_seconds")

    if not isinstance(access_token, str) or access_token.strip() == "":
        raise CandidateResumeFileAccessError(
            "Stored Outlook connection is missing a usable access token.",
            code="integration_connection_invalid",
            status_code=502,
            details=[{"microsoft_user_id": microsoft_user_id}],
        )

    resolved_access_token = access_token.strip()
    if is_outlook_access_token_expired(
        obtained_at=obtained_at,
        expires_in_seconds=(
            int(expires_in_seconds) if expires_in_seconds is not None else None
        ),
    ):
        if not isinstance(refresh_token, str) or refresh_token.strip() == "":
            raise CandidateResumeFileAccessError(
                "Stored Outlook connection cannot be refreshed.",
                code="integration_connection_invalid",
                status_code=502,
                details=[{"microsoft_user_id": microsoft_user_id}],
            )
        refreshed = refresh_outlook_access_token(
            refresh_token=refresh_token.strip()
        )
        resolved_access_token = refreshed.access_token

    resolved_mailbox = None if mailbox == "me" else mailbox
    return download_outlook_message_file_attachment(
        access_token=resolved_access_token,
        message_id=message_id,
        attachment_id=attachment_id,
        mailbox=resolved_mailbox,
    )


def _nested_value(payload: dict[str, Any], *keys: str) -> Any:
    current_value: Any = payload
    for key in keys:
        if not isinstance(current_value, dict):
            return None
        current_value = current_value.get(key)
    return current_value


def _clean_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned_value = value.strip()
    return cleaned_value or None


def _build_dropbox_resume_source_uri(dropbox_path: str) -> str:
    encoded_path = (
        dropbox_path
        .replace("%", "%25")
        .replace("#", "%23")
        .replace("&", "%26")
        .replace(" ", "%20")
    )
    return (
        f"dropbox://{encoded_path}"
        f"#candidate={encoded_path}&attachment={encoded_path}"
    )


def _extract_dropbox_source_path(source_uri: str) -> str:
    if not source_uri.startswith("dropbox://"):
        parsed = urlparse(source_uri)
        decoded_path = unquote(parsed.path or "")
        return decoded_path

    raw_body = source_uri[len("dropbox://") :]
    if "#candidate=" in raw_body:
        raw_path = raw_body.split("#candidate=", 1)[0]
    elif "#attachment=" in raw_body:
        raw_path = raw_body.split("#attachment=", 1)[0]
    else:
        raw_path = raw_body.split("#", 1)[0]
    if raw_path == "":
        parsed = urlparse(source_uri)
        return unquote(parsed.path or "")
    return unquote(raw_path)


__all__ = [
    "CandidateResumeFileAccessError",
    "fetch_candidate_current_resume_file",
]
