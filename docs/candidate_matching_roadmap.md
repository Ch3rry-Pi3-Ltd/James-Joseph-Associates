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

- [ ] Add a new UI tab/page for candidate matching
- [ ] Add a large free-text job description input
- [ ] Add submit/run action
- [ ] Call the backend search endpoint from the UI
- [ ] Show ranked results with:
  - candidate name
  - title
  - company
  - resume updated date
  - match snippet

## Milestone 3: Top-3 Match Endpoint

Goal: move from raw search results to a shortlist suitable for a recruiter
workflow.

- [ ] Add backend endpoint for job-description matching
- [ ] Accept one free-text job description
- [ ] Retrieve an initial candidate pool from Supabase
- [ ] Return the top 3 strongest matches
- [ ] Include brief machine-readable reasons for each match

## Milestone 4: LLM Reranking

Goal: improve quality beyond plain text retrieval.

- [ ] Use resume search as first-pass retrieval
- [ ] Pull top 25-50 candidates from canonical resumes
- [ ] Send those candidates plus the job description to OpenAI for reranking
- [ ] Return:
  - top 3 final matches
  - fit summary
  - risks / gaps
  - rationale

## Milestone 5: Better Retrieval

Goal: improve recall and relevance before full graph-style expansion.

- [ ] Add embeddings for job descriptions
- [ ] Add embeddings for canonical resumes or candidate summaries
- [ ] Implement hybrid retrieval:
  - full-text search
  - embeddings similarity
  - structured ranking signals
- [ ] Add optional structured filters:
  - location
  - title keywords
  - company background
  - skill keywords

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

Build the demo UI page and wire it to the existing resume-search API.

That is the fastest route to a visible milestone without overengineering the
retrieval stack too early.
