"""Deterministic concurrent-load coverage for the application boundary."""

from __future__ import annotations

import asyncio

import pytest

from scripts.run_resilience_load_probe import run_probe, validate_probe_shape


def test_health_boundary_survives_bounded_concurrent_load() -> None:
    """Concurrent requests must all complete with isolated correlation IDs."""

    result = asyncio.run(run_probe(request_count=64, concurrency=8))

    assert result["request_count"] == 64
    assert result["concurrency"] == 8
    assert result["success_count"] == 64
    assert result["failure_count"] == 0
    assert result["unique_request_id_count"] == 64
    assert result["latency_ms"]["p50"] >= 0
    assert result["latency_ms"]["p95"] >= result["latency_ms"]["p50"]
    assert result["latency_ms"]["max"] >= result["latency_ms"]["p95"]


@pytest.mark.parametrize(
    ("request_count", "concurrency"),
    [(0, 1), (2_001, 1), (10, 0), (10, 101), (5, 6)],
)
def test_load_probe_rejects_unsafe_shapes(
    request_count: int,
    concurrency: int,
) -> None:
    with pytest.raises(ValueError):
        validate_probe_shape(
            request_count=request_count,
            concurrency=concurrency,
        )
