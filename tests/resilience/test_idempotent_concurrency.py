"""Concurrent retry-fingerprint coverage for idempotent work."""

from concurrent.futures import ThreadPoolExecutor

from backend.core.idempotency import (
    build_idempotency_metadata,
    detect_idempotency_conflict,
)


def test_equivalent_concurrent_retries_produce_one_stable_fingerprint() -> None:
    """Payload key order must not split identical retries under concurrency."""

    payloads = [
        {"candidate_id": 123, "source": "jobadder"},
        {"source": "jobadder", "candidate_id": 123},
    ]
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [
            executor.submit(
                build_idempotency_metadata,
                " batch-run-123 ",
                payloads[index % 2],
            )
            for index in range(128)
        ]
        results = [future.result(timeout=2) for future in futures]

    assert {result.key for result in results} == {"batch-run-123"}
    assert len({result.payload_hash for result in results}) == 1


def test_reused_key_with_changed_payload_remains_a_conflict() -> None:
    original = build_idempotency_metadata(
        "batch-run-123",
        {"candidate_id": 123, "source": "jobadder"},
    )
    changed = build_idempotency_metadata(
        "batch-run-123",
        {"candidate_id": 456, "source": "jobadder"},
    )

    conflict = detect_idempotency_conflict(
        key=original.key,
        existing_payload_hash=original.payload_hash,
        incoming_payload_hash=changed.payload_hash,
    )

    assert conflict is not None
    assert conflict.key == "batch-run-123"
