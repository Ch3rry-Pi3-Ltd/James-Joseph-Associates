from backend.services import candidate_resume_files
from backend.services.candidate_resume_files import (
    CandidateResumeFileAccessError,
    fetch_candidate_current_resume_file,
)


def test_fetch_candidate_current_resume_file_returns_dropbox_download(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        candidate_resume_files,
        "get_candidate_current_resume_document",
        lambda candidate_id: {
            "candidate_id": candidate_id,
            "document_id": "doc-1",
            "document_title": "Sarah-Jones-CV.pdf",
            "document_source_uri": "dropbox:///cv/Sarah-Jones-CV.pdf#candidate=1&attachment=2",
            "document_mime_type": "application/pdf",
        },
    )
    monkeypatch.setattr(
        candidate_resume_files,
        "get_latest_dropbox_oauth_connection",
        lambda: {
            "access_token": "dropbox-token",
            "refresh_token": "dropbox-refresh",
            "obtained_at": "2026-06-23T18:00:00+00:00",
            "expires_in_seconds": 14400,
        },
    )
    monkeypatch.setattr(
        candidate_resume_files,
        "is_dropbox_access_token_expired",
        lambda **kwargs: False,
    )

    captured: dict[str, object] = {}

    def fake_download_dropbox_file(*, access_token: str, path: str) -> dict[str, object]:
        captured["access_token"] = access_token
        captured["path"] = path
        return {
            "file_name": "Sarah-Jones-CV.pdf",
            "content_type": "application/pdf",
            "content_bytes": b"%PDF%",
        }

    monkeypatch.setattr(
        candidate_resume_files,
        "download_dropbox_file",
        fake_download_dropbox_file,
    )

    result = fetch_candidate_current_resume_file(
        "33333333-3333-3333-3333-333333333331",
    )

    assert result["file_name"] == "Sarah-Jones-CV.pdf"
    assert result["content_bytes"] == b"%PDF%"
    assert captured == {
        "access_token": "dropbox-token",
        "path": "/cv/Sarah-Jones-CV.pdf",
    }


def test_fetch_candidate_current_resume_file_rejects_unsupported_recruiterflow_export(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        candidate_resume_files,
        "get_candidate_current_resume_document",
        lambda candidate_id: {
            "candidate_id": candidate_id,
            "document_id": "doc-1",
            "document_title": "Candidate CV.pdf",
            "document_source_uri": "recruiterflow:///exports/Recruiterflow.zip/candidates/4847/files/5679",
            "document_mime_type": "application/pdf",
        },
    )

    try:
        fetch_candidate_current_resume_file(
            "33333333-3333-3333-3333-333333333331",
        )
    except CandidateResumeFileAccessError as exc:
        assert exc.code == "resume_source_not_supported"
        assert exc.status_code == 501
    else:
        raise AssertionError("Expected unsupported recruiterflow export error.")


def test_fetch_candidate_current_resume_file_raises_not_found_when_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        candidate_resume_files,
        "get_candidate_current_resume_document",
        lambda candidate_id: None,
    )

    try:
        fetch_candidate_current_resume_file(
            "33333333-3333-3333-3333-333333333331",
        )
    except CandidateResumeFileAccessError as exc:
        assert exc.code == "not_found"
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected missing current resume error.")


def test_fetch_candidate_current_resume_file_wraps_provider_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        candidate_resume_files,
        "get_candidate_current_resume_document",
        lambda candidate_id: {
            "candidate_id": candidate_id,
            "document_id": "doc-1",
            "document_title": "Sarah-Jones-CV.pdf",
            "document_source_uri": "dropbox:///cv/Sarah-Jones-CV.pdf",
            "document_mime_type": "application/pdf",
        },
    )
    monkeypatch.setattr(
        candidate_resume_files,
        "_download_current_resume_source",
        lambda source_uri: (_ for _ in ()).throw(RuntimeError("token expired")),
    )

    try:
        fetch_candidate_current_resume_file(
            "33333333-3333-3333-3333-333333333331",
        )
    except CandidateResumeFileAccessError as exc:
        assert exc.code == "resume_download_failed"
        assert exc.status_code == 502
        assert {"error_type": "RuntimeError"} in exc.details
    else:
        raise AssertionError("Expected wrapped provider failure.")


