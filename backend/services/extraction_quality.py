"""
Deterministic quality assessment for structured resume extraction.

This module provides two deterministic, non-LLM assessment layers:

- extraction quality scoring for routing and triage
- source CV richness scoring for source-document quality and downstream review

Why this module exists
----------------------
The extraction pipeline now has multiple plausible model choices:

- cheaper first-pass models
- stronger fallback models

That creates a routing question:

    "Can we reject obviously weak extraction output without asking another
    model to judge it?"

This module answers that with deterministic checks based on:

- schema completeness
- source-hint extraction from cleaned resume text
- simple contradiction / thinness heuristics
- source-document richness signals such as section presence, role density, and
  amount of descriptive text

What this module is for
-----------------------
It is for:

- deciding whether an extraction is probably good enough
- deciding whether to rerun a candidate through a stronger model
- producing explainable reasons for those decisions
- surfacing when a CV is merely sparse rather than poorly extracted

What this module is not for
---------------------------
It is not:

- a semantic truth evaluator
- a substitute for a human gold-standard review set
- a subtle judge of summary quality or skill interpretation

Example
-------
A caller can score one extraction and receive:

    ExtractionQualityAssessment(
        quality_score=61,
        status="rerun",
        reasons=[
            "missing_phones_despite_resume_hint",
            "projects_empty_despite_projects_section",
        ],
        ...
    )

In plain language:

- inspect the output cheaply
- compare it to obvious hints from the source text
- decide whether to keep it, review it, or rerun it
- separately describe whether the source CV itself is rich, adequate, or sparse
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.services.resume_extraction import ResumeStructuredExtraction


_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_CANDIDATE_PATTERN = re.compile(r"(?:\+?\d[\d\s().\-]{8,}\d)")
_DATE_RANGE_PATTERN = re.compile(
    r"\b(?:"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|"
    r"\d{1,2}[./-]\d{4}"
    r"|"
    r"\d{4}[./-]\d{1,2}"
    r"|"
    r"\d{4}"
    r")\s*[-–—]\s*(?:"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|"
    r"\d{1,2}[./-]\d{4}"
    r"|"
    r"\d{4}[./-]\d{1,2}"
    r"|"
    r"\d{4}"
    r"|Present"
    r"|present"
    r"|Current"
    r"|current"
    r"|Currently"
    r"|currently"
    r")\b",
    re.IGNORECASE,
)
_SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "experience": (
        "experience",
        "employment",
        "work history",
        "career history",
        "professional experience",
        "software development experience",
    ),
    "education": ("education",),
    "skills": ("skills", "technical skills", "core skills"),
    "certifications": ("certifications", "certification"),
    "projects": ("projects", "project experience", "major projects"),
    "portfolio": ("portfolio",),
}
_SUSPICIOUS_NOTE_ONLY_TERMS = (
    "openrouter",
    "nemotron",
    "gpt api",
    "gpt o1",
    "mcp server",
)


class ExtractionQualityAssessment(BaseModel):
    """
    One deterministic quality assessment for structured extraction output.

    Attributes
    ----------
    quality_score : int
        Final 0-100 score after deterministic penalties are applied.

    status : Literal["pass", "review", "rerun"]
        Routing decision derived from the thresholds used by the scorer.

    reasons : list[str]
        Short machine-readable reason labels explaining why the score was
        reduced or why a review/rerun decision was reached.

    source_hints : dict[str, Any]
        Deterministically extracted hints from the cleaned resume text, such
        as contact counts and section-presence flags.

    check_results : dict[str, Any]
        Per-check counts and flags that help later debugging and threshold
        tuning.

    Example
    -------
    A realistic assessment may look like:

        ExtractionQualityAssessment(
            quality_score=74,
            status="review",
            reasons=["email_count_lower_than_resume_hint", "evidence_notes_thin"],
            source_hints={"resume_email_count": 2},
            check_results={"email_count": 1},
        )
    """

    quality_score: int
    status: Literal["pass", "review", "rerun"]
    reasons: list[str] = Field(default_factory=list)
    source_hints: dict[str, Any] = Field(default_factory=dict)
    check_results: dict[str, Any] = Field(default_factory=dict)


class CVSourceAssessment(BaseModel):
    """
    One deterministic assessment of the source CV's richness.

    Attributes
    ----------
    richness_score : int
        Final 0-100 richness score for the cleaned source CV text.

    richness_band : Literal["rich", "adequate", "sparse", "very_sparse"]
        Coarse source-quality band derived from the richness score.

    reasons : list[str]
        Short machine-readable reason labels explaining why the richness score
        was reduced.

    source_metrics : dict[str, Any]
        Deterministic source-document metrics such as word count, section
        presence, and role/date-range density.

    Notes
    -----
    This score is intentionally advisory. It should help distinguish:

    - a sparse but correctly extracted CV
    - a richer CV where the extraction itself may have underperformed

    It should not trigger fallback reruns on its own.

    Example
    -------
    A sparse one-page CV may produce:

        CVSourceAssessment(
            richness_score=42,
            richness_band="sparse",
            reasons=["short_resume_text", "limited_employment_signals"],
            source_metrics={"word_count": 78},
        )
    """

    richness_score: int
    richness_band: Literal["rich", "adequate", "sparse", "very_sparse"]
    reasons: list[str] = Field(default_factory=list)
    source_metrics: dict[str, Any] = Field(default_factory=dict)


def score_resume_extraction(
    *,
    extraction: ResumeStructuredExtraction | dict[str, Any],
    cleaned_resume_text: str,
    pass_threshold: int = 80,
    rerun_threshold: int = 65,
) -> ExtractionQualityAssessment:
    """
    Score one structured extraction result using deterministic heuristics.

    Parameters
    ----------
    extraction : ResumeStructuredExtraction | dict[str, Any]
        Structured extraction result to assess. A plain dictionary is accepted
        and validated into the schema first.

    cleaned_resume_text : str
        Cleaned resume text used to derive source hints such as emails, phones,
        and section presence.

    pass_threshold : int
        Score at or above this threshold returns `status="pass"`.

    rerun_threshold : int
        Score below this threshold returns `status="rerun"`. Scores between the
        two thresholds return `status="review"`.

    Returns
    -------
    ExtractionQualityAssessment
        Deterministic quality assessment with score, routing decision, and
        supporting reasons.

    Notes
    -----
    - This is intentionally a routing/trust gate, not a semantic evaluator.
    - It should catch obvious bad runs, suspicious thin outputs, and simple
      source-output mismatches cheaply.

    Example
    -------
    A caller can score a first-pass extraction like:

        assessment = score_resume_extraction(
            extraction=result["structured_extraction"],
            cleaned_resume_text=result["extraction_input"]["cleaned_resume_text"],
        )

    and then route on:

        assessment.status

    In plain language:

    - start from 100
    - subtract penalties for obvious problems
    - return an explainable keep/review/rerun decision
    """

    if not isinstance(extraction, ResumeStructuredExtraction):
        extraction = ResumeStructuredExtraction.model_validate(extraction)

    source_hints = _build_source_hints(cleaned_resume_text)
    score = 100
    reasons: list[str] = []

    has_current_employer = extraction.current_employer is not None and extraction.current_employer.strip() != ""
    has_current_title = extraction.current_title is not None and extraction.current_title.strip() != ""
    email_count = len(extraction.emails)
    phone_count = len(extraction.phones)
    employment_count = len(extraction.employment_history)
    project_count = len(extraction.projects)
    education_count = len(extraction.education)
    evidence_count = len(extraction.evidence_notes)
    skills_count = len(extraction.skills)
    tools_count = len(extraction.tools_and_platforms)
    certification_count = len(extraction.certifications)

    if not has_current_employer and not has_current_title:
        score -= 30
        reasons.append("missing_current_employer_and_title")
    else:
        if not has_current_employer:
            score -= 15
            reasons.append("missing_current_employer")
        if not has_current_title:
            score -= 15
            reasons.append("missing_current_title")

    if extraction.professional_summary is None or extraction.professional_summary.strip() == "":
        score -= 8
        reasons.append("missing_professional_summary")

    if source_hints["resume_email_count"] > 0:
        if email_count == 0:
            score -= 25
            reasons.append("missing_emails_despite_resume_hint")
        elif email_count < source_hints["resume_email_count"]:
            score -= 10
            reasons.append("email_count_lower_than_resume_hint")

    if source_hints["resume_phone_count"] > 0:
        if phone_count == 0:
            score -= 20
            reasons.append("missing_phones_despite_resume_hint")
        elif phone_count < source_hints["resume_phone_count"]:
            score -= 8
            reasons.append("phone_count_lower_than_resume_hint")

    if employment_count == 0:
        score -= 35
        reasons.append("employment_history_empty")

    if source_hints["has_projects_section"] and project_count == 0:
        score -= 15
        reasons.append("projects_empty_despite_projects_section")

    if source_hints["has_education_section"] and education_count == 0:
        score -= 12
        reasons.append("education_empty_despite_education_section")

    if source_hints["has_certifications_section"] and certification_count == 0:
        score -= 5
        reasons.append("certifications_empty_despite_certifications_section")

    if evidence_count == 0:
        score -= 10
        reasons.append("evidence_notes_empty")
    elif evidence_count < 2:
        score -= 5
        reasons.append("evidence_notes_thin")

    if skills_count == 0 and tools_count == 0:
        score -= 10
        reasons.append("skills_and_tools_empty")

    if _all_employment_summaries_empty(extraction):
        score -= 12
        reasons.append("employment_summaries_empty")

    empty_project_detail_count = sum(
        1
        for project in extraction.projects
        if (
            not project.responsibilities
            and not project.deliverables
            and not project.business_outcomes
        )
    )
    if empty_project_detail_count > 0:
        score -= 8 * empty_project_detail_count
        reasons.append("project_details_empty")

    if source_hints["resume_contains_bp"] and not _output_mentions_bp(extraction):
        score -= 12
        reasons.append("bp_missing_despite_resume_hint")

    duplicate_skill_count = _count_casefold_duplicates(extraction.skills)
    if duplicate_skill_count > 0:
        score -= 3
        reasons.append("duplicate_skills")

    duplicate_tool_count = _count_casefold_duplicates(extraction.tools_and_platforms)
    if duplicate_tool_count > 0:
        score -= 3
        reasons.append("duplicate_tools")

    if extraction.linkedin_url and not _looks_like_linkedin_url(extraction.linkedin_url):
        score -= 4
        reasons.append("malformed_linkedin_url")

    if any(not _looks_like_email(email) for email in extraction.emails):
        score -= 4
        reasons.append("malformed_email")

    if any(_digits_only_length(phone) < 10 for phone in extraction.phones):
        score -= 3
        reasons.append("suspicious_phone_format")

    suspicious_terms_present = _find_suspicious_terms_in_output(extraction)
    if suspicious_terms_present:
        score -= 8
        reasons.append("suspicious_note_only_terms_in_output")

    score = max(0, min(100, score))

    if score >= pass_threshold:
        status: Literal["pass", "review", "rerun"] = "pass"
    elif score >= rerun_threshold:
        status = "review"
    else:
        status = "rerun"

    check_results = {
        "has_current_employer": has_current_employer,
        "has_current_title": has_current_title,
        "email_count": email_count,
        "phone_count": phone_count,
        "employment_history_count": employment_count,
        "projects_count": project_count,
        "education_count": education_count,
        "evidence_notes_count": evidence_count,
        "skills_count": skills_count,
        "tools_and_platforms_count": tools_count,
        "certifications_count": certification_count,
        "empty_project_detail_count": empty_project_detail_count,
        "duplicate_skill_count": duplicate_skill_count,
        "duplicate_tool_count": duplicate_tool_count,
        "suspicious_terms_present": suspicious_terms_present,
    }

    return ExtractionQualityAssessment(
        quality_score=score,
        status=status,
        reasons=_deduplicate_preserving_order(reasons),
        source_hints=source_hints,
        check_results=check_results,
    )


def assess_source_cv_richness(*, cleaned_resume_text: str) -> CVSourceAssessment:
    """
    Assess how rich or sparse the source CV text appears to be.

    Parameters
    ----------
    cleaned_resume_text : str
        Cleaned resume text used for extraction.

    Returns
    -------
    CVSourceAssessment
        Advisory source-document richness assessment.

    Notes
    -----
    This helper answers a different question from `score_resume_extraction`.
    It is not asking:

        "Did the extractor behave well?"

    It is asking:

        "How much recruiter-useful signal did the source CV itself contain?"

    That distinction matters because a sparse CV may still be extracted
    correctly and should not automatically be treated as an extraction failure.

    Example
    -------
    A one-page CV with:

        - one email
        - three role titles
        - almost no descriptive prose

    may still yield a `richness_band="sparse"` even if the extraction quality
    score later comes back as `pass`.
    """

    source_hints = _build_source_hints(cleaned_resume_text)
    score = 100
    reasons: list[str] = []

    character_count = len(cleaned_resume_text)
    word_count = len(re.findall(r"\b\w+\b", cleaned_resume_text))
    nonempty_lines = [
        line.strip()
        for line in cleaned_resume_text.splitlines()
        if line.strip() != ""
    ]
    date_range_count = len(_DATE_RANGE_PATTERN.findall(cleaned_resume_text))
    substantial_line_count = sum(
        1 for line in nonempty_lines if len(re.findall(r"\b\w+\b", line)) >= 8
    )
    bullet_like_line_count = sum(
        1
        for line in nonempty_lines
        if line.startswith(("-", "*", "•")) or "•" in line
    )

    if character_count < 500:
        score -= 30
        reasons.append("short_resume_text")
    elif character_count < 1200:
        score -= 15
        reasons.append("limited_resume_text")

    if word_count < 90:
        score -= 25
        reasons.append("low_word_count")
    elif word_count < 220:
        score -= 10
        reasons.append("moderate_word_count")

    if date_range_count == 0:
        score -= 25
        reasons.append("no_employment_signals")
    elif date_range_count == 1:
        score -= 12
        reasons.append("limited_employment_signals")

    if substantial_line_count < 4:
        score -= 15
        reasons.append("limited_descriptive_content")
    elif substantial_line_count < 8:
        score -= 8
        reasons.append("moderate_descriptive_content")

    if bullet_like_line_count == 0:
        score -= 4
        reasons.append("no_bullet_like_content")

    if not source_hints["has_skills_section"]:
        score -= 8
        reasons.append("no_explicit_skills_section")

    if not source_hints["has_projects_section"]:
        score -= 4
        reasons.append("no_explicit_projects_section")

    if not source_hints["has_education_section"]:
        score -= 6
        reasons.append("no_explicit_education_section")

    if source_hints["resume_email_count"] == 0:
        score -= 12
        reasons.append("missing_email_contact")

    if source_hints["resume_phone_count"] == 0:
        score -= 4
        reasons.append("missing_phone_contact")

    score = max(0, min(100, score))

    if score >= 80:
        richness_band: Literal["rich", "adequate", "sparse", "very_sparse"] = "rich"
    elif score >= 55:
        richness_band = "adequate"
    elif score >= 30:
        richness_band = "sparse"
    else:
        richness_band = "very_sparse"

    source_metrics = {
        "character_count": character_count,
        "word_count": word_count,
        "nonempty_line_count": len(nonempty_lines),
        "substantial_line_count": substantial_line_count,
        "bullet_like_line_count": bullet_like_line_count,
        "employment_signal_count": date_range_count,
        "resume_email_count": source_hints["resume_email_count"],
        "resume_phone_count": source_hints["resume_phone_count"],
        "has_experience_section": source_hints["has_experience_section"],
        "has_education_section": source_hints["has_education_section"],
        "has_skills_section": source_hints["has_skills_section"],
        "has_projects_section": source_hints["has_projects_section"],
        "has_certifications_section": source_hints["has_certifications_section"],
    }

    return CVSourceAssessment(
        richness_score=score,
        richness_band=richness_band,
        reasons=_deduplicate_preserving_order(reasons),
        source_metrics=source_metrics,
    )


def _build_source_hints(cleaned_resume_text: str) -> dict[str, Any]:
    """
    Build simple deterministic hints from cleaned resume text.

    Notes
    -----
    These hints are deliberately lightweight. They do not try to parse the CV
    fully. They only extract enough signal to ask useful questions such as:

    - does the resume appear to contain two emails?
    - does the resume appear to contain a projects section?
    - does the resume mention BP anywhere?

    Example
    -------
    The returned dictionary may contain:

        {
            "resume_email_count": 2,
            "resume_phone_count": 1,
            "has_experience_section": True,
            "has_projects_section": True,
            "resume_contains_bp": True,
        }
    """

    emails = _deduplicate_preserving_order(_EMAIL_PATTERN.findall(cleaned_resume_text))
    phones = _extract_phone_hints(cleaned_resume_text)
    lowered_text = cleaned_resume_text.casefold()

    return {
        "resume_email_count": len(emails),
        "resume_phone_count": len(phones),
        "resume_emails": emails,
        "resume_phones": phones,
        "has_experience_section": _section_present(lowered_text, _SECTION_PATTERNS["experience"]),
        "has_education_section": _section_present(lowered_text, _SECTION_PATTERNS["education"]),
        "has_skills_section": _section_present(lowered_text, _SECTION_PATTERNS["skills"]),
        "has_certifications_section": _section_present(lowered_text, _SECTION_PATTERNS["certifications"]),
        "has_projects_section": _section_present(lowered_text, _SECTION_PATTERNS["projects"])
        or _section_present(lowered_text, _SECTION_PATTERNS["portfolio"]),
        "resume_contains_bp": bool(re.search(r"\bbp\b", cleaned_resume_text, re.IGNORECASE)),
    }


def _extract_phone_hints(text: str) -> list[str]:
    """
    Extract likely phone-number strings from resume text conservatively.

    Notes
    -----
    - This helper is intentionally permissive about formatting.
    - It is only trying to derive a count/sanity hint, not canonicalize the
      final stored phone format.
    - It explicitly rejects date-range lookalikes such as:
        - `01.2021- 04.2022`
        - `06.2023- currently`

    Example
    -------
    A source line like:

        `Tel.: +4474-935-89091`

    should be counted as a phone hint, while a work-history line like:

        `01.2021- 04.2022`

    should not.
    """

    phone_candidates = _PHONE_CANDIDATE_PATTERN.findall(text)
    filtered: list[str] = []

    for candidate in phone_candidates:
        digit_count = _digits_only_length(candidate)
        if digit_count < 10 or digit_count > 16:
            continue
        if _looks_like_date_rangeish_phone_false_positive(candidate):
            continue
        filtered.append(candidate.strip())

    return _deduplicate_preserving_order(filtered)


def _section_present(lowered_text: str, patterns: tuple[str, ...]) -> bool:
    """
    Return whether any section-marker string appears in lowered resume text.

    Parameters
    ----------
    lowered_text : str
        Resume text already converted to lowercase.

    patterns : tuple[str, ...]
        Lowercase or case-insensitive-compatible section labels to search for.

    Returns
    -------
    bool
        `True` when any pattern is present, otherwise `False`.

    Notes
    -----
    This helper intentionally uses simple substring checks rather than trying
    to parse full document structure. At this stage the goal is just to derive
    cheap routing hints such as:

    - "does the CV appear to have an education section?"
    - "does the CV appear to have projects or portfolio content?"

    Example
    -------
    A call like:

        _section_present("experience\\neducation\\nprojects", ("projects",))

    returns `True`.
    """

    return any(pattern.casefold() in lowered_text for pattern in patterns)


def _all_employment_summaries_empty(extraction: ResumeStructuredExtraction) -> bool:
    """
    Return whether every employment entry has an empty or missing summary.
    """

    if not extraction.employment_history:
        return False

    return all(
        job.summary is None or job.summary.strip() == ""
        for job in extraction.employment_history
    )


def _output_mentions_bp(extraction: ResumeStructuredExtraction) -> bool:
    """
    Return whether the structured output still preserves BP evidence somewhere.

    Notes
    -----
    BP is used here as a deliberately narrow source-hint check because it is
    a strong known prior-employment signal in the live candidate we have been
    tuning against.
    """

    for job in extraction.employment_history:
        if job.employer and "bp" in job.employer.casefold():
            return True

    for project in extraction.projects:
        if project.employer and "bp" in project.employer.casefold():
            return True
        if project.name and "bp" in project.name.casefold():
            return True
        if any("bp" in value.casefold() for value in project.domains):
            return True

    return False


def _count_casefold_duplicates(values: list[str]) -> int:
    """
    Count duplicate strings case-insensitively while ignoring empties.
    """

    seen: set[str] = set()
    duplicates = 0

    for value in values:
        key = value.strip().casefold()
        if key == "":
            continue
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)

    return duplicates


def _looks_like_linkedin_url(value: str) -> bool:
    """
    Return whether one value looks like a LinkedIn profile URL.

    Notes
    -----
    Recruiter exports and compact CV headers often omit the URL scheme and use
    forms such as:

    - `linkedin.com/in/drougas`
    - `www.linkedin.com/in/roger-campbell/`

    Those are still valid enough for extraction quality purposes, so this
    helper normalizes away an optional scheme and `www.` prefix before it
    checks the core path shape.

    Example
    -------
    All of the following should be accepted:

        https://www.linkedin.com/in/roger-campbell/
        http://www.linkedin.com/in/roger-campbell/
        linkedin.com/in/roger-campbell/
    """

    lowered = value.strip().casefold()

    if lowered.startswith("https://"):
        lowered = lowered[len("https://") :]
    elif lowered.startswith("http://"):
        lowered = lowered[len("http://") :]

    if lowered.startswith("www."):
        lowered = lowered[len("www.") :]

    return lowered.startswith("linkedin.com/in/")


def _looks_like_email(value: str) -> bool:
    """
    Return whether one value looks like a valid email address.
    """

    return bool(_EMAIL_PATTERN.fullmatch(value.strip()))


def _digits_only_length(value: str) -> int:
    """
    Return the number of digits in a phone-like value.
    """

    return len(re.sub(r"\D", "", value))


def _looks_like_date_rangeish_phone_false_positive(value: str) -> bool:
    """
    Return whether a phone-like candidate is actually a work-history date range.

    Parameters
    ----------
    value : str
        Phone-like candidate string produced by the broad phone regex.

    Returns
    -------
    bool
        `True` when the candidate looks more like a date range than a phone
        number.

    Notes
    -----
    The phone-hint regex is intentionally broad because real CVs use many
    phone-number formats. The tradeoff is that role date ranges can sometimes
    look phone-like. This helper is the second-stage filter that removes
    obvious false positives such as:

    - `01.2021- 04.2022`
    - `06.2023- currently`
    - `2011-12 - 2016-11`

    Example
    -------
    A value like:

        `+4474-935-89091`

    returns `False`, while:

        `01.2021- 04.2022`

    returns `True`.
    """

    stripped = value.strip()

    if _DATE_RANGE_PATTERN.search(stripped):
        return True

    return bool(
        re.search(
            r"\b(?:\d{1,2}[./-]\d{4}|\d{4}[./-]\d{1,2})\s*[-–—]\s*(?:\d{1,2}[./-]\d{4}|\d{4}[./-]\d{1,2}|current(?:ly)?|present)\b",
            stripped,
            re.IGNORECASE,
        )
    )


def _find_suspicious_terms_in_output(extraction: ResumeStructuredExtraction) -> list[str]:
    """
    Return suspicious note-only tooling terms that leaked into final fields.

    Notes
    -----
    This is intentionally a narrow heuristic for known contamination patterns,
    not a general profanity/junk filter.
    """

    haystacks: list[str] = []
    haystacks.extend(extraction.skills)
    haystacks.extend(extraction.tools_and_platforms)
    haystacks.extend(extraction.certifications)
    haystacks.extend(extraction.portfolio_references)

    found: list[str] = []
    for value in haystacks:
        lowered = value.casefold()
        for term in _SUSPICIOUS_NOTE_ONLY_TERMS:
            if term in lowered:
                found.append(term)

    return _deduplicate_preserving_order(found)


def _deduplicate_preserving_order(values: list[str]) -> list[str]:
    """
    Deduplicate strings while preserving first-seen order.
    """

    seen: set[str] = set()
    deduplicated: list[str] = []

    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(value)

    return deduplicated


__all__ = [
    "CVSourceAssessment",
    "ExtractionQualityAssessment",
    "assess_source_cv_richness",
    "score_resume_extraction",
]
