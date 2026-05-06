# LLM Testing

This document records the current practical testing status of the models used
for structured resume extraction.

It is not the final evaluation harness. It is a working engineering note that
captures:

- which models we tested
- what they cost per 1M tokens
- whether they worked in the current extraction pipeline
- what failed when they did not work
- which Nemotron configuration is currently the strongest baseline

In plain language:

- OpenAI is the current quality baseline
- Nemotron is much cheaper
- Nemotron is not yet as reliable or precise
- we are iterating toward a cheaper production-capable extraction path

## Purpose

The resume-extraction pipeline is now mature enough that model choice matters
for both:

- quality
- cost

That means we need a record of what was actually tested, rather than relying on
memory or one-off console output.

This document exists to answer the practical question:

> Which models have we tested for resume extraction, what did they cost, and
> what happened?

## Pricing Note

The prices below are snapshots taken on **May 6, 2026** from the provider/model
pages used for these tests.

They may change later.

## Current Price Snapshot

| Model / Route | Provider | Input Cost / 1M | Output Cost / 1M | Worked? | Current Assessment |
| --- | --- | ---: | ---: | --- | --- |
| `gpt-5.4` | OpenAI | $2.50 | $15.00 | Yes | Current quality baseline. Live extraction works end to end and follows the schema reliably. |
| `nvidia/nemotron-3-nano-30b-a3b:nitro` | OpenRouter | $0.05 | $0.20 | Partly | Became usable only after reasoning/thinking suppression, but extraction quality remained clearly below the OpenAI baseline. |
| `nvidia/nemotron-3-super-120b-a12b` | OpenRouter | $0.09 | $0.45 | Partly | Best Nemotron candidate so far. Can complete structured extraction under the stronger suppression configuration with a higher output cap, but still has quality and consistency problems. |

## Sources

- OpenAI GPT-5.4 pricing:
  - https://developers.openai.com/api/docs/models/gpt-5.4
- OpenRouter Nemotron 3 Nano pricing:
  - https://openrouter.ai/nvidia/nemotron-3-nano-30b-a3b%3Anitro
- OpenRouter Nemotron 3 Super pricing:
  - https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b-20230311

## Tested Models and Outcomes

### 1. OpenAI GPT-5.4

Role in testing:

- current extraction baseline
- reference point for quality
- reference point for schema compliance

What worked:

- live extraction completed successfully
- structured output matched the schema reliably
- current employer/title, education, employment history, certifications, and
  project extraction were all materially stronger than the early Nemotron runs

Known downside:

- much more expensive than the OpenRouter/Nemotron routes

Current status:

- this is still the model to beat on quality

### 2. Nemotron 3 Nano

Model:

- `nvidia/nemotron-3-nano-30b-a3b:nitro`

Why we tested it:

- extremely low cost
- plausible workhorse candidate if structured extraction quality proved good

What happened initially:

- native structured output was not a clean drop-in fit
- one route rejected the `json_schema` response format
- fallback JSON mode often returned reasoning/prose instead of parseable JSON

What we changed:

- introduced a fallback JSON extraction path
- added OpenRouter request-body controls for reasoning/thinking suppression

Best Nano configuration found so far:

- `thinking: false`
- `reasoning.exclude: true`
- `reasoning.effort: "none"`

What improved:

- Nano became capable of completing the extraction

What remained weak:

- weaker field quality than OpenAI
- thinner evidence/ambiguity notes
- weaker project extraction
- worse precision around experience/tooling extraction

Current status:

- useful as a cost experiment
- not currently strong enough to replace the OpenAI baseline

### 3. Nemotron 3 Super

Model:

- `nvidia/nemotron-3-super-120b-a12b`

Why we tested it:

- still dramatically cheaper than OpenAI
- stronger model than Nano
- more plausible structured extraction candidate

## Nemotron 3 Super Iterations

### A. Native structured output, original setup

Result:

- failed

Main problems:

- non-JSON / reasoning-style output
- incomplete or invalid structured responses
- unstable compliance with the expected schema contract

### B. Native structured output with higher output cap

Change:

- increased `max_output_tokens` significantly

