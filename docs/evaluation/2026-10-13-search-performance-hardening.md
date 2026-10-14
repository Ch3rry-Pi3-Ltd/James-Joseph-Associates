# Search performance hardening — 13 October 2026

## Scope

This pass addresses the bounded hybrid candidate search used by Match and the
ChatGPT MCP app. It does not alter the separate exhaustive current-CV search,
candidate data, ranking models, or database schema.

## Evidence

A live, read-only `EXPLAIN (ANALYZE, BUFFERS)` of the representative broad Data
Engineer query showed two very different paths:

- the indexed current-CV branch found `52` documents in about `197 ms`
- the compatibility branch scanned all `16,102` candidates, expanded `3,204`
  eligible rows, and brought total SQL execution to `8,129.73 ms`
- the complete plan touched `93,248` shared cached blocks

The broad branch exists to preserve queries whose required terms are split
between profile metadata and CV text. Running it for every query was unnecessary
because hybrid retrieval already has structured semantic evidence in parallel.

## Change

- Try progressively backed-off indexed current-CV queries first.
- Return immediately when that path finds evidence.
- Run the broader cross-field query only when every indexed variant returns no
  results, preserving the previous compatibility behaviour.
- Report `text_query_mode`, attempt count, and cross-field fallback use as
  content-free retrieval metadata.
- Enforce conservative production-smoke ceilings of `20,000 ms` for bounded
  candidate search and `10,000 ms` for exhaustive current-CV search.

No migration or index was added. The existing `idx_documents_resume_fts` and
`idx_document_links_current_document` indexes were sufficient.

## Verification

The revised live plan for the same Data Engineer query:

- completed in `175.952 ms`
- returned the requested `15` rows
- used `idx_documents_resume_fts`
- touched `1,186` shared cached blocks and read none from disk

That is about a `97.8%` SQL-time reduction and a `98.7%` reduction in shared
block touches for this representative query. These are point-in-time measurements,
not a universal latency guarantee.

Three read-only end-to-end repetitions against configured live services returned
five candidates every time with no candidate-data writes or retrieval fallback:

| Case | First | Second | Third |
| --- | ---: | ---: | ---: |
| Securities finance | 14,332 ms | 9,045 ms | 8,917 ms |
| Data Engineer | 6,945 ms | 6,018 ms | 5,974 ms |
| Pirum company context | 4,279 ms | 1,172 ms | 1,231 ms |
| EquiLend company context | 1,312 ms | 1,196 ms | 1,179 ms |

Data Engineer used the indexed branch on its first text attempt. Securities
finance used the indexed branch after five progressively broader variants; its
cold first run remained within the 20-second release budget.

## Automated production gate

Commit `fb76b1e` added a `main`-only GitHub Actions workflow with manual dispatch
and a Tuesday 07:30 UTC schedule. The existing production bearer credential was
copied into the protected `MCP_API_TOKEN` repository secret without rotation.

The first manual run, GitHub Actions run `38519279842` on 14 October 2026,
passed in 46 seconds:

- exactly seven approved read-only tools were exposed
- candidate search returned five results in `12,261 ms` using indexed-CV hybrid
  retrieval without cross-field or semantic fallback
- exhaustive search completed in `6,362 ms`; its then-reported `32,204`
  eligible count included both candidate and mirrored person links. The
  14 October data-quality audit established that this represented `16,102`
  distinct candidate-linked current-CV documents, and the coverage query was
  corrected without changing the documents searched
- the smoke runner performed zero candidate or CRM writes

Both measured searches remained inside their enforced regression budgets.
