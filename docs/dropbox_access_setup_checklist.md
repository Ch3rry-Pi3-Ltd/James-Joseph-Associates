# Dropbox Access and Source-Shape Checklist

This document turns the next Dropbox workstream into a concrete setup and
inspection plan.

It is not yet an ingestion design. It is the checklist we should work through
before deciding how Dropbox CVs should enter the canonical Supabase model.

## Why this document exists

The JobAdder path is now in a materially better place:

- CV extraction is working
- batching and skip logic are working
- accepted CV persistence is working
- no-resume profile-only persistence is working
- JobAdder notes now write into first-class interactions
- post-write verification is working

That means the next practical unknown is no longer the JobAdder pipeline. It
is the next source system.

Dropbox is the most sensible next source because it is likely to contain a
large volume of candidate CVs that need to be:

- discovered
- classified
- matched against existing canonical candidates where possible
- retained with provenance when they do not match cleanly

## 1. What we need from Tom

Before we inspect anything, we should get clarity on the authorization and
scope boundary.

### Authorization model

- Roger does **not** need his own Dropbox account for this integration.
- The backend can use a normal Dropbox OAuth app flow, similar in broad shape
  to the JobAdder setup:
  - a shared Dropbox app is registered once in the Dropbox App Console
  - the backend is configured with that app key, app secret, and redirect URI
  - Tom is sent one authorization URL to approve the app against his Dropbox
  - the backend stores the returned token set and performs API reads later
- This means the practical next setup step is not "create Roger a Dropbox
  account". It is:
  - register the shared Dropbox app
  - configure the backend
  - send Tom the approval URL

### Current app-scope decision

- The shared Dropbox app is now expected to support both:
  - immediate Dropbox reads for source discovery
  - later Dropbox writes for staged document pushes such as Outlook CV
    attachments
- Because Dropbox scopes are attached to the granted token set, and adding new
  scopes later would force a re-authorization flow, the current app should ask
  for the broader first-pass scope set **before** Tom approves access.
- The current intended Dropbox scopes are:
  - `account_info.read`
  - `files.metadata.read`
  - `files.content.read`
  - `sharing.read`
  - `files.metadata.write`
  - `files.content.write`
- This is still intentionally narrower than full sharing/admin write access.
- We are **not** currently asking for `sharing.write` because simply uploading
  Outlook-derived CVs into Dropbox does not require it.

### Access

- Confirm whether the Dropbox area Tom wants us to inspect is:
  - personal Dropbox
  - team/business Dropbox
  - or primarily shared folders
- Confirm whether the first pass should be strictly read-only.
- Confirm whether there are any policy reasons to prefer exported samples over
  live API reads for the very first inspection pass.
- Confirm whether staged write-back into Dropbox is acceptable once the Outlook
  attachment flow is live.

### Scope

- Confirm which folders are in scope for the first review.
- Confirm whether the folders contain:
  - only CVs
  - CVs plus other documents
  - mixed historic recruiter/admin files
- Confirm whether there are any folders that should be excluded from the first
  pass.

### Sensitivity

- Confirm whether any folders contain especially sensitive documents that
  should not be touched in the first pass.
- Confirm whether there are any legal/compliance restrictions around copying or
  re-staging files.

## 2. What we need to inspect first

The first Dropbox pass should be small and observational.

We should inspect:

- top-level folder structure
- one or two levels of nested folders
- file naming conventions
- whether candidate names appear in file names
- whether folders are grouped by:
  - consultant
  - year
  - client
  - candidate
  - workflow stage

We should also sample the actual file types:

- PDF
- DOCX
- DOC
- image scans
- duplicate CV versions
- non-CV files such as cover letters or admin notes

## 3. Questions the first inspection must answer

The Dropbox review is useful only if it answers a few concrete questions.

### A. Is Dropbox mainly a document source or also a candidate source?

We need to determine whether Dropbox gives us:

- only files that need attaching to existing people/candidates
- or enough structure to justify candidate creation directly from Dropbox

