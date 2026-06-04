"""
Unit tests for the Dropbox candidate-name repair script.
"""

from scripts.repair_dropbox_candidate_names import _classify_dropbox_candidate_row


def test_classify_dropbox_candidate_row_marks_clean_replacement_for_update() -> None:
    """
    Verify that suspicious Dropbox names are repaired from the source filename.
    """

    result = _classify_dropbox_candidate_row(
        {
            "candidate_id": "candidate-1",
            "person_id": "person-1",
            "full_name": "etamba Totaljobs",
            "first_name": "etamba",
            "last_name": "Totaljobs",
            "source_file_name": "Etamba (12345 - Totaljobs).pdf",
            "source_path": "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/Etamba (12345 - Totaljobs).pdf",
        }
    )

    assert result["action"] == "update"
    assert result["replacement_full_name"] == "Etamba"
    assert result["reason"] == "repair_suspicious_dropbox_filename_name"


def test_classify_dropbox_candidate_row_flags_unresolved_when_no_name_can_be_derived() -> None:
    """
    Verify that rows with no usable derived replacement stay in the unresolved bucket.
    """

    result = _classify_dropbox_candidate_row(
        {
            "candidate_id": "candidate-1",
            "person_id": "person-1",
            "full_name": "Unknown Candidate",
            "first_name": None,
            "last_name": None,
            "source_file_name": "(73579777 - Totaljobs).doc",
            "source_path": "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/(73579777 - Totaljobs).doc",
        }
    )

    assert result["action"] == "unresolved"
    assert result["reason"] == "no_name_derived_from_filename"


def test_classify_dropbox_candidate_row_repairs_js_suffix_and_camel_case() -> None:
    """
    Verify that JS/date suffixes and camel-cased stems normalize cleanly.
    """

    result = _classify_dropbox_candidate_row(
        {
            "candidate_id": "candidate-1",
            "person_id": "person-1",
            "full_name": "IssamMouradResume",
            "first_name": "IssamMouradResume",
            "last_name": None,
            "source_file_name": "IssamMouradResume.docx",
            "source_path": "/### BIG BAD CV ARCHIVE inc. RFL/### CV Archive/IssamMouradResume.docx",
        }
    )

    assert result["action"] == "update"
    assert result["replacement_full_name"] == "Issam Mourad"
