"""
Unit tests for the batch resume-extraction runner helpers.

Why this module exists
----------------------
The batch runner now does more than just loop over candidate IDs. It also:

- builds batch summaries
- records manifest rows
- decides whether unchanged successful candidates should be skipped
- decides whether unchanged terminal no-resume failures should be skipped

Those behaviours are cheap to test locally and should stay deterministic.

What these tests cover
----------------------
This module focuses on the small pure helpers that are easiest to verify
without touching:

- JobAdder
- the LLM provider layer
- the filesystem-heavy live batch path

In plain language:

- prove the helper logic is stable
- keep the batch runner's control flow explainable
- catch regressions in manifest/summary behaviour early
"""

from __future__ import annotations

from pathlib import Path

from scripts.run_resume_extraction_batch import (
    build_batch_manifest_record,
    build_candidate_processing_fingerprint,
    build_profile_only_persistence_result_payload,
    build_batch_summary,
    find_skip_manifest_record,
    find_success_manifest_record,
    get_manifest_record_source_fingerprint,
    is_stable_source_failure_manifest_record,
    load_candidate_ids,
)


def test_load_candidate_ids_combines_file_and_cli_ids() -> None:
    """
    Verify that CLI-supplied and file-supplied candidate IDs are merged in
    first-seen order.

    Notes
    -----
    - The batch runner accepts both repeated `--candidate-id` flags and a
      looser text-file format.
    - This test pins the practical operator expectation:
        - preserve first-seen order
        - deduplicate repeated IDs
        - accept mixed newline/comma delimiters
    """

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
    """
    Verify that the batch summary aggregates status and fallback counts
    correctly.

    Notes
    -----
    - This is one of the operator-facing summaries, so drift here would be
      confusing even if the underlying per-candidate artifacts were correct.
    - The test deliberately mixes:
        - successes
        - failures
        - skipped items
        - one fallback rerun
    """

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
        profile_only_persisted=[
            {
                "candidate_id": 77,
                "output_json": "temp/profile_only_77.json",
            }
        ],
        output_dir=Path("temp/resume_extraction_batch/20260508T120000Z"),
        quality_log_jsonl=Path("temp/resume_extraction_batch/20260508T120000Z/quality_log.jsonl"),
        manifest_jsonl=Path("temp/resume_extraction_batch_manifest.jsonl"),
    )

    assert summary["requested_count"] == 3
    assert summary["success_count"] == 2
    assert summary["profile_only_persisted_count"] == 1
    assert summary["failure_count"] == 1
    assert summary["skipped_count"] == 1
    assert summary["fallback_count"] == 1
    assert summary["quality_status_counts"] == {"pass": 1, "review": 1}


def test_build_profile_only_persistence_result_payload_keeps_reason_and_notes() -> None:
    """
    Verify that the saved no-resume artifact explains both the reason and the write.

    Notes
    -----
    The profile-only persistence path needs its own per-candidate JSON artifact
    because no CV extraction result exists to inspect later. This helper should
    therefore preserve:

    - the explicit no-resume reason
    - the cleaned notes that justified keeping the contact
    - the canonical IDs written by persistence
    """

    payload = build_profile_only_persistence_result_payload(
        ingest_payload={
            "source_system": "jobadder",
            "source_candidate_id": 13812978,
            "jobadder_account": 2236,
            "attachments": {
                "attachment_count": 0,
                "resume_attachment_count": 0,
            },
            "notes": {
                "cleaned_items": [
                    {
                        "note_id": "note-1",
                        "cleaned_text": "Candidate open to move.",
                    }
                ]
            },
            "ingest_shell": {
                "core_identity": {
                    "first_name": "Roger",
                    "last_name": "Campbell",
                }
            },
        },
        persistence_result={
            "candidate_id": "candidate-uuid",
            "person_id": "person-uuid",
            "profile_source_record_id": "profile-source-uuid",
        },
    )

    assert payload["processing_outcome"] == "profile_only_persisted"
    assert payload["profile_persistence_reason"] == "no_resume_attachment"
    assert payload["cleaned_candidate_notes"][0]["cleaned_text"] == (
        "Candidate open to move."
    )
    assert payload["persistence_result"]["candidate_id"] == "candidate-uuid"


