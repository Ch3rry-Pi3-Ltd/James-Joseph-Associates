"""
Unit tests for the Dropbox zip-member resume ingestion runner.
"""

from io import BytesIO
from zipfile import ZipFile

import scripts.persist_dropbox_zip_resume_archives as dropbox_zip_resume_archives


def test_run_dropbox_zip_archive_resume_persistence_persists_archive_members(
    monkeypatch,
) -> None:
    archive_path = "/archive/TW50/CVs-2019-Mar-07-092045.zip"
    member_name = "Joyce Adjei (18860328 - Jobsite).docx"

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, "w") as archive:
        archive.writestr(member_name, b"fake-docx-bytes")

    monkeypatch.setattr(
        dropbox_zip_resume_archives,
        "download_dropbox_file",
        lambda **kwargs: {
            "file_name": "CVs-2019-Mar-07-092045.zip",
            "content_type": "application/zip",
            "content_bytes": zip_buffer.getvalue(),
            "file_metadata": {"server_modified": "2026-07-13T16:00:00Z"},
        },
    )
    monkeypatch.setattr(
        dropbox_zip_resume_archives,
        "_find_existing_dropbox_resume_skip_record",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        dropbox_zip_resume_archives,
        "extract_text_from_resume_bytes",
        lambda **kwargs: {
            "text": "Joyce Adjei CV text",
            "file_name": member_name,
        },
    )
    monkeypatch.setattr(
        dropbox_zip_resume_archives,
        "build_resume_extraction_input_from_resume_bundle",
        lambda **kwargs: {
            "source_system": "dropbox",
            "source_candidate_id": f"{archive_path}::{member_name}",
            "candidate_context": {"full_name": "Joyce Adjei"},
            "latest_resume": {
                "attachment_id": f"{archive_path}::{member_name}",
                "file_name": member_name,
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "created_at": "2026-07-13T16:00:00Z",
            },
            "cleaned_resume_text": "Joyce Adjei CV text",
        },
    )
    monkeypatch.setattr(
        dropbox_zip_resume_archives,
        "find_existing_resume_duplicate_match",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        dropbox_zip_resume_archives,
        "extract_dropbox_candidate_resume_profile_with_quality_gate",
        lambda **kwargs: {
            "model_profile": {"model_name": "gpt-4.1-mini"},
            "quality_assessment": {"status": "pass", "quality_score": 98},
            "quality_gate": {
                "first_pass_model_name": "gpt-4.1-mini",
                "fallback_model_name": "gpt-4.1-mini",
                "fallback_invoked": False,
                "final_model_name": "gpt-4.1-mini",
            },
        },
    )
    monkeypatch.setattr(
        dropbox_zip_resume_archives,
        "persist_scored_resume_extraction_result",
        lambda result: {
            "candidate_id": "candidate-uuid",
            "person_id": "person-uuid",
            "document_id": "document-uuid",
            "document_title": member_name,
            "quality_status": "pass",
            "quality_score": 98,
        },
    )

    summary = dropbox_zip_resume_archives.run_dropbox_zip_archive_resume_persistence(
        access_token="token",
        archive_path=archive_path,
        member_limit=20,
        member_offset=0,
        force_reprocess=False,
        process_entire_archive=True,
    )

    assert summary["archive_path"] == archive_path
    assert summary["total_eligible_resume_member_count"] == 1
    assert summary["selected_resume_file_count"] == 1
    assert summary["persisted_resume_count"] == 1
    assert summary["accepted_resume_count"] == 1
    assert summary["skipped_count"] == 0
    assert summary["unsupported_count"] == 0
    assert summary["failed_count"] == 0
    assert summary["persisted_resume_preview"][0]["dropbox_path"] == (
        f"{archive_path}::{member_name}"
    )


def test_list_zip_archives_returns_recursive_zip_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        dropbox_zip_resume_archives,
        "fetch_dropbox_list_folder",
        lambda **kwargs: {
            "entries": [
                {
                    ".tag": "file",
                    "name": "CVs-2019-Mar-07-092045.zip",
                    "path_display": "/archive/TW50/CVs-2019-Mar-07-092045.zip",
                },
                {
                    ".tag": "file",
                    "name": "notes.txt",
                    "path_display": "/archive/TW50/notes.txt",
                },
            ],
            "cursor": None,
            "has_more": False,
        },
    )

    archive_paths = dropbox_zip_resume_archives.list_zip_archives(
        access_token="token",
        base_folder_path="/archive",
        dropbox_list_limit=200,
    )

    assert archive_paths == ["/archive/TW50/CVs-2019-Mar-07-092045.zip"]
