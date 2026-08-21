# Model workflow operating budgets

Checked: 3 August 2026.

This is the explicit cost, context, truncation and latency contract for every
active provider-backed workflow. It is an inventory, not evidence that the
latency and cost targets have already been met. The next performance task must
measure actual usage and compare it with these thresholds.

## Provider facts and local ceilings

The configured chat model is `gpt-4.1-mini`. Its provider limit is 1,047,576
context tokens and 32,768 output tokens. Current standard pricing is $0.40 per
million input tokens, $0.10 per million cached input tokens and $1.60 per million
output tokens. The configured embedding model is `text-embedding-3-large` at
$0.13 per million input tokens. Prices are evidence recorded at the check date;
telemetry should calculate cost from a versioned rate card rather than assuming
these values never change.

All chat workflows use a 60-second provider timeout. Local output ceilings are
1,200 tokens for shortlist and recruiter-answer generation, 2,200 tokens for a
normal CV extraction, and 4,000 tokens for the bounded length retry. These are
well below the provider output maximum.

| Workflow | Input and truncation budget | Output / timeout | Cost alert | Known gap |
| --- | --- | --- | --- | --- |
| Candidate shortlist reranking | Reject role briefs over 50,000 characters; default 25 and hard maximum 100 candidates; bound headline, summary and skills evidence | 1,200 tokens / 60s | $0.03 per call | No final token ceiling on the assembled candidate evidence |
| Recruiter Q&A synthesis | Reject questions over 50,000 characters; default 25 candidates, five context items and four memory turns | 1,200 tokens / 60s | $0.03 per call | No final token ceiling on assembled evidence |
| JobAdder CV extraction | First 18,000 CV characters; preserve cleaned notes; retry only on length failure | 2,200 normally, 4,000 retry / 60s | $0.02 per call | Notes remain unbounded by explicit preservation policy |
| Dropbox CV extraction | Same shared extraction contract | 2,200 normally, 4,000 retry / 60s | $0.02 per call | Notes remain unbounded by explicit preservation policy |
| Outlook CV extraction | Same shared extraction contract | 2,200 normally, 4,000 retry / 60s | $0.02 per call | Notes remain unbounded by explicit preservation policy |
| Recruiterflow CV extraction | Same shared extraction contract | 2,200 normally, 4,000 retry / 60s | $0.02 per call | Notes remain unbounded by explicit preservation policy |
| Candidate query embedding | One validated query; 1,536 output dimensions | 10s / zero automatic retries | $0.005 per call | Full-text retrieval remains available after failure |
| Document chunk embedding | Default batch of 25; 1,200 characters per chunk with 150-character overlap; 1,536 output dimensions | 10s / zero automatic retries | $0.005 per batch | Batch runner owns any deliberate retry |
| Candidate semantic-block embedding | Default batch of 25 bounded profile, skills, and experience blocks; 1,536 output dimensions | 10s / zero automatic retries | $0.005 per batch | Batch runner owns any deliberate retry |

The executable registry is `backend/llm/budgets.py`; tests prevent duplicate
workflow names and keep chat output limits within the provider contract.

## Latency measurement

All active provider-backed paths now pass through the content-free measurement
contract in `backend/llm/telemetry.py`:

- candidate shortlist reranking
- recruiter Q&A synthesis
- JobAdder, Dropbox, Outlook, and Recruiterflow CV extraction attempts
- candidate query, document chunk, and candidate semantic-block embeddings

Each call records end-to-end and provider-request duration, framework overhead,
status, workflow, run ID, attempt, provider, model, and the token counts returned
by the provider. If a streaming call emits token callbacks, the same contract
also calculates time to first token, mean and p95 inter-token latency, and
streamed output throughput. If the provider returns queue, prefill/prompt, or
decode/completion timings, those are normalized to milliseconds. Missing
provider metrics remain explicit `null` values rather than estimates.

Telemetry is written as one structured `model_latency` log record and never
contains prompts, responses, CV text, candidate names, or retrieved evidence.
Failures are measured and re-raised unchanged.

The repeatable smoke command is:

```powershell
.\.venv\Scripts\python.exe -m scripts.measure_model_latency
```

The content-free live smoke on 4 August 2026 measured 1,935.100 ms end to end
for a one-token `gpt-4.1-mini` response and 1,596.519 ms for one 1,536-dimension
`text-embedding-3-large` request. This proves the instrumentation path; it is
not a representative benchmark. Current production calls are non-streaming,
and OpenAI returned no queue, prefill, or decode timing fields, so TTFT, ITL,
and provider-stage timing remain unavailable rather than inferred. The compact
evidence artifact is
`docs/evaluation/model_latency_smoke_2026-08-04.json`.

Representative synthetic short, long, output-ceiling, concurrency, query
embedding, and batch-embedding workloads are now versioned separately in
`docs/model_workload_benchmarking.md`. The first live baseline passed all fixed
latency and estimated-cost gates; future runs can also fail on relative changes
against the committed baseline.

## Prompt caching decision

OpenAI prompt caching is automatic for eligible prompts at least 1,024 tokens
long, and cache hits require an exact shared prefix. Static instructions must
therefore precede variable candidate, role and evidence content. The current
system instructions are likely too short to create a reusable 1,024-token prefix
before variable input begins. Do not claim savings yet. During the next telemetry
slice, capture cached input tokens, request latency and calculated input cost by
workflow, then retain or restructure prompts only if representative runs show a
material cache-hit benefit without harming groundedness.

## Follow-on acceptance criteria

- Calculate cost from the captured input, cached-input, and output tokens using
  a versioned rate card.
- Alert when a single request crosses the workflow cost threshold above.
- Add total assembled-prompt token ceilings for shortlist and Q&A.
- [x] Add a 10-second embedding timeout with zero hidden SDK retries; candidate
  search degrades to deterministic full-text retrieval.
- Benchmark short and long inputs before changing models or prompt layout.

Provider references:

- https://developers.openai.com/api/docs/models/gpt-4.1-mini
- https://developers.openai.com/api/docs/models/text-embedding-3-large
- https://developers.openai.com/api/docs/guides/prompt-caching