def test_find_success_manifest_record_ignores_failure_rows() -> None:
    """
    Verify that the success-only lookup ignores prior failure rows for the same
    fingerprint.

    Notes
    -----
    This helper is intentionally narrower than the broader skip-policy helper.
    It should answer only:

    - "Was there a prior identical success?"

    and not silently widen itself into a generic manifest decision function.
    """

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


def test_build_candidate_processing_fingerprint_separates_source_and_contract_identity() -> None:
    """
    Verify that source-only and contract-aware fingerprints can diverge
    deliberately.

    Notes
    -----
    This is the key design point behind the refined skip policy:

    - stable no-resume failures should care only about source state
    - successful reruns should still care about the extraction contract
    """

    ingest_payload = {
        "source_system": "jobadder",
        "jobadder_account": 2236,
        "source_candidate_id": 13812978,
        "candidate": {
            "updatedAt": "2025-07-16T16:53:18Z",
            "status": "Active",
        },
        "latest_resume": None,
        "attachments": {
            "resume_attachment_count": 0,
        },
        "notes": {
            "items": [],
            "note_count": 0,
        },
    }

    source_fingerprint_a, candidate_fingerprint_a, source_markers_a = (
        build_candidate_processing_fingerprint(
            ingest_payload=ingest_payload,
            contract_fingerprint="contract-a",
        )
    )
    source_fingerprint_b, candidate_fingerprint_b, source_markers_b = (
        build_candidate_processing_fingerprint(
            ingest_payload=ingest_payload,
            contract_fingerprint="contract-b",
        )
    )

    assert source_fingerprint_a == source_fingerprint_b
    assert candidate_fingerprint_a != candidate_fingerprint_b
    assert source_markers_a == source_markers_b


def test_is_stable_source_failure_manifest_record_accepts_no_resume_failure() -> None:
    """
    Verify that the narrow stable-failure rule recognises the known no-resume
    source failure pattern.

    Notes
    -----
    - This is intentionally strict.
    - We only want to skip failures that are clearly caused by upstream source
      absence, not by parser/model behaviour that may change after code edits.
    """

    assert (
        is_stable_source_failure_manifest_record(
            {
                "processing_outcome": "failure",
                "failure_stage": "resume_selection",
                "failure_message": (
                    "No likely JobAdder resume attachment was found for this candidate."
                ),
            }
        )
        is True
    )


def test_is_stable_source_failure_manifest_record_rejects_docx_parse_failure() -> None:
    """
    Verify that parser-style failures remain replayable rather than becoming
    skip-worthy terminal states.

    Notes
    -----
    The live batch evidence showed DOCX parsing failures were a feature gap,
    not a permanent source-data absence. That is exactly the kind of failure
    this helper must refuse to classify as terminal.
    """

    assert (
        is_stable_source_failure_manifest_record(
            {
                "processing_outcome": "failure",
                "failure_stage": "resume_text_extraction",
                "failure_message": "JobAdder candidate resume text extraction failed.",
            }
        )
        is False
    )


def test_find_skip_manifest_record_returns_terminal_failure_when_no_success_exists() -> None:
    """
    Verify that the manifest skip lookup can return an unchanged terminal
    source-failure row.

    Notes
    -----
    This pins the intended distinction:

    - unchanged no-resume failures may be skipped
    - generic failures may not
    """

    result = find_skip_manifest_record(
        manifest_records=[
            {
                "source_fingerprint": "source-only-fingerprint",
                "candidate_fingerprint": "same-fingerprint",
                "processing_outcome": "failure",
                "timestamp": "2026-05-10T09:00:00Z",
                "failure_stage": "resume_selection",
                "failure_message": (
                    "No likely JobAdder resume attachment was found for this candidate."
                ),
            }
        ],
        candidate_fingerprint="different-contract-aware-fingerprint",
        source_fingerprint="source-only-fingerprint",
    )

    assert result is not None
    assert result["processing_outcome"] == "failure"
    assert result["failure_stage"] == "resume_selection"


