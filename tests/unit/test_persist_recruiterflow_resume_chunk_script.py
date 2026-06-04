"""
Unit tests for the bounded Recruiterflow resume-chunk runner.
"""

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID
from zipfile import ZipFile

import pytest

import scripts.persist_recruiterflow_resume_chunk as recruiterflow_resume_chunk
from scripts.persist_recruiterflow_resume_chunk import (
    _build_recruiterflow_extraction_source_record_key,
    _find_existing_recruiterflow_resume_skip_record,
)


def test_build_recruiterflow_extraction_source_record_key_returns_candidate_file_pair() -> None:
    """
    Verify that the runner builds the canonical candidate/file skip key.
    """

    assert (
        _build_recruiterflow_extraction_source_record_key(
            source_candidate_id=4847,
            source_file_id=5679,
        )
        == "4847:5679"
    )


def test_build_recruiterflow_extraction_source_record_key_rejects_missing_file_id() -> None:
    """
    Verify that the runner refuses to build a skip key without a file ID.
    """

    with pytest.raises(RuntimeError) as excinfo:
        _build_recruiterflow_extraction_source_record_key(
            source_candidate_id=4847,
            source_file_id=None,
        )

    assert "upstream file ID" in str(excinfo.value)


def test_find_existing_recruiterflow_resume_skip_record_returns_linked_resume_row() -> None:
    """
    Verify that the skip lookup returns existing scored resume metadata.
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        "source_record_uuid": "source-uuid",
        "source_record_id": "4847:5679",
        "quality_status": "pass",
        "quality_score": 92,
        "document_id": "document-uuid",
        "document_title": "Bernardita Gutierrez CV EN 03-2026.pdf",
    }

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "scripts.persist_recruiterflow_resume_chunk.postgres_connection"
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = _find_existing_recruiterflow_resume_skip_record(
            extraction_source_record_id="4847:5679"
        )

    assert result == {
        "source_record_uuid": "source-uuid",
        "source_record_id": "4847:5679",
        "quality_status": "pass",
        "quality_score": 92,
        "document_id": "document-uuid",
        "document_title": "Bernardita Gutierrez CV EN 03-2026.pdf",
    }
    mock_cursor.execute.assert_called_once()


def test_find_existing_recruiterflow_resume_skip_record_returns_none_when_missing() -> None:
    """
    Verify that the skip lookup returns `None` when no canonical resume exists.
    """

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    with patch(
        "scripts.persist_recruiterflow_resume_chunk.postgres_connection"
    ) as mock_postgres_connection:
        mock_postgres_connection.return_value.__enter__.return_value = (
            mock_connection
        )

        result = _find_existing_recruiterflow_resume_skip_record(
            extraction_source_record_id="9999:1234"
        )

    assert result is None


def test_main_skips_already_persisted_resume_before_text_extraction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that the runner skips an already-ingested candidate/file pair
    before paying for extraction work again.

    Example
    -------
    We simulate one candidate row and one resume-like file where the DB-backed
    skip lookup says the canonical resume already exists. The runner should:

    - write an artifact showing one skipped item
    - avoid calling text extraction
    - avoid calling the structured extraction + persistence layer
    """

    candidate_payload = {
        "id": 4847,
        "files": [
            {
                "id": 5679,
                "filename": "Bernardita Gutierrez CV EN 03-2026.pdf",
                "is_primary": True,
                "upload_time": "2026-05-19T10:12:40Z",
            }
        ],
    }

    archive_bytes = _build_candidate_chunk_zip_bytes(
        candidate_member_name="candidate/1.100.json",
        candidate_payloads=[candidate_payload],
    )
    artifact_path = tmp_path / "recruiterflow_skip_summary.json"

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            candidate_member="candidate/1.100.json",
            candidate_limit=1,
            candidate_offset=0,
            persisted_resume_limit=1,
            force_reprocess=False,
            process_entire_chunk=False,
        ),
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "build_artifact_path",
        lambda candidate_member_name: artifact_path,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "download_dropbox_file",
        lambda **kwargs: {"content_bytes": archive_bytes},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_find_existing_recruiterflow_resume_skip_record",
        lambda **kwargs: {
            "source_record_uuid": UUID("84f71518-7bea-4370-9e33-b748e6ebd0e0"),
            "source_record_id": "4847:5679",
            "quality_status": "pass",
            "quality_score": 92,
            "document_id": UUID("2995be8c-b8eb-48b9-b8aa-e6c770c1d98f"),
            "document_title": "Bernardita Gutierrez CV EN 03-2026.pdf",
        },
    )

    def fail_if_called(**kwargs: object) -> None:
        raise AssertionError("expensive extraction path should have been skipped")

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_text_from_resume_bytes",
        fail_if_called,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_recruiterflow_candidate_resume_profile_with_quality_gate",
        fail_if_called,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "persist_scored_resume_extraction_result",
        fail_if_called,
    )

    recruiterflow_resume_chunk.main()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["selected_resume_candidate_count"] == 1
    assert artifact["no_resume_selected_count"] == 0
    assert artifact["already_processed_count"] == 1
    assert artifact["new_resume_candidate_count"] == 0
    assert artifact["persisted_resume_count"] == 0
    assert artifact["skipped_count"] == 1
    assert artifact["unsupported_count"] == 0
    assert artifact["failed_count"] == 0
    assert artifact["skipped_items_preview"] == [
        {
            "source_candidate_id": 4847,
            "source_file_id": 5679,
            "file_name": "Bernardita Gutierrez CV EN 03-2026.pdf",
            "source_record_id": "4847:5679",
            "document_id": "2995be8c-b8eb-48b9-b8aa-e6c770c1d98f",
            "document_title": "Bernardita Gutierrez CV EN 03-2026.pdf",
            "quality_status": "pass",
            "quality_score": 92,
        }
    ]


