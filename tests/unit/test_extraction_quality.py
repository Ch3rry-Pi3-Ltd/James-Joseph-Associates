"""
Unit tests for deterministic resume-extraction quality scoring.
"""

from __future__ import annotations

from backend.services.extraction_quality import score_resume_extraction
from backend.services.resume_extraction import ResumeStructuredExtraction


def _build_strong_extraction() -> ResumeStructuredExtraction:
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


def test_score_resume_extraction_reviews_thin_but_not_broken_output() -> None:
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
