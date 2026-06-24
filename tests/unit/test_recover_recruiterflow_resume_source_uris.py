from scripts.recover_recruiterflow_resume_source_uris import (
    ResumeRow,
    _normalized_text_hash,
    build_review_report,
    build_recovery_plan,
)


def _row(
    *,
    source_system: str,
    candidate_id: str,
    document_id: str,
    full_name: str | None,
    document_title: str | None,
    source_uri: str | None,
    extracted_text: str | None,
) -> ResumeRow:
    return ResumeRow(
        source_system=source_system,
        candidate_id=candidate_id,
        document_id=document_id,
        full_name=full_name,
        current_company_name=None,
        current_title=None,
        document_title=document_title,
        resume_updated_at=None,
        source_uri=source_uri,
        content_hash=None,
        extracted_text=extracted_text,
    )


def test_normalized_text_hash_ignores_case_and_whitespace() -> None:
    left = _normalized_text_hash("Senior Python Engineer\nSQL  AWS")
    right = _normalized_text_hash(" senior python engineer   sql aws ")

    assert left is not None
    assert left == right


def test_build_recovery_plan_prefers_same_candidate_exact_text_match() -> None:
    missing = _row(
        source_system="recruiterflow",
        candidate_id="cand-1",
        document_id="doc-rf-1",
        full_name="Alex Smith",
        document_title="Alex Smith CV.pdf",
        source_uri=None,
        extracted_text="Python SQL AWS",
    )
    dropbox_same_candidate = _row(
        source_system="dropbox",
        candidate_id="cand-1",
        document_id="doc-db-1",
        full_name="Alex Smith",
        document_title="Alex Smith CV.pdf",
        source_uri="dropbox:///alex.pdf",
        extracted_text="python   sql aws",
    )
    dropbox_other_candidate = _row(
        source_system="dropbox",
        candidate_id="cand-2",
        document_id="doc-db-2",
        full_name="Alex Smith",
        document_title="Alex Smith CV.pdf",
        source_uri="dropbox:///alex-copy.pdf",
        extracted_text="python sql aws",
    )

    plan = build_recovery_plan(
        missing_rows=[missing],
        dropbox_rows=[dropbox_same_candidate, dropbox_other_candidate],
    )

    assert len(plan["exact_text_recoveries"]) == 1
    recovery = plan["exact_text_recoveries"][0]
    assert recovery["matched_candidate_id"] == "cand-1"
    assert recovery["matched_source_uri"] == "dropbox:///alex.pdf"
    assert recovery["strategy"] == "exact_normalized_text_same_candidate"


def test_build_recovery_plan_reports_review_match_on_title_and_name() -> None:
    missing = _row(
        source_system="recruiterflow",
        candidate_id="cand-rf",
        document_id="doc-rf-2",
        full_name="Priya Nair",
        document_title="Priya Nair CV.docx",
        source_uri=None,
        extracted_text=None,
    )
    dropbox = _row(
        source_system="dropbox",
        candidate_id="cand-db",
        document_id="doc-db-3",
        full_name="Priya Nair",
        document_title="Priya-Nair-CV.docx",
        source_uri="dropbox:///priya.docx",
        extracted_text="Different body",
    )

    plan = build_recovery_plan(
        missing_rows=[missing],
        dropbox_rows=[dropbox],
    )

    assert len(plan["title_name_review_matches"]) == 1
    review_match = plan["title_name_review_matches"][0]
    assert review_match["matched_source_uri"] == "dropbox:///priya.docx"
    assert review_match["strategy"] == "title_name_review"


