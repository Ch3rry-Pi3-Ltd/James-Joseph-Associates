# Source Data Requirements

<details open>
<summary><strong>1. Purpose</strong></summary>

This document lists the sample source data needed before writing the first real Supabase schema migrations beyond extension setup.

The goal is to avoid designing a tidy schema that does not match the shape, quality, and constraints of the actual recruitment data.

This document should guide collection of safe sample records from the first priority systems.

Related planning notes:

- `docs/make_service_coverage.md` records which services appear to have Make.com
  modules and how unsupported services can still be connected.
- `docs/source_system_discovery_checklist.md` provides the checklist to use once
  access to each source system is available.

</details>

<details open>
<summary><strong>2. Why This Comes Before Core Tables</strong></summary>

The next planned migration is:

```text
supabase/migrations/0002_core_entities.sql
```

That migration should define the first canonical tables, such as companies, people, candidates, contacts, jobs, skills, documents, and interactions.

Before writing it, we need to understand:

- Which fields actually exist in the source systems.
- Which fields are reliable.
- Which fields are duplicated or contradictory.
- Which source IDs can be used for idempotency.
- Which fields are sensitive.
- Which fields are needed for the first matching workflow.
- Which relationships can be inferred safely.

Current blocker:

- Make.com can now securely call the backend.
- The backend has a protected Make.com test endpoint.
- Real source-system access is not available yet.
- Real sample payloads have not been collected yet.
- Therefore, real source-record schemas and core entity migrations should wait
  until discovery samples exist.

</details>

<details>
<summary><strong>3. Required Sample Data</strong></summary>

Collect safe examples from the first priority systems. Samples should be representative, but they must not contain unnecessary sensitive data.

## Candidate Records

Needed to design:

- `people`
- `candidates`
- `candidate_skills`
- `person_company_roles`
- document links
- source-record mapping

Useful fields to inspect:

- source system name
- source record ID
- full name
- email
- phone
- LinkedIn URL or identifier, if legally usable
- current job title
- current company
- previous companies
- location
- skills
- candidate status
- availability
- salary or rate fields, if used
- CV/document references
- notes or summary fields
- created/updated timestamps

## Company Records

Needed to design:

- `companies`
- `contacts`
- `jobs`
- company-role relationships
- company deduplication rules

Useful fields to inspect:

- source system name
- source record ID
- company name
- website/domain
- LinkedIn URL
- industry/sector
- location
- size range
- status
- owner/account manager
- notes
- created/updated timestamps

## Contact and Hiring Manager Records

Needed to design:

- `people`
- `contacts`
- `person_company_roles`
- interaction participants

Useful fields to inspect:

- source system name
- source record ID
- full name
- email
- phone
- LinkedIn URL or identifier, if legally usable
- company
- role title
- seniority
- contact type
- hiring manager flag, if present
- relationship owner
- created/updated timestamps

## Job or Opportunity Records

Needed to design:

- `jobs`
- `job_required_skills`
- company/job relationships
- matching inputs

Useful fields to inspect:

- source system name
- source record ID
- job title
- company
- hiring manager/contact
- job description
- required skills
- preferred skills
- location
- workplace type
- employment type
- salary/rate fields
- status
- opened date
- closed date
- created/updated timestamps

## Document Samples

Needed to design:

- `documents`
- `document_chunks`
- `embeddings`
- `document_links`
- provenance records

Useful examples:

- CV file metadata
- job specification file metadata
- extracted text sample
- document storage location
- content hash or fingerprint, if available
- source-system document ID, if available
- linked candidate/job/company/contact

## Interaction or Note Samples

Needed to design:

- `interactions`
- `interaction_participants`
- retrieval evidence
- provenance

Useful fields to inspect:

- source system name
- source record ID
- interaction type
- occurred timestamp
- subject
- body/note text
- participants
- related company
- related candidate
- related job
- owner/user
- created/updated timestamps

</details>

<details>
<summary><strong>4. Source-System Metadata Needed</strong></summary>

For each priority source system, capture:

- system name
- whether it is legacy or active
- access method: API, export, webhook, manual upload, or Make.com
- record types available
- source IDs available
- export format
- timestamp fields
- rate limits or access limits
- legal/platform constraints
- owner or admin contact
- whether it remains operational during Phase 1

</details>

<details>
<summary><strong>5. Safety Rules for Samples</strong></summary>

Sample data used in the repository must be fake or safely anonymised.

Do not commit:

- real candidate names
- real client names unless explicitly approved
- real email addresses
- real phone numbers
- real CV text
- real LinkedIn profile URLs
- real salary details
- confidential notes
- access tokens or credentials

If real samples are needed for analysis, keep them outside the repository and document only their shape.

</details>

<details>
<summary><strong>6. Minimum Needed Before `0002_core_entities.sql`</strong></summary>

Before writing the core entity migration, collect at least:

- 3 to 5 candidate record examples.
- 3 to 5 company record examples.
- 3 to 5 contact or hiring manager examples.
- 3 to 5 job or opportunity examples.
- 2 to 3 document metadata examples.
- 2 to 3 interaction or note examples, if available.

For each example, capture:

- source system
- source record ID shape
- field names
- field types
- nullable fields
- repeated/list fields
- nested objects
- update timestamp behaviour

</details>

<details>
<summary><strong>7. Open Questions</strong></summary>

Questions to resolve before finalising the core schema:

- Which source provides the first candidate records?
- Which source provides the first job records?
- Which source provides company and contact records?
- Are CVs stored in Supabase Storage, external storage, or metadata-only in Phase 1?
- Which fields are sensitive enough to require stricter access controls?
- Which source wins when two systems disagree?
- Is job-to-candidate matching confirmed as the first workflow?
- What source IDs can support idempotent ingestion?
- What sample data can safely be committed as fake fixtures later?
- Which source system should be inspected first in Make.com?
- Does JobAdder's community Make.com module expose the data we need?
- Can LinkedHelper provide a CSV/API export with stable LinkedIn profile URLs?
- Can Dropbox and Outlook provide safe limited CV/document samples without bulk
  personal data exposure?

</details>
