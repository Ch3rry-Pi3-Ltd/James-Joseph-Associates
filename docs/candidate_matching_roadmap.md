# Candidate Matching Roadmap

## Purpose

This document tracks the staged path from the current ingestion/search backend
to a demoable candidate-matching UI that Tom can use.

The immediate milestone is simple:

- paste a free-text job description
- search the canonical CV corpus already stored in Supabase
- return the top 3 candidate matches with brief reasons

## Current State

- [x] Canonical CV ingestion pipeline in place across major sources
- [x] Canonical resume text persisted on `documents.extracted_text`
- [x] Direct Dropbox ingestion largely blitzed
- [x] Resume search API added:
  - `GET /api/v1/candidates/search-resumes`
- [x] Candidate shortlist API added:
  - `POST /api/v1/candidates/match-job-description`
- [x] Candidate matching UI page added:
  - `/match`
- [x] LLM shortlist/reranking flow added on top of first-pass retrieval
- [x] Dropbox ingestor failure diagnostics improved

## Milestone 1: Searchable CV Corpus

Goal: prove we can retrieve relevant candidates from the existing Supabase CV
store.

- [x] Add backend CV search query over canonical current resumes
- [x] Expose candidate resume search through API
- [ ] Smoke test search quality against real role-style queries
- [ ] Tune ranking weights for:
  - candidate name
  - current title
  - company
  - resume title
  - resume text

## Milestone 2: Demo UI for Tom

Goal: give Tom something he can open and play with.

- [x] Add a new UI tab/page for candidate matching
- [x] Add a large free-text job description input
- [x] Add submit/run action
- [x] Call the backend search endpoint from the UI
- [x] Show ranked results with:
  - candidate name
  - title
  - company
  - resume updated date
  - match snippet

## Milestone 3: Top-3 Match Endpoint

Goal: move from raw search results to a shortlist suitable for a recruiter
workflow.

- [x] Add backend endpoint for job-description matching
- [x] Accept one free-text job description
- [x] Retrieve an initial candidate pool from Supabase
- [x] Return the top 3 strongest matches
- [x] Include brief machine-readable reasons for each match

## Milestone 4: LLM Reranking

Goal: improve quality beyond plain text retrieval.

- [x] Use resume search as first-pass retrieval
- [x] Pull top 25-50 candidates from canonical resumes
- [x] Send those candidates plus the job description to OpenAI for reranking
- [x] Return:
  - top 3 final matches
  - fit summary
  - risks / gaps
  - rationale

## Milestone 5: Better Retrieval

Goal: improve recall and relevance before full graph-style expansion.

- [ ] Enable `pgvector` in Supabase for production and local environments
- [x] Define the canonical embedding target:
  - structured candidate semantic blocks built from canonical fields
  - optional raw resume chunks as secondary evidence
  - job-spec semantic blocks/chunks
- [x] Define the first embedding model/runtime choice:
  - `text-embedding-3-large`
  - shortened to `1536` dimensions to fit the existing `document_chunks.embedding` column
- [ ] Add a dedicated `candidate_semantic_blocks` store for candidate-level retrieval
- [ ] Backfill structured candidate semantic blocks from canonical fields already in Supabase:
  - person profile fields
  - candidate fields
  - candidate skills
  - linked current-resume metadata
- [ ] Embed those structured candidate semantic blocks
- [ ] Keep raw resume chunk embeddings as secondary evidence, not the primary retrieval surface
- [x] Build the first chunking/backfill foundation over existing canonical text
- [x] Prove the first tiny raw-chunk semantic sample on a handful of real records before broad rollout
- [ ] Prove the first structured semantic-block sample on a handful of real candidates before broad rollout
- [ ] Implement hybrid retrieval:
  - full-text search
  - semantic block vector similarity
  - reciprocal rank fusion or equivalent merge
  - structured ranking signals
- [ ] Backfill semantic retrieval artefacts for already-ingested canonical records without reingesting source CVs
- [ ] Update ingestion so new resumes refresh semantic blocks during normal persistence
- [ ] Add optional structured filters:
  - location
  - title keywords
  - company background
  - skill keywords
- [ ] Evaluate retrieval quality against real Tom role briefs before moving deeper into GraphRAG

## Milestone 6: GraphRAG-Style Expansion

Goal: make retrieval richer and more explainable.

- [ ] Expand retrieval across linked canonical entities:
  - candidate
  - person
  - skills
  - companies
  - resume documents
  - source provenance
- [ ] Use graph-style evidence assembly before final ranking
- [ ] Surface explainable match evidence in the UI

## Milestone 7: Recruiter Workflow Improvements

Goal: turn the demo into something closer to a working internal tool.

- [ ] Add saveable searches
- [ ] Add side-by-side candidate comparison
- [ ] Add “why this candidate” explanations
- [ ] Add export/share of shortlist output
- [ ] Add feedback loop for good/bad matches

## Immediate Next Slice

Implement structured semantic retrieval on top of the existing corpus and shortlist flow.

Specifically:

- enable `pgvector`
- build structured candidate semantic blocks from canonical candidate/profile/skill fields
- embed those blocks with `text-embedding-3-large` at `1536` dimensions
- prove the path on a small real candidate sample before any broad backfill
- add hybrid retrieval for `/match`
- keep raw resume chunks available as secondary evidence later
- keep the current LLM reranker as the final shortlist stage
