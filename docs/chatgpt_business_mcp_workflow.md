# ChatGPT Business MCP Workflow

## Purpose

This document defines the first practical path for a ChatGPT-style recruiter
assistant that can query the canonical Supabase data safely.

The key design choice is:

- do **not** connect ChatGPT Business directly to raw Supabase
- expose a **read-only MCP app** in front of Supabase
- let Tom use that app from his ChatGPT Business workspace

That gives us:

- grounded answers
- a controlled tool surface
- permission boundaries
- a path to later add approved write actions without exposing the database
  directly

## What Tom Should Be Able To Ask

The first release should support questions such as:

- Who do we know at this company?
- Which candidates fit this job description?
- Who has spoken to this company before?
- What jobs or opportunities are already linked to this account?
- Summarise the prior notes and interaction history for this company.
- Why was this candidate shortlisted?
- Which candidates have Rust and trading-system experience?
- Which people in the database currently work at this firm?

## Recommended V1 Scope

The first release should be **read-only**.

That means:

- search
- retrieval
- evidence assembly
- answer generation
- no mutation of canonical records yet

This keeps the risk low while giving Tom a real operational assistant.

## MCP Tool Surface

The first MCP app should expose a small, explicit toolset.

### 1. Search candidates from a role brief

Purpose:

- take a free-text job description or role brief
- run the existing retrieval + shortlist logic
- return ranked candidates with strengths, gaps, and evidence

Likely backing routes/services:

- candidate search
- candidate shortlist

### 2. Inspect candidate profile

Purpose:

- fetch a full candidate view
- show title, company, skills, linked context, and current-resume metadata

### 3. Open current CV / resume document

Purpose:

- fetch the current canonical resume document reference
- allow the assistant or UI to cite the underlying CV evidence

### 4. Inspect company context

Purpose:

- find a canonical company
- return linked candidates, contacts, jobs, opportunities, and supporting
  evidence

### 5. Inspect known contacts / hiring-manager context

Purpose:

- list known people linked to a company
- surface whether we already know anyone there
- show relationship context where available

### 6. Inspect prior interactions and notes

Purpose:

- return interaction history already stored in canonical form
- support questions about previous conversations and prior recruiter context

### 7. Inspect linked jobs and opportunities

Purpose:

- show open or historical jobs/opportunities linked to a company or contact

### 8. Explain shortlist evidence

Purpose:

- convert the retrieved evidence into a recruiter-facing explanation:
  - why this candidate
  - what are the gaps
  - what evidence supports the ranking

## V1 MCP Tool Schemas

The first MCP release should keep the tool surface small and explicit.

The tool names below are written in MCP-style terms, but they map onto the
existing backend routes/services wherever possible.

### `search_candidates_for_role`

Purpose:

- take a role brief
- retrieve an initial candidate pool
- optionally produce a ranked shortlist

Input:

```json
{
  "role_brief": "string",
  "search_limit": 10,
  "candidate_pool_limit": 25,
  "shortlist_limit": 5,
  "include_shortlist": true
}
```

Output:

```json
{
  "retrieval_query": "string",
  "detected_target_company": "string | null",
  "candidate_pool_size": 25,
  "search_results": [],
  "shortlist_results": []
}
```

### `get_candidate_profile`

Purpose:

- fetch one candidate profile with linked evidence and canonical fields

Input:

```json
{
  "candidate_id": "uuid"
}
```

Output:

```json
{
  "candidate_id": "uuid",
  "full_name": "string",
  "current_title": "string | null",
  "current_company_name": "string | null",
  "candidate_status": "string | null",
  "resume_updated_at": "timestamp | null",
  "skills": [],
  "contacts": [],
  "jobs": [],
  "opportunities": [],
  "interactions": []
}
```

### `get_candidate_current_resume`

Purpose:

- fetch the current downloadable resume reference for one candidate

Input:

```json
{
  "candidate_id": "uuid"
}
```

Output:

```json
{
  "candidate_id": "uuid",
  "file_name": "string",
  "content_type": "string",
  "download_url": "string | null",
  "source_system": "string | null"
}
```

Implementation note:

- MCP tools should return a secure reference or signed fetch path, not raw file
  bytes by default

