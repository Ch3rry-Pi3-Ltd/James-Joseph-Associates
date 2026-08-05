"""Run a bounded, in-process concurrent load probe against the health route."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app  # noqa: E402


DEFAULT_REQUEST_COUNT = 100
DEFAULT_CONCURRENCY = 10
MAX_REQUEST_COUNT = 2_000
MAX_CONCURRENCY = 100


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise the API application and middleware concurrently without "
            "calling external providers or the production database."
        )
    )
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUEST_COUNT)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    return parser


def validate_probe_shape(*, request_count: int, concurrency: int) -> None:
    """Keep the local probe useful without allowing accidental unbounded load."""

    if not 1 <= request_count <= MAX_REQUEST_COUNT:
        raise ValueError(f"requests must be between 1 and {MAX_REQUEST_COUNT}.")
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        raise ValueError(f"concurrency must be between 1 and {MAX_CONCURRENCY}.")
    if concurrency > request_count:
        raise ValueError("concurrency cannot exceed requests.")


def percentile(values: list[float], fraction: float) -> float:
    """Return a deterministic nearest-rank percentile for a non-empty sample."""

    if not values:
        raise ValueError("percentile requires at least one value.")
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * fraction))
    return ordered[index]


def summarize_probe(samples: list[dict[str, Any]], *, concurrency: int) -> dict[str, Any]:
    """Build a compact, content-free result suitable for CI or operator notes."""

    successful = [sample for sample in samples if sample["status_code"] == 200]
    latencies = [float(sample["duration_ms"]) for sample in samples]
    request_ids = {
        sample["request_id"] for sample in samples if sample.get("request_id")
    }
    return {
        "request_count": len(samples),
        "concurrency": concurrency,
        "success_count": len(successful),
        "failure_count": len(samples) - len(successful),
        "unique_request_id_count": len(request_ids),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
    }


async def run_probe(*, request_count: int, concurrency: int) -> dict[str, Any]:
    """Issue bounded concurrent requests through the real ASGI application."""

    validate_probe_shape(request_count=request_count, concurrency=concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://resilience-probe.local",
    ) as client:

        async def issue_request() -> dict[str, Any]:
            async with semaphore:
                started_at = perf_counter()
                try:
                    response = await client.get("/api/v1/health")
                except Exception as exc:
                    return {
                        "status_code": 0,
                        "duration_ms": (perf_counter() - started_at) * 1000,
                        "request_id": None,
                        "error_type": exc.__class__.__name__,
                    }
                return {
                    "status_code": response.status_code,
                    "duration_ms": (perf_counter() - started_at) * 1000,
                    "request_id": response.headers.get("x-request-id"),
                    "error_type": None,
                }

        samples = await asyncio.gather(
            *(issue_request() for _ in range(request_count))
        )

    return summarize_probe(samples, concurrency=concurrency)


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    logging.getLogger("backend.core.performance").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        summary = asyncio.run(
            run_probe(
                request_count=args.requests,
                concurrency=args.concurrency,
            )
        )
    except ValueError as exc:
        print(str(exc))
        return 2

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
