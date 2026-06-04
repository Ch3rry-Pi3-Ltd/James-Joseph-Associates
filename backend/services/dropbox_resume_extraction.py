"""
Dropbox resume extraction helpers.

This module feeds direct Dropbox CV files into the same LLM-backed structured
resume extraction path already used for JobAdder, Recruiterflow, and Outlook.
"""

from __future__ import annotations

from pathlib import PurePosixPath
import re
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
DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME = "gpt-4.1-mini"
DROPBOX_FILENAME_NOISE_TOKENS = frozenset(
    {
        "cv",
        "resume",
        "resum",
        "curriculum",
        "vitae",
        "totaljobs",
        "jobsite",
        "cvlibrary",
        "cvlibrarycom",
        "cvlibrarycouk",
        "cvlibraryuk",
        "cvlibrarycv",
        "reed",
        "monster",
        "indeed",
        "linkedin",
        "latest",
        "updated",
        "update",
        "final",
        "copy",
        "version",
        "shortcut",
        "suitable",
        "application",
        "js",
        "doc",
        "docx",
        "pdf",
        "rtf",
        "txt",
    }
)


def build_dropbox_resume_text_bundle(
    *,
    dropbox_path: str,
    dropbox_folder_path: str,
    downloaded_file: dict[str, Any],
    extracted_resume_text: dict[str, Any],
) -> dict[str, Any]:
    """
    Build one prepared resume-text bundle for a direct Dropbox CV file.
    """

    file_name = _clean_string(downloaded_file.get("file_name")) or PurePosixPath(
        dropbox_path
    ).name
    file_stem = PurePosixPath(file_name).stem
    first_name, last_name, full_name = derive_dropbox_candidate_name_parts(file_stem)
    source_candidate_id = dropbox_path

    return {
        "source_system": "dropbox",
        "source_candidate_id": source_candidate_id,
        "export_source_uri": dropbox_path,
        "candidate_context": {
            "candidate_id": source_candidate_id,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "email": None,
            "mobile": None,
            "location": None,
            "status": "Dropbox archive CV",
            "source_folder_path": dropbox_folder_path,
            "source_file_name": file_name,
            "source_path": dropbox_path,
            "updated_at": _clean_string(
                ((downloaded_file.get("file_metadata") or {}).get("server_modified"))
            )
            or _clean_string(
                ((downloaded_file.get("file_metadata") or {}).get("client_modified"))
            ),
        },
        "latest_resume": {
            "attachmentId": dropbox_path,
            "fileName": file_name,
            "fileType": downloaded_file.get("content_type"),
            "createdAt": _clean_string(
                ((downloaded_file.get("file_metadata") or {}).get("server_modified"))
            )
            or _clean_string(
                ((downloaded_file.get("file_metadata") or {}).get("client_modified"))
            ),
        },
        "candidate": {},
        "notes": {"cleaned_items": []},
        "downloaded_resume": downloaded_file,
        "extracted_resume_text": extracted_resume_text,
        "ingest_shell": {
            "dropbox_path": dropbox_path,
            "dropbox_folder_path": dropbox_folder_path,
        },
    }