def test_main_force_reprocess_bypasses_skip_lookup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that `--force-reprocess` bypasses the early skip guard.

    Example
    -------
    We simulate the same candidate/file pair as an earlier run, but with the
    force flag enabled. The runner should continue into extraction and
    persistence even though the source record would otherwise be skippable.
    """

    candidate_payload = {
        "id": 4847,
        "files": [
            {
                "id": 5679,
                "filename": "Bernardita Gutierrez CV EN 03-2026.pdf",
                "is_primary": True,
                "upload_time": "2026-05-19T10:12:40Z",
            }
        ],
    }

    archive_bytes = _build_candidate_chunk_zip_bytes(
        candidate_member_name="candidate/1.100.json",
        candidate_payloads=[candidate_payload],
        embedded_resume_members={
            "candidate/files/4847/Bernardita Gutierrez CV EN 03-2026.pdf": b"%PDF fake bytes"
        },
    )
    artifact_path = tmp_path / "recruiterflow_force_summary.json"

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            candidate_member="candidate/1.100.json",
            candidate_limit=1,
            candidate_offset=0,
            persisted_resume_limit=1,
            force_reprocess=True,
            process_entire_chunk=False,
        ),
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "build_artifact_path",
        lambda candidate_member_name: artifact_path,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "download_dropbox_file",
        lambda **kwargs: {"content_bytes": archive_bytes},
    )

    skip_lookup_called = False

    def fake_skip_lookup(**kwargs: object) -> dict[str, object]:
        nonlocal skip_lookup_called
        skip_lookup_called = True
        return {"document_id": "should-not-be-used"}

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_find_existing_recruiterflow_resume_skip_record",
        fake_skip_lookup,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_text_from_resume_bytes",
        lambda **kwargs: "Extracted CV text",
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_recruiterflow_candidate_resume_profile_with_quality_gate",
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
        recruiterflow_resume_chunk,
        "persist_scored_resume_extraction_result",
        lambda result: {
            "source_record_id": "4847:5679",
            "document_id": "document-uuid",
            "document_title": "Bernardita Gutierrez CV EN 03-2026.pdf",
        },
    )

    recruiterflow_resume_chunk.main()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert skip_lookup_called is False
    assert artifact["force_reprocess"] is True
    assert artifact["selected_resume_candidate_count"] == 1
    assert artifact["no_resume_selected_count"] == 0
    assert artifact["already_processed_count"] == 0
    assert artifact["new_resume_candidate_count"] == 1
    assert artifact["persisted_resume_count"] == 1
    assert artifact["accepted_resume_count"] == 1
    assert artifact["skipped_count"] == 0
    assert artifact["persisted_resume_preview"][0]["model_name"] == "gpt-4.1-mini"


def test_main_counts_candidate_rows_with_no_selected_resume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that the runner reports candidate rows with no resume-like file.

    Example
    -------
    We simulate one candidate row whose only attached file is a Windows
    shortcut. That should not enter extraction, and the artifact should report
    one `no_resume_selected` row rather than pretending the row vanished.
    """

    candidate_payload = {
        "id": 3932,
        "name": "Kane Henderson",
        "files": [
            {
                "id": 4296,
                "filename": "updatedCV_latest - Shortcut.lnk",
                "is_primary": False,
                "upload_time": "2026-05-19T10:12:40Z",
            }
        ],
    }

    archive_bytes = _build_candidate_chunk_zip_bytes(
        candidate_member_name="candidate/901.1000.json",
        candidate_payloads=[candidate_payload],
    )
    artifact_path = tmp_path / "recruiterflow_no_resume_summary.json"

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            candidate_member="candidate/901.1000.json",
            candidate_limit=1,
            candidate_offset=0,
            persisted_resume_limit=1,
            force_reprocess=False,
            process_entire_chunk=False,
        ),
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "build_artifact_path",
        lambda candidate_member_name: artifact_path,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "download_dropbox_file",
        lambda **kwargs: {"content_bytes": archive_bytes},
    )

    def fail_if_called(**kwargs: object) -> None:
        raise AssertionError("non-resume file rows should not enter extraction")

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_text_from_resume_bytes",
        fail_if_called,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_recruiterflow_candidate_resume_profile_with_quality_gate",
        fail_if_called,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "persist_scored_resume_extraction_result",
        fail_if_called,
    )

    recruiterflow_resume_chunk.main()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["candidate_count"] == 1
    assert artifact["selected_resume_candidate_count"] == 0
    assert artifact["no_resume_selected_count"] == 1
    assert artifact["already_processed_count"] == 0
    assert artifact["new_resume_candidate_count"] == 0
    assert artifact["persisted_resume_count"] == 0
    assert artifact["skipped_count"] == 0
    assert artifact["unsupported_count"] == 0
    assert artifact["failed_count"] == 0


