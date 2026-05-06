# LLM Pricing Comparison

This document records the current model-pricing comparison and batch-cost
estimates discussed during the resume-extraction model evaluation work.

It is intended as a practical reference for:

- comparing likely extraction-model candidates
- understanding the cost gap between OpenAI and OpenRouter routes
- estimating large-batch processing cost for CV extraction

## Pricing Note

- Date reference: **May 6, 2026**
- USD to GBP conversion used: **1 USD = £0.735**

This means all GBP figures below are converted estimates based on that rate,
not provider-native GBP billing.

## Model Pricing Snapshot in GBP

| Model | Family | Input / 1M tokens | Output / 1M tokens | Notes for this extraction use case |
| --- | --- | ---: | ---: | --- |
| `nvidia/nemotron-3-super-120b-a12b` | OpenRouter baseline | **£0.07** | **£0.37** | Cheapest baseline tested seriously so far; promising cost, unstable quality |
| `gpt-4.1-nano` | GPT-4.1 | £0.07 | £0.29 | Very cheap, but likely too weak |
| `gpt-5-nano` | GPT-5 | £0.04 | £0.29 | Cheapest OpenAI option; probably too weak for this task |
| `gpt-5.4-nano` | GPT-5.4 | £0.15 | £0.92 | Worth testing if we want a low-cost OpenAI floor |
| `gpt-5-mini` | GPT-5 | £0.18 | £1.47 | Strong cost candidate |
| `gpt-4.1-mini` | GPT-4.1 | £0.29 | £1.18 | Very plausible structured-extraction candidate |
| `gpt-5.4-mini` | GPT-5.4 | £0.55 | £3.31 | Best "cheaper but still serious" OpenAI candidate |
| `o4-mini` | o-series | £0.81 | £3.23 | Reasoning-capable, but less attractive than `gpt-5.4-mini` here |
| `gpt-5.1` | GPT-5 | £0.92 | £7.35 | Stronger, but much pricier than mini-tier options |
| `gpt-5` | GPT-5 | £0.92 | £7.35 | Older GPT-5 line; viable but not first-choice next test |
| `gpt-4.1` | GPT-4.1 | £1.47 | £5.88 | Strong non-reasoning candidate |
| `gpt-5.4` | GPT-5.4 | £1.84 | £11.03 | Current expensive benchmark |
| `gpt-5.5` | GPT-5.5 | £3.68 | £22.05 | Highest-cost OpenAI option here; likely overkill for this use case |

## Estimated Cost for 20,000 CV Extractions in GBP

### Assumption Used

Per CV extraction:

- **5,500 input tokens**
- **1,200 output tokens**

This is a working estimate for the current extraction shape:

- CV text
- cleaned notes
- prompt/schema overhead
- structured JSON output

If prompt size or output size grows, these figures increase proportionally.

| Model | Estimated cost per CV | Estimated cost for 20,000 CVs |
| --- | ---: | ---: |
| `gpt-5-nano` | **£0.000555** | **£11.10** |
| `gpt-4.1-nano` | £0.000757 | £15.14 |
| `nvidia/nemotron-3-super-120b-a12b` | £0.000845 | £16.91 |
| `gpt-5.4-nano` | £0.001911 | £38.22 |
| `gpt-5-mini` | £0.002775 | £55.49 |
| `gpt-4.1-mini` | £0.003028 | £60.56 |
| `gpt-5.4-mini` | £0.007001 | £140.02 |
| `o4-mini` | £0.008328 | £166.55 |
| `gpt-5` | £0.013873 | £277.46 |
| `gpt-5.1` | £0.013873 | £277.46 |
| `gpt-4.1` | £0.015141 | £302.82 |
| `gpt-5.4` | £0.023336 | £466.73 |
| `gpt-5.5` | £0.046673 | £933.45 |

## Practical Summary

The important comparison points for the current extraction work are:

| Model | 20,000 CV estimate |
| --- | ---: |
| `nvidia/nemotron-3-super-120b-a12b` | **£16.91** |
| `gpt-5-mini` | **£55.49** |
| `gpt-4.1-mini` | **£60.56** |
| `gpt-5.4-mini` | **£140.02** |
| `gpt-5.4` | **£466.73** |
| `gpt-5.5` | **£933.45** |

For current purposes, the most sensible OpenAI candidates to test next remain:

1. `gpt-5.4-mini`
2. `gpt-4.1-mini`
3. `gpt-5-mini`

These are the strongest balance of:

- structured-output support
- likely extraction quality
- meaningful cost reduction relative to `gpt-5.4`

## Sources

- OpenAI pricing:
  - https://openai.com/api/pricing/
- OpenAI models overview:
  - https://developers.openai.com/api/docs/models
- GPT-5.5:
  - https://developers.openai.com/api/docs/models
- GPT-5.4:
  - https://developers.openai.com/api/docs/models/gpt-5.4
- GPT-5.4 mini:
  - https://developers.openai.com/api/docs/models/gpt-5.4-mini
- GPT-5.4 nano:
  - https://developers.openai.com/api/docs/models/gpt-5.4-nano
- GPT-5.1:
  - https://developers.openai.com/api/docs/models/gpt-5.1
- GPT-5:
  - https://developers.openai.com/api/docs/models/gpt-5
- GPT-5 mini:
  - https://developers.openai.com/api/docs/models/gpt-5-mini
- GPT-5 nano:
  - https://developers.openai.com/api/docs/models/gpt-5-nano
- GPT-4.1:
  - https://developers.openai.com/api/docs/models/gpt-4.1
- GPT-4.1 mini:
  - https://developers.openai.com/api/docs/models/gpt-4.1-mini
- GPT-4.1 nano:
  - https://developers.openai.com/api/docs/models/gpt-4.1-nano
- `o4-mini`:
  - https://developers.openai.com/api/docs/models/o4-mini
- Nemotron 3 Super pricing:
  - https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b/pricing
- USD/GBP conversion reference used:
  - https://currencylive.com/exchange-rate/usd-to-gbp-exchange-rate-today/
