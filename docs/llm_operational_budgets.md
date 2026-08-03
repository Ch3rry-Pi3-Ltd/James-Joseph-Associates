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
| Candidate query embedding | One validated query; 1,536 output dimensions | Provider-determined / no explicit timeout | $0.005 per call | Add an explicit embedding timeout |
| Document chunk embedding | Default batch of 25; 1,200 characters per chunk with 150-character overlap; 1,536 output dimensions | Provider-determined / no explicit timeout | $0.005 per batch | Add an explicit embedding timeout |

The executable registry is `backend/llm/budgets.py`; tests prevent duplicate
workflow names and keep chat output limits within the provider contract.

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

- Record input, cached-input and output tokens, model/profile version, duration,
  run ID and calculated cost without storing prompt or candidate content.
- Alert when a single request crosses the workflow cost threshold above.
- Add total assembled-prompt token ceilings for shortlist and Q&A.
- Add a bounded embedding timeout.
- Benchmark short and long inputs before changing models or prompt layout.

Provider references:

- https://developers.openai.com/api/docs/models/gpt-4.1-mini
- https://developers.openai.com/api/docs/models/text-embedding-3-large
- https://developers.openai.com/api/docs/guides/prompt-caching