def test_main_writes_checkpoints_and_timing_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that the runner writes in-progress checkpoints and timing metadata.

    Example
    -------
    We simulate two candidate rows, force the checkpoint interval down to one
    row, and capture every artifact snapshot in memory. That proves the runner
    now exposes partial progress before the batch finishes, along with timing
    data that helps explain slow later chunks.
    """

    candidate_payloads = [
        {
            "id": 4847,
            "files": [
                {
                    "id": 5679,
                    "filename": "Bernardita Gutierrez CV EN 03-2026.pdf",
                    "is_primary": True,
                    "upload_time": "2026-05-19T10:12:40Z",
                }
            ],
        },
        {
            "id": 4848,
            "files": [
                {
                    "id": 5680,
                    "filename": "Thomas Mitchell CV.pdf",
                    "is_primary": True,
                    "upload_time": "2026-05-19T10:13:40Z",
                }
            ],
        },
    ]

    archive_bytes = _build_candidate_chunk_zip_bytes(
        candidate_member_name="candidate/1.100.json",
        candidate_payloads=candidate_payloads,
        embedded_resume_members={
            "candidate/files/4847/Bernardita Gutierrez CV EN 03-2026.pdf": b"%PDF fake bytes 1",
            "candidate/files/4848/Thomas Mitchell CV.pdf": b"%PDF fake bytes 2",
        },
    )

    artifact_path = tmp_path / "recruiterflow_checkpoint_summary.json"
    written_summaries: list[dict[str, object]] = []

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "CHECKPOINT_WRITE_INTERVAL",
        1,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            candidate_member="candidate/1.100.json",
            candidate_limit=2,
            candidate_offset=0,
            persisted_resume_limit=2,
            force_reprocess=False,
            process_entire_chunk=False,
        ),
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "build_artifact_path",
        lambda candidate_member_name: artifact_path,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "download_dropbox_file",
        lambda **kwargs: {"content_bytes": archive_bytes},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_find_existing_recruiterflow_resume_skip_record",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_text_from_resume_bytes",
        lambda **kwargs: "Extracted CV text",
    )

    quality_statuses = iter(["pass", "review"])

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_recruiterflow_candidate_resume_profile_with_quality_gate",
        lambda **kwargs: {
            "model_profile": {"model_name": "gpt-4.1-mini"},
            "quality_assessment": {
                "status": next(quality_statuses),
                "quality_score": 92,
            },
            "quality_gate": {
                "first_pass_model_name": "gpt-4.1-mini",
                "fallback_model_name": "gpt-4.1-mini",
                "fallback_invoked": False,
                "final_model_name": "gpt-4.1-mini",
            },
        },
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "persist_scored_resume_extraction_result",
        lambda result: {
            "source_record_id": "candidate:file",
            "document_id": "document-uuid",
            "document_title": "Resume.pdf",
        },
    )

    def capture_artifact(*, artifact_path: Path, summary: dict[str, object]) -> None:
        written_summaries.append(dict(summary))

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_write_summary_artifact",
        capture_artifact,
    )

    recruiterflow_resume_chunk.main()

    assert len(written_summaries) == 3
    assert written_summaries[0]["run_complete"] is False
    assert written_summaries[1]["run_complete"] is False
    assert written_summaries[2]["run_complete"] is True
    assert written_summaries[2]["checkpoint_write_count"] == 2
    assert written_summaries[2]["processed_candidate_count"] == 2
    assert written_summaries[2]["selected_resume_candidate_count"] == 2
    assert written_summaries[2]["persisted_resume_count"] == 2
    assert written_summaries[2]["accepted_resume_count"] == 1
    assert written_summaries[2]["non_pass_count"] == 1
    assert "timing_totals_seconds" in written_summaries[2]
    assert "timing_averages_seconds" in written_summaries[2]
    assert len(written_summaries[2]["candidate_timing_preview"]) == 2


def test_main_respects_candidate_offset_within_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that the runner processes a moving window inside one chunk.

    Example
    -------
    We simulate two candidate rows but set `candidate_offset=1` and
    `candidate_limit=1`. The runner should skip the first row entirely and only
    process the second row. This prevents the "first 20 forever" bug that
    would otherwise miss rows 21-100 in every later chunk.
    """

    candidate_payloads = [
        {
            "id": 1001,
            "files": [
                {
                    "id": 5001,
                    "filename": "first-candidate-cv.pdf",
                    "is_primary": True,
                    "upload_time": "2026-05-19T10:12:40Z",
                }
            ],
        },
        {
            "id": 1002,
            "files": [
                {
                    "id": 5002,
                    "filename": "second-candidate-cv.pdf",
                    "is_primary": True,
                    "upload_time": "2026-05-19T10:13:40Z",
                }
            ],
        },
    ]

    archive_bytes = _build_candidate_chunk_zip_bytes(
        candidate_member_name="candidate/1.100.json",
        candidate_payloads=candidate_payloads,
        embedded_resume_members={
            "candidate/files/1002/second-candidate-cv.pdf": b"%PDF fake bytes 2",
        },
    )
    artifact_path = tmp_path / "recruiterflow_offset_summary.json"

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            candidate_member="candidate/1.100.json",
            candidate_limit=1,
            candidate_offset=1,
            persisted_resume_limit=1,
            force_reprocess=False,
            process_entire_chunk=False,
        ),
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "build_artifact_path",
        lambda candidate_member_name: artifact_path,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "download_dropbox_file",
        lambda **kwargs: {"content_bytes": archive_bytes},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_find_existing_recruiterflow_resume_skip_record",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_text_from_resume_bytes",
        lambda **kwargs: "Extracted CV text",
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_recruiterflow_candidate_resume_profile_with_quality_gate",
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
        recruiterflow_resume_chunk,
        "persist_scored_resume_extraction_result",
        lambda result: {
            "source_record_id": "1002:5002",
            "document_id": "document-uuid",
            "document_title": "second-candidate-cv.pdf",
        },
    )

    recruiterflow_resume_chunk.main()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["candidate_limit"] == 1
    assert artifact["candidate_offset"] == 1
    assert artifact["candidate_count"] == 1
    assert artifact["chunk_total_candidate_count"] == 2
    assert artifact["processed_candidate_count"] == 1
    assert artifact["persisted_resume_count"] == 1
    assert artifact["candidate_timing_preview"][0]["source_candidate_id"] == 1002
    assert artifact["candidate_timing_preview"][0]["file_name"] == "second-candidate-cv.pdf"


