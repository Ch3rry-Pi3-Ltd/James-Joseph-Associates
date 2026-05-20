# Source Integration Checkpoint - 2026-05-20

This note records the current state of the Dropbox, JobAdder, and advert-
response investigation so the working model is not trapped in chat history.

## Current position

We now have a coherent cross-source model for at least one real vacancy:

- `tw398`

That vacancy now links across:

- JobAdder `job`
- JobAdder `application`
- JobAdder candidate attachment
- Dropbox job-spec PDF
- Dropbox `.eml` advert-response archive
- Dropbox CV mirror copies

## What has been proved

### JobAdder

- Real `job` record exists for:
  - `jobId = 936462`
  - `jobTitle = tw398 - KDB Developer`
  - company `B2C2`
- Real `applications` exist and carry the `tw398` vacancy code.
- Sample application attachment lists were empty.
- Sample candidate records each had one resume attachment.

### Dropbox

- Tom's Dropbox OAuth connection works and has read/write scopes.
- Dropbox folder structure has been inspected and documented.
- PDF and DOCX extraction from Dropbox are proven.
- Legacy `.doc` is out of scope for the first automated path.
- One real `tw398` `.eml` was parsed successfully and preserved:
  - source channel
  - sender/recipient
  - received timestamp
  - vacancy code
  - attachment filename

### JobAdder vs Dropbox CV copies

Two direct file comparisons were completed:

1. `sanjeev sadha.docx`
2. `Zafar_Lead_Finance.docx`

For both pairs:

- filename matched
- byte size matched
- SHA-256 matched

This is strong evidence that the tested Dropbox CV files are byte-identical
mirrors of the JobAdder candidate attachments.

## Current working model

- JobAdder `job` = opportunity context
- JobAdder `application` = application context
- JobAdder candidate attachment = primary structured CV source
- Dropbox CV files = archive/mirror layer by default
- Dropbox `.eml` files = provenance/history layer
- Dropbox job-spec PDFs = role-spec documents useful for retrieval and match

## Live persistence slices already completed

### Job + job spec

The first narrow persistence slice for the `tw398` job and Dropbox job-spec
PDF has been implemented and proven live.

Persisted shape:

- canonical `jobs` row
- canonical `documents` row with `document_type = job_spec`
- provenance `source_records`
- `source_record_links`
- `document_links` with `relationship_type = job_spec`

### Application

The first narrow JobAdder application persistence slice has also been
implemented and proven live.

Persisted shape:

- canonical `people`
- canonical `candidates`
- canonical `applications`
- provenance `source_records`
- `source_record_links`

## Current design implications

### Duplicate handling

The default assumption should now be:

- if a JobAdder candidate attachment and Dropbox CV copy hash-match, treat the
  JobAdder candidate attachment as the primary source and Dropbox as a mirror
- keep every document version/provenance record; do not overwrite
  destructively
- use a separate "preferred/current CV" policy rather than collapsing all
  versions into one file

### Advert-response ingestion

Advert-response material should be treated as vacancy-aware, not just generic
document ingestion.

The likely rule is:

- JobAdder application/job provide the structured vacancy context
- JobAdder candidate attachment provides the primary CV
- Dropbox `.eml` provides provenance
- Dropbox job-spec PDF provides matchable role requirements

## Immediate next steps

1. Persist one Dropbox `.eml` provenance record and link it where identity is
   clean enough.
2. Chunk/embed the persisted `tw398` job-spec document.
3. Formalise duplicate/latest-file policy in the canonical data model and
   ingestion rules.
4. Move into Outlook/Microsoft 365 ingestion using Microsoft Graph as the
   primary source, not Dropbox as the first landing zone.
