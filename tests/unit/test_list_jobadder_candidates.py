"""
Unit tests for the JobAdder candidate-list script helpers.
"""

from __future__ import annotations

from scripts.list_jobadder_candidates import build_candidate_export_row


def test_build_candidate_export_row_flattens_basic_candidate_fields() -> None:
    row = build_candidate_export_row(
        {
            "candidateId": 16496678,
            "firstName": "Roger",
            "lastName": "Campbell",
            "email": "the_rfc@hotmail.co.uk",
            "mobile": "07934 890 708",
            "location": "London",
            "updatedAt": "2026-04-20T10:02:24Z",
            "createdAt": "2025-07-10T16:01:10Z",
            "status": {
                "name": "Active",
            },
        }
    )

    assert row == {
        "candidateId": 16496678,
        "firstName": "Roger",
        "lastName": "Campbell",
        "email": "the_rfc@hotmail.co.uk",
        "mobile": "07934 890 708",
        "location": "London",
        "updatedAt": "2026-04-20T10:02:24Z",
        "createdAt": "2025-07-10T16:01:10Z",
        "status": "Active",
    }
