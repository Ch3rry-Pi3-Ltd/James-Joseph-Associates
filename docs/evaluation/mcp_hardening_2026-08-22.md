# MCP Hardening Evidence — 22 August 2026

## Revised search benchmark

The second local live-service run used the same bounded Senior Data Engineer
brief as the 20 August test. Full-text and semantic retrieval ran concurrently;
provenance, skills, and employment were loaded together; model shortlisting was
disabled; and skill evidence was role-ranked and capped at 12 per candidate.

| Run | Duration | Retrieval | Results | Skills per result |
| --- | ---: | --- | ---: | ---: |
| 1 | 21,320 ms | Hybrid | 5 | 12 |
| 2 | 16,140 ms | Hybrid | 5 | 12 |
| 3 | 18,224 ms | Hybrid | 5 | 12 |

All three semantic calls succeeded, no fallback or circuit breaker was used,
and the median dropped from approximately `22.3s` in the first revised run to
`18.2s` here. This remains a local-to-live-services measurement rather than the
final deployed ChatGPT timing.

## Company quality review

The shared deterministic policy inspected `24,150` canonical companies and
placed `20` records into a non-destructive review report. No company row was
deleted, rewritten, merged, or otherwise modified.

## MCP operational summary proof

The privacy-safe seven-day report returned metrics for four tools and measured
`1.5` profile calls per candidate search in the historical live-test window.
New audit rows will additionally contain bounded response size, result counts,
retrieval mode, semantic fallback and circuit-breaker state.

## Query-plan evidence

Production `EXPLAIN (ANALYZE, BUFFERS)` checks found:

- candidate-linked provenance: a parallel gather touching `2,963` shared blocks
  to return three rows (`77.979ms` execution)
- person-linked provenance: a parallel gather touching `2,963` shared blocks to
  return three rows (`21.383ms` execution)
- recent employment: a sequential scan removing `61,671` rows to return none
  for the tested person (`10.117ms` execution)

Migration `0016_mcp_read_path_indexes.sql` therefore adds only the three indexes
directly supported by this evidence. Following explicit production approval, it
was applied to live Supabase on 22 August 2026 and all three index definitions
were verified.

Post-migration `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` checks showed:

| Read path | Plan | Index | Execution | Shared blocks |
| --- | --- | --- | ---: | ---: |
| candidate provenance | Index Only Scan | `idx_source_record_links_candidate_id` | 4.247 ms | 3 |
| person provenance | Index Only Scan | `idx_source_record_links_person_id` | 3.311 ms | 3 |
| recent employment | Index Only Scan | `idx_person_company_roles_person_recency` | 4.915 ms | 4 |

## Production deployment and smoke evidence

The hardened release was deployed to Vercel production as deployment
`dpl_Hun8yHVE2vBQExvhWYhFriJq9ftX` and aliased to the canonical production
domain. Three authenticated read-only smoke repetitions then exercised
authentication rejection, six-tool discovery, company-prefix integrity, and
the bounded Senior Data Engineer candidate search.

| Run | Company directory | Candidate search | Results | Retrieval |
| --- | ---: | ---: | ---: | --- |
| 1 | 5,751 ms | 19,942 ms | 5 | Hybrid; no fallback |
| 2 | 7,219 ms | 18,388 ms | 5 | Hybrid; no fallback |
| 3 | 7,020 ms | 16,165 ms | 5 | Hybrid; no fallback |

Every run returned five companies and five candidates, exposed exactly six
read-only tools, used no semantic fallback or open circuit, and performed zero
writes. This is direct production-endpoint evidence. The workspace owner still
needs to rescan and republish ChatGPT's frozen tool snapshot before the same
prompts are repeated through the ChatGPT user interface for recruiter review.
