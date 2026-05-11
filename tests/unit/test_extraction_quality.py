"""
Unit tests for deterministic extraction-quality and source-CV assessments.

Why this module exists
----------------------
The scorer layer now answers two separate questions:

- did the extraction pipeline produce a structurally credible result?
- how rich or sparse was the source CV itself?

Those are easy to conflate in conversation, so the tests pin them separately.

What these tests cover
----------------------
This module checks that the scorer behaves sensibly for a few deliberately
chosen shapes:

- strong extraction from a solid CV
- collapsed extraction that should rerun
- thin but not broken extraction that should review
- rich source CV text
- sparse source CV text

In plain language:

- prove the scorer can tell bad extraction from sparse source material
- keep routing logic and advisory source scoring from drifting together
"""

from __future__ import annotations

from backend.services.extraction_quality import (
    assess_source_cv_richness,
    score_resume_extraction,
)
from backend.services.resume_extraction import ResumeStructuredExtraction


def _build_strong_extraction() -> ResumeStructuredExtraction:
    """
    Build one high-signal extraction fixture for scorer tests.

    Notes
    -----
    This fixture is intentionally richer than the minimal schema. It includes:

    - current role data
    - multiple contact methods
    - projects
    - tools
    - education
    - evidence notes

    so the tests can subtract one dimension at a time without rebuilding the
    whole object inline each time.
    """

    return ResumeStructuredExtraction.model_validate(
        {
            "current_employer": "Ch3rry Pi3 Ltd",
            "current_title": "Co-Founder & AI/ML Consultant",
            "professional_summary": "Applied AI and machine learning consultant.",
            "location": None,
            "emails": ["the_rfc@hotmail.co.uk", "roger@ch3rry-pi3.com"],
            "phones": ["07934 890 708"],
            "skills": ["Machine Learning", "Applied Econometrics"],
            "tools_and_platforms": ["Python", "Azure ML", "Power BI"],
            "certifications": ["Cloud Essentials+"],
            "linkedin_url": "https://www.linkedin.com/in/roger-campbell/",
            "portfolio_references": [],
            "education": [
                {
                    "institution": "University of Birmingham",
                    "qualification": "BSc",
                    "subject": "Economics",
                    "completion_date": "2017",
                }
            ],
            "employment_history": [
                {
                    "employer": "Ch3rry Pi3 Ltd",
                    "title": "Co-Founder & AI/ML Consultant",
                    "start_date": "2025",
                    "end_date": None,
                    "is_current": True,
                    "summary": "Building applied AI products.",
                },
                {
                    "employer": "BP (via Grayce & Harvey Nash)",
                    "title": "Senior Data Scientist",
                    "start_date": "2022",
                    "end_date": "2025",
                    "is_current": False,
                    "summary": "Delivered production optimisation ML work.",
                },
            ],
            "projects": [
                {
                    "name": "GP AI Assistant",
                    "employer": "Ch3rry Pi3 Ltd",
                    "role": "Co-Founder & AI/ML Consultant",
                    "summary": "Clinical decision-support assistant.",
                    "responsibilities": ["End-to-end system design"],
                    "deliverables": ["Web-based assistant"],
                    "business_outcomes": [],
                    "tools_and_platforms": [],
                    "domains": ["Healthcare", "AI"],
                },
                {
                    "name": "Production optimisation ML initiatives",
                    "employer": "BP (via Grayce & Harvey Nash)",
                    "role": "Senior Data Scientist",
                    "summary": "Built ML workflows for production optimisation.",
                    "responsibilities": ["Led ML delivery across six initiatives"],
                    "deliverables": ["Forecasting models"],
                    "business_outcomes": ["Delivered multi-million-dollar efficiency gains"],
                    "tools_and_platforms": ["Azure Databricks", "Python"],
                    "domains": ["Energy", "Forecasting"],
                },
            ],
            "evidence_notes": [
                "Resume contact block contains two emails and one phone number.",
                "Resume BP role bullets support production optimisation work.",
            ],
            "ambiguity_notes": [],
        }
    )


def test_score_resume_extraction_passes_strong_output() -> None:
    """
    Verify that a strong extraction with matching source hints passes cleanly.

    In plain language:

    - feed the scorer a good structured result
    - give it source text that supports the core extracted fields
    - confirm it does not invent problems
    """

    extraction = _build_strong_extraction()
    cleaned_resume_text = """
Roger Campbell
the_rfc@hotmail.co.uk
roger@ch3rry-pi3.com
07934 890 708

Experience
BP (via Grayce & Harvey Nash)

Projects
GP AI Assistant

Education
BSc Economics

Certifications
Cloud Essentials+
""".strip()

    assessment = score_resume_extraction(
        extraction=extraction,
        cleaned_resume_text=cleaned_resume_text,
    )

    assert assessment.status == "pass"
    assert assessment.quality_score >= 80
    assert assessment.reasons == []


