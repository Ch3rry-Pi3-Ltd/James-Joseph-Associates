"""
Unit tests for the batch resume-extraction runner helpers.
"""

from __future__ import annotations

from pathlib import Path

from scripts.run_resume_extraction_batch import (
    build_batch_summary,
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
        output_dir=Path("temp/resume_extraction_batch/20260508T120000Z"),
        quality_log_jsonl=Path("temp/resume_extraction_batch/20260508T120000Z/quality_log.jsonl"),
    )

    assert summary["requested_count"] == 3
    assert summary["success_count"] == 2
    assert summary["failure_count"] == 1
    assert summary["fallback_count"] == 1
    assert summary["quality_status_counts"] == {"pass": 1, "review": 1}
