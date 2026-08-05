"""Restart and partial-failure coverage for the resume-extraction batch worker."""

from __future__ import annotations

import json

import scripts.run_resume_extraction_batch as batch


def test_batch_continues_after_failure_and_restart_skips_completed_work(
    monkeypatch,
    tmp_path,
) -> None:
    """One failed item must not lose later work or duplicate it on restart."""

    processed_candidate_ids: list[int] = []

    def build_ingest_shell(*, jobadder_account: int, candidate_id: int) -> dict:
        assert jobadder_account == 7
        return {
            "candidate_id": candidate_id,
            "latest_resume": {"attachmentId": f"resume-{candidate_id}"},
        }

    def build_fingerprint(*, ingest_payload: dict, contract_fingerprint: str):
        candidate_id = ingest_payload["candidate_id"]
        return (
            f"source-{candidate_id}",
            f"candidate-{candidate_id}-{contract_fingerprint}",
            {"candidate_id": candidate_id},
        )

    def run_candidate(args) -> dict:
        processed_candidate_ids.append(args.candidate_id)
        if args.candidate_id == 1:
            raise RuntimeError("temporary provider failure")
        return {
            "model_profile": {"provider": "openai", "model_name": "test-model"},
            "quality_assessment": {"quality_score": 90, "status": "pass"},
            "cv_source_assessment": {"richness_score": 80, "richness_band": "rich"},
            "quality_gate": {
                "fallback_invoked": False,
                "final_model_name": "test-model",
            },
        }

    monkeypatch.setattr(batch, "build_jobadder_candidate_ingest_shell", build_ingest_shell)
    monkeypatch.setattr(batch, "build_candidate_processing_fingerprint", build_fingerprint)
    monkeypatch.setattr(
        batch,
        "build_extraction_contract_fingerprint",
        lambda *, args: "contract-v1",
    )
    monkeypatch.setattr(
        batch,
        "run_live_resume_extraction_with_optional_quality_gate",
        run_candidate,
    )
    monkeypatch.setattr(
        batch,
        "build_json_ready_result",
        lambda *, result, include_prompts: {"status": "complete"},
    )

    output_dir = tmp_path / "runs"
    manifest_path = tmp_path / "manifest.jsonl"
    common_args = [
        "--jobadder-account",
        "7",
        "--output-dir",
        str(output_dir),
        "--manifest-jsonl",
        str(manifest_path),
    ]

    first_exit_code = batch.main(
        [
            *common_args,
            "--candidate-id",
            "1",
            "--candidate-id",
            "2",
        ]
    )

    assert first_exit_code == 1
    assert processed_candidate_ids == [1, 2]
    manifest_rows = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["processing_outcome"] for row in manifest_rows] == [
        "failure",
        "success",
    ]

    second_exit_code = batch.main([*common_args, "--candidate-id", "2"])

    assert second_exit_code == 0
    assert processed_candidate_ids == [1, 2]
