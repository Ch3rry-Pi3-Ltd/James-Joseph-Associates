# Model workload benchmarking

Checked: 4 August 2026.

This benchmark makes latency and estimated-cost regressions visible for the
configured OpenAI chat and embedding models. It complements the per-call
telemetry in `backend/llm/telemetry.py`; it does not use live candidate records
and it is not a recruiter-quality evaluation.

## Workloads

The harness uses fixed synthetic inputs and records no prompt or response text:

| Scenario | Shape | Repetitions / concurrency | Output ceiling |
| --- | --- | --- | --- |
| Short chat, serial | 107 characters across two messages | 2 / 1 | 32 tokens |
| Long chat, serial | 11,276-character synthetic role and 25-candidate pool | 2 / 1 | 1,200 tokens |
| Short chat, concurrent | Same short input | 4 / 2 | 32 tokens |
| Query embedding | One 40-character search query | 2 / 1 | Provider-defined vector |
| Batch embedding | 25 synthetic blocks, 25,600 characters total | 2 / 1 | 1,536 dimensions each |

Each scenario fails closed if a request fails, provider usage is absent, p95
latency exceeds its fixed alert ceiling, or average estimated cost exceeds its
fixed ceiling. These generous first ceilings are regression alarms, not user
experience SLOs. The small sample counts keep routine checks bounded; they are
not statistically strong capacity-test results.

Costs use the versioned 3 August 2026 price card in
`backend/llm/benchmarking.py`. Chat estimates separate cached and uncached input
tokens when the provider returns that detail.

## First live baseline

The first bounded run passed all five scenario gates with no provider failures:

| Scenario | p50 | p95 | Average estimated cost |
| --- | ---: | ---: | ---: |
| Short chat, serial | 808.341 ms | 2,035.296 ms | $0.000021200 |
| Long chat, serial | 4,383.926 ms | 5,988.712 ms | $0.000947600 |
| Short chat, concurrency 2 | 956.647 ms | 1,202.234 ms | $0.000021200 |
| Query embedding | 223.708 ms | 1,829.852 ms | $0.000001040 |
| 25-item embedding batch | 442.379 ms | 808.665 ms | $0.000549250 |

The entire 12-request baseline cost an estimated $0.003122980. The second long
chat request reported 2,176 cached input tokens. That observation has now been
followed by the dedicated 16-request evaluation in
`docs/prompt_caching_evaluation.md`: all 14 warm requests hit the cache and the
overall estimated input-cost reduction was about 59.3%. Provider queue,
prefill, decode, TTFT, and ITL remained unavailable for these non-streaming
calls.

The committed machine-readable baseline is
`docs/evaluation/model_workload_benchmark_2026-08-04.json`.

## Running and comparing

Run the fixed gates and write a new artifact:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_model_workloads `
  --output-json docs\evaluation\model_workload_benchmark_YYYY-MM-DD.json `
  --fail-on-regression
```

Compare a new run with this baseline as well as the fixed gates:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_model_workloads `
  --baseline-json docs\evaluation\model_workload_benchmark_2026-08-04.json `
  --output-json docs\evaluation\model_workload_benchmark_YYYY-MM-DD.json `
  --fail-on-regression
```

The relative comparison fails when like-for-like p95 latency exceeds 125% of
the baseline or average cost exceeds 110%. Version a new baseline deliberately
when the provider, model, price card, prompt shape, or accepted operating target
changes; do not overwrite historical evidence.