def test_main_process_entire_chunk_walks_offsets_automatically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verify that one command can walk all windows inside a chunk automatically.

    Example
    -------
    We simulate five candidate rows, set `candidate_limit=2`, and enable
    `process_entire_chunk`. The runner should cover three windows with offsets
    `[0, 2, 4]` and persist all five rows without any manual offset juggling.
    """

    candidate_payloads = []
    embedded_resume_members: dict[str, bytes] = {}
    for index in range(5):
        candidate_id = 5000 + index
        file_id = 6000 + index
        file_name = f"candidate-{candidate_id}.pdf"
        candidate_payloads.append(
            {
                "id": candidate_id,
                "files": [
                    {
                        "id": file_id,
                        "filename": file_name,
                        "is_primary": True,
                        "upload_time": f"2026-05-19T10:1{index}:40Z",
                    }
                ],
            }
        )
        embedded_resume_members[
            f"candidate/files/{candidate_id}/{file_name}"
        ] = b"%PDF fake bytes"

    archive_bytes = _build_candidate_chunk_zip_bytes(
        candidate_member_name="candidate/1.100.json",
        candidate_payloads=candidate_payloads,
        embedded_resume_members=embedded_resume_members,
    )
    artifact_path = tmp_path / "recruiterflow_full_chunk_summary.json"

    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "parse_args",
        lambda: MagicMock(
            candidate_member="candidate/1.100.json",
            candidate_limit=2,
            candidate_offset=0,
            persisted_resume_limit=2,
            force_reprocess=False,
            process_entire_chunk=True,
        ),
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "build_artifact_path",
        lambda candidate_member_name: artifact_path,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "download_dropbox_file",
        lambda **kwargs: {"content_bytes": archive_bytes},
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "_find_existing_recruiterflow_resume_skip_record",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_text_from_resume_bytes",
        lambda **kwargs: "Extracted CV text",
    )
    monkeypatch.setattr(
        recruiterflow_resume_chunk,
        "extract_recruiterflow_candidate_resume_profile_with_quality_gate",
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
        recruiterflow_resume_chunk,
        "persist_scored_resume_extraction_result",
        lambda result: {
            "source_record_id": "candidate:file",
            "document_id": "document-uuid",
            "document_title": "Resume.pdf",
        },
    )

    recruiterflow_resume_chunk.main()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["process_entire_chunk"] is True
    assert artifact["candidate_limit"] == 2
    assert artifact["candidate_offset"] == 0
    assert artifact["candidate_count"] == 5
    assert artifact["chunk_total_candidate_count"] == 5
    assert artifact["processed_candidate_count"] == 5
    assert artifact["persisted_resume_count"] == 5
    assert artifact["accepted_resume_count"] == 5
    assert artifact["window_offsets_processed"] == [0, 2, 4]


def _build_candidate_chunk_zip_bytes(
    *,
    candidate_member_name: str,
    candidate_payloads: list[dict[str, object]],
    embedded_resume_members: dict[str, bytes] | None = None,
) -> bytes:
    """
    Build a small in-memory Recruiterflow ZIP export for script tests.
    """

    buffer = BytesIO()
    with ZipFile(buffer, mode="w") as archive:
        archive.writestr(candidate_member_name, json.dumps(candidate_payloads))
        for member_name, content_bytes in (embedded_resume_members or {}).items():
            archive.writestr(member_name, content_bytes)

    return buffer.getvalue()
