# ADR-0001: Grounded RAG over task-specific fine-tuning

- Status: Accepted
- Date: 5 August 2026
- Owners: Ch3rry Pi3 Ltd engineering
- Scope: Candidate retrieval, shortlisting, recruiter Q&A, and related factual
  recruitment-intelligence generation

## Decision

Continue using retrieval-augmented generation over the canonical relational,
graph-style, full-text, and vector retrieval layers. Do not fine-tune a model
for current Phase 1 recruitment workflows.

Canonical records and source evidence remain the factual authority. The model
may rank, extract, or explain bounded evidence, but its weights must not become
the store for candidate facts, contact data, employment history, skills,
provenance, or freshness.

Fine-tuning remains a possible later optimisation for a narrow, stable
behaviour—such as a classifier or reranker—not a replacement for retrieval,
citations, permissions, or current source data.

## Context and evidence

The current implementation already has the properties the product needs most:

- all 25,820 canonical candidates in the July benchmark were indexed;
- lexical, semantic, hybrid, and graph-assisted retrieval can be measured
  independently;
- shortlist generation receives a bounded evidence catalogue;
- every fit summary, strength, and gap must cite valid candidate evidence;
- unknown candidate or evidence identifiers fail grounding validation;
- contact routes are excluded from model-ranking evidence, while canonical
  candidate IDs are used only as bounded join keys for validated output;
- source provenance, freshness, CV-backed/profile-only status, employment, and
  skills remain inspectable outside model weights; and
- missing, stale, conflicting, noisy, malicious, malformed, and provider-failure
  cases have deterministic policies.

The available quality evidence does not justify training:

- the saved retrieval benchmark contains only four representative role briefs;
- its reconstructed briefs are not byte-for-byte source job specifications;
- only four of 20 earlier shortlist names remained in the later final lists;
- the profile-evidence tuning rerun was directionally positive but only one
  profile-only candidate reached a final top five; and
- no recruiter-labelled relevance set exists yet.

Fine-tuning on that evidence would risk encoding unverified preferences and
current data-quality problems. It would also make changing candidate facts
harder, weaken provenance, and create a new training-data governance surface.

The current cost evidence does not create an inference-cost emergency. The 5
August prompt-cache evaluation achieved 14/14 warm cache hits, about 90.3%
cached warm input tokens, and about 59.3% aggregate input-cost reduction. Stage
telemetry now records versions, latency, tokens, cached tokens, and estimated
cost so a future economic case can be measured.

## Alternatives considered

### Fine-tune a generative model on candidate and job data

Rejected. Candidate facts change, private data would require a separate
training-data lifecycle, and generated claims would still need fresh retrieval
and citations. Fine-tuning is not a reliable knowledge database.

### Fine-tune immediately for shortlist ordering

Rejected for now. There is no sufficiently broad recruiter-labelled set, no
accepted baseline metric, and no evidence separating retrieval failures from
ranking-behaviour failures.

### Prompt-only generation without retrieval

Rejected. It cannot provide current canonical facts, reliable provenance, or
claim-level grounding and would materially increase hallucination risk.

### Deterministic retrieval without a model

Retained as a baseline, not selected as the only product path. Lexical,
semantic, and structured filters should continue to narrow and score evidence;
the model is useful for bounded synthesis and comparison where its output is
validated.

## Required operating rules

1. Retrieve current canonical evidence at request time or from an explicitly
   freshness-bounded cache.
2. Keep candidate and job facts outside model weights and prompts unless needed
   for the bounded request.
3. Require structured outputs and claim-to-evidence validation for generated
   recommendations.
4. Version retrieval, prompt, workflow, model-profile, and evaluation contracts.
5. Compare lexical, semantic, hybrid, and graph-assisted stages before blaming
   the generator for poor relevance.
6. Preserve deterministic failure behaviour when evidence is absent,
   conflicting, malicious, stale, or malformed.
7. Treat recruiter feedback as evaluation data only after its provenance,
   consent, retention, and quality rules are defined.

## Fine-tuning reconsideration gate

A fine-tuning experiment may be proposed only when every prerequisite below is
met:

- the task and output contract have remained stable across at least two
  production milestones;
- a versioned set contains at least 500 recruiter-labelled role/candidate
  judgements across at least 20 materially different roles;
- at least 100 judgements across at least five roles are held out and never
  used for training or prompt selection;
- the baseline separates retrieval recall, reranking quality, groundedness,
  schema validity, sensitive-data safety, latency, and cost;
- error analysis shows the target problem is learned behaviour rather than
  missing, stale, or incorrectly linked evidence;
- training-data consent, minimisation, deletion, retention, access, and
  provider-processing rules are approved; and
- the deployment has a versioned rollback path and can continue to retrieve
  and cite current evidence.

Promotion requires a held-out result that:

- improves the predeclared primary task metric by at least five percentage
  points relative to the strongest prompt-plus-RAG baseline;
- produces no statistically material regression in retrieval recall;
- keeps groundedness, schema validity, and sensitive-data checks at or above
  the existing release thresholds;
- stays within the approved p95 latency and per-run cost budgets; and
- repeats across at least three evaluation runs without changing the held-out
  set or decision threshold.

Meeting the gate authorises an experiment, not automatic production adoption.

## Consequences

- Engineering effort remains focused on source quality, retrieval, evidence
  presentation, evaluation, and observability.
- New and corrected source data can affect results without retraining.
- Outputs retain inspectable provenance and freshness.
- Prompt/model upgrades remain replaceable behind versioned contracts.
- The system accepts retrieval latency and token costs, then measures and
  optimises them through caching, batching, and stage telemetry.
- Fine-tuning work remains blocked on labelled data and governance, which in
  practice requires external recruiter participation.

## Related evidence

- [Automated AI quality checks](../evaluation/automated_ai_quality_checks.md)
- [Candidate retrieval benchmark](../evaluation/candidate_retrieval_benchmark_2026-07-29.md)
- [Provider prompt-caching evaluation](../prompt_caching_evaluation.md)
- [Stage-level observability](../stage_level_observability.md)
- [North-star architecture](../north_star_architecture.md)
