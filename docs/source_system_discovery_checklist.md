# Source System Discovery Checklist

This checklist is for reviewing each client system before we design real
ingestion schemas or build production data pipelines.

In plain language:

- we know Make.com can talk to our backend
- we know the client has many useful systems and data sources
- we do not yet know the exact data shape from those systems
- this checklist tells us what to capture before we write ingestion code

## Why This Exists

The project should not guess the shape of real recruitment data.

Before building endpoints such as:

```text
POST /api/v1/source-records
```

we need to inspect real examples from each source system.

This matters because different systems may describe the same real-world thing in
different ways.

For example:

- a candidate in JobAdder
- a LinkedIn connection in LinkedHelper
- a CV file in Dropbox
- an email attachment in Outlook
- a spreadsheet row in Excel

may all refer to the same person, but they will not have the same fields,
identifiers, timestamps, or data quality.

## Discovery Status

Current status:

```text
Make.com -> Vercel -> FastAPI backend
```

is working.

Real source-system access:

```text
Not available yet
```

Therefore, the next step is discovery rather than final ingestion coding.

## Service Priority Order

Start with the systems most likely to contain high-value recruitment data.

1. JobAdder
2. LinkedHelper
3. Dropbox CV folders
4. Outlook CV attachments and recruitment emails
5. Pipedrive legacy records
6. Google Sheets / Microsoft Excel legacy data
7. SourceBreaker
8. SourceWhale
9. Recruiterflow
10. Ringover
11. Calendly
12. Asana / Slack

This order can change once access is available.

## Checklist Per Source System

Use this section once per system.

### 1. Basic System Details

Record:

- system name
- owner/admin contact
- login/access method
- whether Make.com has a native module
- whether API access exists
- whether export exists
- whether webhooks exist
- whether the system is current, legacy, or planned

Template:

```text
System name:
Current status:
Admin/contact:
Access method:
Native Make module:
HTTP/API available:
Webhook available:
CSV/export available:
Notes:
```

### 2. First Safe Test

Define the smallest safe test we can run.

The first test should avoid bulk data and avoid unnecessary sensitive data.

Examples:

- list one candidate
- export five test rows
- list one folder
- download one non-sensitive sample file
- fetch one recent activity
- read one test email folder

Template:

```text
First safe test:
Expected output:
Sensitive data risk:
Who approves this:
```

### 3. Example Payload Or Export Shape

Capture one representative example of the data shape.

This can be:

- Make.com module output
- API response JSON
- CSV header row
- spreadsheet column list
- file metadata
- webhook payload

Do not paste real sensitive data into Git.

If needed, redact values but keep field names and structure.

Good:

```json
{
  "candidate_id": "redacted",
  "first_name": "redacted",
  "last_name": "redacted",
  "email": "redacted",
  "updated_at": "2026-04-18T10:00:00Z"
}
```

Bad:

```json
{
  "candidate_id": "12345",
  "first_name": "Real",
  "last_name": "Person",
  "email": "real.person@example.com"
}
```

Template:

```text
Payload/export type:
Field names captured:
Sample redacted:
Unknown fields:
Notes:
```

### 4. Stable IDs

Identify the fields that can be used to track the same record over time.

This is essential for idempotency and deduplication.

Look for:

- candidate ID
- contact ID
- company ID
- job ID
- email message ID
- file ID
- call ID
- event ID
- source URL
- LinkedIn profile URL

Template:

```text
Primary source ID:
Secondary IDs:
Is the ID stable across exports:
Can records be deleted:
Can records be merged:
Notes:
```

### 5. Record Types

Identify what real-world entities the system contains.

Common recruitment record types:

- candidate
- client
- company
- hiring manager
- contact
- job
- vacancy
- placement
- note
- activity
- email
- CV
- attachment
- call
- meeting
- outreach sequence
- LinkedIn connection
- LinkedIn invitation

Template:

```text
Record types present:
Most important record type:
Related records:
Relationship fields:
Notes:
```

### 6. Timestamps And Change Tracking

Identify whether the system can tell us what changed and when.

Useful fields:

- created_at
- updated_at
- deleted_at
- last_activity_at
- last_contacted_at
- imported_at
- source_modified_at

Useful capabilities:

- watch new records
- watch updated records
- list records updated since a timestamp
- webhook events
- export all records

Template:

```text
Created timestamp:
Updated timestamp:
Deleted/archived signal:
Can filter by updated date:
Can watch changes:
Notes:
```

