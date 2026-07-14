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
- [x] Outlook CV archive ingested into the canonical Dropbox-backed resume path
- [x] Current resumes are downloadable through the candidate UI/backend route
- [x] Resume chunks and embeddings backfilled across the current searchable corpus
- [x] Resume search API added:
  - `GET /api/v1/candidates/search-resumes`
- [x] Candidate shortlist API added:
  - `POST /api/v1/candidates/match-job-description`
- [x] Candidate matching UI page added:
  - `/match`
- [x] LLM shortlist/reranking flow added on top of first-pass retrieval
- [x] Dropbox ingestor failure diagnostics improved

## Tom Idea Buckets

Tom's handwritten notes imply three practical buckets.

### Bucket 1: Clearly Buildable

These are strong product requirements that we can build directly.

- Vacancy-to-candidate matching.
- Company-to-candidate discovery.
- Candidate/company/hiring-manager cross-search.
- Surfacing who currently works somewhere.
- Surfacing prior notes, emails, dates, and interaction history.
- LLM shortlist generation on top of grounded retrieval.
- Chatbot/agent UI on top of the unified data layer.

### Bucket 2: Buildable, But Dependent On Source Access And Data Quality

These are feasible, but only if we have real source coverage, stable IDs, and
enough usable context.

- Keeping profiles fresh automatically across sources.
- Syncing CRM, CV, email, and LinkedIn-derived data together.
- Hiring-manager discovery from company/vacancy signals.
- Relationship warmth scoring.
- "Who is best connected to this company?" style answers.

### Bucket 3: Possible In Principle, But Risky Or Weak As A Dependency

These are not impossible, but they are poor foundations if they depend on
fragile vendor behaviour, scraping, or limited control.

- Heavy LinkedIn scraping workflows.
- Anything dependent on third-party tools without stable API support.
- MCP-only vendor tools where reliability/control is unclear.
- Fully autonomous high-impact actions without review.

## Tom Trigger Workflows

The matching system should be designed around Tom's shorthand recruiter
triggers, not just around a generic "search resumes" box.

Working interpretation from the handwritten `Typical Workflows & Triggers`
notes:

- A candidate gives a lead.
- A company is hiring and Tom wants to know what candidate, hiring-manager, and
  company information already exists in the database.
- Tom sees a company advertising for a role and already has a strong candidate.
- Tom wants to know who has spoken to a target company before and whether there
  are other similar candidates/CVs.
- A new vacancy appears and candidates need to be found quickly.
- Tom wants to pitch to a current hiring manager/company and needs to know who
  in the database is currently working there.
- Tom sees a company advertising and wants to send strong candidates there.

Implication for product scope:

- `/match` is only the first narrow UI surface.
- The real product direction is trigger-led recruiter workflows:
  - vacancy to shortlist
  - candidate to company lead discovery
  - company to candidate/hiring-manager discovery
  - relationship/history lookup before outreach
- Retrieval should eventually combine:
  - CV evidence
  - company evidence
  - hiring-manager evidence
  - prior interaction evidence
  - recruiter relationship history

## Tom Problems and Solutions Notes

Working interpretation from the handwritten `Problems & Solutions` section:

- CV and hiring-manager data goes stale.
  - Tom does not reliably know the latest skills people have or where they are
    currently working.
  - This means missed opportunities.
- Relationship visibility is weak.
  - Tom does not reliably know who has already spoken to a target person or
    company.
  - He also cannot easily tell which relationships are warmer/stronger.
- LinkedIn data and CRM data are not connected tightly enough.
  - There is useful LinkedIn, CV, and hiring-manager data, but it is not
    staying in sync as one usable operating picture.

Working solution ideas captured from the same notes:

- Keep profiles fresh by linking database people to stable LinkedIn identities
  where possible, then refreshing updates back into the platform.
- Use notes, dates, and email context to infer or surface relationship warmth
  and prior-contact history.
- Connect CRM, LinkedIn-derived data, and CV data into one unified recruiter
  view rather than leaving them in separate tools.
- Treat profile-refresh and relationship-context features as core workflow
  value, not as optional extras after matching.

Interpretation note:

- The handwriting reads like compressed recruiter shorthand rather than precise
  product copy.
- The exact vendor/tool names in the notes are less important than the product
  requirements they imply:
  - identity linkage
  - profile refresh
  - relationship context
  - cross-source synchronisation

### Additional Notes From The Same Problems & Solutions Section

Working interpretation from the next handwritten note block:

- Tom's current workflow for finding good candidates for a live vacancy is too
  manual and too slow.
- He wants an LLM to work from:
  - his recruiter instructions
  - the job spec
  - the already-ingested data platform
  so that suitable candidates can be found quickly.
- Another recurring workflow is:
  - Tom sees a company advertising
  - he believes he already has a strong candidate
  - but finding the hiring manager is still a manual LinkedIn-style process
- There may already be candidates, hiring managers, or related contacts in the
  internal CV/database estate who work at that company.
- Direct contact paths such as mobile numbers are materially more valuable than
  generic cold outreach.

Architecture implication captured from the same notes:

- Tom expects the useful end-state to combine:
  - up-to-date source data
  - graph/vector retrieval infrastructure
  - an MCP/LLM layer on top
  - chatbot or agent-style interaction patterns
- The data platform therefore needs to support not just candidate ranking, but
  also company-to-person and vacancy-to-hiring-manager discovery workflows.

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

Priority note:

- This is now one of the most important near-term build slices.
- We already have the searchable corpus, resume chunk embeddings, and
  candidate semantic blocks in place.
- The next step is to build the graph-aware retrieval/evidence layer on top of
  that indexed corpus, rather than letting the work stall at "vector search
  plus reranking".

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

## What Is Already Underway

These are the ideas from Tom's notes that are already materially underway:

- [x] Vacancy-to-candidate matching foundation.
- [x] Unified CV data layer across Recruiterflow, Dropbox, and Outlook-exported
  Dropbox CVs.
- [x] Resume retrieval/download path for current resumes.
- [x] Resume chunking and embeddings across the searchable corpus.
- [x] Initial `/match` UI with shortlist/reranking flow.
- [ ] Company-to-candidate discovery workflow.
- [ ] Hiring-manager discovery workflow.
- [ ] Relationship warmth/context workflow.
- [ ] Profile refresh/sync workflow across external systems.

## Definite Next Slices

These are the most defensible next build steps given the current platform
state.

- [ ] Build the first graph-aware retrieval layer on top of the indexed
  candidate corpus:
  - traverse linked canonical entities before final ranking
  - assemble explainable evidence across candidate, company, contact, and
    interaction context
  - keep the current semantic retrieval and LLM shortlist flow as the ranking
    spine underneath
- [ ] Add dedicated `candidate_semantic_blocks` retrieval data.
- [ ] Backfill structured semantic blocks from canonical candidate/profile/skill
  fields.
- [ ] Embed those semantic blocks and add hybrid retrieval to `/match`.
- [ ] Add explainable evidence blocks to shortlist results.
- [ ] Add a first company-to-candidate discovery API/UI slice.
- [ ] Add a first "who currently works there / who has spoken to them before"
  lookup slice.

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