def test_fetch_candidate_current_resume_file_derives_dropbox_source_uri_from_provenance(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        candidate_resume_files,
        "get_candidate_current_resume_document",
        lambda candidate_id: {
            "candidate_id": candidate_id,
            "document_id": "doc-1",
            "document_title": "Sarah-Jones-CV.pdf",
            "document_source_uri": None,
            "document_mime_type": "application/pdf",
            "provenance_source_system": "dropbox",
            "provenance_source_record_type": "dropbox_resume_attachment",
            "provenance_source_record_id": "/cv/Sarah-Jones-CV.pdf",
            "provenance_source_payload": {
                "latest_resume": {
                    "attachment_id": "/cv/Sarah-Jones-CV.pdf",
                }
            },
        },
    )
    monkeypatch.setattr(
        candidate_resume_files,
        "get_latest_dropbox_oauth_connection",
        lambda: {
            "access_token": "dropbox-token",
            "refresh_token": "dropbox-refresh",
            "obtained_at": "2026-06-23T18:00:00+00:00",
            "expires_in_seconds": 14400,
        },
    )
    monkeypatch.setattr(
        candidate_resume_files,
        "is_dropbox_access_token_expired",
        lambda **kwargs: False,
    )

    captured: dict[str, object] = {}

    def fake_download_dropbox_file(*, access_token: str, path: str) -> dict[str, object]:
        captured["access_token"] = access_token
        captured["path"] = path
        return {
            "file_name": "Sarah-Jones-CV.pdf",
            "content_type": "application/pdf",
            "content_bytes": b"%PDF%",
        }

    monkeypatch.setattr(
        candidate_resume_files,
        "download_dropbox_file",
        fake_download_dropbox_file,
    )

    result = fetch_candidate_current_resume_file(
        "33333333-3333-3333-3333-333333333331",
    )

    assert (
        result["document_source_uri"]
        == "dropbox:///cv/Sarah-Jones-CV.pdf#candidate=/cv/Sarah-Jones-CV.pdf&attachment=/cv/Sarah-Jones-CV.pdf"
    )
    assert captured == {
        "access_token": "dropbox-token",
        "path": "/cv/Sarah-Jones-CV.pdf",
    }


def test_fetch_candidate_current_resume_file_supports_legacy_raw_dropbox_uri_with_hashes(
    monkeypatch,
) -> None:
    raw_path = "/### BIG BAD CV ARCHIVE inc. RFL/##############ACHTUNG! in RFL!/khari.pdf"

    monkeypatch.setattr(
        candidate_resume_files,
        "get_candidate_current_resume_document",
        lambda candidate_id: {
            "candidate_id": candidate_id,
            "document_id": "doc-1",
            "document_title": "khari.pdf",
            "document_source_uri": (
                f"dropbox://{raw_path}#candidate={raw_path}&attachment={raw_path}"
            ),
            "document_mime_type": "application/pdf",
        },
    )
    monkeypatch.setattr(
        candidate_resume_files,
        "get_latest_dropbox_oauth_connection",
        lambda: {
            "access_token": "dropbox-token",
            "refresh_token": "dropbox-refresh",
            "obtained_at": "2026-06-23T18:00:00+00:00",
            "expires_in_seconds": 14400,
        },
    )
    monkeypatch.setattr(
        candidate_resume_files,
        "is_dropbox_access_token_expired",
        lambda **kwargs: False,
    )

    captured: dict[str, object] = {}

    def fake_download_dropbox_file(*, access_token: str, path: str) -> dict[str, object]:
        captured["access_token"] = access_token
        captured["path"] = path
        return {
            "file_name": "khari.pdf",
            "content_type": "application/pdf",
            "content_bytes": b"%PDF%",
        }

    monkeypatch.setattr(
        candidate_resume_files,
        "download_dropbox_file",
        fake_download_dropbox_file,
    )

    result = fetch_candidate_current_resume_file(
        "33333333-3333-3333-3333-333333333331",
    )

    assert result["file_name"] == "khari.pdf"
    assert captured == {
        "access_token": "dropbox-token",
        "path": raw_path,
    }
