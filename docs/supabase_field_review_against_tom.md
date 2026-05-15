# Supabase Field and Entity Review Against Tom's Current Concerns

This document records the current canonical Supabase/Postgres model and
compares it against the issues Tom raised after the recent JobAdder CV
extraction progress.

It is not a future-state design document. It is a current-state review.

In plain language:

- what entities and fields already exist in the schema
- what the current narrow JobAdder persistence slice actually writes today
- what Tom's key concerns are
- which of those concerns are already covered
- which are only partially covered
- which still need deliberate implementation

## Why this review exists

The current project has moved beyond proof-of-concept extraction.

We now have:

- live JobAdder CV extraction
- batch processing
- accepted-output persistence into Supabase/Postgres
- post-write verification against canonical rows and provenance links

That means the next question is no longer only:

> "Can we extract and persist one accepted CV?"

It is also:

> "Does the current canonical model and write slice cover the business-critical
> concerns Tom has raised before we widen ingestion?"

This document answers that question directly.

## 1. Canonical entities currently present in the schema

Current core entities defined in
[`0002_core_entities.sql`](C:\Users\HP\OneDrive\Documents\Ch3rryPi3 Ltd\Clients\james-joseph-associates\supabase\migrations\0002_core_entities.sql):

- `companies`
- `people`
- `candidates`
- `contacts`
- `jobs`
- `applications`
- `placements`
- `opportunities`
- `skills`
- `documents`
- `interactions`
- `source_records`

Current relevant link/relationship tables:

- `candidate_skills`
- `job_required_skills`
- `person_company_roles`
- `document_links`
- `interaction_participants`
- `source_record_links`
- `document_chunks`

## 2. What the current narrow JobAdder persistence slice writes today

The current accepted-output persistence path is implemented in:

- [`resume_extraction_persistence.py`](C:\Users\HP\OneDrive\Documents\Ch3rryPi3 Ltd\Clients\james-joseph-associates\backend\services\resume_extraction_persistence.py)
- [`resume_extraction_persistence.py`](C:\Users\HP\OneDrive\Documents\Ch3rryPi3 Ltd\Clients\james-joseph-associates\backend\db\resume_extraction_persistence.py)

It currently writes only a narrow subset of the full schema:

### `people`

Current fields populated:

- `full_name`
- `first_name`
- `last_name`
- `primary_email`
- `primary_phone`
- `linkedin_url`
- `location`
- `headline`
- `summary`

### `candidates`

Current fields populated:

- `person_id`
- `current_title`
- `current_company_id`
- `candidate_status`
- `availability_status` currently `null`
- `last_contacted_at`
- `resume_updated_at`

### `companies`

Current fields populated:

- `name`

The broader company fields exist in the schema but are not yet populated by
this write slice:

- `domain`
- `website_url`
- `linkedin_url`
- `industry`
- `size_range`
- `location`
- `description`
- `status`

### `documents`

Current resume-document fields populated:

- `document_type = "resume"`
- `title`
- `source_uri`
- `mime_type`
- `content_hash`
- `extracted_text`

Not yet populated:

- `storage_path`

### `source_records`

Three source-record types are currently written:

- `jobadder_candidate_snapshot`
- `jobadder_resume_attachment`
- `jobadder_resume_extraction`

Current fields populated:

- `source_system`
- `source_record_type`
- `source_record_id`
- `source_payload`
- `source_payload_hash`
- `import_run_id`
- `processed_at`
- `sync_status`

### `source_record_links`

Current link targets written:

- candidate snapshot -> person
- candidate snapshot -> candidate
- resume attachment -> document
- resume attachment -> person
- resume attachment -> candidate
- accepted extraction -> person
- accepted extraction -> candidate
- accepted extraction -> company when present
- accepted extraction -> document when present

### `document_links`

Current link targets written for resume documents:

- resume document -> candidate
- resume document -> person

### `candidate_skills`

Current fields populated:

- `candidate_id`
- `skill_id`
- `source_record_id`
- `confidence`
- `evidence_text`

The current write path combines both:

- extracted skills
- extracted tools/platforms

into the shared canonical `skills` table and then links them through
`candidate_skills`.

