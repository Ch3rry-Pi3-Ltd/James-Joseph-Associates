"""
Unit tests for heuristic Outlook CV attachment export helpers.
"""

from backend.services.outlook_cv_attachment_export import (
    assess_outlook_attachment_support,
    score_resume_likeness,
)


def test_assess_outlook_attachment_support_accepts_supported_resume_file() -> None:
    """Verify that a standard PDF file attachment is considered processable."""

    result = assess_outlook_attachment_support(
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": "Jane Doe CV.pdf",
            "contentType": "application/pdf",
        }
    )

    assert result == {
        "is_supported": True,
        "reason": "supported_file_suffix",
    }


def test_assess_outlook_attachment_support_rejects_non_file_attachment() -> None:
    """Verify that non-file Outlook attachments are rejected early."""

    result = assess_outlook_attachment_support(
        {
            "@odata.type": "#microsoft.graph.itemAttachment",
            "name": "forwarded.eml",
            "contentType": "message/rfc822",
        }
    )

    assert result == {
        "is_supported": False,
        "reason": "unsupported_attachment_type",
    }


def test_score_resume_likeness_accepts_structured_cv_text() -> None:
    """Verify that structured CV text clears the heuristic threshold."""

    cleaned_text = """
    Jane Doe
    jane.doe@example.com
    +44 7700 900123
    linkedin.com/in/janedoe

    Professional Summary
    Senior Data Engineer with Python, SQL, ETL, and AWS experience.

    Experience
    Data Engineer, Example Bank, 2022
    Senior Analyst, Example Capital, 2020

    Education
    BSc Computer Science

    Skills
    Python, SQL, AWS, ETL, Airflow
    """

    result = score_resume_likeness(
        file_name="Jane-Doe-CV.pdf",
        content_type="application/pdf",
        cleaned_text=cleaned_text,
    )

    assert result["is_resume_like"] is True
    assert result["score"] >= 5
    assert "email_present" in result["positive_signals"]
    assert "phone_present" in result["positive_signals"]


def test_score_resume_likeness_rejects_non_cv_business_document() -> None:
    """Verify that obvious non-CV business paperwork is rejected."""

    cleaned_text = """
    Invoice 10492
    Purchase Order
    Terms and Conditions
    Receipt for services rendered
    """

    result = score_resume_likeness(
        file_name="invoice.pdf",
        content_type="application/pdf",
        cleaned_text=cleaned_text,
    )

    assert result["is_resume_like"] is False
    assert len(result["negative_signals"]) >= 1
