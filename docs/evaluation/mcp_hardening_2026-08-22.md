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
directly supported by this evidence. It is intentionally not applied to live
Supabase as part of the code change; production application remains a separate
explicitly approved operation.
