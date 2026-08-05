# Resilience and load testing

Implemented: 5 August 2026.

## Outcome

The repository now has deterministic automated coverage for concurrent cache
access, provider authentication recovery, bounded retry behaviour, retry
fingerprints, degraded rate-limit storage, restartable batch processing, model
fallbacks, and concurrent API requests. A bounded in-process load probe is also
available for repeatable local and CI checks without contacting production
providers or Supabase.

The work found and fixed a real cache-stampede risk. Concurrent misses for the
same company-directory or review-overview cache key previously ran the loader
independently, so a burst could duplicate database reads. `BoundedTtlCache` now
coalesces each key's concurrent misses into one load, wakes every waiter on
success or failure, does not cache exceptions, and prevents an older in-flight
read from repopulating a cache after `clear()`.

## Automated resilience matrix

| Boundary | Failure or load exercised | Expected result |
| --- | --- | --- |
| Warm-instance cache | 32 simultaneous misses for one key | One loader call; all callers receive defensively copied results |
| Warm-instance cache | Loader exception with concurrent waiters | All waiters are released; exception is not cached; next load can recover |
| Warm-instance cache | Cache clear during an in-flight load | Cleared generation cannot be repopulated by the older load |
| JobAdder, Dropbox, Outlook | Provider read returns `401` | Refresh credentials once and retry once with the refreshed access token |
| Provider degradation | Refreshed call fails or non-authentication failure occurs | Stop after the bounded attempt and return the existing safe gateway response |
| Model compatibility | Structured-output incompatibility or output-length ceiling | Use the existing bounded JSON-text or larger-output retry path |
| Quality gate | First-pass extraction requests a rerun | Use the configured fallback model and retain fallback metadata |
| Idempotency fingerprinting | 128 equivalent concurrent payloads with different key order | Produce one stable key and payload hash; changed payload remains a conflict |
| Rate-limit database | Durable rate-limit read raises | Fail closed with `503 rate_limit_unavailable`; do not silently disable controls |
| Batch work | First candidate fails and a later candidate succeeds | Continue the batch, persist both outcomes, and return a partial-failure exit code |
| Batch restart | Completed candidate is presented again with the same fingerprint | Skip the completed work rather than repeating extraction or persistence |
| ASGI application | 64 concurrent health requests in the automated suite | Every request succeeds with a distinct correlation ID |

## Bounded load probe

Run the local probe from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\run_resilience_load_probe.py `
  --requests 200 `
  --concurrency 20
```

The probe is deliberately capped at 2,000 requests and concurrency 100. It uses
the real FastAPI application, routing, security middleware, response cache
policy, and request observability, but calls only the dependency-free health
route through an in-process ASGI transport.

The 5 August 2026 development run produced:

| Requests | Concurrency | Successes | Unique request IDs | p50 | p95 | Maximum |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 200 | 20 | 200 | 200 | 24.140 ms | 118.798 ms | 128.738 ms |

These timings are a development-machine diagnostic, not a production service
level objective. Deployment capacity, network latency, database saturation,
and provider quotas require a separately approved preview-environment test.

## Verification commands

The focused suite is:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\resilience `
  tests\unit\test_cache.py `
  tests\unit\test_api_security.py
```

Existing resume-extraction tests remain the regression coverage for:

- OpenRouter JSON-text compatibility fallback;
- larger output-budget retry after a length-limited response; and
- OpenAI quality-gate fallback for JobAdder-compatible, Recruiterflow, and
  Outlook resume extraction.

## Explicit boundaries

- Provider recovery means a one-time OAuth token refresh for JobAdder, Dropbox,
  and Outlook. It does not mean automatic migration of a request to a different
  external provider.
- Model fallback remains bounded to the already configured extraction paths.
  General cross-provider LLM failover is not enabled because output contracts,
  privacy, cost, and model-equivalence policy have not yet been agreed.
- Idempotency hashing is deterministic, and the resume batch manifest prevents
  repeated completed work. Real ingestion endpoints still need a durable,
  atomic idempotency record when those write APIs are introduced.
- The current batch runner is restartable command-line background work, not a
  distributed queue. Moving high-volume imports into leased, restartable jobs
  remains a later backlog item.
- Cache single-flight coordination is per Python process. Separate serverless
  instances do not share warm memory, so database query efficiency and durable
  controls still matter.
- No production load, destructive failure injection, credential rotation, or
  live provider traffic was used for this work.

