"""
Unit tests for Dropbox resume extraction helpers.
"""

from unittest.mock import patch

from backend.services.dropbox_resume_extraction import (
    build_dropbox_resume_text_bundle,
    derive_dropbox_candidate_name_parts,
    extract_dropbox_candidate_resume_profile,
    extract_dropbox_candidate_resume_profile_with_quality_gate,
)


def test_build_dropbox_resume_text_bundle_normalizes_generic_bundle_shape() -> None:
    """
    Verify that a direct Dropbox CV is normalized to the generic bundle contract.
    """

    bundle = build_dropbox_resume_text_bundle(
        dropbox_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf",
        dropbox_folder_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive",
        downloaded_file={
            "file_name": "Jane-Doe-CV.pdf",
            "content_type": "application/pdf",
            "content_bytes": b"pdf-bytes",
            "file_metadata": {
                "server_modified": "2026-05-19T10:12:40Z",
            },
        },
        extracted_resume_text={
            "text": "Jane Doe CV",
            "cleaned_text": "Jane Doe CV",
            "character_count": 11,
            "page_count": 1,
            "extractor": "pypdf",
        },
    )

    assert bundle["source_system"] == "dropbox"
    assert (
        bundle["source_candidate_id"]
        == "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf"
    )
    assert bundle["candidate_context"]["first_name"] == "Jane"
    assert bundle["candidate_context"]["last_name"] == "Doe"
    assert bundle["candidate_context"]["full_name"] == "Jane Doe"
    assert (
        bundle["latest_resume"]["attachmentId"]
        == "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf"
    )
    assert bundle["latest_resume"]["fileName"] == "Jane-Doe-CV.pdf"
    assert bundle["latest_resume"]["createdAt"] == "2026-05-19T10:12:40Z"


def test_extract_dropbox_candidate_resume_profile_adds_quality_layers() -> None:
    """
    Verify that the Dropbox path reuses the generic extraction layer and adds scoring.
    """

    with patch(
        "backend.services.dropbox_resume_extraction.extract_structured_candidate_profile_from_resume_bundle"
    ) as mock_extract, patch(
        "backend.services.dropbox_resume_extraction.score_resume_extraction"
    ) as mock_quality, patch(
        "backend.services.dropbox_resume_extraction.assess_source_cv_richness"
    ) as mock_richness:
        mock_extract.return_value = {
            "source_system": "dropbox",
            "source_candidate_id": "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf",
            "model_profile": {"model_name": "gpt-4.1-mini"},
            "extraction_input": {
                "cleaned_resume_text": "Jane Doe\nExperience\nSkills\nEducation\njane@example.com\n+447700900111",
            },
            "structured_extraction": {
                "current_employer": "Acme",
            },
        }
        mock_quality.return_value.model_dump.return_value = {
            "quality_score": 91,
            "status": "pass",
            "reasons": [],
        }
        mock_richness.return_value.model_dump.return_value = {
            "richness_score": 82,
            "richness_band": "rich",
            "reasons": [],
        }

        result = extract_dropbox_candidate_resume_profile(
            dropbox_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf",
            dropbox_folder_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive",
            downloaded_file={
                "file_name": "Jane-Doe-CV.pdf",
                "content_type": "application/pdf",
                "content_bytes": b"pdf-bytes",
                "file_metadata": {},
            },
            extracted_resume_text={
                "text": "Jane Doe CV",
                "cleaned_text": "Jane Doe CV",
                "character_count": 11,
                "page_count": 1,
                "extractor": "pypdf",
            },
            chat_model=object(),
        )

    assert result["source_system"] == "dropbox"
    assert result["quality_assessment"]["status"] == "pass"
    assert "richness_band" in result["cv_source_assessment"]
    assert result["quality_gate"]["enabled"] is False


def test_derive_dropbox_candidate_name_parts_strips_transport_noise() -> None:
    """
    Verify that common marketplace/transport tokens are removed from filenames.
    """

    first_name, last_name, full_name = derive_dropbox_candidate_name_parts(
        "AJAY ABRAHAM MATHEW (6608403 - Totaljobs)"
    )

    assert first_name == "Ajay"
    assert last_name == "Abraham Mathew"
    assert full_name == "Ajay Abraham Mathew"

    first_name, last_name, full_name = derive_dropbox_candidate_name_parts(
        "Mikael-Khah_20239602_cv-library"
    )

    assert first_name == "Mikael"
    assert last_name == "Khah"
    assert full_name == "Mikael Khah"

    first_name, last_name, full_name = derive_dropbox_candidate_name_parts(
        "IssamMouradResume"
    )

    assert first_name == "Issam"
    assert last_name == "Mourad"
    assert full_name == "Issam Mourad"


def test_extract_dropbox_candidate_resume_profile_with_quality_gate_starts_on_cheap_model() -> None:
    """
    Verify that the quality-gated Dropbox path starts on `gpt-4.1-mini`.
    """

    with patch(
        "backend.services.dropbox_resume_extraction.build_langchain_chat_model"
    ) as mock_builder, patch(
        "backend.services.dropbox_resume_extraction.extract_dropbox_candidate_resume_profile"
    ) as mock_extract:
        mock_builder.return_value = object()
        mock_extract.return_value = {
            "model_profile": {"model_name": "gpt-4.1-mini"},
            "quality_assessment": {"status": "pass", "quality_score": 91},
        }

        result = extract_dropbox_candidate_resume_profile_with_quality_gate(
            dropbox_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Jane-Doe-CV.pdf",
            dropbox_folder_path="/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive",
            downloaded_file={
                "file_name": "Jane-Doe-CV.pdf",
                "content_type": "application/pdf",
                "content_bytes": b"pdf-bytes",
                "file_metadata": {},
            },
            extracted_resume_text={
                "text": "Jane Doe CV",
                "cleaned_text": "Jane Doe CV",
                "character_count": 11,
                "page_count": 1,
                "extractor": "pypdf",
            },
        )

    built_profile = mock_builder.call_args.kwargs["profile"]
    assert built_profile.model_name == "gpt-4.1-mini"
    assert result["quality_gate"]["enabled"] is True
    assert result["quality_gate"]["fallback_invoked"] is False
