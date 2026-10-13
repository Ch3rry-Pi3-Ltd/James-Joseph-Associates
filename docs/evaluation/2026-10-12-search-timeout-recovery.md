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
- Search workers share a deadline, with a 12-second maximum SQL statement budget,
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

- 753 Python tests passed; two opt-in SQL tests excluded from the default suite.
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

The fast retrieval path searches indexed current resumes and semantic profile
blocks and returns a bounded ranked pool. A later release added a separate
deterministic current-CV search workspace, API, CSV export, and paginated MCP
tool; see [`exhaustive_current_cv_search`](../exhaustive_current_cv_search.md).
Historical documents, raw records, and unrelated source tables remain outside
that deliberate current-CV scope.

## Still to verify

- Tom's authorised browser sign-in and complete Match/Company workflow: no claim
  of testing his account or ChatGPT workspace is made by server-side benchmarks.
- Recruiter relevance and evidence usefulness for the returned candidates.
- Agree the scope of exhaustive text search/pagination across historical/source
  data before presenting it as existing functionality.

## Release checks and follow-up

Commit `8245818` built successfully in Vercel. The staged hostname was correctly
rejected by MCP's host allowlist (421), so full MCP tests needed the live hostname.
After promotion, authentication/discovery/directory passed but Data Engineer
search returned a tool error: a SQL statement reached the original eight-second
budget. The release was immediately rolled back to `dpl_Hun8yHVE2vBQExvhWYhFriJq9ftX`.
Migration `0017` remains applied and is compatible with the old application.

Follow-up removes unnecessary default-weight reapplication to large stored CV
vectors and allows 12 seconds per statement, still bounded by the 24-second
search deadline. The broader Data Engineer query returned five hybrid results
in 8.36 seconds locally against live services. SQL/deadline/cache checks passed
again (six tests). Both role briefs are now included in the repeat benchmark.

### Final production verification

Commit `2bde339` was built and promoted successfully on 12 October 2026:
`dpl_8an45aDQqKUbCK4LJsHgWfqmUhyf`. The public production hostname resolves to this
release. Three sequential repetitions per case returned five candidate records
each; no tool errors or semantic fallbacks occurred in this final sample.

| Production MCP call | First | Second | Third |
| --- | ---: | ---: | ---: |
| Securities finance | 14,471 ms | 12,748 ms | 12,287 ms |
| Data Engineer | 9,422 ms | 10,046 ms | 10,897 ms |
| Pirum context | 6,367 ms | 6,077 ms | 5,193 ms |
| EquiLend context | 5,730 ms | 5,327 ms | 5,197 ms |

An additional deployed smoke check passed unauthenticated rejection, protocol
initialisation, all six read-only tool contracts, company prefix/ID/provenance,
and candidate evidence (search 9,301 ms). Unauthenticated Match and Company pages
both redirected to sign-in (307). No error-level logs were found for the final
deployment in the inspected 15-minute window. This is point-in-time verification,
not a load test or proof of Tom's workspace/browser session.

Final full regression: 753 passed, two opt-in tests skipped; both opt-in SQL tests
also passed separately. Repository-wide Ruff passed, production build passed,
and the production npm dependency audit reported zero vulnerabilities.

### GitHub Actions distinction

The paragraphs below record the state observed during the search release. The
branch/CI housekeeping was subsequently resolved; see the follow-up at the end.

The code is pushed to `feat/candidate-evidence-contact-routes`. Recent scheduled
security failures still target stale `main` (`1642e15`): run `37326997103` failed
the old production npm audit (five advisories, including one critical). The
current released lockfile passes that audit. Dependabot CI run `37267455403`
failed Python lint while its Next.js build passed; it is not this release's SHA.

Normal CI/security push triggers cover `main` and PRs, not direct feature-branch
pushes. Therefore there is no new automatic GitHub CI result for `2bde339` to
claim: release verification above was local testing plus Vercel build/live checks.
Reconcile the release branch/main and CI coverage as a separate tracked task.

### Branch and CI follow-up, 12 October 2026

After approval, `main` was fast-forwarded from `1642e15` to `8fb5bb1` without
rewriting history. The application code matches the verified `2bde339` release;
subsequent changes were workflow/documentation only. Before advancing `main`,
the working branch passed GitHub CI (run `38235391599`), Security checks (run
`38235391955`), and Vercel's preview build. The optional passive staging scan
was skipped because no staging target is configured, not counted as passed.

Both workflows now run on every branch push and can be started manually; weekly
security checks continue to use default branch `main`. The temporary exception
for high-severity production Node findings has been removed. Vercel's linked
production branch is confirmed as `main`; pushes trigger an independent build,
not a deployment gated by GitHub Actions. No branch-protection enforcement was
added. Historical failed runs are preserved as evidence rather than deleted.
