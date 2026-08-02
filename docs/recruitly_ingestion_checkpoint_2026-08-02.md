# Recruitly Ingestion Checkpoint — 2 August 2026

## Scope

This checkpoint completes the independently deliverable Recruitly ingestion
slice for jobs, opportunities, and their journal/note-style interactions using
the access already configured for the project.

The existing importer remains deliberately read-from-Recruitly and
upsert-into-canonical-storage only. It does not write back to Recruitly.

## Live result

The bounded bulk runner requested the complete current jobs and opportunities
collections, then requested every available journal page for each returned job
or opportunity.

| Resource | Source rows returned | Canonical result |
| --- | ---: | --- |
| Jobs | 4 | 4 source records persisted and linked one-to-one to 4 canonical jobs |
| Opportunities | 0 | Empty source state verified; no rows invented |
| Job journals | 0 across 4 jobs | Empty source state verified; no interactions invented |
| Opportunity journals | 0 across 0 opportunities | Empty source state verified |

The database verification after the run found:

- `4` `recruitly_job` source records;
- `4` distinct canonical job links;
- `0` Recruitly opportunity source records; and
- `0` canonical interactions with `source_system = 'recruitly'`.

The machine-readable run report is stored in
`docs/evaluation/recruitly_ingestion_2026-08-02.json`.

## Completion interpretation

The ingestion capability and the complete currently available source data have
both been exercised. Opportunities and journal interactions are complete as an
empty-source result, not as populated datasets. A future Recruitly refresh can
use the same idempotent bulk runner; new records will be upserted when the
source begins returning them.

## Validation

- Recruitly ingestion and bulk-runner unit tests: `12 passed`.
- Live collection sweep: `4` jobs persisted, `0` opportunities returned.
- Live journal sweep: all `4` returned jobs checked, `0` entries returned.
- Post-write canonical verification: `4` job source records and `4` linked
  canonical jobs.
