"""
Unit tests for the bounded Dropbox folder resume runner.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

import scripts.persist_dropbox_folder_resume_chunk as dropbox_folder_resume_chunk
from scripts.persist_dropbox_folder_resume_chunk import (
    _build_dropbox_extraction_source_record_key,
    _find_existing_dropbox_resume_skip_record,
)


def test_build_dropbox_extraction_source_record_key_returns_stable_path_pair() -> None:
    """
    Verify that the runner builds the canonical Dropbox path skip key.
    """

    assert (
        _build_dropbox_extraction_source_record_key(
            dropbox_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf"
        )
        == "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf:/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf"
    )


def test_find_existing_dropbox_resume_skip_record_returns_linked_resume_row() -> None:
    """
    Verify that the skip lookup returns existing scored Dropbox resume metadata.
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        "source_record_uuid": "source-uuid",
        "source_record_id": "path:path",
        "quality_status": "pass",
        "quality_score": 92,
        "document_id": "document-uuid",
        "document_title": "Jane-Doe-CV.pdf",
    }

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "scripts.persist_dropbox_folder_resume_chunk.postgres_connection"
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = mock_connection

        result = _find_existing_dropbox_resume_skip_record(
            dropbox_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf"
        )

    assert result == {
        "source_record_uuid": "source-uuid",
        "source_record_id": "path:path",
        "quality_status": "pass",
        "quality_score": 92,
        "document_id": "document-uuid",
        "document_title": "Jane-Doe-CV.pdf",
    }
    mock_cursor.execute.assert_called_once()


def test_main_processes_bounded_resume_like_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that the runner ingests one Dropbox CV and ignores shortcut files.
    """

    artifact_path = tmp_path / "dropbox_folder_summary.json"

    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            folder_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive",
            file_limit=1,
            dropbox_list_limit=10,
            resume_file_offset=0,
            force_reprocess=False,
        ),
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "build_artifact_path",
        lambda folder_path, *, resume_file_offset: artifact_path,
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "fetch_dropbox_list_folder",
        lambda **kwargs: {
            "entries": [
                {
                    ".tag": "file",
                    "name": "Jane-Doe-CV.pdf",
                    "path_display": "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf",
                },
                {
                    ".tag": "file",
                    "name": "Jane-Doe-CV - Shortcut.lnk",
                    "path_display": "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV - Shortcut.lnk",
                },
            ],
            "has_more": False,
        },
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "_find_existing_dropbox_resume_skip_record",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "download_dropbox_file",
        lambda **kwargs: {
            "file_name": "Jane-Doe-CV.pdf",
            "content_type": "application/pdf",
            "content_bytes": b"%PDF fake bytes",
            "file_metadata": {"server_modified": "2026-05-19T10:12:40Z"},
        },
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "extract_text_from_resume_bytes",
        lambda **kwargs: "Extracted CV text",
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "extract_dropbox_candidate_resume_profile_with_quality_gate",
        lambda **kwargs: {
            "model_profile": {"model_name": "gpt-4.1-mini"},
            "quality_assessment": {"status": "pass", "quality_score": 100},
            "quality_gate": {
                "first_pass_model_name": "gpt-4.1-mini",
                "fallback_model_name": "gpt-4.1-mini",
                "fallback_invoked": False,
                "final_model_name": "gpt-4.1-mini",
            },
        },
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "persist_scored_resume_extraction_result",
        lambda result: {
            "source_record_id": "path:path",
            "document_id": "document-uuid",
            "document_title": "Jane-Doe-CV.pdf",
        },
    )

    dropbox_folder_resume_chunk.main()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["folder_path"] == "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive"
    assert artifact["folder_entry_count"] == 2
    assert artifact["selected_resume_file_count"] == 1
    assert artifact["already_processed_count"] == 0
    assert artifact["new_resume_file_count"] == 1
    assert artifact["persisted_resume_count"] == 1
    assert artifact["accepted_resume_count"] == 1
    assert artifact["skipped_count"] == 0
    assert artifact["unsupported_count"] == 0
    assert artifact["failed_count"] == 0
    assert artifact["resume_file_offset"] == 0


def test_main_skips_already_persisted_dropbox_resume_before_extraction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that the runner skips an already-ingested Dropbox path before extraction.
    """

    artifact_path = tmp_path / "dropbox_folder_skip_summary.json"

    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            folder_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive",
            file_limit=1,
            dropbox_list_limit=10,
            resume_file_offset=0,
            force_reprocess=False,
        ),
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "build_artifact_path",
        lambda folder_path, *, resume_file_offset: artifact_path,
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "fetch_dropbox_list_folder",
        lambda **kwargs: {
            "entries": [
                {
                    ".tag": "file",
                    "name": "Jane-Doe-CV.pdf",
                    "path_display": "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf",
                }
            ],
            "has_more": False,
        },
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "_find_existing_dropbox_resume_skip_record",
        lambda **kwargs: {
            "source_record_uuid": UUID("84f71518-7bea-4370-9e33-b748e6ebd0e0"),
            "source_record_id": "path:path",
            "quality_status": "pass",
            "quality_score": 92,
            "document_id": UUID("2995be8c-b8eb-48b9-b8aa-e6c770c1d98f"),
            "document_title": "Jane-Doe-CV.pdf",
        },
    )

    def fail_if_called(**kwargs: object) -> None:
        raise AssertionError("expensive extraction path should have been skipped")

    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "download_dropbox_file",
        fail_if_called,
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "extract_text_from_resume_bytes",
        fail_if_called,
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "extract_dropbox_candidate_resume_profile_with_quality_gate",
        fail_if_called,
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "persist_scored_resume_extraction_result",
        fail_if_called,
    )

    dropbox_folder_resume_chunk.main()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["selected_resume_file_count"] == 1
    assert artifact["already_processed_count"] == 1
    assert artifact["new_resume_file_count"] == 0
    assert artifact["persisted_resume_count"] == 0
    assert artifact["skipped_count"] == 1


