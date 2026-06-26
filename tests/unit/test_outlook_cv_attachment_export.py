"""
Unit tests for heuristic Outlook CV attachment export helpers.
"""

from backend.services.outlook_cv_attachment_export import (
    assess_outlook_attachment_support,
    run_outlook_cv_attachment_export,
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


def test_score_resume_likeness_rejects_generic_long_pdf_without_personal_signals() -> None:
    """Verify that handbook-like PDFs do not pass purely on structure and length."""

    cleaned_text = """
    Asana Help Articles

    Education
    Certifications
    Projects

    2021 Product updates
    2022 Workflow changes
    2023 Admin improvements
    2024 Enterprise rollout

    This document explains how teams should use tasks, projects, and reporting
    workflows across the business. It contains a large amount of descriptive
    platform guidance but no candidate contact details or personal profile.
    """ * 20

    result = score_resume_likeness(
        file_name="asana help articles.pdf",
        content_type="application/pdf",
        cleaned_text=cleaned_text,
    )

    assert result["is_resume_like"] is False
    assert result["career_structure_signal"] is True
    assert result["personal_identity_signal"] is False


def test_score_resume_likeness_rejects_energy_statement() -> None:
    """Verify that transactional household PDFs do not pass as resumes."""

    cleaned_text = """
    Octopus Energy Statement
    Account number: 12345678
    Opening balance: 120.44
    Closing balance: 95.10
    Payment due: 2026-06-23
    Meter reading
    Tariff
    Standing charge
    Unit rate
    Direct debit
    Usage summary
    Contact us at support@example.com
    020 7000 1234
    2024 2025 2026
    """ * 8

    result = score_resume_likeness(
        file_name="octopus-energy-statement-2026-06-23.pdf",
        content_type="application/pdf",
        cleaned_text=cleaned_text,
    )

    assert result["is_resume_like"] is False
    assert "statement" in result["negative_signals"]


def test_score_resume_likeness_rejects_recruitment_services_agreement() -> None:
    """Verify that agency terms paperwork does not pass as a CV."""

    cleaned_text = """
    James Joseph Associates
    Recruitment Services Agreement in respect of Fixed Term and Permanent Staff
    Agency Terms
    This agreement sets out the services, fees, notice periods, and
    responsibilities of both parties.
    Contact: operations@example.com
    Telephone: 020 7000 1234
    Employment business regulations 2023
    Candidate experience requirements and skills definitions may be referenced
    in the agreement text, but this is not a resume.
    Terms and conditions apply.
    """ * 10

    result = score_resume_likeness(
        file_name=(
            "James Joseph Associates - IQUW Recruitment Services Agreement in "
            "respect of Fixed Term and Permanent Staff.pdf"
        ),
        content_type="application/pdf",
        cleaned_text=cleaned_text,
    )

    assert result["is_resume_like"] is False
    assert "agreement" in result["negative_signals"]


def test_run_outlook_cv_attachment_export_records_unexpected_export_error(
    monkeypatch,
) -> None:
    """Verify one bad attachment does not crash the whole bounded export run."""

    monkeypatch.setattr(
        "backend.services.outlook_cv_attachment_export.fetch_outlook_messages",
        lambda **kwargs: {
            "messages": [
                {
                    "id": "message-1",
                    "subject": "Candidate CV",
                    "hasAttachments": True,
                    "receivedDateTime": "2022-01-18T20:15:47Z",
                }
            ],
            "received_from": None,
            "received_to": None,
        },
    )
    monkeypatch.setattr(
        "backend.services.outlook_cv_attachment_export.fetch_outlook_message_attachments",
        lambda **kwargs: {
            "attachments": [
                {
                    "id": "attachment-1",
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": "Jane Doe CV.pdf",
                    "contentType": "application/pdf",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "backend.services.outlook_cv_attachment_export.download_outlook_message_file_attachment",
        lambda **kwargs: {
            "content_bytes": b"pdf-bytes",
            "file_name": "Jane Doe CV.pdf",
            "content_type": "application/pdf",
        },
    )
    monkeypatch.setattr(
        "backend.services.outlook_cv_attachment_export.extract_text_from_resume_bytes",
        lambda **kwargs: {
            "text": (
                "Jane Doe jane.doe@example.com +44 7700 900123 "
                "linkedin.com/in/janedoe Experience 2022 2021 "
                "Skills Python SQL AWS " * 40
            )
        },
    )
    monkeypatch.setattr(
        "backend.services.outlook_cv_attachment_export.clean_resume_text",
        lambda text: text,
    )

    def _raise_upload_error(**kwargs):
        raise RuntimeError("simulated upload failure")

    monkeypatch.setattr(
        "backend.services.outlook_cv_attachment_export.upload_dropbox_file",
        _raise_upload_error,
    )

    result = run_outlook_cv_attachment_export(
        access_token="token",
        mailbox=None,
        folder_id="folder-1",
        folder_path=["Inbox"],
        message_limit=10,
        attachment_limit=10,
        dropbox_access_token="dropbox-token",
        dropbox_export_folder="/+++ Outlook CV Export",
        dry_run=False,
    )

    assert result["exported_count"] == 0
    assert result["failed_count"] == 1
    assert result["failed_items"][0]["stage"] == "attachment_classification_or_export"
    assert result["failed_items"][0]["error_type"] == "RuntimeError"