def test_score_resume_extraction_requests_rerun_for_collapsed_output() -> None:
    """
    Verify that an obviously collapsed extraction is routed to rerun.

    In plain language:

    - strip out the core fields
    - keep the source CV hints intact
    - confirm the scorer treats this as a bad extraction, not a sparse CV
    """

    extraction = ResumeStructuredExtraction.model_validate(
        {
            "current_employer": None,
            "current_title": None,
            "professional_summary": None,
            "location": None,
            "emails": [],
            "phones": [],
            "skills": [],
            "tools_and_platforms": [],
            "certifications": [],
            "linkedin_url": None,
            "portfolio_references": [],
            "education": [],
            "employment_history": [],
            "projects": [],
            "evidence_notes": [],
            "ambiguity_notes": [],
        }
    )
    cleaned_resume_text = """
Roger Campbell
the_rfc@hotmail.co.uk
roger@ch3rry-pi3.com
07934 890 708

Experience
BP (via Grayce & Harvey Nash)

Projects
Production optimisation ML initiatives

Education
BSc Economics

Certifications
Cloud Essentials+
""".strip()

    assessment = score_resume_extraction(
        extraction=extraction,
        cleaned_resume_text=cleaned_resume_text,
    )

    assert assessment.status == "rerun"
    assert assessment.quality_score < 65
    assert "missing_current_employer_and_title" in assessment.reasons
    assert "missing_emails_despite_resume_hint" in assessment.reasons
    assert "employment_history_empty" in assessment.reasons
    assert "projects_empty_despite_projects_section" in assessment.reasons
    assert "bp_missing_despite_resume_hint" in assessment.reasons


def test_score_resume_extraction_flags_suspicious_output_pollution() -> None:
    """
    Verify that known note-only contamination terms are penalised.

    Notes
    -----
    This is a narrow regression test for the exact class of leakage we saw in
    earlier Nemotron/OpenRouter experiments.
    """

    extraction = _build_strong_extraction().model_copy(
        update={
            "tools_and_platforms": [
                "Python",
                "OpenRouter",
                "Nemotron",
            ]
        }
    )

    assessment = score_resume_extraction(
        extraction=extraction,
        cleaned_resume_text="Roger Campbell\nthe_rfc@hotmail.co.uk\n07934 890 708\nExperience",
    )

    assert "suspicious_note_only_terms_in_output" in assessment.reasons
    assert "openrouter" in assessment.check_results["suspicious_terms_present"]
    assert "nemotron" in assessment.check_results["suspicious_terms_present"]


def test_score_resume_extraction_accepts_scheme_less_linkedin_profile_url() -> None:
    """
    Verify that a scheme-less LinkedIn profile URL is treated as acceptable.

    Notes
    -----
    Real recruiter exports often present LinkedIn URLs in compact forms such
    as `linkedin.com/in/...` without `https://`. That should not be penalised
    as malformed when the profile path itself is clear.
    """

    extraction = _build_strong_extraction().model_copy(
        update={
            "linkedin_url": "linkedin.com/in/roger-campbell/",
        }
    )

    assessment = score_resume_extraction(
        extraction=extraction,
        cleaned_resume_text="Roger Campbell\nlinkedin.com/in/roger-campbell/\nExperience",
    )

    assert "malformed_linkedin_url" not in assessment.reasons


def test_score_resume_extraction_reviews_thin_but_not_broken_output() -> None:
    """
    Verify that a weakened but still coherent extraction lands in review.

    In plain language:

    - remove some contact fidelity and evidence depth
    - keep the extraction otherwise usable
    - confirm the scorer distinguishes "thin" from "collapsed"
    """

    extraction = _build_strong_extraction().model_copy(
        update={
            "emails": ["the_rfc@hotmail.co.uk"],
            "phones": [],
            "evidence_notes": ["Resume headline supports current title."],
        }
    )
    cleaned_resume_text = """
Roger Campbell
the_rfc@hotmail.co.uk
roger@ch3rry-pi3.com
07934 890 708
Experience
Projects
Education
""".strip()

    assessment = score_resume_extraction(
        extraction=extraction,
        cleaned_resume_text=cleaned_resume_text,
    )

    assert assessment.status == "review"
    assert 65 <= assessment.quality_score < 80
    assert "email_count_lower_than_resume_hint" in assessment.reasons
    assert "missing_phones_despite_resume_hint" in assessment.reasons
    assert "evidence_notes_thin" in assessment.reasons


