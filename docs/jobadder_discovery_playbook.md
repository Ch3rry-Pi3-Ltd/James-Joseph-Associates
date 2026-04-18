# JobAdder Discovery Playbook

This playbook is for the first time we get access to JobAdder through Make.com
or through JobAdder's own admin/API settings.

It is not an ingestion design yet.

In plain language:

- JobAdder is likely to be one of the most important recruitment systems.
- We need to inspect what data it can expose before building backend schemas.
- The goal is to capture safe, redacted examples of the data shape.
- We should not bulk import or store real client data during discovery.

## Current Assumption

JobAdder is relevant because it may contain:

- candidates
- contacts
- companies
- jobs
- placements
- notes
- activities
- documents
- CV metadata
- pipeline/status information

Make.com appears to have a JobAdder integration, but it should be treated as a
discovery target until we prove:

- authentication works
- useful modules are available
- field output is complete enough
- rate limits and permissions are acceptable
- IDs are stable enough for ingestion

## Discovery Goal

The first goal is not to sync all of JobAdder.

The first goal is to answer:

```text
Can we safely read a small number of JobAdder records and understand their shape?
```

If yes, we can design the first real source-record schema from evidence instead
of guessing.

## What Not To Do Yet

Do not:

- bulk import all candidates
- bulk import all CVs
- commit real candidate data to Git
- send full CV text into the backend
- build canonical tables from assumptions
- connect JobAdder writes before read-only discovery is understood
- update or mutate JobAdder records from Make.com

During discovery, use read-only actions wherever possible.

## Step 1: Confirm Access

Record:

```text
Who owns the JobAdder admin account:
Who can approve API/Make access:
Which JobAdder account/environment is being used:
Whether this is production or test/sandbox:
Whether Make.com can connect successfully:
```

Questions:

- Is there a JobAdder sandbox/test environment?
- Does the client want us to use production read-only access first?
- Are API credentials available?
- Is OAuth required?
- Are there permission levels that restrict access to candidates/CVs?

## Step 2: Find The Make.com JobAdder App

In Make.com:

1. Create a test scenario.
2. Add a new module.
3. Search for:

```text
JobAdder
```

4. Record the exact app name shown in Make.com.
5. Record whether it is marked as a community app or official/native app.

Capture:

```text
Make app name:
Module provider:
Connection method:
Available trigger modules:
Available action/search modules:
Notes:
```

## Step 3: Connect JobAdder Safely

Create the JobAdder connection in Make.com.

Record:

```text
Connection name:
Authentication type:
Scopes/permissions requested:
Approved by:
Date connected:
```

Recommended connection name:

```text
JJA JobAdder - Discovery
```

If possible, use read-only permissions.

## Step 4: List Available Modules

Record the modules Make.com exposes.

Look for modules such as:

- watch candidates
- search candidates
- get candidate
- list candidates
- watch contacts
- search contacts
- get contact
- watch companies
- search companies
- get company
- watch jobs
- search jobs
- get job
- list notes
- list activities
- list attachments
- download document

Template:

```text
Candidate modules:
Contact modules:
Company modules:
Job modules:
Note/activity modules:
Document/CV modules:
Webhook/watch modules:
Search/list modules:
Update/write modules:
```

For discovery, prefer:

```text
search/list/get
```

over:

```text
create/update/delete
```

## Step 5: Run The First Safe Candidate Test

The first safe test should read one or a very small number of records.

Suggested test:

```text
Search/list candidates with a limit of 1 to 5 records.
```

If Make.com allows filters, use the safest filter available:

- a known test candidate
- a recently created dummy record
- a limited updated date range
- a specific candidate ID approved for testing

Capture:

```text
Module used:
Filters used:
Record limit:
Output fields visible:
Any errors:
```

Do not copy real personal values into Git.

Instead, capture the field names and redact values.

Example:

```json
{
  "candidate_id": "redacted",
  "first_name": "redacted",
  "last_name": "redacted",
  "email": "redacted",
  "phone": "redacted",
  "status": "redacted",
  "created_at": "redacted",
  "updated_at": "redacted"
}
```

## Step 6: Identify Candidate Fields

For candidate records, check whether these fields exist:

```text
JobAdder candidate ID:
Full name:
First name:
Last name:
Email:
Phone:
LinkedIn URL:
Location:
Current job title:
Current company:
Skills:
Status:
Owner/recruiter:
Created timestamp:
Updated timestamp:
CV/document references:
Notes:
Activities:
```

Important questions:

- Is there a stable candidate ID?
- Is email always present?
- Is LinkedIn URL present?
- Are CVs attached directly or linked separately?
- Are notes included in the candidate response, or fetched separately?
- Are activities included in the candidate response, or fetched separately?

## Step 7: Run The First Company/Contact Test

Suggested test:

```text
Search/list companies or contacts with a limit of 1 to 5 records.
```

For companies, look for:

```text
Company ID:
Company name:
Website/domain:
LinkedIn URL:
Industry/sector:
Location:
Owner:
Created timestamp:
Updated timestamp:
Notes:
Related contacts:
Related jobs:
```

For contacts/hiring managers, look for:

```text
Contact ID:
Name:
Email:
Phone:
LinkedIn URL:
Company:
Job title:
Seniority:
Owner:
Created timestamp:
Updated timestamp:
Notes:
Related jobs:
```

Important questions:

- Are contacts separate from candidates?
- Can the same person be both a candidate and a contact?
- How does JobAdder link contacts to companies?
- How does JobAdder link contacts to jobs?

## Step 8: Run The First Job Test

Suggested test:

```text
Search/list jobs with a limit of 1 to 5 records.
```

For jobs, look for:

```text
Job ID:
Job title:
Company:
Contact/hiring manager:
Job description:
Required skills:
Location:
Workplace type:
Employment type:
Salary/rate:
Status:
Opened date:
Closed date:
Created timestamp:
Updated timestamp:
Related candidates/applications:
```

Important questions:

- Does JobAdder expose job descriptions through Make.com?
- Are skills structured or only inside free text?
- Can we access related candidates/applications?
- Can we filter jobs by status?

## Step 9: Inspect Notes, Activities, And Documents

These are often where the useful recruitment context lives.

Check whether Make.com can access:

- candidate notes
- contact notes
- company notes
- job notes
- activities
- calls
- emails
- attachments
- CVs

For each object type, record:

```text
Object type:
Module used:
Parent record type:
Parent record ID:
Fields returned:
Can filter by updated date:
Can retrieve full text:
Can retrieve file metadata:
Can download file:
Sensitive data risk:
```

## Step 10: Check Change Tracking

Before designing sync, check whether JobAdder can tell us what changed.

Look for:

- watch modules
- webhooks
- records updated since timestamp
- created_at fields
- updated_at fields
- deleted/archived indicators

Template:

```text
Can watch new candidates:
Can watch updated candidates:
Can filter candidates by updated_at:
Can watch jobs:
Can watch notes/activities:
Can detect deleted/archived records:
Notes:
```

This determines whether the first workflow should be:

```text
scheduled polling
```

or:

```text
event/webhook driven
```

## Step 11: Decide The First Backend Payload

Once we have one real redacted Make.com output, decide the first safe backend
payload.

Do not jump straight to canonical entities.

The first backend payload should probably be a raw source record envelope:

```json
{
  "source_system": "jobadder",
  "source_record_type": "candidate",
  "source_record_id": "redacted",
  "source_updated_at": "redacted",
  "payload": {
    "redacted": "example"
  }
}
```

This lets the backend store or validate the source record before trying to
decide whether it is a canonical person, candidate, contact, or company.

## Step 12: Discovery Output To Capture

At the end of JobAdder discovery, capture:

```text
1. Exact Make.com JobAdder app/module name.
2. Connection/auth method.
3. Candidate output field list.
4. Company output field list.
5. Contact output field list.
6. Job output field list.
7. Note/activity availability.
8. Document/CV availability.
9. Stable source IDs.
10. Timestamp/change tracking support.
11. Known sensitive fields.
12. First recommended record type for ingestion.
13. First recommended Make.com scenario.
```

## Ready For Ingestion Design Criteria

JobAdder is ready for ingestion design when we have:

- confirmed Make.com connection
- one redacted candidate sample
- one redacted company/contact sample
- one redacted job sample, if available
- stable source IDs
- created/updated timestamp behaviour
- known sensitive fields
- confirmed read-only discovery path
- agreed first workflow

Until then, keep JobAdder work in discovery mode.