def test_main_respects_resume_file_offset_across_folder_pages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that the runner can move past the first page/front slice of a folder.
    """

    artifact_path = tmp_path / "dropbox_folder_offset_summary.json"

    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            folder_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive",
            file_limit=2,
            dropbox_list_limit=2,
            resume_file_offset=2,
            force_reprocess=False,
        ),
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "build_artifact_path",
        lambda folder_path, *, resume_file_offset: artifact_path,
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "fetch_dropbox_list_folder",
        lambda **kwargs: {
            "entries": [
                {".tag": "file", "name": "A.pdf", "path_display": "/folder/A.pdf"},
                {".tag": "file", "name": "B.pdf", "path_display": "/folder/B.pdf"},
            ],
            "cursor": "cursor-1",
            "has_more": True,
        },
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "fetch_dropbox_list_folder_continue",
        lambda **kwargs: {
            "entries": [
                {".tag": "file", "name": "C.pdf", "path_display": "/folder/C.pdf"},
                {".tag": "file", "name": "D.pdf", "path_display": "/folder/D.pdf"},
            ],
            "cursor": "cursor-2",
            "has_more": False,
        },
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "_find_existing_dropbox_resume_skip_record",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "download_dropbox_file",
        lambda **kwargs: {
            "file_name": Path(kwargs["path"]).name,
            "content_type": "application/pdf",
            "content_bytes": b"%PDF fake bytes",
            "file_metadata": {"server_modified": "2026-05-19T10:12:40Z"},
        },
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "extract_text_from_resume_bytes",
        lambda **kwargs: "Extracted CV text",
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "extract_dropbox_candidate_resume_profile_with_quality_gate",
        lambda **kwargs: {
            "model_profile": {"model_name": "gpt-4.1-mini"},
            "quality_assessment": {"status": "pass", "quality_score": 100},
            "quality_gate": {
                "first_pass_model_name": "gpt-4.1-mini",
                "fallback_model_name": "gpt-4.1-mini",
                "fallback_invoked": False,
                "final_model_name": "gpt-4.1-mini",
            },
        },
    )
    monkeypatch.setattr(
        dropbox_folder_resume_chunk,
        "persist_scored_resume_extraction_result",
        lambda result: {
            "source_record_id": "path:path",
            "document_id": "document-uuid",
            "document_title": "Resume.pdf",
        },
    )

    dropbox_folder_resume_chunk.main()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["resume_file_offset"] == 2
    assert artifact["selected_resume_file_count"] == 2
    assert artifact["persisted_resume_count"] == 2
    assert artifact["file_timing_preview"][0]["dropbox_path"] == "/folder/C.pdf"
    assert artifact["file_timing_preview"][1]["dropbox_path"] == "/folder/D.pdf"
