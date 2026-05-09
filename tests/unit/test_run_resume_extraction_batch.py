"""
Unit tests for the batch resume-extraction runner helpers.
"""

from __future__ import annotations

from pathlib import Path

from scripts.run_resume_extraction_batch import (
    build_batch_manifest_record,
    build_batch_summary,
    find_success_manifest_record,
    load_candidate_ids,
)


def test_load_candidate_ids_combines_file_and_cli_ids() -> None:
    candidate_ids_file = Path("temp/test_candidate_ids.txt")
    candidate_ids_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        candidate_ids_file.write_text(
            "12345678\n87654321, 12345678\n",
            encoding="utf-8",
        )

        result = load_candidate_ids(
            explicit_candidate_ids=[16496678, 12345678],
            candidate_ids_file=candidate_ids_file,
        )

        assert result == [16496678, 12345678, 87654321]
    finally:
        if candidate_ids_file.exists():
            candidate_ids_file.unlink()


def test_build_batch_summary_counts_fallbacks_and_statuses() -> None:
    summary = build_batch_summary(
        candidate_ids=[1, 2, 3],
        successes=[
            {
                "candidate_id": 1,
                "quality_status": "pass",
                "fallback_invoked": False,
            },
            {
                "candidate_id": 2,
                "quality_status": "review",
                "fallback_invoked": True,
            },
        ],
        failures=[
            {
                "candidate_id": 3,
                "message": "Provider exploded",
                "stage": "llm_invoke",
            }
        ],
        skipped=[
            {
                "candidate_id": 99,
                "candidate_fingerprint": "abc123",
            }
        ],
        output_dir=Path("temp/resume_extraction_batch/20260508T120000Z"),
        quality_log_jsonl=Path("temp/resume_extraction_batch/20260508T120000Z/quality_log.jsonl"),
        manifest_jsonl=Path("temp/resume_extraction_batch_manifest.jsonl"),
    )

    assert summary["requested_count"] == 3
    assert summary["success_count"] == 2
    assert summary["failure_count"] == 1
    assert summary["skipped_count"] == 1
    assert summary["fallback_count"] == 1
    assert summary["quality_status_counts"] == {"pass": 1, "review": 1}


def test_find_success_manifest_record_ignores_failure_rows() -> None:
    result = find_success_manifest_record(
        manifest_records=[
            {
                "candidate_fingerprint": "same-fingerprint",
                "processing_outcome": "failure",
                "timestamp": "2026-05-09T10:00:00Z",
            },
            {
                "candidate_fingerprint": "same-fingerprint",
                "processing_outcome": "success",
                "timestamp": "2026-05-09T11:00:00Z",
                "output_json": "temp/candidate_1.json",
            },
        ],
        candidate_fingerprint="same-fingerprint",
    )

    assert result is not None
    assert result["processing_outcome"] == "success"
    assert result["output_json"] == "temp/candidate_1.json"


def test_build_batch_manifest_record_keeps_quality_metadata() -> None:
    record = build_batch_manifest_record(
        candidate_id=16496678,
        candidate_fingerprint="fingerprint-123",
        source_markers={
            "candidate_id": 16496678,
            "contract_fingerprint": "contract-abc",
        },
        output_json="temp/candidate_16496678.json",
        processing_outcome="success",
        result={
            "model_profile": {
                "provider": "openai",
                "model_name": "gpt-4.1-mini",
            },
            "quality_assessment": {
                "quality_score": 88,
                "status": "pass",
            },
            "quality_gate": {
                "fallback_invoked": True,
                "final_model_name": "gpt-5.4-mini",
            },
        },
    )

    assert record["candidate_id"] == 16496678
    assert record["candidate_fingerprint"] == "fingerprint-123"
    assert record["processing_outcome"] == "success"
    assert record["quality_score"] == 88
    assert record["quality_status"] == "pass"
    assert record["fallback_invoked"] is True
    assert record["final_model_name"] == "gpt-5.4-mini"
