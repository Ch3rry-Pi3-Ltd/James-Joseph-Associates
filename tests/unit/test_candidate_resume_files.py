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
