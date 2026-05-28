"""
Outlook resume extraction helpers.

This module feeds Outlook email-attachment CVs into the same LLM-backed
structured resume extraction path already used for JobAdder and Recruiterflow.

The key design rule is simple:

- Outlook CVs should be scored with the same extraction-quality rules
- persistence should carry the same quality decision the scorer produced
- the existing Outlook provenance path can still own the mailbox/message/job
  context after scoring has classified the CV
"""

from __future__ import annotations

from typing import Any

from backend.llm.models import ModelProfile, ModelProvider, ModelPurpose
from backend.llm.providers import build_langchain_chat_model
from backend.services.extraction_quality import (
    assess_source_cv_richness,
    score_resume_extraction,
)
from backend.services.resume_extraction import (
    DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
    extract_structured_candidate_profile_from_resume_bundle,
)

DEFAULT_QUALITY_GATE_FIRST_PASS_MODEL_NAME = "gpt-4.1-mini"
DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME = "gpt-5.4-mini"


def build_outlook_resume_text_bundle(
    *,
    microsoft_user_id: str,
    mailbox: str | None,
    folder_path: list[str],
    message: dict[str, Any],
    attachment_download: dict[str, Any],
    extracted_resume_text: dict[str, Any],
) -> dict[str, Any]:
    """
    Build one prepared resume-text bundle for an Outlook email attachment.
    """

    message_id = _clean_string(message.get("id")) or "unknown-message"
    attachment_id = (
        _clean_string(attachment_download.get("attachment_id"))
        or "unknown-attachment"
    )
    sender_name, sender_email = _extract_sender_identity(message)
    first_name, last_name = _split_name(sender_name)
    source_candidate_id = sender_email or (
        f"{microsoft_user_id}:{mailbox or 'me'}:{message_id}:{attachment_id}"
    )
    folder_segments = [segment for segment in folder_path if isinstance(segment, str)]

    return {
        "source_system": "outlook",
        "source_candidate_id": source_candidate_id,
        "microsoft_user_id": microsoft_user_id,
        "mailbox": mailbox,
        "candidate_context": {
            "candidate_id": source_candidate_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": sender_email,
            "mobile": None,
            "location": None,
            "status": "Advert response",
            "source_message_subject": _clean_string(message.get("subject")),
            "source_folder_path": " > ".join(folder_segments),
        },
        "latest_resume": {
            "attachment_id": attachment_id,
            "filename": _clean_string(attachment_download.get("file_name")),
            "fileType": _clean_string(attachment_download.get("content_type")),
            "created_at": _clean_string(message.get("receivedDateTime")),
        },
        "candidate": {},
        "notes": {"cleaned_items": []},
        "downloaded_resume": attachment_download,
        "extracted_resume_text": extracted_resume_text,
        "ingest_shell": {
            "microsoft_user_id": microsoft_user_id,
            "mailbox": mailbox,
            "folder_path": folder_segments,
            "message_id": message_id,
            "attachment_id": attachment_id,
        },
    }


def extract_outlook_candidate_resume_profile(
    *,
    microsoft_user_id: str,
    mailbox: str | None,
    folder_path: list[str],
    message: dict[str, Any],
    attachment_download: dict[str, Any],
    extracted_resume_text: dict[str, Any],
    chat_model: Any,
    model_profile: ModelProfile = DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
) -> dict[str, Any]:
    """
    Run the canonical structured resume-extraction path for one Outlook CV.
    """

    resume_text_bundle = build_outlook_resume_text_bundle(
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        folder_path=folder_path,
        message=message,
        attachment_download=attachment_download,
        extracted_resume_text=extracted_resume_text,
    )

    result = extract_structured_candidate_profile_from_resume_bundle(
        resume_text_bundle=resume_text_bundle,
        chat_model=chat_model,
        model_profile=model_profile,
    )

    cleaned_resume_text = result["extraction_input"]["cleaned_resume_text"]
    quality_assessment = score_resume_extraction(
        extraction=result["structured_extraction"],
        cleaned_resume_text=cleaned_resume_text,
    )
    cv_source_assessment = assess_source_cv_richness(
        cleaned_resume_text=cleaned_resume_text,
    )

    enriched_result = dict(result)
    enriched_result["quality_assessment"] = quality_assessment.model_dump()
    enriched_result["cv_source_assessment"] = cv_source_assessment.model_dump()
    enriched_result["quality_gate"] = {
        "enabled": False,
        "fallback_invoked": False,
        "final_model_name": result.get("model_profile", {}).get("model_name"),
    }
    return enriched_result