Result:

- became capable of completing a structured extraction

What improved:

- full extraction returned
- core fields such as employer/title and contact details were usable

What was still wrong:

- note-only technologies leaked into `tools_and_platforms`
- quality was still below the OpenAI baseline

### C. First-pass suppression configuration

Configuration:

- `thinking: false`
- `reasoning.exclude: true`
- `reasoning.effort: "none"`

Why we tried it:

- earlier failures suggested that reasoning output and unstable structured
  formatting were interfering with schema compliance

Result:

- this is the **strongest Nemotron Super baseline found so far**

What improved:

- structured extraction completed more reliably
- reasoning/prose contamination reduced
- high-cost OpenAI-like quality was not reached, but the route became
  practically testable

What still went wrong:

- tool contamination from recruiter-note context
- broader-than-ideal `skills`
- only partial project quality
- not fully stable across repeated runs

### D. Exclude-only reasoning configuration

Configuration:

- `reasoning.exclude: true`
- removed `thinking: false`
- removed `reasoning.effort: "none"`

Why we tried it:

- to test whether simply hiding reasoning output was enough

Result:

- worse than the stronger suppression baseline

Main regressions:

- employer/title dropped to `null` in one completed run
- contamination increased
- evidence quality got thinner

Conclusion:

- `exclude: true` alone is not enough for this extraction task

### E. Thinking enabled, effort none, reasoning hidden

Configuration:

- no `thinking: false`
- `reasoning.exclude: true`
- `reasoning.effort: "none"`

Why we tried it:

- to isolate the Nemotron-specific `thinking` control while keeping the other
  settings fixed

Result:

- sometimes completed
- sometimes failed at `llm_invoke`

Conclusion:

- viable enough to test
- not stable enough to adopt as the working baseline

## Prompt Refinement Work

After the configuration experiments, the next constraint became prompt
discipline rather than raw provider connectivity.

The main prompt refinements introduced were:

1. stronger source-priority rules
   - resume text and candidate metadata are primary
   - recruiter notes are secondary

2. explicit bans on note-only contamination
   - future-project discussion tools should not enter candidate experience
   - recruiter brainstorming should not be treated as proven work history

3. stronger evidence/ambiguity expectations
   - evidence notes should cite where support came from
   - ambiguity notes should explain what is unclear without silently
     overriding the final output

4. stricter `skills` discipline
   - `skills` should stay as high-signal domains/core strengths
   - not become a dumping ground for tools or soft skills

## Current Nemotron Super Problems

Even with the better suppression configuration and prompt refinement, the main
remaining problems are:

- **precision drift**
  - note-only technologies can still leak into `tools_and_platforms`

- **schema drift**
  - when the prompt becomes too strict or too expressive, the model sometimes
    tries to "improve" the schema on its own, for example by returning richer
    certification objects instead of the plain string list we asked for

- **quality still below OpenAI**
  - OpenAI remains stronger on:
    - project extraction
    - evidence quality
    - field consistency
    - schema compliance

- **stability issues**
  - some Nemotron Super runs succeed
  - some fail at invocation/validation under the same general setup

## Current Best Nemotron Super Baseline

The strongest baseline found so far for Nemotron Super is:

- `thinking: false`
- `reasoning.exclude: true`
- `reasoning.effort: "none"`
- higher `max_output_tokens` than the OpenAI baseline

This is not production-ready yet, but it is the most defensible place to keep
iterating from.

## Practical Summary

At this point:

- OpenAI GPT-5.4 is still the best extraction baseline on quality
- Nemotron 3 Nano is cheap but weaker
- Nemotron 3 Super is the most promising low-cost alternative
- the current bottleneck for Nemotron Super is:
  - provenance precision
  - schema discipline
  - repeatability

## Next Step

The next step is:

> continue refining the extraction prompt against the stronger Nemotron Super
> baseline, focusing on provenance precision and strict schema obedience

That means the work now is not broad infrastructure work.

It is careful extraction-quality work:

- better source-priority instructions
- tighter field-boundary rules
- more explicit schema-shape reminders
- repeat testing against the same real candidate bundle