def test_assess_source_cv_richness_treats_work_history_as_experience_signal() -> None:
    """
    Verify that `Work History` is recognised as an experience-section variant.

    Notes
    -----
    The live calibration batch included LinkedIn-style one-page CVs that used
    `Work History` rather than `Experience`. This test protects that broader
    section-heading coverage.
    """

    cleaned_resume_text = """
Yannis Drougas
Senior Software Engineer
London area
linkedin.com/in/drougas

Work History
Senior Software Engineer
Crypto Trading Firm
Jun 2023 - Present

Education
University of California, Riverside
    """.strip()

    assessment = assess_source_cv_richness(
        cleaned_resume_text=cleaned_resume_text,
    )

    assert assessment.source_metrics["has_experience_section"] is True


def test_assess_source_cv_richness_does_not_count_date_ranges_as_phone_hints() -> None:
    """
    Verify that month-year role ranges do not inflate phone-hint counts.

    Notes
    -----
    This pins the specific regression we saw in the Taras CV, where strings
    like `01.2021- 04.2022` were being mistaken for phone numbers by the
    source-hint layer. It also covers the LinkedIn/CV export style:

    - `2011-12 - 2016-11`
    """

    cleaned_resume_text = """
Maliarchuk Taras
Tel.: +4474-935-89091
E-mail: maliarchuk@gmail.com

Software development experience
Senior Software Development Engineer
Tacans Labs
06.2023- currently

Senior Software Development Engineer
Digitex
01.2021- 04.2022

Analyst
Legacy Firm
2011-12 - 2016-11
    """.strip()

    assessment = assess_source_cv_richness(
        cleaned_resume_text=cleaned_resume_text,
    )

    assert assessment.source_metrics["resume_phone_count"] == 1
    assert assessment.source_metrics["employment_signal_count"] >= 2


def test_assess_source_cv_richness_scores_richer_cv_as_adequate_or_better() -> None:
    """
    Verify that a richer multi-role CV text scores as adequate or better.

    Notes
    -----
    This is not trying to prove the scorer can identify a perfect CV.
    It is only pinning the more important boundary:

    - this source is clearly richer than a one-page title-only CV
    - it should not be labelled sparse
    """

    cleaned_resume_text = """
Roger Campbell
the_rfc@hotmail.co.uk
roger@ch3rry-pi3.com
07934 890 708

Experience
Ch3rry Pi3 Ltd
2025 - Present
Co-founded and built applied AI systems for recruitment and healthcare workflows.
Led end-to-end solution design, delivery, and stakeholder communication across product and engineering workstreams.

BP (via Grayce & Harvey Nash)
2022 - 2025
Delivered production optimisation initiatives and forecasting models with measurable business impact.
Worked across forecasting, optimisation, and deployment workflows in close collaboration with operational stakeholders.

Grayce
2021 - 2022
Delivered analytics and machine learning workstreams across client-facing projects with a focus on reproducibility and evidence quality.

Jaguar Land Rover
2018 - 2021
Built data science and econometric analysis deliverables for commercial and operational decision-making use cases.

Projects
GP AI Assistant
AI Recruitment Platform
Machine Learning eBook

Skills
Machine Learning
Applied Econometrics
Python
Azure ML
Power BI

Education
BSc Economics
MSc Data Science
    """.strip()

    assessment = assess_source_cv_richness(
        cleaned_resume_text=cleaned_resume_text,
    )

    assert assessment.richness_score >= 55
    assert assessment.richness_band in {"adequate", "rich"}
    assert assessment.source_metrics["has_skills_section"] is True
    assert assessment.source_metrics["has_projects_section"] is True


def test_assess_source_cv_richness_flags_sparse_one_page_cv() -> None:
    """
    Verify that a short one-page CV is treated as sparse source material.

    In plain language:

    - the source is thin
    - that should be reflected in the advisory source score
    - but it should remain a separate concept from extraction failure
    """

    cleaned_resume_text = """
Aric Kuter
Software Engineer
London area
arickuter99@gmail.com

Work History
Software Engineer
Blockchain.com
Apr 2022 - Present

Programmer: Test Automation
Capitec Bank
Jan 2020 - Apr 2022

Education
Udacity
2019 - 2020
""".strip()

    assessment = assess_source_cv_richness(
        cleaned_resume_text=cleaned_resume_text,
    )

    assert assessment.richness_band in {"sparse", "very_sparse"}
    assert "short_resume_text" in assessment.reasons or "limited_resume_text" in assessment.reasons
    assert assessment.source_metrics["has_projects_section"] is False
