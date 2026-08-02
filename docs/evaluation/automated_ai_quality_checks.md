# Automated AI Quality Checks

This evaluation layer deliberately avoids recruiter-labelled relevance. It is
the deterministic gate that must pass before subjective UAT is useful.

## Retrieval stages

Run `python scripts/benchmark_candidate_retrieval.py --output <artifact.json>`
to measure full-text, semantic, hybrid, and graph-assisted retrieval separately.
The artifact records latency, result count, stable result fingerprints, ranks,
and candidate identifiers. It hashes the role brief and omits retrieved excerpts,
contact routes, credentials, and other free-text evidence.

Live execution reads the private candidate corpus and sends role-query text to
the configured embedding provider, so it requires explicit data-transfer
authorization. Unit tests exercise the complete stage and artifact contract with
safe synthetic evidence without making that external transfer.

The layers have distinct jobs:

- Full-text retrieval is the lexical baseline and should remain the cheapest.
- Semantic retrieval uses the complete role meaning rather than exact wording.
- Hybrid retrieval must justify fusion by improving coverage or ordering.
- Graph-assisted retrieval may add profile, skill, employment, and linked-company
  evidence, but must justify its additional database latency.

## Embedding and chunking contract

The configured default is OpenAI `text-embedding-3-large`, shortened to 1,536
dimensions to match the current pgvector column. This model is used for semantic
similarity, not factual verification or ranking by itself.

Raw document text uses deterministic paragraph-aware chunks of at most 1,200
characters with 150 characters of overlap. Raw CV chunks remain secondary
evidence. Recruiter-facing candidate retrieval primarily uses structured blocks:

- `profile` for current canonical facts;
- `focus` for title, headline, company, and summary;
- `skills` in bounded groups of eight, deduplicated to 24 skills;
- `summary` for career and CV-source context;
- `resume_context` clipped to a bounded excerpt.

The tests lock these defaults and boundaries so a model, dimension, chunk-size,
or block-policy change cannot happen silently.

## Grounded generation

The shortlist model receives a bounded evidence catalog. Every fit summary,
strength, and gap must contain at least one exact reference from that candidate's
catalog. Unknown candidate IDs or evidence references reject the entire model
output with a `grounding_validation` failure. Contact email addresses and phone
numbers are removed from ranking evidence before it reaches the provider.

The public shortlist keeps recruiter-friendly strings and also returns
`claim_evidence`, allowing automated checks and later UI inspection to trace each
claim back to a CV, profile field, retrieval excerpt, employment record, or linked
canonical entity.

## Stability, schema, and sensitive data

`backend.evaluation.quality_checks` provides:

- stable fingerprints that ignore run IDs and timestamps;
- claim-to-evidence validation;
- forbidden-field scans that report paths but never echo sensitive values;
- validation of the versioned RAG failure matrix.

Pydantic structured-output models reject missing fields, extra fields, malformed
outputs, and claims without evidence references. Stability fingerprints compare
repeat runs without treating generated run IDs as regressions.

## Failure policy

`rag_failure_matrix.json` covers missing, stale, conflicting, noisy, and
malicious evidence, provider timeouts, and malformed structured output. Missing
evidence, timeouts, and malformed output fail closed. Stale or conflicting
evidence is flagged for review; malicious content remains untrusted data and is
never treated as an instruction.

## MCP boundary

MCP integration tests run independently of ChatGPT workspace publication. They
verify bearer authentication, the exact six read-only tools and their annotations,
bounded arguments, shared rate limiting, rate-control failure, safe tool failures,
and metadata-only audit events.
