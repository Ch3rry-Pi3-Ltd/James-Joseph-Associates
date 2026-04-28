# JobAdder OpenAPI Snapshot

This directory contains a local snapshot of the JobAdder OpenAPI specification
used as a development reference during integration work.

## Files

- `openapi-2026-04-28.json`

## Provenance

- Source URL: `https://api.jobadder.com/v2/docs`
- Downloaded on: `2026-04-28`
- Original local source: `C:\Users\HP\Downloads\openapi.json`

## Why this is in the repo

The live JobAdder docs site is not always easy to inspect programmatically, and
the OpenAPI document is materially useful for:

- endpoint discovery
- query parameter discovery
- response-schema inspection
- scope and webhook reference
- designing ingestion work for candidates, jobs, applications, opportunities,
  and skills

## Important caveat

This file is a dated snapshot, not a guaranteed live source of truth.

If the live JobAdder API changes, this copy can drift. Treat it as a local
reference and refresh it intentionally when needed.
