"""
Unit tests for the persisted resume-extraction verification CLI script.

This module checks the operator-facing verification entrypoint rather than the
lower-level DB reads directly.

It gives the rest of the repository a stable way to check:

- `persistence_result` is loaded from a saved extraction JSON artifact
- verification results can be written back out as JSON
- the script returns the expected exit code for a successful verification run
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from backend.services.resume_extraction_verification import (
    PersistenceVerificationCheck,
    ResumeExtractionPersistenceVerification,
)
import scripts.check_persisted_resume_extraction as check_script


def test_main_verifies_saved_result_and_writes_report() -> None:
    """
    Verify that the script loads `persistence_result` and writes a report JSON.

    Example
    -------
    A saved extraction artifact containing `persistence_result` should be
    enough for the script to run verification without any extra manual IDs.
    """

    temp_dir = Path("temp/test_check_persisted_resume_extraction_script")
    temp_dir.mkdir(parents=True, exist_ok=True)
    unique_suffix = uuid4().hex
    result_json_path = temp_dir / f"result_{unique_suffix}.json"
    output_json_path = temp_dir / f"verification_{unique_suffix}.json"

    try:
        result_json_path.write_text(
            json.dumps(
                {
                    "persistence_result": {
                        "candidate_id": "candidate-uuid",
                        "person_id": "person-uuid",
                        "candidate_source_record_id": "source-candidate",
                        "extraction_source_record_id": "source-extraction",
                    }
                }
            ),
            encoding="utf-8",
        )

        fake_report = ResumeExtractionPersistenceVerification(
            verification_passed=True,
            passed_check_count=2,
            failed_check_count=0,
            expected={
                "candidate_id": "candidate-uuid",
                "person_id": "person-uuid",
            },
            checks=[
                PersistenceVerificationCheck(
                    name="candidate_profile_exists",
                    passed=True,
                    details="ok",
                )
            ],
            snapshot={"candidate_profile": {"candidate_id": "candidate-uuid"}},
        )

        with patch.object(
            check_script,
            "verify_persisted_resume_extraction_result",
            return_value=fake_report,
        ):
            exit_code = check_script.main(
                [
                    "--result-json",
                    str(result_json_path),
                    "--output-json",
                    str(output_json_path),
                ]
            )

        assert exit_code == 0
        written_payload = json.loads(output_json_path.read_text(encoding="utf-8"))
        assert written_payload["verification_passed"] is True
        assert written_payload["expected"]["candidate_id"] == "candidate-uuid"
    finally:
        if output_json_path.exists():
            output_json_path.unlink()
        if result_json_path.exists():
            result_json_path.unlink()