### B. How matchable are the files?

For a sampled set of files, we should check whether they can be matched by:

- candidate name in filename
- email extracted from CV text
- phone extracted from CV text
- LinkedIn URL extracted from CV text
- strong overlap with existing JobAdder candidates

### C. How noisy is the source?

We need to see how often we hit:

- duplicate CV versions
- renamed copies of the same CV
- non-CV files in CV folders
- incomplete scans
- password-protected files
- unsupported formats

### D. What should count as a Dropbox ingest success?

Before bulk ingestion, we should define a narrow standard such as:

- file discovered
- file classified as likely CV or not
- file text extracted if supported
- canonical person/candidate matched or created
- document retained with provenance

## 4. Recommended first sample size

Do not start with the whole Dropbox corpus.

Start with:

- 20-30 files max
- spread across more than one folder if possible
- deliberately mixed if the source looks messy

That sample should be enough to answer:

- how clean the naming is
- how often files are true CVs
- whether the likely matching signals are strong enough

## 5. Minimum metadata we should capture during the first review

For each sampled file, capture at least:

- Dropbox path
- filename
- extension
- file size
- modified timestamp
- likely document type:
  - CV
  - cover letter
  - admin/other
- whether text extraction succeeds
- whether candidate match seems:
  - strong
  - plausible
  - weak
  - none

This should be enough to support the next ingestion design step without
overbuilding the first review.

## 6. Likely ingestion directions after the review

The Dropbox review will probably push us toward one of three models.

### Model 1: document-first attachment source

Use Dropbox mainly as:

- a source of CV documents
- attached to existing candidates/people where matching is strong

This is the safest model if JobAdder already covers most candidate identity.

### Model 2: mixed document plus candidate enrichment source

Use Dropbox as:

- a document source
- plus a fallback source of candidate data when JobAdder is incomplete

This is more useful if many CVs are outside JobAdder or more current than
JobAdder.

### Model 3: reconciliation-first source

Use Dropbox only after:

- matching against existing canonical records
- deciding preferred/current CV policy

This is likely the right model if the folders are messy and highly duplicated.

## 7. Risks to look for immediately

The first Dropbox review should actively look for these problems:

- duplicate CVs with different filenames
- old CVs mixed with newer versions
- missing candidate identifiers in filenames
- bulk folders with no obvious ownership structure
- non-CV documents mixed into candidate folders
- unsupported formats
- files whose text is hard to extract cleanly

These are not reasons to avoid Dropbox. They are the issues that decide what
the ingestion policy needs to be.

## 8. Recommended output of the first Dropbox review

The first Dropbox review should produce a short design note covering:

- access method used
- folder structure observed
- file-type breakdown
- sample matching quality
- likely ingestion model
- risks
- recommendation on whether Dropbox should be ingested:
  - before wider multi-source reconciliation
  - after more reconciliation work
  - or in a narrow document-only first pass

## 9. What we should ask Tom next

The practical next ask to Tom should be:

1. confirm the Dropbox app registration owner and callback URI
2. which folder(s) to inspect first
3. whether we should treat the first pass as strictly read-only
4. whether there are any folders to exclude
5. whether a 20-30 file sample is acceptable for the first review

## 10. Dropbox OAuth status

The current live Dropbox work has now reached the point where:

- the backend can build a working Dropbox authorization URL
- the redirect URI mismatch has been resolved
- Tom can now reach the Dropbox approval flow
- the `dropbox_oauth_connections` table has been applied to the live database

That means the remaining Dropbox setup work is no longer backend scaffolding.
It is:

- completing Tom's real authorization successfully
- confirming the saved Dropbox connection
- performing the first authenticated folder read

## 11. Immediate recommendation

The right next Dropbox move is:

- get read access
- inspect a small sample
- do not bulk ingest yet
- decide the matching/reconciliation policy from real source evidence

That keeps the project aligned with the current approach taken on JobAdder:

- prove the narrow path
- verify the write model
- then widen carefully
