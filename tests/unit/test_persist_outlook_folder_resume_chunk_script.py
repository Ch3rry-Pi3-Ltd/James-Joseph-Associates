"""
Unit tests for the Outlook folder resume runner path helpers.
"""

import scripts.persist_outlook_tw394_folder as outlook_folder_resume_chunk


def test_build_outlook_dropbox_export_path_uses_year_and_quarter_buckets() -> None:
    """
    Verify that Outlook CV exports land under a year/quarter subfolder.
    """

    assert (
        outlook_folder_resume_chunk._build_outlook_dropbox_export_path(
            base_folder="/+++ Outlook CV Export",
            received_at="2026-06-25T09:30:00Z",
            file_name="Jane-Doe-CV.pdf",
        )
        == "/+++ Outlook CV Export/2026/Q2/Jane-Doe-CV.pdf"
    )


def test_build_outlook_dropbox_export_path_falls_back_when_received_time_is_missing() -> None:
    """
    Verify that Outlook CV exports still produce a stable path when no usable timestamp exists.
    """

    assert (
        outlook_folder_resume_chunk._build_outlook_dropbox_export_path(
            base_folder="/+++ Outlook CV Export",
            received_at=None,
            file_name="Jane-Doe-CV.pdf",
        )
        == "/+++ Outlook CV Export/unknown-date/Jane-Doe-CV.pdf"
    )
