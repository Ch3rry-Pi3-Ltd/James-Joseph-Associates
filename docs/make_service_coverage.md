# Make.com Service Coverage Notes

This note records what we currently know about connecting the client's tools to
Make.com.

It is a planning document, not an implementation document.

In plain language:

- Make.com can already call our Vercel backend.
- We have proved that with the protected `POST /api/v1/make/test-event` route.
- The next real limitation is access to the client's actual source systems.
- Until we can connect to those systems, we should not design final ingestion
  schemas.

## Current Connection Status

The current confirmed connection is:

```text
Make.com
    -> protected HTTP request
    -> Vercel
    -> FastAPI backend
    -> POST /api/v1/make/test-event
```

This proves:

- Make.com can reach the deployed backend.
- Make.com can send a bearer token.
- Make.com can send JSON.
- Make.com can send an `Idempotency-Key`.
- Make.com can include execution metadata through headers.
- The backend can return a controlled `accepted` response.

This does not prove:

- any client source system is connected yet
- any real recruitment data is available yet
- any source-record schema is correct yet
- any Supabase write path is ready yet

## Make.com Coverage Table

| Service | Make.com module status | Current relevance | Notes |
|---|---|---|---|
| JobAdder | Native/community module found | High | Useful because it may become the current CRM/ATS source. The module appears to be community-developed, so it should be tested carefully before relying on it. |
| Pipedrive | Native module found | High | Useful for legacy CRM extraction and migration. Strong Make support appears to exist for people, organisations, deals, notes, activities, files, and related CRM objects. |
| LinkedIn | Native module found | High | Useful for LinkedIn-facing actions, but likely not enough by itself for unrestricted Recruiter Lite data extraction. Needs practical testing. |
| Linked API | Native module found | High | Appears useful for LinkedIn person/company style data. Needs account/API review before use. |
| LinkedHelper | Not clearly confirmed | High | Likely important because it may export LinkedIn connection/invite/profile data. Integration may need CSV export, HTTP/API, or manual export flow. |
| SourceBreaker | Not clearly confirmed | High | Important for market/job-demand intelligence. Need to inspect available exports, webhooks, or APIs. |
| SourceWhale | Not clearly confirmed as a Make module | High | SourceWhale itself integrates with many ATS/CRM tools. May need SourceWhale's own integration/export/API path rather than a native Make module. |
| Recruiterflow | Not clearly confirmed | Medium/high | Legacy ATS/CRM source. May need API credentials, export, or migration route. |
| Dropbox | Native module found | High | Important for the CV/document lake. Useful for watching folders, listing files, downloading files, and sending files onward for parsing. |
| Outlook / Microsoft 365 Email | Native module found | High | Important for CV attachments, candidate/client conversations, and email-derived context. |
| Google Sheets | Native module found | High | Useful for messy manual data and early discovery payloads. |
| Microsoft 365 Excel | Native module found | High | Useful for legacy spreadsheets and manual operational data. |
| Google Drive | Native module found | Medium/high | Useful if documents or sheets live in Google Drive. |
| OneDrive | Native module found | Medium/high | Useful if Office documents or CVs live in OneDrive. |
| Asana | Native module found | Medium | Useful for tasks, workflow state, and operational follow-ups. Probably not the first recruitment data source. |
| Slack | Native module found | Medium | Useful for notifications, operational updates, and possibly extracting structured decisions later. |
| Calendly | Native module found | Medium | Useful later for meeting/call events. |
| Ringover | Native module found | Medium/high | Useful later for call/SMS/WhatsApp events and contact activity. |
| Supabase | Native module found | High | Useful, but serious database writes should probably go through our backend so validation, idempotency, and audit rules stay centralised. |
| OpenAI | Native module found | Medium/high | Useful for Make-level lightweight AI steps, but core reasoning workflows should probably live in Python/LangChain/LangGraph where they can be tested and versioned. |
| Perplexity AI | Native module found | Medium | Useful for research-style enrichment and citation-backed checks. |
| OpenRouter | Native module found | Medium | Useful for model routing/cost control experiments. |
| Power BI | Native module found | Later | Useful once clean data and KPIs exist. Not needed before source data is understood. |

## How To Link Unsupported Or Unclear Services

If Make.com does not have a clean native module for a service, we still have
several routes.

### Option 1: HTTP API

Use Make.com's HTTP module to call the service's API directly.

This works when the service provides:

- API documentation
- API keys or OAuth credentials
- stable endpoints
- permission to access the relevant data

Example flow:

```text
Make.com HTTP module
    -> service API
    -> response data
    -> our backend ingestion endpoint
```

### Option 2: Webhooks

Use a webhook if the service can send events when records change.

This works when the service supports events such as:

- new candidate
- updated contact
- new file
- new email
- new call
- new note
- new outreach activity

Example flow:

```text
service webhook
    -> Make.com webhook
    -> transform/normalise
    -> our backend ingestion endpoint
```

### Option 3: CSV Or Spreadsheet Export

Use CSV, Excel, or Google Sheets as a staging route.

This is often the fastest path for legacy systems or awkward tools.

Example flow:

```text
service export
    -> CSV / Excel / Google Sheets
    -> Make.com reads rows
    -> our backend ingestion endpoint
```

This is especially relevant for:

- LinkedHelper exports
- legacy spreadsheets
- Recruiterflow exports
- SourceBreaker exports
- SourceWhale exports
- LinkedIn-derived exports

### Option 4: File Watchers

Use Dropbox, Google Drive, OneDrive, or Outlook attachments as file sources.

This is useful for CVs and documents.

Example flow:

```text
new file or attachment
    -> Make.com detects/downloads file
    -> our backend receives file metadata or file content
    -> backend queues parsing/chunking/enrichment later
```

### Option 5: Custom Make App

Build a custom Make app only if the service is important enough and the API is
stable enough.

This should come after we have proved:

- the service API is useful
- authentication is manageable
- the data shape is stable
- the workflow will be reused

### Option 6: Manual Discovery First

Before automating, we can manually export a small safe sample and inspect it.

This is often the best first step when:

- the source system is messy
- the API is unclear
- the data is sensitive
- we do not know which fields matter yet

## Current Blocker

We do not currently have enough access to the client's source systems to design
real ingestion schemas.

The missing information is:

- which services we can actually connect to
- which services have API credentials available
- which services have export options
- what one real record looks like from each service
- which record IDs are stable
- which fields contain sensitive personal data
- which fields are needed for matching, retrieval, and reporting

## Recommended Next Work

Before building real ingestion code, create a discovery checklist for the first
few source systems.

Suggested order:

1. JobAdder
2. LinkedHelper
3. Dropbox CV folders
4. Outlook CV attachments
5. Pipedrive legacy records
6. Google Sheets / Excel legacy data
7. SourceBreaker
8. SourceWhale

For each service, we should capture:

- access method
- whether a native Make module exists
- whether HTTP/API access is available
- whether export is available
- example record shape
- stable source ID
- sensitive fields
- rough volume
- sync frequency
- first safe test scenario

In plain language:

- we know Make.com can talk to our backend
- we know many services can probably be connected
- we do not yet know the real data shapes
- the next step is discovery, not final ingestion coding

