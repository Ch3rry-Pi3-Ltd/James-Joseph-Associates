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
tests/unit/test_llm_models.py
tests/unit/test_llm_providers.py
```

These files define and test:

- a local model-description layer
- a provider factory layer
- settings-backed provider configuration for real model calls

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

In plain language:

- profiles describe what model we want
- providers build the real client
- services use that client for structured extraction

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

- OpenRouter provider integration
- Nemotron/OpenRouter extraction benchmarking
- provider fallback
- extraction monitoring metrics
- evaluation harness
- systematic model-quality comparison

Recommended next project step:

- keep the provider layer thin and explicit
- add OpenRouter/Nemotron support behind the same provider interface
- build the evaluation harness before changing the default extraction model
- add extraction run monitoring before scaling volume
