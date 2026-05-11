"""
Unit tests for the single-run resume-extraction CLI script.

This module tests the narrow script-level wiring in
`scripts.run_resume_extraction`.

It gives the rest of the repository a stable way to check:

- CLI flags are parsed into the expected runtime behaviour
- accepted-output persistence is actually applied in `main(...)`
- the JSON output path receives the enriched persisted payload

These tests matter because script regressions are easy to miss: the core
services can remain correct while the operator-facing entrypoint silently stops
calling them in the intended order.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import scripts.run_resume_extraction as run_resume_extraction


def test_main_persists_accepted_output_when_flag_is_enabled() -> None:
    """
    Verify that `main(...)` really applies accepted-output persistence.

    Notes
    -----
    The earlier regression was subtle:

    - the CLI flag existed
    - the persistence helper existed
    - but `main(...)` stopped calling the helper after quality gating

    This test pins the script-level contract directly:

    - parse the persistence flag
    - run the quality-gated extraction path
    - enrich the result with `persistence_result`
    - write that enriched payload to the JSON output helper
    """

    captured_json_payloads: list[dict[str, object]] = []

    fake_result = {
        "source_system": "jobadder",
        "source_candidate_id": 13902889,
        "jobadder_account": 2236,
        "model_profile": {
            "provider": "openai",
            "model_name": "gpt-4.1-mini",
        },
        "extraction_input": {
            "candidate_context": {
                "first_name": "Vincent",
                "last_name": "Odiaka",
            },
            "latest_resume": {
                "file_name": "Vincent-Odiaka_cv-library.pdf",
            },
        },
        "structured_extraction": {
            "current_title": "Data Analyst",
            "current_employer": "NHS Practitioner Health",
            "location": "London England",
            "emails": ["odiaka.vincent@yahoo.com"],
            "phones": ["07858893286"],
            "skills": ["Data Analysis"],
            "tools_and_platforms": ["Python"],
            "certifications": [],
            "employment_history": [],
            "projects": [],
            "education": [],
            "evidence_notes": ["Resume contact block provides email."],
            "ambiguity_notes": ["Education institution names are not stated."],
        },
        "quality_assessment": {
            "quality_score": 100,
            "status": "pass",
        },
        "cv_source_assessment": {
            "richness_score": 100,
            "richness_band": "rich",
        },
        "quality_gate": {
            "enabled": True,
            "fallback_invoked": False,
            "final_model_name": "gpt-4.1-mini",
        },
    }

    def fake_write_json_output(*, payload: dict[str, object], output_path: Path) -> None:
        captured_json_payloads.append(payload)

    with patch.object(
        run_resume_extraction,
        "run_live_resume_extraction_with_optional_quality_gate",
        return_value=fake_result,
    ), patch.object(
        run_resume_extraction,
        "persist_accepted_resume_extraction_result",
        return_value={
            "candidate_id": "candidate-uuid",
            "person_id": "person-uuid",
        },
    ), patch.object(
        run_resume_extraction,
        "write_json_output",
        side_effect=fake_write_json_output,
    ):
        exit_code = run_resume_extraction.main(
            [
                "--jobadder-account",
                "2236",
                "--candidate-id",
                "13902889",
                "--enable-quality-gate",
                "--persist-accepted-output",
                "--output-json",
                "temp/resume_extraction_result_persisted.json",
            ]
        )

    assert exit_code == 0
    assert len(captured_json_payloads) == 1
    assert captured_json_payloads[0]["persistence_requested"] is True
    assert captured_json_payloads[0]["persistence_result"] == {
        "candidate_id": "candidate-uuid",
        "person_id": "person-uuid",
    }
