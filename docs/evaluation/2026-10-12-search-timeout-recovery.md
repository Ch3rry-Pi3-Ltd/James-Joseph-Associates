# Search timeout recovery and Tom's data access

## What failed

Tom's October securities-finance test authenticated successfully, but candidate
and company-context tools exceeded the 30-second MCP response deadline. Directory
results were not candidate evidence. Production diagnostics showed database work
continuing after the response timeout; embeddings alone did not explain the delay.
The previous August smoke results did not establish October reliability.

## Changes

- Migration `0017` adds an automatically maintained full-text vector on documents,
  a partial GIN index for resumes, and two current-resume link indexes. Applied
  to live Supabase on 12 October 2026; all three indexes verified. No records,
  grants, or credentials were removed or changed.
- Candidate text search now prefilters using the index, retains cross-field and
  Boolean matching, and ranks/excerpts the reduced result set. Company searches
  use indexed CV mentions alongside current-employer matches.
- Semantic nearest-neighbour ordering can use the existing vector index; final
  candidate ordering retains deterministic tie-breaking.
- Search workers share a deadline, with an 8-second maximum SQL statement budget,
  connection timeout, and database cancellation at the shared deadline. Expired
  operations do not open another managed connection. Semantic failure still falls
  back to full-text evidence rather than claiming there are no candidates.
- Identical authenticated MCP searches share a short, principal-scoped in-memory
  cache (maximum 15 seconds, 16 entries, deployed environments only). This is not
  a global concurrency limit or cross-instance cache.
- Tool descriptions discourage parallel/repeated timeout retries.
- Next.js and eslint-config-next patched to 16.3.8; production dependency audit
  reports zero vulnerabilities. This does not assert a clean development-only audit.

## Verification before deployment

- 752 Python tests passed; two opt-in SQL tests excluded from the default suite.
- Both opt-in SQL tests passed against session-local synthetic tables rolled back
  afterwards: phrases, OR, exclusions, cross-field matching, current-CV scope,
  automatic vector refresh, and employer/CV-mention lookups.
- Next.js production build and Python lint passed.
- An additional MCP cache regression verifies principal/argument isolation,
  defensive copies, and propagation of the worker read deadline (12 targeted
  MCP/deadline/cache tests passed).
- Live read-only EXPLAIN ANALYZE: representative six-term resume query 1,285 ms;
  Pirum candidate query 269 ms, with the GIN index used.
- Three local-code/live-service securities-finance repetitions returned five
  candidates each in 9,033–11,305 ms. One semantic query hit its SQL budget and
  successfully fell back to text. Pirum: 1,298–2,742 ms; EquiLend: 1,261–1,296 ms.
  These are a small smoke sample, not a latency SLA or recruiter relevance result.
- A harmless five-second database sleep was cancelled in 1.61 seconds under a
  1.5-second read budget (including connection/cleanup overhead).
- Reproduce using `python -m scripts.benchmark_recruiter_search`; add `--endpoint`
  for MCP checks. Output contains timings/counts, not candidate content. MCP
  requests can write normal operational audit/rate-limit records, not candidate data.

## Tom's existing access route

Use the web application, not the Supabase administrator console, for daily work:

1. Open https://james-joseph-associates.vercel.app/match and sign in using Tom's
   authorised Clerk email. The deployment's email allowlist must include it.
2. Enter a role or keywords and select **1. Search corpus**. Inspect the candidate
   pool, CV excerpts, provenance, profiles, and evidence before optional ranking.
3. Use https://james-joseph-associates.vercel.app/company for company context.

The ChatGPT MCP app is an alternative interface, not a prerequisite for website
access. Neither route requires Tom to receive database/service-role credentials.
Do not bypass authentication or loosen database permissions to enable access.

Existing retrieval searches indexed current resumes and semantic profile blocks;
it returns a bounded result pool. It is not yet an exhaustive, paginated browser
of every raw record, historical document, and source table. That is a separate
data-explorer enhancement, not a five-candidate database restriction.

## Still to verify

- Staged and promoted production MCP benchmarks and authentication checks.
- Tom's authorised browser sign-in and complete Match/Company workflow: no claim
  of testing his account or ChatGPT workspace is made by server-side benchmarks.
- Recruiter relevance and evidence usefulness for the returned candidates.
- Agree the scope of exhaustive text search/pagination across historical/source
  data before presenting it as existing functionality.