def test_build_recovery_plan_recovers_exact_content_hash_match() -> None:
    missing = ResumeRow(
        source_system="recruiterflow",
        candidate_id="cand-rf",
        document_id="doc-rf-3",
        full_name="Jordan Lee",
        current_company_name=None,
        current_title=None,
        document_title="Profile.pdf",
        resume_updated_at=None,
        source_uri=None,
        content_hash="same-hash",
        extracted_text=None,
    )
    dropbox = ResumeRow(
        source_system="dropbox",
        candidate_id="cand-db",
        document_id="doc-db-4",
        full_name="Jordan Lee",
        current_company_name=None,
        current_title=None,
        document_title="Jordan Lee CV.pdf",
        resume_updated_at=None,
        source_uri="dropbox:///jordan.pdf",
        content_hash="same-hash",
        extracted_text="Different normalized text",
    )

    plan = build_recovery_plan(
        missing_rows=[missing],
        dropbox_rows=[dropbox],
    )

    assert len(plan["exact_hash_recoveries"]) == 1
    recovery = plan["exact_hash_recoveries"][0]
    assert recovery["matched_source_uri"] == "dropbox:///jordan.pdf"
    assert recovery["strategy"] == "exact_content_hash"


def test_build_recovery_plan_reports_filename_name_review_match() -> None:
    missing = ResumeRow(
        source_system="recruiterflow",
        candidate_id="cand-rf-4",
        document_id="doc-rf-4",
        full_name="Mina Patel",
        current_company_name=None,
        current_title=None,
        document_title="Profile.pdf",
        resume_updated_at=None,
        source_uri=None,
        content_hash=None,
        extracted_text=None,
    )
    dropbox = ResumeRow(
        source_system="dropbox",
        candidate_id="cand-db-4",
        document_id="doc-db-5",
        full_name="Mina Patel",
        current_company_name=None,
        current_title=None,
        document_title="Mina Patel CV.pdf",
        resume_updated_at=None,
        source_uri="dropbox:///mina-patel.pdf",
        content_hash=None,
        extracted_text=None,
    )

    plan = build_recovery_plan(
        missing_rows=[missing],
        dropbox_rows=[dropbox],
    )

    assert len(plan["filename_name_review_matches"]) == 1
    review_match = plan["filename_name_review_matches"][0]
    assert review_match["matched_source_uri"] == "dropbox:///mina-patel.pdf"
    assert review_match["strategy"] == "filename_name_review"


def test_build_review_report_orders_review_candidates_by_confidence() -> None:
    report = build_review_report(
        recovery_plan={
            "title_name_review_matches": [],
            "filename_name_review_matches": [
                {
                    "candidate_id": "cand-2",
                    "full_name": "A Person",
                    "current_title": None,
                    "document_title": "Profile.pdf",
                    "strategy": "filename_name_review",
                },
                {
                    "candidate_id": "cand-1",
                    "full_name": "Alex Morgan",
                    "current_title": "Engineer",
                    "document_title": "Alex Morgan CV.pdf",
                    "strategy": "filename_name_review",
                },
            ],
            "title_name_ambiguous": [],
            "filename_name_ambiguous": [],
            "exact_hash_ambiguous": [],
            "exact_text_ambiguous": [],
            "unmatched": [],
        }
    )

    assert [item["candidate_id"] for item in report["review_candidates"]] == [
        "cand-1",
        "cand-2",
    ]
    assert report["review_candidates"][0]["confidence_label"] == "high"


def test_build_recovery_plan_reports_profile_identity_review_match() -> None:
    missing = ResumeRow(
        source_system="recruiterflow",
        candidate_id="cand-rf-5",
        document_id="doc-rf-5",
        full_name="Alex Morgan",
        current_company_name="Deutsche Bank",
        current_title="Quant Developer",
        document_title="Profile.pdf",
        resume_updated_at=None,
        source_uri=None,
        content_hash=None,
        extracted_text=None,
    )
    dropbox = ResumeRow(
        source_system="dropbox",
        candidate_id="cand-db-5",
        document_id="doc-db-6",
        full_name="Alex Morgan",
        current_company_name="Deutsche Bank",
        current_title="Quant Engineer",
        document_title="Some generic.pdf",
        resume_updated_at=None,
        source_uri="dropbox:///alex-morgan.pdf",
        content_hash=None,
        extracted_text=None,
    )

    plan = build_recovery_plan(
        missing_rows=[missing],
        dropbox_rows=[dropbox],
    )

    assert len(plan["profile_identity_review_matches"]) == 1
    review_match = plan["profile_identity_review_matches"][0]
    assert review_match["matched_source_uri"] == "dropbox:///alex-morgan.pdf"
    assert review_match["strategy"] == "profile_identity_review"
