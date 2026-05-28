"""
Recruiterflow resume extraction helpers.

This module feeds Recruiterflow CV files into the same LLM-backed structured
resume extraction path already used for JobAdder.

The key design rule is simple:

- Recruiterflow CVs should not create a second canonical document model
- they should produce the same accepted-resume result shape as JobAdder
- persistence should therefore converge on the same canonical `resume`
  document type and candidate/person linkage rules

Examples
--------
Build a prepared resume-text bundle from one Recruiterflow candidate/file pair:

    bundle = build_recruiterflow_resume_text_bundle(
        export_source_uri="/exports/Recruiterflow.zip",
        member_name="candidate/1.100.json",
        candidate_payload=candidate_record,
        file_payload=file_record,
        downloaded_file=downloaded_file,
        extracted_resume_text=extracted_resume_text,
    )

Run structured extraction and deterministic quality assessment:

    result = extract_recruiterflow_candidate_resume_profile(
        export_source_uri="/exports/Recruiterflow.zip",
        member_name="candidate/1.100.json",
        candidate_payload=candidate_record,
        file_payload=file_record,
        downloaded_file=downloaded_file,
        extracted_resume_text=extracted_resume_text,
        chat_model=chat_model,
    )
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


def build_recruiterflow_resume_text_bundle(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
    file_payload: dict[str, Any],
    downloaded_file: dict[str, Any],
    extracted_resume_text: dict[str, Any],
) -> dict[str, Any]:
    """
    Build one prepared resume-text bundle for a Recruiterflow candidate CV.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the Recruiterflow ZIP export.

    member_name : str
        ZIP member name that contained the candidate JSON chunk.

    candidate_payload : dict[str, Any]
        Recruiterflow candidate record.

    file_payload : dict[str, Any]
        Recruiterflow nested candidate file record.

    downloaded_file : dict[str, Any]
        Downloaded file bundle containing the raw bytes and metadata.

    extracted_resume_text : dict[str, Any]
        Plain-text extraction result returned by
        `extract_text_from_resume_bytes(...)`.

    Returns
    -------
    dict[str, Any]
        Prepared resume-text bundle compatible with the generic structured
        extraction layer.
    """

    source_candidate_id = int(candidate_payload["id"])
    source_file_id = _extract_recruiterflow_file_id(file_payload=file_payload)

    return {
        "source_system": "recruiterflow",
        "source_candidate_id": source_candidate_id,
        "export_source_uri": export_source_uri,
        "candidate_context": {
            "candidate_id": source_candidate_id,
            "first_name": candidate_payload.get("first_name"),
            "last_name": candidate_payload.get("last_name"),
            "email": _pick_first_string_value(candidate_payload.get("email")),
            "mobile": _pick_first_string_value(candidate_payload.get("phone_number")),
            "location": _build_candidate_location(candidate_payload.get("location")),
            "status": _extract_nested_name(candidate_payload.get("status")),
            "skill_tags": candidate_payload.get("skills", []),
            "created_at": candidate_payload.get("created_at"),
            "updated_at": candidate_payload.get("updated_at"),
        },
        "latest_resume": {
            "file_id": source_file_id,
            "filename": _pick_first_present_string(file_payload, "filename", "name"),
            "fileType": downloaded_file.get("content_type"),
            "upload_time": _pick_first_present_string(
                file_payload,
                "upload_time",
                "created_at",
            ),
        },
        "candidate": {},
        "notes": {"cleaned_items": []},
        "downloaded_resume": downloaded_file,
        "extracted_resume_text": extracted_resume_text,
        "ingest_shell": {
            "export_source_uri": export_source_uri,
            "member_name": member_name,
        },
    }


def extract_recruiterflow_candidate_resume_profile(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
    file_payload: dict[str, Any],
    downloaded_file: dict[str, Any],
    extracted_resume_text: dict[str, Any],
    chat_model: Any,
    model_profile: ModelProfile = DEFAULT_RESUME_EXTRACTION_MODEL_PROFILE,
) -> dict[str, Any]:
    """
    Run the canonical structured resume-extraction path for one Recruiterflow CV.

    Returns
    -------
    dict[str, Any]
        Structured extraction result enriched with deterministic quality and
        source-richness assessments.
    """

    resume_text_bundle = build_recruiterflow_resume_text_bundle(
        export_source_uri=export_source_uri,
        member_name=member_name,
        candidate_payload=candidate_payload,
        file_payload=file_payload,
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


def extract_recruiterflow_candidate_resume_profile_with_quality_gate(
    *,
    export_source_uri: str,
    member_name: str,
    candidate_payload: dict[str, Any],
    file_payload: dict[str, Any],
    downloaded_file: dict[str, Any],
    extracted_resume_text: dict[str, Any],
    pass_threshold: int = 80,
    rerun_threshold: int = 65,
    first_pass_model_name: str = DEFAULT_QUALITY_GATE_FIRST_PASS_MODEL_NAME,
    fallback_model_name: str = DEFAULT_QUALITY_GATE_FALLBACK_MODEL_NAME,
) -> dict[str, Any]:
    """
    Run Recruiterflow CV extraction with the same cheaper first-pass/fallback model policy.

    Parameters
    ----------
    export_source_uri : str
        Stable identifier of the Recruiterflow ZIP export.

    member_name : str
        ZIP member name that contained the candidate JSON chunk.

    candidate_payload : dict[str, Any]
        Recruiterflow candidate record.

    file_payload : dict[str, Any]
        Recruiterflow nested candidate file record.

    downloaded_file : dict[str, Any]
        Downloaded file bundle containing the raw bytes and metadata.

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
    first_pass_result = extract_recruiterflow_candidate_resume_profile(
        export_source_uri=export_source_uri,
        member_name=member_name,
        candidate_payload=candidate_payload,
        file_payload=file_payload,
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
        fallback_result = extract_recruiterflow_candidate_resume_profile(
            export_source_uri=export_source_uri,
            member_name=member_name,
            candidate_payload=candidate_payload,
            file_payload=file_payload,
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
        "final_model_name": final_result.get("model_profile", {}).get("model_name"),
        "first_pass_quality_assessment": first_pass_assessment,
        "final_quality_assessment": final_assessment,
    }
    return enriched_result


def _extract_recruiterflow_file_id(*, file_payload: dict[str, Any]) -> int | None:
    """
    Return the best-effort upstream Recruiterflow file identifier.
    """

    for key in ("id", "file_id"):
        raw_value = file_payload.get(key)
        if isinstance(raw_value, int) and raw_value > 0:
            return raw_value
    return None


def _pick_first_present_string(payload: dict[str, Any], *keys: str) -> str | None:
    """
    Return the first non-empty string value from the supplied keys.
    """

    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
    return None


def _pick_first_string_value(raw_value: Any) -> str | None:
    """
    Return the first non-empty string from one scalar-or-list value.
    """

    if isinstance(raw_value, str) and raw_value.strip() != "":
        return raw_value.strip()

    if isinstance(raw_value, list):
        for item in raw_value:
            if isinstance(item, str) and item.strip() != "":
                return item.strip()

    return None


def _extract_nested_name(raw_value: Any) -> str | None:
    """
    Return a nested `.name` value when present.
    """

    if not isinstance(raw_value, dict):
        return None

    name = raw_value.get("name")
    if isinstance(name, str) and name.strip() != "":
        return name.strip()
    return None


def _build_candidate_location(raw_value: Any) -> str | None:
    """
    Return a compact location string from one Recruiterflow location payload.
    """

    if isinstance(raw_value, str) and raw_value.strip() != "":
        return raw_value.strip()

    if not isinstance(raw_value, dict):
        return None

    parts = []
    for key in ("city", "state", "country"):
        value = raw_value.get(key)
        if isinstance(value, str) and value.strip() != "":
            parts.append(value.strip())

    if not parts:
        return None
    return ", ".join(parts)


__all__ = [
    "build_recruiterflow_resume_text_bundle",
    "extract_recruiterflow_candidate_resume_profile",
    "extract_recruiterflow_candidate_resume_profile_with_quality_gate",
]