def extract_dropbox_candidate_resume_profile(
    *,
    dropbox_path: str,
    dropbox_folder_path: str,
    downloaded_file: dict[str, Any],
    extracted_resume_text: dict[str, Any],
    chat_model: Any,
    model_profile: ModelProfile = DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
) -> dict[str, Any]:
    """
    Run the canonical structured resume-extraction path for one Dropbox CV.
    """

    resume_text_bundle = build_dropbox_resume_text_bundle(
        dropbox_path=dropbox_path,
        dropbox_folder_path=dropbox_folder_path,
        downloaded_file=downloaded_file,
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


def extract_dropbox_candidate_resume_profile_with_quality_gate(
    *,
    dropbox_path: str,
    dropbox_folder_path: str,
    downloaded_file: dict[str, Any],
    extracted_resume_text: dict[str, Any],
    pass_threshold: int = 80,
    rerun_threshold: int = 65,
    first_pass_model_name: str = DEFAULT_QUALITY_GATE_FIRST_PASS_MODEL_NAME,
    fallback_model_name: str = DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME,
) -> dict[str, Any]:
    """
    Run Dropbox CV extraction with the same cheaper first-pass/fallback model policy.
    """

    if rerun_threshold > pass_threshold:
        raise RuntimeError("rerun_threshold cannot be greater than pass_threshold.")

    first_pass_profile = ModelProfile(
        provider=ModelProvider.OPENAI,
        model_name=first_pass_model_name,
        purpose=ModelPurpose.EXTRACTION,
        temperature=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.temperature,
        max_output_tokens=DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE.max_output_tokens,
    )
    first_pass_result = extract_dropbox_candidate_resume_profile(
        dropbox_path=dropbox_path,
        dropbox_folder_path=dropbox_folder_path,
        downloaded_file=downloaded_file,
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
        fallback_result = extract_dropbox_candidate_resume_profile(
            dropbox_path=dropbox_path,
            dropbox_folder_path=dropbox_folder_path,
            downloaded_file=downloaded_file,
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
        "final_model_name": enriched_result.get("model_profile", {}).get(
            "model_name"
        ),
        "pass_threshold": pass_threshold,
        "rerun_threshold": rerun_threshold,
        "final_quality_status": final_assessment.get("status"),
        "final_quality_score": final_assessment.get("quality_score"),
    }
    return enriched_result


def _clean_string(value: Any) -> str | None:
    """
    Return a stripped string value, or `None` for blank-like input.
    """

    if not isinstance(value, str):
        return None
    cleaned_value = value.strip()
    return cleaned_value or None


def _split_name_like_filename(file_stem: str) -> tuple[str | None, str | None]:
    """
    Derive a weak first/last-name guess from a Dropbox CV filename.
    """

    first_name, last_name, _full_name = derive_dropbox_candidate_name_parts(file_stem)
    return first_name, last_name


def derive_dropbox_candidate_name_parts(
    file_stem: str,
) -> tuple[str | None, str | None, str | None]:
    """
    Derive a best-effort candidate name from a Dropbox CV filename.

    Notes
    -----
    Dropbox archive files often carry marketplace or ATS noise such as:

    - `Totaljobs`
    - `cv-library`
    - long numeric IDs
    - duplicate markers like `(1)`

    This helper removes the obvious transport noise before guessing the name.
    """

    normalized = file_stem
    normalized = re.sub(r"\[[^\]]*\]|\{[^}]*\}", " ", normalized)
    normalized = re.sub(r"\([^)]*\)", " ", normalized)
    normalized = normalized.replace("_", " ")
    normalized = normalized.replace("-", " ")
    normalized = normalized.replace("+", " ")
    normalized = normalized.replace("@", " ")
    normalized = normalized.replace("&", " ")
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", normalized)
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", normalized)
    normalized = re.sub(r"(?i)\bcv\s*library\b", " ", normalized)
    normalized = re.sub(r"(?i)\btotal\s*jobs\b", " ", normalized)
    normalized = re.sub(r"(?i)\bjob\s*site\b", " ", normalized)
    normalized = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ' ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized == "":
        return None, None, None

    raw_parts = [segment for segment in normalized.split() if segment]
    filtered_parts = [
        _normalize_name_token(segment)
        for segment in raw_parts
        if _keep_name_token(segment)
    ]
    parts = [segment for segment in filtered_parts if segment]
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0], None, parts[0]

    first_name = parts[0]
    last_name = " ".join(parts[1:])
    full_name = " ".join(parts)
    return first_name, last_name, full_name


def _keep_name_token(token: str) -> bool:
    """
    Return whether one filename token still looks name-like after cleaning.
    """

    normalized_token = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ']+", "", token).casefold()
    if normalized_token == "":
        return False
    if normalized_token in DROPBOX_FILENAME_NOISE_TOKENS:
        return False
    if normalized_token.isdigit():
        return False
    return True


def _normalize_name_token(token: str) -> str | None:
    """
    Return one display-safe candidate-name token.
    """

    cleaned_token = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ']+", "", token).strip("'")
    if cleaned_token == "":
        return None
    if cleaned_token.isupper() or cleaned_token.islower():
        return cleaned_token.title()
    return cleaned_token


__all__ = [
    "build_dropbox_resume_text_bundle",
    "derive_dropbox_candidate_name_parts",
    "extract_dropbox_candidate_resume_profile",
    "extract_dropbox_candidate_resume_profile_with_quality_gate",
]
