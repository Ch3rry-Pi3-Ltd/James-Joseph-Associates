# Exhaustive Current-CV Search

## Outcome

The application has a deterministic search mode for recruiters who need every
exact match rather than a ranked top-K shortlist. It searches the stored full
text of every searchable document linked as a candidate's `current_resume`.
No CV is sent to an LLM for this operation.

Use the authenticated workspace at `/cv-search`. The existing `/match` page
remains the fast hybrid retrieval and shortlist workflow.

## Search contract

- `GET /api/v1/candidates/search-documents`
  - accepts `query`, `page_size` (1-100), and an opaque `cursor`
  - supports quoted phrases, uppercase `OR`, and minus-prefixed exclusions
  - returns deterministic keyset pagination, evidence excerpts, original
    filenames, source provenance, and current-CV download references
- reports eligible, searchable, searched, excluded, matched-document,
    distinct-matched-candidate, and missing-CV counts
- `GET /api/v1/candidates/search-documents/export`
  - streams all matches as formula-safe CSV
- MCP `search_candidate_documents`
  - exposes the same search in pages of at most 50
  - callers must follow `next_cursor` until `has_more` is false before claiming
    to have enumerated every match

The search is labelled `is_exhaustive=true` only when every eligible current CV
has searchable extracted text. When text is missing, the response says
`complete_with_exclusions` and reports the exact exclusion count.

## Cost and architecture

Postgres executes the full-text query using the stored `resume_search_vector`
and GIN index introduced by migration `0017`. Search, pagination, coverage, and
CSV export do not call an embedding provider or language model. An LLM can still
be used later to assess a selected result set, but it is not part of exhaustive
retrieval.

## Deliberate scope

This release searches canonical current CVs. Historical CV versions, raw source
records, job documents, and unrelated document types are not silently mixed
into recruiter results. Expanding that scope requires an explicit product and
retention decision.

After deployment, the ChatGPT Business workspace owner must rescan and
republish the MCP app so the new read-only tool is visible. No credential change
is required.
