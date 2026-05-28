"""
Unit tests for Outlook resume extraction helpers.
"""

from unittest.mock import patch

from backend.services.outlook_resume_extraction import (
    build_outlook_resume_text_bundle,
    extract_outlook_candidate_resume_profile,
    extract_outlook_candidate_resume_profile_with_quality_gate,
)


def _build_message_payload() -> dict[str, object]:
    return {
        "id": "message-123",
        "subject": "candidate@example.com - Totaljobs - Suitable application for tw394",
        "receivedDateTime": "2026-05-28T10:00:00Z",
        "from": {
            "emailAddress": {
                "name": "Thomas Mitchell",
                "address": "candidate@example.com",
            }
        },
    }


def _build_attachment_download() -> dict[str, object]:
    return {
        "attachment_id": "attachment-456",
        "file_name": "Thomas Mitchell CV.pdf",
        "content_type": "application/pdf",
        "content_bytes": b"pdf-bytes",
    }


def test_build_outlook_resume_text_bundle_normalizes_generic_bundle_shape() -> None:
    """
    Verify that Outlook CV input is normalized to the generic bundle contract.
    """

    bundle = build_outlook_resume_text_bundle(
        microsoft_user_id="user-1",
        mailbox=None,
        folder_path=["Inbox", "# ADV-CVR", "tw394"],
        message=_build_message_payload(),
        attachment_download=_build_attachment_download(),
        extracted_resume_text={
            "text": "Thomas Mitchell CV",
            "cleaned_text": "Thomas Mitchell CV",
            "character_count": 18,
            "page_count": 1,
            "extractor": "pypdf",
        },
    )

    assert bundle["source_system"] == "outlook"
    assert bundle["source_candidate_id"] == "candidate@example.com"
    assert bundle["candidate_context"]["first_name"] == "Thomas"
    assert bundle["candidate_context"]["last_name"] == "Mitchell"
    assert bundle["latest_resume"]["attachment_id"] == "attachment-456"
    assert bundle["downloaded_resume"]["content_type"] == "application/pdf"


def test_extract_outlook_candidate_resume_profile_adds_quality_layers() -> None:
    """
    Verify that the Outlook path reuses the generic extraction layer and scoring.
    """

    with patch(
        "backend.services.outlook_resume_extraction.extract_structured_candidate_profile_from_resume_bundle"
    ) as mock_extract, patch(
        "backend.services.outlook_resume_extraction.score_resume_extraction"
    ) as mock_quality, patch(
        "backend.services.outlook_resume_extraction.assess_source_cv_richness"
    ) as mock_richness:
        mock_extract.return_value = {
            "source_system": "outlook",
            "source_candidate_id": "candidate@example.com",
            "model_profile": {"model_name": "gpt-5.4"},
            "extraction_input": {
                "cleaned_resume_text": "Thomas Mitchell\nExperience\nSkills\nEducation\ncandidate@example.com",
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

        result = extract_outlook_candidate_resume_profile(
            microsoft_user_id="user-1",
            mailbox=None,
            folder_path=["Inbox", "# ADV-CVR", "tw394"],
            message=_build_message_payload(),
            attachment_download=_build_attachment_download(),
            extracted_resume_text={
                "text": "Thomas Mitchell CV",
                "cleaned_text": "Thomas Mitchell CV",
                "character_count": 18,
                "page_count": 1,
                "extractor": "pypdf",
            },
            chat_model=object(),
        )

    assert result["source_system"] == "outlook"
    assert result["quality_assessment"]["status"] == "pass"
    assert "richness_band" in result["cv_source_assessment"]
    assert result["quality_gate"]["enabled"] is False


def test_extract_outlook_candidate_resume_profile_with_quality_gate_starts_on_cheap_model() -> None:
    """
    Verify that the quality-gated Outlook path starts on `gpt-4.1-mini`.
    """

    with patch(
        "backend.services.outlook_resume_extraction.build_langchain_chat_model"
    ) as mock_builder, patch(
        "backend.services.outlook_resume_extraction.extract_outlook_candidate_resume_profile"
    ) as mock_extract:
        mock_builder.return_value = object()
        mock_extract.return_value = {
            "model_profile": {"model_name": "gpt-4.1-mini"},
            "quality_assessment": {"status": "pass", "quality_score": 91},
        }

        result = extract_outlook_candidate_resume_profile_with_quality_gate(
            microsoft_user_id="user-1",
            mailbox=None,
            folder_path=["Inbox", "# ADV-CVR", "tw394"],
            message=_build_message_payload(),
            attachment_download=_build_attachment_download(),
            extracted_resume_text={
                "text": "Thomas Mitchell CV",
                "cleaned_text": "Thomas Mitchell CV",
                "character_count": 18,
                "page_count": 1,
                "extractor": "pypdf",
            },
        )

    built_profile = mock_builder.call_args.kwargs["profile"]
    assert built_profile.model_name == "gpt-4.1-mini"
    assert result["quality_gate"]["enabled"] is True
    assert result["quality_gate"]["fallback_invoked"] is False


def test_extract_outlook_candidate_resume_profile_with_quality_gate_uses_fallback_for_rerun() -> None:
    """
    Verify that the fallback model is used only when the first pass requests a rerun.
    """

    with patch(
        "backend.services.outlook_resume_extraction.build_langchain_chat_model"
    ) as mock_builder, patch(
        "backend.services.outlook_resume_extraction.extract_outlook_candidate_resume_profile"
    ) as mock_extract:
        mock_builder.side_effect = [object(), object()]
        mock_extract.side_effect = [
            {
                "model_profile": {"model_name": "gpt-4.1-mini"},
                "quality_assessment": {"status": "rerun", "quality_score": 61},
            },
            {
                "model_profile": {"model_name": "gpt-5.4-mini"},
                "quality_assessment": {"status": "pass", "quality_score": 88},
            },
        ]

        result = extract_outlook_candidate_resume_profile_with_quality_gate(
            microsoft_user_id="user-1",
            mailbox=None,
            folder_path=["Inbox", "# ADV-CVR", "tw394"],
            message=_build_message_payload(),
            attachment_download=_build_attachment_download(),
            extracted_resume_text={
                "text": "Thomas Mitchell CV",
                "cleaned_text": "Thomas Mitchell CV",
                "character_count": 18,
                "page_count": 1,
                "extractor": "pypdf",
            },
        )

    built_model_names = [
        call.kwargs["profile"].model_name for call in mock_builder.call_args_list
    ]
    assert built_model_names == ["gpt-4.1-mini", "gpt-5.4-mini"]
    assert result["quality_gate"]["fallback_invoked"] is True
    assert result["quality_gate"]["final_model_name"] == "gpt-5.4-mini"