### 7. Sensitive Data

Identify sensitive data before moving it.

Sensitive examples:

- personal email addresses
- phone numbers
- home addresses
- CVs
- salary details
- interview notes
- call recordings
- email content
- LinkedIn messages
- client commercial information

Template:

```text
Sensitive fields:
Personal data present:
CVs/documents present:
Call recordings present:
Email/message content present:
Redaction needed for samples:
Notes:
```

### 8. Data Quality

Capture obvious quality issues.

Look for:

- duplicate people
- missing emails
- inconsistent company names
- old records
- incomplete phone numbers
- invalid LinkedIn URLs
- mixed candidate/client records
- notes containing important structured facts
- data trapped in free-text fields

Template:

```text
Known quality issues:
Duplicate risk:
Missing fields:
Important free-text fields:
Cleanup needed:
Notes:
```

### 9. Volume And Frequency

Estimate size and sync needs.

Template:

```text
Approx record count:
Approx file count:
Approx daily changes:
One-off migration or ongoing sync:
Recommended sync frequency:
Notes:
```

### 10. First Backend Ingestion Candidate

Decide whether this source is ready for backend ingestion.

Do not mark a source as ready until we know:

- access method
- field shape
- stable ID
- sensitive data risk
- first useful workflow

Template:

```text
Ready for ingestion design:
Reason:
Recommended first endpoint:
Recommended source_record_type:
Blockers:
Notes:
```

## Per-Service Starting Notes

### JobAdder

Detailed playbook:

- `docs/jobadder_discovery_playbook.md`

Likely value:

- current CRM/ATS records
- candidates
- contacts
- companies
- jobs
- activities
- notes

Main discovery questions:

- Does the Make.com community module work reliably?
- What authentication is required?
- Can we list candidates, contacts, companies, jobs, and notes?
- What stable IDs exist?
- Can we query records changed since a timestamp?

### LinkedHelper

Likely value:

- LinkedIn connections
- invited contacts
- accepted/not-accepted connection state
- profile export data

Main discovery questions:

- Can LinkedHelper export CSV?
- Does it provide API access?
- What fields are included in exports?
- Does it include LinkedIn profile URLs?
- Can it refresh profile data?

### Dropbox CV Folders

Likely value:

- unparsed CVs
- candidate documents
- historical document lake

Main discovery questions:

- Which folders contain CVs?
- Are filenames meaningful?
- Can Make.com watch folders?
- Can Make.com download files safely?
- What file types are common: PDF, DOCX, DOC?
- Do we need OCR for scanned PDFs?

### Outlook

Likely value:

- CV attachments
- candidate/client conversations
- hiring context
- meeting follow-ups

Main discovery questions:

- Which mailbox/folders matter?
- Can Make.com filter emails by folder, sender, or attachment?
- Can we safely test on a limited folder?
- Do we ingest email body, attachments, or metadata first?

### Pipedrive

Likely value:

- legacy CRM data
- people
- organisations
- deals
- activities
- notes

Main discovery questions:

- Which Pipedrive objects contain recruitment data?
- Are custom fields used?
- Can Make.com export all relevant objects?
- What needs to be migrated versus ignored?

### Google Sheets / Microsoft Excel

Likely value:

- manually captured company, hiring-manager, and candidate data
- messy historical notes
- operational tracking

Main discovery questions:

- Which sheets/workbooks matter?
- What are the column headers?
- Are there multiple formats?
- Which rows are still useful?
- Can this be treated as one-off migration data?

### SourceBreaker

Likely value:

- market intelligence
- companies advertising for skillsets
- job-demand signals
- candidate/job matching context

Main discovery questions:

- Does SourceBreaker provide API access?
- Does it export CSV?
- What data can be exported?
- Can searches be automated or scheduled?

### SourceWhale

Likely value:

- outreach sequences
- contact attempts
- engagement history
- candidate/client outreach state

Main discovery questions:

- Does SourceWhale expose API/export access?
- Can it sync to JobAdder or another ATS?
- Can outreach activities be exported?
- Which system should be the source of truth for outreach?

## When To Start Building Ingestion

Start building real ingestion only after we have at least one source with:

- confirmed access
- one redacted sample payload/export
- stable source ID
- agreed first record type
- clear sensitive-data handling
- agreed first workflow

The first real ingestion route will probably be:

```text
POST /api/v1/source-records
```

But that route should not be designed from guesses.

It should be based on a real sample from the first source system we choose.