## 3. Important entities/areas that exist in the schema but are not yet used by the current JobAdder CV persistence slice

The schema already has room for more than the current narrow write path uses.

Not yet populated by the current accepted CV flow:

- `contacts`
- `interactions`
- `interaction_participants`
- `person_company_roles`
- `jobs`
- `applications`
- `placements`
- `opportunities`
- `job_required_skills`
- `document_chunks`

This matters because some of Tom's concerns are already "schema-supported" but
not yet "write-path implemented".

## 4. Tom's current concerns mapped against the present state

## 4.1 "Can I see the current fields in Supabase?"

**Status:** covered by this review.

The current schema is broader than the current write slice.

The important practical distinction is:

- **schema present**
- versus
- **currently written by the accepted JobAdder CV path**

That distinction is exactly why this review is useful.

## 4.2 "If the system sees a candidate again later, will it still keep a newer CV?"

**Status:** partially covered, not fully solved.

What exists now:

- the schema supports multiple `documents`
- `document_links` can associate documents to people/candidates
- `source_records` and `source_record_links` preserve provenance
- the current write path uses content hash and source links to avoid obvious
  duplicate document rows

What does **not** exist yet:

- a formal "preferred/current CV" policy across multiple source systems
- ranking logic to decide which of several CVs should be treated as the best
  current working CV
- any explicit write logic to compare an old JobAdder CV against a fresher
  Dropbox or email-derived CV and mark one as preferred

Conclusion:

- we can retain provenance-bearing resume documents
- we do **not yet** have the final preferred-CV decision logic

## 4.3 "Will email be the unique identifier?"

**Status:** partially covered, intentionally conservative.

What exists now:

- `people.primary_email`
- `people.linkedin_url`
- `people.primary_phone`
- source-system provenance via `source_records`

Current write-path matching order for candidates:

1. existing source-record link
2. exact LinkedIn URL
3. exact primary email
4. otherwise create new person

This is intentionally narrow and conservative.

Conclusion:

- email is useful
- email is **not** the only identity signal
- we do **not yet** have the fuller cross-source reconciliation policy Tom is
  asking for, especially for hiring managers/contacts

## 4.4 "Is raw CV/source document data still being saved?"

**Status:** largely covered for accepted CV-based records.

What exists now:

- raw-ish provenance-bearing `source_records`
- canonical `documents` row
- `documents.extracted_text`
- `documents.content_hash`
- `documents.source_uri`
- source/document link tables

What is not yet done:

- broader direct binary-storage policy for all future document sources
- a final decision about whether all documents should also be copied to a
  storage layer path consistently

Conclusion:

- the current narrow accepted JobAdder CV path does retain the extracted
  resume text and provenance metadata
- the wider multi-source raw-document policy still needs formalising

## 4.5 "What happens in no-CV / LinkedIn-PDF / sparse-profile cases?"

**Status:** now covered in a first narrow persistence slice, but still not the
final form.

Current reality:

- extraction batches can skip repeated unchanged no-resume cases operationally
- the accepted-output persistence slice is still built around accepted CV
  extraction results
- there is now a separate profile-only persistence path for JobAdder
  candidates who have:
  - no proper CV
  - useful contact identity data
  - useful recruiter notes/provenance
- that profile-only path currently preserves:
  - person/candidate rows
  - source provenance
  - note-bearing source payloads
  - optional current company when available

What is still not yet final:

- notes are still provenance payloads rather than first-class interactions
- richer sparse-profile sources such as LinkedIn-PDF-style cases may need
  broader handling than the current explicit no-resume JobAdder path

Conclusion:

- the current system can now persist those cases in a first narrow way
- the broader richer sparse-profile policy still needs to mature

## 4.6 "Are notes being stored?"

**Status:** now covered in a first narrow interaction slice.

What exists now:

- cleaned recruiter notes are preserved inside `candidate_source_payload`
  provenance stored in `source_records.source_payload`
- JobAdder candidate notes are now also promoted into first-class
  `interactions`
- those note interactions are linked back to the persisted person/candidate via
  `interaction_participants`
- `last_contacted_at` is derived from cleaned notes and written onto the
  canonical candidate row

What is not yet implemented:

- broader cross-source interaction modelling beyond JobAdder candidate notes
- direct provenance links from note source records to interactions in the
  current schema
- richer note-level querying/reporting semantics

Conclusion:

- notes are now retained both:
  - in provenance payloads
  - and as first-class canonical interactions
- the interaction slice is still intentionally narrow and JobAdder-specific

## 4.7 "Are LinkedIn URLs captured?"

**Status:** covered for current accepted candidate CV writes.

What exists now:

- `people.linkedin_url` in the schema
- current persistence path writes extracted LinkedIn URL into that field
- current person matching logic already treats LinkedIn URL as a stronger
  identity signal than email fallback

Conclusion:

- yes, LinkedIn URL is already treated as important
- but wider contact/hiring-manager reconciliation rules still need more design

## 4.8 "Do we have room for hiring-manager / contact data?"

**Status:** schema yes, write path no.

What exists now:

- `contacts` table
- company/contact relationships in the schema
- job/contact relationships in the schema

What is not yet implemented:

- a current persistence path from Pipedrive / other sources into `contacts`
- reconciliation logic for hiring-manager identity across company moves
- broader contact-note persistence

Conclusion:

- the schema has somewhere for this data to live
- the current JobAdder CV slice does not populate it yet

## 4.9 "Can the model support later source reconciliation across Dropbox, Pipedrive, LinkedHelper, etc.?"

**Status:** partially prepared, not yet implemented.

What is already helpful:

- canonical UUID primary keys
- provenance-bearing `source_records`
- `source_record_links`
- `documents` and `document_links`
- `people`, `candidates`, `contacts`, `companies`

What is still missing:

- source-specific ingestion paths
- formal deduplication/reconciliation policy per entity class
- company alias/pseudonym handling
- repeatable import-order policy

Conclusion:

- the schema is directionally compatible with Tom's broader source landscape
- the actual reconciliation workflows still need to be designed and built

## 5. Main gaps revealed by this review

These are the biggest current gaps relative to Tom's concerns.

### Gap 2: broader interaction modelling beyond the first JobAdder note slice

Notes are now written into:

- `interactions`
- `interaction_participants`

But the broader interaction model is still incomplete across other sources and
other communication/event types.

### Gap 3: preferred/current CV policy

We can store resume documents and provenance, but we do not yet have a formal
rule for:

- multiple CVs per candidate
- later fresher CV arrival from different sources
- how to rank or mark the preferred/current CV

### Gap 4: broader contact / hiring-manager ingestion

The schema has `contacts`, but the current write slice does not yet populate
it. This matters later for Pipedrive and LinkedHelper-driven hiring-manager
data.

### Gap 5: broader company reconciliation

The schema has `companies`, but the current write slice only populates the
name. It does not yet reconcile:

- domains
- websites
- LinkedIn company URLs
- aliases / pseudonyms

## 6. What is already in a good enough place

The following are materially stronger now:

- accepted JobAdder CV extraction
- accepted-output persistence
- provenance-bearing source record capture
- canonical people/candidates/documents/skills writes
- post-write verification against canonical rows and link tables

That means the current narrow CV path is now good enough to use as a stable
foundation while the broader modelling questions are handled deliberately.

## 7. Recommended immediate next implementation move

Based on this review and the latest implementation work, the next sensible
implementation move is now:

### broaden sparse-profile handling beyond explicit no-resume JobAdder cases

Reason:

- the first narrow no-resume/profile-only persistence path now exists
- the first JobAdder note-to-interaction slice now exists
- the next bigger mismatch with Tom's source landscape is wider sparse-profile
  handling across non-CV and non-JobAdder inputs

## 8. Secondary next move after that

After that, the next sensible move is:

### Dropbox access and source-shape review

That would align the model more closely with Tom's wider source landscape,
including:

- LinkedIn-PDF-style profiles
- partial profile snapshots from non-CV sources

The current first-pass operational checklist for that work now lives in:

- [dropbox_access_setup_checklist.md](C:\Users\HP\OneDrive\Documents\Ch3rryPi3 Ltd\Clients\james-joseph-associates\docs\dropbox_access_setup_checklist.md)
- other valuable contact records that are not yet rich enough to count as a
  full CV ingestion