def test_find_skip_manifest_record_prefers_later_success_over_failure() -> None:
    """
    Verify that a later identical success remains the strongest skip signal.

    Notes
    -----
    If the same fingerprint has both:

    - an earlier terminal source failure
    - a later success

    then the later success should win because it is the freshest known outcome
    for that unchanged source state.
    """

    result = find_skip_manifest_record(
        manifest_records=[
            {
                "source_fingerprint": "source-only-fingerprint",
                "candidate_fingerprint": "same-fingerprint",
                "processing_outcome": "failure",
                "timestamp": "2026-05-10T09:00:00Z",
                "failure_stage": "resume_selection",
                "failure_message": (
                    "No likely JobAdder resume attachment was found for this candidate."
                ),
            },
            {
                "source_fingerprint": "source-only-fingerprint",
                "candidate_fingerprint": "same-fingerprint",
                "processing_outcome": "success",
                "timestamp": "2026-05-10T10:00:00Z",
                "output_json": "temp/candidate_13816907.json",
            },
        ],
        candidate_fingerprint="same-fingerprint",
        source_fingerprint="source-only-fingerprint",
    )

    assert result is not None
    assert result["processing_outcome"] == "success"
    assert result["output_json"] == "temp/candidate_13816907.json"


def test_get_manifest_record_source_fingerprint_derives_legacy_row_value() -> None:
    """
    Verify that older manifest rows can still produce a source-only
    fingerprint.

    Notes
    -----
    Earlier manifest rows stored only `source_markers`, and those markers still
    included `contract_fingerprint`. The new stable-failure skip policy needs a
    source-only identity, so this helper must be able to reconstruct it for
    backward compatibility.
    """

    record = {
        "source_markers": {
            "contract_fingerprint": "old-contract",
            "source_system": "jobadder",
            "jobadder_account": 2236,
            "candidate_id": 13812978,
            "resume_attachment_count": 0,
            "latest_note_timestamp": None,
        }
    }

    derived = get_manifest_record_source_fingerprint(record)

    assert isinstance(derived, str)
    assert derived != ""


def test_find_skip_manifest_record_accepts_legacy_terminal_failure_row() -> None:
    """
    Verify that a legacy no-resume failure row can still be skipped after the
    source-only fingerprint change.

    Notes
    -----
    This pins the migration path we care about operationally:

    - older rows may not have `source_fingerprint`
    - they should still be usable for source-only no-resume skips
    """

    ingest_payload = {
        "source_system": "jobadder",
        "jobadder_account": 2236,
        "source_candidate_id": 13812978,
        "candidate": {
            "updatedAt": "2025-07-16T16:53:18Z",
            "status": "Active",
        },
        "latest_resume": None,
        "attachments": {
            "resume_attachment_count": 0,
        },
        "notes": {
            "items": [],
            "note_count": 0,
        },
    }

    source_fingerprint, candidate_fingerprint, source_markers = (
        build_candidate_processing_fingerprint(
            ingest_payload=ingest_payload,
            contract_fingerprint="new-contract",
        )
    )

    legacy_record = {
        "candidate_fingerprint": "older-contract-aware-fingerprint",
        "source_markers": {
            **source_markers,
            "contract_fingerprint": "old-contract",
        },
        "processing_outcome": "failure",
        "timestamp": "2026-05-10T09:00:00Z",
        "failure_stage": "resume_selection",
        "failure_message": "No likely JobAdder resume attachment was found for this candidate.",
    }

    result = find_skip_manifest_record(
        manifest_records=[legacy_record],
        candidate_fingerprint=candidate_fingerprint,
        source_fingerprint=source_fingerprint,
    )

    assert result is not None
    assert result["processing_outcome"] == "failure"
    assert result["failure_stage"] == "resume_selection"


def test_build_batch_manifest_record_keeps_quality_metadata() -> None:
    """
    Verify that manifest rows preserve the extraction-quality routing metadata.

    Notes
    -----
    The manifest is no longer just a dedupe ledger. It also captures the
    information later calibration work needs, such as:

    - quality score
    - quality status
    - whether fallback was invoked
    - which final model actually won
    """

    record = build_batch_manifest_record(
        candidate_id=16496678,
        source_fingerprint="source-xyz",
        candidate_fingerprint="fingerprint-123",
        source_markers={
            "candidate_id": 16496678,
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
                "final_model_name": "gpt-4.1-mini",
            },
        },
    )

    assert record["candidate_id"] == 16496678
    assert record["source_fingerprint"] == "source-xyz"
    assert record["candidate_fingerprint"] == "fingerprint-123"
    assert record["processing_outcome"] == "success"
    assert record["quality_score"] == 88
    assert record["quality_status"] == "pass"
    assert record["fallback_invoked"] is True
    assert record["final_model_name"] == "gpt-4.1-mini"
