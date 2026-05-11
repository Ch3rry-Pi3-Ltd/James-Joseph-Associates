# LLM Foundation

This document records the current LLM foundation work in the backend.

It is a status and explanation document, not a full model-comparison or
evaluation guide.

In plain language:

- the backend can describe model choices locally
- the backend can build real provider-backed LangChain chat models
- OpenAI-backed live extraction is working end to end
- provider and extraction layers are tested locally
- evaluation and model-comparison work are still the next major gap

## What Exists Now

Current files:

```text
backend/llm/models.py
backend/llm/providers.py
backend/services/extraction_quality.py
tests/unit/test_llm_models.py
tests/unit/test_llm_providers.py
tests/unit/test_extraction_quality.py
```

These files define and test:

- a local model-description layer
- a provider factory layer
- settings-backed provider configuration for real model calls
- a deterministic non-LLM extraction quality scorer

The current layer can describe:

- model provider
- model name
- model purpose
- temperature
- max output tokens
- whether a profile is deterministic-style

## Current Model Concepts

### Model Provider

`ModelProvider` describes who supplies the model.

Current provider identifiers:

```text
openai
openrouter
nemotron
perplexity
```

In plain language:

- provider = where the model comes from
- model name = which model from that provider

### Model Purpose

`ModelPurpose` describes why the backend would use a model.

Current purpose identifiers:

```text
reasoning
extraction
summarisation
classification
utility
```

In plain language:

- purpose = what job the model is meant to do

Examples:

- reasoning for harder judgement tasks
- extraction for pulling structured fields from text
- summarisation for shortening notes or documents
- classification for assigning labels
- utility for small helper tasks

### Model Profile

`ModelProfile` describes one local model configuration.

It includes:

```python
provider: ModelProvider
model_name: str
purpose: ModelPurpose
temperature: float
max_output_tokens: int
```

It is a frozen dataclass.

That means profiles are not meant to be changed in place.

Instead of mutating a shared profile, future code should create a new profile if
it needs different values.

## Current Defaults

The current default utility profile is:

```python
DEFAULT_UTILITY_MODEL_PROFILE = ModelProfile(
    provider=ModelProvider.OPENAI,
    model_name="gpt-5.4-mini",
    purpose=ModelPurpose.UTILITY,
    temperature=0.0,
    max_output_tokens=500,
)
```

The current default reasoning profile is:

```python
DEFAULT_REASONING_MODEL_PROFILE = ModelProfile(
    provider=ModelProvider.OPENAI,
    model_name="gpt-5.4",
    purpose=ModelPurpose.REASONING,
    temperature=0.2,
    max_output_tokens=1200,
)
```

These defaults now feed real provider-backed clients and extraction services.

They are still configuration choices rather than permanent architecture.
Provider choices, model names, and cost assumptions are expected to keep
evolving as evaluation data improves.

## Deterministic-Style Profiles

The helper:

```python
is_deterministic_profile(profile)
```

currently checks whether:

```python
profile.temperature == 0.0
```

In plain language:

- temperature zero means "try to be predictable"
- this is useful for helper tasks and structured outputs
- it does not guarantee perfect provider-level determinism
- it only checks local configuration

## What This Proves

This foundation now proves:

- provider strings are constrained
- model purposes are constrained
- default profiles are available
- profiles are immutable
- deterministic-style configuration can be detected locally
- tests can verify model configuration locally
- provider clients can be constructed from model profiles
- extraction services can consume provider-backed chat models cleanly

## What This Does Not Do Yet

This layer still does not:

- implement OpenRouter transport yet
- implement Nemotron transport yet
- implement Perplexity transport yet
- choose providers automatically based on cost or quality
- maintain a production evaluation harness
- run GraphRAG retrieval/matching workflows
- log and score extraction quality at scale

Some of that is still intentional.

The immediate goal was to establish a clean provider boundary before broadening
to multi-model routing and evaluation.

## What Exists Now

The backend now has:

- `ModelProfile` and related enums in `backend/llm/models.py`
- provider construction in `backend/llm/providers.py`
- settings-backed OpenAI key and timeout configuration in `backend/settings.py`
- live extraction orchestration in `backend/services/resume_extraction.py`
- a local integration script in `scripts/run_resume_extraction.py`
- a deterministic extraction quality gate in `backend/services/extraction_quality.py`
- a separate deterministic CV source-richness assessment in `backend/services/extraction_quality.py`
- a batch calibration runner in `scripts/run_resume_extraction_batch.py`
- a JobAdder candidate-listing helper script in `scripts/list_jobadder_candidates.py`
- an accepted-output persistence path in `backend/services/resume_extraction_persistence.py`

In plain language:

- profiles describe what model we want
- providers build the real client
- services use that client for structured extraction
- the quality gate can route weak first-pass extractions to a stronger fallback
- the source-richness score can describe whether a CV is rich, adequate, or sparse
- the batch runner now uses two skip identities:
  - a full contract-aware fingerprint for unchanged successful candidates
  - a source-only fingerprint for unchanged no-resume source failures
- accepted `pass` results can now be persisted into the canonical schema on an opt-in basis
  through the CLI runners, covering:
  - source records
  - person
  - candidate
  - current company
  - resume document
  - candidate skills

## Why Multi-Provider Routing Is Still Deferred

The backend now has a real OpenAI path, but broader routing should still wait
for clearer evidence on:

- which extraction model gives acceptable quality per cost
- whether OpenRouter should become the default route
- which workloads justify stronger models versus cheaper workhorses
- how extraction quality is scored over time
- how provider fallback and retries should behave in production

Until that is clearer, `ModelProfile` remains the stable local description and
the provider layer remains deliberately thin.

## How This Will Evolve

Possible next LLM modules or extensions:

```text
backend/llm/structured_output.py
backend/llm/prompts.py
backend/llm/observability.py
backend/evals/
```

Possible future responsibilities:

- route `ModelProfile` values through multiple providers
- choose provider/model based on `ModelPurpose`
- validate structured output schemas
- centralise prompt templates
- support provider fallback
- support test doubles for LLM calls
- log latency, token usage, and estimated cost
- run sampled extraction evaluations

## Current Development Status

Done:

- local model provider enum
- local model purpose enum
- local model profile dataclass
- default utility model profile
- default reasoning model profile
- deterministic-style profile helper
- OpenAI-backed provider factory
- settings-backed provider configuration
- unit tests for model configuration
- unit tests for provider construction
- live structured resume extraction using a real model

Not done yet:

- provider fallback beyond the current extraction quality-gate flow
- extraction monitoring metrics
- evaluation harness
- systematic batch-score calibration across a wider real candidate sample

Recommended next project step:

- calibrate the deterministic quality gate on a real multi-candidate batch
- tighten the rerun/review thresholds using real disagreement cases
- widen the accepted-output persistence slice beyond the current narrow canonical write path
- then move from local JSON artifacts toward richer persistence and reporting