### `search_company_context`

Purpose:

- find one target company and return the linked operating context

Input:

```json
{
  "company_name": "string",
  "candidate_limit": 10,
  "contact_limit": 10,
  "interaction_limit": 10,
  "job_limit": 10,
  "opportunity_limit": 10
}
```

Output:

```json
{
  "company_name": "string",
  "candidates": [],
  "contacts": [],
  "interactions": [],
  "jobs": [],
  "opportunities": []
}
```

### `list_company_directory`

Purpose:

- provide a typeahead/searchable list of known canonical companies

Input:

```json
{
  "prefix": "string | null",
  "limit": 50
}
```

Output:

```json
{
  "count": 50,
  "companies": [
    "Company A",
    "Company B"
  ]
}
```

### `discover_company_leads_for_candidate`

Purpose:

- start from one candidate and a target company
- show linked contacts, jobs, interaction history, and peer candidates

Input:

```json
{
  "candidate_id": "uuid",
  "company_name": "string",
  "limit": 10
}
```

Output:

```json
{
  "candidate": {},
  "target_company_name": "string",
  "contacts": [],
  "jobs": [],
  "interactions": [],
  "peer_candidates": []
}
```

### `answer_recruiter_question`

Purpose:

- grounded natural-language answer over the read-only tools above
- this should orchestrate retrieval, not query Supabase directly

Input:

```json
{
  "question": "string",
  "conversation_id": "string | null",
  "max_candidates": 5,
  "max_contacts": 5,
  "max_interactions": 5
}
```

Output:

```json
{
  "answer": "string",
  "supporting_entities": [],
  "supporting_candidates": [],
  "supporting_companies": [],
  "supporting_contacts": [],
  "supporting_interactions": [],
  "citations": []
}
```

## Current Backend Route Mapping

The first MCP layer should reuse existing routes/services as far as possible.

### Already Mapped Cleanly

#### Candidate search and shortlist

- `GET /api/v1/candidates/search-resumes`
- `POST /api/v1/candidates/match-job-description`

Maps to:

- `search_candidates_for_role`

#### Candidate profile

- `GET /api/v1/candidates/{candidate_id}`

Maps to:

- `get_candidate_profile`

#### Current resume access

- `GET /api/v1/candidates/{candidate_id}/current-resume`

Maps to:

- `get_candidate_current_resume`

#### Company directory

- `GET /api/v1/candidates/company-directory`

Maps to:

- `list_company_directory`

#### Company-linked candidates

- `GET /api/v1/candidates/discover-by-company`

#### Company-linked contacts

- `GET /api/v1/candidates/discover-contacts-by-company`

#### Company-linked interactions

- `GET /api/v1/candidates/discover-interactions-by-company`

#### Company-linked jobs

- `GET /api/v1/candidates/discover-jobs-by-company`

#### Company-linked opportunities

- `GET /api/v1/candidates/discover-opportunities-by-company`

Together these map to:

- `search_company_context`

#### Candidate to company lead flow

- `GET /api/v1/candidates/{candidate_id}/company-leads`

Maps to:

- `discover_company_leads_for_candidate`

### Thin MCP Adapter Needed

These do not need major new backend primitives, but they do need an adapter
layer.

#### Unified company context tool

The MCP tool should call the five company-discovery routes and return one
merged response rather than exposing five separate tools to ChatGPT.

#### Natural-language Q&A tool

`answer_recruiter_question` should:

- classify the recruiter question
- decide which read-only tools to call
- assemble evidence
- return a grounded answer with citations

This is where the assistant behavior lives. It should not be implemented as
direct SQL or raw Supabase exposure.

### Gaps Still To Fill

The following still need deliberate implementation or clarification before the
assistant is complete.

- persisted conversation/session memory policy
- citation format for notes/interactions/documents
- access policy for downloadable CV references
- audit logging for assistant queries
- optional summarization route for long interaction histories


## Memory Model

There are two different kinds of memory here and they should not be confused.

### A. Chat memory

This is the running conversation inside ChatGPT.

Useful for:

- follow-up questions in the same session
- clarifying what Tom means by "that candidate" or "that company"

### B. Operational memory

This is the real business memory and should live in Supabase.

That includes:

- recruiter notes
- prior interactions
- linked documents
- company context
- previous stored conversation summaries if we decide to persist them

Recommended rule:

- ChatGPT session memory is convenience
- Supabase remains the source of truth

## Authentication Model

Tom should connect this through his ChatGPT Business workspace, but the app
itself still needs to enforce access.

Recommended V1:

- approved-workspace users only
- read-only MCP app
- server-side Supabase access via controlled backend credentials
- tool-level access restrictions enforced in the MCP app

That means ChatGPT Business becomes the interface, but our backend remains the
security boundary.

## Read-Only V1 Implementation Order

### Stage 1: MCP contract and adapter

- [x] Define the MCP tool schemas above.
- [x] Implement one MCP adapter service over the existing canonical services.
- [x] Expose the adapter through stateless Streamable HTTP at `/mcp`.
- [x] Keep every published MCP tool read-only.
- [x] Add a dedicated bearer credential, DNS-rebinding protection, a shared
  database-backed rate limit, and metadata-only audit events.

### Stage 2: Grounded recruiter Q&A

- [x] Implement `answer_recruiter_question`.
- [x] Route questions to:
  - candidate shortlist
  - candidate profile
  - company context
  - company lead discovery
- [x] Return citations and structured supporting entities.

The remote MCP release deliberately exposes the evidence-retrieval tools rather
than publishing a second reasoning tool. ChatGPT can reason over the returned
evidence directly, while the existing backend Q&A route remains available to
the application UI.

### Stage 3: Session memory

- [x] Keep lightweight conversation memory for follow-up questions in the
  application Q&A workflow.
- [x] Use per-user, per-conversation memory with a 12-hour TTL and a maximum of
  four retained turns.
- [ ] Decide whether approved conversation summaries should later become
  first-class recruiter interaction records.
- Memory options considered:
  - in-session only
  - persisted as summaries
  - persisted as first-class interaction rows

Recommended first cut:

- in-session memory first
- persisted summaries later if operationally useful

### Stage 4: Workspace rollout

- [ ] Connect the read-only MCP app to the approved ChatGPT Business workspace.
- [ ] Confirm which authentication options are exposed by that workspace's
  custom-app setup. Use the dedicated bearer credential where supported;
  otherwise add the platform's required OAuth flow rather than weakening auth.
- [ ] Restrict publication to approved workspace users.
- [ ] Validate the realistic recruiter prompts in the connection guide.

### Stage 5: Controlled write actions later

Only after the read-only path is trusted:

- save shortlist
- save recruiter note
- draft update for CRM
- draft outreach action

These should remain approval-gated.

## Rollout Order

### Phase A: Read-only assistant

- expose the MCP app
- enable candidate/company/contact/job/interaction retrieval
- answer grounded recruiter questions

### Phase B: Saved operational context

- persist approved conversation summaries or recruiter notes if useful
- allow the assistant to reference prior stored context more effectively

### Phase C: Approved write actions

Only after the read-only path is trusted:

- save shortlist
- create recruiter note
- draft outbound action
- propose CRM update

Write actions should remain human-approved.

## Why This Is Better Than Direct Database Access

Direct raw database exposure is the wrong boundary.

The MCP layer gives us:

- a stable contract for ChatGPT
- safer permissions
- cleaner schema abstraction
- room to change the Supabase schema without breaking Tom's assistant workflow
- easier auditing and future approval controls

## Immediate Build Tasks

- [x] Define the exact MCP tool request/response schemas.
- [x] Map each MCP tool to existing backend routes/services where possible.
- [x] Add any missing read services needed for company/contact/interaction lookup.
- [x] Add read-only bearer authentication, shared rate limiting, and metadata-only
  audit logging.
- [x] Implement bounded per-user application conversation memory with a 12-hour
  TTL and four-turn ceiling.
- [x] Produce a first test script with realistic recruiter prompts.
- [ ] Publish and validate the app in the ChatGPT Business workspace.

## Priority Note

This workflow is now a top-priority product direction because it aligns with
Tom's repeated request for:

- a ChatGPT-style interface
- grounded access to the canonical database
- memory of prior context
- minimal custom reasoning UI beyond what a strong LLM interface can already do
