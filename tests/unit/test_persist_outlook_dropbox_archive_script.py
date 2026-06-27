import json
from argparse import Namespace
from pathlib import Path

import scripts.persist_outlook_dropbox_archive as outlook_dropbox_archive


def test_list_resume_bearing_dropbox_folders_discovers_leaf_resume_folders(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        outlook_dropbox_archive,
        "fetch_dropbox_list_folder",
        lambda **kwargs: {
            "entries": [
                {
                    ".tag": "file",
                    "name": "Jane Doe CV.pdf",
                    "path_display": "/+++ Outlook CV Export/2026/Q2/Jane Doe CV.pdf",
                },
                {
                    ".tag": "file",
                    "name": "ignore.txt",
                    "path_display": "/+++ Outlook CV Export/notes/ignore.txt",
                },
            ],
            "cursor": "cursor-1",
            "has_more": True,
        },
    )
    monkeypatch.setattr(
        outlook_dropbox_archive,
        "fetch_dropbox_list_folder_continue",
        lambda **kwargs: {
            "entries": [
                {
                    ".tag": "file",
                    "name": "John Doe CV.docx",
                    "path_display": "/+++ Outlook CV Export/2026/Q1/John Doe CV.docx",
                }
            ],
            "cursor": "cursor-2",
            "has_more": False,
        },
    )

    result = outlook_dropbox_archive.list_resume_bearing_dropbox_folders(
        access_token="token",
        base_folder_path="/+++ Outlook CV Export",
        dropbox_list_limit=200,
    )

    assert result == [
        "/+++ Outlook CV Export/2026/Q1",
        "/+++ Outlook CV Export/2026/Q2",
        "/+++ Outlook CV Export/notes",
    ]


def test_main_processes_outlook_archive_and_runs_backfills(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "outlook_archive_summary.json"

    monkeypatch.setattr(
        outlook_dropbox_archive,
        "build_parser",
        lambda: type(
            "Parser",
            (),
            {
                "parse_args": lambda self: Namespace(
                    base_folder_path="/+++ Outlook CV Export",
                    folder_limit=None,
                    file_limit=20,
                    dropbox_list_limit=200,
                    resume_file_offset=0,
                    force_reprocess=False,
                    skip_chunk_backfill=False,
                    skip_embedding_backfill=False,
                    chunk_limit=250,
                    chunk_max_chars=1200,
                    chunk_overlap_chars=150,
                    embedding_limit=1000,
                    embedding_batch_size=25,
                    output_json=output_json,
                )
            },
        )(),
    )
    monkeypatch.setattr(
        outlook_dropbox_archive,
        "_load_dropbox_connection",
        lambda account_id: {"access_token": "token"},
    )
    monkeypatch.setattr(
        outlook_dropbox_archive,
        "list_resume_bearing_dropbox_folders",
        lambda **kwargs: [
            "/+++ Outlook CV Export/2026/Q1",
            "/+++ Outlook CV Export/2026/Q2",
        ],
    )
    monkeypatch.setattr(
        outlook_dropbox_archive,
        "build_artifact_path",
        lambda folder_path, *, resume_file_offset: (
            tmp_path / f"{Path(folder_path).name}_artifact.json"
        ),
    )
    monkeypatch.setattr(
        outlook_dropbox_archive,
        "run_dropbox_folder_resume_persistence",
        lambda **kwargs: {
            "folder_path": kwargs["folder_path"],
            "persisted_resume_count": 2,
            "skipped_count": 1,
            "unsupported_count": 0,
            "failed_count": 0,
        },
    )
    monkeypatch.setattr(
        outlook_dropbox_archive,
        "_run_chunk_backfill",
        lambda **kwargs: [
            {
                "documents_selected": 2,
                "documents_processed": 2,
                "chunks_inserted": 8,
            }
        ],
    )
    monkeypatch.setattr(
        outlook_dropbox_archive,
        "_run_embedding_backfill",
        lambda **kwargs: [
            {
                "chunks_selected": 8,
                "chunks_embedded": 8,
            }
        ],
    )

    outlook_dropbox_archive.main()

    summary = json.loads(output_json.read_text(encoding="utf-8"))
    assert summary["resume_folder_count"] == 2
    assert summary["processed_folder_count"] == 2
    assert summary["failed_folder_count"] == 0
    assert len(summary["folder_summaries"]) == 2
    assert summary["chunk_backfill_runs"][0]["documents_processed"] == 2
    assert summary["embedding_backfill_runs"][0]["chunks_embedded"] == 8
