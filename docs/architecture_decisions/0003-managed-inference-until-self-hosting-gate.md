# ADR-0003: Managed inference until the self-hosting gate is met

- Status: Accepted
- Date: 5 August 2026
- Owners: Ch3rry Pi3 Ltd engineering
- Scope: Chat-model, extraction-model, reranking-model, and embedding inference

## Decision

Keep the current managed-provider inference architecture. Do not benchmark or
deploy vLLM, SGLang, llama.cpp, or another self-hosted inference engine now.

An engine comparison becomes authorised only when the executable admission gate
in `backend/llm/self_hosted_gate.py` passes. Unknown measurements fail closed.
Passing the gate authorises a bounded benchmark; it does not authorise a
production migration.

The current content-free assessment is committed at
`docs/evaluation/self_hosted_inference_gate_2026-08-05.json`. Its decision is
`do_not_benchmark`.

## Why the gate exists

Self-hosting can improve control, locality, unit economics at sustained scale,
or continuity, but it also creates a new production service. The real comparison
is not API token price versus GPU rental. It includes:

- model quality and licence restrictions;
- weights, quantisation, runtime, and driver compatibility;
- GPU memory for weights plus KV cache at target context and concurrency;
- batching, queueing, autoscaling, warm-up, and cold capacity;
- security patching, access control, network isolation, and audit logging;
- monitoring, incident response, failover, backups, and upgrades; and
- engineering and operational ownership.

The gate requires both readiness and a material benefit. Technical curiosity on
its own is not sufficient reason to create that operational surface.

## Benchmark admission rule

Benchmarking is authorised only when:

```text
all readiness prerequisites pass
AND
at least one material-benefit trigger passes
```

### Readiness prerequisites

| Prerequisite | Passing threshold |
| --- | --- |
| Representative workload | At least 100 production-shaped samples, every active workflow covered, with no private content retained in the artifact |
| Evaluation | Groundedness, schema, sensitive-data, stability, task-quality, latency, and cost release criteria approved |
| Candidate model | Exact model/version selected and its commercial use, redistribution, data, and output licence terms approved |
| Security boundary | Hosting region, network, authentication, encryption, logging, retention, patching, and incident handling reviewed |
| Operations ownership | A named owner accepts deployment, monitoring, upgrades, on-call response, rollback, and capacity planning |
| Hardware readiness | Benchmark hardware is available and the planned weights plus runtime plus KV cache fit at target context/concurrency with at least 20% memory headroom |
| TCO evidence | Positive monthly managed-provider cost and fully loaded monthly self-hosted TCO estimates exist on the same workload |

### Material-benefit triggers

At least one of these must pass:

| Driver | Passing threshold |
| --- | --- |
| Privacy or residency | An approved policy or contract prohibits third-party processing for at least one core model workflow |
| Sustained scale | At least 50 million billable tokens per month, or at least 1.0 request/second sustained over a measured 15-minute peak window |
| Economics | Managed-provider spend is at least $1,000/month and fully loaded self-hosted TCO is no more than 70% of it |
| Latency | Production p95 is at least 125% of its approved budget and provider time is at least 70% of end-to-end model latency |
| Continuity | An approved provider-outage requirement remains unmet and requires recovery within 15 minutes or less |

The thresholds are admission controls, not promises that self-hosting will win.
They should be versioned if operating conditions or business requirements
materially change.

## Current assessment

The 5 August assessment fails all seven readiness prerequisites and meets no
material-benefit trigger.

Evidence available now:

- the live workload baseline contains 12 synthetic requests across five shapes,
  not representative production traffic across the nine active workflow budget
  entries;
- all five fixed latency and cost gates passed;
- long-chat p95 was 5,988.712 ms against a 30,000 ms alert ceiling;
- the complete workload baseline cost an estimated $0.003122980;
- the separate prompt-cache run achieved 14/14 warm cache hits and about 59.3%
  aggregate input-cost reduction;
- the planning estimate for 20,000 `gpt-4.1-mini` CV extractions is £60.56,
  not an observed recurring bill;
- production token volume, sustained request rate, and trailing provider spend
  have not yet been aggregated;
- no approved privacy/residency rule currently prohibits the configured managed
  provider for a core workflow;
- no unmet 15-minute provider-outage recovery requirement is recorded; and
- no candidate open-weight model/licence, hardware quote, capacity plan,
  security review, operations owner, or fully loaded TCO has been approved.

Running an engine benchmark now would therefore answer a technology-demo
question, not a product or operating question.

## Evidence collection for reassessment

Re-evaluate at a production milestone or when a privacy/continuity requirement
changes. Use a rolling 30-day, content-free telemetry window and record:

- calls, input/cached/output tokens, and estimated provider cost by workflow;
- p50/p95 latency, provider share, errors, retries, and concurrency;
- context-length and output-length distributions;
- approved latency, availability, recovery, privacy, and residency requirements;
- candidate model/version and licence review;
- model weight size and precision;
- KV-cache calculation at target context, batch size, and concurrency;
- hardware purchase/rental, energy, storage, network, support, and engineering
  cost; and
- named security and operational ownership.

Do not store prompts, responses, CV text, candidate/contact identifiers, or
retrieved evidence in the gate artifact.

## Benchmark contract after admission

If the gate later passes, compare only a representative, fixed workload and use
the smallest engine shortlist justified by deployment constraints. The benchmark
must record:

- exact model, weights revision, licence, quantisation, engine and version;
- hardware, VRAM, memory headroom, driver/runtime, region, and hourly cost;
- context length, prompt/output sizes, concurrency, batching, and cache policy;
- quality, groundedness, schema, and sensitive-data evaluation results;
- TTFT, inter-token latency, end-to-end p50/p95/p99, throughput, queue time,
  warm-up, failure rate, and recovery behaviour;
- idle and loaded cost per successful request and projected monthly TCO; and
- operational failure, upgrade, rollback, and managed-provider fallback tests.

No production promotion is allowed unless the candidate:

- passes the same quality and safety release gates as the managed baseline;
- fits target concurrency with at least 20% memory headroom;
- meets approved p95 latency and availability objectives under load;
- either resolves the approved privacy/continuity driver or reduces fully
  loaded 12-month TCO by at least 30%; and
- has signed security, licence, operational ownership, and rollback approval.

## Consequences

- No model weights, inference engines, GPU runtimes, or serving infrastructure
  are added now.
- Managed-provider costs and latency continue to be observed through the
  existing content-free telemetry.
- Engineering remains focused on measured product bottlenecks rather than an
  unused serving platform.
- Self-hosting remains a controlled option with an executable, reviewable path.

## Related evidence

- [Model workflow operating budgets](../llm_operational_budgets.md)
- [Model workload benchmarking](../model_workload_benchmarking.md)
- [Provider prompt-caching evaluation](../prompt_caching_evaluation.md)
- [Stage-level observability](../stage_level_observability.md)
- [RAG over fine-tuning](0001-rag-over-fine-tuning.md)
- [Bounded workflows over multi-agent orchestration](0002-bounded-workflows-over-multi-agent.md)

