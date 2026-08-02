"""Deterministic regression checks for AI workflow output quality."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.evaluation.quality_checks import (
    find_sensitive_fields,
    stable_payload_fingerprint,
    validate_claim_evidence,
    validate_rag_failure_matrix,
)
from backend.services.candidate_matching import CandidateEvidenceClaim


def test_claim_grounding_accepts_known_refs_and_rejects_unknown_refs() -> None:
    valid = validate_claim_evidence(
        claim_groups={
            "strengths": [
                {
                    "claim": "Python delivery",
                    "evidence_refs": ["document:doc-1"],
                }
            ]
        },
        allowed_evidence_refs={"document:doc-1"},
    )
    invalid = validate_claim_evidence(
        claim_groups={
            "strengths": [
                {
                    "claim": "Invented Kubernetes experience",
                    "evidence_refs": ["document:invented"],
                }
            ]
        },
        allowed_evidence_refs={"document:doc-1"},
    )

    assert valid == []
    assert [finding.code for finding in invalid] == [
        "unknown_evidence_reference"
    ]


def test_grounded_claim_schema_rejects_missing_evidence_refs() -> None:
    with pytest.raises(ValidationError):
        CandidateEvidenceClaim(
            claim="Unreferenced recommendation",
            evidence_refs=[],
        )


def test_stability_fingerprint_ignores_run_metadata_and_key_order() -> None:
    first = {
        "match_run_id": "run-1",
        "candidates": [{"fit_score": 91, "candidate_id": "cand-1"}],
    }
    second = {
        "candidates": [{"candidate_id": "cand-1", "fit_score": 91}],
        "match_run_id": "run-2",
    }

    assert stable_payload_fingerprint(first) == stable_payload_fingerprint(second)


def test_sensitive_field_check_reports_paths_without_copying_values() -> None:
    secret_email = "private.person@example.test"
    findings = find_sensitive_fields(
        {
            "candidate_id": "cand-1",
            "contact": {"primary_email": secret_email},
        }
    )

    assert [finding.path for finding in findings] == ["contact.primary_email"]
    assert secret_email not in str([finding.to_dict() for finding in findings])


def test_versioned_rag_failure_matrix_is_complete_and_fail_closed() -> None:
    matrix_path = Path("docs/evaluation/rag_failure_matrix.json")
    cases = json.loads(matrix_path.read_text(encoding="utf-8"))

    assert validate_rag_failure_matrix(cases) == []
