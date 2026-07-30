"""Tests for recruiter-ready shortlist export packages."""

from io import BytesIO
import json
from unittest.mock import patch
from zipfile import ZipFile

from backend.services.candidate_resume_files import CandidateResumeFileAccessError
from backend.services.candidate_shortlist_export import (
    build_candidate_shortlist_export_package,
)


def _shortlist_candidate(
    *,
    candidate_id: str,
    full_name: str,
    fit_score: int,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "full_name": full_name,
        "current_title": "Financial Systems Analyst",
        "current_company_name": "Example Bank",
        "document_title": f"{full_name} CV.pdf",
        "retrieval_score": 0.91234,
        "fit_score": fit_score,
        "fit_summary": "Strong evidence across the principal role requirements.",
        "strengths": ["IBM Planning Analytics", "Financial reporting"],
        "gaps": ["Insurance experience is not explicit"],
    }


def test_shortlist_export_builds_word_report_and_retrievable_cv_files() -> None:
    """The package should remain useful when one shortlisted CV is unavailable."""

    candidates = [
        _shortlist_candidate(
            candidate_id="candidate-1",
            full_name="Sarah Jones",
            fit_score=94,
        ),
        _shortlist_candidate(
            candidate_id="candidate-2",
            full_name="Ari Smith",
            fit_score=88,
        ),
    ]

    def fetch_resume(candidate_id: str) -> dict[str, object]:
        if candidate_id == "candidate-2":
            raise CandidateResumeFileAccessError(
                "Current resume source is unavailable.",
                code="resume_source_unavailable",
                status_code=501,
            )
        return {
            "candidate_id": candidate_id,
            "document_id": "document-1",
            "file_name": "Sarah original.pdf",
            "content_type": "application/pdf",
            "content_bytes": b"%PDF-test%",
        }

    with patch(
        "backend.services.candidate_shortlist_export.fetch_candidate_current_resume_file",
        side_effect=fetch_resume,
    ):
        package = build_candidate_shortlist_export_package(
            match_run_id="61b18a15-0ca1-42c6-80c2-4800b002c17b",
            role_title="Financial Systems Analyst.pdf",
            job_description="Financial systems analyst with TM1 experience.",
            shortlisted_candidates=candidates,
        )

    assert package["file_name"] == (
        "Shortlist package - Financial Systems Analyst.zip"
    )
    assert package["exported_cv_count"] == 1
    assert package["unavailable_cv_count"] == 1

    with ZipFile(BytesIO(package["content_bytes"])) as export_zip:
        export_names = export_zip.namelist()
        assert "Shortlist - Financial Systems Analyst.docx" in export_names
        assert "CVs/01 - Sarah Jones.pdf" in export_names
        assert export_zip.read("CVs/01 - Sarah Jones.pdf") == b"%PDF-test%"

        manifest = json.loads(export_zip.read("export-manifest.json"))
        assert manifest["shortlisted_candidate_count"] == 2
        assert manifest["exported_cv_count"] == 1
        assert manifest["unavailable_cv_count"] == 1
        assert manifest["unavailable_resumes"] == [
            {
                "candidate_id": "candidate-2",
                "candidate_name": "Ari Smith",
                "reason": "Current resume source is unavailable.",
            }
        ]

        with ZipFile(
            BytesIO(
                export_zip.read("Shortlist - Financial Systems Analyst.docx")
            )
        ) as report_docx:
            document_xml = report_docx.read("word/document.xml").decode("utf-8")

    assert "Recruiter Shortlist" in document_xml
    assert "Sarah Jones" in document_xml
    assert "Ari Smith" in document_xml
    assert "IBM Planning Analytics" in document_xml
    assert "Insurance experience is not explicit" in document_xml