def extract_outlook_candidate_resume_profile_with_quality_gate(
    *,
    microsoft_user_id: str,
    mailbox: str | None,
    folder_path: list[str],
    message: dict[str, Any],
    attachment_download: dict[str, Any],
    extracted_resume_text: dict[str, Any],
    pass_threshold: int = 80,
    rerun_threshold: int = 65,
    first_pass_model_name: str = DEFAULT_QUALITY_GATE_FIRST_PASS_MODEL_NAME,
    fallback_model_name: str = DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME,
) -> dict[str, Any]:
    """
    Run Outlook CV extraction with the same cheaper first-pass/fallback model policy.

    Parameters
    ----------
    microsoft_user_id : str
        Connected Microsoft user identifier.

    mailbox : str | None
        Optional delegated mailbox identifier.

    folder_path : list[str]
        Human-readable mailbox folder path.

    message : dict[str, Any]
        Outlook message payload.

    attachment_download : dict[str, Any]
        Downloaded Outlook attachment payload.

    extracted_resume_text : dict[str, Any]
        Plain-text extraction result returned by
        `extract_text_from_resume_bytes(...)`.

    pass_threshold : int, default=80
        Score at or above this threshold is considered a pass.

    rerun_threshold : int, default=65
        Score below this threshold triggers the stronger fallback model.

    first_pass_model_name : str, default="gpt-4.1-mini"
        Cheaper first-pass model name.

    fallback_model_name : str, default="gpt-5.4-mini"
        Stronger fallback model name used only when the first pass asks for a rerun.

    Returns
    -------
    dict[str, Any]
        Final extraction result enriched with the same quality-gate metadata
        shape used by the JobAdder path.
    """

    if rerun_threshold > pass_threshold:
        raise RuntimeError(
            "rerun_threshold cannot be greater than pass_threshold."
        )

    first_pass_profile = ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name=first_pass_model_name,
        purpose=ModelPurpose.EXTRACTION,
        temperature=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.temperature,
        max_output_tokens=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.max_output_tokens,
    )
    first_pass_result = extract_outlook_candidate_resume_profile(
        microsoft_user_id=microsoft_user_id,
        mailbox=mailbox,
        folder_path=folder_path,
        message=message,
        attachment_download=attachment_download,
        extracted_resume_text=extracted_resume_text,
        chat_model=build_langchain_chat_model(profile=first_pass_profile),
        model_profile=first_pass_profile,
    )
    first_pass_assessment = first_pass_result["quality_assessment"]
    fallback_invoked = False
    final_result = first_pass_result
    final_assessment = first_pass_assessment

    if first_pass_assessment.get("status") == "rerun":
        fallback_invoked = True
        fallback_profile = ModelProfile(
            provider=ModelProvider.OPENAI,
            model_name=fallback_model_name,
            purpose=ModelPurpose.EXTRACTION,
            temperature=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.temperature,
            max_output_tokens=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.max_output_tokens,
        )
        fallback_result = extract_outlook_candidate_resume_profile(
            microsoft_user_id=microsoft_user_id,
            mailbox=mailbox,
            folder_path=folder_path,
            message=message,
            attachment_download=attachment_download,
            extracted_resume_text=extracted_resume_text,
            chat_model=build_langchain_chat_model(profile=fallback_profile),
            model_profile=fallback_profile,
        )
        fallback_assessment = fallback_result["quality_assessment"]
        if (
            fallback_assessment.get("quality_score", 0)
            >= first_pass_assessment.get("quality_score", 0)
        ):
            final_result = fallback_result
            final_assessment = fallback_assessment

    enriched_result = dict(final_result)
    enriched_result["quality_gate"] = {
        "enabled": True,
        "first_pass_model_name": first_pass_model_name,
        "fallback_model_name": fallback_model_name,
        "fallback_invoked": fallback_invoked,
        "final_model_name": final_result.get("model_profile", {}).get("model_name"),
        "first_pass_quality_assessment": first_pass_assessment,
        "final_quality_assessment": final_assessment,
    }
    return enriched_result


def _extract_sender_identity(message: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Return sender display name and email from one Outlook message payload.
    """

    from_payload = message.get("from")
    if not isinstance(from_payload, dict):
        return None, None

    email_address = from_payload.get("emailAddress")
    if not isinstance(email_address, dict):
        return None, None

    sender_name = _clean_string(email_address.get("name"))
    sender_email = _clean_string(email_address.get("address"))
    return sender_name, sender_email


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    """
    Split one display name into first-name and last-name parts conservatively.
    """

    if full_name is None:
        return None, None

    parts = [part for part in full_name.split() if part.strip() != ""]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def _clean_string(value: Any) -> str | None:
    """
    Return a stripped string value, or `None` for blank-like input.
    """

    if not isinstance(value, str):
        return None

    cleaned_value = value.strip()
    return cleaned_value or None


__all__ = [
    "build_outlook_resume_text_bundle",
    "extract_outlook_candidate_resume_profile",
    "extract_outlook_candidate_resume_profile_with_quality_gate",
]
