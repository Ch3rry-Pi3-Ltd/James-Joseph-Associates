# Source Integration Checkpoint - 2026-05-20

This note records the current state of the Dropbox, JobAdder, Outlook, and
advert-response investigation so the working model is not trapped in chat
history.

## Current position

We now have a coherent cross-source model for at least one real vacancy:

- `tw398`

That vacancy now links across:

- JobAdder `job`
- JobAdder `application`
- JobAdder candidate attachment
- Outlook advert-response mailbox folders/messages
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

### Outlook

- Tom's Outlook OAuth connection now works and is stored in Postgres.
- First live Microsoft Graph reads succeeded for:
  - current user
  - top-level mail folders
- The broad root-Inbox message preview is too heavy for naive first-page
  reads and currently times out.
- A narrower advert-response mailbox path has now been identified:
  - `Inbox`
  - `# ADV-CVR`
  - `### DOMINIQUE FOLDER`
  - `tw394`
  - `tw396`
  - `tw397`
  - `tw398`
  - `tw399`
- Real advert-response messages were confirmed in Outlook:
  - CV-Library application emails
  - Totaljobs "Suitable application" emails
- Real Outlook attachment-list visibility is proven for advert-response
  messages.
- `tw394` is now the cleanest first Outlook folder for narrow ingestion
  because it contains vacancy-coded Totaljobs messages with attachments and a
  manageable message count.
- One real `tw394` Outlook PDF attachment has now been downloaded transiently
  and passed through the existing resume text-extraction layer successfully.
- The first narrow Outlook folder-ingestion slice has now been implemented and
  proven live against:
  - `Inbox > # ADV-CVR > ### DOMINIQUE FOLDER > tw394`
- One real `tw394` advert-response attachment has now been persisted as:
  - one canonical `documents` row with `document_type = resume`
  - one Outlook message provenance `source_record`
  - one Outlook attachment provenance `source_record`
  - linked `source_record_links` back to the canonical document
- The first live persisted Outlook sample initially resolved:
  - `tw_code = tw394`
  - canonical `document_id = 5cc458b8-e02e-4418-962c-fabaf5faeb66`
  - `resolved_job_id = null`
- That initial `resolved_job_id = null` outcome was expected because the
  canonical `tw394` job/opportunity had not been persisted yet.
- The canonical `tw394` job/spec pair has now also been persisted:
  - JobAdder job `891841`
  - canonical `job_id = 8279afc7-6525-4fc7-bb3a-e6e8ffb82b35`
  - Dropbox job-spec PDF:
    `/NEW Dropbox/# DLV/LIVE JOBS - [Job Specs]/tw394 - GSAcapital - Technical Support/GSA Capital - INFRA-Technical Support -2026.pdf`
  - canonical job-spec `document_id = 8222d726-ee80-4c38-951f-02d5dc7dae34`
- After rerunning the Outlook `tw394` folder-ingestion slice, the same
  advert-response resume now resolves:
  - canonical `document_id = 5cc458b8-e02e-4418-962c-fabaf5faeb66`
  - `resolved_job_id = 8279afc7-6525-4fc7-bb3a-e6e8ffb82b35`
- That means the `tw...` vacancy-code bridge is now proven live not just for
  source discovery, but for canonical Outlook advert-response job linking too.
- The first conservative candidate-reconciliation check for that same `tw394`
  Outlook resume is now also complete:
  - Outlook file:
    `SULAIMAN MOHAMMED (412c3f29-e0be-4888-981a-4ae29d524ae2 - Totaljobs).pdf`
  - Outlook SHA-256:
    `8a1645f5f7ebf410801bfee560cb948a12b8e33df790140627dec3162ee5b39f`
  - JobAdder applications scanned for canonical job `891841`: `28`
  - exact file-hash matches found across current JobAdder candidate
    attachments: `0`
- The current safe conclusion for that first Outlook advert-response sample is:
  - keep the canonical job link
  - keep the Outlook message/attachment provenance
  - do **not** auto-link a canonical candidate/person yet
  - treat the record as candidate-unresolved until stronger evidence appears

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
- Outlook advert-response folders/messages = live inbound mailbox source
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

### Outlook advert-response attachment

The first narrow Outlook advert-response ingestion slice has now been
implemented and proven live for one bounded mailbox folder.

Persisted shape:

- canonical `documents` row with `document_type = resume`
- Outlook message provenance `source_record`
- Outlook attachment provenance `source_record`
- `source_record_links`
- optional job link by `tw...` code when a matching canonical job already
  exists

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

1. Use the first internal review surface to inspect what is already in the
   canonical database:
   - API: `/api/v1/review/overview`
   - UI: `/review`
2. Recruiterflow static import is now live for the first bounded chunk:
   - `job/1.134.json` persisted successfully
   - `candidate/1.100.json` persisted successfully
   - `169` candidate-job applications resolved against the imported jobs
3. Recruiterflow attachment-reference import is now live for the same bounded
   chunk:
   - `106` candidate file references persisted
   - `7` job file references persisted
   - file bytes were intentionally not downloaded yet
   - the purpose of this slice is to surface the Recruiterflow document layer
     in the canonical schema before bulk byte ingestion
4. Recruiterflow bounded file-content import is now live for the first primary
   candidate-file batch:
   - source chunk: `candidate/1.100.json`
   - selected primary candidate files: `15`
   - extracted successfully: `15`
   - unsupported: `0`
   - failed: `0`
   - the static importer now prefers embedded ZIP members under:
     - `candidate/files/{candidate_id}/...`
   - the signed S3-style file URLs inside the JSON proved to be stale by the
     time of import and should be treated as fallback provenance only, not the
     primary byte source for the official backup
4. Shift broader import planning toward static export sources now that Tom is
   cancelling JobAdder and long-term Dropbox usage:
   - Recruiterflow official backup first
   - JobAdder full export/zip next
   - broad Dropbox archive folders after that
5. Persist one Dropbox `.eml` provenance record and link it where identity is
   clean enough.
6. Decide the next Outlook step after the first fully linked `tw394`
   persistence proof:
   - [x] reconcile the first Outlook advert-response document conservatively
     against the current JobAdder applications for the same job
   - [x] record the first result clearly when no safe candidate match exists
   - reconcile later Outlook advert-response documents to canonical
     candidates/jobs only when the identity is strong enough, or
   - persist the next bounded vacancy folder in the same pattern
7. Chunk/embed the persisted `tw398` job-spec document.
8. Formalise duplicate/latest-file policy in the canonical data model and
   ingestion rules.
9. Keep Microsoft Graph as the primary mailbox source; use Dropbox as archive
   / provenance where it fits, not as the first landing zone for Outlook.
