# Provider prompt-caching evaluation

Checked: 5 August 2026.

## Decision

Keep OpenAI's automatic prompt caching enabled and preserve a stable-first
prompt layout for long, repeated workflows. Do not add a production
`prompt_cache_key` to the current low-volume `gpt-4.1-mini` workflows yet: this
evaluation found no material cache-hit, cost, or latency advantage over
automatic routing.

Reconsider an explicit key if traffic becomes sustained or concurrent, cache
hit rates regress, or the application migrates to a model whose caching contract
benefits from explicit breakpoints. The next stage-level observability work
should retain `cached_input_tokens` alongside latency and cost so that decision
can be revisited with production-shaped evidence.

## Method

The harness ran two isolated sequences against `gpt-4.1-mini`:

1. a stable prefix with a unique `prompt_cache_key`;
2. the same shape using automatic cache routing without a key.

Each sequence contained one cold request followed immediately by seven warm
requests. Every request used a newly generated, synthetic recruitment-shaped
prefix of roughly 15,500 characters, with stable instructions and retrieval
context first and only the small final user instruction changing. A unique
isolation marker prevented earlier benchmark traffic from creating a false
cold-start cache hit.

The artifact contains no prompts, responses, cache keys, candidate records, CV
text, or client data. It records only variant and phase labels, latency, token
usage, estimated cost, and completion status.

OpenAI's current guidance says cache matching requires an exact shared prefix,
that static material should come before variable material, and that eligible
requests report cache reads through `cached_tokens`. The guide also documents
automatic caching for long prompts and `prompt_cache_key` as an optional routing
aid:

- <https://developers.openai.com/api/docs/guides/prompt-caching>

## Live result

All `16` requests succeeded. All `14` requests after the two cold warm-up calls
reported cache hits.

| Variant | Warm hits | Cached-token ratio | Cold latency | Warm average | Warm p50 / p95 | Overall input-cost reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stable prefix with key | 7/7 | 90.39% | 1,238.388 ms | 743.540 ms | 678.277 / 1,121.809 ms | 59.32% |
| Automatic routing | 7/7 | 90.32% | 864.266 ms | 775.455 ms | 760.958 / 983.987 ms | 59.27% |

Across both variants:

- warm cache-hit rate was `100%` (`14/14`);
- roughly `90.3%` of warm input tokens were served from cache;
- estimated input cost was `$0.0066432`, compared with `$0.0163200` if all
  input tokens had been billed uncached;
- estimated input-cost saving was `$0.0096768`, or about `59.3%`, including the
  two necessary cold requests;
- each successful warm request cached `2,304` of roughly `2,550` input tokens,
  reducing that request's estimated input cost by about `67.8%`; and
- total estimated cost, including output tokens, was `$0.0068736`.

The keyed variant's warm average was about `4.1%` faster than automatic routing,
but both variants achieved identical hit rates and effectively identical input
cost. With only seven warm timings per variant and normal provider latency
variation, that difference is not strong enough to justify extra production
configuration.

## Re-running

Run the content-free evaluation with the committed sample size:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_prompt_caching `
  --repetitions 8 `
  --output-json docs\evaluation\prompt_caching_evaluation_YYYY-MM-DD.json `
  --fail-on-incomplete
```

The committed machine-readable result is
`docs/evaluation/prompt_caching_evaluation_2026-08-05.json`.
