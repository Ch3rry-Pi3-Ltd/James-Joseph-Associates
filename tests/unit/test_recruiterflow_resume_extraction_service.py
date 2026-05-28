"""
Unit tests for Recruiterflow resume extraction helpers.
"""

from unittest.mock import patch

from backend.services.recruiterflow_resume_extraction import (
    build_recruiterflow_resume_text_bundle,
    extract_recruiterflow_candidate_resume_profile,
    extract_recruiterflow_candidate_resume_profile_with_quality_gate,
)


def _build_candidate_payload() -> dict[str, object]:
    return {
        "id": 4847,
        "first_name": "Bernardita",
        "last_name": "Gutierrez",
        "email": ["bngutierrezvg@gmail.com"],
        "phone_number": ["7775092914"],
        "status": {"name": "Active"},
        "location": {"city": "Santiago", "country": "Chile"},
    }


def _build_file_payload() -> dict[str, object]:
    return {
        "id": 5679,
        "filename": "Bernardita Gutierrez CV EN 03-2026.pdf",
        "upload_time": "2026-03-11T20:27:51+00:00",
        "is_primary": True,
    }


def test_build_recruiterflow_resume_text_bundle_normalizes_generic_bundle_shape() -> None:
    """
    Verify that Recruiterflow CV input is normalized to the generic bundle contract.
    """

    bundle = build_recruiterflow_resume_text_bundle(
        export_source_uri="/exports/Recruiterflow.zip",
        member_name="candidate/1.100.json",
        candidate_payload=_build_candidate_payload(),
        file_payload=_build_file_payload(),
        downloaded_file={
            "file_name": "Bernardita Gutierrez CV EN 03-2026.pdf",
            "content_type": "application/pdf",
            "content_bytes": b"pdf-bytes",
        },
        extracted_resume_text={
            "text": "Bernardita Gutierrez CV",
            "cleaned_text": "Bernardita Gutierrez CV",
            "character_count": 24,
            "page_count": 1,
            "extractor": "pypdf",
        },
    )

    assert bundle["source_system"] == "recruiterflow"
    assert bundle["source_candidate_id"] == 4847
    assert bundle["candidate_context"]["first_name"] == "Bernardita"
    assert bundle["latest_resume"]["file_id"] == 5679
    assert bundle["downloaded_resume"]["content_type"] == "application/pdf"


def test_extract_recruiterflow_candidate_resume_profile_adds_quality_layers() -> None:
    """
    Verify that the Recruiterflow path reuses the generic extraction layer and adds scoring.
    """

    with patch(
        "backend.services.recruiterflow_resume_extraction.extract_structured_candidate_profile_from_resume_bundle"
    ) as mock_extract, patch(
        "backend.services.recruiterflow_resume_extraction.score_resume_extraction"
    ) as mock_quality, patch(
        "backend.services.recruiterflow_resume_extraction.assess_source_cv_richness"
    ) as mock_richness:
        mock_extract.return_value = {
            "source_system": "recruiterflow",
            "source_candidate_id": 4847,
            "model_profile": {"model_name": "gpt-5.4"},
            "extraction_input": {
                "cleaned_resume_text": "Bernardita Gutierrez\nExperience\nSkills\nEducation\nbernardita@example.com\n+447700900111",
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

        result = extract_recruiterflow_candidate_resume_profile(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="candidate/1.100.json",
            candidate_payload=_build_candidate_payload(),
            file_payload=_build_file_payload(),
            downloaded_file={
                "file_name": "Bernardita Gutierrez CV EN 03-2026.pdf",
                "content_type": "application/pdf",
                "content_bytes": b"pdf-bytes",
            },
            extracted_resume_text={
                "text": "Bernardita Gutierrez CV",
                "cleaned_text": "Bernardita Gutierrez CV",
                "character_count": 24,
                "page_count": 1,
                "extractor": "pypdf",
            },
            chat_model=object(),
        )

    assert result["source_system"] == "recruiterflow"
    assert result["quality_assessment"]["status"] == "pass"
    assert "richness_band" in result["cv_source_assessment"]
    assert result["quality_gate"]["enabled"] is False


def test_extract_recruiterflow_candidate_resume_profile_with_quality_gate_starts_on_cheap_model() -> None:
    """
    Verify that the quality-gated Recruiterflow path starts on `gpt-4.1-mini`.
    """

    with patch(
        "backend.services.recruiterflow_resume_extraction.build_langchain_chat_model"
    ) as mock_builder, patch(
        "backend.services.recruiterflow_resume_extraction.extract_recruiterflow_candidate_resume_profile"
    ) as mock_extract:
        mock_builder.return_value = object()
        mock_extract.return_value = {
            "model_profile": {"model_name": "gpt-4.1-mini"},
            "quality_assessment": {"status": "pass", "quality_score": 91},
        }

        result = extract_recruiterflow_candidate_resume_profile_with_quality_gate(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="candidate/1.100.json",
            candidate_payload=_build_candidate_payload(),
            file_payload=_build_file_payload(),
            downloaded_file={
                "file_name": "Bernardita Gutierrez CV EN 03-2026.pdf",
                "content_type": "application/pdf",
                "content_bytes": b"pdf-bytes",
            },
            extracted_resume_text={
                "text": "Bernardita Gutierrez CV",
                "cleaned_text": "Bernardita Gutierrez CV",
                "character_count": 24,
                "page_count": 1,
                "extractor": "pypdf",
            },
        )

    built_profile = mock_builder.call_args.kwargs["profile"]
    assert built_profile.model_name == "gpt-4.1-mini"
    assert result["quality_gate"]["enabled"] is True
    assert result["quality_gate"]["fallback_invoked"] is False


def test_extract_recruiterflow_candidate_resume_profile_with_quality_gate_uses_fallback_for_rerun() -> None:
    """
    Verify that the fallback model is used only when the first pass requests a rerun.
    """

    with patch(
        "backend.services.recruiterflow_resume_extraction.build_langchain_chat_model"
    ) as mock_builder, patch(
        "backend.services.recruiterflow_resume_extraction.extract_recruiterflow_candidate_resume_profile"
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

        result = extract_recruiterflow_candidate_resume_profile_with_quality_gate(
            export_source_uri="/exports/Recruiterflow.zip",
            member_name="candidate/1.100.json",
            candidate_payload=_build_candidate_payload(),
            file_payload=_build_file_payload(),
            downloaded_file={
                "file_name": "Bernardita Gutierrez CV EN 03-2026.pdf",
                "content_type": "application/pdf",
                "content_bytes": b"pdf-bytes",
            },
            extracted_resume_text={
                "text": "Bernardita Gutierrez CV",
                "cleaned_text": "Bernardita Gutierrez CV",
                "character_count": 24,
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
